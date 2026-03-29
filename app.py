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
import io
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from PIL import Image
from starlette.requests import Request

load_dotenv()

from services.ai_service import analyze_math_problem
from services.diagram_service import generate_diagram_base64

BASE_DIR = Path(__file__).parent

# Maximum accepted upload size (10 MB)
MAX_IMAGE_BYTES = 10 * 1024 * 1024

# Allowed image magic-byte signatures  {magic_bytes: canonical_mime}
_IMAGE_SIGNATURES: list[tuple[bytes, str]] = [
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"RIFF", "image/webp"),      # RIFF....WEBP — checked further below
    (b"\x00\x00\x00\x0cftyp", "image/heic"),  # HEIF/HEIC ftyp box
    (b"\x00\x00\x00\x18ftyp", "image/heic"),
    (b"\x00\x00\x00\x1cftyp", "image/heic"),
    (b"\x00\x00\x00\x20ftyp", "image/heic"),
]


def _detect_mime(data: bytes) -> str | None:
    """Return the canonical MIME type based on magic bytes, or None."""
    for magic, mime in _IMAGE_SIGNATURES:
        if data[:len(magic)] == magic:
            if mime == "image/webp" and data[8:12] != b"WEBP":
                continue
            return mime
    return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("WARNING: ANTHROPIC_API_KEY is not set. Please set it in your .env file.")
    yield


app = FastAPI(title="오답노트 - Wrong Answer Journal", lifespan=lifespan)

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/api/analyze")
async def analyze(
    image: UploadFile = File(None),
    text: str = Form(None),
    language: str = Form("korean"),
):
    """Analyze a math problem from an image or text input."""
    if (not image or not image.filename) and not text:
        raise HTTPException(status_code=400, detail="이미지 또는 텍스트를 입력해주세요.")

    image_base64 = None
    media_type = "image/jpeg"

    if image and image.filename:
        # Read with a hard size cap to prevent memory exhaustion
        contents = await image.read(MAX_IMAGE_BYTES + 1)
        if len(contents) > MAX_IMAGE_BYTES:
            raise HTTPException(
                status_code=413, detail="이미지 크기가 10MB를 초과합니다."
            )

        # Validate actual file content via magic bytes (not client-supplied type)
        detected = _detect_mime(contents)
        if detected is None:
            raise HTTPException(
                status_code=415, detail="지원하지 않는 이미지 형식입니다. JPG, PNG, WEBP, HEIC를 사용해주세요."
            )
        media_type = detected

        # Convert HEIC/HEIF to JPEG bytes so the API receives correct content
        if media_type in ("image/heic", "image/heif"):
            try:
                pil_img = Image.open(io.BytesIO(contents)).convert("RGB")
                buf = io.BytesIO()
                pil_img.save(buf, format="JPEG", quality=92)
                contents = buf.getvalue()
                media_type = "image/jpeg"
            except Exception as exc:
                raise HTTPException(
                    status_code=422, detail=f"HEIC 이미지 변환 실패: {exc}"
                ) from exc

        image_base64 = base64.standard_b64encode(contents).decode()

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
                print(f"[diagram] Problem {i + 1} failed: {exc}")

    return result
