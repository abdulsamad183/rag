from app.config import get_settings
from app.rag.confidence import compute_confidence


def test_all_strong_signals_high_confidence():
    report = compute_confidence(
        {
            "retrieval": 0.9,
            "rerank": 0.85,
            "coverage": 1.0,
            "claim_support": 1.0,
            "contradiction": 1.0,
            "source_trust": 0.8,
        },
        get_settings(),
    )
    assert report.level == "high"
    assert report.score > 0.8


def test_missing_signals_renormalize():
    report = compute_confidence({"retrieval": 1.0, "coverage": 1.0}, get_settings())
    assert report.score == 1.0  # weights renormalized over available signals
    assert set(report.signals) == {"retrieval", "coverage"}


def test_no_signals_insufficient():
    report = compute_confidence({}, get_settings())
    assert report.level == "insufficient"
    assert report.score == 0.0


def test_contradictions_drag_score_down():
    base = {
        "retrieval": 0.8, "coverage": 0.8, "claim_support": 0.9,
        "contradiction": 1.0, "source_trust": 0.7,
    }
    clean = compute_confidence(base, get_settings())
    conflicted = compute_confidence({**base, "contradiction": 0.0, "claim_support": 0.3},
                                    get_settings())
    assert conflicted.score < clean.score
    assert conflicted.level in ("low", "insufficient", "medium")


def test_signals_clamped_to_unit_interval():
    report = compute_confidence({"retrieval": 5.0}, get_settings())
    assert report.score <= 1.0
