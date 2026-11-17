import json

import pytest

from webhooks.events import emit_event
from webhooks.models import WebhookDelivery, WebhookEvent


@pytest.mark.django_db
def test_emit_event_queues_a_delivery_per_active_endpoint_only(northstar, endpoint, inactive_endpoint):
    event = emit_event(northstar, WebhookEvent.TYPE_TIMESHEET_APPROVED, {'x': 1})

    deliveries = WebhookDelivery.objects.filter(event=event)
    assert [d.endpoint for d in deliveries] == [endpoint]
    body = json.loads(event.body)
    assert body['id'] == event.id
    assert body['schema_version'] == '1'


@pytest.mark.django_db
def test_emit_event_without_endpoints_writes_nothing(northstar):
    assert emit_event(northstar, WebhookEvent.TYPE_TIMESHEET_APPROVED, {}) is None
    assert not WebhookEvent.objects.exists()


@pytest.mark.django_db
def test_approving_an_entry_emits_exactly_one_event(admin_client, endpoint, submitted_entry):
    url = f'/api/timesheets/{submitted_entry.id}/'

    assert admin_client.patch(url, {'status': 'approved'}).status_code == 200
    # Re-approving, removing race condition
    assert admin_client.patch(url, {'status': 'approved'}).status_code == 200

    event = WebhookEvent.objects.get()
    assert event.type == WebhookEvent.TYPE_TIMESHEET_APPROVED
    assert json.loads(event.body)['data']['timesheet_entry']['id'] == submitted_entry.id
    assert WebhookDelivery.objects.filter(event=event, endpoint=endpoint).count() == 1


@pytest.mark.django_db
def test_rejecting_an_entry_emits_nothing(admin_client, endpoint, submitted_entry):
    resp = admin_client.patch(
        f'/api/timesheets/{submitted_entry.id}/',
        {'status': 'rejected', 'rejection_reason': 'Wrong day'},
    )
    assert resp.status_code == 200
    assert not WebhookEvent.objects.exists()
