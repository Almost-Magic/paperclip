"""JWT authentication service for Paperclip."""

from datetime import datetime, timedelta
from typing import Optional
import jwt
import os
import logging

logger = logging.getLogger("paperclip.auth")

# Configuration
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "paperclip-dev-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "1440"))  # 24 hours default


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token.

    Args:
        data: Claims to encode in token (e.g., {"sub": "user_id", "role": "admin"})
        expires_delta: Custom expiration time (default: ACCESS_TOKEN_EXPIRE_MINUTES)

    Returns:
        JWT token string
    """
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire})

    try:
        encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
        logger.info(f"Token created for {data.get('sub', 'unknown')}")
        return encoded_jwt
    except Exception as e:
        logger.error(f"Failed to create token: {e}")
        raise


def verify_token(token: str) -> dict:
    """Verify and decode a JWT token.

    Args:
        token: JWT token string

    Returns:
        Decoded token payload (claims dict)

    Raises:
        jwt.InvalidTokenError: If token is invalid or expired
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        logger.warning(f"Token expired: {token[:20]}...")
        raise ValueError("Token expired")
    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid token: {str(e)[:50]}")
        raise ValueError("Invalid token")


def get_token_from_header(auth_header: Optional[str]) -> Optional[str]:
    """Extract token from Authorization header.

    Args:
        auth_header: Authorization header value (e.g., "Bearer token_here")

    Returns:
        Token string or None
    """
    if not auth_header:
        return None

    parts = auth_header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None

    return parts[1]


# Default test credentials (Phase 2 — TODO: replace with persistent user storage)
TEST_USERS = {
    "admin": {
        "password": os.getenv("ADMIN_PASSWORD", "admin-password"),  # TODO: hash this
        "role": "admin",
        "permissions": ["*"],
    },
    "operator": {
        "password": os.getenv("OPERATOR_PASSWORD", "operator-password"),
        "role": "operator",
        "permissions": ["read", "write"],
    },
    "viewer": {
        "password": os.getenv("VIEWER_PASSWORD", "viewer-password"),
        "role": "viewer",
        "permissions": ["read"],
    },
}


def authenticate_user(username: str, password: str) -> Optional[dict]:
    """Authenticate user and return user info if valid.

    Args:
        username: Username
        password: Password (plaintext for Phase 1, should be hashed in production)

    Returns:
        User info dict or None if authentication fails

    TODO: Replace with database lookup + bcrypt hash verification
    """
    user = TEST_USERS.get(username)
    if not user:
        logger.warning(f"Login attempt for unknown user: {username}")
        return None

    if user["password"] != password:
        logger.warning(f"Failed login for user: {username}")
        return None

    logger.info(f"User authenticated: {username} (role={user['role']})")
    return {
        "username": username,
        "role": user["role"],
        "permissions": user["permissions"],
    }
