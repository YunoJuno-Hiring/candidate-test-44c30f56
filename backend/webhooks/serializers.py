from urllib.parse import urlsplit

from rest_framework import serializers

from .models import WebhookAttempt, WebhookDelivery, WebhookEndpoint


class WebhookEndpointSerializer(serializers.ModelSerializer):
    """Endpoint without its secret: used for list, detail and update."""

    # Not serializers.URLField: Django's URLValidator requires a dotted domain,
    # which rejects docker service names like http://webhook-receiver:8027/hook.
    url = serializers.CharField(max_length=2048)

    class Meta:
        model = WebhookEndpoint
        fields = ['id', 'url', 'description', 'active', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_url(self, value):
        parts = urlsplit(value)
        if parts.scheme not in ('http', 'https') or not parts.hostname:
            raise serializers.ValidationError('Enter a valid http(s) URL.')
        return value


class WebhookEndpointWithSecretSerializer(WebhookEndpointSerializer):
    """Only returned on create and from the explicit reveal endpoint, so the
    secret isn't sitting in every list response, browser cache or log line."""

    class Meta(WebhookEndpointSerializer.Meta):
        fields = WebhookEndpointSerializer.Meta.fields + ['secret']
        read_only_fields = WebhookEndpointSerializer.Meta.read_only_fields + ['secret']


class WebhookAttemptSerializer(serializers.ModelSerializer):
    class Meta:
        model = WebhookAttempt
        fields = ['attempt_number', 'attempted_at', 'response_status', 'response_body', 'error', 'duration_ms']


class WebhookDeliverySerializer(serializers.ModelSerializer):
    event_id = serializers.CharField(source='event.id')
    event_type = serializers.CharField(source='event.type')
    attempts = WebhookAttemptSerializer(many=True)

    class Meta:
        model = WebhookDelivery
        fields = [
            'id', 'event_id', 'event_type', 'status', 'attempt_count',
            'next_attempt_at', 'created_at', 'attempts',
        ]
