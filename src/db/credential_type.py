"""SQLAlchemy TypeDecorator for transparent Fernet encryption of credential columns.

Usage:
    from src.db.credential_type import EncryptedStr
    column = Column(EncryptedStr, nullable=True)

The column is stored as opaque ciphertext in Postgres (still a String/Text column —
no migration needed when adding encryption to an existing String column, but existing
plaintext rows must be re-encrypted via a one-time migration script).

If CREDENTIAL_ENCRYPTION_KEY is not set, values pass through unencrypted with a
warning. This preserves backward compatibility during rollout.
"""

import logging
from typing import Optional

from sqlalchemy import String
from sqlalchemy.types import TypeDecorator

logger = logging.getLogger(__name__)

_fernet = None
_key_missing_warned = False


def _get_fernet():
    global _fernet, _key_missing_warned
    if _fernet is not None:
        return _fernet
    try:
        from src.config import settings
        key = settings.credential_encryption_key
        if not key:
            if not _key_missing_warned:
                logger.warning(
                    "CREDENTIAL_ENCRYPTION_KEY not set — credential columns stored unencrypted. "
                    "Generate a key with: python -c \"from cryptography.fernet import Fernet; "
                    "print(Fernet.generate_key().decode())\""
                )
                _key_missing_warned = True
            return None
        from cryptography.fernet import Fernet
        _fernet = Fernet(key.encode())
        return _fernet
    except Exception as e:
        logger.error("credential_type: failed to initialize Fernet — %s", e)
        return None


class EncryptedStr(TypeDecorator):
    """Transparent Fernet-encrypted String column.

    Stores ciphertext in the DB; returns plaintext in Python.
    Falls back to plaintext storage when CREDENTIAL_ENCRYPTION_KEY is not set.
    """
    impl = String
    cache_ok = True

    def process_bind_param(self, value: Optional[str], dialect) -> Optional[str]:
        """Encrypt on write."""
        if value is None or value == "":
            return value
        f = _get_fernet()
        if f is None:
            return value
        return f.encrypt(value.encode()).decode()

    def process_result_value(self, value: Optional[str], dialect) -> Optional[str]:
        """Decrypt on read."""
        if value is None or value == "":
            return value
        f = _get_fernet()
        if f is None:
            return value
        try:
            return f.decrypt(value.encode()).decode()
        except Exception:
            # Value may be plaintext (pre-encryption data) — return as-is
            return value
