from flask import Blueprint, render_template, redirect, url_for, flash, abort, request
from flask_login import current_user, login_required
from ChatbotWebsite.models import Journal
from ChatbotWebsite.journal.forms import JournalForm
from ChatbotWebsite import db
from ChatbotWebsite.chatbot.chatbot_logic import save_user_mood

journals = Blueprint("journals", __name__)

# ----------------------------
# All Journals Page (Paginated)
# ----------------------------
@journals.route("/all_journals")
@login_required
def all_journals():
    page = request.args.get("page", 1, type=int)
    journals_paginated = (
        Journal.query.filter_by(user_id=current_user.id)
        .order_by(Journal.timestamp.desc())
        .paginate(page=page, per_page=5)
    )
    return render_template("all_journals.html", title="Journals", journals=journals_paginated)


# ----------------------------
# New Journal Page
# ----------------------------
@journals.route("/journal/new", methods=["GET", "POST"])
@login_required
def new_journal():
    form = JournalForm()
    if form.validate_on_submit():
        # Create new journal entry
        journal = Journal(
            title=form.title.data,
            mood=form.mood.data,
            content=form.content.data,
            user_id=current_user.id  # use user_id instead of user
        )
        db.session.add(journal)
        db.session.commit()
        flash("Journal has been created!", "success")
        return redirect(url_for("journals.all_journals"))
    elif request.method == "POST":
        # Print form errors if submission fails
        print("Form errors:", form.errors)
    return render_template(
        "create_journal.html",
        title="New Journal",
        legend="New Journal",
        form=form
    )


# ----------------------------
# Single Journal Page
# ----------------------------
@journals.route("/journal/<int:journal_id>")
@login_required
def journal(journal_id):
    journal = Journal.query.get_or_404(journal_id)
    if journal.user_id != current_user.id:
        abort(403)
    return render_template("journal.html", title=f"Journal #{journal.id}", journal=journal)


# ----------------------------
# Update Journal Page
# ----------------------------
@journals.route("/journal/<int:journal_id>/update", methods=["GET", "POST"])
@login_required
def update_journal(journal_id):
    journal = Journal.query.get_or_404(journal_id)
    if journal.user_id != current_user.id:
        abort(403)
    
    form = JournalForm()
    if form.validate_on_submit():
        journal.title = form.title.data
        journal.mood = form.mood.data
        journal.content = form.content.data
        db.session.commit()
        flash("Journal has been updated!", "success")
        return redirect(url_for("journals.journal", journal_id=journal.id))
    elif request.method == "GET":
        form.title.data = journal.title
        form.mood.data = journal.mood
        form.content.data = journal.content
    
    return render_template(
        "create_journal.html",
        title="Update Journal",
        legend="Update Journal",
        journal=journal,
        form=form,
    )


# ----------------------------
# Delete Journal Route
# ----------------------------
# ----------------------------
# Delete Journal Route
# ----------------------------
from flask import abort, flash, redirect, url_for, request
from flask_login import login_required, current_user
from ChatbotWebsite import db
from ChatbotWebsite.models import Journal

@journals.route("/journal/<int:journal_id>/delete", methods=["POST"])
@login_required
def delete_journal(journal_id):
    journal = Journal.query.get_or_404(journal_id)

    # ✅ security: only owner can delete
    if journal.user_id != current_user.id:
        abort(403)

    try:
        db.session.delete(journal)
        db.session.commit()
        flash("Journal has been deleted!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Delete failed: {e}", "danger")

    return redirect(url_for("journals.all_journals"))
# ------------------------------
# Mood Check-in (FORM)
# ------------------------------
@journals.route("/mood/checkin", methods=["GET", "POST"])
@login_required
def mood_checkin():
    if request.method == "POST":
        mood_value = int(request.form.get("mood"))
        save_user_mood(current_user.id, mood_value)

        flash("Mood recorded successfully 💙", "success")
        return redirect(url_for("chatbot.mood_dashboard"))

    return render_template("mood_checkin.html")