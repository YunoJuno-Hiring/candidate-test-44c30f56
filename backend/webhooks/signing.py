import base64
import hashlib
import hmac
import secrets

SECRET_PREFIX = 'whsec_'


def generate_secret() -> str:
    return SECRET_PREFIX + base64.b64encode(secrets.token_bytes(32)).decode()


def _key(secret: str) -> bytes:
    return base64.b64decode(secret.removeprefix(SECRET_PREFIX))


def sign(secret: str, msg_id: str, timestamp: int, body: str) -> str:
    """Sign a webhook event and create a HMAC key."""
    signed_content = f'{msg_id}.{timestamp}.{body}'.encode()
    digest = hmac.new(_key(secret), signed_content, hashlib.sha256).digest()
    return 'v1,' + base64.b64encode(digest).decode()
