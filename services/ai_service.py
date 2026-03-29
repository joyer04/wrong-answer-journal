"""
services/ai_service.py
======================
Claude API integration for math problem analysis.

Sends the problem (image and/or text) to Claude claude-opus-4-6 and returns a
structured JSON result containing the solution, concept explanation in
개념원리 style, and three similar practice problems.
"""

from __future__ import annotations

import json
import os
import re
from typing import Optional

from anthropic import AsyncAnthropic

# Lazy client: created on first call so load_dotenv() always runs first.
_client: AsyncAnthropic | None = None


class AIParseError(ValueError):
    """Raised when Claude's response cannot be parsed as JSON."""


def _get_client() -> AsyncAnthropic:
    global _client
    if _client is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY 환경 변수가 설정되지 않았습니다.")
        _client = AsyncAnthropic(api_key=api_key)
    return _client


LANGUAGE_INSTRUCTIONS: dict[str, str] = {
    "korean":   "모든 응답을 한국어로 작성하세요.",
    "english":  "Write all responses in English.",
    "chinese":  "请用中文回答所有内容。",
    "japanese": "すべての回答を日本語で書いてください。",
}

# ---------------------------------------------------------------------------
# System prompt — instructs Claude to behave as a 개념원리-level tutor and
# to return strict JSON only.
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """You are an expert Korean high-school mathematics tutor at the 개념원리 (Concept & Principle) textbook level.

You MUST return ONLY a single valid JSON object — no markdown, no code fences, no preamble, no trailing text.

The JSON must follow this exact schema:

{
  "problem_text": "Full problem statement as a string",
  "problem_type": "one of: arithmetic | linear_equation | quadratic | function | geometry | trigonometry | calculus | statistics | other",
  "difficulty": "one of: 중1 | 중2 | 중3 | 고1 | 고2 | 고3",
  "solution": {
    "steps": ["Step 1: ...", "Step 2: ...", "Step 3: ..."],
    "final_answer": "The final answer as a string"
  },
  "concept": {
    "title": "Name of the core concept",
    "definition": "Formal definition. Use LaTeX inline math with \\( ... \\) and display math with \\[ ... \\]",
    "key_points": ["Key point 1", "Key point 2", "Key point 3"],
    "formulas": ["Formula 1 in LaTeX", "Formula 2 in LaTeX"],
    "common_mistakes": ["Common mistake 1", "Common mistake 2"],
    "tip": "A short memorable tip or mnemonic"
  },
  "similar_problems": [
    {
      "number": 1,
      "question": "Problem statement",
      "answer": "Answer as a string",
      "solution_steps": ["Step 1", "Step 2"],
      "diagram": {
        "type": "none"
      }
    },
    {
      "number": 2,
      "question": "Problem statement",
      "answer": "Answer as a string",
      "solution_steps": ["Step 1", "Step 2"],
      "diagram": {
        "type": "function_graph",
        "title": "Graph title",
        "functions": [
          {"expr": "x**2 - 4", "label": "f(x) = x² - 4", "color": "#2563eb"}
        ],
        "x_range": [-4, 4],
        "y_range": [-6, 6],
        "points": [
          {"x": 2, "y": 0, "label": "(2, 0)"},
          {"x": -2, "y": 0, "label": "(-2, 0)"}
        ]
      }
    },
    {
      "number": 3,
      "question": "Problem statement",
      "answer": "Answer as a string",
      "solution_steps": ["Step 1", "Step 2"],
      "diagram": {
        "type": "triangle",
        "title": "Triangle diagram",
        "vertices": {"A": [0, 0], "B": [4, 0], "C": [2, 3]},
        "labels": {"AB": "4", "BC": "√13", "CA": "√13"},
        "right_angle_at": null
      }
    }
  ]
}

Diagram type rules:
- "none"           → no diagram
- "function_graph" → use for functions/equations that should be graphed.
                     IMPORTANT: expr must use only: numbers, the variable x,
                     basic arithmetic operators (+ - * / **), and sympy-compatible
                     functions (sqrt, sin, cos, tan, exp, log, Abs).
                     No imports, no attribute access, no builtins, no semicolons.
                     Example valid exprs: "x**2 - 3*x + 2", "sqrt(x)", "sin(x)"
- "triangle"       → for geometry triangle problems;
                     vertices are [x, y] coordinates scaled for clarity
- "circle"         → for circle geometry; include center [x,y] and radius (number),
                     optional points array with {angle_deg, label}
- "number_line"    → for inequalities / number-line problems;
                     include range [min, max] and points array with
                     {x, label, type: "open"|"closed"}

Only include a diagram when it genuinely helps understand the problem.
Provide exactly 3 similar problems; vary difficulty slightly across the three."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def analyze_math_problem(
    *,
    image_base64: Optional[str],
    media_type: str,
    text: Optional[str],
    language: str = "korean",
) -> dict:
    """Call Claude and return a parsed analysis dict."""

    lang_instruction = LANGUAGE_INSTRUCTIONS.get(language, LANGUAGE_INSTRUCTIONS["korean"])

    # Build the user message content blocks
    content: list[dict] = []

    if image_base64:
        content.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": image_base64,
                },
            }
        )

    user_text = f"{lang_instruction}\n\n"
    if text:
        user_text += f"문제:\n{text}"
    elif image_base64:
        user_text += "위 이미지의 수학 문제를 읽고 분석해주세요."

    content.append({"type": "text", "text": user_text})

    response = await _get_client().messages.create(
        model="claude-opus-4-6",
        max_tokens=4096,
        timeout=90.0,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": content}],
    )

    raw = response.content[0].text.strip()

    # Strip any accidental markdown code fences
    raw = _strip_code_fence(raw)

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        # Attempt a best-effort extraction of the outermost JSON object
        extracted = _extract_json(raw)
        if extracted:
            try:
                return json.loads(extracted)
            except json.JSONDecodeError:
                pass
        raise AIParseError(
            f"Claude returned non-JSON response. Raw (first 500 chars):\n{raw[:500]}"
        ) from exc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_code_fence(text: str) -> str:
    """Remove ```json ... ``` or ``` ... ``` wrappers if present."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        # Drop opening fence line (```json or ```)
        inner = lines[1:]
        # Drop closing fence line if present
        if inner and inner[-1].strip() == "```":
            inner = inner[:-1]
        text = "\n".join(inner).strip()
    return text


def _extract_json(text: str) -> Optional[str]:
    """Try to find the outermost balanced {...} block in text."""
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    for i, ch in enumerate(text[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None
