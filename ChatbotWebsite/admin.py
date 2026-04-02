# ChatbotWebsite/admin.py

from flask import redirect, url_for, request
from flask_admin import Admin
from flask_admin.contrib.sqla import ModelView
from flask_login import current_user

from ChatbotWebsite import db
from ChatbotWebsite.models import (
    User,
    ChatMessage,
    Journal,
    MessageLabel,
    MoodEntry,
    Notification,
    PsychiatristBooking,
    UserEmotionEvent,
    UserEmotionProfile,
    UserFeedback,
    # community models (these exist in your models.py)
    CommunityPost,
    CommunityComment,
    CommunityReaction,
    CommunityReport,
)

# -------------------------------------------------
# Access Control
# -------------------------------------------------
def admin_only():
    return (
        current_user.is_authenticated
        and getattr(current_user, "is_admin", False) is True
    )


class SecureModelView(ModelView):
    def is_accessible(self):
        return admin_only()

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for("users.login", next=request.url))


# -------------------------------------------------
# Admin Initialization
# -------------------------------------------------
def init_admin(app):
    admin = Admin(app, name="LUMORA Admin", url="/admin")

    # ✅ Grouping into categories gives you dropdown menus
    admin.add_view(SecureModelView(User, db.session, name="Users", category="Core"))
    admin.add_view(SecureModelView(ChatMessage, db.session, name="Chat Messages", category="Core"))
    admin.add_view(SecureModelView(Journal, db.session, name="Journals", category="Core"))
    admin.add_view(SecureModelView(MoodEntry, db.session, name="Mood Entries", category="Core"))

    admin.add_view(SecureModelView(MessageLabel, db.session, name="Message Labels", category="Evaluation"))
    admin.add_view(SecureModelView(UserFeedback, db.session, name="User Feedback", category="Evaluation"))
    admin.add_view(SecureModelView(UserEmotionEvent, db.session, name="Emotion Events", category="Evaluation"))
    admin.add_view(SecureModelView(UserEmotionProfile, db.session, name="Emotion Profiles", category="Evaluation"))

    admin.add_view(SecureModelView(Notification, db.session, name="Notifications", category="Appointments"))
    admin.add_view(SecureModelView(PsychiatristBooking, db.session, name="Psychiatrist Bookings", category="Appointments"))

    # Community
    admin.add_view(SecureModelView(CommunityPost, db.session, name="Posts", category="Community"))
    admin.add_view(SecureModelView(CommunityComment, db.session, name="Comments", category="Community"))
    admin.add_view(SecureModelView(CommunityReaction, db.session, name="Reactions", category="Community"))
    admin.add_view(SecureModelView(CommunityReport, db.session, name="Reports", category="Community"))

    return admin