from passlib.context import CryptContext
import hashlib
import warnings

# Suppress bcrypt version warnings
warnings.filterwarnings("ignore", category=UserWarning, module="passlib")

# Support both bcrypt_sha256 (for existing hashes) and bcrypt (for new hashes)
# This ensures backward compatibility while fixing the bcrypt version issues
pwd_context = CryptContext(
    schemes=["bcrypt", "bcrypt_sha256"],
    deprecated="auto",
    # Use bcrypt for new hashes, but still verify bcrypt_sha256
    default="bcrypt"
)


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
    try:
        truncated_password = _truncate_password(plain_password)
        return pwd_context.verify(truncated_password, hashed_password)
    except Exception as e:
        # Log the error for debugging
        print(f"Password verification error: {e}")
        print(
            f"Hash format: {hashed_password[:20]}..." if hashed_password else "No hash provided")

        # Try with a fallback context that only supports bcrypt_sha256
        try:
            fallback_context = CryptContext(
                schemes=["bcrypt_sha256"], deprecated="auto")
            return fallback_context.verify(plain_password, hashed_password)
        except Exception as fallback_e:
            print(f"Fallback verification also failed: {fallback_e}")
            return False
