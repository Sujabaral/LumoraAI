# ChatbotWebsite/chatbot/trend.py
from __future__ import annotations

import os
from datetime import datetime, timedelta
from sqlalchemy import func

from ChatbotWebsite import db
from ChatbotWebsite.models import ChatHistory, ChatSession

# ChatbotWebsite/chatbot/trend.py

from typing import Optional

# ✅ Reuse your existing risk logic (single source of truth)
from ChatbotWebsite.chatbot.brain.risk import assess_risk


def classify_risk(text: Optional[str]) -> str:
    """
    Compatibility wrapper for routes.py imports.
    Returns: "low" | "medium" | "high"
    """
    return assess_risk((text or "").strip())

def update_chat_trend(user_id: int, session_id: int, days: int = 14) -> None:
    """
    Updates ChatSession.trend_label and ChatSession.trend_slope using
    user's sentiment_score trend over the last N days in that session.

    Requires ChatHistory fields:
      - timestamp (datetime)
      - sentiment_score (float)
      - role ('user'/'assistant')
      - session_id (int)
    """
    now = datetime.utcnow()
    start = now - timedelta(days=days)

    # Daily average sentiment for USER messages only
    rows = (
        db.session.query(
            func.date(ChatHistory.timestamp).label("day"),
            func.avg(ChatHistory.sentiment_score).label("avg_sent"),
        )
        .filter(
            ChatHistory.user_id == user_id,
            ChatHistory.session_id == session_id,
            ChatHistory.role == "user",
            ChatHistory.sentiment_score.isnot(None),
            ChatHistory.timestamp >= start,
        )
        .group_by("day")
        .order_by("day")
        .all()
    )

    sess = ChatSession.query.filter_by(id=session_id, user_id=user_id).first()
    if not sess:
        return

    # Not enough points to compute a trend
    if len(rows) < 2:
        sess.trend_label = "stable"
        sess.trend_slope = 0.0
        db.session.commit()
        return

    # Convert to numeric x and y
    y = [float(r.avg_sent) for r in rows]
    x = list(range(len(y)))

    # Least-squares slope
    x_mean = sum(x) / len(x)
    y_mean = sum(y) / len(y)

    denom = sum((xi - x_mean) ** 2 for xi in x)
    slope = 0.0 if denom == 0 else (
        sum((xi - x_mean) * (yi - y_mean) for xi, yi in zip(x, y)) / denom
    )

    POS = float(os.getenv("TREND_POS_SLOPE", "0.02"))
    NEG = float(os.getenv("TREND_NEG_SLOPE", "-0.02"))

    if slope > POS:
        label = "improving"
    elif slope < NEG:
        label = "declining"
    else:
        label = "stable"

    sess.trend_label = label
    sess.trend_slope = float(slope)
    db.session.commit()
