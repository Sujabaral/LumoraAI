from __future__ import annotations

from typing import Dict, List, Optional, Any

Strategy = Dict[str, Any]


def _top_key(counts: Dict[str, Any]) -> Optional[str]:
    if not counts:
        return None
    def score(v: Any) -> float:
        try:
            return float(v)
        except Exception:
            return 0.0
    return max(counts.items(), key=lambda kv: score(kv[1]))[0]


def _risk_priority(risk_level: str) -> Strategy:
    rl = (risk_level or "none").lower()
    if rl == "high":
        return {"name": "crisis_escalation", "tone": "urgent_calm", "tool": None, "goal": "safety"}
    if rl == "medium":
        return {"name": "safety_checkin", "tone": "calm_supportive", "tool": "grounding", "goal": "stabilize"}
    return {}


def _distortion_strategy(distortions: List[str], style: str) -> Optional[Strategy]:
    if not distortions:
        return None

    s = (style or "").lower()

    if s in {"overthinker", "validation_seeker", "neutral"}:
        if "catastrophizing" in distortions or "fortune_telling" in distortions:
            return {"name": "cbt_reframe", "tone": "calm", "tool": "thought_challenge", "focus": "worst_case"}
        if "all_or_nothing" in distortions or "overgeneralization" in distortions:
            return {"name": "cbt_reframe", "tone": "calm", "tool": "reframe_spectrum", "focus": "balanced_thinking"}
        if "labeling" in distortions or "personalization" in distortions:
            return {"name": "self_compassion_reframe", "tone": "warm", "tool": "self_compassion", "focus": "identity_vs_behavior"}
        if "should_statements" in distortions:
            return {"name": "cbt_reframe", "tone": "warm", "tool": "flexible_rules", "focus": "should_to_prefer"}
        return {"name": "cbt_reframe", "tone": "calm", "tool": "thought_challenge", "focus": "general"}

    if s == "problem_solver":
        return {"name": "cbt_plus_plan", "tone": "calm", "tool": "planning", "focus": "actionable"}

    return {"name": "gentle_reframe", "tone": "warm", "tool": "thought_challenge", "focus": "soft"}


def _emotion_strategy(emotion: str, intensity: int, style: str, trigger: Optional[str]) -> Strategy:
    e = (emotion or "neutral").lower()
    s = (style or "").lower()
    intensity = int(intensity or 2)

    if intensity >= 4 and e in {"anxiety", "burnout"}:
        return {"name": "validate_and_ground", "tone": "calm", "tool": "grounding", "focus": "body"}

    if e == "anxiety":
        if trigger == "exam":
            return {"name": "exam_support", "tone": "calm", "tool": "planning", "focus": "study_plan"}
        return {"name": "validate_and_ground", "tone": "calm", "tool": "breathing", "focus": "present"}

    if e == "burnout":
        return {"name": "burnout_reset", "tone": "warm", "tool": "self_care", "focus": "rest_boundaries"}

    if e == "sadness":
        if s == "problem_solver":
            return {"name": "gentle_step_plan", "tone": "warm", "tool": "tiny_steps", "focus": "minimum_day"}
        return {"name": "validation_and_reflection", "tone": "warm", "tool": "journaling", "focus": "feelings"}

    if e == "anger":
        return {"name": "anger_cooldown", "tone": "calm", "tool": "cooldown", "focus": "regulation"}

    if e == "guilt":
        return {"name": "guilt_reframe", "tone": "warm", "tool": "self_compassion", "focus": "repair_learning"}

    if e == "neutral":
        if s == "lonely":
            return {"name": "connection_support", "tone": "warm", "tool": "connection", "focus": "reach_out"}
        return {"name": "supportive_checkin", "tone": "warm", "tool": None, "focus": "clarify"}

    return {"name": "supportive_checkin", "tone": "warm", "tool": None, "focus": "clarify"}


def _personalize_with_profile(strategy: Strategy, profile: Dict) -> Strategy:
    if not profile:
        return strategy

    out = dict(strategy)
    out.setdefault("extra", {})

    # read prefs
    coping = profile.get("coping_pref") or profile.get("coping_pref_json") or {}
    last_strategy = profile.get("last_strategy")

    # keep for debugging
    out["extra"]["last_strategy"] = last_strategy

    # if last was supportive_checkin, bias away to avoid loops
    if last_strategy == "supportive_checkin" and out.get("name") == "supportive_checkin":
        return {"name": "step_plan", "tone": "calm", "tool": "tiny_steps", "focus": "next_steps", "extra": {"loop_break": True}}

    # prefer top tool IF positive
    top_tool = _top_key(coping)
    if top_tool:
        try:
            if float(coping.get(top_tool, 0)) > 0 and out.get("name") not in {"crisis_escalation", "safety_checkin"}:
                out["tool"] = top_tool
                out["extra"]["personalized_tool"] = True
        except Exception:
            pass

    # don’t force strongly disliked tools
    if out.get("tool") and top_tool:
        try:
            if float(coping.get(out["tool"], 0)) < 0:
                out["tool"] = None
                out["extra"]["tool_blocked"] = True
        except Exception:
            pass

    return out


def choose_strategy(
    emotion: str,
    style: str,
    distortions: List[str],
    risk_level: str,
    profile: Dict,
    intensity: int = 2,
    trigger: Optional[str] = None,
    avoid_supportive_checkin: bool = False,
) -> Strategy:
    # 1) Risk-first
    r = _risk_priority(risk_level)
    if r:
        return _personalize_with_profile(r, profile)

    # 2) Distortions → CBT
    d = _distortion_strategy(distortions, style)
    if d:
        return _personalize_with_profile(d, profile)

    # 3) Emotion-based default
    base = _emotion_strategy(emotion, intensity, style, trigger)

    # 3.5) Anti-repeat: if we already asked “hardest part lately”, don’t do it again
    if avoid_supportive_checkin and base.get("name") == "supportive_checkin":
        base = {"name": "step_plan", "tone": "calm", "tool": "tiny_steps", "focus": "next_steps", "extra": {"avoid_repeat": True}}

    return _personalize_with_profile(base, profile)