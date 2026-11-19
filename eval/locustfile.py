"""Explicit HTTP/SSE scenarios; loaded only by the separate Locust process."""
import json
import os
import time
from pathlib import Path
from uuid import uuid4

from locust import HttpUser, between, events, task
from sse_metrics import events as sse_events, percentile

OUTPUT = Path(os.environ.get('HOTLINE_LOAD_OUTPUT', 'data/load-tests'))
PROFILE = os.environ.get('HOTLINE_LOAD_PROFILE', 'http')
TIMINGS = {'firstEventMs': [], 'firstTextMs': [], 'completionMs': []}
COUNTS = {'completed': 0, 'failed': 0}


@events.quitting.add_listener
def summary(environment, **kwargs):
    OUTPUT.mkdir(parents=True, exist_ok=True)
    payload = {**COUNTS, 'timings': {key: {'count': len(values), 'p50': percentile(values, .5),
        'p95': percentile(values, .95), 'p99': percentile(values, .99)} for key, values in TIMINGS.items()}}
    (OUTPUT / 'stream-summary.json').write_text(json.dumps(payload), 'utf-8')
    name = 'SSE task' if PROFILE == 'sse' else 'HTTP readiness'
    stat = environment.stats.get(name, 'GET')
    count, failures = stat.num_requests, stat.num_failures
    final = {'requestCount': count, 'failureCount': failures,
             'errorRate': failures / count if count else None,
             'requestsPerSecond': stat.total_rps,
             'p50Ms': stat.get_response_time_percentile(.5) if count else None,
             'p95Ms': stat.get_response_time_percentile(.95) if count else None,
             'p99Ms': stat.get_response_time_percentile(.99) if count else None}
    (OUTPUT / 'load-summary.json').write_text(json.dumps(final), 'utf-8')


class HotlineUser(HttpUser):
    wait_time = between(.5, 1)

    def on_start(self):
        self.conversation = ''
        OUTPUT.mkdir(parents=True, exist_ok=True)
        self.active = OUTPUT / f'active-{uuid4().hex}.json'

    def on_stop(self):
        if self.conversation:
            self.client.get('/agent/stop', params={'conversationId': self.conversation}, timeout=3, name='cancel unfinished task')
        self.active.unlink(missing_ok=True)

    @task
    def request(self):
        if PROFILE == 'http':
            self.client.get('/health/ready', name='HTTP readiness', timeout=10)
            return
        started = time.perf_counter()
        self.conversation = 'load-' + uuid4().hex
        self.active.write_text(json.dumps({'conversationId': self.conversation}), 'utf-8')
        completed, first, text = False, False, False
        try:
            with self.client.get('/agent/chat/stream', params={'conversationId': self.conversation,
                    'query': '请只回答：测试成功'}, stream=True, timeout=(10, 90),
                    catch_response=True, name='SSE task') as response:
                if response.status_code != 200:
                    response.failure(f'HTTP {response.status_code}')
                    return
                for event in sse_events(response.iter_lines(chunk_size=1)):
                    elapsed = (time.perf_counter() - started) * 1000
                    if not first:
                        TIMINGS['firstEventMs'].append(elapsed)
                        first = True
                    if event.get('type') == 'text' and event.get('content') and not text:
                        TIMINGS['firstTextMs'].append(elapsed)
                        text = True
                    if event.get('type') in {'error', 'clarify'}:
                        completed = False
                        response.failure('Agent failed or requested clarification')
                        break
                    if event.get('type') == 'complete':
                        completed = True
                        TIMINGS['completionMs'].append(elapsed)
                    if event.get('type') == 'done':
                        break
                if not completed:
                    response.failure('SSE ended without successful completion')
                response.request_meta['response_time'] = (time.perf_counter() - started) * 1000
        finally:
            COUNTS['completed' if completed else 'failed'] += 1
            if not completed:
                self.client.get('/agent/stop', params={'conversationId': self.conversation}, timeout=3,
                                name='cancel unfinished task')
            self.conversation = ''
            self.active.unlink(missing_ok=True)
