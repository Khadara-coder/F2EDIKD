"""Application log ring-buffer + file reader for the Paramètres Logs UI."""
from __future__ import annotations

import logging
import os
import re
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_LEVELS = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}
_LINE_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?)?\s*"
    r"(?:\[(?P<level>[A-Z]+)\s*\])?\s*"
    r"(?:(?P<logger>[^\s:]+):\s*)?"
    r"(?P<message>.*)$"
)

_RING: deque[dict[str, Any]] = deque(maxlen=2000)
_HANDLER: logging.Handler | None = None


class _RingHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            _RING.append(
                {
                    "id": f"mem-{int(record.created * 1000)}-{id(record)}",
                    "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc)
                    .isoformat()
                    .replace("+00:00", "Z"),
                    "level": record.levelname,
                    "logger": record.name,
                    "message": self.format(record) if self.formatter else record.getMessage(),
                    "source": "memory",
                }
            )
        except Exception:
            self.handleError(record)


def ensure_ring_handler(capacity: int = 2000) -> None:
    """Attach a process-wide ring buffer to the root logger (idempotent)."""
    global _HANDLER, _RING
    root = logging.getLogger()
    if _HANDLER is not None and _HANDLER in root.handlers:
        return
    if _HANDLER is not None:
        try:
            root.removeHandler(_HANDLER)
        except Exception:
            pass
    _RING = deque(maxlen=max(100, capacity))
    handler = _RingHandler()
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logging.Formatter("%(message)s"))
    # Capture even if root level is higher - filter in get_recent_logs
    root.addHandler(handler)
    if root.level == logging.NOTSET or root.level > logging.DEBUG:
        # Keep existing root level if already configured; only lower for empty configs
        if not any(isinstance(h, logging.StreamHandler) or isinstance(h, logging.FileHandler) for h in root.handlers if h is not handler):
            root.setLevel(logging.INFO)
    _HANDLER = handler


def reset_ring_for_tests() -> None:
    """Test helper: clear ring and re-attach handler."""
    global _HANDLER, _RING
    root = logging.getLogger()
    if _HANDLER is not None:
        try:
            root.removeHandler(_HANDLER)
        except Exception:
            pass
    _HANDLER = None
    _RING = deque(maxlen=2000)
    ensure_ring_handler()


def resolve_log_dir() -> Path:
    raw = (os.environ.get("LOG_DIR") or "").strip()
    if raw:
        return Path(raw)
    return Path(__file__).resolve().parents[1] / "data" / "logs"


def _parse_file_line(raw: str, source: str, idx: int) -> dict[str, Any]:
    text = raw.rstrip("\n")
    m = _LINE_RE.match(text)
    level = "INFO"
    logger = "file"
    message = text
    ts = None
    if m:
        level = (m.group("level") or "INFO").strip().upper()
        logger = (m.group("logger") or "file").strip()
        message = (m.group("message") or text).strip()
        ts = m.group("ts")
    if level not in _LEVELS:
        level = "INFO"
    return {
        "id": f"{source}-{idx}",
        "timestamp": ts or "",
        "level": level,
        "logger": logger,
        "message": message or text,
        "source": source,
        "raw": text,
    }


def _read_tail_lines(path: Path, max_lines: int) -> list[str]:
    if not path.is_file():
        return []
    try:
        # Efficient-ish tail for typical log sizes
        with path.open("rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            block = 8192
            data = b""
            while size > 0 and data.count(b"\n") <= max_lines:
                read_size = min(block, size)
                size -= read_size
                fh.seek(size)
                data = fh.read(read_size) + data
            text = data.decode("utf-8", errors="replace")
        lines = text.splitlines()
        return lines[-max_lines:]
    except Exception:
        try:
            return path.read_text(encoding="utf-8", errors="replace").splitlines()[-max_lines:]
        except Exception:
            return []


def list_log_files() -> list[dict[str, Any]]:
    log_dir = resolve_log_dir()
    files: list[dict[str, Any]] = []
    if not log_dir.exists():
        return files
    for path in sorted(log_dir.glob("*")):
        if not path.is_file():
            continue
        try:
            st = path.stat()
        except OSError:
            continue
        files.append(
            {
                "name": path.name,
                "path": str(path),
                "sizeBytes": st.st_size,
                "modifiedAt": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc)
                .isoformat()
                .replace("+00:00", "Z"),
            }
        )
    return files


def get_recent_logs(
    *,
    limit: int = 200,
    level: str = "INFO",
    search: str = "",
    file_name: str | None = None,
) -> dict[str, Any]:
    ensure_ring_handler()
    limit = max(1, min(1000, int(limit or 200)))
    min_level = _LEVELS.get(str(level or "INFO").upper(), 20)
    needle = str(search or "").strip().lower()

    entries: list[dict[str, Any]] = []

    # Memory ring (most recent process activity)
    for item in list(_RING):
        if _LEVELS.get(str(item.get("level") or "INFO").upper(), 20) < min_level:
            continue
        hay = f"{item.get('logger','')} {item.get('message','')}".lower()
        if needle and needle not in hay:
            continue
        entries.append(dict(item))

    # File tails
    log_dir = resolve_log_dir()
    candidates: list[Path] = []
    if file_name:
        safe = Path(str(file_name)).name
        candidates = [log_dir / safe]
    else:
        # Prefer known names, then any *.log
        preferred = [
            log_dir / "edifact.log",
            log_dir / "app.log",
            log_dir / "server.log",
        ]
        candidates = [p for p in preferred if p.exists()]
        if not candidates and log_dir.exists():
            candidates = sorted(log_dir.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)[:3]

    for path in candidates:
        for idx, line in enumerate(_read_tail_lines(path, limit)):
            if not line.strip():
                continue
            parsed = _parse_file_line(line, path.name, idx)
            if _LEVELS.get(parsed["level"], 20) < min_level:
                continue
            hay = f"{parsed['logger']} {parsed['message']} {parsed.get('raw','')}".lower()
            if needle and needle not in hay:
                continue
            entries.append(parsed)

    # Sort newest first when timestamp present, else keep insertion order and reverse
    def _sort_key(row: dict[str, Any]) -> str:
        return str(row.get("timestamp") or "")

    entries.sort(key=_sort_key, reverse=True)
    # Deduplicate identical consecutive messages
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in entries:
        key = f"{row.get('timestamp')}|{row.get('level')}|{row.get('message')}"
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
        if len(deduped) >= limit:
            break

    return {
        "items": deduped,
        "count": len(deduped),
        "limit": limit,
        "level": str(level or "INFO").upper(),
        "search": search,
        "logDir": str(log_dir),
        "files": list_log_files(),
        "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
