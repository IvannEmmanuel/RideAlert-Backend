from passlib.context import CryptContext

# Use bcrypt_sha256 to safely handle passwords >72 bytes (bcrypt limit),
# keep bcrypt for backward compatibility with existing hashes.
pwd_context = CryptContext(
    schemes=["bcrypt_sha256", "bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except ValueError as e:
        # Workaround for bcrypt 72-byte limit when verifying legacy bcrypt hashes
        # If the stored hash is a bcrypt hash and the password is >72 bytes,
        # truncate to 72 bytes (bcrypt semantics) and verify again.
        bcrypt_prefixes = ("$2a$", "$2b$", "$2y$")
        if isinstance(hashed_password, str) and hashed_password.startswith(bcrypt_prefixes):
            try:
                pb = plain_password.encode("utf-8")
                if len(pb) > 72:
                    return pwd_context.verify(pb[:72], hashed_password)
            except Exception:
                pass
        # Re-raise if not recoverable
        raise


def needs_update(hashed_password: str) -> bool:
    """Return True if the stored hash should be upgraded to the preferred scheme (bcrypt_sha256)."""
    try:
        return pwd_context.needs_update(hashed_password)
    except Exception:
        # Unknown/legacy format: treat as upgradeable
        return True
