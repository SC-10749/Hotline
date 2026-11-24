from __future__ import annotations

import csv
import io
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from ...config import settings
from ...modules.execution.store import event_level, event_tool

RUN_STATUSES = ('queued', 'running', 'completed', 'failed', 'cancelled')
EXPORT_COLUMNS = ('run_id', 'event_id', 'created_at', 'type', 'level', 'tool', 'status', 'summary')
SUMMARY_LIMIT = 200
BUCKETS = ('hour', 'day')


def _parse_timestamp(value: str) -> datetime | None:
    text = str(value or '').strip()
    if not text:
        return None
    if text.endswith('Z'):
        text = text[:-1] + '+00:00'
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return None
    return moment.replace(tzinfo=timezone.utc) if moment.tzinfo is None else moment.astimezone(timezone.utc)


def _bucket_start(moment: datetime, bucket: str) -> datetime:
    if bucket == 'day':
        return moment.replace(hour=0, minute=0, second=0, microsecond=0)
    return moment.replace(minute=0, second=0, microsecond=0)


def _bucket_label(moment: datetime) -> str:
    return moment.strftime('%Y-%m-%dT%H:%M:%SZ')


def _summary(event: dict[str, Any]) -> str:
    content = event.get('content')
    if isinstance(content, str):
        text = content
    elif content is None:
        text = ''
    else:
        text = json.dumps(content, ensure_ascii=False)
    return ' '.join(text.split())[:SUMMARY_LIMIT]


def _event_row(row: sqlite3.Row) -> dict[str, Any]:
    try:
        event = json.loads(row['event_json'])
    except (TypeError, ValueError):
        event = {}
    if not isinstance(event, dict):
        event = {}
    return {'run_id': row['run_id'], 'event_id': row['event_id'], 'created_at': row['created_at'],
            'type': event.get('type') or '', 'level': event_level(event), 'tool': event_tool(event),
            'status': event.get('status') or '', 'summary': _summary(event)}


def _open_readonly(path: Path) -> sqlite3.Connection | None:
    """Read-only handle on the execution database; a missing file means no data."""
    try:
        if not Path(path).is_file():
            return None
        db = sqlite3.connect(f"{Path(path).resolve().as_uri()}?mode=ro", uri=True, timeout=30)
    except sqlite3.Error:
        return None
    db.row_factory = sqlite3.Row
    return db


def create_observability_router(
    list_runs: Callable[..., tuple[list[dict[str, Any]], int]],
    get_run: Callable[[str], dict[str, Any] | None],
    get_events: Callable[..., list[dict[str, Any]]],
    execution_db_path: Path | None = None,
) -> APIRouter:
    router = APIRouter()
    db_path = Path(execution_db_path) if execution_db_path else Path(settings.execution_db_path)

    @router.get('/harness/observability/runs')
    def observability_runs(limit: int = Query(100, ge=1, le=200)):
        items, total = list_runs(limit=limit)
        return {'items': items, 'total': total}

    @router.get('/harness/observability/runs/{run_id}/events')
    def observability_events(run_id: str, after: int = Query(0, ge=0),
                             level: str | None = None, tool: str | None = None,
                             hasError: bool | None = None, since: str | None = None,
                             until: str | None = None, type: str | None = None):
        if not get_run(run_id):
            return {'items': []}
        return {'items': get_events(run_id, after, level=level, tool=tool, has_error=hasError,
                                    since=since, until=until, event_type=type)}

    @router.get('/harness/observability/metrics')
    def observability_metrics(limit: int = Query(100, ge=1, le=200)):
        runs, total = list_runs(limit=limit)
        by_status = {status: list_runs(status=status, limit=1)[1] for status in RUN_STATUSES}
        errors = 0
        tool_calls = 0
        for run in runs:
            for item in get_events(run['run_id']):
                event = item.get('event') or {}
                if event_level(event) == 'error':
                    errors += 1
                if event.get('type') == 'tool_start':
                    tool_calls += 1
        recent = [{'run_id': run['run_id'], 'status': run['status'], 'created_at': run['created_at']}
                  for run in runs[:10]]
        return {'runs': total, 'byStatus': by_status, 'errors': errors, 'toolCalls': tool_calls,
                'recentRuns': recent, 'limit': limit}

    @router.get('/harness/observability/runs/{run_id}/export')
    def observability_export(run_id: str):
        run = get_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail='运行不存在')
        payload = {'runId': run_id, 'status': run.get('status'),
                   'created_at': run.get('created_at'), 'events': get_events(run_id)}
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode('utf-8')
        filename = re.sub(r'[^A-Za-z0-9_-]', '_', run_id) or 'run'
        return Response(content=body, media_type='application/json; charset=utf-8',
                        headers={'Content-Disposition': f'attachment; filename="{filename}-trace.json"'})

    @router.get('/harness/observability/exports')
    def observability_exports(from_: str | None = Query(None, alias='from'), to: str | None = None,
                              runId: str | None = None, format_: str = Query('json', alias='format'),
                              limit: int = Query(1000, ge=1, le=10000)):
        """Cross-run event export; JSON by default, CSV on request."""
        if format_ not in {'json', 'csv'}:
            raise HTTPException(status_code=400, detail='导出格式只支持 json 或 csv')
        clauses, params = [], []
        if runId:
            clauses.append('run_id=?')
            params.append(runId)
        for value, operator in ((from_, '>='), (to, '<=')):
            if not value:
                continue
            moment = _parse_timestamp(value)
            if moment is None:
                raise HTTPException(status_code=400, detail='时间参数必须是 ISO 格式')
            clauses.append(f'created_at{operator}?')
            params.append(moment.strftime('%Y-%m-%dT%H:%M:%SZ'))
        where = (' WHERE ' + ' AND '.join(clauses)) if clauses else ''
        db = _open_readonly(db_path)
        if db is None:
            items, total = [], 0
        else:
            try:
                total = db.execute(f'SELECT COUNT(*) FROM execution_event{where}', params).fetchone()[0]
                rows = db.execute(
                    f'SELECT run_id,event_id,created_at,event_json FROM execution_event{where} '
                    'ORDER BY created_at, event_id LIMIT ?', [*params, limit]).fetchall()
                items = [_event_row(row) for row in rows]
            except sqlite3.Error as exc:
                raise HTTPException(status_code=503, detail='执行日志暂不可用') from exc
            finally:
                db.close()
        truncated = total > len(items)
        if format_ == 'csv':
            buffer = io.StringIO()
            writer = csv.DictWriter(buffer, fieldnames=list(EXPORT_COLUMNS))
            writer.writeheader()
            writer.writerows(items)
            return Response(content=buffer.getvalue(), media_type='text/csv; charset=utf-8',
                            headers={'Content-Disposition': 'attachment; filename="harness-events.csv"',
                                     'X-Harness-Total': str(total),
                                     'X-Harness-Truncated': str(truncated).lower()})
        return {'items': items, 'total': total, 'limit': limit, 'truncated': truncated}

    @router.get('/harness/observability/trends')
    def observability_trends(bucket: str = Query('hour'), limit: int = Query(24, ge=1, le=720)):
        """Bucket runs and events over time; empty input yields no points at all."""
        if bucket not in BUCKETS:
            raise HTTPException(status_code=400, detail='bucket 只支持 hour 或 day')
        points: dict[str, dict[str, Any]] = {}
        db = _open_readonly(db_path)
        if db is None:
            return {'bucket': bucket, 'points': []}

        def point(label: str) -> dict[str, Any]:
            return points.setdefault(label, {'bucketStart': label, 'runs': 0, 'completed': 0,
                                             'failed': 0, 'cancelled': 0, 'errors': 0, 'toolCalls': 0})

        try:
            for row in db.execute('SELECT created_at,status FROM execution_run'):
                moment = _parse_timestamp(row['created_at'])
                if not moment:
                    continue
                entry = point(_bucket_label(_bucket_start(moment, bucket)))
                entry['runs'] += 1
                status = row['status']
                if status in {'completed', 'failed', 'cancelled'}:
                    entry[status] += 1
            for row in db.execute('SELECT created_at,event_json FROM execution_event'):
                moment = _parse_timestamp(row['created_at'])
                if not moment:
                    continue
                try:
                    event = json.loads(row['event_json'])
                except (TypeError, ValueError):
                    continue
                if not isinstance(event, dict):
                    continue
                entry = point(_bucket_label(_bucket_start(moment, bucket)))
                if event_level(event) == 'error':
                    entry['errors'] += 1
                if event.get('type') == 'tool_start':
                    entry['toolCalls'] += 1
        except sqlite3.Error as exc:
            raise HTTPException(status_code=503, detail='执行日志暂不可用') from exc
        finally:
            db.close()
        # Only buckets carrying data are reported, newest ones first up to the limit.
        labels = sorted(points)[-limit:]
        return {'bucket': bucket, 'points': [points[label] for label in labels]}

    return router
