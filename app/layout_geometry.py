from __future__ import annotations


def bbox_from_values(x0: float, y0: float, x1: float, y1: float) -> dict:
    return {"x0": float(x0), "y0": float(y0), "x1": float(x1), "y1": float(y1)}


def union_bbox(boxes: list[dict]) -> dict:
    return {
        "x0": min(box["x0"] for box in boxes),
        "y0": min(box["y0"] for box in boxes),
        "x1": max(box["x1"] for box in boxes),
        "y1": max(box["y1"] for box in boxes),
    }


def bbox_center(box: dict) -> tuple[float, float]:
    return ((box["x0"] + box["x1"]) / 2, (box["y0"] + box["y1"]) / 2)
