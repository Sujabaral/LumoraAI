# ChatbotWebsite/chatbot/brain/feedback_intent.py
import re

def detect_feedback_intent(text: str) -> str:
    t = (text or "").lower().strip()

    # Only treat as feedback if explicitly about the bot/response/technique
    not_helped = [
        "not helping", "doesn't help", "didn't help", "no help",
        "this isn't working", "not working", "it doesn't work",
        "stop", "don't do this", "change approach"
    ]
    confused = [
        "i don't understand", "confusing", "what do you mean",
        "i'm confused", "can you explain", "explain again"
    ]

    if any(p in t for p in not_helped):
        return "not_helped"

    if any(p in t for p in confused):
        return "confused"

    # IMPORTANT: don't mark generic uncertainty as feedback
    # (prevents the loop)
    return "none"