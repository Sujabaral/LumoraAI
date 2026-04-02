# ChatbotWebsite/chatbot/brain/pipeline.py
from __future__ import annotations

import os
from typing import Optional, List, Dict, Any

from ChatbotWebsite.chatbot.brain.emotion import detect_emotion
from ChatbotWebsite.chatbot.brain.distortions import detect_distortions
from ChatbotWebsite.chatbot.brain.style import detect_style, style_from_user_mode
from ChatbotWebsite.chatbot.brain.risk import assess_risk
from ChatbotWebsite.chatbot.brain.memory import (
    detect_trigger,
    get_profile_summary,
    update_profile_no_commit,
)
from ChatbotWebsite.chatbot.brain.policy import choose_strategy
from ChatbotWebsite.chatbot.brain.templates import render_reply
from ChatbotWebsite.chatbot.brain.therapeutic_presence import humanize_reply

# Map common strategy/tool names to a coping "bucket" we store in memory.
COPING_ALIASES = {
    "breathing": "breathing",
    "grounding": "grounding",
    "journal": "journaling",
    "journaling": "journaling",
    "self_care": "self_care",
    "self-care": "self_care",
    "planning": "planning",
    "plan": "planning",
    "study_plan": "planning",
    "tiny_steps": "tiny_steps",
    "connection": "connection",
    "cooldown": "cooldown",
    "reflection": "reflection",
    "thought_challenge": "thought_challenge",
    "reframe_spectrum": "reframe_spectrum",
    "flexible_rules": "flexible_rules",
    "self_compassion": "self_compassion",
}


def _normalize_coping(tool_or_name: Optional[str]) -> Optional[str]:
    if not tool_or_name:
        return None
    s = str(tool_or_name).strip().lower().replace(" ", "_")
    if s in COPING_ALIASES:
        return COPING_ALIASES[s]
    for k, v in COPING_ALIASES.items():
        if k in s:
            return v
    return None


def _infer_coping_used(strategy: Any) -> Optional[str]:
    if strategy is None:
        return None

    if isinstance(strategy, dict):
        tool = strategy.get("tool")
        if isinstance(tool, str):
            c = _normalize_coping(tool)
            if c:
                return c

        for key in ("name", "strategy", "id"):
            val = strategy.get(key)
            if isinstance(val, str):
                c = _normalize_coping(val)
                if c:
                    return c
        return None

    if isinstance(strategy, str):
        return _normalize_coping(strategy)

    return None


def _infer_coping_accepted(user_text: str) -> Optional[bool]:
    t = (user_text or "").lower()

    yes_terms = [
        "yes", "okay", "ok", "sure", "i will try", "i'll try",
        "helped", "that helped", "thanks", "thank you"
    ]
    no_terms = [
        "no", "stop", "dont", "don't",
        "didnt help", "didn't help", "doesnt help", "doesn't help"
    ]

    if any(k in t for k in yes_terms):
        return True
    if any(k in t for k in no_terms):
        return False
    return None


def generate_brain_reply(
    user_id: Optional[int],
    session_id: Optional[int],
    user_text_en: str,
    history_last_n: Optional[List[str]] = None,
    preferred_mode: Optional[str] = None,  # auto/listener/coach/therapist/balanced
) -> Dict[str, Any]:
    user_text_en = (user_text_en or "").strip()

    # 1) Emotion
    emotion, intensity, emo_details = detect_emotion(user_text_en)

    # 2) Distortions + style (apply mode override)
    distortions = detect_distortions(user_text_en)
    detected_style = detect_style(user_text_en, history_last_n=history_last_n)

    mode = (preferred_mode or "auto").lower().strip()
    style = style_from_user_mode(mode, detected_style)

    if os.getenv("LUMORA_DEBUG", "0") == "1":
        print(f"[brain] preferred_mode={mode} detected_style={detected_style} final_style={style}")

    # 3) Risk (single source of truth)
    risk_level = assess_risk(user_text_en)

    # 4) Trigger
    trigger = detect_trigger(user_text_en)

    # 5) Profile
    if user_id:
        profile = get_profile_summary(user_id) or {}
    else:
        profile = {}

    # Ensure keys exist (safe defaults)
    profile.setdefault("dominant_emotions", {})
    profile.setdefault("triggers", {})
    profile.setdefault("coping_pref", {})
    profile.setdefault("style_pref", None)
    profile.setdefault("risk_trend", None)
    profile.setdefault("last_strategy", None)

    # Attach preferred_mode into profile (templates + therapeutic_presence read it)
    profile["preferred_mode"] = mode

    # Anti-repeat guard
    recent = " ".join(history_last_n or []).lower()
    asked_checkin_recently = (
        ("what’s been the hardest part lately" in recent)
        or ("what's been the hardest part lately" in recent)
    )

    # 6) Choose strategy (IMPORTANT: pass user_text_en so your _UNSURE_SET works)
    strategy = choose_strategy(
        emotion=emotion,
        style=style,
        distortions=distortions,
        risk_level=risk_level,
        profile=profile,
        intensity=intensity,
        trigger=trigger,
        avoid_supportive_checkin=asked_checkin_recently,
        user_text_en=user_text_en,
    )

    # 7) Coping learning BEFORE render
    coping_used = _infer_coping_used(strategy)
    coping_accepted = _infer_coping_accepted(user_text_en)

    if isinstance(strategy, dict):
        strategy.setdefault("extra", {})
        strategy["extra"]["coping_used"] = coping_used
        strategy["extra"]["coping_accepted"] = coping_accepted

    # 8) Render base reply
    reply_en = render_reply(strategy, emotion, style, distortions, profile, risk_level)
    reply_en = (reply_en or "").replace("**", "")  # remove bold everywhere

    # 8.5) Humanize reply (uses profile['preferred_mode'])
    reply_en = humanize_reply(
        user_text=user_text_en,
        base_reply=reply_en,
        emotion=emotion,
        intensity=intensity,
        profile=profile,
        user_obj=None,
    )

    # 9) Memory (no commit)
    if user_id:
        update_profile_no_commit(
            user_id=user_id,
            session_id=session_id,
            emotion=emotion,
            intensity=intensity,
            distortions=distortions,
            style=style,
            trigger=trigger,
            risk_level=risk_level,
            coping_used=coping_used,
            coping_accepted=coping_accepted,
            last_strategy=(strategy.get("name") if isinstance(strategy, dict) else str(strategy)),
            user_text=user_text_en,
        )

    redirect_sos = True if risk_level in ("high", "medium") else False

    return {
        "reply_en": reply_en,
        "meta": {
            "emotion": emotion,
            "intensity": intensity,
            "emotion_confidence": getattr(emo_details, "confidence", None),
            "emotion_evidence": getattr(emo_details, "evidence", None),
            "risk_level": risk_level,
            "redirect_sos": redirect_sos,
            "distortions": distortions,
            "style": style,
            "detected_style": detected_style,
            "trigger": trigger,
            "strategy": strategy,
            "coping_used": coping_used,
            "coping_accepted": coping_accepted,
            "preferred_mode": mode,
        },
    }