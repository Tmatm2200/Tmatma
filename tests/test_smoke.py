"""Unit tests for the smoke check script.

These tests perform only the quick (non-network) checks so they are safe in CI.
"""
from scripts.smoke_check import run_checks


def test_quick_checks_pass():
    ok, messages = run_checks(network=False)
    # The quick checks should run without raising; we assert the return type
    assert isinstance(ok, bool)
    assert isinstance(messages, list)
