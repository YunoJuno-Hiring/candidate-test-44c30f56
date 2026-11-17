"""Outbound webhook event creation: the request-path half.

Emission (``emit_event``) runs inside the caller's DB transaction and only
writes rows: the outbox pattern. Nothing here touches the network; the
``deliver_webhooks`` worker picks the rows up (see ``delivery.py``).
"""
import json

from django.db import transaction
from django.utils import timezone

from .models import WebhookDelivery, WebhookEndpoint, WebhookEvent

SCHEMA_VERSION = '1'


def _serialise(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(',', ':'))


def _create_event(company, event_type: str, data: dict) -> WebhookEvent:
    event = WebhookEvent(company=company, type=event_type, created_at=timezone.now())
    event.body = _serialise({
        'id': event.id,
        'type': event_type,
        'schema_version': SCHEMA_VERSION,
        'created_at': event.created_at.isoformat().replace('+00:00', 'Z'),
        'data': data,
    })
    event.save()
    return event


def emit_event(company, event_type: str, data: dict) -> WebhookEvent | None:
    """Record an event and queue a delivery for each active endpoint."""
    endpoints = list(WebhookEndpoint.objects.filter(company=company, active=True))
    if not endpoints:
        return None

    event = _create_event(company, event_type, data)
    now = timezone.now()
    WebhookDelivery.objects.bulk_create(
        [WebhookDelivery(event=event, endpoint=ep, next_attempt_at=now) for ep in endpoints]
    )
    return event


@transaction.atomic
def send_test_event(endpoint: WebhookEndpoint) -> WebhookDelivery:
    """Queue a ``webhook.test`` event to a single endpoint, via the real pipeline."""
    event = _create_event(endpoint.company, WebhookEvent.TYPE_TEST, {
        'endpoint': {'id': endpoint.id, 'url': endpoint.url},
        'message': 'This is a test event from YunoJuno.',
    })
    return WebhookDelivery.objects.create(event=event, endpoint=endpoint, next_attempt_at=timezone.now())


def timesheet_approved_data(entry) -> dict:
    contract = entry.contract
    return {
        'timesheet_entry': {
            'id': entry.id,
            'date': entry.date.isoformat(),
            'hours': str(entry.hours),
            'status': entry.status,
        },
        'contract': {
            'id': contract.id,
            'daily_rate': str(contract.daily_rate),
            'freelancer': {'id': contract.freelancer_id, 'name': contract.freelancer.name},
        },
    }
