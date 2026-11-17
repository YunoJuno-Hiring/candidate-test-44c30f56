import base64
import hashlib
import hmac

from webhooks.signing import SECRET_PREFIX, generate_secret, sign

SECRET = SECRET_PREFIX + base64.b64encode(b'k' * 32).decode()


def test_signature_matches_standard_webhooks_scheme():
    expected = hmac.new(b'k' * 32, b'evt_1.1700000000.{"a":1}', hashlib.sha256).digest()
    assert sign(SECRET, 'evt_1', 1700000000, '{"a":1}') == 'v1,' + base64.b64encode(expected).decode()


def test_signature_changes_when_body_is_tampered_with():
    assert sign(SECRET, 'evt_1', 1700000000, '{"a":1}') != sign(SECRET, 'evt_1', 1700000000, '{"a":2}')


def test_generated_secrets_are_prefixed_and_unique():
    a, b = generate_secret(), generate_secret()
    assert a.startswith(SECRET_PREFIX)
    assert a != b
