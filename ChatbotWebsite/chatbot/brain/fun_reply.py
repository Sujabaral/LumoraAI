# ChatbotWebsite/chatbot/brain/fun_reply.py
from __future__ import annotations

import random
import re
from typing import Optional


# ---- Safety: avoid encouraging harm/violence ----
_HARMY = re.compile(
    r"\b(how to|ways to|teach|train|make|force)\b.*\b(fight|attack|hurt|kill)\b|"
    r"\b(kill|torture|gore|stab|strangle)\b",
    re.IGNORECASE,
)

# Requests that *sound* violent but are often used as playful hypotheticals ("who wins", "vs", "battle")
_PLAY_BATTLE = re.compile(r"\b(who\s+wins|vs\.?|versus|battle|fight|duel)\b", re.IGNORECASE)

# Classic playful formats / entertainment requests
_FUN_REQUESTS = re.compile(
    r"\b(joke|meme|riddle|roast|pickup\s*line|fun\s*fact|would\s+you\s+rather|"
    r"truth\s+or\s+dare|guess|rank|quiz|pun)\b",
    re.IGNORECASE,
)

_LAUGH = re.compile(r"\b(lol|lmao|rofl|haha+|hehe+)\b|[😂🤣😹]", re.IGNORECASE)


def _soft_refuse_and_redirect() -> str:
    # Keeps tone light while refusing harm instructions
    return (
        "I can’t help with anything that harms people or animals. 🙏\n"
        "But we *can* keep it fun—want to turn it into a harmless version like a **race**, "
        "**game**, **debate**, or **dance battle**? 😄"
    )


def _answer_playful_vs(text: str) -> str:
    """
    Generic response for 'X vs Y / who wins' without promoting violence.
    Works for most objects/animals/characters by turning it into a harmless comparison.
    """
    t = (text or "").strip()
    # Try to extract a simple "A vs B" pair for a fun follow-up question
    m = re.search(r"(.+?)\s+\bvs\.?\b\s+(.+)", t, flags=re.IGNORECASE)
    a = b = None
    if m:
        a = m.group(1).strip(" ?!.")
        b = m.group(2).strip(" ?!.")
    # If "who wins in a A vs B fight" style
    m2 = re.search(r"who\s+wins.*?\b(a|an|the)?\s*(.+?)\s+vs\.?\s+(.+)", t, flags=re.IGNORECASE)
    if m2:
        a = (m2.group(2) or "").strip(" ?!.")
        b = (m2.group(3) or "").strip(" ?!.")

    if a and b:
        return (
            f"If it’s a real fight, nobody “wins”—someone gets hurt.\n"
            f"But as a playful hypothetical: it depends on things like size, speed, strategy, and temperament.\n"
            f"Want to make it fun and harmless: **{a} vs {b}** in a **race**, **chess**, or **cooking contest**—who takes it? 😄"
        )

    return (
        "If it’s a real fight, nobody “wins”—someone gets hurt.\n"
        "But as a playful hypothetical, it depends on size, speed, and strategy.\n"
        "Want to flip it into a harmless challenge like a **race** or **game** and pick a winner? 😄"
    )


def _joke() -> str:
    jokes = [
        "Why don’t scientists trust atoms? Because they make up everything. 😄",
        "I told my computer I needed a break… and it said: ‘No problem — I’ll go to sleep.’ 😴",
        "Why did the scarecrow win an award? Because it was outstanding in its field. 🌾",
    ]
    return random.choice(jokes)


def _riddle() -> str:
    riddles = [
        "Riddle: What has keys but can’t open locks? (Answer: a piano 🎹)",
        "Riddle: What gets wetter the more it dries? (Answer: a towel 🧻)",
        "Riddle: What has a head and a tail but no body? (Answer: a coin 🪙)",
    ]
    return random.choice(riddles)


def _pickup_line() -> str:
    lines = [
        "Are you Wi-Fi? Because I’m really feeling a connection. 📶😄",
        "Do you have a map? I keep getting lost in your thoughts. 🗺️",
        "Are you a bug? Because you’ve been running through my code all day. 🐛💻",
    ]
    return random.choice(lines)


def fun_reply(text: str, *, last_mode: Optional[str] = None) -> str:
    """
    General playful responder for FUN mode.
    - Refuses harmful requests but keeps tone friendly.
    - Handles common entertainment requests (joke, riddle, would-you-rather, roast, etc.)
    - Handles 'X vs Y' / 'who wins' prompts in a non-violent, playful way.

    last_mode: optional hint about prior conversation mode (unused for now, but useful later).
    """
    t = (text or "").strip()
    tl = t.lower()

    # 1) If user is asking for instructions to harm -> refuse + redirect
    if _HARMY.search(tl):
        return _soft_refuse_and_redirect()

    # 2) Explicit fun requests
    if "joke" in tl:
        return _joke()

    if "riddle" in tl:
        return _riddle()

    if "pickup" in tl or "pick up" in tl:
        return _pickup_line()

    if "would you rather" in tl:
        prompts = [
            "Would you rather be able to **pause time** or **rewind time**? ⏸️⏪",
            "Would you rather have **infinite snacks** or **infinite Wi-Fi**? 🍿📶",
            "Would you rather be **super fast** or **super strong**? ⚡💪",
        ]
        return random.choice(prompts)

    if "truth or dare" in tl:
        truths = [
            "Truth: What’s a skill you wish you were instantly good at?",
            "Truth: What’s the most random thing that made you laugh recently?",
        ]
        dares = [
            "Dare: Send a 😄 emoji to a friend (or just imagine doing it).",
            "Dare: Write a 1-sentence superhero name for yourself.",
        ]
        return random.choice([random.choice(truths), random.choice(dares)])

    if "roast me" in tl:
        roasts = [
            "Okay, gentle roast: you’ve got big ‘I’ll start tomorrow’ energy… but tomorrow is scared of you. 😄",
            "You’re like a loading bar—always stuck at 99% when it matters most. 😂",
        ]
        return random.choice(roasts)

    # 3) Playful battle / vs prompts -> respond safely
    if _PLAY_BATTLE.search(tl) and ("vs" in tl or "who wins" in tl):
        return _answer_playful_vs(t)

    # 4) If user is laughing, match vibe
    if _LAUGH.search(tl):
        return "😂 Same. Want a joke, a riddle, or a quick ‘would you rather’?"

    # 5) Generic FUN fallback
    return "😄 I’m down for something fun—pick one: **joke**, **riddle**, **fun fact**, or **would you rather**?"