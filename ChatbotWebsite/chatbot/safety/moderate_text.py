from ChatbotWebsite.chatbot.safety import detect_self_harm
from ChatbotWebsite.chatbot.brain.risk import assess_risk

def moderate_text(text: str):
    """
    Returns:
        level: low | medium | high
        should_block: bool
        should_redirect: bool
    """

    crisis = detect_self_harm(text)

    risk = assess_risk(text)

    level = risk if risk else "low"

    if level == "high":
        return level, True, True

    if level == "medium":
        return level, False, True

    return "low", False, False