from datetime import timedelta

import pytest
from django.utils import timezone

from webhooks import delivery as delivery_module
from webhooks.delivery import MAX_ATTEMPTS, HttpResult, deliver_due
from webhooks.events import send_test_event
from webhooks.models import WebhookDelivery


@pytest.fixture
def fake_http(monkeypatch):
    """Replace the real HTTP call; tests set ``fake_http.result`` and inspect ``fake_http.calls``."""

    class FakeHttp:
        result = HttpResult(status=200, body='ok')
        calls = []

        def __call__(self, url, body, headers):
            self.calls.append({'url': url, 'body': body, 'headers': headers})
            return self.result

    fake = FakeHttp()
    fake.calls = []
    monkeypatch.setattr(delivery_module, 'http_post', fake)
    return fake


@pytest.mark.django_db
def test_2xx_marks_delivery_succeeded(fake_http, endpoint):
    delivery = send_test_event(endpoint)

    assert deliver_due() == 1

    delivery.refresh_from_db()
    assert delivery.status == WebhookDelivery.STATUS_SUCCEEDED
    assert delivery.next_attempt_at is None
    attempt = delivery.attempts.get()
    assert (attempt.attempt_number, attempt.response_status) == (1, 200)
    headers = fake_http.calls[0]['headers']
    assert headers['webhook-id'] == delivery.event_id
    assert headers['webhook-signature'].startswith('v1,')


@pytest.mark.django_db
def test_failure_schedules_a_retry_with_jitter(fake_http, endpoint):
    fake_http.result = HttpResult(status=500, body='boom')
    delivery = send_test_event(endpoint)

    before = timezone.now()
    deliver_due()

    delivery.refresh_from_db()
    assert delivery.status == WebhookDelivery.STATUS_PENDING
    assert delivery.attempt_count == 1
    assert before + timedelta(seconds=27) <= delivery.next_attempt_at <= timezone.now() + timedelta(seconds=33)


@pytest.mark.django_db
def test_network_error_is_recorded_on_the_attempt(fake_http, endpoint):
    fake_http.result = HttpResult(status=None, error='Connection refused by example.test')
    delivery = send_test_event(endpoint)

    deliver_due()

    attempt = delivery.attempts.get()
    assert attempt.response_status is None
    assert attempt.error == 'Connection refused by example.test'


@pytest.mark.django_db
def test_final_failed_attempt_marks_delivery_dead(fake_http, endpoint):
    fake_http.result = HttpResult(status=503)
    delivery = send_test_event(endpoint)
    WebhookDelivery.objects.filter(pk=delivery.pk).update(attempt_count=MAX_ATTEMPTS - 1)

    deliver_due()

    delivery.refresh_from_db()
    assert delivery.status == WebhookDelivery.STATUS_DEAD
    assert delivery.attempt_count == MAX_ATTEMPTS
    assert delivery.next_attempt_at is None


@pytest.mark.django_db
def test_event_id_is_stable_across_retries(fake_http, endpoint):
    fake_http.result = HttpResult(status=500)
    delivery = send_test_event(endpoint)

    deliver_due()
    WebhookDelivery.objects.filter(pk=delivery.pk).update(next_attempt_at=timezone.now())
    deliver_due()

    ids = {call['headers']['webhook-id'] for call in fake_http.calls}
    assert len(fake_http.calls) == 2
    assert ids == {delivery.event_id}


@pytest.mark.django_db
def test_disabled_endpoint_is_dropped_without_sending(fake_http, endpoint):
    delivery = send_test_event(endpoint)
    endpoint.active = False
    endpoint.save()

    assert deliver_due() == 0

    delivery.refresh_from_db()
    assert delivery.status == WebhookDelivery.STATUS_DEAD
    assert fake_http.calls == []


@pytest.mark.django_db
def test_deliveries_not_yet_due_are_skipped(fake_http, endpoint):
    delivery = send_test_event(endpoint)
    WebhookDelivery.objects.filter(pk=delivery.pk).update(next_attempt_at=timezone.now() + timedelta(minutes=5))

    assert deliver_due() == 0
    assert fake_http.calls == []
