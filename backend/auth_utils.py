
import base64
import hashlib
import hmac


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify the PBKDF2 format used by the synthetic seed."""
    try:
        algorithm, iterations, salt_b64, digest_b64 = stored_hash.split("$")

        if algorithm != "pbkdf2_sha256":
            return False

        rounds = int(iterations)
        if rounds < 100_000 or rounds > 2_000_000:
            return False

        salt = base64.b64decode(salt_b64, validate=True)
        expected = base64.b64decode(digest_b64, validate=True)

        actual = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            rounds,
        )

        return hmac.compare_digest(actual, expected)

    except (ValueError, TypeError):
        return False
