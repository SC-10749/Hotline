"""审批策略判定：只有一个口径，risk-based 的高风险工具也要拦。

对应规格 S-013。
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ...infrastructure.governance_store import GovernanceStore
from .tools import approval_required, enforce_approval


class ApprovalPolicyTests(unittest.TestCase):
    def test_always_requires_approval(self):
        self.assertTrue(approval_required({'approval_policy': 'always', 'risk': 'low'}))

    def test_risk_based_requires_approval_for_high_risk(self):
        self.assertTrue(approval_required({'approval_policy': 'risk-based', 'risk': 'high'}))

    def test_risk_based_allows_low_risk(self):
        self.assertFalse(approval_required({'approval_policy': 'risk-based', 'risk': 'low'}))

    def test_required_uses_the_same_rule_as_risk_based(self):
        self.assertTrue(approval_required({'approval_policy': 'required', 'risk': 'high'}))
        self.assertFalse(approval_required({'approval_policy': 'required', 'risk': 'medium'}))

    def test_missing_or_unknown_policy_never_requires_approval(self):
        self.assertFalse(approval_required({}))
        self.assertFalse(approval_required({'approval_policy': 'unknown', 'risk': 'high'}))


class EnforceApprovalPolicyTests(unittest.TestCase):
    def test_risk_based_high_risk_creates_a_pending_request(self):
        temp = tempfile.TemporaryDirectory()
        try:
            path = Path(temp.name) / 'governance.db'
            store = GovernanceStore(path)
            with self.assertRaises(ValueError):
                enforce_approval('mcp_tool', {'path': 'x'},
                                  {'approval_policy': 'risk-based', 'risk': 'high'},
                                  run_id='run-1', governance_db=path, wait_seconds=1)
            pending = store.list('pending')
            self.assertEqual(len(pending), 1)
            self.assertEqual(pending[0]['tool'], 'mcp_tool')
            self.assertEqual(pending[0]['run_id'], 'run-1')
        finally:
            temp.cleanup()

    def test_risk_based_low_risk_is_not_blocked(self):
        temp = tempfile.TemporaryDirectory()
        try:
            path = Path(temp.name) / 'governance.db'
            store = GovernanceStore(path)
            enforce_approval('mcp_tool', {}, {'approval_policy': 'risk-based', 'risk': 'low'},
                              run_id='run-1', governance_db=path, wait_seconds=1)
            self.assertEqual(store.list('pending'), [])
        finally:
            temp.cleanup()
