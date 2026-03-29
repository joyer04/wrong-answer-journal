"""
tests/test_app.py
==================
Integration tests for FastAPI endpoints using TestClient.
No real API calls are made — analyze_math_problem is mocked where needed.
"""

import io
import os
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch

# Set a fake API key before importing the app so the module loads without error
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test-key")

from app import app

client = TestClient(app)

MOCK_RESULT = {
    "problem_text": "x² - 5x + 6 = 0",
    "problem_type": "quadratic",
    "difficulty": "중3",
    "solution": {
        "steps": ["인수분해: (x-2)(x-3) = 0", "x = 2 또는 x = 3"],
        "final_answer": "x = 2, x = 3",
    },
    "concept": {
        "title": "이차방정식",
        "definition": "ax² + bx + c = 0",
        "key_points": ["근의 공식", "인수분해"],
        "formulas": ["x = (-b ± √(b²-4ac)) / 2a"],
        "common_mistakes": ["부호 실수"],
        "tip": "판별식 D = b²-4ac",
    },
    "similar_problems": [],
}


class TestHealthEndpoint:
    def test_health_ok(self):
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "api_key_set" in data


class TestAnalyzeEndpoint:
    @patch("app.analyze_math_problem", new_callable=AsyncMock, return_value=MOCK_RESULT)
    def test_text_input(self, mock_analyze):
        response = client.post(
            "/api/analyze",
            data={"text": "x² - 5x + 6 = 0을 풀어라", "language": "korean"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["problem_type"] == "quadratic"

    def test_missing_input_returns_400(self):
        response = client.post("/api/analyze", data={"language": "korean"})
        assert response.status_code == 400

    def test_invalid_language_returns_422(self):
        response = client.post(
            "/api/analyze",
            data={"text": "문제", "language": "klingon"},
        )
        assert response.status_code == 422

    def test_text_too_long_returns_422(self):
        long_text = "x" * 2001
        response = client.post(
            "/api/analyze",
            data={"text": long_text, "language": "korean"},
        )
        assert response.status_code == 422

    def test_image_too_large_returns_413(self):
        large_bytes = b"\xff\xd8\xff" + b"x" * (10 * 1024 * 1024 + 1)
        response = client.post(
            "/api/analyze",
            data={"language": "korean"},
            files={"image": ("big.jpg", io.BytesIO(large_bytes), "image/jpeg")},
        )
        assert response.status_code == 413

    def test_invalid_file_type_returns_415(self):
        response = client.post(
            "/api/analyze",
            data={"language": "korean"},
            files={"image": ("test.exe", io.BytesIO(b"MZ\x90\x00bad"), "image/jpeg")},
        )
        assert response.status_code == 415

    @patch("app.analyze_math_problem", new_callable=AsyncMock, return_value=MOCK_RESULT)
    def test_empty_text_treated_as_none(self, mock_analyze):
        # Whitespace-only text without image should be treated as missing → 400
        response = client.post("/api/analyze", data={"text": "   ", "language": "korean"})
        assert response.status_code == 400


class TestIndexPage:
    def test_index_returns_html(self):
        response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "오답노트" in response.text
