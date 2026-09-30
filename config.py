"""Central configuration.

Secrets and deployment settings come from ENVIRONMENT VARIABLES (never hard-code them).
Experiment design constants live here too so they are visible in one place and are
snapshotted into every session row for reproducibility.
"""
import os
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

APP_VERSION = "1.1.0"


def _int(name, default):
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def database_url():
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url and os.environ.get("RENDER"):
        raise RuntimeError("DATABASE_URL must be set on Render (SQLite would lose data on redeploy).")
    if not url:
        # Local-development fallback ONLY. Production must set DATABASE_URL (PostgreSQL).
        return "sqlite:///local_dev.db"
    # Render may provide postgres:// or postgresql://, while some environments
    # already provide an explicit driver. This project uses psycopg 3 everywhere.
    if url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url[len("postgres://"):]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    elif url.startswith("postgresql+psycopg2://"):
        url = "postgresql+psycopg://" + url[len("postgresql+psycopg2://"):]
    return url


class Config:
    SQLALCHEMY_DATABASE_URI = database_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}
    SECRET_KEY = os.environ.get("SECRET_KEY")  # validated in app.py
    MAX_CONTENT_LENGTH = 512 * 1024
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "0") == "1"


ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")

# ---- Experiment parameters (defaults follow Millisecond's Color Matching manual) ----
EXPERIMENT = {
    "colors": ["blue", "green", "red", "yellow", "white"],
    "color_hex": {  # display colours on black background; edit if you calibrate differently
        "blue": "#2f5bff", "green": "#00b83c", "red": "#e60000",
        "yellow": "#ffe600", "white": "#ffffff",
    },
    "square_ms": 500, "isi_ms": 250, "iti_ms": 1000, "practice_feedback_ms": 500,
    "keys": {"yes": "y", "no": "n", "pm": "z"},
    "n_trials": 62,
    "target_positions": [10, 20, 30, 40, 50, 60],
    "n_target_match": 3,
    "n_filler_match": 28,
    "n_practice_trials": 6,
    # Millisecond default is 10 minutes (600 s). Set BREAK_SECONDS=5 for local testing.
    "break_seconds": _int("BREAK_SECONDS", 600),
    # 0 = repeat recall until all 6 correct (Millisecond behaviour).
    "max_recall_attempts": _int("MAX_RECALL_ATTEMPTS", 0),
}
REQUIRE_PARTICIPANT_ID = os.environ.get("REQUIRE_PARTICIPANT_ID", "1") == "1"
