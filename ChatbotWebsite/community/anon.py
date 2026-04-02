# ChatbotWebsite/community/anon.py
import random

ADJECTIVES = [
    "Gentle", "Brave", "Quiet", "Kind", "Calm", "Hopeful", "Strong", "Bright", "Soft", "Patient",
    "Steady", "Caring", "Resilient", "Thoughtful"
]

NOUNS = [
    "Sunflower", "Lotus", "River", "Mountain", "Lantern", "Cloud", "Jasmine", "Pine", "Moon", "Sparrow",
    "Butterfly", "Himalaya", "Star", "Rose"
]

def generate_alias(user_id=None) -> str:
    """
    Per-post alias (recommended MVP).
    - If logged-in: lightly incorporate user_id, but still add randomness.
    - If guest: random only.
    """
    rnd = random.Random()
    # Mild seed so alias isn't fully predictable, still changes per post
    base = f"{user_id}-{random.randint(1, 999999)}" if user_id else f"guest-{random.randint(1, 999999)}"
    rnd.seed(base)

    adj = rnd.choice(ADJECTIVES)
    noun = rnd.choice(NOUNS)
    num = rnd.randint(100, 999)

    return f"Anonymous {adj} {noun} #{num}"