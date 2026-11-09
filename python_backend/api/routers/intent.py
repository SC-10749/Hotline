"""意图识别接口：识别一次提问的意图与置信度。"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from ...modules.intent import (ACTION_CATALOG, RETRIEVAL_CATALOG, ExampleVectorStore,
                               classify)


class IntentRequest(BaseModel):
    query: str
    scope: str = 'action'   # action（顶层动作）| retrieval（检索链路）


def create_intent_router(chat=None, vectors: dict[str, ExampleVectorStore] | None = None) -> APIRouter:
    """chat 为可选的模型调用入口；vectors 为按 scope 缓存的向量层。"""
    router = APIRouter()

    @router.get('/intent/catalogs')
    def intent_catalogs():
        return {
            'items': [
                {'scope': catalog.name, 'default': catalog.default,
                 'intents': [{'name': item.name, 'label': item.label,
                              'description': item.description}
                             for item in catalog.intents]}
                for catalog in (ACTION_CATALOG, RETRIEVAL_CATALOG)
            ]
        }

    @router.post('/intent/classify')
    def classify_intent(payload: IntentRequest):
        catalog = RETRIEVAL_CATALOG if payload.scope == 'retrieval' else ACTION_CATALOG
        store = (vectors or {}).get(catalog.name)
        result = classify(payload.query, catalog, chat, vectors=store)
        return {
            'scope': catalog.name,
            'intent': result.intent,
            'label': result.label,
            'confidence': result.confidence,
            'source': result.source,
            'tier': result.tier,
            'needsClarification': result.needs_clarification,
            'candidates': list(result.candidates),
        }

    return router