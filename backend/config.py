"""Central configuration, read from environment variables (see .env.example)."""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:  # python-dotenv optional
    pass


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "")
    JWT_EXPIRY_HOURS = int(os.getenv("JWT_EXPIRY_HOURS", "8"))
    APP_TZ_OFFSET_MINUTES = int(os.getenv("APP_TZ_OFFSET_MINUTES", "330"))  # IST
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*")
    FORCE_HTTPS = os.getenv("FORCE_HTTPS", "0") == "1"
    # duplicate detection
    DUP_TIME_WINDOW_MIN = int(os.getenv("DUP_TIME_WINDOW_MIN", "180"))
    DUP_MATCH_THRESHOLD = float(os.getenv("DUP_MATCH_THRESHOLD", "0.55"))
    # spam protection
    MAX_REPORTS_PER_USER_PER_HOUR = int(os.getenv("MAX_REPORTS_PER_USER_PER_HOUR", "5"))
    RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "1") == "1"
    # AWS (all optional; nothing is called unless enabled AND credentials exist)
    SNS_ENABLED = os.getenv("SNS_ENABLED", "0") == "1"
    SNS_TOPIC_ARN = os.getenv("SNS_TOPIC_ARN", "")
    AWS_REGION = os.getenv("AWS_REGION", "ap-south-1")
    TESTING = False
