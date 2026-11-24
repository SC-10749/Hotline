"""共享密钥鉴权：未配置时放行一切，配置后要求正确的请求头。

对应规格 S-007。
"""

from __future__ import annotations

import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from python_backend.api.auth import TOKEN_HEADER, build_auth_middleware


def make_app(token: str) -> FastAPI:
    app = FastAPI()
    app.add_middleware(build_auth_middleware(token))

    @app.get('/health')
    def health():
        return {'status': 'UP'}

    @app.get('/harness/profile/credentials')
    def credentials():
        return {'credential': {'provider': 'demo'}}

    return app


class AuthMiddlewareTests(unittest.TestCase):
    def test_disabled_when_token_is_empty(self):
        client = TestClient(make_app(''))
        self.assertEqual(client.get('/harness/profile/credentials').status_code, 200)

    def test_missing_token_is_rejected(self):
        client = TestClient(make_app('secret'))
        response = client.get('/harness/profile/credentials')
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()['code'], 'UNAUTHORIZED')

    def test_wrong_token_is_rejected(self):
        client = TestClient(make_app('secret'))
        response = client.get('/harness/profile/credentials', headers={TOKEN_HEADER: 'nope'})
        self.assertEqual(response.status_code, 401)

    def test_correct_token_is_accepted(self):
        client = TestClient(make_app('secret'))
        response = client.get('/harness/profile/credentials', headers={TOKEN_HEADER: 'secret'})
        self.assertEqual(response.status_code, 200)

    def test_health_endpoints_stay_public(self):
        client = TestClient(make_app('secret'))
        self.assertEqual(client.get('/health').status_code, 200)

    def test_token_check_is_case_sensitive(self):
        client = TestClient(make_app('secret'))
        response = client.get('/harness/profile/credentials', headers={TOKEN_HEADER: 'SECRET'})
        self.assertEqual(response.status_code, 401)


if __name__ == '__main__':
    unittest.main()
