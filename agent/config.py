"""
SENTINEL Configuration
Loads environment variables from .env for all agent components.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ── MongoDB ────────────────────────────────────────────────────────────────────
MONGODB_CONNECTION_STRING = os.getenv(
    "MONGODB_CONNECTION_STRING", "mongodb://localhost:27017"
)
MONGODB_DATABASE = os.getenv("MONGODB_DATABASE", "sentinel_demo")
QUARANTINE_COLLECTION_SUFFIX = "_quarantine"

# ── Gemini / Google Cloud ──────────────────────────────────────────────────────
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-exp")
GOOGLE_CLOUD_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT", "")
GOOGLE_CLOUD_LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")          # AI Studio fallback
# Approvals
AUTO_APPROVE_SCHEMA_CHANGES = os.getenv("AUTO_APPROVE_SCHEMA_CHANGES", "false").lower() in ("1", "true", "yes")

# ── Arize Phoenix
ARIZE_PHOENIX_API_KEY = os.getenv("ARIZE_PHOENIX_API_KEY")
ARIZE_PHOENIX_SPACE_ID = os.getenv("ARIZE_PHOENIX_SPACE_ID")
ARIZE_PHOENIX_ENDPOINT = os.getenv("ARIZE_PHOENIX_ENDPOINT")

# ── Fivetran
FIVETRAN_API_KEY = os.getenv("FIVETRAN_API_KEY")
FIVETRAN_API_SECRET = os.getenv("FIVETRAN_API_SECRET")

# ── Elastic
ELASTIC_API_KEY = os.getenv("ELASTIC_API_KEY")
ELASTIC_ENDPOINT = os.getenv("ELASTIC_ENDPOINT")

# ── GitLab
GITLAB_TOKEN = os.getenv("GITLAB_TOKEN")
GITLAB_API_URL = os.getenv("GITLAB_API_URL", "https://gitlab.com/api/v4")

# ── Dynatrace
DYNATRACE_TOKEN = os.getenv("DYNATRACE_TOKEN")
DYNATRACE_ENV = os.getenv("DYNATRACE_ENV")

# ── Audit
SENTINEL_AUDIT_LOG = os.getenv("SENTINEL_AUDIT_LOG", "./sentinel_audit.jsonl")
SENTINEL_HMAC_SIGNING_KEY = os.getenv("SENTINEL_HMAC_SIGNING_KEY", "change-me-to-a-real-secret")
