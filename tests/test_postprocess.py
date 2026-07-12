"""Tests for postprocess.py — D4 disfluency removal.

Table of ≥20 input→expected pairs per the implementation plan.
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from postprocess import clean

# (input, expected_output) — use None to mean "same as input" (no change)
CASES = [
    # Tier 1: um / uh always stripped
    ("Um, I think so", "I think so"),
    ("I um went to the store", "I went to the store"),
    ("uh hello there", "Hello there"),
    ("That was, um, pretty good", "That was pretty good"),
    ("Uh, uh, let me think", "Let me think"),

    # Tier 2: bounded fillers stripped
    ("So, I think that's right", "I think that's right"),
    ("it was, like, huge", "it was huge"),
    ("Actually, we should go", "We should go"),
    ("We should go, actually", "We should go"),
    ("Basically, it works", "It works"),
    ("It works, basically", "It works"),
    ("Right, let's do this", "Let's do this"),
    ("You know, it's hard", "It's hard"),
    ("I mean, that's the point", "That's the point"),

    # Preservation cases — must NOT be stripped
    ("I like pizza", "I like pizza"),
    ("turn right here", "turn right here"),
    ("so far so good", "so far so good"),
    ("That's actually correct", "That's actually correct"),
    ("literally on fire", "literally on fire"),
    ("I literally can't even", "I literally can't even"),

    # Chained fillers
    ("So, like, I think", "I think"),
    ("Um, so, basically", ""),

    # Capitalization after removal
    ("like, we need to talk", "We need to talk"),

    # No double spaces left
    ("I  went", "I went"),
]


@pytest.mark.parametrize("text,expected", CASES)
def test_clean(text, expected):
    result = clean(text)
    assert result == expected, f"Input: {text!r}\nGot:      {result!r}\nExpected: {expected!r}"
