# ChatbotWebsite/chatbot/routes.py

import os
import json
import csv
import math
import re
from io import BytesIO, StringIO
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from ChatbotWebsite.chatbot.test import get_test_messages, needs_immediate_danger_check
import matplotlib
matplotlib.use("Agg")  # required for Flask / macOS
import matplotlib.pyplot as plt

from flask import (
    Blueprint,
    Response,
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from flask_login import current_user, login_required

from sqlalchemy import func, case
from sqlalchemy.sql import and_

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from reportlab.lib import colors

from ChatbotWebsite import db

# -------------------------
# DB models
# -------------------------
from ChatbotWebsite.models import (
    AssessmentResult,
    ChatHistory,
    ChatMessage,
    ChatSession,
    DistortionEvent,
    EvalDataset,
    EvalDatasetItem,
    Journal,
    MessageLabel,
    MoodEntry,
    UserEmotionEvent,
    UserFeedback,
    SavedInsight,
)



# -------------------------
# Simple greeting helpers (for Saved Insights button)
# -------------------------
_GREETINGS = {
    "hi","hello","hey","hii","hiii","namaste","yo","sup","hy",
    "good morning","good afternoon","good evening"
}

def _norm_text(t: str) -> str:
    t = (t or "").strip().lower()
    t = re.sub(r"\s+", " ", t)
    return t

def _is_greeting_text(user_text: str) -> bool:
    t = _norm_text(user_text)
    if not t:
        return False
    if t in _GREETINGS:
        return True
    for g in _GREETINGS:
        if t.startswith(g + " "):
            return True
    return False

def _is_greeting_reply(bot_text: str) -> bool:
    t = _norm_text(bot_text)
    if not t:
        return False
    patterns = [
        r"^(hi|hello|hey|namaste)[!. ]*$",
        r"^(hi|hello|hey|namaste).{0,35}$",
        r"^how can i help( you)?\??$",
        r"^how are you( doing)?\??$",
    ]
    return any(re.match(p, t) for p in patterns)

def _mentions_depressed(user_text_en: str) -> bool:
    t = _norm_text(user_text_en)
    if not t:
        return False
    patterns = [
        r"\bi am depressed\b",
        r"\bi'?m depressed\b",
        r"\bim depressed\b",
        r"\bfeeling depressed\b",
        r"\bfeel depressed\b",
        r"\bso depressed\b",
    ]
    return any(re.search(p, t) for p in patterns)

# -------------------------
# Chatbot modules
# -------------------------
from ChatbotWebsite.chatbot.chatbot_logic import (
    get_hybrid_response,
    save_user_mood_no_commit,
)

from ChatbotWebsite.chatbot.sentiment import analyze_sentiment
from ChatbotWebsite.chatbot.safety import detect_self_harm

from ChatbotWebsite.chatbot.translate import translate_text

from ChatbotWebsite.chatbot.topic import topics, get_content
from ChatbotWebsite.chatbot.test import tests, get_questions, get_test_messages
from ChatbotWebsite.chatbot.mindfulness import mindfulness_exercises, get_description

from ChatbotWebsite.chatbot.trend import update_chat_trend
from flask import current_app
# Brain helpers used by chat_messages (must exist in your tree)
from ChatbotWebsite.chatbot.brain.language_detector import detect_language
from ChatbotWebsite.chatbot.brain.feedback_intent import detect_feedback_intent
from ChatbotWebsite.chatbot.brain.tone_router import route_tone
from ChatbotWebsite.chatbot.brain.fun_reply import fun_reply
from ChatbotWebsite.chatbot.brain.response_rewriter import rewrite_if_needed
from ChatbotWebsite.chatbot.rewriter import rewrite_reply_en  # your file is rewriter.py

# Optional profile updater (safe fallback if missing)
try:
    from ChatbotWebsite.chatbot.brain.memory import update_profile_no_commit
except Exception:
    update_profile_no_commit = None  # type: ignore

# Optional reply humanizer (safe fallback if missing)
try:
    from ChatbotWebsite.chatbot.brain.therapeutic_presence import humanize_reply
except Exception:
    humanize_reply = None  # type: ignore

# ✅ streak helper now lives in users/utils.py
from ChatbotWebsite.users.utils import calculate_positive_streak

# Evaluation chart helper(s)
from ChatbotWebsite.chatbot.evaluation.charts import fig_to_png, fig_to_png_response

chatbot = Blueprint("chatbot", __name__)



# -------------------------
# Mindfulness / meditation intent (for audio-only replies)
# -------------------------
_MINDFULNESS_PATTERNS = [
    r"\bmeditat(e|ion|ing)?\b",
    r"\bmindful(ness)?\b",
    r"\bbreath(ing)?\b",
    r"\bground(ing)?\b",
    r"\brelax\b",
    r"\bcalm\s*down\b",
]

def _is_mindfulness_request(user_text: str) -> bool:
    t = (user_text or "").strip()
    if not t:
        return False
    for p in _MINDFULNESS_PATTERNS:
        if re.search(p, t, flags=re.IGNORECASE):
            return True
    return False

def _pick_default_mindfulness_title() -> Optional[str]:
    """Pick a reasonable default mindfulness audio title."""
    try:
        items = (mindfulness_exercises or {}).get("mindfulness_exercises", [])
        if not items:
            return None

        # Prefer a "Mountain" meditation if present (matches your UI label)
        for ex in items:
            title = (ex.get("title") or "").strip()
            if "mountain" in title.lower():
                return title

        # Otherwise take the first exercise
        return (items[0].get("title") or "").strip() or None
    except Exception:
        return None
# -----------------------------
# Safe debug logger (never crashes)
# -----------------------------
def brain_debug_log(*args, **kwargs):
    """
    Debug helper. If you later implement a real logger, keep same signature.
    """
    try:
        current_app.logger.info("[BRAIN_DEBUG] %s %s", args, kwargs)
    except Exception:
        # If current_app isn't available or logger fails, ignore.
        pass
# -------------------------
# Shared mappings (Mood + Journal)
# -------------------------
MOOD_EMOJI_MAP = {
    1: {"label": "Terrible", "emoji": "😭"},
    2: {"label": "Low", "emoji": "😔"},
    3: {"label": "Neutral", "emoji": "😐"},
    4: {"label": "Good", "emoji": "🙂"},
    5: {"label": "Excellent", "emoji": "😄"},
}

JOURNAL_VALUE_MAP = {
    "Angry": 1,
    "Sad": 2,
    "Neutral": 3,
    "Happy": 4,
    "Excited": 5,
}

JOURNAL_EMOJI_MAP = {
    "Angry": "😡",
    "Sad": "😢",
    "Neutral": "😐",
    "Happy": "😊",
    "Excited": "🤩",
}
from flask import current_app
def looks_nepali(text: str) -> bool:
    # Devanagari unicode block (Nepali/Hindi/etc.)
    return any("\u0900" <= ch <= "\u097F" for ch in (text or ""))
def looks_roman_nepali(s: str) -> bool:
    t = (s or "").lower()
    roman_markers = [
        "malai", "mero", "man", "dherai", "ekdam", "dar", "aatin", "attin",
        "lagyo", "lagiracha", "lagiraxa", "xa", "cha", "vayo", "vako",
        "k garum", "kina", "huncha", "hudaina"
    ]
    return any(m in t for m in roman_markers)

@chatbot.route("/__routes", methods=["GET"])
def __routes():
    lines = []
    for r in current_app.url_map.iter_rules():
        if "label" in r.rule or "evaluation" in r.rule:
            lines.append(f"{r.rule}  methods={sorted(r.methods)}  endpoint={r.endpoint}")
    return "<br>".join(sorted(lines)), 200

# -------------------------
# Helpers
# -------------------------
def make_title(text: str) -> str:
    text = (text or "").strip()
    if not text:
        return "New Chat"
    words = text.split()
    title = " ".join(words[:6])
    return title[:120]


def _ensure_logged_in_session(session_id: int | None, user_id: int):
    """
    Ensures a valid ChatSession for logged-in user.
    - If session_id provided and owned -> use it
    - else use most recent
    - else create new
    Returns ChatSession instance.
    """
    chat_session = None
    if session_id:
        chat_session = ChatSession.query.filter_by(id=session_id, user_id=user_id).first()

    if not chat_session:
        chat_session = (
            ChatSession.query
            .filter_by(user_id=user_id, is_archived=False)
            .order_by(ChatSession.updated_at.desc())
            .first()
        )

    if not chat_session:
        chat_session = ChatSession(user_id=user_id, title="New Chat")
        db.session.add(chat_session)
        db.session.commit()

    return chat_session


def _journal_to_value(mood_name: str | None) -> int:
    name = (mood_name or "Neutral").strip()
    return JOURNAL_VALUE_MAP.get(name, 3)


def _normalize_sources_for_graph(user_id: int):
    """
    Returns combined entries as a list of dicts:
      {timestamp: datetime, value: float/int, source: 'mood'|'journal', label: str}
    """
    moods = (
        MoodEntry.query
        .filter_by(user_id=user_id)
        .order_by(MoodEntry.timestamp.asc())
        .all()
    )

    journals = (
        Journal.query
        .filter_by(user_id=user_id)
        .filter(Journal.mood.isnot(None))
        .order_by(Journal.timestamp.asc())
        .all()
    )

    combined = []

    for m in moods:
        if m.mood_value is None:
            continue
        combined.append({
            "timestamp": m.timestamp,
            "value": float(m.mood_value),
            "source": "mood",
            "label": (m.source or "Mood").strip() or "Mood",
        })

    for j in journals:
        combined.append({
            "timestamp": j.timestamp,
            "value": float(_journal_to_value(j.mood)),
            "source": "journal",
            "label": (j.mood or "Journal").strip() or "Journal",
        })

    combined.sort(key=lambda x: x["timestamp"])
    return combined


# ---------------------------------
# ---------------------------------

@chatbot.route("/set_lang", methods=["POST"])
def set_lang():
    data = request.json or {}
    lang = (data.get("lang") or "en").lower().strip()

    if lang not in ("en", "ne"):
        lang = "en"

    if current_user.is_authenticated:
        current_user.preferred_lang = lang
        db.session.commit()
    else:
        session["lang"] = lang   # guest support

    return jsonify({"ok": True, "lang": lang})
# ---------------------------------
# Chat Explain (✅ ONLY ONE ROUTE — used by "Why?" modal)
# ---------------------------------
@chatbot.route("/chat/explain/<int:id>")
@login_required
def chat_explain(id):
    msg = ChatHistory.query.filter_by(
        id=id,
        user_id=current_user.id
    ).first_or_404()

    return jsonify({
        "label": msg.sentiment_label,
        "confidence": msg.confidence,
        "vader_score": msg.vader_score,
        "final_score": msg.final_score,
        "top_tokens": json.loads(msg.explain_tokens or "[]"),
        "ml_prob": json.loads(msg.ml_prob or "{}"),
        "contains_self_harm": bool(msg.contains_self_harm),
        "crisis_mode": bool(getattr(msg, "crisis_mode", False)),
    })


# ---------------------------------
# Chat Page
# ---------------------------------

@chatbot.route("/chat", methods=["GET"])
def chat():
    lang = (getattr(current_user, "preferred_lang", None) or "en").lower().strip()
    t = translate_text

    # ---------------- GUEST ----------------
    if not current_user.is_authenticated:
        return render_template(
            "chat/chat.html",
            title="Chat",
            topics=topics,
            tests=tests,
            mindfulness_exercises=mindfulness_exercises,
            sessions=[],
            active_session_id="",
            messages=[],
            already_feedback=False,
            is_guest=True,
            lang=lang,
            t=t,
            search_q='',
            search_results=[],
        )

    # ---------------- ALWAYS LOAD SIDEBAR SESSIONS FIRST ----------------
    sessions = (
        ChatSession.query
        .filter_by(user_id=current_user.id, is_archived=False)
        .order_by(ChatSession.updated_at.desc())
        .all()
    )

    session_id = request.args.get("session", type=int)
    force_new = (request.args.get("new") == "1")
    search_q = (request.args.get("q") or "").strip()

    # ---------------- SEARCH MODE ----------------
    if search_q and not session_id:
        search_results = []

        matched_sessions = (
            ChatSession.query
            .filter(ChatSession.user_id == current_user.id, ChatSession.is_archived == False)
            .filter(ChatSession.title.ilike(f"%{search_q}%"))
            .order_by(ChatSession.updated_at.desc())
            .limit(20)
            .all()
        )

        for s in matched_sessions:
            search_results.append({
                "session_id": s.id,
                "timestamp": s.updated_at,
                "snippet": f"[Session] {s.title}",
            })

        matched_msgs = (
            ChatHistory.query
            .filter(ChatHistory.user_id == current_user.id)
            .filter(ChatHistory.content.ilike(f"%{search_q}%"))
            .order_by(ChatHistory.timestamp.desc())
            .limit(30)
            .all()
        )

        for h in matched_msgs:
            snippet = (h.content or "").strip()
            if len(snippet) > 90:
                snippet = snippet[:90] + "…"
            search_results.append({
                "session_id": h.session_id,
                "timestamp": h.timestamp,
                "snippet": snippet,
            })

        return render_template(
            "chat/chat.html",
            title="Chat",
            topics=topics,
            tests=tests,
            mindfulness_exercises=mindfulness_exercises,
            sessions=sessions,
            active_session_id="",
            messages=[],
            already_feedback=False,
            is_guest=False,
            lang=lang,
            t=t,
            search_q=search_q,
            search_results=search_results,
        )

    # ---------------- NO SESSION SELECTED ----------------
    # ✅ Force-create a new session (used when the page is refreshed)
    if force_new:
        new_s = ChatSession(user_id=current_user.id, title="New Chat")
        db.session.add(new_s)
        db.session.commit()
        return redirect(url_for("chatbot.chat", session=new_s.id))
    if not session_id:
        latest = (
            ChatSession.query
            .filter_by(user_id=current_user.id, is_archived=False)
            .order_by(ChatSession.updated_at.desc())
            .first()
        )
        if latest:
            return redirect(url_for("chatbot.chat", session=latest.id))

        new_s = ChatSession(user_id=current_user.id, title="New Chat")
        db.session.add(new_s)
        db.session.commit()
        return redirect(url_for("chatbot.chat", session=new_s.id))

    # ---------------- OPEN SESSION ----------------
    active_session = ChatSession.query.filter_by(id=session_id, user_id=current_user.id).first()

    # ✅ If session id is stale / deleted, never hard-404 — open a fresh chat instead
    if not active_session:
        flash("That chat was not found (maybe deleted). Opening a new chat.", "warning")
        return redirect(url_for("chatbot.chat", new=1))

    messages = (
        ChatHistory.query
        .filter_by(user_id=current_user.id, session_id=active_session.id)
        .order_by(ChatHistory.timestamp.asc())
        .all()
    )

    already_feedback = (
        UserFeedback.query
        .filter_by(user_id=current_user.id, session_id=active_session.id)
        .first()
        is not None
    )

    return render_template(
        "chat/chat.html",
        title="Chat",
        topics=topics,
        tests=tests,
        mindfulness_exercises=mindfulness_exercises,
        sessions=sessions,
        active_session_id=active_session.id,
        messages=messages,
        already_feedback=already_feedback,
        search_q="",
        search_results=[],
        is_guest=False,
        lang=lang,
        t=t,
    )
# ---------------------------------
# Create a new chat session (button)
# ---------------------------------
# ---------------------------------
# Chat Messages (Hybrid + Mood Save + Sentiment + Risk + Translation)
# ---------------------------------
# ChatbotWebsite/chatbot/routes.py


import json
from datetime import datetime

from flask import jsonify, request, url_for, current_app
from flask_login import current_user

from ChatbotWebsite import db
from ChatbotWebsite.models import (
    ChatHistory,
    ChatMessage,
    MessageLabel,
    UserEmotionEvent,
    DistortionEvent,
)
from ChatbotWebsite.chatbot.brain.therapeutic_presence import humanize_reply
# your existing imports
from ChatbotWebsite.chatbot.translate import translate_text
from ChatbotWebsite.chatbot.safety import detect_self_harm
from ChatbotWebsite.chatbot.brain.risk import assess_risk
from ChatbotWebsite.chatbot.rewriter import rewrite_reply_en
from ChatbotWebsite.chatbot.sentiment import analyze_sentiment
from ChatbotWebsite.chatbot.brain.distortions import detect_distortions
from ChatbotWebsite.chatbot.brain.style import detect_style
from ChatbotWebsite.chatbot.brain.policy import choose_strategy
from ChatbotWebsite.chatbot.brain.templates import render_reply
from ChatbotWebsite.chatbot.brain.emotion import detect_emotion  # make sure this exists
from ChatbotWebsite.chatbot.brain.memory import (
    get_profile_summary,
    update_profile_no_commit,
    detect_trigger,
)# session helper (your existing)
# ---------------------------------
# Chat Messages (Hybrid + Mood + Risk + Rewrite + Translation)
# ---------------------------------


from datetime import datetime
from typing import Any, Dict, List

from flask import jsonify, request, url_for, current_app
from flask_login import current_user

from ChatbotWebsite import db
from ChatbotWebsite.models import ChatHistory, ChatMessage, MessageLabel, ChatSession

from ChatbotWebsite.chatbot.translate import translate_text
from ChatbotWebsite.chatbot.sentiment import analyze_sentiment
from ChatbotWebsite.chatbot.rewriter import rewrite_reply_en

from ChatbotWebsite.chatbot.brain.language_detector import detect_language
from ChatbotWebsite.chatbot.brain.feedback_intent import detect_feedback_intent
from ChatbotWebsite.chatbot.brain.response_rewriter import rewrite_if_needed

from ChatbotWebsite.chatbot.chatbot_logic import (
    save_user_mood_no_commit,
    get_hybrid_response,
)

# You already have these helpers in your file:
# - make_title(text) -> str
# - _ensure_logged_in_session(session_id, user_id) -> ChatSession
# - brain_debug_log(**payload)


# ---------------------------------
# Chat Messages (Hybrid + Mood + Risk + Rewrite + Translation)
# ---------------------------------


from datetime import datetime
from typing import Any, Dict, List

from flask import jsonify, request, url_for, current_app
from flask_login import current_user

from ChatbotWebsite import db
from ChatbotWebsite.models import ChatHistory, ChatMessage, MessageLabel, ChatSession

from ChatbotWebsite.chatbot.translate import translate_text
from ChatbotWebsite.chatbot.sentiment import analyze_sentiment
from ChatbotWebsite.chatbot.rewriter import rewrite_reply_en
from ChatbotWebsite.chatbot import safety
from ChatbotWebsite.chatbot.safety import detect_self_harm

from ChatbotWebsite.chatbot.brain.language_detector import detect_language
from ChatbotWebsite.chatbot.brain.feedback_intent import detect_feedback_intent
from ChatbotWebsite.chatbot.brain.response_rewriter import rewrite_if_needed
from ChatbotWebsite.chatbot.brain.memory import update_profile_no_commit

from ChatbotWebsite.chatbot.chatbot_logic import (
    save_user_mood_no_commit,
    get_hybrid_response,
)

# ChatbotWebsite/chatbot/routes.py

# ChatbotWebsite/chatbot/routes.py
# ChatbotWebsite/chatbot/routes.py  (only the updated parts you need)

# ✅ ADD these imports near your other imports at top
from ChatbotWebsite.chatbot.brain.tone_router import route_tone
from ChatbotWebsite.chatbot.brain.fun_reply import fun_reply


# ChatbotWebsite/chatbot/routes.py  (or wherever your @chatbot.route lives)

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from flask import Blueprint, request, jsonify, session, url_for, current_app
from flask_login import current_user

from ChatbotWebsite import db
from ChatbotWebsite.models import (
    ChatHistory,
    ChatMessage,
    ChatSession,
    MessageLabel,
)

# your existing helpers/utilities (keep your real import paths)
# ChatbotWebsite/chatbot/routes.py

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from flask import Blueprint, request, jsonify, session, url_for, current_app
from flask_login import current_user

from ChatbotWebsite import db
from ChatbotWebsite.models import (
    ChatHistory,
    ChatMessage,
    ChatSession,
    MessageLabel,
)

# ✅ These files exist in your project tree:
from ChatbotWebsite.chatbot.brain.language_detector import detect_language
from ChatbotWebsite.chatbot.translate import translate_text
from ChatbotWebsite.chatbot.sentiment import analyze_sentiment
from ChatbotWebsite.chatbot.safety import classify_risk
# Your hybrid engine + mood saver exist:
from ChatbotWebsite.chatbot.chatbot_logic import get_hybrid_response, save_user_mood_no_commit

# Your rewriter exists as rewriter.py (NOT rewrite.py)
# Adjust function names below if yours are slightly different.
from ChatbotWebsite.chatbot.rewriter import rewrite_reply_en
# Safety: you have safety.py and safety/ folder.
# Use the functions that are actually inside safety.py.
from ChatbotWebsite.chatbot.safety import detect_self_harm

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from flask import Blueprint, request, jsonify, session, url_for, current_app
from flask_login import current_user, login_required

from ChatbotWebsite import db
from ChatbotWebsite.models import ChatHistory, ChatMessage, ChatSession, MessageLabel

# ✅ Your hybrid responder + mood saver (you already have these)
from ChatbotWebsite.chatbot.chatbot_logic import get_hybrid_response, save_user_mood_no_commit

# ✅ Your brain modules (from screenshot)
from ChatbotWebsite.chatbot.brain.language_detector import detect_language
from ChatbotWebsite.chatbot.translate import translate_text  # you already have translate.py in tree

from ChatbotWebsite.chatbot.brain.feedback_intent import detect_feedback_intent
from ChatbotWebsite.chatbot.brain.tone_router import route_tone
from ChatbotWebsite.chatbot.brain.fun_reply import fun_reply

from ChatbotWebsite.chatbot.brain.response_rewriter import rewrite_if_needed
from ChatbotWebsite.chatbot.rewriter import rewrite_reply_en
from ChatbotWebsite.chatbot.brain.risk import assess_risk

# ✅ your existing sentiment + trend/risk scorer (you already use these)
from ChatbotWebsite.chatbot.sentiment import analyze_sentiment
from ChatbotWebsite.chatbot.trend import classify_risk

# ✅ raw self-harm detector (your project has chatbot/safety + chatbot/safety.py)
# Pick ONE that exists in your codebase:
from ChatbotWebsite.chatbot.safety import detect_self_harm   # if detect_self_harm is in safety.py
# If detect_self_harm is inside the folder package chatbot/safety/ instead, use:
# from ChatbotWebsite.chatbot.safety_raw import detect_self_harm

# ✅ optional brain humanizer/profile/debug/session helpers
# If you already have these files, import them; if not, remove these lines and use the fallbacks below.
try:
    from ChatbotWebsite.chatbot.brain.memory import update_profile_no_commit
except Exception:
    update_profile_no_commit = None

try:
    from ChatbotWebsite.chatbot.brain.therapeutic_presence import humanize_reply
except Exception:
    humanize_reply = None
# If you DO NOT have these helpers, keep the fallback implementations below:
# - detect_feedback_intent
# - route_tone / fun_reply
# - humanize_reply
# - update_profile_no_commit
# - _ensure_logged_in_session / make_title
# - brain_debug_log

@chatbot.route("/chat_messages", methods=["POST"])
def chatting():
    payload = request.get_json(silent=True) if request.is_json else {}
    message_raw = ((payload.get("msg") if payload else None) or (request.form.get("msg")) or "").strip()
    if not message_raw:
        return jsonify({"reply": "Please type something 😊", "crisis": False, "session_id": ""})

    now = datetime.utcnow()

    user_is_logged_in = bool(getattr(current_user, "is_authenticated", False))
    user_id: Optional[int] = current_user.id if user_is_logged_in else None

    bot_message_id: Optional[int] = None
    allow_save: bool = False
    need_confirm: bool = False
    confirm_prompt: str = ""
    confirm_yes_url: str = ""

    # ✅ preferred mode (auto/listener/coach/therapist/balanced)
    preferred_mode = "auto"
    if user_is_logged_in:
        preferred_mode = (getattr(current_user, "preferred_mode", None) or "auto").strip().lower()

    # =========================================================
    # ✅ robust session_id parsing (handles "" safely)
    # =========================================================
    chat_session: Optional[ChatSession] = None
    active_session_id: Optional[int] = None

    session_id = None
    if user_is_logged_in and user_id:
        session_id_raw = (((payload.get("session_id") if payload else None) or request.form.get("session_id") or "") if True else "").strip()
        session_id = int(session_id_raw) if session_id_raw.isdigit() else None
        chat_session = _ensure_logged_in_session(session_id, user_id)
        active_session_id = int(chat_session.id)

    # ---------------------------
    # Language detection + translate to EN
    # ---------------------------
    request_lang = (payload.get("lang") if payload else None) or request.form.get("lang")  # "en" or "ne" (may be omitted)

    lang_res = detect_language(
        message_raw,
        preferred_lang=getattr(current_user, "preferred_lang", "en"),
        request_lang=request_lang,
    )

    effective_lang = (getattr(lang_res, "effective_lang", None) or "en").lower().strip()
    message_en = message_raw if effective_lang == "en" else translate_text(message_raw, "en")

    # =========================================================
    # ✅ LANGUAGE MEMORY + ROMAN NEPALI FIX
    # =========================================================
    try:
        if bool(getattr(lang_res, "is_roman_nepali", False)):
            effective_lang = "ne"

        msg_en_lower = (message_en or "").lower()
        if ("nepali" in msg_en_lower) or ("नेपाली" in (message_raw or "")):
            effective_lang = "ne"

        prev_lang = session.get("conv_lang")
        if prev_lang in ("en", "ne") and effective_lang not in ("en", "ne"):
            effective_lang = prev_lang

        if effective_lang in ("en", "ne"):
            session["conv_lang"] = effective_lang

        message_en = translate_text(message_raw, "en") if effective_lang != "en" else message_raw
    except Exception:
        # never block chat on language issues
        effective_lang = effective_lang or "en"
        message_en = message_raw

    # ---------------------------
    # Feedback intent (EN)
    # ---------------------------
    feedback = detect_feedback_intent(message_en)

    # =========================================================
    # ✅ MEMORY/CONTEXT RECALL
    # =========================================================
    session_context_last_n: List[str] = []
    user_memory_last_n: List[str] = []

    if user_is_logged_in and user_id:
        # A) session context (user turns)
        if active_session_id:
            last_rows_session = (
                ChatHistory.query
                .filter_by(user_id=user_id, session_id=active_session_id, role="user")
                .order_by(ChatHistory.timestamp.desc())
                .limit(6)
                .all()
            )
            session_context_last_n = [r.content for r in reversed(last_rows_session) if r.content]

        # B) long-term memory across sessions (normalize to EN)
        last_rows_user = (
            ChatHistory.query
            .filter_by(user_id=user_id, role="user")
            .order_by(ChatHistory.timestamp.desc())
            .limit(24)
            .all()
        )

        tmp: List[str] = []
        for r in reversed(last_rows_user):
            txt = (r.content or "").strip()
            if not txt:
                continue
            lr = detect_language(
                txt,
                preferred_lang=getattr(current_user, "preferred_lang", "en"),
                request_lang=None,
            )
            eff = (getattr(lr, "effective_lang", None) or "en").lower().strip()
            txt_en = txt if eff == "en" else translate_text(txt, "en")
            tmp.append(txt_en)
        user_memory_last_n = tmp[-24:]
    else:
        # Guest: short memory in flask session
        guest_key = "guest_history_last_n"
        user_memory_last_n = session.get(guest_key, []) or []
        if not isinstance(user_memory_last_n, list):
            user_memory_last_n = []
        user_memory_last_n = (user_memory_last_n + [message_en])[-12:]
        session[guest_key] = user_memory_last_n

    # ---------------------------
    # Meta (always exists)
    # ---------------------------
    meta: Dict[str, Any] = {
        "feedback": feedback,
        "effective_lang": effective_lang,
        "is_roman_nepali": bool(getattr(lang_res, "is_roman_nepali", False)),
        "is_nepali": bool(getattr(lang_res, "is_nepali", False)),
        "session_id_in": session_id,
        "active_session_id": active_session_id,
        "session_context_n": len(session_context_last_n),
        "memory_context_n": len(user_memory_last_n),
        "preferred_mode": preferred_mode,
    }

    # =========================================================
    # ✅ RAW CRISIS DETECTION (HARD STOP ONLY ON HIGH)
    # =========================================================
    raw_sh = detect_self_harm(message_raw)
    self_harm = bool(getattr(raw_sh, "hit", False))

    sent_user = analyze_sentiment(message_en) or {}
    final_score = float(sent_user.get("final_score", 0.5))

    # If you compute trend elsewhere, keep it. Otherwise safe defaults:
    trend_label = "stable"
    slope = 0.0

    risk_level_raw, raw_reasons = safety.classify_risk(final_score, self_harm, trend_label, slope)
    risk_level_raw = (risk_level_raw or "low").lower().strip()

    # =========================================================
    # ✅ SAFETY CONFIRMATION (modal) — ONLY for *strong* distress
    # =========================================================
    try:
        txt = (message_en or "").lower()

        dep_or_help = re.search(
            r"\b(depressed|depression|hopeless|helpless|worthless)\b",
            txt,
            flags=re.IGNORECASE,
        )
        dep_strong = re.search(
            r"\b(very|so|really|extremely|severely|totally|super)\s+(depressed|hopeless|helpless|anxious|overwhelmed|stressed)\b",
            txt,
            flags=re.IGNORECASE,
        )
        helpless_phrases = re.search(
            r"(can't cope|cant cope|can't go on|cant go on|no way out|nothing can help|i give up|i can't handle|i cant handle)",
            txt,
            flags=re.IGNORECASE,
        )
        extreme_noun_forms = re.search(
            r"\b(extreme|severe)\s+(depression|anxiety|stress)\b|\bextremely\s+overwhelmed\b|\bextreme\s+overwhelmed\b",
            txt,
            flags=re.IGNORECASE,
        )
        anxiety_strong = re.search(
            r"\b(panic attack|anxiety attack|i'm panicking|im panicking|can't breathe|cant breathe|heart racing|terrified|extremely anxious|so anxious)\b",
            txt,
            flags=re.IGNORECASE,
        )

        strong_distress = bool(
            dep_strong
            or helpless_phrases
            or anxiety_strong
            or extreme_noun_forms
            or (dep_or_help and ("can't" in txt or "cant" in txt))
        )

        if strong_distress and risk_level_raw in ("low", "medium"):
            need_confirm = True
            confirm_prompt = "Are you in immediate danger right now?"
            confirm_yes_url = url_for("main.sos")
    except Exception:
        pass

    # Keep your brain raw risk check (if you still want it):
    try:
        from ChatbotWebsite.chatbot.brain.risk import assess_risk
        risk_brain_raw = (assess_risk(message_raw) or "low").lower().strip()
        if risk_brain_raw == "high" and risk_level_raw != "high":
            risk_level_raw = "high"
            raw_reasons = (raw_reasons or []) + ["brain_risk_high_from_raw_text"]
    except Exception:
        risk_brain_raw = "low"
    
    # ---------------- Protective statement (NEGATION) ----------------
# Example: "I don't want to die" → not crisis, supportive acknowledgment
    if getattr(raw_sh, "reason", None) == "negation":

        response_en = (
         "Life is beautiful and hard times eventually pass. I'm really glad you said that — it sounds like a part of you still wants to hold on.\n"
            "Do you want to tell me what’s been making things feel this heavy lately?"
        )

        response_ne = (
            "तपाईंले यस्तो भन्नु भयो, यो सुन्दा राम्रो लाग्यो — तपाईंभित्र अझै बाँचिरहन चाहने भाग छ जस्तो लाग्छ।\n"
            "के भइरहेको छ जसले यस्तो गाह्रो महसुस गराइरहेको छ, भन्न चाहनुहुन्छ?"
        )

        response_text = response_en if effective_lang == "en" else response_ne
        response_text = (response_text or "").replace("**", "")

        meta.update({
            "source": "safety_negation",
            "risk_level": "low",
            "crisis": False,
            "self_harm_reason": "negation_protective_statement",
            "risk_reasons": ["User expressed not wanting to die"],
            "redirect_sos": False,
            "cbt_tools": [],
        })

        return jsonify({
            "reply": response_text,
            "crisis": False,
            "session_id": active_session_id,
            "meta": meta
        })
    # =========================================================
    # ✅ HIGH RISK HARD STOP
    # =========================================================
    if risk_level_raw == "high":
        response_en = (
            "I’m really sorry you’re feeling this way.\n"
            "If you might harm yourself or you’re not safe, please get help now:\n"
            "• Nepal Police: 100  • Ambulance: 102\n"
            "• Call someone you trust and say: “I’m not safe alone.”\n"
            "I’m opening the emergency help page."
        )
        response_ne = (
            "मलाई दुःख लाग्यो तपाईं यस्तो महसुस गर्दै हुनुहुन्छ।\n"
            "यदि तपाईं सुरक्षित छैन/आफूलाई चोट पुर्‍याउने सोच छ भने, अहिले नै सहयोग लिनुहोस्:\n"
            "• नेपाल प्रहरी: 100  • एम्बुलेन्स: 102\n"
            "• नजिकको विश्वासिलो मान्छेलाई फोन गरेर भन्नुहोस्: “म एक्लै सुरक्षित छैन।”\n"
            "म SOS (Emergency Help) पेज खोल्दैछु।"
        )

        response_text = response_en if effective_lang == "en" else response_ne
        response_text = (response_text or "").replace("**", "")

        meta.update({
            "source": "safety_raw",
            "risk_level": "high",
            "crisis": True,
            "self_harm_reason": getattr(raw_sh, "reason", None),
            "risk_reasons": raw_reasons,
            "risk_brain_raw": risk_brain_raw,
            "sentiment_final_score": final_score,
            "sentiment_label": sent_user.get("label"),
            "sentiment_confidence": sent_user.get("confidence"),
            "redirect_sos": True,
            "redirect_url": url_for("main.sos"),
            "cbt_tools": ["crisis_escalation"],
        })

        brain_debug_log(
            message_raw=message_raw,
            message_en=message_en,
            effective_lang=effective_lang,
            feedback=feedback,
            risk_level="high",
            crisis=True,
            source="safety_raw",
            rewrite="crisis_raw",
            session_id=active_session_id,
            user_id=user_id,
            meta=meta,
        )

        # save (logged-in only)
        if user_is_logged_in and user_id and active_session_id:
            try:
                sent_bot = analyze_sentiment(response_en) or {}

                db.session.add(ChatHistory(
                    user_id=user_id,
                    session_id=active_session_id,
                    role="user",
                    content=message_raw,
                    timestamp=now,
                    sentiment_score=sent_user.get("final_score"),
                    sentiment_label=sent_user.get("label"),
                    contains_self_harm=self_harm,
                    crisis_mode=True,
                ))
                db.session.add(ChatHistory(
                    user_id=user_id,
                    session_id=active_session_id,
                    role="assistant",
                    content=response_text,
                    timestamp=now,
                    sentiment_score=sent_bot.get("final_score"),
                    sentiment_label=sent_bot.get("label"),
                    contains_self_harm=False,
                    crisis_mode=True,
                ))

                user_msg = ChatMessage(
                    message=message_raw,
                    timestamp=now,
                    user_id=user_id,
                    role="user",
                    session_id=active_session_id,
                )
                user_msg.intent_tag = "crisis"
                db.session.add(user_msg)
                db.session.flush()

                db.session.add(MessageLabel(
                    message_id=user_msg.id,
                    label="crisis",
                    labeled_by=None,
                ))

                if chat_session:
                    chat_session.updated_at = now

                db.session.commit()
            except Exception as e:
                db.session.rollback()
                current_app.logger.exception("DB save failed in crisis /chat_messages: %s", e)

        return jsonify({
            "reply": response_text,
            "crisis": True,
            "risk_level": "high",
            "redirect_sos": True,
            "redirect_url": url_for("main.sos"),
            "actions": {"sos_url": url_for("main.sos")},
            "session_id": active_session_id or "",
            "source": "safety_raw",
            "rewrite": "crisis_raw",
            "meta": meta,
        })

    # ✅ Not high → continue
    meta.update({
        "risk_level_raw": risk_level_raw,
        "risk_reasons_raw": raw_reasons,
        "risk_brain_raw": risk_brain_raw,
        "sentiment_final_score": final_score,
        "sentiment_label": sent_user.get("label"),
    })

    # =========================================================
    # ✅ MINDFULNESS SHORTCUT (audio-only, no text, no LLM)
    # Only when low risk
    # =========================================================
    hy = None
    try:
        if risk_level_raw == "low" and (_is_mindfulness_request(message_raw) or _is_mindfulness_request(message_en)):
            AUDIO_MAP = {
                "Mountain Meditation": ("Mountain Meditation", "8:12", "mountain_meditation.mp3"),
                "Breathing Retraining (10:45)": ("Breathing Retraining", "10:45", "breathing_retraining.mp3"),
                "Body Scan Meditation": ("Body Scan Meditation", "10:00", "body _scan_meditation.mp3"),
                "Rain and Thunder Sounds": ("Rain & Thunder Sounds", "10:00", "rain_and _thunder_sounds.mp3"),
            }

            title, duration, filename = AUDIO_MAP["Mountain Meditation"]
            audio_url = url_for("chatbot.serve_mindfulness_audio", filename=filename)
            hy = {
                "text": "",
                "crisis": False,
                "source": "mindfulness_audio",
                "meta": {"type": "mindfulness", "risk_level": "low"},
                "actions": {
                    "open_mindfulness": True,
                    "audio_url": audio_url,
                    "title": title,
                    "duration": duration,
                },
            }
    except Exception as e:
        current_app.logger.warning(f"Mindfulness shortcut failed: {e}")
        hy = None

    # =========================================================
    # ✅ TONE ROUTER GUARD (FUN/SOCIAL) BEFORE HYBRID
    # =========================================================
    try:
        tone = route_tone(message_en)
        meta.update({
            "tone_mode": getattr(tone, "mode", None),
            "tone_reason": getattr(tone, "reason", None),
            "tone_confidence": getattr(tone, "confidence", None),
        })

        if hy is None and getattr(tone, "mode", "") == "fun":
            response_en = (fun_reply(message_en) or "").strip() or "😄 Want a joke, a riddle, or a fun fact?"
            response_text = response_en if effective_lang == "en" else translate_text(response_en, effective_lang)
            response_text = (response_text or "").replace("**", "")

            if user_is_logged_in and user_id and active_session_id:
                try:
                    sent_bot = analyze_sentiment(response_en) or {}

                    db.session.add(ChatHistory(
                        user_id=user_id,
                        session_id=active_session_id,
                        role="user",
                        content=message_raw,
                        timestamp=now,
                        sentiment_score=sent_user.get("final_score"),
                        sentiment_label=sent_user.get("label"),
                        contains_self_harm=self_harm,
                        crisis_mode=False,
                    ))
                    db.session.add(ChatHistory(
                        user_id=user_id,
                        session_id=active_session_id,
                        role="assistant",
                        content=response_text,
                        timestamp=now,
                        sentiment_score=sent_bot.get("final_score"),
                        sentiment_label=sent_bot.get("label"),
                        contains_self_harm=False,
                        crisis_mode=False,
                    ))

                    user_msg = ChatMessage(
                        message=message_raw,
                        timestamp=now,
                        user_id=user_id,
                        role="user",
                        session_id=active_session_id,
                    )
                    user_msg.intent_tag = "fun"
                    db.session.add(user_msg)
                    db.session.flush()

                    db.session.add(MessageLabel(
                        message_id=user_msg.id,
                        label="fun",
                        labeled_by=None,
                    ))

                    if chat_session and chat_session.title == "New Chat":
                        chat_session.title = make_title(message_raw)
                    if chat_session:
                        chat_session.updated_at = now

                    db.session.commit()
                except Exception as e:
                    db.session.rollback()
                    current_app.logger.exception("DB save failed (fun guard) in /chat_messages: %s", e)

            return jsonify({
                "reply": response_text,
                "crisis": False,
                "risk_level": "low",
                "redirect_sos": False,
                "redirect_url": None,
                "session_id": active_session_id or "",
                "source": "tone_fun_guard",
                "rewrite": "none",
                "meta": meta,
            })

        if hy is None and getattr(tone, "mode", "") == "social":
            response_en = "Hey 😄 What’s up?"
            response_text = response_en if effective_lang == "en" else translate_text(response_en, effective_lang)
            response_text = (response_text or "").replace("**", "")
            return jsonify({
                "reply": response_text,
                "crisis": False,
                "risk_level": "low",
                "redirect_sos": False,
                "redirect_url": None,
                "session_id": active_session_id or "",
                "source": "tone_social_guard",
                "rewrite": "none",
                "meta": meta,
            })
    except Exception as e:
        current_app.logger.warning(f"Tone routing failed: {e}")

    # =========================================================
    # ✅ HYBRID RESPONSE (Brain + Mistral + Keras hint)
    # =========================================================
    if hy is None:
        if need_confirm:
            confirm_reply_en = (
                "I hear you. Before we continue—just one quick safety check.\n"
                "Are you in immediate danger right now?"
            )

            response_en = confirm_reply_en
            response_text = response_en if effective_lang == "en" else translate_text(response_en, effective_lang)
            response_text = (response_text or "").replace("**", "")

            hy = {
                "text": response_en,
                "crisis": False,
                "source": "safety_confirm_gate",
                "meta": {"risk_level": "medium", "redirect_sos": False},
            }
        else:
            hy = get_hybrid_response(
                user_message=message_en,
                user_message_raw=message_raw,
                user_lang=effective_lang,
                user_id=user_id if user_is_logged_in else "anon",
                session_id=active_session_id,
                history_last_n=user_memory_last_n,
                preferred_mode=preferred_mode,
            )

    # ✅ If mindfulness audio-only, allow empty text (no bot bubble)
    response_en = (hy.get("text") or "").strip()
    hy_meta = hy.get("meta") or {}
    is_mindfulness = (hy_meta.get("type") == "mindfulness")

    if (not response_en) and (not is_mindfulness):
        response_en = "I’m here with you. Tell me a little more."

    is_crisis = bool(hy.get("crisis", False))
    response_source = (hy.get("source") or "hybrid").strip()

    risk_level = (hy_meta.get("risk_level") or "low").lower().strip()
    redirect_sos = bool(hy_meta.get("redirect_sos", False))
    redirect_url = hy_meta.get("redirect_url")

    meta.update(hy_meta)
    meta["source"] = response_source
    meta["risk_level"] = risk_level

    # =========================================================
    # ✅ If mindfulness: SKIP rewrite/humanize/translate; keep empty reply
    # =========================================================
    if is_mindfulness:
        rewritten_en = ""
        rewrite_tag = "none"
        response_text = ""
    else:
        rw = rewrite_if_needed(
            is_crisis=is_crisis,
            user_raw=message_raw,
            user_en=message_en,
            base_reply_en=response_en,
            sentiment=sent_user if isinstance(sent_user, dict) else {},
            source=response_source,
            rewrite_reply_en_func=rewrite_reply_en,
        )
        rewritten_en, rewrite_tag = rw.text_en, rw.tag

        try:
            rewritten_en = humanize_reply(
                user_text=message_en,
                base_reply=rewritten_en,
                emotion=meta.get("emotion", "neutral"),
                intensity=int(meta.get("intensity", 2) or 2),
                profile={"preferred_mode": preferred_mode},
                user_obj=None,
            )
        except Exception as e:
            current_app.logger.warning(f"Humanize failed: {e}")

        response_text = rewritten_en if effective_lang == "en" else translate_text(rewritten_en, effective_lang)
        response_text = (response_text or "").replace("**", "")

    # ---------------------------
    # SAVE TO DB (logged-in only)
    # ---------------------------
    if user_is_logged_in and user_id and active_session_id:
        try:
            sent_bot = analyze_sentiment(rewritten_en) or {} if rewritten_en else {}

            db.session.add(ChatHistory(
                user_id=user_id,
                session_id=active_session_id,
                role="user",
                content=message_raw,
                timestamp=now,
                sentiment_score=sent_user.get("final_score"),
                sentiment_label=sent_user.get("label"),
                contains_self_harm=self_harm,
                crisis_mode=bool(is_crisis),
            ))

            db.session.add(ChatHistory(
                user_id=user_id,
                session_id=active_session_id,
                role="assistant",
                content=response_text,
                timestamp=now,
                sentiment_score=sent_bot.get("final_score") if sent_bot else None,
                sentiment_label=sent_bot.get("label") if sent_bot else None,
                contains_self_harm=False,
                crisis_mode=bool(is_crisis),
            ))

            assistant_msg = ChatMessage(
                message=response_text,
                timestamp=now,
                user_id=user_id,
                role="assistant",
                session_id=active_session_id,
            )
            assistant_msg.intent_tag = (rewrite_tag or response_source or "assistant")[:50]
            db.session.add(assistant_msg)
            db.session.flush()
            bot_message_id = int(assistant_msg.id)

            user_msg = ChatMessage(
                message=message_raw,
                timestamp=now,
                user_id=user_id,
                role="user",
                session_id=active_session_id,
            )

            predicted_tag = (
                meta.get("keras_intent_hint")
                or meta.get("keras_intent")
                or meta.get("strategy_name")
                or response_source
                or "general"
            )
            user_msg.intent_tag = str(predicted_tag)[:64]
            db.session.add(user_msg)
            db.session.flush()

            db.session.add(MessageLabel(
                message_id=user_msg.id,
                label=str(predicted_tag)[:10],
                labeled_by=None,
            ))

            if chat_session and chat_session.title == "New Chat":
                chat_session.title = make_title(message_raw)
            if chat_session:
                chat_session.updated_at = now

            save_user_mood_no_commit(user_id, message_raw)

            if risk_level != "high":
                update_profile_no_commit(
                    user_id=user_id,
                    session_id=active_session_id,
                    emotion=meta.get("emotion", "neutral"),
                    intensity=int(meta.get("intensity", 2) or 2),
                    distortions=meta.get("distortions", []),
                    style=meta.get("style", "neutral"),
                    trigger=meta.get("trigger"),
                    risk_level=risk_level,
                    coping_used=meta.get("coping_used"),
                    coping_accepted=meta.get("coping_accepted"),
                )

            db.session.commit()
        except Exception as e:
            db.session.rollback()
            current_app.logger.exception("DB save failed in /chat_messages: %s", e)

    # ---------------------------
    # RESPONSE JSON
    # ---------------------------
    allow_save = bool(
        user_is_logged_in
        and bot_message_id
        and (not is_crisis)
        and (len((_norm_text(response_text) or "")) >= 12)
        and (not _is_greeting_text(message_raw))
        and (not _is_greeting_reply(response_text))
    )

    resp: Dict[str, Any] = {
        "reply": response_text,
        "crisis": is_crisis,
        "risk_level": risk_level,
        "redirect_sos": bool(redirect_sos),
        "redirect_url": redirect_url,
        "session_id": active_session_id or "",
        "source": response_source,
        "rewrite": rewrite_tag,
        "meta": meta,
    }

    if hy.get("actions"):
        resp["actions"] = hy.get("actions")

    resp["bot_message_id"] = bot_message_id
    resp["allow_save"] = bool(allow_save)

    if need_confirm:
        resp["need_confirm"] = True
        resp["confirm_prompt"] = confirm_prompt
        resp["confirm_yes_url"] = confirm_yes_url

    if risk_level in ("high", "medium") or redirect_sos:
        resp["actions"] = {
            "sos_url": url_for("main.sos"),
            "consult_url": url_for("main.psychiatrist_page") if user_is_logged_in else url_for("users.login"),
        }

    brain_debug_log(
        message_raw=message_raw,
        message_en=message_en,
        effective_lang=effective_lang,
        feedback=feedback,
        risk_level=risk_level,
        crisis=is_crisis,
        source=response_source,
        rewrite=rewrite_tag,
        session_id=active_session_id,
        user_id=user_id,
        meta=meta,
    )

    return jsonify(resp)
# ---------------------------------
# Topic / Test / Mindfulness
# (Accepts both form-data and JSON)
# ---------------------------------
from flask import request, jsonify, current_app

def _get_payload_value(key: str, default: str = "") -> str:
    """
    Robustly read a key from either JSON body or form body.
    """
    try:
        if request.is_json:
            data = request.get_json(silent=True) or {}
            val = data.get(key, default)
        else:
            val = request.form.get(key, default)

        return (val or "").strip()
    except Exception:
        return default

from ChatbotWebsite.chatbot.test import get_test_messages, needs_immediate_danger_check
@chatbot.route("/topic", methods=["POST"])
def topic():
    data = request.get_json(silent=True) or {}
    title = (data.get("title") if isinstance(data, dict) else None) or request.form.get("title") or ""

    contents = get_content(title)
    return jsonify({"contents": contents})


@chatbot.route("/test", methods=["POST"])
def test():
    data = request.get_json(silent=True) or {}
    title = (data.get("title") if isinstance(data, dict) else None) or request.form.get("title") or ""

    questions = get_questions(title)

    # ✅ Safety: ensure frontend always receives a list
    if not isinstance(questions, list):
        questions = []

    return jsonify({"questions": questions})


@chatbot.route("/score", methods=["POST"])
def score():
    data = request.get_json(silent=True) or {}

    score_val = (data.get("score") if isinstance(data, dict) else None) or request.form.get("score") or 0
    title = (data.get("title") if isinstance(data, dict) else None) or request.form.get("title") or ""

    try:
        score_int = int(score_val)
    except Exception:
        score_int = 0

    score_msg = get_test_messages(title, score_int)

    # your existing helper (keep it)
    danger_check = needs_immediate_danger_check(title, score_int)

    # ✅ your requirement: show popup when score >= 20
    need_confirm = bool(danger_check) or (score_int >= 20)

    return jsonify({
        "score_message": score_msg,
        "danger_check": bool(danger_check),
        "need_confirm": bool(need_confirm),
        "confirm_prompt": "Are you in immediate danger right now?",
        "confirm_yes_url": url_for("main.sos"),
        "score": score_int,
        "title": title,
    })
    
from flask import jsonify, request

@chatbot.route("/mindfulness", methods=["POST"])
def mindfulness():
    """
    Returns JSON: { description: str, file_name: str }
    Used by send_function.html -> responseExercise()
    """
    payload = request.get_json(silent=True) if request.is_json else (request.form or {})
    title = (payload.get("title") or "").strip()

    if not title:
        return jsonify({"description": "Please choose a mindfulness exercise.", "file_name": ""}), 200

    file_name = ""
    desc = ""

    # mindfulness_exercises might be a dict:
    # {"Mountain Meditation (8:12)": {"file_name": "...", "description": "..."}} OR {"Title":"file.mp3"}
    try:
        if isinstance(mindfulness_exercises, dict):
            item = mindfulness_exercises.get(title)

            # dict could map directly to filename string
            if isinstance(item, str):
                file_name = item
                desc = get_description(title) or ""
            # dict could map to object/dict
            elif isinstance(item, dict):
                file_name = item.get("file_name") or item.get("file") or ""
                desc = item.get("description") or get_description(title) or ""
            else:
                # fallback
                desc = get_description(title) or ""

        # mindfulness_exercises might be a list of dicts
        elif isinstance(mindfulness_exercises, list):
            found = None
            for x in mindfulness_exercises:
                if not isinstance(x, dict):
                    continue
                if (x.get("title") or "").strip() == title:
                    found = x
                    break
            if found:
                file_name = found.get("file_name") or found.get("file") or ""
                desc = found.get("description") or get_description(title) or ""
            else:
                desc = get_description(title) or ""

        else:
            desc = get_description(title) or ""

    except Exception:
        # Never crash the UI
        desc = get_description(title) or ""

    # Friendly fallback description if still empty
    if not desc:
        desc = f"Starting: {title}\nFind a comfortable posture and begin when you're ready."

    return jsonify({"description": desc, "file_name": file_name}), 200    
# Manual Mood Add
# ---------------------------------
@chatbot.route("/mood/add", methods=["POST"])
@login_required
def add_mood():
    data = request.json or {}
    mood_value = data.get("mood_value")

    if mood_value is None:
        return jsonify({"error": "Mood is required"}), 400

    try:
        mood_int = int(mood_value)
    except ValueError:
        return jsonify({"error": "Mood must be a number"}), 400

    if not (1 <= mood_int <= 5):
        return jsonify({"error": "Mood must be between 1 and 5"}), 400

    db.session.add(MoodEntry(
        user_id=current_user.id,
        mood_value=mood_int,
        source="Manual",
        timestamp=datetime.utcnow()
    ))
    db.session.commit()

    return jsonify({"success": True})


# ---------------------------------
# Mood History
# ---------------------------------
@chatbot.route("/mood/history")
@login_required
def mood_history():
    moods = (
        MoodEntry.query
        .filter_by(user_id=current_user.id)
        .order_by(MoodEntry.timestamp.asc())
        .all()
    )

    mood_data = []
    for m in moods:
        if m.mood_value is None:
            continue

        src = (m.source or "Chat").strip()
        src_lower = src.lower()

        if src_lower == "manual":
            icon = "✏️"
            label_src = "Manual"
        elif src_lower == "chat":
            icon = "💬"
            label_src = "Chat"
        else:
            icon = "💬"
            label_src = src or "Chat"

        mv = int(m.mood_value)

        mood_data.append({
            "value": mv,
            "timestamp": m.timestamp.isoformat(),
            "source": f"{icon} {label_src}",
            "emoji": MOOD_EMOJI_MAP.get(mv, {}).get("emoji", "")
        })

    return jsonify(mood_data)


# ---------------------------------
# Chat Sentiment Stats
# ---------------------------------
@chatbot.route("/chat/sentiment/stats")
@login_required
def chat_sentiment_stats():
    q = (
        ChatHistory.query
        .filter_by(user_id=current_user.id, role="user")
        .filter(ChatHistory.sentiment_score.isnot(None))
    )

    total = q.count()
    if total == 0:
        return jsonify({
            "total": 0,
            "avg": None,
            "positive": 0,
            "neutral": 0,
            "negative": 0,
            "daily": []
        })

    avg_sent = (
        db.session.query(func.avg(ChatHistory.sentiment_score))
        .filter_by(user_id=current_user.id, role="user")
        .filter(ChatHistory.sentiment_score.isnot(None))
        .scalar()
    )

    counts = (
        db.session.query(ChatHistory.sentiment_label, func.count(ChatHistory.id))
        .filter_by(user_id=current_user.id, role="user")
        .filter(ChatHistory.sentiment_label.isnot(None))
        .group_by(ChatHistory.sentiment_label)
        .all()
    )
    count_map = {label: c for (label, c) in counts}

    daily = (
        db.session.query(
            func.date(ChatHistory.timestamp).label("day"),
            func.avg(ChatHistory.sentiment_score).label("avg"),
        )
        .filter_by(user_id=current_user.id, role="user")
        .filter(ChatHistory.sentiment_score.isnot(None))
        .group_by("day")
        .order_by("day")
        .all()
    )
    daily_data = [{"day": str(d), "avg": float(a)} for (d, a) in daily]

    return jsonify({
        "total": total,
        "avg": round(float(avg_sent), 4) if avg_sent is not None else None,
        "positive": count_map.get("positive", 0),
        "neutral": count_map.get("neutral", 0),
        "negative": count_map.get("negative", 0),
        "daily": daily_data
    })


# ---------------------------------
# Chat Sentiment Range (Day/Week/Month)
# ---------------------------------
@chatbot.route("/chat/sentiment/range")
@login_required
def chat_sentiment_range():
    range_mode = (request.args.get("range") or "week").lower().strip()
    now = datetime.utcnow()

    start = now - timedelta(days=7)
    group_key = func.date(ChatHistory.timestamp)

    if range_mode == "day":
        start = now - timedelta(hours=24)
        group_key = func.strftime("%Y-%m-%d %H:00", ChatHistory.timestamp)
    elif range_mode == "week":
        start = now - timedelta(days=7)
        group_key = func.date(ChatHistory.timestamp)
    elif range_mode == "month":
        start = now - timedelta(days=30)
        group_key = func.date(ChatHistory.timestamp)
    else:
        range_mode = "week"
        start = now - timedelta(days=7)
        group_key = func.date(ChatHistory.timestamp)

    rows = (
        db.session.query(
            group_key.label("bucket"),
            func.avg(ChatHistory.sentiment_score).label("avg_sent")
        )
        .filter(
            ChatHistory.user_id == current_user.id,
            ChatHistory.role == "user",
            ChatHistory.sentiment_score.isnot(None),
            ChatHistory.timestamp >= start
        )
        .group_by("bucket")
        .order_by("bucket")
        .all()
    )

    labels = [str(r.bucket) for r in rows]
    values = [float(r.avg_sent) if r.avg_sent is not None else None for r in rows]

    return jsonify({
        "range": range_mode,
        "start": start.isoformat(),
        "end": now.isoformat(),
        "labels": labels,
        "values": values
    })


# ---------------------------------
# Mood Stats (✅ includes Journal in streak + avg)
# ---------------------------------
@chatbot.route("/mood/stats")
@login_required
def mood_stats():
    avg_mood = db.session.query(func.avg(MoodEntry.mood_value)).filter_by(user_id=current_user.id).scalar()
    min_mood = db.session.query(func.min(MoodEntry.mood_value)).filter_by(user_id=current_user.id).scalar()
    max_mood = db.session.query(func.max(MoodEntry.mood_value)).filter_by(user_id=current_user.id).scalar()

    combined = _normalize_sources_for_graph(current_user.id)

    class _FakeMood:
        def __init__(self, ts, val):
            self.timestamp = ts
            self.mood_value = val

    fake_moods = [_FakeMood(x["timestamp"], x["value"]) for x in combined]

    positive_streak = calculate_positive_streak(
        fake_moods,
        positive_threshold=3,
        mode="avg"
    )

    combined_values = [x["value"] for x in combined]
    combined_avg = (sum(combined_values) / len(combined_values)) if combined_values else None

    return jsonify({
        "average": round(float(combined_avg), 2) if combined_avg is not None else (round(float(avg_mood), 2) if avg_mood is not None else None),
        "min": int(min_mood) if min_mood is not None else None,
        "max": int(max_mood) if max_mood is not None else None,
        "positive_streak": int(positive_streak)
    })

@chatbot.route("/chat/new_session", methods=["POST"])
@login_required
def new_session():
    # create a new session for the logged-in user
    s = ChatSession(user_id=current_user.id, title="New Chat")
    db.session.add(s)
    db.session.commit()

    return redirect(url_for("chatbot.chat", session=s.id))
# ---------------------------------
# Mood Dashboard Page
# ---------------------------------
@chatbot.route("/mood")
@login_required
def mood_dashboard():
    return render_template("mood_dashboard.html", title="Mood Tracker")


# ---------------------------------
# Export Mood PDF (kept; uses MoodEntry only)
# ---------------------------------
@chatbot.route("/mood/export_pdf")
@login_required
def export_mood_pdf():
    moods = (
        MoodEntry.query
        .filter_by(user_id=current_user.id)
        .order_by(MoodEntry.timestamp.asc())
        .all()
    )

    if not moods:
        return "No mood data available", 400

    def hex_color(h):
        h = h.lstrip("#")
        return colors.Color(int(h[0:2], 16)/255, int(h[2:4], 16)/255, int(h[4:6], 16)/255)

    LUMORA_RED = hex_color("#d63031")
    LUMORA_MUTED = hex_color("#636e72")
    SOFT_BG = hex_color("#fbf7ff")
    SOFT_LINE = hex_color("#eee6f5")

    mood_labels = {1: "Terrible", 2: "Low", 3: "Neutral", 4: "Good", 5: "Excellent"}

    values = [int(m.mood_value) for m in moods if m.mood_value is not None]
    avg_mood = (sum(values) / len(values)) if values else None
    last = moods[-1]
    best_val = max(values) if values else None
    worst_val = min(values) if values else None

    last7 = [int(m.mood_value) for m in moods[-7:] if m.mood_value is not None]
    trend = ""
    if len(last7) >= 2:
        if last7[-1] > last7[0]:
            trend = "Improving"
        elif last7[-1] < last7[0]:
            trend = "Declining"
        else:
            trend = "Stable"

    x_labels = [m.timestamp.strftime("%b %d") for m in moods]
    y_values = [int(m.mood_value) for m in moods]

    img_buf = BytesIO()
    fig = plt.figure(figsize=(10, 4))
    ax = fig.add_subplot(111)
    ax.plot(x_labels, y_values, marker="o", linewidth=2)
    ax.set_ylim(1, 5)
    ax.set_yticks([1, 2, 3, 4, 5])
    ax.set_title("Mood Trend", fontsize=12)
    ax.grid(True, alpha=0.25)

    if len(x_labels) > 12:
        step = max(1, len(x_labels) // 10)
        for i, lbl in enumerate(ax.get_xticklabels()):
            lbl.set_visible(i % step == 0)

    plt.xticks(rotation=0)
    plt.tight_layout()
    fig.savefig(img_buf, format="PNG", dpi=180)
    plt.close(fig)
    img_buf.seek(0)

    pdf_buf = BytesIO()
    c = canvas.Canvas(pdf_buf, pagesize=letter)
    width, height = letter

    LEFT, RIGHT = 50, width - 50
    TOP, BOTTOM = height - 55, 50

    def draw_soft_card(x, y, w, h):
        c.setFillColor(SOFT_BG)
        c.setStrokeColor(SOFT_LINE)
        c.setLineWidth(1)
        c.rect(x, y, w, h, stroke=1, fill=1)
        c.setFillColor(colors.black)

    def header(page_num):
        c.setFont("Helvetica-Bold", 20)
        c.setFillColor(LUMORA_RED)
        c.drawString(LEFT, TOP + 10, "LUMORA")

        c.setFont("Helvetica", 12)
        c.setFillColor(colors.black)
        c.drawString(LEFT + 95, TOP + 12, "Mood Report")

        c.setFont("Helvetica", 10)
        c.setFillColor(LUMORA_MUTED)
        c.drawString(LEFT, TOP - 8, f"User: {current_user.username}")
        c.drawRightString(RIGHT, TOP - 8, f"Page {page_num}")

        c.setFillColor(LUMORA_MUTED)
        c.drawString(LEFT, TOP - 23, f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        c.setFillColor(colors.black)

        c.setStrokeColor(SOFT_LINE)
        c.setLineWidth(1)
        c.line(LEFT, TOP - 33, RIGHT, TOP - 33)

    def table_header(y):
        c.setFont("Helvetica-Bold", 10)
        c.setFillColor(colors.black)
        c.drawString(LEFT, y, "Date & Time")
        c.drawString(250, y, "Mood")
        c.drawString(310, y, "Label")
        c.drawString(420, y, "Source")

        c.setStrokeColor(SOFT_LINE)
        c.line(LEFT, y - 6, RIGHT, y - 6)
        return y - 18

    page = 1
    header(page)

    card_top = TOP - 50
    card_h = 85
    card_y = card_top - card_h
    draw_soft_card(LEFT, card_y, RIGHT - LEFT, card_h)

    c.setFont("Helvetica-Bold", 11)
    c.setFillColor(colors.black)
    c.drawString(LEFT + 12, card_top - 18, "Summary")

    c.setFont("Helvetica", 10)
    c.setFillColor(LUMORA_MUTED)

    avg_text = f"{avg_mood:.2f} ({mood_labels.get(round(avg_mood), '')})" if avg_mood is not None else "—"
    last_text = f"{int(last.mood_value)} ({mood_labels.get(int(last.mood_value), '')})" if last.mood_value is not None else "—"
    best_text = f"{best_val} ({mood_labels.get(best_val,'')})" if best_val is not None else "—"
    worst_text = f"{worst_val} ({mood_labels.get(worst_val,'')})" if worst_val is not None else "—"

    c.drawString(LEFT + 12, card_top - 40, f"Average mood: {avg_text}")
    c.drawString(LEFT + 12, card_top - 58, f"Latest mood: {last_text}  •  Trend (last 7): {trend or '—'}")

    c.drawRightString(RIGHT - 12, card_top - 40, f"Best: {best_text}")
    c.drawRightString(RIGHT - 12, card_top - 58, f"Worst: {worst_text}")

    c.setFillColor(colors.black)

    legend_y = card_y - 18
    c.setFont("Helvetica", 9)
    c.setFillColor(LUMORA_MUTED)
    c.drawString(LEFT, legend_y, "Mood scale: 1 Terrible  •  2 Low  •  3 Neutral  •  4 Good  •  5 Excellent")
    c.setFillColor(colors.black)

    chart_y_top = legend_y - 10
    chart_h = 210
    chart_y = chart_y_top - chart_h
    image = ImageReader(img_buf)
    c.drawImage(image, LEFT, chart_y, width=(RIGHT - LEFT), height=chart_h, preserveAspectRatio=True, mask="auto")

    y = chart_y - 22
    c.setFont("Helvetica-Bold", 12)
    c.setFillColor(colors.black)
    c.drawString(LEFT, y, "Entries")
    y -= 16

    y = table_header(y)
    c.setFont("Helvetica", 10)

    for m in moods:
        if y < BOTTOM + 25:
            c.showPage()
            page += 1
            header(page)
            y = TOP - 60
            y = table_header(y)
            c.setFont("Helvetica", 10)

        dt = m.timestamp.strftime("%Y-%m-%d %H:%M")
        mv = int(m.mood_value) if m.mood_value is not None else None
        label = mood_labels.get(mv, "") if mv is not None else ""
        src = (m.source or "Chat").strip()

        c.setFillColor(colors.black)
        c.drawString(LEFT, y, dt)

        c.setFillColor(LUMORA_RED if mv is not None and mv <= 2 else colors.black)
        c.drawString(250, y, str(mv) if mv is not None else "—")

        c.setFillColor(LUMORA_MUTED)
        c.drawString(310, y, label)
        c.setFillColor(colors.black)
        c.drawString(420, y, src[:28])

        c.setStrokeColor(SOFT_LINE)
        c.line(LEFT, y - 6, RIGHT, y - 6)

        y -= 16

    c.setFont("Helvetica-Oblique", 8.5)
    c.setFillColor(LUMORA_MUTED)
    c.drawString(LEFT, BOTTOM - 10, "Educational self-tracking only — not a medical diagnosis.")
    c.setFillColor(colors.black)

    c.save()
    pdf_buf.seek(0)

    return send_file(
        pdf_buf,
        as_attachment=True,
        download_name="Mood_Report.pdf",
        mimetype="application/pdf",
    )


# ---------------------------------
# Mood Journal API (✅ fixed mapping)
# ---------------------------------
@chatbot.route("/mood/journal")
@login_required
def mood_journal():
    journals = (
        Journal.query
        .filter_by(user_id=current_user.id)
        .order_by(Journal.timestamp.asc())
        .all()
    )

    journal_data = []
    for j in journals:
        mood_name = (j.mood or "Neutral").strip()
        journal_data.append({
            "id": j.id,
            "title": j.title,
            "content": j.content,
            "mood": mood_name,
            "mood_value": JOURNAL_VALUE_MAP.get(mood_name, 3),
            "emoji": JOURNAL_EMOJI_MAP.get(mood_name, "📝"),
            "timestamp": j.timestamp.isoformat()
        })

    return jsonify(journal_data)


# ---------------------------------
# Burnout Detection (✅ updated to use numeric mapping)
# ---------------------------------
@chatbot.route("/mood/burnout")
@login_required
def burnout_page():
    return render_template("burnout_page.html", title="Burnout Check")


@chatbot.route("/api/mood/burnout")
@login_required
def detect_burnout_api():
    LOW_MOOD_VALUES = {1, 2}
    LOW_SENTIMENT = {"negative"}

    moods = (
        MoodEntry.query
        .filter_by(user_id=current_user.id)
        .order_by(MoodEntry.timestamp.desc())
        .limit(10)
        .all()
    )

    journals = (
        Journal.query
        .filter_by(user_id=current_user.id)
        .filter(Journal.mood.isnot(None))
        .order_by(Journal.timestamp.desc())
        .limit(10)
        .all()
    )

    sentiments = (
        ChatHistory.query
        .filter_by(user_id=current_user.id, role="user")
        .filter(ChatHistory.sentiment_label.isnot(None))
        .order_by(ChatHistory.timestamp.desc())
        .limit(20)
        .all()
    )

    combined = []

    for m in moods:
        if m.mood_value is None:
            continue
        mv = int(m.mood_value)
        combined.append({
            "timestamp": m.timestamp,
            "source": "mood",
            "is_low": mv in LOW_MOOD_VALUES,
            "raw": mv,
        })

    for j in journals:
        jv = _journal_to_value(j.mood)
        combined.append({
            "timestamp": j.timestamp,
            "source": "journal",
            "is_low": jv in LOW_MOOD_VALUES,
            "raw": (j.mood or "Neutral"),
            "value": jv
        })

    for s in sentiments:
        lab = str(s.sentiment_label).lower()
        combined.append({
            "timestamp": s.timestamp,
            "source": "chat_sentiment",
            "is_low": lab in LOW_SENTIMENT,
            "raw": lab,
        })

    combined.sort(key=lambda x: x["timestamp"], reverse=True)

    if len(combined) < 3:
        return jsonify({
            "burnout": False,
            "level": "Normal",
            "message": "Not enough recent data. Add at least 3 signals (mood/journal/chat).",
            "why": "Burnout is trend-based. Lumora needs 3 recent signals to check a pattern.",
            "last_three": [],
            "redirect_url": None
        })

    last_three = combined[:3]

    score = 0
    for x in last_three:
        if x["source"] in ("mood", "journal") and x["is_low"]:
            score += 2
        elif x["source"] == "chat_sentiment" and x["is_low"]:
            score += 1

    payload_last_three = [{
        "source": x["source"],
        "raw": x["raw"],
        "is_low": bool(x["is_low"]),
        "time": x["timestamp"].isoformat()
    } for x in last_three]

    if score >= 4:
        return jsonify({
            "burnout": True,
            "level": "High",
            "message": "High burnout risk detected: repeated low signals.",
            "why": "Two or more strong recent signals (mood/journal) were low. Chat sentiment is treated as a weaker signal to reduce false alarms.",
            "score": score,
            "last_three": payload_last_three,
            "redirect_url": url_for("main.psychiatrist_page")
        })

    if score >= 2:
        return jsonify({
            "burnout": True,
            "level": "Moderate",
            "message": "Moderate burnout risk: some recent low signals.",
            "why": "At least one recent signal suggests stress/low mood. Consider journaling, rest, and checking again tomorrow.",
            "score": score,
            "last_three": payload_last_three,
            "redirect_url": None,
            "consult_url": url_for("main.psychiatrist_page")
        })

    return jsonify({
        "burnout": False,
        "level": "Normal",
        "message": "No burnout detected from recent signals.",
        "why": "Your recent signals are not consistently low. Lumora looks for patterns across mood, journaling, and chat sentiment to reduce false positives.",
        "score": score,
        "last_three": payload_last_three,
        "redirect_url": None
    })


# ---------------------------------
# Mood Check-in Page
# ---------------------------------
@chatbot.route("/mood/checkin", methods=["GET", "POST"])
@login_required
def mood_checkin():
    if request.method == "POST":
        mood_value = int(request.form.get("mood"))
        db.session.add(MoodEntry(
            user_id=current_user.id,
            mood_value=mood_value,
            source="Manual",
            timestamp=datetime.utcnow()
        ))
        db.session.commit()

        flash("Mood recorded successfully 💙", "success")
        return redirect(url_for("chatbot.mood_dashboard"))

    return render_template("mood_checkin.html")


# ---------------------------------
# Extra: summary + trend endpoints
# ---------------------------------
@chatbot.route("/chat/sentiment/summary")
@login_required
def chat_sentiment_summary():
    stats = (
        db.session.query(ChatHistory.sentiment_label, func.count(ChatHistory.id))
        .filter(ChatHistory.user_id == current_user.id, ChatHistory.role == "user")
        .group_by(ChatHistory.sentiment_label)
        .all()
    )
    return jsonify({label: count for label, count in stats})


@chatbot.route("/chat/sentiment/trend")
@login_required
def chat_sentiment_trend():
    daily = (
        db.session.query(
            func.date(ChatHistory.timestamp).label("day"),
            func.avg(ChatHistory.sentiment_score).label("avg_sent")
        )
        .filter(
            ChatHistory.user_id == current_user.id,
            ChatHistory.role == "user",
            ChatHistory.sentiment_score.isnot(None)
        )
        .group_by("day")
        .order_by("day")
        .all()
    )
    return jsonify([{"day": str(d), "avg": float(a)} for d, a in daily])


@chatbot.route("/analytics/mood_vs_sentiment")
@login_required
def mood_vs_sentiment():
    mood_daily = dict(
        db.session.query(
            func.date(MoodEntry.timestamp).label("day"),
            func.avg(MoodEntry.mood_value).label("avg_mood")
        )
        .filter(MoodEntry.user_id == current_user.id)
        .group_by("day")
        .all()
    )

    sent_daily = dict(
        db.session.query(
            func.date(ChatHistory.timestamp).label("day"),
            func.avg(ChatHistory.sentiment_score).label("avg_sent")
        )
        .filter(
            ChatHistory.user_id == current_user.id,
            ChatHistory.role == "user",
            ChatHistory.sentiment_score.isnot(None)
        )
        .group_by("day")
        .all()
    )

    mood_daily_str = {str(k): float(v) for k, v in mood_daily.items()}
    sent_daily_str = {str(k): float(v) for k, v in sent_daily.items()}
    all_days = sorted(set(mood_daily_str.keys()) | set(sent_daily_str.keys()))

    data = []
    for day in all_days:
        data.append({
            "day": day,
            "avg_mood": mood_daily_str.get(day, None),
            "avg_sent": sent_daily_str.get(day, None)
        })

    return jsonify(data)


# ---------------------------------
# Feedback submit
# ---------------------------------
@chatbot.route("/feedback", methods=["POST"])
@login_required
def submit_feedback():
    session_id = request.form.get("session_id", type=int)
    rating = request.form.get("rating", type=int)
    helpful = (request.form.get("helpful") == "yes")
    comments = (request.form.get("comments") or "").strip()

    if session_id is None:
        flash("Missing session id.", "danger")
        return redirect(url_for("chatbot.chat"))

    if rating is None or not (1 <= rating <= 5):
        flash("Invalid rating (must be 1 to 5).", "danger")
        return redirect(url_for("chatbot.chat", session=session_id))

    already = UserFeedback.query.filter_by(
        user_id=current_user.id,
        session_id=session_id
    ).first()
    if already:
        flash("Feedback already submitted for this chat.", "info")
        return redirect(url_for("chatbot.chat", session=session_id))

    fb = UserFeedback(
        user_id=current_user.id,
        session_id=session_id,
        rating=rating,
        helpful=helpful,
        comments=comments[:1000] if comments else None
    )
    db.session.add(fb)
    db.session.commit()

    flash("Thanks! Feedback saved.", "success")
    return redirect(url_for("chatbot.chat", session=session_id))


import json
from sqlalchemy import func
from flask import request, abort, flash, redirect, url_for, render_template, send_file
from flask_login import login_required, current_user

import matplotlib.pyplot as plt

from ChatbotWebsite import db
from ChatbotWebsite.models import ChatHistory, EvalDataset  # make sure EvalDataset exists

# ---------------------------
# Helper: sample messages (non-frozen)
# ---------------------------
from sqlalchemy import func
from flask import request, abort, flash, redirect, url_for, render_template, send_file
from flask_login import login_required, current_user
import matplotlib.pyplot as plt

from ChatbotWebsite import db
from ChatbotWebsite.models import ChatHistory, EvalDataset, EvalDatasetItem


def _balanced_sample_chat_history(limit: int = 90):
    labels = ["negative", "neutral", "positive"]
    per = max(1, limit // 3)

    picked_ids = set()
    picked_rows = []

    for lab in labels:
        q = (
            ChatHistory.query
            .filter(ChatHistory.role == "user")
            .filter(ChatHistory.sentiment_label == lab)
            .order_by(func.random())
            .limit(per)
        )
        rows = q.all()
        for r in rows:
            if r.id not in picked_ids:
                picked_ids.add(r.id)
                picked_rows.append(r)

    remaining = limit - len(picked_rows)
    if remaining > 0:
        q2 = (
            ChatHistory.query
            .filter(ChatHistory.role == "user")
            .filter(ChatHistory.id.notin_(list(picked_ids)) if picked_ids else True)
            .order_by(func.random())
            .limit(remaining)
        )
        more = q2.all()
        for r in more:
            if r.id not in picked_ids:
                picked_ids.add(r.id)
                picked_rows.append(r)

    return picked_rows


def _ensure_dataset_items(dataset_id: int, limit: int = 90) -> int:
    """
    If dataset has no items, create a balanced sample ONCE and insert items.
    Returns total item count after ensuring.
    """
    existing = EvalDatasetItem.query.filter_by(dataset_id=dataset_id).count()
    if existing > 0:
        return existing

    rows = _balanced_sample_chat_history(limit=limit)
    for r in rows:
        db.session.add(EvalDatasetItem(dataset_id=dataset_id, chat_history_id=r.id))
    db.session.commit()
    return EvalDatasetItem.query.filter_by(dataset_id=dataset_id).count()


@chatbot.route("/evaluation/dataset/<int:dataset_id>/freeze", methods=["POST"])
@login_required
def freeze_eval_dataset(dataset_id: int):
    if not _is_admin_user():
        abort(403)

    ds = EvalDataset.query.filter_by(id=dataset_id, created_by=current_user.id).first_or_404()

    # ✅ make sure membership exists before freezing
    _ensure_dataset_items(dataset_id, limit=90)

    ds.is_frozen = True
    db.session.commit()

    flash("Dataset frozen (reproducible set locked).", "success")
    return redirect(url_for("chatbot.label_messages_page", dataset_id=dataset_id))


@chatbot.route("/evaluation/dataset/<int:dataset_id>/unfreeze", methods=["POST"])
@login_required
def unfreeze_eval_dataset(dataset_id: int):
    if not _is_admin_user():
        abort(403)

    ds = EvalDataset.query.filter_by(id=dataset_id, created_by=current_user.id).first_or_404()
    ds.is_frozen = False
    db.session.commit()

    flash("Dataset unfrozen.", "info")
    return redirect(url_for("chatbot.label_messages_page", dataset_id=dataset_id))


# ---------------------------------
# Evaluation J1 (UPDATED)
# ---------------------------------
@chatbot.route("/evaluation/j1")
@login_required
def j1_evaluation():
    from ChatbotWebsite.chatbot.evaluation.j1_sentiment_eval import evaluate_sentiment

    dataset_id_raw = (request.args.get("dataset_id") or "").strip()
    dataset_id = int(dataset_id_raw) if dataset_id_raw.isdigit() else None

    results = evaluate_sentiment(dataset_id=dataset_id) or {}
    if not isinstance(results, dict):
        results = {}

    # --- meta (template expects results.meta.* in places) ---
    meta = results.get("meta") if isinstance(results.get("meta"), dict) else {}
    meta.setdefault("labels", results.get("labels", ["negative", "neutral", "positive"]))
    meta.setdefault("metric", "Macro-F1")
    meta.setdefault("note", "Results are computed on the selected evaluation dataset (freeze = reproducible).")

    # ✅ ensure distribution always exists (prevents jinja UndefinedError)
    meta.setdefault("distribution", {"negative": 0, "neutral": 0, "positive": 0})

    # ✅ IMPORTANT: keep meta inside results too (because template uses results.meta.distribution.*)
    results["meta"] = meta

    return render_template("evaluation/j1.html", results=results, meta=meta)
@chatbot.route("/evaluation/j1/f1.png")
@login_required
def j1_f1_chart():
    from ChatbotWebsite.chatbot.evaluation.j1_sentiment_eval import evaluate_sentiment
    from ChatbotWebsite.chatbot.evaluation.charts import fig_to_png

    dataset_id_raw = (request.args.get("dataset_id") or "").strip()
    dataset_id = int(dataset_id_raw) if dataset_id_raw.isdigit() else None

    res = evaluate_sentiment(dataset_id=dataset_id)
    names = ["VADER", "ML", "Hybrid"]
    vals = [res["f1"]["vader"], res["f1"]["ml"], res["f1"]["hybrid"]]

    fig, ax = plt.subplots(figsize=(7.2, 4.0), dpi=160)
    bars = ax.bar(names, vals, edgecolor="black", linewidth=0.6)
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("Macro-F1 Score")
    ax.set_title("Macro-F1 Comparison")
    ax.grid(axis="y", alpha=0.25)

    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width()/2, v + 0.02, f"{v:.2f}", ha="center", va="bottom", fontsize=10)

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    buf = fig_to_png(fig)
    resp = send_file(buf, mimetype="image/png")
    resp.headers["Cache-Control"] = "no-store"
    return resp


@chatbot.route("/evaluation/j1/confusion.png")
@login_required
def j1_confusion_chart():
    from ChatbotWebsite.chatbot.evaluation.j1_sentiment_eval import evaluate_sentiment
    from ChatbotWebsite.chatbot.evaluation.charts import fig_to_png

    dataset_id_raw = (request.args.get("dataset_id") or "").strip()
    dataset_id = int(dataset_id_raw) if dataset_id_raw.isdigit() else None

    res = evaluate_sentiment(dataset_id=dataset_id)

    cm = res["confusion"]["hybrid"]
    labels = res["labels"]

    fig, ax = plt.subplots(figsize=(6.2, 5.0), dpi=160)
    im = ax.imshow(cm, cmap="Blues")

    ax.set_title("Confusion Matrix (Hybrid Model)")
    ax.set_xlabel("Predicted Label")
    ax.set_ylabel("Actual Label")

    ax.set_xticks(range(len(labels)))
    ax.set_yticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=25, ha="right")
    ax.set_yticklabels(labels)

    for i in range(len(labels)):
        for j in range(len(labels)):
            ax.text(j, i, cm[i][j], ha="center", va="center", fontsize=11, color="black")

    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    fig.tight_layout()

    buf = fig_to_png(fig)
    resp = send_file(buf, mimetype="image/png")
    resp.headers["Cache-Control"] = "no-store"
    return resp

# ---------------------------------
#
# ---------------------------------
# Evaluation J2
# ---------------------------------
@chatbot.route("/evaluation/j2")
@login_required
def j2_page():
    rows = UserFeedback.query.filter_by(user_id=current_user.id).all()

    total = len(rows)
    avg_rating = round(sum(r.rating for r in rows) / total, 2) if total else None
    helpful_yes = sum(1 for r in rows if r.helpful)
    helpful_no = sum(1 for r in rows if not r.helpful)
    helpful_pct = round((helpful_yes / total) * 100, 1) if total else None

    stats = {
        "total": total,
        "avg_rating": avg_rating,
        "helpful_yes": helpful_yes,
        "helpful_no": helpful_no,
        "helpful_pct": helpful_pct,
    }

    # ✅ Wilson 95% CI for Helpful rate (credit-heavy)
    import math
    if total and total > 0:
        z = 1.96
        phat = helpful_yes / total
        denom = 1 + (z**2) / total
        center = (phat + (z**2) / (2 * total)) / denom
        margin = (z * math.sqrt((phat * (1 - phat) + (z**2) / (4 * total)) / total)) / denom

        lo = max(0.0, center - margin)
        hi = min(1.0, center + margin)

        stats["ci_lo"] = round(lo * 100, 1)
        stats["ci_hi"] = round(hi * 100, 1)
    else:
        stats["ci_lo"] = None
        stats["ci_hi"] = None


    per_session = (
        db.session.query(
            ChatSession.id.label("session_id"),
            ChatSession.title.label("title"),
            func.count(UserFeedback.id).label("n"),
            func.avg(UserFeedback.rating).label("avg_rating"),
            func.sum(case((UserFeedback.helpful == True, 1), else_=0)).label("yes"),
            func.sum(case((UserFeedback.helpful == False, 1), else_=0)).label("no"),
            func.max(UserFeedback.created_at).label("last_feedback_at"),
        )
        .join(UserFeedback, UserFeedback.session_id == ChatSession.id)
        .filter(ChatSession.user_id == current_user.id)
        .group_by(ChatSession.id, ChatSession.title)
        .order_by(func.max(UserFeedback.created_at).desc())
        .all()
    )

    return render_template("evaluation/j2.html", stats=stats, per_session=per_session)
@chatbot.route("/evaluation/j2/ratings.png")
@login_required
def j2_ratings_chart():
    # ✅ match J2: current user only
    rows = UserFeedback.query.filter_by(user_id=current_user.id).all()

    counts = {i: 0 for i in range(1, 6)}
    total = 0
    weighted_sum = 0

    for r in rows:
        if r.rating in counts:
            counts[r.rating] += 1
            total += 1
            weighted_sum += int(r.rating)

    fig, ax = plt.subplots(figsize=(8.0, 4.2), dpi=180)

    if total == 0:
        ax.text(0.5, 0.5, "No ratings submitted yet", ha="center", va="center", fontsize=13)
        ax.axis("off")
        buf = fig_to_png(fig, dpi=220)
        resp = send_file(buf, mimetype="image/png", max_age=0)
        resp.headers["Cache-Control"] = "no-store"
        return resp

    avg = weighted_sum / total

    y_labels = [f"{i} ★" for i in range(5, 0, -1)]
    values = [counts[i] for i in range(5, 0, -1)]
    perc = [(v / total) * 100 for v in values]

    bars = ax.barh(y_labels, values, edgecolor="#111", linewidth=0.6)

    pad = max(0.15, total * 0.02)
    for b, v, p in zip(bars, values, perc):
        ax.text(v + pad, b.get_y() + b.get_height()/2, f"{v}  ({p:.1f}%)",
                va="center", fontsize=10)

    # ----- title & subtitle (NO suptitle) -----
    ax.set_title(
    "Ratings Distribution (Session-level)",
    fontsize=14,
    fontweight="bold",
    pad=14
)

    ax.text(
    0.5, 1.01,
    "Counts and percentages of session-level feedback",
    transform=ax.transAxes,
    ha="center",
    va="bottom",
    fontsize=10,
    color="#555555"
)

# footer annotation (academic, compact)
    ax.text(
    0.99, -0.18,
    f"Total = {total}   •   Mean = {avg:.2f}/5",
    transform=ax.transAxes,
    ha="right",
    va="top",
    fontsize=11,
    fontweight="bold"
)

# IMPORTANT: control layout manually
    fig.subplots_adjust(top=0.82, bottom=0.22)

    buf = fig_to_png(fig, dpi=240)
    resp = send_file(buf, mimetype="image/png", max_age=0)
    resp.headers["Cache-Control"] = "no-store"
    return resp



@chatbot.route("/evaluation/j2/helpful.png")
@login_required
def j2_helpful_chart():
    yes = (
        db.session.query(func.count(UserFeedback.id))
        .filter(UserFeedback.user_id == current_user.id, UserFeedback.helpful == True)
        .scalar()
    ) or 0

    no = (
        db.session.query(func.count(UserFeedback.id))
        .filter(UserFeedback.user_id == current_user.id, UserFeedback.helpful == False)
        .scalar()
    ) or 0

    n = int(yes) + int(no)

    fig, ax = plt.subplots(figsize=(8.0, 4.2), dpi=180)

    if n == 0:
        ax.text(0.5, 0.5, "No feedback submitted yet", ha="center", va="center", fontsize=13)
        ax.axis("off")
        buf = fig_to_png(fig, dpi=220)
        resp = send_file(buf, mimetype="image/png", max_age=0)
        resp.headers["Cache-Control"] = "no-store"
        return resp

    labels = [f"Helpful (n={yes})", f"Not Helpful (n={no})"]
    values = [yes, no]
    colors = ["#2F6FED", "#FF8A00"]

    wedges, _ = ax.pie(
        values,
        startangle=90,
        counterclock=False,
        colors=colors,
        wedgeprops=dict(width=0.38, edgecolor="white", linewidth=2),
    )

    # % labels on ring
    for w, v in zip(wedges, values):
        pct = 100.0 * v / n
        ang = (w.theta2 + w.theta1) / 2.0
        x = 0.78 * math.cos(math.radians(ang))
        y = 0.78 * math.sin(math.radians(ang))
        ax.text(x, y, f"{pct:.1f}%\n(n={v})", ha="center", va="center", fontsize=10)

    # center text
    ax.text(0, 0.04, "Total", ha="center", va="center", fontsize=12, fontweight="bold")
    ax.text(0, -0.10, f"{n}", ha="center", va="center", fontsize=18, fontweight="bold")

    ax.set_aspect("equal")
    ax.axis("off")  # ✅ looks clean

    # legend below (inside figure space)
    ax.legend(
        wedges, labels,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.06),
        ncol=2,
        frameon=False,
        fontsize=10
    )

    # ✅ more bottom space so legend never gets cut
    fig.subplots_adjust(top=0.95, bottom=0.22)

    buf = fig_to_png(fig, dpi=220)
    resp = send_file(buf, mimetype="image/png", max_age=0)
    resp.headers["Cache-Control"] = "no-store"
    return resp

# ---------------------------------
# Evaluation J3
# ---------------------------------
@chatbot.route("/evaluation/j3")
@login_required
def j3_page():
    user_id = current_user.id

    sessions_used = (
        db.session.query(func.count(ChatSession.id))
        .filter(ChatSession.user_id == user_id)
        .filter(ChatSession.is_archived == False)
        .scalar()
    ) or 0

    now = datetime.utcnow()
    recent_start = now - timedelta(days=7)
    prev_start = now - timedelta(days=14)

    recent_avg = (
        db.session.query(func.avg(ChatHistory.sentiment_score))
        .filter(ChatHistory.user_id == user_id)
        .filter(ChatHistory.role == "user")
        .filter(ChatHistory.sentiment_score.isnot(None))
        .filter(ChatHistory.timestamp >= recent_start)
        .scalar()
    )

    prev_avg = (
        db.session.query(func.avg(ChatHistory.sentiment_score))
        .filter(ChatHistory.user_id == user_id)
        .filter(ChatHistory.role == "user")
        .filter(ChatHistory.sentiment_score.isnot(None))
        .filter(ChatHistory.timestamp >= prev_start)
        .filter(ChatHistory.timestamp < recent_start)
        .scalar()
    )

    recent_avg = float(recent_avg) if recent_avg is not None else 0.0
    prev_avg = float(prev_avg) if prev_avg is not None else 0.0
    avg_trend = recent_avg - prev_avg

    def score_change_for(test_type: str) -> int:
        earliest = (
            db.session.query(AssessmentResult)
            .filter(AssessmentResult.user_id == user_id, AssessmentResult.type == test_type)
            .order_by(AssessmentResult.created_at.asc())
            .first()
        )
        latest = (
            db.session.query(AssessmentResult)
            .filter(AssessmentResult.user_id == user_id, AssessmentResult.type == test_type)
            .order_by(AssessmentResult.created_at.desc())
            .first()
        )
        if not earliest or not latest:
            return 0
        return int(latest.score) - int(earliest.score)

    phq9_change = score_change_for("PHQ9")
    gad7_change = score_change_for("GAD7")
    assessment_change = phq9_change if phq9_change != 0 else gad7_change

    data = {
        "sessions": int(sessions_used),
        "avg_trend": round(avg_trend, 3),
        "assessment_change": int(assessment_change),
    }

    return render_template("evaluation/j3.html", data=data)


@chatbot.route("/evaluation/j3/timeline.png")
@login_required
def j3_timeline_chart():
    uid = current_user.id

    sess = (
        db.session.query(
            func.strftime("%Y-%W", ChatSession.created_at).label("wk"),
            func.count(ChatSession.id)
        )
        .filter(ChatSession.user_id == uid)
        .group_by("wk").order_by("wk")
        .all()
    )
    sess_map = {wk: int(c) for wk, c in sess}

    sent = (
        db.session.query(
            func.strftime("%Y-%W", ChatHistory.timestamp).label("wk"),
            func.avg(ChatHistory.sentiment_score)
        )
        .filter(ChatHistory.user_id == uid)
        .filter(ChatHistory.role == "user")
        .filter(ChatHistory.sentiment_score.isnot(None))
        .group_by("wk").order_by("wk")
        .all()
    )
    sent_map = {wk: float(a) for wk, a in sent if a is not None}

    weeks = sorted(set(sess_map.keys()) | set(sent_map.keys()))
    weeks = weeks[-12:]  # keep readable

    plt.figure(figsize=(9, 4))
    if not weeks:
        plt.text(0.5, 0.5, "No data available yet", ha="center", va="center")
        plt.axis("off")
        buf = fig_to_png_response()
        plt.close()
        return send_file(buf, mimetype="image/png")

    sess_y = [sess_map.get(w, 0) for w in weeks]
    sent_y = [sent_map.get(w, float("nan")) for w in weeks]

    plt.plot(weeks, sess_y, marker="o", label="Sessions/Week")
    plt.plot(weeks, sent_y, marker="o", label="Avg Sentiment/Week")
    plt.title("Engagement vs Sentiment Trend (Weekly)")
    plt.xticks(rotation=30)
    plt.grid(True, alpha=0.3)
    plt.legend()

    buf = fig_to_png_response()
    plt.close()
    return send_file(buf, mimetype="image/png")

def _is_admin_user() -> bool:
    return bool(
        getattr(current_user, "is_authenticated", False)
        and getattr(current_user, "is_admin", False)
    )

    # Option 2 (better): add user.is_admin boolean in User model
@chatbot.route("/evaluation/label", methods=["GET"])
@login_required
def label_messages_page():
    limit = request.args.get("limit", 60, type=int)
    only_unlabeled = request.args.get("only_unlabeled", 0, type=int) == 1

    q = (
        ChatHistory.query
        .filter(ChatHistory.user_id == current_user.id)   # ✅ IMPORTANT
        .filter(ChatHistory.role == "user")
        .order_by(ChatHistory.timestamp.desc())
    )

    if only_unlabeled:
        q = q.filter(ChatHistory.human_label.is_(None))

    rows = q.limit(limit).all()

    total_labeled = (
        ChatHistory.query
        .filter(
            ChatHistory.user_id == current_user.id,
            ChatHistory.role == "user",
        ChatHistory.human_label.isnot(None))        
        .count()
    )

    total_messages = (
        ChatHistory.query
        .filter(
            ChatHistory.user_id == current_user.id,
            ChatHistory.role == "user",
        )
        .count()
    )

    return render_template(
        "evaluation/label_messages.html",
        rows=rows,
        limit=limit,
        only_unlabeled=only_unlabeled,
        total_labeled=total_labeled,
        progress_done=total_labeled,
        progress_total=total_messages,
    )

@chatbot.route("/evaluation/label/save", methods=["POST"])
@login_required
def save_label():
    data = request.get_json(force=True) or {}
    row_id = int(data.get("id") or 0)
    label = (data.get("label") or "").strip().lower()

    if label not in {"negative", "neutral", "positive"}:
        return jsonify({"ok": False, "error": "Invalid label"}), 400

    row = (
        ChatHistory.query
        .filter(
            ChatHistory.id == row_id,
            ChatHistory.user_id == current_user.id,   # ✅ must match GET
            ChatHistory.role == "user",
        )
        .first()
    )

    if not row:
        return jsonify({"ok": False, "error": "Message not found"}), 404

    row.human_label = label
    row.is_human_labeled = True
    # ✅ Also update any EvalDatasetItem rows that reference this ChatHistory row
    try:
        # EvalDatasetItem has column sentiment_gt (added via ALTER TABLE)
        EvalDatasetItem.query.filter(EvalDatasetItem.chat_history_id == row.id).update(
            {"sentiment_gt": label}, synchronize_session=False
        )
    except Exception:
        # If column/table not present, ignore
        pass

    db.session.commit()

    return jsonify({"ok": True, "id": row.id, "human_label": row.human_label})

import random
def _pick_random_mindfulness():
    # mindfulness_exercises is an object/dict-like with key "mindfulness_exercises"
    items = getattr(mindfulness_exercises, "mindfulness_exercises", None) or mindfulness_exercises.get("mindfulness_exercises")
    ex = random.choice(items)
    return ex["title"], ex.get("description", ""), ex["file_name"]


@chatbot.route("/evaluation/dataset/<int:dataset_id>/export.csv", methods=["GET"])
@login_required
def export_eval_dataset_csv(dataset_id: int):
    
    ds = EvalDataset.query.filter_by(id=dataset_id, created_by=current_user.id).first_or_404()

    # get rows in dataset
    rows = (
        db.session.query(ChatHistory)
        .join(EvalDatasetItem, EvalDatasetItem.chat_history_id == ChatHistory.id)
        .filter(EvalDatasetItem.dataset_id == ds.id)
        .order_by(ChatHistory.timestamp.asc())
        .all()
    )

    sio = StringIO()
    writer = csv.writer(sio)

    writer.writerow([
        "dataset_id", "dataset_name", "dataset_frozen",
        "chat_history_id", "timestamp", "user_id", "session_id",
        "message", "predicted_label", "human_label"
    ])

    for r in rows:
        writer.writerow([
            ds.id, ds.name, int(ds.is_frozen),
            r.id,
            r.timestamp.isoformat() if r.timestamp else "",
            r.user_id,
            r.session_id,
            (r.content or "").replace("\n", " ").strip(),
            r.sentiment_label,
            r.human_label,
        ])

    csv_bytes = sio.getvalue().encode("utf-8")
    filename = f"j1_ground_truth_dataset_{ds.id}.csv"

    return Response(
        csv_bytes,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
from sqlalchemy.exc import IntegrityError


@chatbot.route("/evaluation/dataset/create", methods=["POST"])
@login_required
def create_eval_dataset():
    # ✅ Option A: any logged-in user can create THEIR OWN dataset
    data = request.form or request.get_json(silent=True) or {}

    name = (data.get("name") or "J1 Ground Truth Set").strip()
    note = (data.get("note") or "Manual sentiment labels for J1 evaluation").strip()
    freeze_now = str(data.get("freeze_now") or "0") in {"1", "true", "True", "on"}
    target_n = int(data.get("n") or 90)
    target_n = max(15, min(target_n, 1000))

    # ✅ only THIS user's labeled messages
    labeled = (
        ChatHistory.query
        .filter(ChatHistory.user_id == current_user.id)
        .filter(ChatHistory.role == "user")
        .filter(ChatHistory.human_label.isnot(None))
        .order_by(ChatHistory.timestamp.desc())
        .all()
    )

    if not labeled:
        return jsonify({"ok": False, "error": "No labeled user messages found yet."}), 400

    buckets = {"negative": [], "neutral": [], "positive": []}
    for r in labeled:
        lab = (r.human_label or "").strip().lower()
        if lab in buckets:
            buckets[lab].append(r)

    non_empty = [k for k, v in buckets.items() if v]
    if not non_empty:
        return jsonify({"ok": False, "error": "No valid labels found (negative/neutral/positive)."}), 400

    balanced = (str(data.get("balanced") or "1") in {"1", "true", "True", "on"})

    selected_rows = []
    if balanced and len(non_empty) >= 2:
        per_class = target_n // 3
        remainder = target_n % 3

        import random
        for lab in ["negative", "neutral", "positive"]:
            pool = buckets[lab]
            take = per_class + (1 if remainder > 0 else 0)
            if remainder > 0:
                remainder -= 1
            if pool:
                take = min(take, len(pool))
                selected_rows.extend(random.sample(pool, k=take))

        if len(selected_rows) < target_n:
            selected_ids = {x.id for x in selected_rows}
            rest = [x for x in labeled if x.id not in selected_ids]
            need = min(target_n - len(selected_rows), len(rest))
            if need > 0:
                selected_rows.extend(rest[:need])
    else:
        selected_rows = labeled[:target_n]

    ds = EvalDataset(
        name=name[:80],
        created_at=datetime.utcnow(),
        created_by=current_user.id,     # ✅ owner
        is_frozen=bool(freeze_now),
        note=note[:255] if note else None
    )
    db.session.add(ds)
    db.session.flush()

    from sqlalchemy.exc import IntegrityError
    added, skipped = 0, 0

    for r in selected_rows:
        db.session.add(EvalDatasetItem(dataset_id=ds.id, chat_history_id=r.id))
        try:
            db.session.flush()
            added += 1
        except IntegrityError:
            db.session.rollback()
            db.session.add(ds)
            skipped += 1

    db.session.commit()

    counts = {"negative": 0, "neutral": 0, "positive": 0}
    for r in selected_rows:
        lab = (r.human_label or "").strip().lower()
        if lab in counts:
            counts[lab] += 1

    return jsonify({
        "ok": True,
        "dataset_id": ds.id,
        "name": ds.name,
        "is_frozen": ds.is_frozen,
        "target_n": target_n,
        "selected": len(selected_rows),
        "added": added,
        "skipped": skipped,
        "class_counts": counts
    })
from flask import redirect, url_for, request
from flask_login import login_required, current_user
from datetime import datetime
from ChatbotWebsite import db
from ChatbotWebsite.models import ChatHistory

# =========================================================
# Saved Insights (Save button in chat) + Privacy & Data Controls
# =========================================================

from sqlalchemy.exc import IntegrityError


def _cutoff_from_window(window: str) -> datetime:
    """window: '1h', '1d', '1w', '1m' (default 1m)."""
    w = (window or "").strip().lower()
    now = datetime.utcnow()
    if w == "1h":
        return now - timedelta(hours=1)
    if w == "1d":
        return now - timedelta(days=1)
    if w == "1w":
        return now - timedelta(weeks=1)
    if w == "1m":
        return now - timedelta(days=30)
    return now - timedelta(days=30)


# ---------------------------------
# Saved Insights
# ---------------------------------
@chatbot.route("/saved_insights/add", methods=["POST"])
@login_required
def add_saved_insight():
    """Save a bot reply (or any text) as a short snippet for the user.

    Supports:
      - message_id (ChatMessage.id) ✅ preferred (assistant ChatMessage)
      - chat_history_id (ChatHistory.id) (legacy)
      - content (direct text override)
    """
    from ChatbotWebsite.models import SavedInsight

    # Support both form-encoded POSTs (legacy) and JSON POSTs (AJAX)
    payload = {}
    if request.is_json:
        payload = request.get_json(silent=True) or {}

    message_id = (payload.get("message_id") if payload else None) or request.form.get("message_id", type=int)
    chat_history_id = (payload.get("chat_history_id") if payload else None) or request.form.get("chat_history_id", type=int)
    content = ((payload.get("content") if payload else None) or request.form.get("content") or "").strip()

    m = None  # ChatMessage
    h = None  # ChatHistory
    session_id = None

    # ✅ Preferred: save from ChatMessage (usually the assistant message bubble)
    if message_id:
        m = ChatMessage.query.filter_by(id=message_id, user_id=current_user.id).first()
        if not m:
            if request.is_json:
                return jsonify({"ok": False, "error": "Message not found"}), 404
            flash("Message not found.", "warning")
            return redirect(request.referrer or url_for("chatbot.chat"))

        session_id = getattr(m, "session_id", None)

        # if no override content, save the message text
        if not content:
            content = (getattr(m, "message", None) or "").strip()

    # ✅ Legacy: save from ChatHistory row
    elif chat_history_id:
        h = ChatHistory.query.filter_by(id=chat_history_id, user_id=current_user.id).first()
        if not h:
            if request.is_json:
                return jsonify({"ok": False, "error": "Message not found"}), 404
            flash("Message not found.", "warning")
            return redirect(request.referrer or url_for("chatbot.chat"))

        session_id = getattr(h, "session_id", None)

        if not content:
            content = (getattr(h, "content", None) or "").strip()

    if not content:
        if request.is_json:
            return jsonify({"ok": False, "error": "Nothing to save"}), 400
        flash("Nothing to save.", "warning")
        return redirect(request.referrer or url_for("chatbot.chat"))

    si = SavedInsight(
        user_id=current_user.id,
        session_id=session_id,
        chat_history_id=(h.id if h else None),
        content=content[:4000],
    )
    db.session.add(si)
    db.session.commit()

    if request.is_json:
        return jsonify({"ok": True, "id": si.id})

    flash("Saved to insights.", "success")
    return redirect(request.referrer or url_for("chatbot.saved_insights"))


# Backward-compatible alias: some JS calls /save_insight
@chatbot.route("/save_insight", methods=["POST"])
@login_required
def save_insight_alias():
    return add_saved_insight()
@chatbot.route("/saved_insights", methods=["GET"])
@login_required
def saved_insights():
    from ChatbotWebsite.models import SavedInsight

    items = (
        SavedInsight.query
        .filter_by(user_id=current_user.id)
        .order_by(SavedInsight.created_at.desc())
        .limit(250)
        .all()
    )
    return render_template("saved_insights.html", title="Saved Insights", items=items)


@chatbot.route("/saved_insights/<int:item_id>/delete", methods=["POST"])
@login_required
def delete_saved_insight(item_id: int):
    from ChatbotWebsite.models import SavedInsight

    item = SavedInsight.query.filter_by(id=item_id, user_id=current_user.id).first_or_404()
    db.session.delete(item)
    db.session.commit()
    flash("Deleted.", "info")
    return redirect(url_for("chatbot.saved_insights"))


# ---------------------------------
# Privacy & Data Controls
# ---------------------------------
@chatbot.route("/privacy", methods=["GET"])
@login_required
def privacy_page():
    sessions = (ChatSession.query
                .filter(ChatSession.user_id == current_user.id,
                        ChatSession.is_archived == False)
                .order_by(ChatSession.updated_at.desc(), ChatSession.id.desc())
                .all())

    return render_template("privacy.html",
                           title="Privacy & Data Controls",
                           sessions=sessions)
    
    
@chatbot.route("/privacy/delete_chats_older_than", methods=["POST"])
@login_required
def delete_chats_older_than():
    """
    Deletes WHOLE sessions whose last update is older than the selected window,
    and deletes all session-linked rows safely.
    """
    window = (request.form.get("window") or "1m").strip().lower()
    cutoff = _cutoff_from_window(window)
    uid = current_user.id

    try:
        # ✅ sessions older than cutoff
        old_session_ids = [
            sid for (sid,) in db.session.query(ChatSession.id)
            .filter(
                ChatSession.user_id == uid,
                (ChatSession.updated_at <= cutoff) | (ChatSession.created_at <= cutoff),
            )
            .all()
        ]

        if not old_session_ids:
            flash("No old sessions found for that window.", "info")
            return redirect(url_for("chatbot.privacy_page"))

        # ----- Delete session-linked tables FIRST -----
        UserFeedback.query.filter(UserFeedback.session_id.in_(old_session_ids)).delete(synchronize_session=False)
        DistortionEvent.query.filter(DistortionEvent.session_id.in_(old_session_ids)).delete(synchronize_session=False)
        UserEmotionEvent.query.filter(UserEmotionEvent.session_id.in_(old_session_ids)).delete(synchronize_session=False)
        SavedInsight.query.filter(SavedInsight.session_id.in_(old_session_ids)).delete(synchronize_session=False)

        # ----- ChatMessage + labels -----
        msg_ids = [
            mid for (mid,) in db.session.query(ChatMessage.id)
            .filter(ChatMessage.session_id.in_(old_session_ids))
            .all()
        ]
        if msg_ids:
            MessageLabel.query.filter(MessageLabel.message_id.in_(msg_ids)).delete(synchronize_session=False)
        ChatMessage.query.filter(ChatMessage.session_id.in_(old_session_ids)).delete(synchronize_session=False)

        # ----- ChatHistory + anything that references chat_history -----
        hist_ids = [
            hid for (hid,) in db.session.query(ChatHistory.id)
            .filter(ChatHistory.session_id.in_(old_session_ids))
            .all()
        ]

        # ✅ Known FK child: EvalDatasetItem.chat_history_id
        try:
            from ChatbotWebsite.models import EvalDatasetItem
            if hist_ids:
                EvalDatasetItem.query.filter(EvalDatasetItem.chat_history_id.in_(hist_ids)) \
                    .delete(synchronize_session=False)
        except Exception:
            pass

        ChatHistory.query.filter(ChatHistory.session_id.in_(old_session_ids)).delete(synchronize_session=False)

        # ----- Finally delete sessions -----
        deleted_sessions = (ChatSession.query
                            .filter(ChatSession.user_id == uid, ChatSession.id.in_(old_session_ids))
                            .delete(synchronize_session=False))

        db.session.commit()
        flash(f"Deleted {deleted_sessions} old sessions (older than {window}).", "success")

    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("delete_chats_older_than failed")
        flash(f"Delete failed: {e}", "danger")

    return redirect(url_for("chatbot.privacy_page"))


@chatbot.route("/privacy/delete_journals_older_than", methods=["POST"])
@login_required
def delete_journals_older_than():
    window = (request.form.get("window") or "1m").strip().lower()
    cutoff = _cutoff_from_window(window)

    try:
        q = Journal.query.filter(Journal.user_id == current_user.id).filter(Journal.timestamp >= cutoff)
        count = q.count()
        q.delete(synchronize_session=False)
        db.session.commit()
        flash(f"Deleted {count} journal entries from the last {window}.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Delete failed: {e}", "danger")

    return redirect(url_for("chatbot.privacy_page"))


@chatbot.route("/privacy/delete_moods_older_than", methods=["POST"])
@login_required
def delete_moods_older_than():
    window = (request.form.get("window") or "1m").strip().lower()
    cutoff = _cutoff_from_window(window)

    try:
        q = MoodEntry.query.filter(MoodEntry.user_id == current_user.id).filter(MoodEntry.timestamp >= cutoff)
        count = q.count()
        q.delete(synchronize_session=False)
        db.session.commit()
        flash(f"Deleted {count} mood logs from the last {window}.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Delete failed: {e}", "danger")

    return redirect(url_for("chatbot.privacy_page"))


from io import BytesIO
from datetime import datetime
from flask import send_file
from flask_login import login_required, current_user
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter

@chatbot.route("/privacy/export_my_data", methods=["POST"])
@login_required
def export_my_data():
    """Download a PDF export of user data (summary + small samples)."""

    # ---- Safe import SavedInsight (optional model) ----
    SavedInsightModel = None
    try:
        from ChatbotWebsite.models import SavedInsight as SavedInsightModel
    except Exception:
        SavedInsightModel = None

    # ---- Counts ----
    sessions_n = ChatSession.query.filter_by(user_id=current_user.id).count()
    chats_n = ChatHistory.query.filter_by(user_id=current_user.id).count()
    moods_n = MoodEntry.query.filter_by(user_id=current_user.id).count()
    journals_n = Journal.query.filter_by(user_id=current_user.id).count()

    insights_n = 0
    if SavedInsightModel is not None:
        insights_n = SavedInsightModel.query.filter_by(user_id=current_user.id).count()

    # ---- Samples (real data, not empty) ----
    recent_sessions = (
        ChatSession.query
        .filter_by(user_id=current_user.id, is_archived=False)
        .order_by(ChatSession.updated_at.desc())
        .limit(5)
        .all()
    )

    recent_insights = []
    if SavedInsightModel is not None:
        recent_insights = (
            SavedInsightModel.query
            .filter_by(user_id=current_user.id)
            .order_by(SavedInsightModel.created_at.desc())
            .limit(10)
            .all()
        )

    # ---- PDF ----
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    w, h = letter

    def new_page(font_size=11):
        """Start a new page and reset Y and font."""
        c.showPage()
        c.setFont("Helvetica", font_size)
        return h - 60

    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, h - 60, "LUMORA - Data Export (Summary)")

    c.setFont("Helvetica", 11)
    y = h - 95

    lines = [
        f"User: {current_user.username} (ID: {current_user.id})",
        f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        f"Chat sessions: {sessions_n}",
        f"Chat history rows: {chats_n}",
        f"Mood logs: {moods_n}",
        f"Journal entries: {journals_n}",
        f"Saved insights: {insights_n}",
        "",
        "Note: This PDF contains a summary for academic demonstration only.",
        "",
    ]

    for line in lines:
        c.drawString(50, y, line)
        y -= 16
        if y < 80:
            y = new_page(font_size=11)

    # ---- Recent sessions ----
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, "Recent chat sessions (latest 5)")
    y -= 18
    c.setFont("Helvetica", 10)

    if not recent_sessions:
        c.drawString(55, y, "(No chat sessions yet)")
        y -= 14
    else:
        for s in recent_sessions:
            title = (s.title or "New Chat").strip()
            ts2 = s.updated_at.strftime("%Y-%m-%d %H:%M") if s.updated_at else ""
            c.drawString(55, y, f"- [{ts2}] {title}")
            y -= 14
            if y < 80:
                y = new_page(font_size=10)

    y -= 12
    if y < 100:
        y = new_page(font_size=10)

    # ---- Recent saved insights ----
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, "Saved insights (latest 10)")
    y -= 18
    c.setFont("Helvetica", 10)

    if not recent_insights:
        c.drawString(55, y, "(No saved insights yet)")
        y -= 14
    else:
        for si in recent_insights:
            snippet = (getattr(si, "content", "") or "").strip().replace("\n", " ")
            if len(snippet) > 110:
                snippet = snippet[:110] + "…"
            ts3 = ""
            if getattr(si, "created_at", None):
                ts3 = si.created_at.strftime("%Y-%m-%d %H:%M")
            c.drawString(55, y, f"- [{ts3}] {snippet}")
            y -= 14
            if y < 80:
                y = new_page(font_size=10)

    c.save()
    buf.seek(0)

    return send_file(
        buf,
        mimetype="application/pdf",
        as_attachment=True,
        download_name="lumora_data_export.pdf",
    )
@chatbot.route("/chat/session/<int:session_id>/star", methods=["POST"])
@login_required
def toggle_star_session(session_id):
    s = ChatSession.query.filter_by(id=session_id, user_id=current_user.id).first_or_404()
    s.is_starred = not bool(s.is_starred)
    db.session.commit()
    return redirect(url_for("chatbot.chat", session=session_id))


@chatbot.route("/chat/session/<int:session_id>/rename", methods=["POST"])
@login_required
def rename_session(session_id):
    s = ChatSession.query.filter_by(id=session_id, user_id=current_user.id).first_or_404()
    title = (request.form.get("title") or "").strip()
    if not title:
        flash("Title cannot be empty.", "warning")
        return redirect(url_for("chatbot.chat", session=session_id))
    s.title = title[:120]
    s.updated_at = datetime.utcnow()
    db.session.commit()
    flash("Chat renamed.", "success")
    return redirect(url_for("chatbot.chat", session=session_id))

@chatbot.route("/chat/session/<int:session_id>/delete", methods=["POST"])
@login_required
def delete_session(session_id):
    s = ChatSession.query.filter_by(id=session_id, user_id=current_user.id).first_or_404()

    try:
        msg_ids = [mid for (mid,) in db.session.query(ChatMessage.id).filter(ChatMessage.session_id == s.id).all()]
        if msg_ids:
            MessageLabel.query.filter(MessageLabel.message_id.in_(msg_ids)).delete(synchronize_session=False)
            ChatMessage.query.filter(ChatMessage.id.in_(msg_ids)).delete(synchronize_session=False)

        SavedInsight.query.filter(SavedInsight.session_id == s.id).update(
            {"session_id": None}, synchronize_session=False
        )

        UserFeedback.query.filter(UserFeedback.session_id == s.id).delete(synchronize_session=False)
        UserEmotionEvent.query.filter(UserEmotionEvent.session_id == s.id).delete(synchronize_session=False)
        DistortionEvent.query.filter(DistortionEvent.session_id == s.id).delete(synchronize_session=False)

        db.session.delete(s)
        db.session.commit()
        flash("Chat session deleted.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Delete failed: {e}", "danger")

    return redirect(url_for("chatbot.chat"))
from flask import request, jsonify, url_for

from flask import request, jsonify, url_for
@chatbot.route("/mindfulness/get_audio", methods=["POST"])
def mindfulness_get_audio():
    data = request.get_json() or {}
    title_raw = (data.get("title") or "").strip()
    title = title_raw.lower()

    # Files are inside: ChatbotWebsite/static/mindfulness/
    # We return a URL served by our custom route /mindfulness/audio/<filename>
    AUDIO_MAP = {
        "mountain": ("Mountain Meditation", "8:12", "mountain_meditation.mp3"),
        "breathing": ("Breathing Retraining", "10:45", "breathing_retraining.mp3"),
        "body": ("Body Scan Meditation", "4:01", "body_scan_meditation.mp3"),
        "rain": ("Rain & Thunder Sounds", "9:37", "rain_and_thunder_sounds.mp3"),
        "thunder": ("Rain & Thunder Sounds", "9:37", "rain_and_thunder_sounds.mp3"),
    }

    # ✅ fuzzy match so "(10:45)" doesn't break it
    for key, (nice_title, duration, filename) in AUDIO_MAP.items():
        if key in title:
            audio_url = url_for("chatbot.serve_mindfulness_audio", filename=filename)


            return jsonify(
                ok=True,
                audio_url=audio_url,
                actions={
                    "audio_url": audio_url,
                    "audio_title": nice_title,
                    "audio_desc": f"Duration: {duration}",
                    "title": nice_title,
                    "duration": duration,
                },
            )

    return jsonify(ok=False, error=f"Exercise not found: {title_raw}")


from flask import send_from_directory, abort
import os

@chatbot.route("/mindfulness/audio/<path:filename>")
def serve_mindfulness_audio(filename):
    """
    Serve mindfulness audio files from ChatbotWebsite/static/mindfulness/.

    Frontend should request: /mindfulness/audio/<filename>
    """
    mindfulness_dir = os.path.join(current_app.root_path, "static", "mindfulness")

    # security: allow only mp3
    if not filename.lower().endswith(".mp3"):
        abort(404)

    file_path = os.path.join(mindfulness_dir, filename)
    if not os.path.exists(file_path):
        current_app.logger.warning(f"[AUDIO] File not found: {file_path}")
        abort(404)

    return send_from_directory(mindfulness_dir, filename, mimetype="audio/mpeg", as_attachment=False)
