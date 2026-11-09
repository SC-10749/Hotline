"""Bounded, source-addressable summaries built without external model calls."""
from __future__ import annotations

import json
import re


GLOBAL_QUERY = re.compile(r'全局|整体|总览|全貌|所有|全部|跨文档|汇总|总结|overview|summari[sz]e', re.I)


def source_layers(source_id: str, chunks: list[str]) -> tuple[str, str]:
    texts = [text.strip() for text in chunks if text and text.strip()]
    if not texts:
        return '', ''
    positions = sorted({round(index * (len(texts) - 1) / 15) for index in range(16)})
    sections = [{'source': f'{source_id}#{index}', 'preview': texts[index][:180]}
                for index in positions]
    abstract = texts[0].replace('\n', ' ')[:256]
    overview = json.dumps({'source': source_id, 'method': 'extractive', 'sectionCount': len(texts),
                           'sampledSections': sections, 'coveredSections': len(sections)}, ensure_ascii=False)
    return abstract, overview
