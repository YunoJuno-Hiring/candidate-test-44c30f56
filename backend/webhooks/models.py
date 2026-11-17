import uuid

from django.db import models

from accounts.models import Company

from .signing import generate_secret


def generate_event_id() -> str:
    return f'evt_{uuid.uuid4().hex}'


class WebhookEndpoint(models.Model):
    """A company-configured destination for outbound webhook events."""

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='webhook_endpoints')
    url = models.URLField(max_length=2048)
    description = models.CharField(max_length=255, blank=True)
    secret = models.CharField(max_length=128, default=generate_secret)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.url} ({self.company.name})'


class WebhookEvent(models.Model):
    """An event that has occured.

    ``body`` is the exact payload sent.
    """

    TYPE_TIMESHEET_APPROVED = 'timesheet.approved'
    TYPE_TEST = 'webhook.test'

    id = models.CharField(primary_key=True, max_length=40, default=generate_event_id, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='webhook_events')
    type = models.CharField(max_length=64)
    body = models.TextField()
    created_at = models.DateTimeField()

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.type} {self.id}'


class WebhookDelivery(models.Model):
    """One event fanned out to one endpoint."""

    STATUS_PENDING = 'pending'
    STATUS_SUCCEEDED = 'succeeded'
    STATUS_DEAD = 'dead'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_SUCCEEDED, 'Succeeded'),
        (STATUS_DEAD, 'Dead'),
    ]

    event = models.ForeignKey(WebhookEvent, on_delete=models.CASCADE, related_name='deliveries')
    endpoint = models.ForeignKey(WebhookEndpoint, on_delete=models.CASCADE, related_name='deliveries')
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING)
    attempt_count = models.PositiveSmallIntegerField(default=0)
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(fields=['event', 'endpoint'], name='unique_delivery_per_event_endpoint'),
        ]
        indexes = [
            models.Index(fields=['status', 'next_attempt_at'], name='webhook_delivery_due_idx'),
        ]

    def __str__(self):
        return f'{self.event_id} → {self.endpoint.url} ({self.status})'


class WebhookAttempt(models.Model):
    """A single HTTP attempt for a delivery: the delivery log the UI shows."""

    delivery = models.ForeignKey(WebhookDelivery, on_delete=models.CASCADE, related_name='attempts')
    attempt_number = models.PositiveSmallIntegerField()
    attempted_at = models.DateTimeField()
    response_status = models.PositiveSmallIntegerField(null=True, blank=True)
    response_body = models.TextField(blank=True)
    error = models.TextField(blank=True)
    duration_ms = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ['-attempt_number']
        constraints = [
            models.UniqueConstraint(fields=['delivery', 'attempt_number'], name='unique_attempt_number'),
        ]

    @property
    def succeeded(self) -> bool:
        return self.response_status is not None and 200 <= self.response_status < 300
