from django.contrib import admin

from .models import WebhookAttempt, WebhookDelivery, WebhookEndpoint, WebhookEvent


@admin.register(WebhookEndpoint)
class WebhookEndpointAdmin(admin.ModelAdmin):
    list_display = ['url', 'company', 'active', 'created_at']
    list_filter = ['active']


@admin.register(WebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    list_display = ['id', 'type', 'company', 'created_at']
    list_filter = ['type']


class WebhookAttemptInline(admin.TabularInline):
    model = WebhookAttempt
    extra = 0
    readonly_fields = ['attempt_number', 'attempted_at', 'response_status', 'error', 'duration_ms']


@admin.register(WebhookDelivery)
class WebhookDeliveryAdmin(admin.ModelAdmin):
    list_display = ['event', 'endpoint', 'status', 'attempt_count', 'next_attempt_at']
    list_filter = ['status']
    inlines = [WebhookAttemptInline]
