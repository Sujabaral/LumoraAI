# train_app_min.py
from __future__ import annotations

import os
from flask import Flask
from ChatbotWebsite import db

def create_train_app() -> Flask:
    """
    Minimal app context for training scripts.
    Avoids importing blueprints/routes.
    Ensures SQLite path exists (instance folder) so SQLAlchemy can open DB.
    """
    root = os.path.dirname(os.path.abspath(__file__))   # project root
    instance_path = os.path.join(root, "instance")
    os.makedirs(instance_path, exist_ok=True)

    app = Flask(__name__, instance_path=instance_path)
    app.config["SECRET_KEY"] = "train-only"

    # ✅ Force SQLite DB to your real file (pick the one you actually use)
    # You have: instance/lumora.db
    db_path = os.path.join(instance_path, "lumora.db")
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + db_path
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    db.init_app(app)
    return app