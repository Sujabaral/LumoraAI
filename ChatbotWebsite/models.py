from datetime import datetime
from flask_login import UserMixin
from ChatbotWebsite import db  # single db instance
from itsdangerous import URLSafeTimedSerializer
from flask import current_app
# ---------------- Models ----------------

class User(db.Model, UserMixin):
    __tablename__ = "user"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(20), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(60), nullable=False)

    profile_image = db.Column(db.String(20), nullable=False, default="default.jpg")

    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    is_phi = db.Column(db.Boolean, default=False, nullable=False)
    is_verified = db.Column(db.Boolean, default=False, nullable=False)

    preferred_lang = db.Column(db.String(5), default="en", nullable=False)  # en/ne
    preferred_mode = db.Column(db.String(20), default="auto")

    # ✅ Relationships
    chat_sessions = db.relationship("ChatSession", backref="user", lazy=True, cascade="all, delete-orphan")
    chat_history  = db.relationship("ChatHistory", backref="user", lazy=True, cascade="all, delete-orphan")
    messages      = db.relationship("ChatMessage", backref="user", lazy=True, cascade="all, delete-orphan")
    journals      = db.relationship("Journal", backref="user", lazy=True, cascade="all, delete-orphan")
    mood_entries  = db.relationship("MoodEntry", backref="user", lazy=True, cascade="all, delete-orphan")

    assessments = db.relationship("AssessmentResult", backref="user", lazy=True, cascade="all, delete-orphan")
    feedbacks   = db.relationship("UserFeedback", backref="user", lazy=True, cascade="all, delete-orphan")
    saved_insights = db.relationship("SavedInsight", backref="user", lazy=True, cascade="all, delete-orphan")

    # ✅ Password reset token helpers
    def get_reset_token(self):
        s = URLSafeTimedSerializer(current_app.config["SECRET_KEY"])
        return s.dumps({"user_id": self.id})

    @staticmethod
    def verify_reset_token(token, expires_sec=1800):
        s = URLSafeTimedSerializer(current_app.config["SECRET_KEY"])
        try:
            data = s.loads(token, max_age=expires_sec)
            user_id = data.get("user_id")
        except Exception:
            return None
        return User.query.get(user_id)

    def __repr__(self):
        return f"User({self.username}, {self.email}, verified={self.is_verified})"
    
    
    

class Journal(db.Model):
    __tablename__ = "journal"

    id = db.Column(db.Integer, primary_key=True)

    title   = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)

    mood = db.Column(db.String(50), nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    def __repr__(self):
        return f"Journal({self.title}, user_id={self.user_id})"


class ChatSession(db.Model):
    __tablename__ = "chat_session"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    title = db.Column(db.String(120), nullable=False, default="New Chat")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    is_archived = db.Column(db.Boolean, default=False, nullable=False)

    is_starred = db.Column(db.Boolean, default=False, nullable=False)

    # analytics fields (optional)
    avg_sentiment = db.Column(db.Float, nullable=True)
    trend_slope   = db.Column(db.Float, nullable=True)
    trend_label   = db.Column(db.String(20), nullable=True)

    risk_level   = db.Column(db.String(20), nullable=True)   # low/medium/high
    risk_reasons = db.Column(db.Text, nullable=True)         # JSON string

    messages = db.relationship(
        "ChatHistory",
        backref="session",
        lazy=True,
        cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"ChatSession(id={self.id}, user_id={self.user_id}, title={self.title})"


class ChatHistory(db.Model):
    __tablename__ = "chat_history"

    id = db.Column(db.Integer, primary_key=True)

    user_id    = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    session_id = db.Column(db.Integer, db.ForeignKey("chat_session.id"), nullable=False)

    role = db.Column(db.String(20), nullable=False)  # user/assistant/system
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    emotion = db.Column(db.String(20), nullable=True)

    vader_score = db.Column(db.Float, nullable=True)
    ml_prob = db.Column(db.Text, nullable=True)        # JSON string dict
    final_score = db.Column(db.Float, nullable=True)
    confidence = db.Column(db.Float, nullable=True)

    sentiment_score = db.Column(db.Float, nullable=True)
    sentiment_label = db.Column(db.String(20), nullable=True)
    is_human_labeled = db.Column(db.Boolean, default=False, nullable=False)  # <--- ADD
    explain_tokens = db.Column(db.Text, nullable=True)  # JSON string list

    contains_self_harm = db.Column(db.Boolean, default=False, nullable=False)
    crisis_mode = db.Column(db.Boolean, default=False, nullable=False)
    human_label = db.Column(db.String(20), nullable=True)  # negative / neutral / positive

    def __repr__(self):
        return f'ChatHistory(user_id={self.user_id}, session_id={self.session_id}, role={self.role})'



class SavedInsight(db.Model):
    __tablename__ = "saved_insight"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    session_id = db.Column(db.Integer, db.ForeignKey("chat_session.id"), nullable=True)
    chat_history_id = db.Column(db.Integer, db.ForeignKey("chat_history.id"), nullable=True)

    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # optional relationships (safe for convenience)
    session = db.relationship("ChatSession", backref=db.backref("saved_insights", lazy=True))
    chat_history = db.relationship("ChatHistory", backref=db.backref("saved_insights", lazy=True))

    def __repr__(self):
        return f"SavedInsight(user_id={self.user_id}, id={self.id})"

class ChatMessage(db.Model):
    __tablename__ = "chat_message"

    id = db.Column(db.Integer, primary_key=True)

    message = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    intent_tag = db.Column(db.String(64), nullable=True)
    intent_confidence = db.Column(db.Float, nullable=True)
    session_id = db.Column(db.Integer, db.ForeignKey("chat_session.id"), nullable=True)

    def __repr__(self):
        return f'ChatMessage(user_id={self.user_id}, role={self.role})'


class MoodEntry(db.Model):
    __tablename__ = "mood_entry"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    mood_value = db.Column(db.Integer, nullable=False)

    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    source = db.Column(db.String(20), nullable=False, default="Manual")  # Manual/Chat

    def __repr__(self):
        return f"MoodEntry(user_id={self.user_id}, mood={self.mood_value})"


class PsychiatristBooking(db.Model):
    __tablename__ = "psychiatrist_booking"

    __table_args__ = (
        db.UniqueConstraint("user_id", "date", "time", name="uq_user_booking_same_slot"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    psychiatrist_id = db.Column(db.String(50), nullable=False)
    psychiatrist_name = db.Column(db.String(120), nullable=False)

    date = db.Column(db.Date, nullable=False)
    time = db.Column(db.Time, nullable=False)

    amount = db.Column(db.Integer, nullable=False, default=1500)
    payment_method = db.Column(db.String(50), nullable=True)
    paid = db.Column(db.Boolean, default=False, nullable=False)

    khalti_pidx = db.Column(db.String(60), nullable=True)
    khalti_transaction_id = db.Column(db.String(80), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    reminded_24h = db.Column(db.Boolean, default=False, nullable=False)
    reminded_1h = db.Column(db.Boolean, default=False, nullable=False)


class Appointment(db.Model):
    __tablename__ = "appointment"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    psychiatrist_id = db.Column(db.Integer, nullable=True)
    psychiatrist_name = db.Column(db.String(120), nullable=False)

    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=True)

    amount = db.Column(db.Integer, default=1500)

    method = db.Column(db.String(20), nullable=False)       # cash/khalti/esewa...
    status = db.Column(db.String(20), default="pending")    # pending/confirmed/paid/cancelled

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    reminded_24h = db.Column(db.Boolean, default=False, nullable=False)
    reminded_1h = db.Column(db.Boolean, default=False, nullable=False)

# ChatbotWebsite/models.py

from datetime import datetime
from zoneinfo import ZoneInfo

NEPAL_TZ = ZoneInfo("Asia/Kathmandu")

from datetime import datetime
from zoneinfo import ZoneInfo
from ChatbotWebsite import db

NEPAL_TZ = ZoneInfo("Asia/Kathmandu")

class Notification(db.Model):
    __tablename__ = "notification"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    title = db.Column(db.String(120), nullable=False)
    body = db.Column(db.Text, nullable=False)
    link = db.Column(db.String(255), nullable=True)

    # ✅ NEW FIELDS (needed for expiry + filtering)
    notif_type = db.Column(db.String(50), nullable=True)  # "appt_24h", "appt_1h", etc.
    appointment_dt = db.Column(db.DateTime(timezone=True), nullable=True)
    booking_id = db.Column(db.Integer, nullable=True)

    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(NEPAL_TZ))
    read = db.Column(db.Boolean, nullable=False, default=False)

    def __repr__(self):
        return f"Notification(user_id={self.user_id}, title={self.title}, read={self.read})"
class AssessmentResult(db.Model):
    __tablename__ = "assessment_result"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    type = db.Column(db.String(10), nullable=False)  # "PHQ9" or "GAD7"
    score = db.Column(db.Integer, nullable=False)
    severity = db.Column(db.String(30), nullable=False)

    answers_json = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())


class UserFeedback(db.Model):
    __tablename__ = "user_feedback"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    session_id = db.Column(db.Integer, db.ForeignKey("chat_session.id"), nullable=True)

    rating = db.Column(db.Integer, nullable=False)  # 1..5
    helpful = db.Column(db.Boolean, nullable=False, default=True)
    comments = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # ✅ Optional: link to session object (this one is OK)
    session = db.relationship("ChatSession", backref=db.backref("feedbacks", lazy=True))

from datetime import datetime
from ChatbotWebsite import db
from datetime import datetime
from ChatbotWebsite import db

class EvalDataset(db.Model):
    __tablename__ = "eval_dataset"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False, default="J1 Ground Truth Set")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)

    # membership freeze (reproducibility)
    is_frozen = db.Column(db.Boolean, default=False, nullable=False)
    # ✅ J1 ground-truth sentiment label: negative / neutral / positive
    # optional notes (for report)
    note = db.Column(db.String(255), nullable=True)


class EvalDatasetItem(db.Model):
    __tablename__ = "eval_dataset_item"

    id = db.Column(db.Integer, primary_key=True)

    dataset_id = db.Column(
        db.Integer,
        db.ForeignKey("eval_dataset.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    chat_history_id = db.Column(
        db.Integer,
        db.ForeignKey("chat_history.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    __table_args__ = (
        db.UniqueConstraint("dataset_id", "chat_history_id", name="uq_dataset_chat_history"),
    )

    dataset = db.relationship("EvalDataset", backref=db.backref("items", lazy=True, cascade="all, delete-orphan"))
    row = db.relationship("ChatHistory", backref=db.backref("eval_memberships", lazy=True))

class MessageLabel(db.Model):
    __tablename__ = "message_label"

    __table_args__ = (
        db.UniqueConstraint("message_id", "label", name="uq_message_label_message_label"),
        db.ForeignKeyConstraint(
            ["message_id"],
            ["chat_message.id"],
            name="fk_message_label_message_id",
            ondelete="CASCADE",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)

    message_id = db.Column(db.Integer, nullable=False, index=True)

    label = db.Column(db.String(32), nullable=False)
    labeled_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    labeled_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)

    # ✅ IMPORTANT: one message -> many labels now
    message = db.relationship(
        "ChatMessage",
        backref=db.backref("ground_truth", uselist=True, cascade="all, delete-orphan"),
    )
# --- ADD THIS near bottom of ChatbotWebsite/models.py ---

import json
from datetime import datetime
from ChatbotWebsite import db

# ChatbotWebsite/models.py (add/replace these classes)

import json
from datetime import datetime
from ChatbotWebsite import db


class UserEmotionProfile(db.Model):
    __tablename__ = "user_emotion_profile"

    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), primary_key=True)

    dominant_emotions_json = db.Column(db.Text, nullable=False, default="{}")
    triggers_json = db.Column(db.Text, nullable=False, default="{}")
    coping_pref_json = db.Column(db.Text, nullable=False, default="{}")

    style_pref = db.Column(db.String(50), nullable=True)
    risk_trend = db.Column(db.String(30), nullable=True)

    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    user = db.relationship("User", backref=db.backref("emotion_profile", uselist=False, cascade="all, delete-orphan", passive_deletes=True))

    # optional helpers (avoid json.loads everywhere)
    def emotions(self) -> dict:
        return json.loads(self.dominant_emotions_json or "{}")

    def triggers(self) -> dict:
        return json.loads(self.triggers_json or "{}")

    def coping(self) -> dict:
        return json.loads(self.coping_pref_json or "{}")


class UserEmotionEvent(db.Model):
    __tablename__ = "user_emotion_event"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    session_id = db.Column(db.Integer, db.ForeignKey("chat_session.id"), nullable=True)

    emotion = db.Column(db.String(30), nullable=False)
    intensity = db.Column(db.Integer, nullable=False, default=2)
    trigger = db.Column(db.String(60), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    user = db.relationship("User", backref="emotion_events")


class DistortionEvent(db.Model):
    __tablename__ = "distortion_event"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    session_id = db.Column(db.Integer, db.ForeignKey("chat_session.id"), nullable=True)

    distortions_json = db.Column(db.Text, nullable=False, default="[]")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    user = db.relationship("User", backref="distortion_events")

    def distortions(self) -> list:
        return json.loads(self.distortions_json or "[]")
    
# ChatbotWebsite/models.py

from datetime import datetime
from ChatbotWebsite import db


class CommunityPost(db.Model):
    __tablename__ = "community_post"

    id = db.Column(db.Integer, primary_key=True)

    # If your user table is named something else, adjust "user.id"
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)

    anon_alias = db.Column(db.String(80), nullable=False, index=True)

    title = db.Column(db.String(140), nullable=False)
    body = db.Column(db.Text, nullable=False)

    # store a JSON string (simple MVP)
    tags_json = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    # visible / under_review / hidden / removed
    status = db.Column(db.String(20), nullable=False, default="visible", index=True)

    # quick auto-moderation counter
    reports_count = db.Column(db.Integer, nullable=False, default=0, index=True)

    comments = db.relationship(
        "CommunityComment",
        backref="post",
        lazy=True,
        cascade="all, delete-orphan",
    )

    reactions = db.relationship(
        "CommunityReaction",
        backref="post",
        lazy=True,
        cascade="all, delete-orphan",
    )


class CommunityComment(db.Model):
    __tablename__ = "community_comment"

    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey("community_post.id"), nullable=False, index=True)

    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    anon_alias = db.Column(db.String(80), nullable=False, index=True)

    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    status = db.Column(db.String(20), nullable=False, default="visible", index=True)
    reports_count = db.Column(db.Integer, nullable=False, default=0, index=True)


class CommunityReaction(db.Model):
    __tablename__ = "community_reaction"

    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey("community_post.id"), nullable=False, index=True)

    # Recommended: reactions require login (user_id not nullable)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)

    # support / relate / heart
    type = db.Column(db.String(20), nullable=False, index=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    __table_args__ = (
        db.UniqueConstraint("post_id", "user_id", "type", name="uq_reaction_post_user_type"),
    )


class CommunityReport(db.Model):
    __tablename__ = "community_report"

    id = db.Column(db.Integer, primary_key=True)

    # guests can report too => nullable
    reporter_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)

    # one of these must be set
    post_id = db.Column(db.Integer, db.ForeignKey("community_post.id"), nullable=True, index=True)
    comment_id = db.Column(db.Integer, db.ForeignKey("community_comment.id"), nullable=True, index=True)

    reason = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    # open / reviewed / closed
    status = db.Column(db.String(20), nullable=False, default="open", index=True)  