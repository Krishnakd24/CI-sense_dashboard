import os
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[2] / ".env")
from cryptography.fernet import Fernet
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg://cisense:cisense@localhost:5432/cisense")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000").rstrip("/")
PUBLIC_API_URL = os.getenv("PUBLIC_API_URL", "http://localhost:8000").rstrip("/")
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "true").lower() == "true"
ADMIN_IDS = set(os.getenv("ADMIN_GITHUB_IDS", "").split(","))
def cipher(): return Fernet(os.environ["ENCRYPTION_KEY"].encode())
