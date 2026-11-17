"""Outbound webhook delivery: the worker half.

Run by the ``deliver_webhooks`` worker, never on the request path.

Delivery guarantee: at-least-once. Consumers dedupe on ``webhook-id``, which
is the event id and is stable across every retry and every endpoint.
"""
import http.client
import logging
import random
import socket
import ssl
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import timedelta
from urllib.parse import urlsplit

from django.db import transaction
from django.utils import timezone

from .models import WebhookAttempt, WebhookDelivery, WebhookEvent
from .signing import sign

logger = logging.getLogger(__name__)

USER_AGENT = 'YunoJuno-Webhooks/1'
REQUEST_TIMEOUT_SECONDS = 10
RESPONSE_BODY_LIMIT = 2048

RETRY_SCHEDULE = [
    timedelta(seconds=30),
    timedelta(minutes=2),
    timedelta(minutes=10),
    timedelta(minutes=30),
    timedelta(hours=2),
    timedelta(hours=6),
    timedelta(hours=12),
]
MAX_ATTEMPTS = len(RETRY_SCHEDULE) + 1
JITTER = 0.1


@dataclass
class HttpResult:
    status: int | None
    body: str = ''
    error: str = ''


def http_post(url: str, body: str, headers: dict) -> HttpResult:
    """Generic HTTP POST request."""
    req = urllib.request.Request(url, data=body.encode(), headers=headers, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
            return HttpResult(status=resp.status, body=resp.read(RESPONSE_BODY_LIMIT).decode(errors='replace'))
    except urllib.error.HTTPError as exc:
        # The server answered with a non-2xx
        return HttpResult(status=exc.code, body=exc.read(RESPONSE_BODY_LIMIT).decode(errors='replace'))
    except urllib.error.URLError as exc:
        # Failed before any response
        return HttpResult(status=None, error=describe_network_error(exc.reason, url))
    except (OSError, http.client.HTTPException) as exc:
        # Failed after connecting, while reading the response.
        return HttpResult(status=None, error=describe_network_error(exc, url))
    except Exception:
        logger.exception('Unexpected error delivering webhook to %s', url)
        return HttpResult(status=None, error='Unexpected error while sending the request')


def describe_network_error(exc: BaseException, url: str) -> str:
    """A customer-facing reason for a request that got no HTTP response.

    Shown in the delivery log, so it says what happened in plain terms rather
    than exposing Python exceptions.
    """
    host = urlsplit(url).hostname
    if isinstance(exc, socket.gaierror):
        return f'Could not resolve host {host}'
    if isinstance(exc, ConnectionRefusedError):
        return f'Connection refused by {host}'
    if isinstance(exc, TimeoutError):
        return f'No response within {REQUEST_TIMEOUT_SECONDS}s'
    if isinstance(exc, ssl.SSLCertVerificationError):
        return f'TLS certificate verification failed for {host}'
    if isinstance(exc, ssl.SSLError):
        return f'TLS handshake with {host} failed'
    if isinstance(exc, ConnectionResetError):
        return 'Connection closed by the server before it responded'
    if isinstance(exc, http.client.HTTPException):
        return 'The server sent an invalid HTTP response'
    if isinstance(exc, OSError) and exc.strerror:
        return f'Network error: {exc.strerror}'
    return 'Network error'


def build_headers(event: WebhookEvent, secret: str, timestamp: int) -> dict:
    return {
        'Content-Type': 'application/json',
        'User-Agent': USER_AGENT,
        'webhook-id': event.id,
        'webhook-timestamp': str(timestamp),
        'webhook-signature': sign(secret, event.id, timestamp, event.body),
    }


def next_retry_delay(attempts_made: int) -> timedelta:
    base = RETRY_SCHEDULE[attempts_made - 1]
    return base * random.uniform(1 - JITTER, 1 + JITTER)


def attempt_delivery(delivery: WebhookDelivery) -> WebhookAttempt:
    """Make one HTTP attempt and move the delivery to its next state."""
    event = delivery.event
    endpoint = delivery.endpoint
    attempt_number = delivery.attempt_count + 1

    # Fresh timestamp per attempt
    timestamp = int(time.time())
    started = time.monotonic()
    result = http_post(endpoint.url, event.body, build_headers(event, endpoint.secret, timestamp))
    duration_ms = int((time.monotonic() - started) * 1000)

    attempt = WebhookAttempt.objects.create(
        delivery=delivery,
        attempt_number=attempt_number,
        attempted_at=timezone.now(),
        response_status=result.status,
        response_body=result.body[:RESPONSE_BODY_LIMIT],
        error=result.error,
        duration_ms=duration_ms,
    )

    delivery.attempt_count = attempt_number
    if attempt.succeeded:
        delivery.status = WebhookDelivery.STATUS_SUCCEEDED
        delivery.next_attempt_at = None
    elif attempt_number >= MAX_ATTEMPTS:
        delivery.status = WebhookDelivery.STATUS_DEAD
        delivery.next_attempt_at = None
    else:
        delivery.next_attempt_at = timezone.now() + next_retry_delay(attempt_number)
    delivery.save(update_fields=['attempt_count', 'status', 'next_attempt_at', 'updated_at'])
    return attempt


def deliver_due(limit: int = 20) -> int:
    """Attempt up to ``limit``. Returns how many were attempted."""
    attempted = 0
    for _ in range(limit):
        with transaction.atomic():
            delivery = (
                WebhookDelivery.objects
                .select_for_update(skip_locked=True, of=('self',))
                .select_related('event', 'endpoint')
                .filter(status=WebhookDelivery.STATUS_PENDING, next_attempt_at__lte=timezone.now())
                .order_by('next_attempt_at')
                .first()
            )
            if delivery is None:
                break
            if not delivery.endpoint.active:
                # Customer has disabled endpoint since event has fired. Drop event here
                delivery.status = WebhookDelivery.STATUS_DEAD
                delivery.next_attempt_at = None
                delivery.save(update_fields=['status', 'next_attempt_at', 'updated_at'])
                continue
            attempt_delivery(delivery)
            attempted += 1
    return attempted
