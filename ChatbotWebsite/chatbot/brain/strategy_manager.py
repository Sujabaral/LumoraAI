from dataclasses import dataclass
from typing import Any, Dict, List, Union

StrategyType = Union[str, Dict[str, Any]]

@dataclass
class StrategyDecision:
    strategy: StrategyType
    strategy_name: str
    reason: str

_UNSURE_SET = {
    "i don't know", "idk", "i dunno", "not sure", "no idea",
    "can't tell", "cant tell", "unsure"
}

def decide_strategy(
    *,
    user_text_en: str,          # ✅ add this
    is_crisis: bool,
    risk_level: str,
    feedback: str,
    emotion: str,
    style: str,
    distortions: List[str],
    profile: Dict[str, Any],
    choose_strategy_func,
) -> StrategyDecision:

    t = (user_text_en or "").strip().lower()

    # 1) Crisis always wins
    if is_crisis or risk_level == "high":
        return StrategyDecision(
            strategy="crisis_escalation",
            strategy_name="crisis_escalation",
            reason="high_risk",
        )

    # 2) If user is unsure, don't repeat the same "mind/body/both" question
    if t in _UNSURE_SET:
        return StrategyDecision(
            strategy="grounding_microstep",
            strategy_name="grounding_microstep",
            reason="user_unsure",
        )

    # 3) User feedback overrides the normal strategy
    if feedback in ("not_helped", "confused"):
        return StrategyDecision(
            strategy="pivot_support",
            strategy_name="pivot_support",
            reason=f"feedback_{feedback}",
        )

    # 4) Otherwise use your existing policy chooser
    s = choose_strategy_func(
        emotion=emotion,
        style=style,
        distortions=distortions,
        risk_level=risk_level,
        profile=profile,
    )
    name = s.get("name") if isinstance(s, dict) else str(s)
    return StrategyDecision(strategy=s, strategy_name=name, reason="default_choose_strategy")