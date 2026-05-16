"""JWT creation and verification."""
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt

from config import JWT_ALG, JWT_EXPIRE_HOURS, JWT_SECRET


def create_token(username: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRE_HOURS)
    return jwt.encode(
        {"sub": username, "exp": expire},
        JWT_SECRET,
        algorithm=JWT_ALG,
    )


def verify_token(token: str) -> str | None:
    try:
        # Strip "Bearer " prefix if present (defensive handling)
        clean_token = token.split()[-1] if ' ' in token else token
        
        payload = jwt.decode(clean_token, JWT_SECRET, algorithms=[JWT_ALG])
        sub = payload.get("sub")
        return str(sub) if sub else None
    except JWTError as e:
        print(f"Token verification failed: {e}")
        return None
