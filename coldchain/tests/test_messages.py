from __future__ import annotations

import pytest

from shared.enums import FaultCause, Severity
from shared.messages import (
    AUDIENCES,
    BANNED_DRIVER_JARGON,
    COUNTDOWN_CLAUSE,
    DRIVER_MAX_CHARS,
    LOCALES,
    SAFE_NOW_CLAUSE,
    render,
)

ALL_CAUSES = list(FaultCause)
ALL_SEVERITIES = list(Severity)


def _full_context(**overrides: object) -> dict[str, object]:
    ctx: dict[str, object] = {
        "vehicle": "TN-1234-GW",
        "eta_min": 38.0,
        "temp_c": 6.2,
        "ambient_c": 34.0,
        "place": "Sfax",
        "mins": 18.0,
        "dev_pp": 22.0,
        "v_bus": 19.8,
        "peak_g": 4.3,
    }
    ctx.update(overrides)
    return ctx


def test_every_cause_has_all_audiences_in_all_locales() -> None:
    for cause in ALL_CAUSES:
        for severity in ALL_SEVERITIES:
            for audience in AUDIENCES:
                for locale in LOCALES:
                    text = render(cause, severity, audience, locale, {}, **_full_context())
                    assert isinstance(text, str)
                    assert text.strip() != ""


def test_driver_messages_within_char_limit() -> None:
    for cause in ALL_CAUSES:
        for severity in ALL_SEVERITIES:
            for locale in LOCALES:
                text = render(cause, severity, "driver", locale, {}, **_full_context())
                assert len(text) <= DRIVER_MAX_CHARS, (cause, severity, locale, text)


def test_driver_messages_state_safety_or_countdown() -> None:
    for cause in ALL_CAUSES:
        for severity in ALL_SEVERITIES:
            for locale in LOCALES:
                text = render(cause, severity, "driver", locale, {}, **_full_context())
                if severity == Severity.watch:
                    assert SAFE_NOW_CLAUSE[locale] in text
                else:
                    clause_prefix = COUNTDOWN_CLAUSE[locale].split("{eta_min")[0]
                    assert clause_prefix in text


def test_driver_messages_have_no_banned_jargon() -> None:
    for cause in ALL_CAUSES:
        for severity in ALL_SEVERITIES:
            for locale in LOCALES:
                text = render(cause, severity, "driver", locale, {}, **_full_context())
                for term in BANNED_DRIVER_JARGON:
                    assert term not in text, (cause, severity, locale, term, text)


def test_missing_placeholder_raises() -> None:
    with pytest.raises(KeyError):
        render(FaultCause.door_unsecured, Severity.warning, "dispatcher", "fr", {})


def test_render_differs_by_locale_with_same_placeholders_filled() -> None:
    ctx = _full_context()
    fr_text = render(FaultCause.door_unsecured, Severity.warning, "dispatcher", "fr", {}, **ctx)
    en_text = render(FaultCause.door_unsecured, Severity.warning, "dispatcher", "en", {}, **ctx)
    ar_text = render(FaultCause.door_unsecured, Severity.warning, "dispatcher", "ar", {}, **ctx)

    assert fr_text != en_text
    assert fr_text != ar_text
    assert en_text != ar_text
    # Same evidence values should show up in every locale's rendering.
    for text in (fr_text, en_text, ar_text):
        assert "18" in text  # mins
        assert "6.2" in text  # temp_c
