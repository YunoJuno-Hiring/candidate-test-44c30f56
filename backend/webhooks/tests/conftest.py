import pytest

from webhooks.models import WebhookEndpoint


@pytest.fixture
def endpoint(northstar):
    return WebhookEndpoint.objects.create(company=northstar, url='https://example.test/hook')


@pytest.fixture
def inactive_endpoint(northstar):
    return WebhookEndpoint.objects.create(company=northstar, url='https://disabled.test/hook', active=False)
