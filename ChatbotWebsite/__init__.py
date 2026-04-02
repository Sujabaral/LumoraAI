import os
from dotenv import load_dotenv
from flask import Flask, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import LoginManager, current_user
from flask_mail import Mail
from flask_admin import Admin
from flask_admin.contrib.sqla import ModelView
from flask_migrate import Migrate
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.exc import OperationalError
from sqlalchemy import inspect

from flask_wtf.csrf import CSRFProtect

# ✅ ADD THESE imports (for SQLite FK pragma)
from sqlalchemy import event
from sqlalchemy.engine import Engine

from ChatbotWebsite.config import Config

# ------------------- Initialize extensions globally -------------------
db = SQLAlchemy()
migrate = Migrate()
bcrypt = Bcrypt()
mail = Mail()
login_manager = LoginManager()
login_manager.login_view = "users.login"
login_manager.login_message_category = "info"

csrf = CSRFProtect()


# ✅ ADD THIS: enforce SQLite foreign keys (critical for correct delete behavior)
@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    try:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
    except Exception:
        pass


# ------------------- Scheduler helper -------------------
def _run_with_app_context(app, func):
    with app.app_context():
        func()


# ------------------- Default admin creator (MIGRATION-SAFE) -------------------
def ensure_default_admin(app):
    """
    Create default admin user only when:
    - 'user' table exists
    - schema is ready (no missing columns)
    - admin user doesn't already exist
    """
    with app.app_context():
        from ChatbotWebsite.models import User  # local import

        try:
            inspector = inspect(db.engine)
            if "user" not in inspector.get_table_names():
                return  # migrations not applied yet

            try:
                existing_admin = User.query.filter_by(username="admin").first()
            except OperationalError:
                db.session.rollback()
                return  # schema not ready yet (migration pending)

            if existing_admin:
                return

            # Create admin
            temp_admin = User(
                username="admin",
                email="admin@example.com",
                is_admin=True,  # ✅ required for admin panel access control
                is_phi=True     # keep if you use it in your app
            )
            temp_admin.password = bcrypt.generate_password_hash("admin123").decode("utf-8")
            db.session.add(temp_admin)
            db.session.commit()
            print("✅ Admin created: admin / admin123")

        except Exception as e:
            db.session.rollback()
            print(f"⚠️ Skipped admin creation: {e}")


# ------------------- App Factory -------------------
def create_app(config_class=Config):
    app = Flask(__name__, instance_relative_config=True)

    # ------------------- Load config -------------------
    load_dotenv()
    app.config.from_object(config_class)

    # ✅ Public base URL EARLY (used by email links)
    app.config["PUBLIC_BASE_URL"] = os.environ.get(
        "PUBLIC_BASE_URL",
        "http://127.0.0.1:5000"
    ).rstrip("/")

    # ✅ Stable secret key
    app.config["SECRET_KEY"] = os.getenv(
        "SECRET_KEY",
        app.config.get("SECRET_KEY", "fallbacksecret")
    )

    # ✅ Disable CSRF validation globally (OK for demo)
    app.config["WTF_CSRF_ENABLED"] = False

    os.makedirs(app.instance_path, exist_ok=True)
    default_db_path = os.path.join(app.instance_path, "lumora.db")
    default_db_uri = "sqlite:///" + default_db_path

    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
        "SQLALCHEMY_DATABASE_URI",
        default_db_uri
    )

    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["TEMPLATES_AUTO_RELOAD"] = True
    app.debug = True
    app.jinja_env.auto_reload = True

    # ------------------- Cache-busting for static files -------------------
    @app.context_processor
    def override_url_for():
        import time

        def dated_url_for(endpoint, **values):
            if endpoint == "static":
                values["v"] = int(time.time())
            return url_for(endpoint, **values)

        return dict(url_for=dated_url_for)

    # ------------------- Initialize extensions -------------------
    db.init_app(app)
    migrate.init_app(app, db)
    bcrypt.init_app(app)
    mail.init_app(app)
    login_manager.init_app(app)

    # ✅ Keep this so {{ csrf_token() }} exists in templates
    csrf.init_app(app)

    # ------------------- Import models AFTER db.init_app -------------------
    from ChatbotWebsite.models import User  # noqa: F401
    from ChatbotWebsite import models as models_module

    # ------------------- Login loader -------------------
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # ------------------- Register blueprints -------------------
    from ChatbotWebsite.main.routes import main
    from ChatbotWebsite.users.routes import users
    from ChatbotWebsite.errors.handlers import errors
    from ChatbotWebsite.journal.routes import journals
    from ChatbotWebsite.chatbot.routes import chatbot

    app.register_blueprint(main)
    app.register_blueprint(users)
    app.register_blueprint(chatbot)
    app.register_blueprint(errors)
    app.register_blueprint(journals)

    # ------------------- Flask-Admin (ADMIN ONLY) -------------------
    from ChatbotWebsite.admin import init_admin
    init_admin(app)
    # ------------------- Create default admin user (safe) -------------------
    ensure_default_admin(app)

    # ------------------- APScheduler (REMINDERS) -------------------
    if not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        from ChatbotWebsite.reminders import run_booking_reminders

        scheduler = BackgroundScheduler(daemon=True)
        scheduler.add_job(
            func=lambda: _run_with_app_context(app, run_booking_reminders),
            trigger=IntervalTrigger(minutes=5),
            id="booking_reminders",
            replace_existing=True,
        )
        scheduler.start()
        print("✅ Reminder scheduler started")

    # ------------------- Community blueprint -------------------
    from ChatbotWebsite.community import community as community_bp
    app.register_blueprint(community_bp)

    return app

