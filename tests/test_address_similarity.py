from __future__ import annotations

import app.address_similarity as sim
from app.address_similarity import (
    cosine_similarity,
    delivery_block_text,
    embedding_score_bonus,
    rank_shipto_by_similarity,
)


def test_delivery_block_text_ignores_service_when_precise_address_exists():
    block = delivery_block_text(
        {
            "Nom / service": "IZI CONFORT CLERMONT",
            "Rue": "1 RUE JACQUES MONOD",
            "Code postal": "63360",
            "Ville": "GERZAT",
        }
    )
    assert "IZI CONFORT CLERMONT" not in block
    assert "1 RUE JACQUES MONOD" in block
    assert "63360 GERZAT" in block


def test_delivery_block_text_keeps_service_without_street():
    block = delivery_block_text(
        {
            "Nom / service": "IZI CONFORT CLERMONT",
            "Code postal": "63360",
            "Ville": "GERZAT",
        }
    )
    assert "IZI CONFORT CLERMONT" in block
    assert "63360 GERZAT" in block


def test_cosine_similarity_identical_vectors():
    import numpy as np

    vector = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    assert cosine_similarity(vector, vector) == 1.0


def test_embedding_score_bonus_applies_above_threshold():
    bonus, applied = embedding_score_bonus(0.8, weight=25, min_sim=0.55)
    assert applied is True
    assert bonus == 20


def test_rank_shipto_without_model_returns_zero_similarity():
    sim._model_state["loaded"] = True
    sim._model_state["model"] = None
    sim._model_state["error"] = "disabled"

    partners = [
        {"id": "1", "name": "A", "street": "1 RUE", "postal": "63360", "city": "GERZAT", "country": "FR"},
        {"id": "2", "name": "B", "street": "2 RUE", "postal": "75001", "city": "PARIS", "country": "FR"},
    ]
    ranked = rank_shipto_by_similarity("63360 GERZAT", partners)
    assert len(ranked) == 2
    assert all(score == 0.0 for _partner, score in ranked)
