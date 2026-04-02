from ChatbotWebsite import create_app, db
from ChatbotWebsite.models import ChatHistory
from ChatbotWebsite.chatbot.sentiment import analyze_sentiment

app = create_app()

with app.app_context():
    rows = ChatHistory.query.filter(ChatHistory.sentiment_score.is_(None)).all()
    for r in rows:
        s, l = analyze_sentiment(r.content)
        r.sentiment_score = s
        r.sentiment_label = l
    db.session.commit()
    print("Updated:", len(rows))
