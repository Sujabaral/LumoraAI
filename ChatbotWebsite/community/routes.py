from __future__ import annotations

import json
from flask import render_template, request, redirect, url_for, flash, jsonify
from flask_login import current_user

from ChatbotWebsite import db
from ChatbotWebsite.models import (
    CommunityPost,
    CommunityComment,
    CommunityReaction,
    CommunityReport,
)

from .anon import generate_alias
from .safety import analyze_text
from . import community


# -----------------------------
# Moderation thresholds (MVP)
# -----------------------------
REPORTS_UNDER_REVIEW = 3
REPORTS_AUTO_HIDE = 5

ALLOWED_REACTIONS = {"support", "relate", "heart"}
ALLOWED_TAGS = {"anxiety", "sadness", "stress", "relationship", "exams", "sleep"}


def _is_logged_in() -> bool:
    return bool(getattr(current_user, "is_authenticated", False))


def _user_id_or_none():
    return current_user.id if _is_logged_in() else None


def _parse_tags(tags_raw: str) -> list[str]:
    """Accept comma-separated tags; keep only allowed tags."""
    if not tags_raw:
        return []
    parts = [t.strip().lower() for t in tags_raw.split(",") if t.strip()]
    tags = [t for t in parts if t in ALLOWED_TAGS]

    # de-dup preserve order
    out: list[str] = []
    for t in tags:
        if t not in out:
            out.append(t)
    return out


def _apply_report_thresholds_post(post: CommunityPost):
    if post.reports_count >= REPORTS_AUTO_HIDE:
        post.status = "hidden"
    elif post.reports_count >= REPORTS_UNDER_REVIEW and post.status == "visible":
        post.status = "under_review"


def _apply_report_thresholds_comment(c: CommunityComment):
    if c.reports_count >= REPORTS_AUTO_HIDE:
        c.status = "hidden"
    elif c.reports_count >= REPORTS_UNDER_REVIEW and c.status == "visible":
        c.status = "under_review"


@community.route("/community", methods=["GET"])
def feed():
    """
    Public feed shows ONLY visible posts.
    (Under_review is for moderators/admin, not public.)
    """
    sort = (request.args.get("sort") or "recent").lower()

    q = CommunityPost.query.filter(CommunityPost.status == "visible")
    posts = q.order_by(CommunityPost.created_at.desc()).all()

    if sort == "supportive":
        # support score = reactions + comments
        posts.sort(
            key=lambda p: (len(p.reactions) + len(p.comments), p.created_at),
            reverse=True,
        )

    return render_template(
        "community/feed.html",
        posts=posts,
        sort=sort,
        allowed_tags=sorted(ALLOWED_TAGS),
    )

@community.route("/community/post", methods=["POST"])
def create_post():
    title = (request.form.get("title") or "").strip()
    body = (request.form.get("body") or "").strip()
    tags_raw = (request.form.get("tags") or "").strip()

    # basic validation
    if not title or not body:
        flash("Title and body are required.", "warning")
        return redirect(url_for("community.feed"))

    title = title[:140]
    if len(body) > 3000:
        flash("Body is too long (max 3000 chars).", "warning")
        return redirect(url_for("community.feed"))

    # safety checks (title + body)
    safety = analyze_text(title + "\n" + body, sos_url=url_for("main.sos"))

    # ✅ CRISIS: hard block + redirect to SOS (do not save post)
    if not safety.ok and getattr(safety, "crisis", False):
        flash("SOS: Please use support resources right now.", "warning")
        return redirect(getattr(safety, "redirect_url", None) or url_for("main.sos"))

    # ✅ BLOCKED (PII etc.)
    if not safety.ok:
        flash(safety.block_reason or "Blocked for safety.", "danger")
        return redirect(url_for("community.feed"))

    # non-crisis moderation
    status = "under_review" if getattr(safety, "flag_under_review", False) else "visible"

    # ✅ allow posting even when not logged in (guest allowed)
    user_id = _user_id_or_none()  # None for guests
    alias = generate_alias(user_id=user_id)
    tags = _parse_tags(tags_raw)

    post = CommunityPost(
        user_id=user_id,
        anon_alias=alias,
        title=title,
        body=body,
        tags_json=json.dumps(tags),
        status=status,
    )
    db.session.add(post)
    db.session.commit()

    # ✅ If under_review, do NOT show publicly—send back to feed
    if status != "visible":
        flash("Posted ✅ (Under review)", "warning")
        return redirect(url_for("community.feed"))

    flash("Posted anonymously ✅", "success")
    return redirect(url_for("community.view_post", id=post.id))

@community.route("/community/post/<int:id>", methods=["GET"])
def view_post(id: int):
    post = CommunityPost.query.get_or_404(id)

    # public users can only view visible posts
    if post.status != "visible":
        flash("This post is not available.", "warning")
        return redirect(url_for("community.feed"))

    comments = (
        CommunityComment.query
        .filter_by(post_id=post.id)
        .filter(CommunityComment.status == "visible")
        .order_by(CommunityComment.created_at.asc())
        .all()
    )

    # reaction counts
    reactions = CommunityReaction.query.filter_by(post_id=post.id).all()
    counts = {"support": 0, "relate": 0, "heart": 0}
    for r in reactions:
        if r.type in counts:
            counts[r.type] += 1

    try:
        tags = json.loads(post.tags_json or "[]")
        if not isinstance(tags, list):
            tags = []
    except Exception:
        tags = []

    return render_template(
        "community/post_detail.html",
        post=post,
        comments=comments,
        counts=counts,
        tags=tags,
    )


@community.route("/community/post/<int:id>/comment", methods=["POST"])
def add_comment(id: int):
    post = CommunityPost.query.get_or_404(id)

    # only allow commenting on visible posts (public)
    if post.status != "visible":
        flash("This post is not available.", "warning")
        return redirect(url_for("community.feed"))

    body = (request.form.get("body") or "").strip()
    if not body:
        flash("Comment cannot be empty.", "warning")
        return redirect(url_for("community.view_post", id=id))

    if len(body) > 2000:
        flash("Comment too long (max 2000 chars).", "warning")
        return redirect(url_for("community.view_post", id=id))

    safety = analyze_text(body)

    # ✅ IMMEDIATE TAKE-DOWN + SOS (do not save)
    if getattr(safety, "crisis", False):
        flash("SOS: Please use support resources right now.", "warning")
        return redirect(url_for("main.sos"))

    if not safety.ok:
        flash(safety.block_reason or "Blocked for safety.", "danger")
        return redirect(url_for("community.view_post", id=id))

    status = "under_review" if getattr(safety, "flag_under_review", False) else "visible"

    user_id = _user_id_or_none()
    alias = generate_alias(user_id=user_id)

    c = CommunityComment(
        post_id=post.id,
        user_id=user_id,
        anon_alias=alias,
        body=body,
        status=status,
    )
    db.session.add(c)
    db.session.commit()

    if status != "visible":
        flash("Comment posted ✅ (Under review)", "warning")
        return redirect(url_for("community.view_post", id=id))

    flash("Comment posted anonymously ✅", "success")
    return redirect(url_for("community.view_post", id=id))


@community.route("/community/post/<int:id>/react", methods=["POST"])
def react(id: int):
    # reactions require login (recommended)
    if not _is_logged_in():
        return jsonify({"ok": False, "message": "Login required to react."}), 401

    post = CommunityPost.query.get_or_404(id)
    if post.status != "visible":
        return jsonify({"ok": False, "message": "Post not available."}), 404

    rtype = (request.form.get("type") or "").strip().lower()
    if rtype not in ALLOWED_REACTIONS:
        return jsonify({"ok": False, "message": "Invalid reaction type."}), 400

    existing = CommunityReaction.query.filter_by(
        post_id=post.id,
        user_id=current_user.id,
        type=rtype,
    ).first()

    # toggle behavior
    if existing:
        db.session.delete(existing)
        db.session.commit()
        return jsonify({"ok": True, "toggled": "off"})

    r = CommunityReaction(post_id=post.id, user_id=current_user.id, type=rtype)
    db.session.add(r)
    db.session.commit()
    return jsonify({"ok": True, "toggled": "on"})


@community.route("/community/report", methods=["POST"])
def report():
    reason = (request.form.get("reason") or "").strip()
    post_id = (request.form.get("post_id") or "").strip()
    comment_id = (request.form.get("comment_id") or "").strip()

    if not reason:
        return jsonify({"ok": False, "message": "Reason required."}), 400

    pid = int(post_id) if post_id.isdigit() else None
    cid = int(comment_id) if comment_id.isdigit() else None

    if not pid and not cid:
        return jsonify({"ok": False, "message": "Must report a post or a comment."}), 400

    reporter_id = _user_id_or_none()  # guests can report too

    rep = CommunityReport(
        reporter_user_id=reporter_id,
        post_id=pid,
        comment_id=cid,
        reason=reason[:200],
        status="open",
    )
    db.session.add(rep)

    # increment counters + apply auto moderation
    if pid:
        post = CommunityPost.query.get(pid)
        if post:
            post.reports_count += 1
            _apply_report_thresholds_post(post)

    if cid:
        c = CommunityComment.query.get(cid)
        if c:
            c.reports_count += 1
            _apply_report_thresholds_comment(c)

    db.session.commit()
    return jsonify({"ok": True, "message": "Report submitted. Thank you."})