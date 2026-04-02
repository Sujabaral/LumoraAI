import re

_NOT_HELPING = [
    "not helping", "doesn't help", "doesnt help", "no help",
    "not working", "isn't working", "isnt working",
    "still anxious", "still panicking", "same feeling", "not better",
    "making it worse", "worse", "more anxious", "annoying",
]

_CONFUSED = [
    "i don't know", "idk", "confused", "what do you mean", "huh", "???"
]

def detect_therapy_feedback(text_en: str) -> str:
    t = (text_en or "").lower().strip()
    t = re.sub(r"\s+", " ", t)

    if any(p in t for p in _NOT_HELPING):
        return "not_helped"
    if any(p in t for p in _CONFUSED):
        return "confused"
    return "neutral"