# ChatbotWebsite/chatbot/chatbot_logic.py
from __future__ import annotations

import os
import re
import traceback
import requests
from datetime import datetime
from typing import Optional, List, Dict, Any, Union

from flask import url_for

from ChatbotWebsite import db
from ChatbotWebsite.models import ChatHistory, ChatMessage, MoodEntry

from ChatbotWebsite.chatbot.brain.pipeline import generate_brain_reply
from ChatbotWebsite.chatbot.brain.risk import assess_risk

# ✅ TF-IDF intent model exports (from UPDATED chatbot.py)
from ChatbotWebsite.chatbot.chatbot import (
    keras_available,
    predict_class,
)

# ------------------ Simple intent guards ------------------
_GREETINGS = {"hi", "hello", "hey", "hii", "hiii", "namaste", "hy", "yo", "sup"}
_SHORT_EMOTIONS = {"sad", "mad", "low", "fear", "hurt", "cry", "panic", "anxious", "tired", "empty"}
_OK_ACKS = {"ok", "okay", "okk", "k", "alright", "fine", "sure", "hm", "hmm"}

_META_QUESTIONS = {
    "who are you", "what are you", "are you real", "are you a bot", "what can you do",
    "what is this", "what is lumora", "who made you"
}

_UNCERTAINTY_PHRASES = {
    "i don't know", "i dont know", "idk", "dont know", "not sure", "no idea",
    "can't explain", "cant explain", "nothing", "nvm", "never mind"
}

# ✅ With CORE intents ON, these are the labels you trained on:
# ['addiction','anger','anxiety','bipolar','coping','crisis','culture','depression','eating_disorders',
#  'fun','general','goodbye','greeting','journaling','loneliness','motivation','ocd','personality',
#  'professional_help','psychosis','ptsd','relationship','schizophrenia','sleep','stress','thanks']

# ✅ Never use these as "hint steerers"
SKIP_HINT_LABELS = {
    "general", "greeting", "goodbye", "thanks"
}

# ✅ Avoid dangerous/expensive false hints (risk system handles this)
DONT_HINT_LABELS = {
    "crisis",
}

# ------------------ Normalizers ------------------
def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _is_meta_question(text: str) -> bool:
    t = _norm(text)
    if t in _META_QUESTIONS:
        return True
    return bool(re.search(r"\b(who are you|what are you|what can you do|are you real|are you a bot)\b", t))


def _is_uncertainty(text: str) -> bool:
    t = _norm(text)
    if t in _UNCERTAINTY_PHRASES:
        return True

    return bool(re.search(
        r"\b("
        r"idk|"
        r"i\s*don'?t\s*know|"
        r"don'?t\s*know|"
        r"not\s*sure|"
        r"no\s*idea|"
        r"nvm|never\s*mind|"
        r"nothing(\s+(is\s+)?helping)?|"
        r"not\s+helping|doesn'?t\s*help|no\s+help"
        r")\b",
        t
    ))


def _is_greeting(text: str) -> bool:
    t = _norm(text)
    if t in _GREETINGS:
        return True
    return bool(re.match(r"^(hi+|hey+|hello+)$", t))


def _is_too_short(text: str) -> bool:
    t = _norm(text)

    # let greeting/uncertainty handle
    if _is_greeting(t) or _is_uncertainty(t):
        return False

    if t in _SHORT_EMOTIONS:
        return False

    if len(t) < 4:
        return True

    if re.fullmatch(r"[.?!,]+", t):
        return True

    return False


def _has_signal_for_intent(text: str) -> bool:
    """
    TF-IDF safe gating: avoid predicting on super-short/noisy text.
    """
    t = _norm(text)
    if not t:
        return False
    return len(t.split()) >= 2 or len(t) >= 6


# ------------------ Locale + concision safety (guaranteed) ------------------
_US_HOTLINE_RE = re.compile(
    r"\b988\b|\bu\.s\.\b|\bunited states\b|\bcrisis line\b|\b988 in the u\.s\b",
    re.IGNORECASE
)

def _sanitize_locale(text: str) -> str:
    """
    Hard-remove US-centric hotline references that sometimes leak from LLMs.
    Keep it simple + safe.
    """
    t = (text or "").strip()

    # remove common sentence patterns
    t = re.sub(r"For immediate help.*?(?:\.|\!|\?)", "", t, flags=re.IGNORECASE)
    t = re.sub(r"contact a crisis line.*?(?:\.|\!|\?)", "", t, flags=re.IGNORECASE)
    t = re.sub(r"call 988.*?(?:\.|\!|\?)", "", t, flags=re.IGNORECASE)

    # remove explicit tokens
    t = _US_HOTLINE_RE.sub("", t)

    # tidy whitespace
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _clamp(text: str, max_chars: int = 420) -> str:
    """
    Keep output concise even if an upstream model becomes verbose.
    """
    t = re.sub(r"\s+", " ", (text or "").strip())
    if len(t) <= max_chars:
        return t
    return t[:max_chars].rstrip()


# ------------------ Mistral config ------------------
MISTRAL_KEY = os.getenv("MISTRAL_KEY")


def _looks_like_info_query(text: str) -> bool:
    """
    Heuristic: treat as general info/knowledge query (college, fees, address, admission, etc).
    Route these to Mistral first (LOW risk only).
    """
    t = _norm(text)
    if not t:
        return False

    keywords = [
        "college", "school", "university", "campus",
        "fee", "fees", "tuition", "admission", "apply", "entrance",
        "address", "location", "where", "contact", "phone", "email",
        "schedule", "time", "open", "close",
        "hostel", "library", "course", "program", "semester",
        "syllabus", "result", "notice", "website",
        "price", "cost", "rate", "deadline", "form"
    ]

    if "?" in t:
        return True
    if any(k in t for k in keywords):
        return True

    # short informational prompt like "nepal engineering college"
    if len(t.split()) >= 3 and all(w.isalpha() for w in t.split()):
        return True

    return False


# ------------------ Technique control for Mistral (therapy mode only) ------------------
TECHNIQUE_MAP = {
    "breathing": "breathing_reset",
    "grounding": "grounding_3_2_1",
    "tiny_steps": "tiny_steps_plan",
    "thought_challenge": "thought_check",
    "reframe_spectrum": "balanced_reframe",
    "flexible_rules": "flexible_rules",
    "self_compassion": "self_compassion",
    "reflection": "guided_reflection",
    "cooldown": "anger_cooldown",
    "planning": "simple_plan",
    "journaling": "one_prompt_journal",
    "connection": "connection_step",
    "self_care": "self_care_basics",
}


def _pick_one_technique(brain_meta: Dict[str, Any]) -> str:
    """
    Choose ONE technique name to allow Mistral to use.
    Preference order:
    - coping_used (from your pipeline)
    - strategy.tool if present
    - fallback: guided_reflection
    """
    tool = brain_meta.get("coping_used")
    if not tool and isinstance(brain_meta.get("strategy"), dict):
        tool = brain_meta.get("strategy", {}).get("tool")

    if not tool:
        return "guided_reflection"

    t = str(tool).strip().lower().replace(" ", "_")
    return TECHNIQUE_MAP.get(t, "guided_reflection")


def _mistral_system_prompt_concise(selected_technique: str) -> str:
    return (
        "You are LUMORA, an educational mental-health support chatbot for Nepal (not diagnostic).\n"
        "Write concise, warm replies.\n\n"
        "HARD RULES:\n"
        "- 2 to 4 short sentences max.\n"
        "- If you give steps, max 3 bullets.\n"
        "- Ask at most ONE question.\n"
        f"- Use EXACTLY ONE technique: {selected_technique}\n"
        "- Do NOT give multiple options or multiple exercises.\n"
        "- Do NOT write long explanations.\n"
        "- Do NOT mention US resources (e.g., 988) or 'crisis lines in the U.S.'\n"
        "- If user mentions self-harm, do not give techniques; tell them to use Nepal SOS resources only.\n"
        "- Do NOT use markdown bold (**).\n\n"
        "Output format (exact):\n"
        "REPLY: <final reply only>\n"
    )


def _mistral_system_prompt_info() -> str:
    return (
        "You are LUMORA, a helpful assistant for users in Nepal.\n"
        "Be concise and factual.\n"
        "HARD RULES:\n"
        "- 2 to 4 short sentences max.\n"
        "- If listing steps, max 3 bullets.\n"
        "- Do NOT mention US resources (e.g., 988) or 'crisis lines in the U.S.'\n"
        "If you are not sure, say what you need to answer (e.g., exact campus, department, year) "
        "or recommend checking the official website/notice.\n"
        "No therapy techniques.\n"
        "Do NOT use markdown bold (**).\n\n"
        "Output format (exact):\n"
        "REPLY: <final reply only>\n"
    )


def get_mistral_response(
    user_id: Optional[int],
    user_message: str,
    session_id: Optional[int] = None,
    history_last_n: Optional[List[str]] = None,
    *,
    selected_technique: str = "guided_reflection",
    user_lang: str = "en",
) -> Optional[str]:
    """
    Mistral chat completions.
    - NEVER call this for medium/high risk (enforced by caller).
    - If info query -> INFO prompt (no technique).
    - Else -> therapy prompt with EXACTLY one technique.
    """
    if not MISTRAL_KEY:
        return None

    try:
        is_info = _looks_like_info_query(user_message)
        system_prompt = _mistral_system_prompt_info() if is_info else _mistral_system_prompt_concise(selected_technique)
        messages = [{"role": "system", "content": system_prompt}]

        # Logged-in: use DB chat history
        if isinstance(user_id, int):
            q = ChatHistory.query.filter_by(user_id=user_id)
            if session_id:
                q = q.filter_by(session_id=session_id)
            history = q.order_by(ChatHistory.id.desc()).limit(6).all()
            history = list(reversed(history))
            for m in history:
                messages.append({"role": m.role, "content": (m.content or "")[:700]})
        # Guest: use provided history slice
        elif history_last_n:
            for h in history_last_n[-4:]:
                if h:
                    messages.append({"role": "user", "content": (h or "")[:500]})

        if is_info:
            messages.append({"role": "user", "content": f"Language: {user_lang}\nUser message: {user_message}"[:1500]})
        else:
            technique_rules = {
                "breathing_reset": "Give ONE 20–30 second breathing instruction. No alternatives.",
                "grounding_3_2_1": "Give ONE quick grounding step (3 things you see / 2 feel / 1 hear). No alternatives.",
                "tiny_steps_plan": "Convert the issue into ONE tiny next step + ONE question.",
                "thought_check": "Do ONE thought check: ask for evidence or a kinder reframe + ONE question.",
                "self_compassion": "Use ONE self-compassion line + ONE small kind action.",
                "guided_reflection": "Ask ONE gentle question only (no lists).",
                "anger_cooldown": "Give ONE 20–30 second cool-down step + ONE question.",
                "simple_plan": "Give ONE simple plan with 2 steps max + ONE question.",
                "one_prompt_journal": "Give ONE journaling prompt + ONE question.",
                "connection_step": "Suggest ONE connection step (message/call) + ONE question.",
                "self_care_basics": "Suggest ONE basic self-care action + ONE question.",
                "balanced_reframe": "Offer ONE balanced reframe sentence + ONE question.",
                "flexible_rules": "Suggest ONE flexible rule (reduce 'should') + ONE question.",
            }

            messages.append({
                "role": "user",
                "content": (
                    f"Language: {user_lang}\n"
                    f"Selected technique: {selected_technique}\n"
                    f"Technique rule: {technique_rules.get(selected_technique, 'Use exactly one technique.')}\n\n"
                    f"User message: {user_message}"
                )[:1500]
            })

        url = "https://api.mistral.ai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {MISTRAL_KEY}", "Content-Type": "application/json"}
        payload = {
            "model": "mistral-tiny",
            "messages": messages,
            "temperature": 0.4,
            # ✅ shorter output
            "max_tokens": 140,
        }

        r = requests.post(url, headers=headers, json=payload, timeout=20)
        r.raise_for_status()
        data = r.json()
        out = data["choices"][0]["message"]["content"].strip()

        if "REPLY:" in out:
            out = out.split("REPLY:", 1)[1].strip()

        out = out.replace("**", "").strip()
        out = _sanitize_locale(out)
        out = _clamp(out, max_chars=420)
        return out

    except Exception as e:
        print("Mistral API error:", e)
        traceback.print_exc()
        return None


# ------------------ SOS message (PLAIN TEXT) ------------------
def suicide_message_text(lang: str = "en") -> str:
    lang = (lang or "en").lower().strip()
    if lang == "ne":
        return (
            "⚠️ मलाई दुःख लाग्यो तपाईं यस्तो महसुस गर्दै हुनुहुन्छ।\n"
            "यदि तपाईं सुरक्षित छैन/आफूलाई चोट पुर्‍याउने सोच छ भने, अहिले नै सहयोग लिनुहोस्:\n"
            "• नेपाल प्रहरी: 100  • एम्बुलेन्स: 102\n"
            "• नजिकको विश्वासिलो मान्छेलाई फोन/सन्देश गर्नुहोस्।\n"
            "SOS पेज खोल्दैछु।"
        )
    return (
        "⚠️ I’m really sorry you’re feeling this way.\n"
        "If you might harm yourself or you’re not safe, please get help now:\n"
        "• Nepal Police: 100  • Ambulance: 102\n"
        "• Contact someone you trust nearby.\n"
        "I’m opening the SOS page."
    )


# ------------------ DB Saver ------------------
def _save_to_db_no_commit(user_id: int, session_id: Optional[int], user_message: str, bot_text: str):
    """
    Add ChatHistory + ChatMessage safely. DOES NOT COMMIT.
    IMPORTANT: include session_id so history features work by session.
    """
    try:
        from ChatbotWebsite.chatbot.sentiment import analyze_sentiment

        s1 = analyze_sentiment(user_message) or {}
        s2 = analyze_sentiment(bot_text) or {}

        su = float(s1.get("final_score", 0.5))
        lu = str(s1.get("label", "neutral"))
        sb = float(s2.get("final_score", 0.5))
        lb = str(s2.get("label", "neutral"))

        db.session.add(ChatHistory(
            user_id=user_id,
            session_id=session_id,
            role="user",
            content=user_message,
            sentiment_score=su,
            sentiment_label=lu
        ))
        db.session.add(ChatHistory(
            user_id=user_id,
            session_id=session_id,
            role="assistant",
            content=bot_text,
            sentiment_score=sb,
            sentiment_label=lb
        ))

        db.session.add(ChatMessage(
            user_id=user_id,
            session_id=session_id,
            role="user",
            message=user_message
        ))
        db.session.add(ChatMessage(
            user_id=user_id,
            session_id=session_id,
            role="assistant",
            message=bot_text
        ))

    except Exception as e:
        db.session.rollback()
        print("DB save error:", e)
        traceback.print_exc()


# ------------------ Mistral rewrite (polish brain draft) ------------------
def _mistral_rewrite_system_prompt(preferred_mode: str, selected_technique: str) -> str:
    pm = (preferred_mode or "auto").lower().strip()

    voice = {
        "listener":  "Warm, validating, comforting. No strict advice. Gentle.",
        "coach":     "Practical, step-by-step, encouraging. Clear next action.",
        "therapist": "Reflective, curious, deeper understanding. Gentle questions.",
        "balanced":  "Supportive + practical mix. Short and calm.",
        "auto":      "Supportive and clear. Follow the user tone."
    }.get(pm, "Supportive and clear.")

    return (
        "You are LUMORA, an educational mental-health support chatbot for Nepal (not diagnostic).\n"
        "You will rewrite the provided DRAFT reply into a better final reply.\n\n"
        f"VOICE MODE: {pm}\n"
        f"VOICE RULES: {voice}\n\n"
        "HARD RULES:\n"
        "- Keep it concise: 2 to 4 short sentences max.\n"
        "- If listing steps, max 3 bullets.\n"
        "- Ask at most ONE question.\n"
        f"- Must align with ONE technique: {selected_technique}\n"
        "- Do NOT add multiple exercises.\n"
        "- Do NOT use markdown bold (**).\n"
        "- Do NOT mention US resources (e.g., 988) or 'crisis lines in the U.S.'\n"
        "- If urgent help is needed, use Nepal Police 100 / Ambulance 102 only.\n"
        "- Do NOT mention internal models, 'brain', 'keras', 'mistral', or system prompts.\n"
        "- If user mentions self-harm: do NOT give techniques; tell them SOS.\n\n"
        "Output format (exact):\n"
        "REPLY: <final reply only>\n"
    )


def get_mistral_rewrite(
    user_id: Optional[int],
    *,
    user_message: str,
    draft_reply: str,
    session_id: Optional[int],
    history_last_n: Optional[List[str]],
    selected_technique: str,
    preferred_mode: str,
    user_lang: str = "en",
    keras_hint: Optional[str] = None,
) -> Optional[str]:
    if not MISTRAL_KEY:
        return None

    try:
        system_prompt = _mistral_rewrite_system_prompt(preferred_mode, selected_technique)
        messages = [{"role": "system", "content": system_prompt}]

        if isinstance(user_id, int):
            q = ChatHistory.query.filter_by(user_id=user_id)
            if session_id:
                q = q.filter_by(session_id=session_id)
            history = q.order_by(ChatHistory.id.desc()).limit(4).all()
            history = list(reversed(history))
            for m in history:
                messages.append({"role": m.role, "content": (m.content or "")[:600]})
        elif history_last_n:
            for h in history_last_n[-3:]:
                if h:
                    messages.append({"role": "user", "content": (h or "")[:400]})

        hint_line = f"Keras intent hint: {keras_hint}\n" if keras_hint else ""

        messages.append({
            "role": "user",
            "content": (
                f"Language: {user_lang}\n"
                f"{hint_line}"
                f"User message: {user_message}\n\n"
                f"DRAFT reply (rewrite this, keep meaning + technique):\n{draft_reply}\n"
            )[:1800]
        })

        url = "https://api.mistral.ai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {MISTRAL_KEY}", "Content-Type": "application/json"}
        payload = {
            "model": "mistral-tiny",
            "messages": messages,
            "temperature": 0.35,
            # ✅ shorter output
            "max_tokens": 160,
        }

        r = requests.post(url, headers=headers, json=payload, timeout=20)
        r.raise_for_status()
        data = r.json()
        out = data["choices"][0]["message"]["content"].strip()

        if "REPLY:" in out:
            out = out.split("REPLY:", 1)[1].strip()

        out = out.replace("**", "").strip()
        out = _sanitize_locale(out)
        out = _clamp(out, max_chars=420)
        return out

    except Exception as e:
        print("Mistral rewrite error:", e)
        traceback.print_exc()
        return None


# ------------------ Keras uncertain helper ------------------
def _keras_uncertain(brain_meta: Dict[str, Any]) -> bool:
    """
    True when Keras didn't provide a strong hint.
    """
    return not bool(brain_meta.get("keras_hint_used", False))


# ------------------ Main hybrid response (PRODUCTION SAFE) ------------------
def get_hybrid_response(
    user_message: str,
    user_id: Union[int, str] = "anon",
    session_id: Optional[int] = None,
    history_last_n: Optional[List[str]] = None,
    *,
    user_message_raw: Optional[str] = None,
    user_lang: str = "en",
    preferred_mode: str = "auto",
) -> Dict[str, Any]:
    user_message = (user_message or "").strip()
    user_message_raw = (user_message_raw or user_message).strip()
    user_lang = (user_lang or "en").lower().strip()
    preferred_mode = (preferred_mode or "auto").lower().strip()

    # 0) Greeting
    if _is_greeting(user_message):
        reply = (
            "Hi 😊 How are you feeling today? "
            "You can tell me what’s on your mind, or choose a Topic / Test / Mindfulness below."
        )
        return {"text": _clamp(reply), "crisis": False, "source": "rule_greeting", "meta": {"risk_level": "low"}}

    # 0.5) Too short
    if _is_too_short(user_message):
        t = _norm(user_message)
        if t in _OK_ACKS:
            reply = (
                "Okay 😊 Just checking in—how are you feeling right now? "
                "For example: calm, stressed, anxious, tired, or low?"
            )
        elif t.isalpha() and len(t) <= 4:
            reply = (
                f"I saw you wrote “{t}”. What does that mean for you? "
                "Is it related to exams, pressure, or something on your mind? "
                "Tell me a little more about how you’re feeling."
            )
        else:
            reply = (
                "I’m here with you. Can you share a little more—"
                "are you feeling stressed, anxious, low, angry, or overwhelmed?"
            )
        return {"text": _clamp(reply), "crisis": False, "source": "rule_short", "meta": {"risk_level": "low"}}

    # 0.75) Meta questions
    if _is_meta_question(user_message):
        reply = (
            "I’m LUMORA — a supportive mental-health chatbot for your project. "
            "I’m not a human therapist, but I can listen, help you calm down, and suggest coping steps.\n\n"
            "What’s going on right now — stress, anxiety, sadness, or something else?"
        )
        return {"text": _clamp(reply), "crisis": False, "source": "rule_meta", "meta": {"risk_level": "low"}}

    # 0.8) Uncertainty
    if _is_uncertainty(user_message):
        reply = (
            "That’s okay — we can keep it super simple. "
            "Pick one word: stress, anxiety, sad, angry, or numb.\n"
            "Or tell me what happened in one short line."
        )
        return {"text": _clamp(reply), "crisis": False, "source": "rule_uncertainty", "meta": {"risk_level": "low"}}

    # 1) Risk detection MUST use RAW text (Nepali/roman Nepali)
    risk_level = assess_risk(user_message_raw)

    if risk_level == "high":
        sos_text = suicide_message_text(user_lang)
        return {
            "text": sos_text,  # keep as-is (SOS needs clarity)
            "crisis": True,
            "source": "risk_high",
            "meta": {
                "risk_level": "high",
                "redirect_sos": True,
                "redirect_url": url_for("main.sos"),
            }
        }

    # 2) Therapeutic brain (runs for medium/low)
    brain = generate_brain_reply(
        user_id=user_id if isinstance(user_id, int) else None,
        session_id=session_id,
        user_text_en=user_message,
        history_last_n=history_last_n,
        preferred_mode=preferred_mode,
    )
    brain_meta = (brain.get("meta", {}) or {})
    brain_meta["risk_level"] = risk_level
    brain_meta["redirect_sos"] = False
    brain_meta["preferred_mode"] = preferred_mode

    # ✅ MEDIUM RISK: brain + SOS info (no Mistral)
    if risk_level == "medium":
        text = (brain.get("reply_en") or "I’m here with you.").strip()
        text = _sanitize_locale(text)
        text = _clamp(text, max_chars=520)
        text = f"{text}\n\n{suicide_message_text(user_lang)}"
        return {"text": text, "crisis": False, "source": "brain_medium", "meta": brain_meta}

    # ✅ LOW RISK: Mistral FIRST for info-like query (INFO PROMPT, no therapy technique)
    if risk_level == "low" and MISTRAL_KEY and _looks_like_info_query(user_message):
        uid = user_id if isinstance(user_id, int) else None
        selected = _pick_one_technique(brain_meta)  # unused for info mode, but fine to pass
        mistral_reply = get_mistral_response(
            uid,
            user_message,
            session_id=session_id,
            history_last_n=history_last_n,
            selected_technique=selected,
            user_lang=user_lang,
        )
        if mistral_reply:
            brain_meta["mistral_reason"] = "info_query"
            return {"text": _clamp(mistral_reply), "crisis": False, "source": "mistral", "meta": brain_meta}

    # 3) LOW RISK: Keras intent (HINT ONLY; CORE labels)
    KERAS_PROB_THRESHOLD = float(os.getenv("KERAS_PROB_THRESHOLD", "0.60"))
    KERAS_MARGIN_THRESHOLD = float(os.getenv("KERAS_MARGIN_THRESHOLD", "0.15"))

    hint_env = os.getenv(
        "LUMORA_HINT_INTENTS",
        "anxiety,stress,depression,loneliness,relationship,coping,sleep,journaling,anger,motivation,professional_help"
    )
    HINT_INTENTS = {x.strip().lower() for x in hint_env.split(",") if x.strip()}

    brain_meta["keras_hint_used"] = False  # default

    if keras_available and _has_signal_for_intent(user_message):
        try:
            uid = user_id if isinstance(user_id, int) else None
            results = predict_class(
                user_message,
                user_id=uid,
                session_id=session_id,
                prob_threshold=KERAS_PROB_THRESHOLD,
                margin_threshold=KERAS_MARGIN_THRESHOLD,
                top_k=3,
            )

            if results:
                top_intent, top_prob = results[0]
                top_intent = (top_intent or "").strip().lower()

                second_prob = float(results[1][1]) if len(results) > 1 else 0.0
                margin = float(top_prob) - float(second_prob)

                brain_meta["keras_intent"] = top_intent
                brain_meta["keras_confidence"] = float(top_prob)
                brain_meta["keras_margin"] = float(margin)

                # ✅ Never hint these
                if top_intent in DONT_HINT_LABELS or top_intent in SKIP_HINT_LABELS:
                    brain_meta["keras_hint_used"] = False
                # ✅ Hint only allowed buckets
                elif top_intent in HINT_INTENTS:
                    brain_meta["keras_intent_hint"] = top_intent
                    brain_meta["keras_hint_used"] = True
                else:
                    brain_meta["keras_hint_used"] = False
            else:
                brain_meta["keras_hint_used"] = False

        except Exception as e:
            print("❌ Keras prediction error:", e)
            traceback.print_exc()
            brain_meta["keras_hint_used"] = False

    # 3.5) ✅ LOW RISK: If Keras is uncertain OR predicts "general", let Mistral answer directly
    if MISTRAL_KEY and risk_level == "low":
        uid = user_id if isinstance(user_id, int) else None

        keras_top = (brain_meta.get("keras_intent") or "").strip().lower()
        keras_uncertain = (
            (not _has_signal_for_intent(user_message))
            or _keras_uncertain(brain_meta)
            or (keras_top in ("", "general"))
        )

        if keras_uncertain:
            selected = _pick_one_technique(brain_meta)
            direct = get_mistral_response(
                uid,
                user_message,
                session_id=session_id,
                history_last_n=history_last_n,
                selected_technique=selected,
                user_lang=user_lang,
            )
            if direct:
                brain_meta["mistral_reason"] = "keras_uncertain"
                brain_meta["mistral_technique"] = selected
                return {"text": _clamp(direct), "crisis": False, "source": "mistral_direct", "meta": brain_meta}

    # 4) LOW RISK: final response = Mistral rewrite of Brain draft (best quality)
    draft = (brain.get("reply_en") or "").strip()
    if not draft:
        draft = "I’m here with you. Tell me a little more about what’s going on."

    draft = _sanitize_locale(draft)

    selected = _pick_one_technique(brain_meta)
    keras_hint = brain_meta.get("keras_intent_hint")

    if MISTRAL_KEY and risk_level == "low":
        uid = user_id if isinstance(user_id, int) else None
        rewritten = get_mistral_rewrite(
            uid,
            user_message=user_message,
            draft_reply=draft,
            session_id=session_id,
            history_last_n=history_last_n,
            selected_technique=selected,
            preferred_mode=preferred_mode,
            user_lang=user_lang,
            keras_hint=keras_hint,
        )
        if rewritten:
            brain_meta["mistral_reason"] = "rewrite_brain"
            brain_meta["mistral_technique"] = selected
            return {"text": _clamp(rewritten), "crisis": False, "source": "brain+mistral", "meta": brain_meta}

    # If Mistral fails, return brain draft (with optional debug)
    if os.getenv("LUMORA_DEBUG", "0") == "1":
        draft += (
            f"\n\n[debug] emotion={brain_meta.get('emotion')} intensity={brain_meta.get('intensity')} "
            f"style={brain_meta.get('style')} distortions={brain_meta.get('distortions')} "
            f"strategy={brain_meta.get('strategy')} keras_hint={brain_meta.get('keras_intent_hint')}"
        )

    return {"text": _clamp(draft), "crisis": False, "source": "brain", "meta": brain_meta}


# ------------------ Mood save (unchanged) ------------------
def save_user_mood(user_id, message_or_value, source=None):
    if source is None:
        source = "Chat"

    if isinstance(message_or_value, int):
        mood_value = message_or_value
    else:
        message = str(message_or_value)
        mood_map = {
            "sad": 1, "depressed": 1,
            "angry": 2, "unhappy": 2,
            "okay": 3, "neutral": 3,
            "happy": 4,
            "excited": 5, "great": 5, "amazing": 5
        }
        mood_value = 3
        for k, v in mood_map.items():
            if k in message.lower():
                mood_value = v
                break

    mood_value = max(1, min(5, int(mood_value)))

    mood = MoodEntry(
        user_id=user_id,
        mood_value=mood_value,
        source=source,
        timestamp=datetime.utcnow()
    )
    db.session.add(mood)
    db.session.commit()


def save_user_mood_no_commit(user_id, message_or_value, source=None):
    """
    Same as save_user_mood, but DOES NOT commit.
    Use this inside routes.py so routes.py commits once at the end.
    """
    if source is None:
        source = "Chat"

    if isinstance(message_or_value, int):
        mood_value = message_or_value
    else:
        message = str(message_or_value)
        mood_map = {
            "sad": 1, "depressed": 1,
            "angry": 2, "unhappy": 2,
            "okay": 3, "neutral": 3,
            "happy": 4,
            "excited": 5, "great": 5, "amazing": 5
        }
        mood_value = 3
        for k, v in mood_map.items():
            if k in message.lower():
                mood_value = v
                break

    mood_value = max(1, min(5, int(mood_value)))

    mood = MoodEntry(
        user_id=user_id,
        mood_value=mood_value,
        source=source,
        timestamp=datetime.utcnow()
    )
    db.session.add(mood)  # ✅ NO COMMIT HERE