"""
PALIMPSEST Configuration Module
Centralized configuration for Flask, SQLite database, token budgets, and LLM services.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file from project root
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


class Config:
    """Base application configuration."""
    SECRET_KEY = os.getenv("SECRET_KEY", "palimpsest-default-dev-secret-key-2026")
    
    # Instance directory & SQLite database path (Windows-safe absolute posix URI)
    INSTANCE_DIR = BASE_DIR / "instance"
    INSTANCE_DIR.mkdir(exist_ok=True)
    
    env_db = os.getenv("DATABASE_URI", "").strip()
    if env_db and not env_db.startswith("sqlite:///instance"):
        SQLALCHEMY_DATABASE_URI = env_db
    else:
        db_path = (INSTANCE_DIR / "palimpsest.db").resolve().as_posix()
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{db_path}"

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # LLM & Classifier Settings
    LLM_PROVIDER = os.getenv("LLM_PROVIDER", "rule_based").lower()
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
    DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "gpt-4o-mini")
    FORCE_FALLBACK = os.getenv("FORCE_FALLBACK", "false").lower() == "true"
    
    # Token Budget and Memory Thresholds
    DEFAULT_TOKEN_BUDGET = int(os.getenv("DEFAULT_TOKEN_BUDGET", "2048"))
    VERBATIM_THRESHOLD = float(os.getenv("VERBATIM_THRESHOLD", "0.75"))
    DISCARD_THRESHOLD = float(os.getenv("DISCARD_THRESHOLD", "0.30"))
    
    # Upload limits: 5MB text/markdown files
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024
    ALLOWED_EXTENSIONS = {"txt", "md", "markdown", "json", "csv"}

    @classmethod
    def is_llm_configured(cls) -> bool:
        """Return True if an actual external LLM is configured and not forced to fallback."""
        if cls.FORCE_FALLBACK:
            return False
        if cls.LLM_PROVIDER == "openai" and cls.OPENAI_API_KEY:
            return True
        if cls.LLM_PROVIDER == "anthropic" and cls.ANTHROPIC_API_KEY:
            return True
        return False


class TestConfig(Config):
    """Configuration for automated test suite using in-memory SQLite database."""
    TESTING = True
    # In-memory SQLite with static pool so connections share the memory DB during testing
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    FORCE_FALLBACK = True
    LLM_PROVIDER = "rule_based"
