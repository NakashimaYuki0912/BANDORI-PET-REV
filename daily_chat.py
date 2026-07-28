"""Helpers for the fixed desktop-pet daily chat pool.

Imported lines live separately from legacy ``click_responses`` because each
character has a different number of motion groups. Runtime code accepts the
new pool only when all 24 revised lines are valid, so a partial edit falls
back to the untouched legacy greetings instead of shrinking the visible
dialogue.
"""

from __future__ import annotations


DAILY_CHAT_ENTRY_COUNT = 24


def daily_chat_entries(greetings: dict) -> list[dict[str, str]]:
    """Return validated daily-chat entries in a stable runtime shape.

    String entries remain supported for hand-edited files.  Object entries can
    additionally bind a neutral Live2D motion and expression to the text.
    Invalid or empty values are ignored instead of breaking the pet bubble.
    """
    if not isinstance(greetings, dict):
        return []

    values = greetings.get("daily_chat", [])
    if not isinstance(values, list):
        return []

    result: list[dict[str, str]] = []
    for value in values:
        if isinstance(value, str):
            text = value.strip()
            tts_text = text
            motion = ""
            expression = ""
        elif isinstance(value, dict) and isinstance(value.get("text"), str):
            text = value["text"].strip()
            tts_value = value.get("tts_text", text)
            tts_text = tts_value.strip() if isinstance(tts_value, str) else text
            motion_value = value.get("motion", "")
            expression_value = value.get("expression", "")
            motion = motion_value.strip() if isinstance(motion_value, str) else ""
            expression = (
                expression_value.strip()
                if isinstance(expression_value, str)
                else ""
            )
        else:
            continue
        if not text or not tts_text:
            continue
        result.append(
            {
                "text": text,
                "tts_text": tts_text,
                "motion": motion,
                "expression": expression,
            }
        )
    return result


def daily_chat_texts(greetings: dict) -> list[str]:
    """Return the display text from :func:`daily_chat_entries`."""
    return [entry["text"] for entry in daily_chat_entries(greetings)]


def daily_chat_tts_texts(greetings: dict) -> list[str]:
    """Return the pre-translated TTS text for the complete or partial pool."""
    return [entry["tts_text"] for entry in daily_chat_entries(greetings)]


def complete_daily_chat_entries(greetings: dict) -> list[dict[str, str]]:
    """Return the complete 24-line pool, or no entries for legacy fallback."""
    raw_entries = greetings.get("daily_chat", []) if isinstance(greetings, dict) else []
    if not isinstance(raw_entries, list) or len(raw_entries) != DAILY_CHAT_ENTRY_COUNT:
        return []
    entries = daily_chat_entries(greetings)
    texts = [entry["text"] for entry in entries]
    if len(entries) != len(raw_entries) or len(set(texts)) != len(texts):
        return []
    return entries


def complete_daily_chat_texts(greetings: dict) -> list[str]:
    """Return text from a complete pool, or no text for legacy fallback."""
    return [entry["text"] for entry in complete_daily_chat_entries(greetings)]
