"""Per-signal-type recovery minimum: head_away can be shorter; phone and absence cannot."""

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_ROOT))

from app.config import DEMO_ENV, Settings  # noqa: E402
from app.contracts.models import SignalEvent  # noqa: E402
from app.signals.service import SignalService  # noqa: E402


def service(**settings) -> SignalService:
    """Build the service; only the settings are used by the eligibility rule."""
    return SignalService(None, Settings(app_env="test", **settings), None, None)  # type: ignore[arg-type]


def event(event_type: str, seconds: int, signals: list[str] | None = None) -> SignalEvent:
    return SignalEvent(
        event_id="e",
        session_id="s",
        event_type=event_type,
        start_ms=0,
        end_ms=seconds * 1000,
        signals=signals or [event_type],
        confidence=0.8,
    )


def test_default_keeps_the_single_thirty_second_rule():
    rules = service()
    assert not rules.is_recovery_eligible(event("head_away", 12))
    assert rules.is_recovery_eligible(event("head_away", 30))


def test_head_away_can_use_a_shorter_minimum_without_changing_other_signals():
    rules = service(min_head_away_window_ms=10_000)
    assert rules.is_recovery_eligible(event("head_away", 10))
    assert not rules.is_recovery_eligible(event("head_away", 9))
    # Absence keeps the long rule.
    assert not rules.is_recovery_eligible(event("student_left_frame", 12))
    assert not rules.is_recovery_eligible(event("face_absent", 12))


def test_phone_never_qualifies_alone_even_with_a_short_head_away_minimum():
    rules = service(min_head_away_window_ms=1_000)
    assert not rules.is_recovery_eligible(event("phone_visible", 60))
    assert not rules.is_recovery_eligible(event("possible_missed_window", 5, ["phone_visible"]))


def test_demo_environment_defaults_a_short_head_away_minimum(monkeypatch):
    from app import config

    monkeypatch.setenv("APP_ENV", DEMO_ENV)
    monkeypatch.delenv("MIN_HEAD_AWAY_WINDOW_MS", raising=False)
    assert config._settings_from_environment().min_head_away_window_ms == 5_000
    monkeypatch.setenv("MIN_HEAD_AWAY_WINDOW_MS", "8000")
    assert config._settings_from_environment().min_head_away_window_ms == 8_000
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("MIN_HEAD_AWAY_WINDOW_MS")
    assert config._settings_from_environment().min_head_away_window_ms is None


def test_rule_cards_match_the_code_defaults():
    from scripts.generate_rule_cards import OUTPUT_PATH, render_rule_cards

    assert OUTPUT_PATH.read_text() == render_rule_cards(), (
        "Rule cards are stale; run `python -m scripts.generate_rule_cards`."
    )
