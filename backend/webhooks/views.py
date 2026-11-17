from rest_framework import status
from rest_framework.pagination import CursorPagination
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import WebhookEndpoint
from .serializers import (
    WebhookDeliverySerializer,
    WebhookEndpointSerializer,
    WebhookEndpointWithSecretSerializer,
)
from .events import send_test_event


class DeliveryLogPagination(CursorPagination):
    """Cursor, not page numbers: new deliveries are inserted at the top while
    someone is paging, which would shift ?page=N and duplicate or skip rows.
    ``-id`` is unique and increases with creation, so cursors stay stable."""

    page_size = 20
    ordering = '-id'


class IsCompanyAdmin(BasePermission):
    message = 'Only company admins can manage webhook endpoints.'

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and hasattr(request.user, 'company_admin'))


class CompanyEndpointMixin:
    """Every lookup is scoped to the admin's own company. Another company's
    endpoint is a 404, not a 403. We don't want to leak across companies."""

    permission_classes = [IsCompanyAdmin]

    def get_queryset(self):
        return WebhookEndpoint.objects.filter(company=self.request.user.company_admin.company)

    def get_endpoint(self, pk):
        return self.get_queryset().filter(pk=pk).first()


def not_found():
    return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)


class WebhookEndpointListCreateView(CompanyEndpointMixin, APIView):
    def get(self, request):
        return Response(WebhookEndpointSerializer(self.get_queryset(), many=True).data)

    def post(self, request):
        serializer = WebhookEndpointWithSecretSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        endpoint = serializer.save(company=request.user.company_admin.company)
        return Response(WebhookEndpointWithSecretSerializer(endpoint).data, status=status.HTTP_201_CREATED)


class WebhookEndpointDetailView(CompanyEndpointMixin, APIView):
    def get(self, request, pk):
        endpoint = self.get_endpoint(pk)
        if endpoint is None:
            return not_found()
        return Response(WebhookEndpointSerializer(endpoint).data)

    def patch(self, request, pk):
        endpoint = self.get_endpoint(pk)
        if endpoint is None:
            return not_found()
        serializer = WebhookEndpointSerializer(endpoint, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def delete(self, request, pk):
        endpoint = self.get_endpoint(pk)
        if endpoint is None:
            return not_found()
        endpoint.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class WebhookEndpointSecretView(CompanyEndpointMixin, APIView):
    def get(self, request, pk):
        endpoint = self.get_endpoint(pk)
        if endpoint is None:
            return not_found()
        return Response({'secret': endpoint.secret})


class WebhookEndpointTestView(CompanyEndpointMixin, APIView):
    def post(self, request, pk):
        endpoint = self.get_endpoint(pk)
        if endpoint is None:
            return not_found()
        if not endpoint.active:
            return Response(
                {'detail': 'Enable the endpoint before sending a test event.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        delivery = send_test_event(endpoint)
        # Status 202 because we have only queued the event.
        return Response(WebhookDeliverySerializer(delivery).data, status=status.HTTP_202_ACCEPTED)


class WebhookEndpointDeliveriesView(CompanyEndpointMixin, APIView):
    def get(self, request, pk):
        endpoint = self.get_endpoint(pk)
        if endpoint is None:
            return not_found()
        deliveries = endpoint.deliveries.select_related('event').prefetch_related('attempts')
        paginator = DeliveryLogPagination()
        page = paginator.paginate_queryset(deliveries, request, view=self)
        return paginator.get_paginated_response(WebhookDeliverySerializer(page, many=True).data)
