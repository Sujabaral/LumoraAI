# ChatbotWebsite/main/routes.py

import os
import requests
from datetime import datetime, timedelta, time as dtime

from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session,
    jsonify,
    current_app,
)
from flask_login import login_required, current_user

from ChatbotWebsite import db
from ChatbotWebsite.models import Notification, PsychiatristBooking, ChatHistory, ChatSession


main = Blueprint("main", __name__)

# ----------------------------
# ngrok helper header (removes "Visit Site" warning)
# ----------------------------
@main.after_app_request
def add_ngrok_header(resp):
    resp.headers["ngrok-skip-browser-warning"] = "1"
    return resp


# ----------------------------
# Helpers / Config
# ----------------------------
FIXED_AMOUNT = 1500
KHALTI_BASE = "https://dev.khalti.com/api/v2"  # sandbox
LOCAL_FALLBACK_BASE = "http://127.0.0.1:5000"


def get_app_base_url() -> str:
    """
    Priority:
      1) ENV APP_BASE_URL (ngrok URL)
      2) app.config["PUBLIC_BASE_URL"] (if set)
      3) local fallback
    """
    env_url = (os.getenv("APP_BASE_URL") or "").strip()
    if env_url:
        return env_url.rstrip("/")

    cfg_url = (current_app.config.get("PUBLIC_BASE_URL") or "").strip()
    if cfg_url:
        return cfg_url.rstrip("/")

    return LOCAL_FALLBACK_BASE


def khalti_headers():
    """
    Return headers if key exists; otherwise return None (no crash).
    """
    secret = (os.getenv("KHALTI_SECRET_KEY") or "").strip()
    if not secret:
        return None
    return {
        "Authorization": f"Key {secret}",
        "Content-Type": "application/json",
    }


def is_public_base_url(base_url: str) -> bool:
    # Khalti cannot call 127.0.0.1 / localhost for return_url
    return not ("127.0.0.1" in base_url or "localhost" in base_url)


from ChatbotWebsite.utils import NEPAL_TZ

def booking_start_dt(b: PsychiatristBooking) -> datetime:
    """Combine booking date+time into a Nepal timezone-aware datetime."""
    return datetime(
        b.date.year, b.date.month, b.date.day,
        b.time.hour, b.time.minute, b.time.second,
        tzinfo=NEPAL_TZ
    )

# ----------------------------
# Auto cleanup unpaid bookings
# ----------------------------
UNPAID_EXPIRY_MINUTES = 15

def cleanup_unpaid_bookings():
    expiry_time = datetime.utcnow() - timedelta(minutes=UNPAID_EXPIRY_MINUTES)

    stale = (
        PsychiatristBooking.query
        .filter(PsychiatristBooking.paid == False)
        .filter(PsychiatristBooking.created_at <= expiry_time)
        .all()
    )

    for b in stale:
        db.session.delete(b)

    if stale:
        db.session.commit()

# ----------------------------
# Psychiatrists (Demo List)
# ----------------------------
PSYCHIATRISTS = [
    {
        "id": "dr-shrestha",
        "name": "Dr. Asha Shrestha",
        "specialty": "Anxiety, Depression",
        "location": "Kathmandu",
        "fee": 1500,
        "languages": ["Nepali", "English"],
        "availability": "Mon–Fri (4pm–8pm)",
        "about": "Focuses on CBT-based care and medication management.",
        "image": "images/psychiatrists/dr_asha.jpg",
    },
    {
        "id": "dr-kc",
        "name": "Dr. Rohan KC",
        "specialty": "Stress, Burnout, Sleep",
        "location": "Lalitpur",
        "fee": 1200,
        "languages": ["Nepali", "English", "Hindi"],
        "availability": "Sun–Thu (10am–2pm)",
        "about": "Works with students and young adults; burnout & sleep hygiene.",
        "image": "images/psychiatrists/dr_rohan.jpg",
    },
    {
        "id": "dr-gurung",
        "name": "Dr. Mira Gurung",
        "specialty": "Trauma, PTSD",
        "location": "Online",
        "fee": 2000,
        "languages": ["English", "Nepali"],
        "availability": "By appointment",
        "about": "Trauma-informed care, supportive counseling + meds when needed.",
        "image": "images/psychiatrists/dr_mira.jpg",
    },
]

# Availability rules used for validation (simple + viva-friendly)
# 0=Mon ... 6=Sun
PSYCHIATRIST_SLOTS = {
    "dr-shrestha": {  # Mon–Fri 4pm–8pm
        "days": {0, 1, 2, 3, 4},
        "start": "16:00",
        "end": "20:00",
    },
    "dr-kc": {  # Sun–Thu 10am–2pm
        "days": {6, 0, 1, 2, 3},
        "start": "10:00",
        "end": "14:00",
    },
    "dr-gurung": {  # Wider for demo
        "days": {0, 1, 2, 3, 4, 5, 6},
        "start": "09:00",
        "end": "20:00",
    },
}


def parse_hhmm(s: str) -> dtime:
    return datetime.strptime(s, "%H:%M").time()


def is_within_availability(psychiatrist_id: str, booking_date, booking_time) -> bool:
    rule = PSYCHIATRIST_SLOTS.get(psychiatrist_id)
    if not rule:
        return False

    weekday = booking_date.weekday()  # Mon=0..Sun=6
    if weekday not in rule["days"]:
        return False

    start_t = parse_hhmm(rule["start"])
    end_t = parse_hhmm(rule["end"])
    return start_t <= booking_time <= end_t


    from datetime import timedelta
from ChatbotWebsite.utils import now_nepal, NEPAL_TZ
from sqlalchemy import and_

def booking_start_dt(b: PsychiatristBooking):
    # Nepal-aware datetime
    return datetime(
        b.date.year, b.date.month, b.date.day,
        b.time.hour, b.time.minute, b.time.second,
        tzinfo=NEPAL_TZ
    )

def check_booking_reminders():
    """
    HOME page: show flash banners ONLY.
    DO NOT flip reminded flags here (scheduler handles that),
    otherwise notifications never get created.
    """
    if not getattr(current_user, "is_authenticated", False):
        return

    now = now_nepal()

    bookings = (
        PsychiatristBooking.query
        .filter_by(user_id=current_user.id)
        .filter(PsychiatristBooking.paid == True)
        .all()
    )
    if not bookings:
        return

    future = [b for b in bookings if booking_start_dt(b) >= now]
    if not future:
        return

    future.sort(key=lambda x: booking_start_dt(x))
    b = future[0]
    dt = booking_start_dt(b)
    diff = dt - now

    if diff <= timedelta(hours=24):
        flash(
            f"⏰ Reminder: You have an appointment with {b.psychiatrist_name} within 24 hours "
            f"({dt.strftime('%Y-%m-%d %H:%M')}).",
            "info",
        )

    if diff <= timedelta(hours=1):
        flash(
            f"🚨 Reminder: Your appointment with {b.psychiatrist_name} is within 1 hour "
            f"({dt.strftime('%Y-%m-%d %H:%M')}).",
            "warning",
        )
        


# ----------------------------
# Home
# ----------------------------
from sqlalchemy import or_
from zoneinfo import ZoneInfo
from datetime import datetime

NEPAL_TZ = ZoneInfo("Asia/Kathmandu")
from ChatbotWebsite.reminders import run_booking_reminders

@main.route("/")
def home():
    if getattr(current_user, "is_authenticated", False):
        check_booking_reminders()

        # ✅ Generate DB notifications now (instant)
        run_booking_reminders()

        now = datetime.now(NEPAL_TZ)
        notes = (
            Notification.query
            .filter(Notification.user_id == current_user.id)
            .filter(
                or_(
                    Notification.notif_type.is_(None),
                    Notification.appointment_dt >= now
                )
            )
            .order_by(Notification.created_at.desc())
            .limit(5)
            .all()
        )
    else:
        notes = []
    return render_template("home.html", title="Lumora AI", notes=notes)
@main.route("/about")
def about():
    return render_template("about.html", title="About")


@main.route("/sos")
def sos():
    return render_template("sos.html", title="SOS")


# ----------------------------
# Calendar API (home calendar uses this)
# ----------------------------
@main.route("/api/bookings")
@login_required
def api_bookings():
    bookings = (
    PsychiatristBooking.query
    .filter_by(user_id=current_user.id)
    .filter(PsychiatristBooking.paid == True)
    .order_by(PsychiatristBooking.date.asc(), PsychiatristBooking.time.asc())
    .all()
)


    events = []
    for b in bookings:
        start_dt = datetime.combine(b.date, b.time)
        end_dt = start_dt + timedelta(minutes=30)

        events.append(
            {
                "id": b.id,
                "psychiatrist_name": b.psychiatrist_name,
                "start": start_dt.isoformat(),
                "end": end_dt.isoformat(),
                "paid": bool(b.paid),
                "payment_method": (b.payment_method or "").lower(),
                "amount": b.amount,
            }
        )

    return jsonify(events)


# ✅ Used by booking page to disable times already booked for selected date
@main.route("/api/booked-slots")
@login_required
def api_booked_slots():
    date_str = request.args.get("date")
    psychiatrist_id = request.args.get("psychiatrist_id")

    if not date_str or not psychiatrist_id:
        return jsonify({"slots": []})

    try:
        booking_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"slots": []}), 400

    rows = (
    PsychiatristBooking.query
    .filter_by(date=booking_date, psychiatrist_id=psychiatrist_id)
    .filter(PsychiatristBooking.paid == True)
    .all()
)


    slots = sorted([r.time.strftime("%H:%M") for r in rows])
    return jsonify({"slots": slots})


# ----------------------------
# Psychiatrists Page
# ----------------------------
@main.route("/psychiatrist", methods=["GET", "POST"])
@login_required
def psychiatrist_page():
    if request.method == "POST":
        selected_id = request.form.get("psychiatrist_id")
        chosen = next((p for p in PSYCHIATRISTS if p["id"] == selected_id), None)

        if not chosen:
            flash("Please select a valid psychiatrist.", "danger")
            return redirect(url_for("main.psychiatrist_page"))

        session["selected_psychiatrist"] = chosen["id"]
        flash(f"You selected {chosen['name']}.", "success")
        return redirect(url_for("main.psychiatrist_page"))

    selected_id = session.get("selected_psychiatrist")
    selected_doc = next((p for p in PSYCHIATRISTS if p["id"] == selected_id), None)

    return render_template(
        "psychiatrist.html",
        title="Psychiatrist Consultation",
        psychiatrists=PSYCHIATRISTS,
        selected_doc=selected_doc,
        fixed_amount=FIXED_AMOUNT,
    )


# ----------------------------
# Create Payment / Booking
# ----------------------------
@main.route("/create-local-payment", methods=["POST"])
@login_required
def create_local_payment():
    data = request.get_json() or {}
    cleanup_unpaid_bookings()

    date_str = data.get("date")
    time_str = data.get("time")
    method = (data.get("method") or "").lower()

    psychiatrist_id = data.get("psychiatrist_id")
    psychiatrist_name = data.get("psychiatrist_name")

    # 1️⃣ basic validation
    if not psychiatrist_id or not psychiatrist_name:
        return jsonify({"success": False, "message": "Please choose a psychiatrist."}), 400

    if not date_str or not time_str or not method:
        return jsonify({"success": False, "message": "Please select date, time, and payment method."}), 400

    allowed = {"khalti", "cash", "esewa", "fonepay"}
    if method not in allowed:
        return jsonify({"success": False, "message": "Invalid payment method."}), 400

    # 2️⃣ parse date & time
    try:
        booking_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        booking_time = datetime.strptime(time_str, "%H:%M").time()
    except ValueError:
        return jsonify({"success": False, "message": "Invalid date/time format."}), 400

    # 3️⃣ block past booking
    from ChatbotWebsite.utils import now_nepal, NEPAL_TZ

    requested_dt = datetime(
        booking_date.year, booking_date.month, booking_date.day,
        booking_time.hour, booking_time.minute, booking_time.second,
        tzinfo=NEPAL_TZ
    )
    if requested_dt < now_nepal():
        return jsonify(
            {
                "success": False,
                "message": "You cannot book an appointment in the past. Please choose a future date/time.",
            }
        ), 400

    # 4️⃣ block outside availability
    if not is_within_availability(psychiatrist_id, booking_date, booking_time):
        return jsonify(
            {"success": False, "message": "Selected time is outside the psychiatrist's available hours."}
        ), 400

    # 5️⃣ BLOCK same user overlapping booking (ANY doctor)
    existing_user = (
        PsychiatristBooking.query.filter_by(
            user_id=current_user.id, date=booking_date, time=booking_time
        ).first()
    )
    if existing_user:
        return jsonify(
            {"success": False, "message": "You already have an appointment at this date and time."}
        ), 409

    # 6️⃣ BLOCK same doctor double booking (ANY user)
    existing_doctor = (
        PsychiatristBooking.query.filter_by(
            psychiatrist_id=psychiatrist_id, date=booking_date, time=booking_time
        ).first()
    )
    if existing_doctor:
        return jsonify(
            {"success": False, "message": "This time slot has already been booked. Please choose another time."}
        ), 409

    # 7️⃣ Create booking (unpaid initially)
    booking = PsychiatristBooking(
        user_id=current_user.id,
        psychiatrist_id=psychiatrist_id,
        psychiatrist_name=psychiatrist_name,
        date=booking_date,
        time=booking_time,
        payment_method=method,
        amount=FIXED_AMOUNT,
        paid=False,
    )
    db.session.add(booking)
    db.session.commit()

    # ----------------------------
    # CASH ON VISIT (No gateway)
    # ----------------------------
    if method == "cash":
        payment_url = url_for("main.payment_checkout", booking_id=booking.id, _external=True)
        return jsonify(
            {"success": True, "payment_url": payment_url, "message": "Booking created. Pay cash on visit."}
        )

    # ----------------------------
    # KHALTI SANDBOX
    # ----------------------------
    if method == "khalti":
        base_url = get_app_base_url()
        headers = khalti_headers()

        # If no key or still local URL -> fallback to internal demo checkout
        if not headers or not is_public_base_url(base_url):
            payment_url = url_for("main.payment_checkout", booking_id=booking.id, _external=True)
            return jsonify(
                {
                    "success": True,
                    "payment_url": payment_url,
                    "message": "Khalti sandbox not configured (missing key or public URL). Using internal demo checkout.",
                }
            )

        # IMPORTANT: Use _external=True and FORCE trailing slash
        return_url = url_for("main.khalti_return", booking_id=booking.id, _external=True).rstrip("/") + "/"
        website_url = base_url

        payload = {
            "return_url": return_url,
            "website_url": website_url,
            "amount": FIXED_AMOUNT * 100,
            "purchase_order_id": str(booking.id),
            "purchase_order_name": f"Lumora Psychiatrist Booking #{booking.id}",
            "customer_info": {
                "name": current_user.username or "Lumora User",
                "email": current_user.email or "test@lumora.com",
                "phone": "9800000001",
            },
        }

        try:
            r = requests.post(
                f"{KHALTI_BASE}/epayment/initiate/",
                json=payload,
                headers=headers,
                timeout=20,
            )
            resp = r.json()
        except Exception as e:
            # ✅ delete booking so it doesn't take space
            db.session.delete(booking)
            db.session.commit()
            return jsonify({"success": False, "message": f"Khalti initiate failed: {e}"}), 500

        if r.status_code != 200:
            # ✅ delete booking if Khalti rejects
            db.session.delete(booking)
            db.session.commit()
            return jsonify({"success": False, "message": f"Khalti error: {resp}"}), 400

        booking.khalti_pidx = resp.get("pidx")
        db.session.commit()

        return jsonify({"success": True, "payment_url": resp.get("payment_url")})

    # ----------------------------
    # TODO: Esewa/Fonepay later
    # ----------------------------
    payment_url = url_for("main.payment_checkout", booking_id=booking.id, _external=True)
    return jsonify(
        {"success": True, "payment_url": payment_url, "message": "Gateway not integrated yet. Using internal demo checkout."}
    )


# ----------------------------
# Khalti Return + Lookup (no login required, accepts slash/no-slash)
# - Deletes unpaid bookings if canceled / not completed (removes "took space")
# ----------------------------
@main.route("/khalti/return/<int:booking_id>/")
@main.route("/khalti/return/<int:booking_id>")
def khalti_return(booking_id):
    booking = PsychiatristBooking.query.get_or_404(booking_id)

    pidx = request.args.get("pidx", "")
    status_raw = request.args.get("status", "") or ""
    status = status_raw.lower()

    # User canceled in Khalti UI
    if "canceled" in status or "cancelled" in status:
        if not booking.paid:
            db.session.delete(booking)
            db.session.commit()
        flash("Payment canceled. Booking removed.", "warning")
        return redirect(url_for("main.psychiatrist_page"))

    if not pidx:
        flash("Missing pidx from Khalti.", "danger")
        return redirect(url_for("main.payment_checkout", booking_id=booking.id))

    headers = khalti_headers()
    if not headers:
        flash("Khalti secret key not configured.", "danger")
        return redirect(url_for("main.payment_checkout", booking_id=booking.id))

    try:
        r = requests.post(
            f"{KHALTI_BASE}/epayment/lookup/",
            json={"pidx": pidx},
            headers=headers,
            timeout=20,
        )
        resp = r.json()
    except Exception as e:
        flash(f"Khalti lookup failed: {e}", "danger")
        return redirect(url_for("main.payment_checkout", booking_id=booking.id))

    if r.status_code != 200:
        flash(f"Khalti lookup error: {resp}", "danger")
        return redirect(url_for("main.payment_checkout", booking_id=booking.id))

    if resp.get("status") == "Completed":
        booking.paid = True
        booking.khalti_pidx = resp.get("pidx") or booking.khalti_pidx
        booking.khalti_transaction_id = resp.get("transaction_id") or booking.khalti_transaction_id
        db.session.commit()
        flash("✅ Payment successful! Booking confirmed.", "success")
        return redirect(url_for("main.payment_checkout", booking_id=booking.id))

    # Not completed -> remove unpaid booking so it doesn't take space
    if not booking.paid:
        db.session.delete(booking)
        db.session.commit()

    flash(f"Payment not completed (status: {resp.get('status')}). Booking removed.", "info")
    return redirect(url_for("main.psychiatrist_page"))


# ----------------------------
# Manual remove unpaid consultation (button/action)
# ----------------------------
@main.route("/booking/<int:booking_id>/cancel", methods=["POST"])
@login_required
def cancel_booking(booking_id):
    booking = PsychiatristBooking.query.get_or_404(booking_id)

    if booking.user_id != current_user.id:
        return jsonify({"success": False, "message": "Unauthorized"}), 403

    if booking.paid:
        return jsonify({"success": False, "message": "Paid booking cannot be removed here."}), 400

    db.session.delete(booking)
    db.session.commit()
    return jsonify({"success": True, "message": "Unpaid booking removed."})


# ----------------------------
# Internal Payment Page (Demo / Cash / Fallback)
# ----------------------------
@main.route("/payment/<int:booking_id>")
@login_required
def payment_checkout(booking_id):
    booking = PsychiatristBooking.query.get_or_404(booking_id)

    if booking.user_id != current_user.id:
        flash("Unauthorized access.", "danger")
        return redirect(url_for("main.psychiatrist_page"))

    return render_template("payment_checkout.html", title="Payment", booking=booking)


@main.route("/payment/<int:booking_id>/mark-paid")
@login_required
def mock_mark_paid(booking_id):
    booking = PsychiatristBooking.query.get_or_404(booking_id)

    if booking.user_id != current_user.id:
        flash("Unauthorized access.", "danger")
        return redirect(url_for("main.psychiatrist_page"))

    booking.paid = True
    db.session.commit()

    flash("Marked as paid (test mode).", "success")
    return redirect(url_for("main.payment_checkout", booking_id=booking.id))


# ----------------------------
# Fix legacy chat history sessions
# ----------------------------
@main.route("/_fix_chat_history_sessions")
@login_required
def _fix_chat_history_sessions():
    rows = ChatHistory.query.filter(ChatHistory.session_id.is_(None)).all()
    if not rows:
        return "No missing session_id rows ✅"

    legacy = ChatSession.query.filter_by(user_id=current_user.id, title="Legacy Chat").first()
    if not legacy:
        legacy = ChatSession(user_id=current_user.id, title="Legacy Chat", created_at=datetime.utcnow())
        db.session.add(legacy)
        db.session.commit()

    updated = 0
    for r in rows:
        if r.user_id == current_user.id:
            r.session_id = legacy.id
            updated += 1

    db.session.commit()
    return f"Updated {updated} rows ✅"


# ----------------------------
# Notifications Page
# ----------------------------
from zoneinfo import ZoneInfo
from sqlalchemy import or_
from datetime import datetime

NEPAL_TZ = ZoneInfo("Asia/Kathmandu")
from sqlalchemy import or_, and_
from ChatbotWebsite.utils import now_nepal

@main.route("/notifications")
@login_required
def notifications_page():
    now = now_nepal()

    notes = (
        Notification.query
        .filter(Notification.user_id == current_user.id)
        .filter(
            or_(
                # non-appointment notifications (notif_type is NULL)
                Notification.notif_type.is_(None),

                # appointment reminders must be upcoming
                and_(
                    Notification.notif_type.in_(["appt_24h", "appt_1h"]),
                    Notification.appointment_dt.isnot(None),
                    Notification.appointment_dt >= now
                )
            )
        )
        .order_by(Notification.created_at.desc())
        .limit(20)
        .all()
    )
    return render_template("notifications.html", notes=notes, title="Notifications")