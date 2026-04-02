from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from ChatbotWebsite import db
from ChatbotWebsite.models import PsychiatristBooking, Notification

NEPAL_TZ = ZoneInfo("Asia/Kathmandu")

def _booking_dt_local(b: PsychiatristBooking) -> datetime:
    return datetime(
        b.date.year, b.date.month, b.date.day,
        b.time.hour, b.time.minute, b.time.second,
        tzinfo=NEPAL_TZ
    )

def run_booking_reminders():
    now = datetime.now(NEPAL_TZ)

    # ✅ Cleanup expired appointment reminders
    try:
        Notification.query.filter(
            Notification.notif_type.in_(["appt_24h", "appt_1h"]),
            Notification.appointment_dt.isnot(None),
            Notification.appointment_dt < now,
        ).delete(synchronize_session=False)
        db.session.commit()
    except Exception:
        db.session.rollback()

    # ✅ Only PAID bookings
    bookings = (
        PsychiatristBooking.query
        .filter(PsychiatristBooking.date.isnot(None))
        .filter(PsychiatristBooking.paid == True)
        .all()
    )

    changed = False

    for b in bookings:
        appt_dt = _booking_dt_local(b)
        if appt_dt <= now:
            continue

        delta = appt_dt - now

        # --- 24h reminder (DB dedupe is enough) ---
        exists_24h = Notification.query.filter_by(
            user_id=b.user_id,
            booking_id=b.id,
            notif_type="appt_24h"
        ).first()

        if (delta <= timedelta(hours=24)) and (not exists_24h):
            db.session.add(Notification(
                user_id=b.user_id,
                title="📅 Appointment Reminder (24h)",
                body=f"Your appointment with {b.psychiatrist_name} is within 24 hours: {appt_dt.strftime('%Y-%m-%d %I:%M %p')}.",
                link="/",
                notif_type="appt_24h",
                appointment_dt=appt_dt,
                booking_id=b.id,
            ))
            b.reminded_24h = True
            changed = True

        # --- 1h reminder (DB dedupe is enough) ---
        exists_1h = Notification.query.filter_by(
            user_id=b.user_id,
            booking_id=b.id,
            notif_type="appt_1h"
        ).first()

        if (delta <= timedelta(hours=1)) and (not exists_1h):
            db.session.add(Notification(
                user_id=b.user_id,
                title="⏰ Appointment Reminder (1h)",
                body=f"Your appointment with {b.psychiatrist_name} is within 1 hour: {appt_dt.strftime('%Y-%m-%d %I:%M %p')}.",
                link="/",
                notif_type="appt_1h",
                appointment_dt=appt_dt,
                booking_id=b.id,
            ))
            b.reminded_1h = True
            changed = True

    if changed:
        db.session.commit()