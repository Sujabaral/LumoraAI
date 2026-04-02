import os

basedir = os.path.abspath(os.path.dirname(__file__))

class Config:
    DEBUG = True
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev_secret_key")
    SQLALCHEMY_DATABASE_URI = "sqlite:///instance/lumora.db"

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    LUMORA_DEBUG_BRAIN=1
# config.py
    SECURITY_PASSWORD_SALT = "email-confirm-salt"


    # Mail
    MAIL_SERVER = "smtp.gmail.com"
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USE_SSL = False

    MAIL_USERNAME = os.environ.get("MAIL_USERNAME")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD")

    SECURITY_PASSWORD_SALT = os.environ.get("SECURITY_PASSWORD_SALT", "your-salt-key")
