"""共享密钥鉴权中间件。

对应规格 S-008：配置为空时放行一切；配置后要求请求带正确的 X-Hotline-Token。
健康检查放行，供探针与 Java 就绪探测使用。
"""

from __future__ import annotations

import hmac

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

TOKEN_HEADER = 'X-Hotline-Token'

# 匿名可访问的路径前缀：健康检查用于探针与 Java 就绪探测。
PUBLIC_PATHS = ('/health',)


def _is_public(path: str) -> bool:
    return any(path == item or path.startswith(item + '/') for item in PUBLIC_PATHS)


def build_auth_middleware(token: str):
    """构造校验共享密钥的中间件；token 为空表示不启用。"""
    expected = (token or '').strip()

    class SharedTokenMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            if not expected or _is_public(request.url.path):
                return await call_next(request)
            presented = request.headers.get(TOKEN_HEADER, '')
            # 恒定时间比较，避免时序侧信道。
            if not hmac.compare_digest(presented, expected):
                return JSONResponse(
                    {'code': 'UNAUTHORIZED', 'message': '缺少或无效的访问令牌'},
                    status_code=401,
                )
            return await call_next(request)

    return SharedTokenMiddleware
