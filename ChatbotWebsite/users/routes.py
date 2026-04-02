# ChatbotWebsite/users/routes.py
from __future__ import annotations

import os
from sqlalchemy import update

from flask import (
    Blueprint,
    render_template,
    request,
    url_for,
    flash,
    redirect,
    current_app,
)
from flask_login import login_user, current_user, logout_user, login_required
from flask_mail import Message

from ChatbotWebsite import db, bcrypt, mail

# ✅ CSRF (only used to exempt a couple plain POST routes)
try:
    from ChatbotWebsite import csrf
except Exception:
    csrf = None  # type: ignore

from ChatbotWebsite.models import (
    User,
    ChatSession,
    ChatHistory,
    ChatMessage,
    Journal,
    MoodEntry,
    PsychiatristBooking,
    Appointment,
    Notification,
    AssessmentResult,
    UserFeedback,
    EvalDataset,
    EvalDatasetItem,
    MessageLabel,
    UserEmotionProfile,
    UserEmotionEvent,
    DistortionEvent,
    CommunityPost,
    CommunityComment,
    CommunityReaction,
    CommunityReport,
    SavedInsight,
)

from ChatbotWebsite.users.forms import (
    RegistrationForm,
    LoginForm,
    UpdateAccountForm,
    RequestResetForm,
    ResetPasswordForm,
)
from ChatbotWebsite.users.utils import (
    save_picture,
    send_reset_email,
    generate_confirmation_token,
    confirm_token,
    get_public_url,
)

users = Blueprint("users", __name__)


# -----------------------------
# Helper: send email
# -----------------------------
def send_email(to: str, subject: str, html: str) -> None:
    msg = Message(
        subject,
        sender=current_app.config.get("MAIL_USERNAME"),
        recipients=[to],
    )
    msg.html = html
    mail.send(msg)


# -----------------------------
# Register (with email verify)
# -----------------------------
@users.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.home"))

    form = RegistrationForm()

    if form.validate_on_submit():
        if User.query.filter_by(username=form.username.data).first():
            flash("Username already exists.", "warning")
            return redirect(url_for("users.register"))

        if User.query.filter_by(email=form.email.data).first():
            flash("Email already exists.", "warning")
            return redirect(url_for("users.register"))

        hashed_password = bcrypt.generate_password_hash(form.password.data).decode("utf-8")

        new_user = User(
            username=form.username.data,
            email=form.email.data,
            password=hashed_password,
            is_verified=False,
        )

        db.session.add(new_user)
        db.session.commit()

        token = generate_confirmation_token(new_user.email)
        confirm_url = f"{get_public_url()}{url_for('users.confirm_email', token=token)}"

        html = render_template(
            "email/verify_email.html",
            confirm_url=confirm_url,
            user=new_user,
        )

        send_email(new_user.email, "Please confirm your email", html)

        flash("A confirmation email has been sent. Please check your inbox.", "info")
        return redirect(url_for("users.login"))

    return render_template("register.html", title="Register", form=form)


# -----------------------------
# Email confirmation
# -----------------------------
@users.route("/confirm/<token>")
def confirm_email(token):
    if current_user.is_authenticated:
        return redirect(url_for("main.home"))

    email = confirm_token(token)

    if not email:
        flash("Invalid or expired confirmation link.", "danger")
        return render_template("email/confirmation_failed.html")

    user = User.query.filter_by(email=email).first()

    if not user:
        flash("Account not found.", "danger")
        return render_template("email/confirmation_failed.html")

    if user.is_verified:
        flash("Account already verified. Please login.", "info")
        return render_template(
            "email/confirmation_success.html",
            already_verified=True,
            user=user,
        )

    user.is_verified = True
    db.session.commit()

    flash("Your email has been verified! You can now login.", "success")
    return render_template(
        "email/confirmation_success.html",
        already_verified=False,
        user=user,
    )


# -----------------------------
# Login
# -----------------------------
@users.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.home"))

    form = LoginForm()

    if form.validate_on_submit():
        user = User.query.filter(
            (User.email == form.username.data) | (User.username == form.username.data)
        ).first()

        if not user or not bcrypt.check_password_hash(user.password, form.password.data):
            flash("Invalid username/email or password.", "danger")
            return redirect(url_for("users.login"))

        if not user.is_verified:
            flash("Please verify your email before logging in.", "warning")
            return redirect(url_for("users.login"))

        login_user(user, remember=form.remember_me.data)
        next_page = request.args.get("next")
        return redirect(next_page) if next_page else redirect(url_for("main.home"))

    return render_template("login.html", form=form)


# -----------------------------
# Account
# -----------------------------
@users.route("/account", methods=["GET", "POST"])
@login_required
def account():
    form = UpdateAccountForm()

    if form.validate_on_submit():
        if form.picture.data:
            old_picture = current_user.profile_image
            picture_file = save_picture(form.picture.data)
            current_user.profile_image = picture_file

            if old_picture and old_picture != "default.jpg":
                try:
                    os.remove(
                        os.path.join(
                            current_app.root_path,
                            "static/profile_images",
                            old_picture,
                        )
                    )
                except Exception:
                    pass

        current_user.username = form.username.data
        current_user.email = form.email.data
        current_user.preferred_mode = form.preferred_mode.data

        db.session.commit()
        flash("Your account has been updated!", "success")
        return redirect(url_for("users.account"))

    # Prefill form on GET
    if request.method == "GET":
        form.username.data = current_user.username
        form.email.data = current_user.email
        form.preferred_mode.data = getattr(current_user, "preferred_mode", "auto") or "auto"

    return render_template("account.html", title="Account", form=form)
# -----------------------------
# Logout
# -----------------------------
@users.route("/logout")
def logout():
    logout_user()
    return redirect(url_for("main.home"))


# -----------------------------
# Delete ALL conversations for this user
# (Fixes: eval_dataset_item.chat_history_id NOT NULL)
# -----------------------------
@users.route("/delete_conversation", methods=["POST"])
@login_required
def delete_conversation():
    uid = current_user.id

    # Where did it come from?
    # - "scope" = "all" means delete ALL sessions for this user (account page)
    scope = (request.form.get("scope") or "").strip().lower()

    # Redirect target: "account" or "chat"
    next_page = (request.form.get("next") or "").strip().lower()

    # session_id for single delete (chat bin)
    session_id = request.form.get("session_id") or request.form.get("session")
    if not session_id and request.is_json:
        payload = request.get_json(silent=True) or {}
        scope = (payload.get("scope") or scope or "").strip().lower()
        next_page = (payload.get("next") or next_page or "").strip().lower()
        session_id = payload.get("session_id")

    def _redirect():
        if next_page == "chat":
            return redirect(url_for("chatbot.chat"))
        return redirect(url_for("users.account"))

    try:
        # ======================================================
        # ✅ MODE A: Delete ALL conversations for this user
        # ======================================================
        if scope == "all":
            session_ids = [r[0] for r in db.session.query(ChatSession.id)
                           .filter(ChatSession.user_id == uid).all()]

            if not session_ids:
                flash("No conversations to delete.", "info")
                return _redirect()

            # message ids across all sessions
            message_ids = [r[0] for r in db.session.query(ChatMessage.id)
                           .filter(ChatMessage.session_id.in_(session_ids)).all()]

            # labels
            if message_ids:
                MessageLabel.query.filter(MessageLabel.message_id.in_(message_ids)) \
                    .delete(synchronize_session=False)

            # session-linked tables
            UserFeedback.query.filter(UserFeedback.session_id.in_(session_ids)).delete(synchronize_session=False)
            DistortionEvent.query.filter(DistortionEvent.session_id.in_(session_ids)).delete(synchronize_session=False)
            UserEmotionEvent.query.filter(UserEmotionEvent.session_id.in_(session_ids)).delete(synchronize_session=False)
            SavedInsight.query.filter(SavedInsight.session_id.in_(session_ids)).delete(synchronize_session=False)

            # chat tables
            ChatMessage.query.filter(ChatMessage.session_id.in_(session_ids)).delete(synchronize_session=False)
            ChatHistory.query.filter(ChatHistory.session_id.in_(session_ids)).delete(synchronize_session=False)

            # sessions last
            ChatSession.query.filter(ChatSession.id.in_(session_ids)).delete(synchronize_session=False)

            db.session.commit()
            flash("All conversations deleted.", "success")
            return _redirect()

        # ======================================================
        # ✅ MODE B: Delete ONE specific session
        # ======================================================
        # Validate session_id
        try:
            session_id_int = int(session_id)
        except Exception:
            flash("Conversation not found.", "danger")
            return _redirect()

        # Must belong to the user
        s = ChatSession.query.filter_by(id=session_id_int, user_id=uid).first()
        if not s:
            flash("Conversation not found.", "danger")
            return _redirect()

        # message ids in this session
        message_ids = [r[0] for r in db.session.query(ChatMessage.id)
                       .filter(ChatMessage.session_id == session_id_int).all()]

        # labels
        if message_ids:
            MessageLabel.query.filter(MessageLabel.message_id.in_(message_ids)) \
                .delete(synchronize_session=False)

        # session-linked tables
        UserFeedback.query.filter(UserFeedback.session_id == session_id_int).delete(synchronize_session=False)
        DistortionEvent.query.filter(DistortionEvent.session_id == session_id_int).delete(synchronize_session=False)
        UserEmotionEvent.query.filter(UserEmotionEvent.session_id == session_id_int).delete(synchronize_session=False)
        SavedInsight.query.filter(SavedInsight.session_id == session_id_int).delete(synchronize_session=False)

        # chat tables
        ChatMessage.query.filter_by(session_id=session_id_int).delete(synchronize_session=False)
        ChatHistory.query.filter_by(session_id=session_id_int).delete(synchronize_session=False)

        # session last
        ChatSession.query.filter_by(id=session_id_int, user_id=uid).delete(synchronize_session=False)

        db.session.commit()
        flash("Conversation deleted.", "success")
        return _redirect()

    except Exception:
        db.session.rollback()
        current_app.logger.exception("DELETE_CONVERSATION FAILED")
        flash("Failed to delete conversation.", "danger")
        return _redirect()
# -----------------------------
# Delete account (hard delete + anonymize community)
# -----------------------------
# ChatbotWebsite/users/routes.py

from flask import Blueprint, redirect, url_for, flash
from flask_login import login_required, current_user, logout_user

from ChatbotWebsite import db
from ChatbotWebsite.models import (
    User,
    Journal,
    MoodEntry,
    ChatSession,
    ChatHistory,
    ChatMessage,
    Appointment,
    PsychiatristBooking,
    Notification,
    AssessmentResult,
    UserFeedback,
    EvalDataset,
    EvalDatasetItem,
    MessageLabel,
    UserEmotionProfile,
    UserEmotionEvent,
    DistortionEvent,
    CommunityPost,
    CommunityComment,
    CommunityReaction,
    CommunityReport,
)

# If you already have this Blueprint in your file, DO NOT re-define it.
# users = Blueprint("users", __name__)


# ----------------------------------------
# ✅ Delete ALL conversations (keep account)
# ----------------------------------------

# -----------------------------
# ✅ Delete Account (FULL)
# -----------------------------
from flask import current_app
import traceback

from flask import current_app
import traceback

from sqlalchemy.exc import IntegrityError
from flask_login import login_required, current_user, logout_user
from ChatbotWebsite import db
from ChatbotWebsite.models import User

# -----------------------------
# Delete account (hard delete)
# -----------------------------
@users.route("/delete_account", methods=["POST"])
@login_required
def delete_account():
    uid = current_user.id
    current_app.logger.warning(f"DELETE_ACCOUNT HIT uid={uid}")

    try:
        from sqlalchemy import delete

        # ---------------- session ids ----------------
        session_ids = [r[0] for r in db.session.query(ChatSession.id)
                       .filter(ChatSession.user_id == uid).all()]

        # ---------------- message ids (for labels) ----------------
        message_ids = []
        if session_ids:
            message_ids = [r[0] for r in db.session.query(ChatMessage.id)
                           .filter(ChatMessage.session_id.in_(session_ids)).all()]

        # ======================================================
        # 1) Delete things that depend on chat_message/user
        # ======================================================

        if message_ids:
            MessageLabel.query.filter(MessageLabel.message_id.in_(message_ids)) \
                .delete(synchronize_session=False)

        MessageLabel.query.filter(MessageLabel.labeled_by == uid) \
            .delete(synchronize_session=False)

        # ======================================================
        # 2) Delete session-linked tables (FK -> chat_session.id)
        # ======================================================
        if session_ids:
            UserFeedback.query.filter(UserFeedback.session_id.in_(session_ids)) \
                .delete(synchronize_session=False)

            DistortionEvent.query.filter(DistortionEvent.session_id.in_(session_ids)) \
                .delete(synchronize_session=False)

            UserEmotionEvent.query.filter(UserEmotionEvent.session_id.in_(session_ids)) \
                .delete(synchronize_session=False)

            SavedInsight.query.filter(SavedInsight.session_id.in_(session_ids)) \
                .delete(synchronize_session=False)

        # ======================================================
        # 3) Delete chat tables (FK -> chat_session.id)
        # ======================================================
        if session_ids:
            ChatMessage.query.filter(ChatMessage.session_id.in_(session_ids)) \
                .delete(synchronize_session=False)

            ChatHistory.query.filter(ChatHistory.session_id.in_(session_ids)) \
                .delete(synchronize_session=False)

        # (extra safety: if any rows exist by user_id)
        ChatMessage.query.filter(ChatMessage.user_id == uid).delete(synchronize_session=False)
        ChatHistory.query.filter(ChatHistory.user_id == uid).delete(synchronize_session=False)

        # ======================================================
        # 4) Delete user-linked tables (FK -> user.id)
        # ======================================================

        Journal.query.filter_by(user_id=uid).delete(synchronize_session=False)
        MoodEntry.query.filter_by(user_id=uid).delete(synchronize_session=False)
        Appointment.query.filter_by(user_id=uid).delete(synchronize_session=False)
        Notification.query.filter_by(user_id=uid).delete(synchronize_session=False)
        PsychiatristBooking.query.filter_by(user_id=uid).delete(synchronize_session=False)
        AssessmentResult.query.filter_by(user_id=uid).delete(synchronize_session=False)
        UserFeedback.query.filter_by(user_id=uid).delete(synchronize_session=False)
        UserEmotionProfile.query.filter_by(user_id=uid).delete(synchronize_session=False)
        DistortionEvent.query.filter_by(user_id=uid).delete(synchronize_session=False)
        UserEmotionEvent.query.filter_by(user_id=uid).delete(synchronize_session=False)
        SavedInsight.query.filter_by(user_id=uid).delete(synchronize_session=False)

        # ======================================================
        # ✅ community tables (FIXED ORDER - uses post_id)
        # ======================================================

        # all posts owned by this user
        post_ids_subq = db.session.query(CommunityPost.id).filter(CommunityPost.user_id == uid).subquery()

        # delete reports referencing those posts
        db.session.execute(
            delete(CommunityReport).where(CommunityReport.post_id.in_(post_ids_subq))
        )

        # delete reports referencing comments under those posts
        comment_ids_subq = db.session.query(CommunityComment.id).filter(
            CommunityComment.post_id.in_(post_ids_subq)
        ).subquery()
        db.session.execute(
            delete(CommunityReport).where(CommunityReport.comment_id.in_(comment_ids_subq))
        )

        # delete reactions/comments on those posts (including by other users)
        db.session.execute(delete(CommunityReaction).where(CommunityReaction.post_id.in_(post_ids_subq)))
        db.session.execute(delete(CommunityComment).where(CommunityComment.post_id.in_(post_ids_subq)))

        # cleanup: delete reports made by this user anywhere
        CommunityReport.query.filter(CommunityReport.reporter_user_id == uid) \
            .delete(synchronize_session=False)

        # cleanup: delete user's own reactions/comments anywhere
        CommunityReaction.query.filter_by(user_id=uid).delete(synchronize_session=False)
        CommunityComment.query.filter_by(user_id=uid).delete(synchronize_session=False)

        # now delete posts
        db.session.execute(delete(CommunityPost).where(CommunityPost.user_id == uid))

        # ======================================================
        # ✅ EvalDataset (items first, then datasets)  (FIXED)
        # ======================================================

        dataset_ids = [r[0] for r in db.session.query(EvalDataset.id)
                       .filter(EvalDataset.created_by == uid).all()]
        if dataset_ids:
            EvalDatasetItem.query.filter(EvalDatasetItem.dataset_id.in_(dataset_ids)) \
                .delete(synchronize_session=False)

        EvalDataset.query.filter(EvalDataset.created_by == uid) \
            .delete(synchronize_session=False)

        # ======================================================
        # 5) Delete sessions then user
        # ======================================================
        if session_ids:
            ChatSession.query.filter(ChatSession.id.in_(session_ids)) \
                .delete(synchronize_session=False)

        User.query.filter_by(id=uid).delete(synchronize_session=False)

        db.session.commit()

        logout_user()
        flash("Your account has been permanently deleted.", "success")
        return redirect(url_for("users.login"))

    except Exception:
        db.session.rollback()
        current_app.logger.exception("DELETE_ACCOUNT FAILED")
        flash("Account deletion failed.", "danger")
        return redirect(url_for("users.account"))

@users.route("/reset_password", methods=["GET", "POST"])
def reset_request():
    if current_user.is_authenticated:
        return redirect(url_for("main.home"))

    form = RequestResetForm()

    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user:
            send_reset_email(user)

        flash("If that email exists, a reset link has been sent.", "info")
        return redirect(url_for("users.login"))

    return render_template("reset_request.html", title="Reset Password", form=form)


@users.route("/reset_password/<token>", methods=["GET", "POST"])
def reset_token(token):
    if current_user.is_authenticated:
        return redirect(url_for("main.home"))

    user = User.verify_reset_token(token)
    if not user:
        flash("Invalid or expired token.", "warning")
        return redirect(url_for("users.reset_request"))

    form = ResetPasswordForm()

    if form.validate_on_submit():
        hashed_password = bcrypt.generate_password_hash(form.password.data).decode("utf-8")
        user.password = hashed_password
        db.session.commit()
        flash("Your password has been updated!", "success")
        return redirect(url_for("users.login"))

    return render_template("reset_token.html", title="Reset Password", form=form)


# -----------------------------
# Resend verification
# -----------------------------
@users.route("/resend_verification", methods=["GET", "POST"])
def resend_verification():
    if current_user.is_authenticated:
        return redirect(url_for("main.home"))

    form = LoginForm()

    if form.validate_on_submit():
        user = User.query.filter_by(email=form.username.data).first()

        if not user:
            flash("No account found with this email.", "warning")
        elif user.is_verified:
            flash("Account already verified.", "info")
        else:
            token = generate_confirmation_token(user.email)
            confirm_url = f"{get_public_url()}{url_for('users.confirm_email', token=token)}"
            html = render_template(
                "email/verify_email.html",
                confirm_url=confirm_url,
                user=user,
            )
            send_email(user.email, "Confirm your email", html)
            flash("Verification email resent.", "success")

        return redirect(url_for("users.login"))

    return render_template("resend_verification.html", title="Resend Verification", form=form)


# -----------------------------
# Set language (changes user state)
# NOTE: GET that modifies state is not ideal.
# If CSRF is enabled, change this to POST.
# -----------------------------
@users.route("/set-language/<lang>")
@login_required
def set_language(lang):
    lang = (lang or "en").lower()
    if lang not in ("en", "ne"):
        lang = "en"
    current_user.preferred_lang = lang
    db.session.commit()
    return redirect(request.referrer or url_for("chatbot.chat"))

