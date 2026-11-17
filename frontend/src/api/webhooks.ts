import { api, CursorPage, WebhookDelivery, WebhookEndpoint, WebhookEndpointWithSecret } from './client'

export function fetchWebhookEndpoints(): Promise<WebhookEndpoint[]> {
  return api.get('/api/webhook-endpoints/')
}

export function createWebhookEndpoint(data: { url: string; description: string }): Promise<WebhookEndpointWithSecret> {
  return api.post('/api/webhook-endpoints/', data)
}

export function updateWebhookEndpoint(
  id: number,
  data: Partial<Pick<WebhookEndpoint, 'url' | 'description' | 'active'>>
): Promise<WebhookEndpoint> {
  return api.patch(`/api/webhook-endpoints/${id}/`, data)
}

export function deleteWebhookEndpoint(id: number): Promise<void> {
  return api.delete(`/api/webhook-endpoints/${id}/`)
}

export function revealWebhookSecret(id: number): Promise<{ secret: string }> {
  return api.get(`/api/webhook-endpoints/${id}/secret/`)
}

export function sendWebhookTest(id: number): Promise<WebhookDelivery> {
  return api.post(`/api/webhook-endpoints/${id}/test/`, {})
}

export interface DeliveryPage {
  results: WebhookDelivery[]
  newerCursor: string | null
  olderCursor: string | null
}

// DRF builds next/previous as absolute URLs from the request's Host, which
// behind the dev proxy is the internal backend:8000. Keep only the cursor.
function cursorFrom(url: string | null): string | null {
  return url ? new URL(url).searchParams.get('cursor') : null
}

export async function fetchWebhookDeliveries(id: number, cursor: string | null): Promise<DeliveryPage> {
  const qs = cursor ? `?cursor=${encodeURIComponent(cursor)}` : ''
  const page: CursorPage<WebhookDelivery> = await api.get(`/api/webhook-endpoints/${id}/deliveries/${qs}`)
  return {
    results: page.results,
    newerCursor: cursorFrom(page.previous),
    olderCursor: cursorFrom(page.next),
  }
}
