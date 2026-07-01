import base64
import json
import os
import re
import time
from io import BytesIO
from pathlib import Path
from typing import Literal

import fitz
import requests
import torch
from contextlib import asynccontextmanager
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator
from PIL import Image
from transformers import AutoModel, AutoProcessor, AutoTokenizer

from app.config import get_config
from app.engine import get_engine
from app.extraction import build_text_extraction_result
from app.image_extract import extract_image_with_selective_ocr
from app.masterdata import MASTER_DATA_DIR, get_master_data
from app.ocr import ocr_image, ocr_image_with_layout
from app.pdf_reader import parse_page_selection, pdf_page_layout, pdf_pages_to_text as read_pdf_pages, render_pdf_page
from app.runtime import configure_runtime
from app.text_utils import compact_text


MODEL_ID = os.getenv("MODEL_ID", "nvidia/LocateAnything-3B")
DEFAULT_GENERATION_MODE = os.getenv("DEFAULT_GENERATION_MODE", "hybrid")
DEFAULT_MAX_NEW_TOKENS = int(os.getenv("MAX_NEW_TOKENS", "1024"))
APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "static"
TESSERACT_LANG = os.getenv("TESSERACT_LANG", "fra+eng")

GenerationMode = Literal["fast", "slow", "hybrid"]
Task = Literal[
    "raw",
    "detect",
    "ground_single",
    "ground_multi",
    "ground_text",
    "detect_text",
    "ground_gui",
    "point",
]
ExtractionEngine = Literal["full_code", "text", "locateanything"]
LOCAL_EXTRACTION_ENGINES = {"full_code", "text"}


class PredictRequest(BaseModel):
    image_url: str | None = None
    image_base64: str | None = None
    image_path: str | None = None
    task: Task = "ground_multi"
    query: str | None = None
    categories: list[str] | None = None
    output_type: Literal["box", "point"] = "box"
    generation_mode: GenerationMode = Field(default=DEFAULT_GENERATION_MODE)
    max_new_tokens: int = Field(default=DEFAULT_MAX_NEW_TOKENS, ge=1, le=8192)
    temperature: float = Field(default=0.7, ge=0.01, le=2.0)
    top_p: float = Field(default=0.9, gt=0.0, le=1.0)
    repetition_penalty: float = Field(default=1.1, ge=0.0, le=3.0)

    @model_validator(mode="after")
    def validate_image_source(self) -> "PredictRequest":
        sources = [self.image_url, self.image_base64, self.image_path]
        if sum(bool(source) for source in sources) != 1:
            raise ValueError("Provide exactly one image source: image_url, image_base64, or image_path.")
        return self


class LocateAnythingWorker:
    def __init__(self, model_id: str) -> None:
        self.model_id = model_id
        self.device = self._resolve_device(os.getenv("DEVICE", "auto"))
        self.dtype = self._resolve_dtype(os.getenv("TORCH_DTYPE", "auto"), self.device)

        token = os.getenv("HF_TOKEN") or None
        self.tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True, token=token)
        self.processor = AutoProcessor.from_pretrained(model_id, trust_remote_code=True, token=token)
        self.model = AutoModel.from_pretrained(
            model_id,
            torch_dtype=self.dtype,
            trust_remote_code=True,
            token=token,
        ).to(self.device).eval()

    @staticmethod
    def _resolve_device(value: str) -> str:
        requested = value.lower()
        allow_cpu = os.getenv("ALLOW_CPU_MODEL_LOAD", "false").lower() in {"1", "true", "yes", "on"}
        if requested == "auto":
            if torch.cuda.is_available():
                return "cuda"
            if allow_cpu:
                return "cpu"
            raise RuntimeError(
                "CUDA is not available, so LocateAnything model loading was blocked to avoid an out-of-memory crash. "
                "Use the Text/OCR engine on this machine, or set ALLOW_CPU_MODEL_LOAD=true if you really want to force CPU."
            )
        if requested == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("DEVICE=cuda was requested, but torch.cuda.is_available() is false.")
        if requested == "cpu" and not allow_cpu:
            raise RuntimeError(
                "DEVICE=cpu was requested, but ALLOW_CPU_MODEL_LOAD is false. "
                "Set ALLOW_CPU_MODEL_LOAD=true to force CPU model loading."
            )
        if requested not in {"cuda", "cpu"}:
            raise RuntimeError("DEVICE must be one of: auto, cuda, cpu.")
        return requested

    @staticmethod
    def _resolve_dtype(value: str, device: str) -> torch.dtype:
        requested = value.lower()
        if requested == "auto":
            return torch.bfloat16 if device == "cuda" else torch.float32
        options = {
            "bfloat16": torch.bfloat16,
            "bf16": torch.bfloat16,
            "float16": torch.float16,
            "fp16": torch.float16,
            "float32": torch.float32,
            "fp32": torch.float32,
        }
        if requested not in options:
            raise RuntimeError("TORCH_DTYPE must be one of: auto, bfloat16, float16, float32.")
        return options[requested]

    @torch.no_grad()
    def predict(self, image: Image.Image, prompt: str, request: PredictRequest) -> dict:
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": image},
                    {"type": "text", "text": prompt},
                ],
            }
        ]
        text = self.processor.py_apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        images, videos = self.processor.process_vision_info(messages)
        inputs = self.processor(text=[text], images=images, videos=videos, return_tensors="pt").to(self.device)

        response = self.model.generate(
            pixel_values=inputs["pixel_values"].to(self.dtype),
            input_ids=inputs["input_ids"],
            attention_mask=inputs["attention_mask"],
            image_grid_hws=inputs.get("image_grid_hws"),
            tokenizer=self.tokenizer,
            max_new_tokens=request.max_new_tokens,
            use_cache=True,
            generation_mode=request.generation_mode,
            temperature=request.temperature,
            do_sample=True,
            top_p=request.top_p,
            repetition_penalty=request.repetition_penalty,
            verbose=True,
        )

        answer = response[0] if isinstance(response, tuple) else response
        answer = answer if isinstance(answer, str) else str(answer)
        width, height = image.size
        result = {
            "model": self.model_id,
            "device": self.device,
            "dtype": str(self.dtype).replace("torch.", ""),
            "generation_mode": request.generation_mode,
            "prompt": prompt,
            "answer": answer,
            "boxes": parse_boxes(answer, width, height),
            "points": parse_points(answer, width, height),
        }
        if isinstance(response, tuple) and len(response) >= 3:
            result["stats"] = response[2]
        return result


master_data_preload_ms: int | None = None
engine_preload_ms: int | None = None
full_code_engine = None


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global master_data_preload_ms, engine_preload_ms, full_code_engine
    configure_runtime()
    started = time.perf_counter()
    get_master_data()
    master_data_preload_ms = int((time.perf_counter() - started) * 1000)
    started = time.perf_counter()
    full_code_engine = get_engine()
    full_code_engine.health()
    engine_preload_ms = int((time.perf_counter() - started) * 1000)
    yield


app = FastAPI(title="LocateAnything local API", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
worker: LocateAnythingWorker | None = None


def get_worker() -> LocateAnythingWorker:
    global worker
    if worker is None:
        try:
            worker = LocateAnythingWorker(MODEL_ID)
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    return worker


def build_prompt(request: PredictRequest) -> str:
    query = (request.query or "").strip()
    if request.task == "raw":
        if not query:
            raise HTTPException(status_code=400, detail="query is required for task=raw.")
        return query
    if request.task == "detect":
        categories = request.categories or ([item.strip() for item in query.split(",") if item.strip()] if query else [])
        if not categories:
            raise HTTPException(status_code=400, detail="categories or query is required for task=detect.")
        return f"Locate all the instances that matches the following description: {'</c>'.join(categories)}."
    if not query and request.task not in {"detect_text"}:
        raise HTTPException(status_code=400, detail=f"query is required for task={request.task}.")
    prompts = {
        "ground_single": f"Locate a single instance that matches the following description: {query}.",
        "ground_multi": f"Locate all the instances that match the following description: {query}.",
        "ground_text": f"Please locate the text referred as {query}.",
        "detect_text": "Detect all the text in box format.",
        "point": f"Point to: {query}.",
    }
    if request.task == "ground_gui":
        if request.output_type == "point":
            return f"Point to: {query}."
        return f"Locate the region that matches the following description: {query}."
    return prompts[request.task]


def load_image(request: PredictRequest) -> Image.Image:
    if request.image_url:
        response = requests.get(request.image_url, timeout=30)
        response.raise_for_status()
        return Image.open(BytesIO(response.content)).convert("RGB")
    if request.image_base64:
        payload = request.image_base64.split(",", 1)[-1]
        return Image.open(BytesIO(base64.b64decode(payload))).convert("RGB")

    path = Path(request.image_path or "")
    if not path.is_absolute():
        path = Path("/data") / path
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Image path not found inside container: {path}")
    return Image.open(path).convert("RGB")


def parse_boxes(answer: str, image_width: int, image_height: int) -> list[dict]:
    boxes = []
    for match in re.finditer(r"<box><(\d+)><(\d+)><(\d+)><(\d+)></box>", answer):
        x1, y1, x2, y2 = [int(group) for group in match.groups()]
        boxes.append(
            {
                "x1": x1 / 1000 * image_width,
                "y1": y1 / 1000 * image_height,
                "x2": x2 / 1000 * image_width,
                "y2": y2 / 1000 * image_height,
            }
        )
    return boxes


def parse_points(answer: str, image_width: int, image_height: int) -> list[dict]:
    points = []
    for match in re.finditer(r"<box><(\d+)><(\d+)></box>", answer):
        x, y = int(match.group(1)), int(match.group(2))
        points.append({"x": x / 1000 * image_width, "y": y / 1000 * image_height})
    return points


def _parse_pages(selection: str, page_count: int, limit: int | None = None) -> list[int]:
    try:
        return parse_page_selection(selection, page_count, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def pdf_pages_to_images(payload: bytes, selection: str) -> list[tuple[int, Image.Image]]:
    try:
        document = fitz.open(stream=payload, filetype="pdf")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Unable to read PDF: {exc}") from exc

    if document.page_count == 0:
        raise HTTPException(status_code=400, detail="The PDF has no pages.")

    rendered_pages: list[tuple[int, Image.Image]] = []
    for page_number in _parse_pages(selection, document.page_count):
        page = document.load_page(page_number - 1)
        rendered_pages.append((page_number, render_pdf_page(page)))
    return rendered_pages


def image_payload_to_image(payload: bytes) -> Image.Image:
    try:
        return Image.open(BytesIO(payload)).convert("RGB")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Unable to read image: {exc}") from exc


def decode_text_payload(payload: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return payload.decode(encoding)
        except UnicodeDecodeError:
            continue
    return payload.decode("utf-8", errors="replace")


def pdf_pages_to_text(payload: bytes, selection: str) -> list[dict]:
    try:
        return read_pdf_pages(payload, selection, ocr_with_layout=ocr_image_with_layout)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Unable to read PDF: {exc}") from exc


def build_extraction_prompt(instruction: str) -> str:
    cleaned = instruction.strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail="Instruction is required.")
    return (
        "You are reading a document image. Extract the requested information from the visible content. "
        "Return a concise JSON object when possible. Use null for information that is not visible. "
        f"Requested information: {cleaned}"
    )


@app.get("/health")
def health() -> dict:
    active_engine = full_code_engine or get_engine()
    engine_status = active_engine.health()
    return {
        "ok": True,
        "model_id": MODEL_ID,
        "loaded": worker is not None,
        "cuda_available": torch.cuda.is_available(),
        "cuda_device_count": torch.cuda.device_count(),
        "device_env": os.getenv("DEVICE", "auto"),
        "allow_cpu_model_load": os.getenv("ALLOW_CPU_MODEL_LOAD", "false"),
        "tesseract_lang": TESSERACT_LANG,
        "master_data_dir": str(MASTER_DATA_DIR),
        "master_data_preload_ms": master_data_preload_ms,
        "engine_preload_ms": engine_preload_ms,
        "torch": torch.__version__,
        **engine_status,
    }


@app.get("/", response_class=HTMLResponse)
def root() -> HTMLResponse:
    return HTMLResponse((STATIC_DIR / "index.html").read_text(encoding="utf-8"))


@app.post("/load")
def load() -> dict:
    active_worker = get_worker()
    return {
        "loaded": True,
        "model_id": active_worker.model_id,
        "device": active_worker.device,
        "dtype": str(active_worker.dtype).replace("torch.", ""),
    }


@app.post("/predict")
def predict(request: PredictRequest) -> dict:
    prompt = build_prompt(request)
    image = load_image(request)
    return get_worker().predict(image, prompt, request)


@app.post("/extract")
async def extract(
    file: UploadFile = File(...),
    instruction: str = Form(...),
    pages: str = Form("1"),
    engine: ExtractionEngine = Form("text"),
    generation_mode: GenerationMode = Form(DEFAULT_GENERATION_MODE),
    max_new_tokens: int = Form(DEFAULT_MAX_NEW_TOKENS),
    debug: bool = Form(False),
) -> dict:
    if max_new_tokens < 1 or max_new_tokens > 8192:
        raise HTTPException(status_code=400, detail="max_new_tokens must be between 1 and 8192.")

    payload = await file.read()
    if not payload:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    extract_started = time.perf_counter()
    extraction_context: dict = {}
    content_type = (file.content_type or "").lower()
    suffix = Path(file.filename or "").suffix.lower()
    if content_type == "application/pdf" or suffix == ".pdf":
        file_type = "pdf"
        if engine == "full_code":
            active = full_code_engine or get_engine()
            try:
                return active.extract_pdf(
                    payload,
                    filename=file.filename,
                    pages=pages,
                    instruction=instruction,
                    include_debug=debug,
                    extraction_context=extraction_context,
                )
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        if engine in LOCAL_EXTRACTION_ENGINES:
            text_pages = pdf_pages_to_text(payload, pages)
            results = []
            for item in text_pages:
                results.append(
                    build_text_extraction_result(
                        item["page"],
                        item["text"],
                        item["source"],
                        instruction,
                        file.filename,
                        item.get("layout"),
                        engine,
                        extraction_context,
                        debug,
                    )
                )
            response = {
                "filename": file.filename,
                "file_type": file_type,
                "engine": engine,
                "instruction": instruction,
                "pages": [item["page"] for item in results],
                "results": results,
                "extraction_context": {
                    "order_number": extraction_context.get("order_number"),
                    "known_soldto_id": extraction_context.get("known_soldto_id"),
                },
                "timings_ms": {"request_total": int((time.perf_counter() - extract_started) * 1000)},
            }
            if debug and results:
                response["debug"] = results[-1].get("debug")
            return response
        images = pdf_pages_to_images(payload, pages)
    elif content_type.startswith("image/") or suffix in {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}:
        file_type = "image"
        image = image_payload_to_image(payload)
        if engine == "full_code":
            active = full_code_engine or get_engine()
            try:
                response = active.extract_image(
                    image,
                    filename=file.filename,
                    instruction=instruction,
                    include_debug=debug,
                    extraction_context=extraction_context,
                )
                if response["results"]:
                    response["results"][0]["image_size"] = {"width": image.width, "height": image.height}
                return response
            except (ValueError, RuntimeError) as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        if engine in LOCAL_EXTRACTION_ENGINES:
            text, layout, source = extract_image_with_selective_ocr(image, ocr_image_with_layout)
            result = build_text_extraction_result(
                1,
                text,
                source,
                instruction,
                file.filename,
                layout,
                engine,
                extraction_context,
                debug,
            )
            result["image_size"] = {"width": image.width, "height": image.height}
            response = {
                "filename": file.filename,
                "file_type": file_type,
                "engine": engine,
                "instruction": instruction,
                "pages": [1],
                "results": [result],
                "extraction_context": {
                    "order_number": extraction_context.get("order_number"),
                    "known_soldto_id": extraction_context.get("known_soldto_id"),
                },
                "timings_ms": {"request_total": int((time.perf_counter() - extract_started) * 1000)},
            }
            if debug:
                response["debug"] = result.get("debug")
            return response
        images = [(1, image)]
    elif content_type.startswith("text/") or suffix in {".md", ".markdown", ".txt"}:
        file_type = "text"
        text = decode_text_payload(payload)
        local_engine = engine if engine in LOCAL_EXTRACTION_ENGINES else "text"
        result = build_text_extraction_result(
            1, text, "text", instruction, file.filename, None, local_engine, extraction_context, debug
        )
        response = {
            "filename": file.filename,
            "file_type": file_type,
            "engine": local_engine,
            "instruction": instruction,
            "pages": [1],
            "results": [result],
            "extraction_context": {
                "order_number": extraction_context.get("order_number"),
                "known_soldto_id": extraction_context.get("known_soldto_id"),
            },
            "timings_ms": {"request_total": int((time.perf_counter() - extract_started) * 1000)},
        }
        if debug:
            response["debug"] = result.get("debug")
        return response
    else:
        raise HTTPException(status_code=400, detail="Upload a PDF, an image, a markdown file, or a text file.")

    prompt = build_extraction_prompt(instruction)
    options = PredictRequest(
        image_base64="inline",
        task="raw",
        query=prompt,
        generation_mode=generation_mode,
        max_new_tokens=max_new_tokens,
    )
    active_worker = get_worker()
    results = []
    for page_number, image in images:
        page_result = active_worker.predict(image, prompt, options)
        page_result["page"] = page_number
        page_result["image_size"] = {"width": image.width, "height": image.height}
        results.append(page_result)

    return {
        "filename": file.filename,
        "file_type": file_type,
        "engine": engine,
        "instruction": instruction,
        "pages": [item["page"] for item in results],
        "results": results,
    }
