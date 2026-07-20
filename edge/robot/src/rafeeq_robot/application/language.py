from __future__ import annotations

import re


def detect_spoken_locale(text: str) -> str:
    """Return the best speech locale for a short Arabic/English transcript."""

    arabic_chars = len(re.findall(r"[\u0600-\u06FF]", text))
    latin_chars = len(re.findall(r"[A-Za-z]", text))
    if latin_chars > arabic_chars:
        return "en"
    return "ar"


def choose_locale_text(locale: str, arabic: str, english: str) -> str:
    return english if locale == "en" else arabic
