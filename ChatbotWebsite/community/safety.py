# ChatbotWebsite/community/safety.py
import re
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class SafetyResult:
    ok: bool
    block_reason: Optional[str]
    flag_under_review: bool
    crisis: bool
    pii_found: bool
    harassment_found: bool
    matched: List[str]
    redirect_url: Optional[str] = None  # ✅ used for SOS redirect


# -------------------------
# PII patterns (MVP)
# -------------------------
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)

# Nepal-ish mobile patterns + generic 10-digit
PHONE_RE = re.compile(r"\b(?:\+?\d{1,3}[\s-]?)?(?:98|97)\d{8}\b|\b\d{10}\b")

# Address hint words (keep simple)
ADDRESS_HINT_RE = re.compile(
    r"\b(ward|tole|street|st\.|road|rd\.|house\s*no|flat|apartment)\b", re.I
)


# -------------------------
# Crisis patterns (stronger)
# -------------------------
# -------------------------
# Crisis patterns (intent-based)
# -------------------------
CRISIS_RE = re.compile(
    r"("

    # DIRECT SELF HARM
    r"\b(i\s*(want|wanna|plan|going)\s*to\s*(die|kill\s*myself))\b|"
    r"\bkill\s*myself\b|"
    r"\bend\s*my\s*life\b|"
    r"\bsuicide\b|"
    r"\bself[-\s]*harm\b|"
    r"\bcut\s*myself\b|"
    r"\boverdose\b|"

    # STRONG INTENT
    r"\bbetter\s*off\s*dead\b|"
    r"\bno\s*reason\s*to\s*live\b|"
    r"\bi\s*should\s*die\b|"
    r"\bi\s*dont\s*want\s*to\s*live\b|"
    r"\bi\s*don't\s*want\s*to\s*live\b|"
    r"\bi\s*wish\s*i\s*was\s*dead\b|"

    # INDIRECT INTENT (VERY IMPORTANT)
    r"\bi\s*can't\s*go\s*on\b|"
    r"\bcant\s*go\s*on\b|"
    r"\bi\s*give\s*up\s*on\s*life\b|"
    r"\blife\s*is\s*pointless\b|"
    r"\blife\s*is\s*meaningless\b|"
    r"\bnothing\s*matters\b|"
    r"\bi\s*am\s*done\s*with\s*life\b|"
    r"\beveryone\s*would\s*be\s*better\s*without\s*me\b|"

    # NEPALI (very important for your project)
    r"\bmarna\s*man\s*lagyo\b|"
    r"\bmarnu\s*parcha\b|"
    r"\bbachna\s*man\s*chaina\b|"
    r"\bsab\s*sakiyo\b|"
    r"\bjeevan\s*bekar\b|"
    r"\bma\s*marchu\b|"
    r"\bmalai\s*marnu\s*cha\b|"
    r"\batmahatya\b|"
    r"\bmarna\s*cha\b"

    r")",
    re.I,
)

# -------------------------
# Harassment keywords (MVP)
# -------------------------
HARASS_RE = re.compile(
    r"\b(slut|whore|retard|idiot|bitch|bastard|stupid|moron|loser)\b", re.I
)


def analyze_text(text: str, sos_url: str = "/sos") -> SafetyResult:
    """
    Returns SafetyResult:
      - crisis: hard block + redirect_url
      - pii: hard block
      - harassment: allow but under_review
    """
    t = (text or "").strip()
    matched: List[str] = []

    # -------- PII detection --------
    pii_found = False
    if EMAIL_RE.search(t):
        pii_found = True
        matched.append("email")
    if PHONE_RE.search(t):
        pii_found = True
        matched.append("phone")
    if ADDRESS_HINT_RE.search(t):
        pii_found = True
        matched.append("address_hint")

    # -------- Crisis detection --------
    crisis = bool(CRISIS_RE.search(t))
    if crisis:
        matched.append("crisis")

    # -------- Harassment detection --------
    harassment = bool(HARASS_RE.search(t))
    if harassment:
        matched.append("harassment")

    # ✅ 1) Crisis always wins: block + redirect to SOS (do not post)
    if crisis:
        return SafetyResult(
            ok=False,
            block_reason=(
                "It looks like you may be in crisis. For your safety, community posting is disabled right now. "
                "Please use SOS help instead."
            ),
            flag_under_review=False,
            crisis=True,
            pii_found=pii_found,
            harassment_found=harassment,
            matched=matched,
            redirect_url=sos_url,
        )

    # ✅ 2) PII blocks posting too
    if pii_found:
        return SafetyResult(
            ok=False,
            block_reason="Please remove personal info (phone/email/address) before posting.",
            flag_under_review=False,
            crisis=False,
            pii_found=True,
            harassment_found=harassment,
            matched=matched,
            redirect_url=None,
        )

    # ✅ 3) Otherwise: allow; harassment goes under_review
    flag_under_review = bool(harassment)

    return SafetyResult(
        ok=True,
        block_reason=None,
        flag_under_review=flag_under_review,
        crisis=False,
        pii_found=False,
        harassment_found=harassment,
        matched=matched,
        redirect_url=None,
    )