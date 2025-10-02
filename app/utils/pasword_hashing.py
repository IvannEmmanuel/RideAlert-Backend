from passlib.context import CryptContext
import bcrypt as _bcrypt

# Use bcrypt_sha256 to safely handle passwords >72 bytes (bcrypt limit),
# keep bcrypt for backward compatibility with existing hashes.
pwd_context = CryptContext(
    schemes=["bcrypt_sha256", "bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    bcrypt_prefixes = ("$2a$", "$2b$", "$2y$")

    # Manual path for legacy bcrypt hashes to avoid passlib backend issues on some platforms
    if isinstance(hashed_password, str) and hashed_password.startswith(bcrypt_prefixes):
        try:
            pb = plain_password.encode("utf-8")
            if len(pb) > 72:
                pb = pb[:72]
            return _bcrypt.checkpw(pb, hashed_password.encode("utf-8"))
        except Exception:
            # Fall back to passlib if direct bcrypt fails for any reason
            pass

    # Normal path (bcrypt_sha256 and others)
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except ValueError:
        # As a last resort, try passlib with truncated secret
        try:
            pb = plain_password.encode("utf-8")
            if len(pb) > 72:
                return pwd_context.verify(pb[:72], hashed_password)
        except Exception:
            pass
        raise


def needs_update(hashed_password: str) -> bool:
    """Return True if the stored hash should be upgraded to the preferred scheme (bcrypt_sha256)."""
    bcrypt_prefixes = ("$2a$", "$2b$", "$2y$")
    try:
        # Force-upgrade legacy bcrypt hashes
        if isinstance(hashed_password, str) and hashed_password.startswith(bcrypt_prefixes):
            return True
        return pwd_context.needs_update(hashed_password)
    except Exception:
        # Unknown/legacy format: treat as upgradeable
        return True
