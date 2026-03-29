"""
app.py
======
오답노트 (Wrong Answer Journal) - FastAPI Web Application

Run with:
    uvicorn app:app --reload --port 8000

Then open http://localhost:8000 in your browser.
"""

from __future__ import annotations

import base64
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

load_dotenv()

from services.ai_service import analyze_math_problem
from services.diagram_service import generate_diagram_base64


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: verify API key is set
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("WARNING: ANTHROPIC_API_KEY is not set. Please set it in your .env file.")
    yield


app = FastAPI(title="오답노트 - Wrong Answer Journal", lifespan=lifespan)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/api/analyze")
async def analyze(
    image: UploadFile = File(None),
    text: str = Form(None),
    language: str = Form("korean"),
):
    """Analyze a math problem from an image or text input.

    Returns a structured JSON with:
    - problem_text: extracted/cleaned problem statement
    - problem_type: category of the problem
    - difficulty: estimated Korean grade level
    - solution: step-by-step solution
    - concept: 개념원리-level conceptual explanation
    - similar_problems: 3 generated practice problems with answers
    """
    if (not image or not image.filename) and not text:
        raise HTTPException(status_code=400, detail="이미지 또는 텍스트를 입력해주세요.")

    image_base64 = None
    media_type = "image/jpeg"

    if image and image.filename:
        contents = await image.read()
        image_base64 = base64.standard_b64encode(contents).decode()
        media_type = image.content_type or "image/jpeg"
        # Normalize HEIC to jpeg media type for API compatibility
        if media_type in ("image/heic", "image/heif"):
            media_type = "image/jpeg"

    try:
        result = await analyze_math_problem(
            image_base64=image_base64,
            media_type=media_type,
            text=text,
            language=language,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"AI 분석 실패: {exc}") from exc

    # Generate diagrams for any similar problem that requests one
    for i, problem in enumerate(result.get("similar_problems", [])):
        diagram = problem.get("diagram", {})
        dtype = diagram.get("type", "none")
        if dtype and dtype != "none":
            try:
                img_b64 = generate_diagram_base64(diagram)
                result["similar_problems"][i]["diagram_image"] = img_b64
            except Exception as exc:
                # Diagram generation is non-critical; log and continue
                print(f"[diagram] Problem {i + 1} failed: {exc}")

    return result
