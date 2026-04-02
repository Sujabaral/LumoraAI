import re
from dataclasses import dataclass
from typing import Optional

@dataclass
class LangResult:
    user_lang: str        # what user profile says
    effective_lang: str   # what we actually use for this message
    is_nepali: bool
    is_roman_nepali: bool
    reason: str = ""      # debug/helpful


_DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")

# Use regex markers with word boundaries to avoid matching inside English words.
# Also: DO NOT include super-common tokens like "ma" or "man".
_ROMAN_MARKER_PATTERNS = [
    r"\bmalai\b", r"\bmero\b", r"\btimilai\b", r"\btimi\b",
    r"\bdherai\b", r"\bekdam\b",
    r"\bdar\b", r"\baatin\b", r"\battin\b", r"\bpir\b",
    r"\btension\b", r"\bchinta\b",
    r"\blagyo\b", r"\blagiracha\b", r"\blagiraxa\b",
    r"\bxa\b", r"\bcha\b", r"\bvayo\b", r"\bvako\b",
    r"\bk\s*garum\b", r"\bkina\b", r"\bhuncha\b", r"\bhudaina\b",
    r"\bsanchai\b", r"\bsanchai\s+chha\b",
]

_ROMAN_REGEXES = [re.compile(p, re.IGNORECASE) for p in _ROMAN_MARKER_PATTERNS]


def looks_nepali(text: str) -> bool:
    return bool(_DEVANAGARI_RE.search(text or ""))


def looks_roman_nepali(text: str, min_hits: int = 2) -> bool:
    """
    Roman Nepali should require multiple signals (min_hits),
    otherwise English sentences get misclassified.
    """
    t = (text or "").strip().lower()
    if not t:
        return False

    hits = 0
    for rx in _ROMAN_REGEXES:
        if rx.search(t):
            hits += 1
            if hits >= min_hits:
                return True
    return False


def detect_language(
    message_raw: str,
    preferred_lang: str = "en",
    request_lang: Optional[str] = None,  # from frontend ("en"/"ne") if you send it
) -> LangResult:
    """
    Rules (safe + predictable):
    1) If request_lang provided ("en"/"ne"), trust it.
    2) If Devanagari present -> Nepali.
    3) If strong roman-nepali signal -> Nepali.
    4) Else -> English (NOT user preference).
       (User preference should not force translation of English input.)
    """
    user_lang = (preferred_lang or "en").lower().strip()
    if user_lang not in ("en", "ne"):
        user_lang = "en"

    req = (request_lang or "").lower().strip()
    if req in ("en", "ne"):
        # trust frontend hint
        return LangResult(
            user_lang=user_lang,
            effective_lang=req,
            is_nepali=(req == "ne" and looks_nepali(message_raw)),
            is_roman_nepali=(req == "ne" and looks_roman_nepali(message_raw)),
            reason="request_lang_override",
        )

    is_ne = looks_nepali(message_raw)
    if is_ne:
        return LangResult(
            user_lang=user_lang,
            effective_lang="ne",
            is_nepali=True,
            is_roman_nepali=False,
            reason="devanagari_detected",
        )

    is_rn = looks_roman_nepali(message_raw, min_hits=2)
    if is_rn:
        return LangResult(
            user_lang=user_lang,
            effective_lang="ne",
            is_nepali=False,
            is_roman_nepali=True,
            reason="roman_nepali_markers",
        )

    # ✅ Default for unknown = English
    return LangResult(
        user_lang=user_lang,
        effective_lang="en",
        is_nepali=False,
        is_roman_nepali=False,
        reason="default_en",
    )