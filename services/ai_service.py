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

from anthropic import Anthropic

client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

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
- "none"          → no diagram
- "function_graph" → use for functions/equations that should be graphed;
                     expr must be valid Python/NumPy (use ** not ^, use np.sqrt, etc.)
- "triangle"      → for geometry triangle problems;
                     vertices are [x, y] coordinates scaled for clarity
- "circle"        → for circle geometry; include center [x,y] and radius (number),
                     optional points array with {angle_deg, label}
- "number_line"   → for inequalities / number-line problems;
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

    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": content}],
    )

    raw = response.content[0].text.strip()

    # Strip any accidental markdown code fences
    raw = _strip_code_fence(raw)

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        # Attempt a best-effort extraction of JSON object from the response
        extracted = _extract_json(raw)
        if extracted:
            return json.loads(extracted)
        raise ValueError(
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
        # Drop first line (```json or ```) and last line (```)
        inner = lines[1:] if lines[-1].strip() == "```" else lines[1:]
        if inner and inner[-1].strip() == "```":
            inner = inner[:-1]
        text = "\n".join(inner).strip()
    return text


def _extract_json(text: str) -> Optional[str]:
    """Try to find the first {...} block in text."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    return match.group(0) if match else None
