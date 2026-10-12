"""Password hashing (bcrypt) + signed session tokens (itsdangerous)."""
import os

import bcrypt
from itsdangerous import BadSignature, URLSafeTimedSerializer

SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")
if SECRET_KEY == "dev-secret-change-me":
    print("⚠️  SECRET_KEY not set — using dev default. Set SECRET_KEY in production!")

_serializer = URLSafeTimedSerializer(SECRET_KEY, salt="sweet-circuit-session")
SESSION_MAX_AGE = 30 * 24 * 3600  # 30 days


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def check_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def make_session(user_id: int) -> str:
    return _serializer.dumps({"uid": user_id})


def read_session(token: str):
    try:
        data = _serializer.loads(token, max_age=SESSION_MAX_AGE)
        return data.get("uid")
    except BadSignature:
        return None
