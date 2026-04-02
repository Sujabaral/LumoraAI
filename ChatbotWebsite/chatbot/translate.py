import re
from functools import lru_cache
from deep_translator import GoogleTranslator

_DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")  # Nepali/Hindi script
_LATIN_RE = re.compile(r"[A-Za-z]")

def _clean_text(s: str) -> str:
    # remove zero-width chars that sometimes appear and confuse translators
    return (s or "").replace("\u200b", "").replace("\ufeff", "").strip()

def _looks_nepali(s: str) -> bool:
    return bool(_DEVANAGARI_RE.search(s or ""))

def _looks_english(s: str) -> bool:
    return bool(_LATIN_RE.search(s or ""))

@lru_cache(maxsize=4096)
def _translate_cached(text: str, target_lang: str) -> str:
    return GoogleTranslator(source="auto", target=target_lang).translate(text)

def translate_text(text: str, target_lang: str) -> str:
    """
    target_lang: 'en' or 'ne'
    Online translation (deep_translator). Returns original on failure.
    Fail-safe: avoids unnecessary translation + avoids gibberish results.
    """
    text = _clean_text(text)
    if not text:
        return text

    target_lang = (target_lang or "en").lower()
    if target_lang not in ("en", "ne"):
        return text

    # ✅ don't translate extremely short things (often becomes nonsense)
    if len(text) < 2:
        return text

    # ✅ if it already looks like the target language, skip
    if target_lang == "ne" and _looks_nepali(text):
        return text
    if target_lang == "en" and _looks_english(text) and not _looks_nepali(text):
        return text

    # ✅ protect code-ish / URLs from being mangled
    if "http://" in text or "https://" in text:
        return text

    try:
        out = _translate_cached(text, target_lang)
        out = _clean_text(out)

        # ✅ if translation failed silently or produced junk, fall back
        if not out:
            return text

        # If target is Nepali but output has no Devanagari at all, likely failed
        if target_lang == "ne" and not _looks_nepali(out):
            return text

        return out

    except Exception:
        return text