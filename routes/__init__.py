"""
PALIMPSEST Routes Package
Exports API blueprint and UI view blueprint.
"""

from routes.api import api_bp
from routes.views import views_bp

__all__ = ["api_bp", "views_bp"]
