"""Character-level folding for the gates that match on words.

The consent check and the prohibited-question gate are regular expressions written with
keyboard apostrophes and ordinary spaces. Speech recognisers and language models do not
always produce those. A typographic apostrophe turned "Yes, but I'd rather you didn't
record this" into consent and let "What's your nationality?" be spoken, and a
non-breaking space let every multi-word prohibited question through. Folding happens
before matching, so how a character was typed can never change a decision.

Characters only. This does not rewrite words, strip filler or change meaning, and
nothing folded here is ever quoted back to anyone.
"""

import re
import unicodedata

#: Characters that stand in for an apostrophe in recogniser and model output.
_APOSTROPHES = {
    "’": "'",  # right single quotation mark, the usual typographic apostrophe
    "‘": "'",  # left single quotation mark
    "ʼ": "'",  # modifier letter apostrophe
    "′": "'",  # prime
}

_QUOTES = {
    "“": '"',
    "”": '"',
    "„": '"',
}

_TABLE = str.maketrans({**_APOSTROPHES, **_QUOTES})

#: Any run of whitespace, including non-breaking, thin and narrow spaces.
_SPACE = re.compile(r"\s+")


def fold(text: str) -> str:
    """Typographic apostrophes, quotes and every kind of whitespace, made plain.

    The apostrophe table runs before compatibility normalisation, which would otherwise
    turn some of these characters into something the table no longer recognises.
    Compatibility normalisation then folds fullwidth forms and non-breaking spaces.
    """
    text = text.translate(_TABLE)
    text = unicodedata.normalize("NFKC", text)
    return _SPACE.sub(" ", text).strip()
