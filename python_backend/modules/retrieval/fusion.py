from __future__ import annotations

import re


def fuse_evidence(rankings: list[list[str]], query: str, limit: int = 8) -> list[str]:
    """Reciprocal rank fusion with a lexical tie-breaker and parent-content deduplication."""
    candidates = {}
    for ranking in rankings:
        seen = set()
        for rank, content in enumerate(ranking, 1):
            key = re.sub(r'\s+', ' ', content).strip()
            if not key or key in seen:
                continue
            seen.add(key)
            item = candidates.setdefault(key, {'content': content, 'score': 0.0})
            item['score'] += 1 / (60 + rank)
    terms = re.findall(r'[A-Za-z0-9_]{2,}|[\u4e00-\u9fff]{2,}', query.casefold())
    def score(item):
        text = item['content'].casefold()
        matched = sum(term in text for term in terms)
        return item['score'], matched
    return [item['content'] for item in sorted(candidates.values(), key=score, reverse=True)[:limit]]
