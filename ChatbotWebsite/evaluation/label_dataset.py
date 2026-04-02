from ChatbotWebsite import create_app, db
from ChatbotWebsite.models import ChatMessage
from .auto_label import auto_label
from sqlalchemy import func

app = create_app()

with app.app_context():
    # ✅ relabel ALL user messages (overwrite old labels)
    msgs = ChatMessage.query.filter(ChatMessage.role == "user").all()

    changed = 0
    counts = {}

    for m in msgs:
        new_label = auto_label(m.message)
        if not new_label:
            continue

        old_label = m.intent_tag
        if old_label != new_label:
            changed += 1

        m.intent_tag = new_label
        counts[new_label] = counts.get(new_label, 0) + 1

    db.session.commit()

    print(f"✅ DONE AUTO LABELING (overwrote labels). Changed: {changed}")
    print("📊 New label distribution from this run:", counts)

    # ✅ optional: verify actual DB distribution (source of truth)
    db_counts = dict(
        db.session.query(ChatMessage.intent_tag, func.count())
        .filter(ChatMessage.role == "user")
        .group_by(ChatMessage.intent_tag)
        .all()
    )
    print("📊 DB label distribution:", db_counts)