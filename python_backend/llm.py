from __future__ import annotations

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI

from .config import Settings


def build_chat_model(settings: Settings) -> BaseChatModel:
    if not settings.model_api_key or not settings.model_name or not settings.model_base_url:
        raise ValueError('未配置模型，无法执行技能。')
    return ChatOpenAI(
        model=settings.model_name,
        api_key=settings.model_api_key,
        base_url=settings.model_base_url.rstrip('/'),
        temperature=0.2,
        timeout=90,
        max_retries=0,
        cache=False,
    )
