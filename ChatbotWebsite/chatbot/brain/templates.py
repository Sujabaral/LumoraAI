# ChatbotWebsite/chatbot/brain/templates.py
from __future__ import annotations

from typing import List, Dict, Optional, Any, Tuple
import re
import random

DISTORTION_LABELS = {
    "all_or_nothing": "all-or-nothing thinking",
    "catastrophizing": "catastrophizing (worst-case thinking)",
    "mind_reading": "mind reading (assuming others’ thoughts)",
    "overgeneralization": "overgeneralizing (one event = always)",
    "should_statements": "should/must pressure",
    "labeling": "harsh self-labeling",
    "personalization": "personalization (taking too much blame)",
    "emotional_reasoning": "emotional reasoning (I feel it, so it must be true)",
    "fortune_telling": "fortune telling (predicting a negative future)",
}

TOOL_LABELS = {
    "breathing": "breathing",
    "grounding": "grounding",
    "journaling": "journaling",
    "self_care": "self-care basics",
    "planning": "a simple plan",
    "tiny_steps": "tiny steps",
    "connection": "connection support",
    "cooldown": "anger cool-down",
    "thought_challenge": "thought check",
    "reframe_spectrum": "balanced reframe",
    "flexible_rules": "flexible rules",
    "self_compassion": "self-compassion",
    "reflection": "reflection",
}

# -------------------------
# Language helpers
# -------------------------
_DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")  # Nepali/Hindi script range

_ROMAN_NE_CRISIS = [
    "malai marna man",
    "malai marnu man",
    "ma marna chahanchu",
    "ma marnu chahanchu",
    "bachna man chaina",
    "jiuna man chaina",
    "ma sakdina aba",
    "sabai sakiyo",
]

# -------------------------
# Less-robotic openers
# -------------------------
OPENERS = {
    "neutral": [
        "Got it.",
        "Okay.",
        "Alright.",
        "I hear you.",
        "Thanks — I’m with you.",
    ],
    "listener": [
        "I hear you.",
        "That sounds heavy.",
        "That makes sense.",
        "I’m here with you.",
        "I’m listening.",
    ],
    "coach": [
        "Okay — let’s make this practical.",
        "Alright, let’s break this down.",
        "Let’s turn this into a small plan.",
        "Okay — one step at a time.",
    ],
    "therapist": [
        "Let’s slow down and unpack this.",
        "Let’s understand this together.",
        "Let’s take a breath and look at it clearly.",
        "We can sort this out step by step.",
    ],
}

NE_OPENERS = {
    "neutral": ["ठीक छ।", "हुन्छ।", "म बुझ्दैछु।", "ठिकै छ, अगाडि बढौँ।"],
    "listener": ["म बुझ्दैछु।", "यो गाह्रो लाग्नु स्वाभाविक हो।", "म यहाँ छु।", "म सुनिरहेको छु।"],
    "coach": ["हुन्छ — अब यसलाई व्यवहारिक बनाऔँ।", "ठीक छ, सानो योजना बनाऔँ।", "एक-एक कदम गरौँ।"],
    "therapist": ["यसलाई बिस्तारै बुझौँ।", "एकछिन सास फेरेर हेर्नुहोस्।", "यसलाई सँगै प्रष्ट गरौँ।"],
}


def _mode_key(style: str, profile: Dict) -> str:
    pm = (profile.get("preferred_mode") or "").lower().strip()
    s = (style or "").lower().strip()
    key = pm or s

    if key in ("listener", "validation_seeker"):
        return "listener"
    if key in ("coach", "problem_solver"):
        return "coach"
    if key in ("therapist", "overthinker"):
        return "therapist"
    return "neutral"


def _pick_opener(profile: Dict, style: str, use_nepali: bool) -> str:
    """
    Picks a short opener with variety and avoids repeating the same one back-to-back.
    Stores last opener in profile["_last_opener"] for the current request.
    """
    key = _mode_key(style, profile)
    pool = NE_OPENERS.get(key, NE_OPENERS["neutral"]) if use_nepali else OPENERS.get(key, OPENERS["neutral"])

    last = str(profile.get("_last_opener") or "").strip()
    candidates = [o for o in pool if o != last] or pool
    chosen = random.choice(candidates)

    profile["_last_opener"] = chosen
    return chosen + " "


def _is_nepali_text(text: str) -> bool:
    if not text:
        return False
    t = text.lower()
    if _DEVANAGARI_RE.search(text):
        return True
    return any(p in t for p in _ROMAN_NE_CRISIS)


def _profile_lang(profile: Dict) -> str:
    return (profile.get("lang") or profile.get("language") or "").strip().lower()


# -------------------------
# Profile helpers
# -------------------------
def _top_key(counts: Dict[str, Any]) -> Optional[str]:
    if not counts:
        return None

    def score(v: Any) -> float:
        try:
            return float(v)
        except Exception:
            return 0.0

    return max(counts.items(), key=lambda kv: score(kv[1]))[0]


def _top_trigger(profile: Dict) -> Optional[str]:
    return _top_key(profile.get("triggers") or {})


def _top_coping(profile: Dict) -> Optional[str]:
    return _top_key(profile.get("coping_pref") or {}) or _top_key(profile.get("coping_pref_json") or {})


def _strategy_name_and_tool(strategy: Any) -> Tuple[str, Optional[str], Dict[str, Any]]:
    if isinstance(strategy, str):
        return strategy, None, {}

    if isinstance(strategy, dict):
        name = strategy.get("name") or strategy.get("strategy") or strategy.get("id") or "supportive_checkin"
        tool = strategy.get("tool")
        extra = strategy.get("extra") if isinstance(strategy.get("extra"), dict) else {}
        return str(name), (str(tool) if tool else None), extra

    return "supportive_checkin", None, {}


def _trig_line(profile: Dict) -> str:
    trig = _top_trigger(profile)
    triggers = (profile.get("triggers") or {})
    trig_count = 0
    if trig and trig in triggers:
        try:
            trig_count = int(triggers.get(trig, 0) or 0)
        except Exception:
            trig_count = 0

    if trig and trig_count >= 3:
        return f" I’ve noticed {trig} stress comes up for you often."
    return ""


def _personal_tool_hint(tool: Optional[str], profile: Dict, extra: Dict[str, Any]) -> str:
    if not tool:
        return ""
    if extra.get("coping_accepted") is False:
        return ""
    if extra.get("suppress_tool_hint") is True:
        return ""

    label = TOOL_LABELS.get(tool, tool)
    top = _top_coping(profile)

    if top and top == tool:
        return f"\n\n(We can use {label} since it often helps you.)"
    return ""


def _distortion_text(distortions: List[str], max_n: int = 2) -> str:
    labels = [DISTORTION_LABELS.get(d, d) for d in (distortions or [])[:max_n]]
    return ", ".join(labels) if labels else "a thinking pattern"


# -------------------------
# Replies
# -------------------------
def render_reply(
    strategy: Any,
    emotion: str,
    style: str,
    distortions: List[str],
    profile: Dict,
    risk_level: str,
) -> str:
    name, tool, extra = _strategy_name_and_tool(strategy)

    e = (emotion or "neutral").lower()
    rl = (risk_level or "none").lower()

    trig_line = _trig_line(profile)
    tool_hint = _personal_tool_hint(tool, profile, extra)

    # detect language
    lang = _profile_lang(profile)
    last_user_text = str(profile.get("last_user_text") or "")
    use_nepali = (lang == "ne") or _is_nepali_text(last_user_text)

    # ✅ varied opener (less robotic)
    opener = _pick_opener(profile, style, use_nepali)

    # -------------------- Crisis / Safety --------------------
    if name == "crisis_escalation" or rl == "high":
        if use_nepali:
            return (
                f"{opener}यो धेरै गाह्रो भइरहेको छ।\n\n"
                "अहिले तपाईँ सुरक्षित हुनुहुन्छ?\n"
                "यदि सुरक्षित महसुस हुनुन्न भने नजिकको व्यक्तिलाई तुरुन्त भनिदिनुहोस् (परिवार/साथी) वा नजिकको अस्पताल जानुहोस्।\n\n"
                "Nepal Suicide Hotline: 1166\n\n"
                "के अहिले तपाईँ एक्लै हुनुहुन्छ, कि कसैलाई सम्पर्क गर्न सक्नुहुन्छ?"
            )

        return (
            f"{opener}I’m sorry you’re feeling this heavy.\n\n"
            "Are you safe right now?\n"
            "If you feel you might hurt yourself, please contact emergency services or go to the nearest hospital.\n"
            "If you can, tell someone nearby: I’m not safe alone right now.\n\n"
            "Is someone with you, or who can you contact right now?"
        )

    # -------------------- Medium risk --------------------
    if name == "safety_checkin" or rl == "medium":
        if use_nepali:
            return (
                f"{opener}यस्तो बेला {e} महसुस हुनु स्वाभाविक हो।{trig_line}\n\n"
                "छोटो सुरक्षा जाँच:\n"
                "• अहिले तपाईं सुरक्षित हुनुहुन्छ?\n"
                "• आफैलाई चोट पुर्‍याउने विचार आएको छ?\n\n"
                "यदि जोखिम महसुस हुन्छ भने, विश्वासिलो व्यक्तिलाई सम्पर्क गर्नुहोस् वा LUMORA को SOS/resources हेर्नुहोस्।"
                f"{tool_hint}"
            )

        return (
            f"{opener}Feeling {e} makes sense.{trig_line}\n\n"
            "Quick safety check:\n"
            "• Are you safe right now?\n"
            "• Are you having thoughts of harming yourself?\n\n"
            "If you feel at risk, reach someone you trust or use LUMORA’s SOS/resources page."
            f"{tool_hint}"
        )

    # -------------------- Loop breaker / step plan --------------------
    if name in {"step_plan", "gentle_step_plan"}:
        intro = (
            "Let’s make this practical." if name == "step_plan"
            else "Let’s take this gently, one small step at a time."
        )
        return (
            f"{opener}{intro} You’re feeling {e}.{trig_line}\n\n"
            "Tell me the problem in one line, and I’ll turn it into 3 tiny steps.\n\n"
            "Quick start (pick one):\n"
            "• 5-minute step (smallest next action)\n"
            "• Reduce pressure (what can wait?)\n"
            "• Support step (message someone)\n"
            f"{tool_hint}"
        )

    # -------------------- CBT / Reframing --------------------
    if name in {"cbt_reframe", "gentle_reframe", "cbt_plus_plan", "self_compassion_reframe"}:
        label_text = _distortion_text(distortions)

        if name == "self_compassion_reframe":
            return (
                f"{opener}It makes sense you feel {e}.{trig_line}\n\n"
                f"I’m noticing {label_text}. That can make you judge yourself harshly.\n\n"
                "Try a kinder lens:\n"
                "1) What happened (facts only)?\n"
                "2) What would you say to a friend?\n"
                "3) One small kind step today?\n"
                f"{tool_hint}"
            )

        if name == "cbt_plus_plan":
            return (
                f"{opener}It makes sense you feel {e}.{trig_line}\n\n"
                f"I’m noticing {label_text}. Let’s reframe + make a tiny plan:\n\n"
                "A) What’s the thought?\n"
                "B) What’s a more balanced version (even 10% kinder)?\n"
                "C) One tiny step next.\n"
                f"{tool_hint}"
            )

        return (
            f"{opener}It makes sense you feel {e}.{trig_line}\n\n"
            f"I’m noticing {label_text}. Let’s test it gently:\n"
            "1) Evidence for the thought?\n"
            "2) Evidence against it (even 5%)?\n"
            "3) If a friend said this, what would you say?\n"
            f"{tool_hint}"
        )

    # -------------------- Panic stabilization --------------------
    if name == "panic_stabilize":
        return (
            f"{opener}That sounds scary.\n\n"
            "When panic spikes, it can feel like you can’t breathe or you’ll faint — "
            "but this feeling is common and it passes.\n\n"
            "If you have chest pain, blue lips, severe asthma symptoms, or you actually faint, "
            "please get urgent medical help right away.\n\n"
            "Right now, let’s do one tiny step together:\n"
            "Breathe in through your nose for 4… hold 1… out slowly for 6… (x3)\n\n"
            "Tell me: is it more chest tightness, racing heart, or dizziness?"
            f"{tool_hint}"
        )

    # -------------------- Overwhelmed microstep --------------------
    if name == "grounding_microstep":
        return (
            f"{opener}You don’t have to do it perfectly.\n"
            "Let’s make it even smaller.\n\n"
            "Put both feet on the floor and press them down for 5 seconds.\n"
            "Now name just ONE thing you can see.\n\n"
            "What’s the one thing you see right now?"
            f"{tool_hint}"
        )

    # -------------------- Anxiety grounding --------------------
    if name == "validate_and_ground":
        return (
            f"{opener}That’s a lot to hold right now."
            f"{trig_line}\n\n"
            "Let’s do one simple reset together (20 seconds):\n"
            "In 4… out 6… (x3).\n\n"
            "Is it mostly racing thoughts, or body sensations?"
            f"{tool_hint}"
        )

    if name == "burnout_reset":
        return (
            f"{opener}This sounds like burnout — like you’ve been carrying too much for too long.{trig_line}\n\n"
            "Quick reset:\n"
            "1) Water / small snack\n"
            "2) 2 minutes stretch or short walk\n"
            "3) Choose one task to be minimum-effort today\n\n"
            "What’s draining you most: studies, work, family, or relationship?"
            f"{tool_hint}"
        )

    if name == "exam_support":
        return (
            f"{opener}Exam stress can feel intense.{trig_line}\n\n"
            "Answer 3 quick things and I’ll make a realistic plan:\n"
            "1) Which subject/topic?\n"
            "2) How much time today?\n"
            "3) Exam/deadline date?\n"
            f"{tool_hint}"
        )

    if name == "connection_support":
        return (
            f"{opener}Feeling alone can hurt.{trig_line}\n\n"
            "Do you want comfort right now, or help figuring out what to do next?\n"
            "If you’re open to one small step: who’s one person you could message today, even just “hey”?"
            f"{tool_hint}"
        )

    if name == "anger_cooldown":
        return (
            f"{opener}Anger often shows up when something feels unfair or hurtful.{trig_line}\n\n"
            "30-second cool-down:\n"
            "• unclench jaw/shoulders\n"
            "• inhale 4, exhale 6 (x3)\n"
            "• step away 2 minutes if you can\n\n"
            "What triggered it — and what did you need in that moment?"
            f"{tool_hint}"
        )

    if name == "guilt_reframe":
        return (
            f"{opener}Guilt can be really heavy.{trig_line}\n\n"
            "Two gentle questions:\n"
            "1) Did you do something wrong, or did you do your best with what you knew then?\n"
            "2) If there’s something to repair, what’s one small action you can take?\n\n"
            "Tell me what happened (1–2 lines) and I’ll help separate responsibility vs self-blame."
            f"{tool_hint}"
        )

    # -------------------- Supportive check-in --------------------
    if name == "supportive_checkin":
        return (
            f"{opener}{trig_line}\n\n"
            "Tell me the hardest part in one line — is it thoughts, feelings, or something happening around you?"
            f"{tool_hint}"
        )

    # -------------------- Default fallback --------------------
    return (
        f"{opener}{trig_line}\n\n"
        f"Feeling {e} can be hard. What feels strongest right now — thoughts, feelings, or what’s happening around you?"
        f"{tool_hint}"
    )