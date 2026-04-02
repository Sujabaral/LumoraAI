from __future__ import annotations

import json
from datetime import datetime
from typing import Optional, Dict, Any, List

from ChatbotWebsite import db

# Try to import your models; if names differ, adjust here.
from ChatbotWebsite.models import UserEmotionProfile, UserEmotionEvent, DistortionEvent


def _loads(v: Any) -> Dict[str, Any]:
    if not v:
        return {}
    if isinstance(v, dict):
        return v
    if isinstance(v, str):
        try:
            return json.loads(v)
        except Exception:
            return {}
    return {}


def _dumps(d: Dict[str, Any]) -> str:
    try:
        return json.dumps(d, ensure_ascii=False)
    except Exception:
        return "{}"


def _bump(counter: Dict[str, Any], key: str, delta: float) -> None:
    if not key:
        return
    cur = 0.0
    try:
        cur = float(counter.get(key, 0) or 0)
    except Exception:
        cur = 0.0
    counter[key] = cur + float(delta)


def detect_trigger(text: str) -> Optional[str]:
    t = (text or "").lower()
    if any(k in t for k in ["exam", "exams", "test", "assignment", "deadline", "study"]):
        return "exam"
    if any(k in t for k in ["family", "parents", "mother", "father", "home"]):
        return "family"
    if any(k in t for k in ["relationship", "breakup", "boyfriend", "girlfriend"]):
        return "relationship"
    if any(k in t for k in ["sleep", "insomnia", "can't sleep", "cant sleep"]):
        return "sleep"
    if any(k in t for k in ["money", "rent", "fees", "financial"]):
        return "money"
    return None


def get_profile_summary(user_id: int) -> Dict[str, Any]:
    prof = UserEmotionProfile.query.filter_by(user_id=user_id).first()
    if not prof:
        return {
            "dominant_emotions": {},
            "triggers": {},
            "coping_pref": {},
            "style_pref": None,
            "risk_trend": None,
            "last_strategy": None,
        }

    dom = _loads(getattr(prof, "dominant_emotions_json", None))
    trig = _loads(getattr(prof, "triggers_json", None))
    coping = _loads(getattr(prof, "coping_pref_json", None))
    style_pref = getattr(prof, "style_pref", None)
    risk_trend = getattr(prof, "risk_trend", None)
    last_strategy = getattr(prof, "last_strategy", None) if hasattr(prof, "last_strategy") else None

    # fallback: store last strategy inside coping json
    if not last_strategy and isinstance(coping, dict):
        last_strategy = coping.get("_last_strategy")

    return {
        "dominant_emotions": dom or {},
        "triggers": trig or {},
        "coping_pref": coping or {},
        "style_pref": style_pref,
        "risk_trend": risk_trend,
        "last_strategy": last_strategy,
    }


def update_profile_no_commit(
    user_id: int,
    session_id: Optional[int],
    emotion: str,
    intensity: int,
    distortions: List[str],
    style: str,
    trigger: Optional[str],
    risk_level: str,
    coping_used: Optional[str],
    coping_accepted: Optional[bool],
    last_strategy: Optional[str] = None,
    user_text: Optional[str] = None,
) -> None:
    prof = UserEmotionProfile.query.filter_by(user_id=user_id).first()
    if not prof:
        prof = UserEmotionProfile(user_id=user_id)
        db.session.add(prof)

    dom = _loads(getattr(prof, "dominant_emotions_json", None))
    trig = _loads(getattr(prof, "triggers_json", None))
    coping = _loads(getattr(prof, "coping_pref_json", None))

    # 1) bump dominant emotion
    if emotion:
        _bump(dom, emotion.lower(), 1)

    # 2) bump trigger frequency
    if trigger:
        _bump(trig, trigger, 1)

    # 3) update style preference
    if style:
        setattr(prof, "style_pref", style)

    # 4) coping preference learning (THIS FIXES YOUR REFLECTION LOOP)
    if coping_used:
        key = coping_used

        if coping_accepted is True:
            _bump(coping, key, +2)
        elif coping_accepted is False:
            _bump(coping, key, -3)  # ✅ rejection must reduce score
        else:
            _bump(coping, key, 0)

    # 4.5) explicit rejection phrases (extra strong)
    t = (user_text or "").lower()
    if "reflection" in t and ("no" in t or "doesnt help" in t or "doesn't help" in t):
        _bump(coping, "reflection", -10)

    # 5) risk trend (simple)
    # You can improve this later with rolling window from UserEmotionEvent.
    if risk_level == "high":
        prof.risk_trend = "worsening"
    elif risk_level == "medium":
        prof.risk_trend = getattr(prof, "risk_trend", None) or "stable"
    else:
        prof.risk_trend = getattr(prof, "risk_trend", None) or "stable"

    # 6) last strategy (prevents supportive_checkin loop)
    if last_strategy:
        if hasattr(prof, "last_strategy"):
            setattr(prof, "last_strategy", last_strategy)
        else:
            coping["_last_strategy"] = last_strategy

    # 7) write back json fields
    if hasattr(prof, "dominant_emotions_json"):
        prof.dominant_emotions_json = _dumps(dom)
    if hasattr(prof, "triggers_json"):
        prof.triggers_json = _dumps(trig)
    if hasattr(prof, "coping_pref_json"):
        prof.coping_pref_json = _dumps(coping)

    # 8) optional event logs (safe if your models exist)
    try:
        db.session.add(UserEmotionEvent(
            user_id=user_id,
            session_id=session_id,
            emotion=(emotion or "neutral"),
            intensity=int(intensity or 2),
            trigger=trigger,
            created_at=datetime.utcnow(),
        ))
    except Exception:
        # model/fields may differ; ignore safely
        pass

    try:
        if distortions:
            db.session.add(DistortionEvent(
                user_id=user_id,
                session_id=session_id,
                distortions_json=_dumps({d: 1 for d in distortions}),
                created_at=datetime.utcnow(),
            ))
    except Exception:
        pass