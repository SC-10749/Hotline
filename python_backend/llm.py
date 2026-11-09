from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_openai import ChatOpenAI

from pathlib import Path

from .config import Settings
from .infrastructure.credential_store import CredentialStore
from .infrastructure.registry_store import RegistryStore

logger = logging.getLogger(__name__)

REGISTRY_DB_NAME = 'harness-registry.db'


class FallbackChatModel(ChatOpenAI):
    """主模型调用失败时，按顺序回退到已登记的备用模型。

    备用模型复用同一套凭据与 base_url，只替换模型名；回退发生时记录一次事件。
    """

    fallback_models: list[Any] = []
    bound_fallbacks: list[Any] = []
    fallback_callback: Any = None

    def bind_tools(self, tools, *, tool_choice=None, **kwargs):
        bound = super().bind_tools(tools, tool_choice=tool_choice, **kwargs)
        # 备用模型必须带上同一批工具，否则回退后模型无法继续工具调用。
        self.bound_fallbacks = [
            model.bind_tools(tools, tool_choice=tool_choice, **kwargs) for model in self.fallback_models
        ]
        return bound

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        try:
            return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
        except Exception as exc:
            call_kwargs = {key: value for key, value in kwargs.items() if key not in {'tools', 'tool_choice'}}
            last_error = exc
            for index, fallback in enumerate(self.bound_fallbacks or self.fallback_models):
                try:
                    message = fallback.invoke(messages, stop=stop, **call_kwargs)
                except Exception as fallback_error:
                    last_error = fallback_error
                    continue
                self._record_fallback(index, fallback, exc)
                return ChatResult(generations=[ChatGeneration(message=message)])
            raise last_error

    def _record_fallback(self, index: int, fallback: Any, cause: BaseException) -> None:
        name = getattr(fallback, 'model_name', '') or getattr(fallback, 'model', '') or f'fallback-{index + 1}'
        logger.warning('主模型调用失败，已回退到备用模型 %s（原异常：%s）', name, type(cause).__name__)
        if callable(self.fallback_callback):
            self.fallback_callback({'fallback': name, 'index': index, 'error': type(cause).__name__})


def model_config(settings: Settings) -> dict[str, str]:
    """模型连接参数：用户在本机保存的凭证优先于环境变量。"""
    config = {'api_key': getattr(settings, 'model_api_key', '') or '',
              'base_url': getattr(settings, 'model_base_url', '') or '',
              'model': getattr(settings, 'model_name', '') or ''}
    data_dir = getattr(settings, 'data_dir', None)
    credential = None
    if data_dir is not None:
        try:
            credential = CredentialStore(Path(data_dir) / 'harness-credentials.db').get()
        except Exception:
            credential = None
    if credential and credential.get('api_key'):
        config['api_key'] = credential['api_key']
        config['base_url'] = credential.get('base_url') or config['base_url']
        config['model'] = credential.get('model') or config['model']
    return config


def model_ready(settings: Settings) -> bool:
    """是否已有可用凭证：本机保存的凭证优先，其次环境变量。"""
    return bool(model_config(settings)['api_key'])


def _client_kwargs(config: dict[str, str], model_name: str) -> dict[str, Any]:
    return {
        'model': model_name,
        'api_key': config['api_key'],
        'base_url': config['base_url'].rstrip('/'),
        'temperature': 0.2,
        'timeout': 90,
        'max_retries': 0,
        'cache': False,
    }


def _fallback_clients(config: dict[str, str], model_ids: Sequence[str],
                        data_dir: Path) -> list[ChatOpenAI]:
    if not model_ids:
        return []
    path = Path(data_dir) / REGISTRY_DB_NAME
    if not path.exists():
        return []
    store = RegistryStore(path)
    clients: list[ChatOpenAI] = []
    for model_id in model_ids:
        row = store.get_model(model_id)
        if not row:
            continue
        name = str(row.get('name') or '').strip()
        if not name:
            continue
        clients.append(ChatOpenAI(**_client_kwargs(config, name)))
    return clients


def build_chat_model(settings: Settings,
                     fallback_model_ids: Sequence[str] | None = None,
                     on_fallback: Callable[[dict], None] | None = None) -> BaseChatModel:
    config = model_config(settings)
    if not config['api_key'] or not config['model'] or not config['base_url']:
        raise ValueError('未配置模型，无法执行技能。')
    fallbacks = _fallback_clients(config, fallback_model_ids or [],
                                  getattr(settings, 'data_dir', 'data'))
    if not fallbacks:
        return ChatOpenAI(**_client_kwargs(config, config['model']))
    return FallbackChatModel(**_client_kwargs(config, config['model']),
                             fallback_models=fallbacks,
                             fallback_callback=on_fallback)


def probe_credentials(api_key: str, base_url: str, model: str) -> dict[str, Any]:
    """用给定凭证发一次极短请求，验证连通性。失败只回显异常类型。"""
    if not api_key or not model or not base_url:
        return {'ok': False, 'message': '未配置模型凭据，无法测试'}
    try:
        client = ChatOpenAI(model=model, api_key=api_key, base_url=base_url.rstrip('/'),
                             temperature=0, timeout=20, max_retries=0, cache=False)
        client.invoke([HumanMessage(content='ping')], max_tokens=1)
    except Exception as exc:
        return {'ok': False, 'message': f'模型连接失败：{type(exc).__name__}'}
    return {'ok': True, 'message': '连接正常', 'details': {'model': model}}


def probe_credential(credential: dict[str, str]) -> dict[str, Any]:
    return probe_credentials(credential.get('api_key', ''), credential.get('base_url', ''),
                             credential.get('model', ''))


def probe_model(settings: Settings) -> dict[str, Any]:
    """用当前模型配置发一次极短请求，验证路由是否可用。失败只回显异常类型。"""
    config = model_config(settings)
    return probe_credentials(config['api_key'], config['base_url'], config['model'])
