from flask import Blueprint, render_template, request, redirect, url_for, flash
from ChatbotWebsite import db
from ChatbotWebsite.models import MoodEntry
from .logic import detect_low_mood_trend, mood_summary
from flask_login import current_user, login_required

mood_bp = Blueprint('mood', __name__, template_folder='templates')

@mood_bp.route('/mood', methods=['GET', 'POST'])
@login_required
def mood_checkin():
    if request.method == 'POST':
        mood_value = int(request.form.get('mood'))
        entry = MoodEntry(user_id=current_user.id, mood_value=mood_value)
        db.session.add(entry)
        db.session.commit()
        flash('Mood saved!', 'success')

        # check trend
        if detect_low_mood_trend(current_user.id):
            flash('I notice you’ve been feeling low recently. Here are some coping suggestions.', 'warning')

        return redirect(url_for('chatbot.chat'))  # redirect back to chatbot page
    return render_template('mood_checkin.html')
