"""
tests/test_ai_service.py
========================
Unit tests for pure utility functions in services/ai_service.py.
No Claude API calls are made — only _strip_code_fence and _extract_json are tested.
"""

import json
import pytest
from services.ai_service import _strip_code_fence, _extract_json


class TestStripCodeFence:
    def test_no_fence(self):
        assert _strip_code_fence('{"a": 1}') == '{"a": 1}'

    def test_json_fence(self):
        result = _strip_code_fence('```json\n{"a": 1}\n```')
        assert result == '{"a": 1}'

    def test_plain_fence(self):
        result = _strip_code_fence('```\n{"a": 1}\n```')
        assert result == '{"a": 1}'

    def test_fence_no_closing(self):
        result = _strip_code_fence('```json\n{"a": 1}')
        assert result == '{"a": 1}'

    def test_whitespace_preserved(self):
        result = _strip_code_fence('```json\n{"a": 1, "b": 2}\n```')
        assert '"a"' in result and '"b"' in result

    def test_non_fence_with_backtick_content(self):
        text = '{"code": "`x + 1`"}'
        assert _strip_code_fence(text) == text


class TestExtractJson:
    def test_clean_json(self):
        result = _extract_json('{"key": "value"}')
        assert result == '{"key": "value"}'

    def test_json_with_preamble(self):
        result = _extract_json('Here is the JSON:\n{"key": "value"}\nDone.')
        assert result == '{"key": "value"}'

    def test_nested_json(self):
        text = '{"a": {"b": 1}}'
        result = _extract_json(text)
        assert result == '{"a": {"b": 1}}'

    def test_no_json(self):
        assert _extract_json('no json here') is None

    def test_complex_nested(self):
        text = 'prefix {"steps": ["step 1", "step 2"], "answer": "42"} suffix'
        extracted = _extract_json(text)
        parsed = json.loads(extracted)
        assert parsed['answer'] == '42'
        assert len(parsed['steps']) == 2

    def test_unbalanced_brace(self):
        # Only one { — should return None (can't find closing })
        result = _extract_json('{"a": 1')
        assert result is None
