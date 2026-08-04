"""Lazy bridge from File2EDI router to legacy server engine helpers.

Keeps `import server` out of router route bodies while the heavy PDF
process / generate / conversion persistence logic still lives in server.py.
"""

from __future__ import annotations

from typing import Any


def process_pdf(payload: bytes, filename: str, actor: str | None = None) -> dict:
    import server as srv

    return srv._local_process_and_respond(payload, filename, actor=actor)


def resolve_processing_actor(uploaded_by: str, result: dict | None = None) -> str:
    import server as srv

    return srv._resolve_processing_actor(uploaded_by, result)


def init_db() -> None:
    import server as srv

    srv._init_db()


def upsert_conversion(data: dict, callback_url: str | None = None) -> None:
    import server as srv

    srv._upsert_conversion(data, callback_url=callback_url)


def load_conversion(cid: str) -> dict | None:
    import server as srv

    return srv.load_conversion(cid)


def list_conversions(
    status: str | None = None,
    limit: int = 100,
    **kwargs: Any,
) -> list:
    import server as srv

    return srv.list_conversions(status=status, limit=limit, **kwargs)


async def generate_edifact(cid: str, req: Any) -> Any:
    import server as srv

    return await srv.api_generate(cid, req)
