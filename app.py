"""
PALIMPSEST — Transparent, Version-Controlled Context Memory System
Main Application Entry Point (Flask)
"""

import os
from flask import Flask
from config import Config
from models import db
from routes.api import api_bp
from routes.views import views_bp
from sample_data.seed_data import seed_database


def create_app(config_class=Config):
    """Application factory for PALIMPSEST."""
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_class)

    # Initialize extensions
    db.init_app(app)

    # Register Blueprints
    app.register_blueprint(api_bp)
    app.register_blueprint(views_bp)

    # Create tables and seed default data
    with app.app_context():
        db.create_all()
        seed_database()

    return app


app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print("=" * 65)
    print("PALIMPSEST Context Memory System for Long-Running Agents")
    print(f"* Environment: {app.config.get('ENV', 'development')}")
    print(f"* Database: {app.config['SQLALCHEMY_DATABASE_URI']}")
    print(f"* LLM Provider: {Config.LLM_PROVIDER} ({'API Enabled' if Config.is_llm_configured() else 'Deterministic Rule-Based Fallback'})")
    print(f"* Server listening at: http://127.0.0.1:{port}/")
    print("=" * 65)
    app.run(host="0.0.0.0", port=port, debug=False)
