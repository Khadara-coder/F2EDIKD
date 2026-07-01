from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import numpy as np

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MODEL_DIR = _PROJECT_ROOT / "all-MiniLM-L6-v2"

_model_state: dict[str, Any] = {
    "model": None,
    "tokenizer": None,
    "backend": None,
    "error": "",
    "loaded": False,
}


def embeddings_enabled() -> bool:
    return os.getenv("ENABLE_ADDRESS_EMBEDDINGS", "true").lower() not in ("0", "false", "no")


def model_dir() -> Path:
    configured = os.getenv("EMBEDDING_MODEL_DIR")
    if not configured:
        return DEFAULT_MODEL_DIR
    path = Path(configured)
    if not path.is_absolute():
        path = _PROJECT_ROOT / path
    return path


def _model_files_present(model_path: Path) -> bool:
    if not model_path.exists():
        return False
    weight_names = (
        "model.safetensors",
        "pytorch_model.bin",
        "onnx/model.onnx",
    )
    return any((model_path / name).exists() for name in weight_names)


def _mean_pooling(model_output, attention_mask):
    import torch

    token_embeddings = model_output.last_hidden_state
    mask = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
    summed = torch.sum(token_embeddings * mask, dim=1)
    counts = torch.clamp(mask.sum(dim=1), min=1e-9)
    return summed / counts


def _load_model() -> None:
    if _model_state["loaded"]:
        return
    _model_state["loaded"] = True

    if not embeddings_enabled():
        _model_state["error"] = "disabled"
        return

    path = model_dir()
    if not _model_files_present(path):
        _model_state["error"] = f"model weights missing in {path}"
        return

    try:
        from sentence_transformers import SentenceTransformer

        _model_state["model"] = SentenceTransformer(str(path))
        _model_state["backend"] = "sentence-transformers"
        return
    except Exception:
        pass

    try:
        import torch
        from transformers import AutoModel, AutoTokenizer

        tokenizer = AutoTokenizer.from_pretrained(str(path))
        model = AutoModel.from_pretrained(str(path))
        model.eval()
        _model_state["model"] = model
        _model_state["tokenizer"] = tokenizer
        _model_state["backend"] = "transformers"
    except Exception as exc:
        _model_state["error"] = str(exc)


def is_available() -> bool:
    _load_model()
    return _model_state["model"] is not None


def availability_reason() -> str:
    _load_model()
    return _model_state["error"] or ("ok" if is_available() else "unknown")


def model_backend() -> str:
    _load_model()
    return str(_model_state.get("backend") or "")


def embed_text(text: str) -> np.ndarray | None:
    _load_model()
    if not _model_state["model"]:
        return None

    cleaned = (text or "").strip()
    if not cleaned:
        return None

    if _model_state["backend"] == "sentence-transformers":
        vector = _model_state["model"].encode(cleaned, normalize_embeddings=True)
        return np.asarray(vector, dtype=np.float32)

    import torch

    tokenizer = _model_state["tokenizer"]
    model = _model_state["model"]
    encoded = tokenizer(
        cleaned,
        padding=True,
        truncation=True,
        max_length=512,
        return_tensors="pt",
    )
    with torch.no_grad():
        outputs = model(**encoded)
        embedding = _mean_pooling(outputs, encoded["attention_mask"])
        embedding = torch.nn.functional.normalize(embedding, p=2, dim=1)
    return embedding[0].cpu().numpy().astype(np.float32)


def cosine_similarity(a: np.ndarray | None, b: np.ndarray | None) -> float:
    if a is None or b is None:
        return 0.0
    return float(np.dot(a, b))


def delivery_block_text(delivery: dict) -> str:
    from app.text_utils import compact_text

    parts: list[str] = []
    has_precise_address = bool(delivery.get("Rue") and (delivery.get("Code postal") or delivery.get("Ville")))
    keys = ("Rue", "Complement", "Code postal", "Ville", "Pays")
    if not has_precise_address:
        keys = ("Nom / service", *keys)
    for key in keys:
        value = delivery.get(key)
        if value:
            parts.append(str(value).strip())
    if delivery.get("Code postal") and delivery.get("Ville"):
        line = compact_text(f"{delivery['Code postal']} {delivery['Ville']}")
        if line not in parts:
            parts.append(line)
    if parts:
        return "\n".join(parts)
    if delivery.get("Adresse complete"):
        return str(delivery["Adresse complete"]).strip()
    return ""


def rank_shipto_by_similarity(detected_block: str, partners: list[dict]) -> list[tuple[dict, float]]:
    from app.masterdata import address_text

    query = embed_text(detected_block)
    if query is None:
        return [(partner, 0.0) for partner in partners]

    ranked: list[tuple[dict, float]] = []
    for partner in partners:
        partner_text = address_text(partner)
        vector = embed_text(partner_text)
        ranked.append((partner, cosine_similarity(query, vector)))
    ranked.sort(key=lambda item: item[1], reverse=True)
    return ranked


def embedding_score_bonus(similarity: float, weight: int, min_sim: float) -> tuple[int, bool]:
    if similarity < min_sim:
        return 0, False
    return int(similarity * weight), True
