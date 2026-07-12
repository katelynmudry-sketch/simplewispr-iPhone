"""Disfluency removal (D4). Two-tier conservative stripping."""

import re
from typing import Sequence

TIER1 = ["um", "uh"]

TIER2_DEFAULTS = ["like", "you know", "so", "actually", "basically",
                  "literally", "I mean", "right"]


def clean(text: str, disfluency_list: Sequence[str] | None = None) -> str:
    if disfluency_list is None:
        disfluency_list = list(TIER2_DEFAULTS) + list(TIER1)

    tier1_words = [w for w in TIER1 if w in [d.lower() for d in disfluency_list]]
    tier2_words = [w for w in disfluency_list if w.lower() not in TIER1]

    result = text

    # Tier 1: strip wherever found; replace with space so adjacent words don't merge
    if tier1_words:
        alts = "|".join(re.escape(w) for w in tier1_words)
        # Absorb surrounding comma+space; replace whole match with single space
        t1_pat = re.compile(
            rf"(?i)(?:,\s*)?\b(?:{alts})\b(?:,\s*)?",
        )
        result = t1_pat.sub(" ", result)

    # Tier 2: strip only when bounded by delimiters
    if tier2_words:
        result = _apply_tier2(result, tier2_words)

    result = _normalize(result)

    # Re-capitalize only if the first word was removed (start of result differs from start of text)
    if result and text and result[0].lower() != text[0].lower():
        result = result[0].upper() + result[1:]

    return result


def _apply_tier2(text: str, words: list[str]) -> str:
    # Sort longest first to prevent partial matches (e.g. "I mean" before "I")
    sorted_words = sorted(words, key=len, reverse=True)
    prev = None
    while prev != text:
        prev = text
        # Pass A: lone fillers (entire remaining text is just the word)
        for word in sorted_words:
            w = re.escape(word)
            text = re.sub(rf"(?i)^\s*{w}\s*$", "", text)
        # Pass B: sentence-start and sentence-end (before mid-sentence so chained
        # fillers like "So, like, ..." get their start filler removed first)
        for word in sorted_words:
            w = re.escape(word)
            text = re.sub(rf"(?im)(?:^|(?<=[\.!?…])\s*){w}\s*,\s*", "", text)
            text = re.sub(rf"(?im)\s*,\s*{w}\s*(?=$|[\.!?…])", "", text)
        # Pass C: mid-sentence , WORD, → " "
        for word in sorted_words:
            w = re.escape(word)
            text = re.sub(rf"(?i)\s*,\s*{w}\s*,\s*", " ", text)
    return text


def _normalize(text: str) -> str:
    # Collapse doubled commas
    text = re.sub(r",\s*,+", ",", text)
    # Strip leading/trailing commas
    text = re.sub(r"^\s*,\s*", "", text)
    text = re.sub(r",\s*$", "", text)
    # Fix space before punctuation
    text = re.sub(r"\s+([,\.?!…])", r"\1", text)
    # Collapse multiple spaces
    text = re.sub(r"  +", " ", text)
    return text.strip()
