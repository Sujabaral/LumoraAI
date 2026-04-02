# ChatbotWebsite/community/__init__.py
from flask import Blueprint

community = Blueprint(
    "community",
    __name__,
    template_folder="templates",
)

from . import routes  # noqa