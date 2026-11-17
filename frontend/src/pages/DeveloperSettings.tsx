import { useState, FormEvent } from 'react'
import { keepPreviousData, useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  fetchWebhookEndpoints,
  createWebhookEndpoint,
  updateWebhookEndpoint,
  deleteWebhookEndpoint,
  revealWebhookSecret,
  sendWebhookTest,
  fetchWebhookDeliveries,
} from '../api/webhooks'
import { ApiError, WebhookDelivery, WebhookEndpoint, WebhookEndpointWithSecret } from '../api/client'
import { StatusBadge } from '../components/StatusBadge'

const ENDPOINTS_KEY = ['webhook-endpoints']
const deliveriesKey = (id: number) => ['webhook-deliveries', id]

// While anything is pending the worker may change it at any moment, so poll;
// once everything has settled, stop.
const DELIVERY_POLL_MS = 2000

function errorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError) {
    const first = Object.values(err.data)[0]
    if (typeof first === 'string') return first
    if (Array.isArray(first) && typeof first[0] === 'string') return first[0]
  }
  return fallback
}

function formatTime(iso: string | null): string {
  return iso ? new Date(iso).toLocaleString() : '—'
}

const inputCls =
  'w-full border border-slate-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500'
const primaryBtn =
  'bg-indigo-600 text-white text-sm px-4 py-2 rounded hover:bg-indigo-700 disabled:opacity-60 disabled:cursor-not-allowed'
const linkBtn = 'text-xs disabled:opacity-50'

function CopyButton({ value }: { value: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <button
      type="button"
      onClick={() => {
        navigator.clipboard.writeText(value).then(() => {
          setCopied(true)
          setTimeout(() => setCopied(false), 1500)
        })
      }}
      className={`${linkBtn} text-indigo-600 hover:text-indigo-800`}
    >
      {copied ? 'Copied' : 'Copy'}
    </button>
  )
}

function NewSecretNotice({ endpoint, onDismiss }: { endpoint: WebhookEndpointWithSecret; onDismiss: () => void }) {
  return (
    <div className="mt-4 bg-green-50 border border-green-200 rounded px-4 py-3 text-sm space-y-2">
      <p className="text-green-800">
        Endpoint saved: <span className="font-mono text-xs">{endpoint.url}</span>
      </p>
      <p className="text-slate-600">
        Use this signing secret to verify the <code className="bg-white px-1 rounded">webhook-signature</code> header.
        You can reveal it again later from the endpoint's details.
      </p>
      <div className="flex items-center gap-3">
        <code className="bg-white border border-green-200 rounded px-2 py-1 text-xs font-mono break-all">
          {endpoint.secret}
        </code>
        <CopyButton value={endpoint.secret} />
      </div>
      <button type="button" onClick={onDismiss} className={`${linkBtn} text-slate-500 hover:text-slate-700`}>
        Dismiss
      </button>
    </div>
  )
}

function AddEndpointForm() {
  const queryClient = useQueryClient()
  const [url, setUrl] = useState('')
  const [description, setDescription] = useState('')
  const [created, setCreated] = useState<WebhookEndpointWithSecret | null>(null)

  const createMutation = useMutation({
    mutationFn: () => createWebhookEndpoint({ url, description }),
    onSuccess: (endpoint) => {
      queryClient.invalidateQueries({ queryKey: ENDPOINTS_KEY })
      setCreated(endpoint)
      setUrl('')
      setDescription('')
    },
  })

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setCreated(null)
    createMutation.mutate()
  }

  return (
    <div className="bg-white border border-slate-200 rounded-lg p-6">
      <h2 className="text-base font-medium text-slate-800 mb-4">Add webhook destination</h2>
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label htmlFor="webhook-url" className="block text-sm font-medium text-slate-700 mb-1">
            Destination URL
          </label>
          <input
            id="webhook-url"
            type="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            required
            placeholder="https://example.com/webhook"
            className={inputCls}
          />
          <p className="text-slate-400 text-xs mt-1">
            For local testing, use{' '}
            <code className="bg-slate-100 px-1 rounded">http://webhook-receiver:8027/hook</code>
          </p>
        </div>
        <div>
          <label htmlFor="webhook-description" className="block text-sm font-medium text-slate-700 mb-1">
            Description <span className="text-slate-400 font-normal">(optional)</span>
          </label>
          <input
            id="webhook-description"
            type="text"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            maxLength={255}
            placeholder="e.g. Finance system"
            className={inputCls}
          />
        </div>
        <button type="submit" disabled={createMutation.isPending} className={primaryBtn}>
          {createMutation.isPending ? 'Saving…' : 'Save endpoint'}
        </button>
      </form>

      {created && <NewSecretNotice endpoint={created} onDismiss={() => setCreated(null)} />}
      {createMutation.isError && (
        <div className="mt-4 bg-red-50 border border-red-200 text-red-700 text-sm rounded px-3 py-2">
          {errorMessage(createMutation.error, 'Failed to save endpoint. Please try again.')}
        </div>
      )}
    </div>
  )
}

function SecretField({ endpointId }: { endpointId: number }) {
  const [secret, setSecret] = useState<string | null>(null)
  const revealMutation = useMutation({
    mutationFn: () => revealWebhookSecret(endpointId),
    onSuccess: (data) => setSecret(data.secret),
  })

  return (
    <div>
      <h3 className="text-xs font-medium text-slate-500 uppercase tracking-wide mb-1">Signing secret</h3>
      {secret ? (
        <div className="flex items-center gap-3">
          <code className="bg-slate-100 rounded px-2 py-1 text-xs font-mono break-all">{secret}</code>
          <CopyButton value={secret} />
          <button type="button" onClick={() => setSecret(null)} className={`${linkBtn} text-slate-500 hover:text-slate-700`}>
            Hide
          </button>
        </div>
      ) : (
        <div className="flex items-center gap-3">
          <code className="bg-slate-100 rounded px-2 py-1 text-xs font-mono text-slate-400">whsec_••••••••••••</code>
          <button
            type="button"
            onClick={() => revealMutation.mutate()}
            disabled={revealMutation.isPending}
            className={`${linkBtn} text-indigo-600 hover:text-indigo-800`}
          >
            {revealMutation.isPending ? 'Revealing…' : 'Reveal'}
          </button>
          {revealMutation.isError && <span className="text-xs text-red-600">Couldn't load secret.</span>}
        </div>
      )}
    </div>
  )
}

function lastResponse(delivery: WebhookDelivery): string {
  const latest = delivery.attempts[0]
  if (!latest) return '—'
  if (latest.response_status !== null) return `HTTP ${latest.response_status}`
  return latest.error || 'No response'
}

function DeliveryRow({ delivery }: { delivery: WebhookDelivery }) {
  const [open, setOpen] = useState(false)
  return (
    <>
      <tr className="hover:bg-slate-50 cursor-pointer" onClick={() => setOpen((o) => !o)}>
        <td className="px-3 py-2">
          <div className="text-slate-700">{delivery.event_type}</div>
          <div className="font-mono text-[11px] text-slate-400">{delivery.event_id}</div>
        </td>
        <td className="px-3 py-2 text-slate-600">{formatTime(delivery.created_at)}</td>
        <td className="px-3 py-2">
          <StatusBadge status={delivery.status} />
        </td>
        <td className="px-3 py-2 text-slate-600">{delivery.attempt_count}</td>
        <td className="px-3 py-2 text-slate-600">{lastResponse(delivery)}</td>
        <td className="px-3 py-2 text-slate-600">
          {delivery.status === 'pending' ? formatTime(delivery.next_attempt_at) : '—'}
        </td>
      </tr>
      {open && (
        <tr className="bg-slate-50">
          <td colSpan={6} className="px-3 py-2">
            {delivery.attempts.length === 0 ? (
              <p className="text-xs text-slate-500">Queued — not attempted yet.</p>
            ) : (
              <ul className="space-y-1 text-xs">
                {delivery.attempts.map((a) => (
                  <li key={a.attempt_number} className="flex gap-4 text-slate-600">
                    <span className="w-16">Attempt {a.attempt_number}</span>
                    <span className="w-40">{formatTime(a.attempted_at)}</span>
                    <span className="w-20">{a.response_status !== null ? `HTTP ${a.response_status}` : 'No response'}</span>
                    <span className="w-16">{a.duration_ms !== null ? `${a.duration_ms} ms` : ''}</span>
                    <span className="flex-1 font-mono text-slate-500 truncate" title={a.error || a.response_body}>
                      {a.error || a.response_body}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </td>
        </tr>
      )}
    </>
  )
}

function DeliveryLog({ endpointId }: { endpointId: number }) {
  // null = newest page. Cursors keep pages stable while new deliveries arrive.
  const [cursor, setCursor] = useState<string | null>(null)
  const deliveriesQuery = useQuery({
    queryKey: [...deliveriesKey(endpointId), cursor],
    queryFn: () => fetchWebhookDeliveries(endpointId, cursor),
    placeholderData: keepPreviousData,
    refetchInterval: (query) =>
      query.state.data?.results.some((d) => d.status === 'pending') ? DELIVERY_POLL_MS : false,
  })
  const page = deliveriesQuery.data

  return (
    <div>
      <h3 className="text-xs font-medium text-slate-500 uppercase tracking-wide mb-2">Recent deliveries</h3>
      {deliveriesQuery.isLoading ? (
        <p className="text-slate-500 text-sm">Loading…</p>
      ) : deliveriesQuery.isError ? (
        <p className="text-red-600 text-sm">Failed to load deliveries.</p>
      ) : !page || page.results.length === 0 ? (
        <p className="text-slate-500 text-sm">No deliveries yet. Send a test event to try it out.</p>
      ) : (
        <>
        <div className="border border-slate-200 rounded overflow-hidden">
          <table className="w-full text-xs">
            <thead className="bg-slate-50 border-b border-slate-200">
              <tr>
                <th className="text-left px-3 py-2 font-medium text-slate-600">Event</th>
                <th className="text-left px-3 py-2 font-medium text-slate-600">Created</th>
                <th className="text-left px-3 py-2 font-medium text-slate-600">Status</th>
                <th className="text-left px-3 py-2 font-medium text-slate-600">Attempts</th>
                <th className="text-left px-3 py-2 font-medium text-slate-600">Last response</th>
                <th className="text-left px-3 py-2 font-medium text-slate-600">Next retry</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {page.results.map((d) => (
                <DeliveryRow key={d.id} delivery={d} />
              ))}
            </tbody>
          </table>
        </div>
        {(page.newerCursor || page.olderCursor || cursor) && (
          <div className="flex items-center justify-between mt-2">
            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={() => setCursor(null)}
                disabled={!cursor}
                className={`${linkBtn} text-slate-600 hover:text-slate-800`}
              >
                Newest
              </button>
              <button
                type="button"
                onClick={() => setCursor(page.newerCursor)}
                disabled={!page.newerCursor}
                className={`${linkBtn} text-slate-600 hover:text-slate-800`}
              >
                ← Newer
              </button>
            </div>
            <button
              type="button"
              onClick={() => setCursor(page.olderCursor)}
              disabled={!page.olderCursor}
              className={`${linkBtn} text-slate-600 hover:text-slate-800`}
            >
              Older →
            </button>
          </div>
        )}
        </>
      )}
    </div>
  )
}

function EditEndpointForm({ endpoint, onDone }: { endpoint: WebhookEndpoint; onDone: () => void }) {
  const queryClient = useQueryClient()
  const [url, setUrl] = useState(endpoint.url)
  const [description, setDescription] = useState(endpoint.description)

  const updateMutation = useMutation({
    mutationFn: () => updateWebhookEndpoint(endpoint.id, { url, description }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ENDPOINTS_KEY })
      onDone()
    },
  })

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        updateMutation.mutate()
      }}
      className="space-y-3"
    >
      <input type="url" value={url} onChange={(e) => setUrl(e.target.value)} required className={inputCls} aria-label="Destination URL" />
      <input
        type="text"
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        maxLength={255}
        placeholder="Description"
        className={inputCls}
        aria-label="Description"
      />
      <div className="flex items-center gap-3">
        <button type="submit" disabled={updateMutation.isPending} className={primaryBtn}>
          {updateMutation.isPending ? 'Saving…' : 'Save'}
        </button>
        <button type="button" onClick={onDone} className="text-sm text-slate-600 hover:text-slate-800">
          Cancel
        </button>
        {updateMutation.isError && (
          <span className="text-sm text-red-600">{errorMessage(updateMutation.error, 'Failed to save changes.')}</span>
        )}
      </div>
    </form>
  )
}

function EndpointCard({ endpoint }: { endpoint: WebhookEndpoint }) {
  const queryClient = useQueryClient()
  const [editing, setEditing] = useState(false)
  const [expanded, setExpanded] = useState(false)

  const toggleMutation = useMutation({
    mutationFn: () => updateWebhookEndpoint(endpoint.id, { active: !endpoint.active }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ENDPOINTS_KEY }),
  })

  const deleteMutation = useMutation({
    mutationFn: () => deleteWebhookEndpoint(endpoint.id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ENDPOINTS_KEY }),
  })

  const testMutation = useMutation({
    mutationFn: () => sendWebhookTest(endpoint.id),
    onSuccess: () => {
      setExpanded(true)
      queryClient.invalidateQueries({ queryKey: deliveriesKey(endpoint.id) })
    },
  })

  function handleDelete() {
    if (window.confirm(`Delete the endpoint ${endpoint.url}? Its delivery history will be removed too.`)) {
      deleteMutation.mutate()
    }
  }

  const actionError = [toggleMutation, deleteMutation, testMutation].find((m) => m.isError)?.error

  return (
    <div className="bg-white border border-slate-200 rounded-lg">
      <div className="px-4 py-3">
        {editing ? (
          <EditEndpointForm endpoint={endpoint} onDone={() => setEditing(false)} />
        ) : (
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span className="font-mono text-xs text-slate-700 break-all">{endpoint.url}</span>
                <span
                  className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${endpoint.active ? 'bg-green-100 text-green-800' : 'bg-slate-100 text-slate-500'}`}
                >
                  {endpoint.active ? 'Active' : 'Disabled'}
                </span>
              </div>
              {endpoint.description && <p className="text-sm text-slate-500 mt-1">{endpoint.description}</p>}
            </div>
            <div className="flex items-center gap-3 shrink-0">
              <button
                type="button"
                onClick={() => testMutation.mutate()}
                disabled={!endpoint.active || testMutation.isPending}
                title={endpoint.active ? undefined : 'Enable the endpoint to send a test event'}
                className={`${linkBtn} text-indigo-600 hover:text-indigo-800`}
              >
                {testMutation.isPending ? 'Sending…' : 'Send test'}
              </button>
              <button type="button" onClick={() => setEditing(true)} className={`${linkBtn} text-slate-600 hover:text-slate-800`}>
                Edit
              </button>
              <button
                type="button"
                onClick={() => toggleMutation.mutate()}
                disabled={toggleMutation.isPending}
                className={`${linkBtn} text-slate-600 hover:text-slate-800`}
              >
                {endpoint.active ? 'Disable' : 'Enable'}
              </button>
              <button
                type="button"
                onClick={handleDelete}
                disabled={deleteMutation.isPending}
                className={`${linkBtn} text-red-600 hover:text-red-800`}
              >
                Remove
              </button>
              <button
                type="button"
                onClick={() => setExpanded((x) => !x)}
                aria-expanded={expanded}
                className={`${linkBtn} text-slate-600 hover:text-slate-800`}
              >
                {expanded ? 'Hide details' : 'Details'}
              </button>
            </div>
          </div>
        )}
        {actionError && (
          <p className="text-sm text-red-600 mt-2">{errorMessage(actionError, 'Something went wrong. Please try again.')}</p>
        )}
      </div>

      {expanded && (
        <div className="border-t border-slate-200 px-4 py-4 space-y-5 bg-slate-50/50">
          <SecretField endpointId={endpoint.id} />
          <DeliveryLog endpointId={endpoint.id} />
        </div>
      )}
    </div>
  )
}

export default function DeveloperSettings() {
  const endpointsQuery = useQuery({
    queryKey: ENDPOINTS_KEY,
    queryFn: fetchWebhookEndpoints,
  })

  return (
    <div className="space-y-8 max-w-4xl">
      <div>
        <h1 className="text-xl font-semibold text-slate-900 mb-1">Developer settings</h1>
        <p className="text-slate-500 text-sm">
          Configure webhook endpoints to receive event notifications from YunoJuno. We currently send{' '}
          <code className="bg-slate-100 px-1 rounded">timesheet.approved</code>.
        </p>
      </div>

      <AddEndpointForm />

      <div>
        <h2 className="text-base font-medium text-slate-800 mb-3">Configured endpoints</h2>

        {endpointsQuery.isLoading ? (
          <p className="text-slate-500 text-sm">Loading…</p>
        ) : endpointsQuery.isError ? (
          <p className="text-red-600 text-sm">Failed to load endpoints.</p>
        ) : !endpointsQuery.data || endpointsQuery.data.length === 0 ? (
          <div className="bg-white border border-slate-200 rounded-lg px-6 py-10 text-center">
            <p className="text-slate-500 text-sm">No webhook endpoints configured.</p>
          </div>
        ) : (
          <div className="space-y-3">
            {endpointsQuery.data.map((ep) => (
              <EndpointCard key={ep.id} endpoint={ep} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
