from datetime import datetime, timedelta
from ChatbotWebsite.models import MoodEntry
from ChatbotWebsite import db

def get_recent_moods(user_id, days=7):
    """Get last N days moods"""
    cutoff = datetime.utcnow() - timedelta(days=days)
    moods = MoodEntry.query.filter(MoodEntry.user_id==user_id,
                                   MoodEntry.timestamp >= cutoff).order_by(MoodEntry.timestamp).all()
    return moods

def detect_low_mood_trend(user_id):
    """Return True if user mood <=2 for 3 consecutive days"""
    moods = get_recent_moods(user_id, days=7)
    low_streak = 0
    for mood in moods:
        if mood.mood_value <= 2:
            low_streak += 1
            if low_streak >= 3:
                return True
        else:
            low_streak = 0
    return False

def mood_summary(user_id, days=7):
    """Return weekly summary"""
    moods = get_recent_moods(user_id, days)
    if not moods:
        return None
    avg = sum(m.mood_value for m in moods)/len(moods)
    return {
        "average": round(avg,2),
        "min": min(m.mood_value for m in moods),
        "max": max(m.mood_value for m in moods),
        "count": len(moods)
    }
def mood_trends(user_id, days):
    moods = get_recent_moods(user_id, days)
    if not moods:
        return None

    avg = sum(m.mood_value for m in moods) / len(moods)

    if avg <= 2:
        level = "Low"
    elif avg <= 3.5:
        level = "Moderate"
    else:
        level = "Healthy"

    return {
        "average": round(avg, 2),
        "days": days,
        "trend": level
    }
# NEW: write mood from chatbot message
from ChatbotWebsite.chatbot.sentiment import analyze_sentiment

def save_user_mood(user_id: int, text: str):
    """
    Convert chatbot sentiment → mood value (1-5)
    and store MoodEntry.
    """
    try:
        result = analyze_sentiment(text)

        if isinstance(result, dict):
            label = result.get("label", "neutral")
            score = result.get("score", 0.5)
        else:
            label = "neutral"
            score = 0.5

        # map sentiment → mood scale (1 very bad → 5 very good)
        if label == "negative":
            mood_value = 1 if score > 0.7 else 2
        elif label == "positive":
            mood_value = 5 if score > 0.7 else 4
        else:
            mood_value = 3

        entry = MoodEntry(
            user_id=user_id,
            mood_value=mood_value,
            source="chatbot",
            timestamp=datetime.utcnow()
        )

        db.session.add(entry)

    except Exception as e:
        # never crash chat if mood saving fails
        print("Mood save failed:", e)