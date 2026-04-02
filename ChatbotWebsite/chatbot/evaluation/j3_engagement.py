from ChatbotWebsite.models import ChatSession, AssessmentResult
from sqlalchemy import func

def engagement_vs_outcome(user_id):
    sessions = ChatSession.query.filter_by(user_id=user_id).count()

    avg_trend = (
        ChatSession.query
        .with_entities(func.avg(ChatSession.trend_slope))
        .filter_by(user_id=user_id)
        .scalar()
    )

    assessments = (
        AssessmentResult.query
        .filter_by(user_id=user_id)
        .order_by(AssessmentResult.created_at)
        .all()
    )

    delta = None
    if len(assessments) >= 2:
        delta = assessments[-1].score - assessments[0].score

    return {
        "sessions": sessions,
        "avg_trend": avg_trend,
        "assessment_change": delta
    }
