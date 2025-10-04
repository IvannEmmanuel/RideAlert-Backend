from passlib.context import CryptContext
import hashlib

# Use bcrypt instead of bcrypt_sha256 for better compatibility
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _truncate_password(password: str) -> str:
    """Truncate password to 72 bytes to comply with bcrypt limitation"""
    # Convert to bytes and truncate if necessary
    password_bytes = password.encode('utf-8')
    if len(password_bytes) > 72:
        # If password is too long, hash it first to ensure consistent length
        password = hashlib.sha256(password_bytes).hexdigest()
    return password


def hash_password(password: str) -> str:
    truncated_password = _truncate_password(password)
    return pwd_context.hash(truncated_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    truncated_password = _truncate_password(plain_password)
    return pwd_context.verify(truncated_password, hashed_password)
