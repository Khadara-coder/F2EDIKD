from __future__ import annotations

import os
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def is_databricks() -> bool:
    return bool(os.getenv("DATABRICKS_RUNTIME_VERSION"))


def project_root() -> Path:
    configured = os.getenv("LOCATEANYTHING_PROJECT_ROOT")
    if configured:
        return Path(configured)
    return _PROJECT_ROOT


def assets_dir() -> Path:
    configured = os.getenv("LOCATEANYTHING_ASSETS_DIR")
    if configured:
        if configured.startswith("dbfs:"):
            return Path("/dbfs") / configured[5:].lstrip("/")
        path = Path(configured)
        if not path.is_absolute() and is_databricks():
            return Path("/dbfs") / str(path).replace("\\", "/").lstrip("/")
        return path
    if is_databricks():
        return Path("/dbfs/FileStore/users/dik1dy/locateanything")
    return project_root()


def configure_runtime() -> dict[str, str]:
    root = project_root()
    assets = assets_dir()
    master_default = assets / "data" / "masterdata"
    if not master_default.exists():
        master_default = root / "data" / "masterdata"

    embedding_default = assets / "all-MiniLM-L6-v2"
    if not embedding_default.exists():
        embedding_default = root / "all-MiniLM-L6-v2"

    postal_reference_default = assets / "data" / "reference" / "fr_communes.json"
    if not postal_reference_default.exists():
        postal_reference_default = root / "data" / "reference" / "fr_communes.json"

    resolved = {
        "LOCATEANYTHING_PROJECT_ROOT": str(root),
        "LOCATEANYTHING_ASSETS_DIR": str(assets),
        "MASTER_DATA_DIR": os.getenv("MASTER_DATA_DIR", str(master_default)),
        "EMBEDDING_MODEL_DIR": os.getenv("EMBEDDING_MODEL_DIR", str(embedding_default)),
        "POSTAL_REFERENCE_PATH": os.getenv("POSTAL_REFERENCE_PATH", str(postal_reference_default)),
        "ENABLE_ADDRESS_EMBEDDINGS": os.getenv("ENABLE_ADDRESS_EMBEDDINGS", "true"),
    }
    for key, value in resolved.items():
        os.environ.setdefault(key, value)
    return resolved


def runtime_info() -> dict:
    configure_runtime()
    return {
        "runtime": "databricks" if is_databricks() else "local",
        "project_root": os.environ.get("LOCATEANYTHING_PROJECT_ROOT", ""),
        "assets_dir": os.environ.get("LOCATEANYTHING_ASSETS_DIR", ""),
        "master_data_dir": os.environ.get("MASTER_DATA_DIR", ""),
        "embedding_model_dir": os.environ.get("EMBEDDING_MODEL_DIR", ""),
        "postal_reference_path": os.environ.get("POSTAL_REFERENCE_PATH", ""),
        "embeddings_enabled": os.environ.get("ENABLE_ADDRESS_EMBEDDINGS", "true"),
    }
