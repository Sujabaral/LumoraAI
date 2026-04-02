# ChatbotWebsite/users/utils.py

import os
import secrets
from PIL import Image

from flask import url_for, current_app, render_template
from flask_mail import Message
from itsdangerous import URLSafeTimedSerializer

from ChatbotWebsite import mail
from flask import current_app, url_for, render_template
from flask_mail import Message
from itsdangerous import URLSafeTimedSerializer  # optional (not needed if using user.get_reset_token)
from ChatbotWebsite import mail

# -----------------------------
# Save profile picture
# -----------------------------
def save_picture(form_picture):
    random_hex = secrets.token_hex(8)
    _, f_ext = os.path.splitext(form_picture.filename)
    picture_fn = random_hex + f_ext
    picture_path = os.path.join(
        current_app.root_path,
        "static/profile_images",
        picture_fn
    )

    output_size = (125, 125)
    i = Image.open(form_picture)
    i.thumbnail(output_size)
    i.save(picture_path)

    return picture_fn


# -----------------------------
# Public base URL (ngrok)
# -----------------------------
def get_public_url() -> str:
    """
    Public base URL for links in emails.
    Priority:
      1) ENV APP_BASE_URL / BASE_URL / PUBLIC_BASE_URL
      2) app.config["PUBLIC_BASE_URL"]
      3) localhost fallback
    """
    base = (
        os.getenv("APP_BASE_URL")
        or os.getenv("BASE_URL")
        or os.getenv("PUBLIC_BASE_URL")
        or current_app.config.get("PUBLIC_BASE_URL")
        or "http://127.0.0.1:5000"
    ).strip()

    base = base.rstrip("/")

    if base and not base.startswith(("http://", "https://")):
        base = "https://" + base

    return base


# -----------------------------
# Generate email confirmation token
# -----------------------------
def generate_confirmation_token(email: str) -> str:
    serializer = URLSafeTimedSerializer(current_app.config["SECRET_KEY"])
    return serializer.dumps(
        email,
        salt=current_app.config["SECURITY_PASSWORD_SALT"]
    )


# -----------------------------
# Confirm email token
# -----------------------------
def confirm_token(token: str, expiration: int = 3600):
    serializer = URLSafeTimedSerializer(current_app.config["SECRET_KEY"])
    try:
        email = serializer.loads(
            token,
            salt=current_app.config["SECURITY_PASSWORD_SALT"],
            max_age=expiration
        )
    except Exception:
        return None
    return email


# -----------------------------
# Send reset password email (PUBLIC URL for phone)
# -----------------------------
def send_reset_email(user):
    token = user.get_reset_token()

    reset_path = url_for("users.reset_token", token=token, _external=False)
    reset_url = f"{get_public_url()}{reset_path}"

    html = render_template(
        "email/reset_password.html",
        reset_url=reset_url,
        user=user
    )

    msg = Message(
        "Reset Your Password",
        sender=current_app.config.get("MAIL_USERNAME"),
        recipients=[user.email],
    )
    msg.html = html
    mail.send(msg)

# -----------------------------
# Send verification email (PUBLIC URL for phone)
# -----------------------------
def send_verification_email(user):
    token = generate_confirmation_token(user.email)

    confirm_path = url_for("users.confirm_email", token=token, _external=False)
    confirm_url = f"{get_public_url()}{confirm_path}"

    html = render_template(
        "email/confirm_email.html",
        confirm_url=confirm_url,
        user=user
    )

    msg = Message(
        "Confirm Your Email",
        sender=current_app.config.get("MAIL_USERNAME"),
        recipients=[user.email],
    )
    msg.html = html
    mail.send(msg)


# -----------------------------
# Resend verification email (PUBLIC URL for phone)
# -----------------------------
def resend_verification_email(user):
    token = generate_confirmation_token(user.email)

    confirm_path = url_for("users.confirm_email", token=token, _external=False)
    confirm_url = f"{get_public_url()}{confirm_path}"

    html = render_template(
        "email/verify_email.html",
        confirm_url=confirm_url,
        user=user
    )

    msg = Message(
        "Resend: Please Confirm Your Email",
        sender=current_app.config.get("MAIL_USERNAME"),
        recipients=[user.email],
    )
    msg.html = html
    mail.send(msg)
from collections import defaultdict
from datetime import timedelta

def calculate_positive_streak(moods, positive_threshold=3, mode="avg"):
    """
    Streak is counted per CALENDAR DAY, not per entry.
    mode="avg"  -> daily value = average mood of that day
    mode="last" -> daily value = last mood of that day
    """
    daily = defaultdict(list)

    for m in moods:
        if not getattr(m, "timestamp", None):
            continue
        daily[m.timestamp.date()].append((m.timestamp, int(m.mood_value)))

    daily_values = []
    for day, items in daily.items():
        if not items:
            continue

        if mode == "last":
            items.sort(key=lambda x: x[0])
            day_value = items[-1][1]
        else:
            vals = [v for _, v in items]
            day_value = sum(vals) / len(vals)

        daily_values.append((day, day_value))

    daily_values.sort(key=lambda x: x[0])

    streak = 0
    prev_day = None

    for day, value in daily_values:
        if value >= positive_threshold:
            if prev_day is None or day == prev_day + timedelta(days=1):
                streak += 1
            else:
                streak = 1
            prev_day = day
        else:
            streak = 0
            prev_day = None

    return streak
