import random

OPENERS = [
    "I hear you.",
    "I'm really glad you told me.",
    "That sounds heavy.",
    "That makes sense you'd feel that way.",
    "I'm here with you."
]

SOFTENERS = [
    "We can go slowly.",
    "You don't have to solve it all right now.",
    "We can just understand it first.",
    "You’re not alone in this moment."
]

FOLLOWUPS = [
    "What part of this feels hardest right now?",
    "When did this start feeling this intense?",
    "What usually goes through your mind when it happens?",
    "What worries you most about it?",
    "Does this happen often or today was different?"
]

def humanize_reply(user_text, base_reply, emotion, intensity):
    opening = random.choice(OPENERS)
    soft = random.choice(SOFTENERS)
    question = random.choice(FOLLOWUPS)

    # Short responses when overwhelmed
    if intensity >= 4:
        return f"{opening}\n\n{soft}\n\n{base_reply}\n\n{question}"

    # Reflective responses when calm
    else:
        return f"{opening}\n\n{base_reply}\n\n{soft}\n\n{question}"