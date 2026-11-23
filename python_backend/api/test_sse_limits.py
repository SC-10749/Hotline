"""SSE 空闲超时与共享并发限额。

对应规格 S-009：长时间没有事件的流要主动结束，避免连接与线程长期挂着；
同时打开的流超过上限时直接拒绝新连接。
"""

from __future__ import annotations

import unittest

from python_backend.api.routers.execution import (SseLimitExceeded, SseLimiter,
                                                 sse_idle_timeout_seconds)


class SseLimiterTests(unittest.TestCase):
    def test_limit_is_not_reached_below_cap(self):
        limiter = SseLimiter(2)
        with limiter.slot():
            with limiter.slot():
                pass

    def test_limit_rejects_the_third_holder(self):
        limiter = SseLimiter(2)
        with limiter.slot():
            with limiter.slot():
                with self.assertRaises(SseLimitExceeded):
                    with limiter.slot():
                        pass

    def test_slot_is_released_when_the_stream_ends(self):
        limiter = SseLimiter(1)
        with limiter.slot():
            pass
        # 释放后可以再次占用。
        with limiter.slot():
            pass

    def test_zero_limit_disables_the_check(self):
        limiter = SseLimiter(0)
        with limiter.slot():
            with limiter.slot():
                with limiter.slot():
                    pass


class SseIdleTimeoutTests(unittest.TestCase):
    def test_zero_disables_the_timeout(self):
        self.assertEqual(sse_idle_timeout_seconds(0), 0.0)

    def test_positive_value_is_kept(self):
        self.assertEqual(sse_idle_timeout_seconds(90), 90.0)


if __name__ == '__main__':
    unittest.main()
