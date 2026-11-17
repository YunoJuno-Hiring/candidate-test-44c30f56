# What did I build and why?
I chose to build out the Outbound Webhooks feature in Task C. I felt that this task gave me the opportunity to show my backend knowledge, some forward planning with system design, and a bit of frontend.

The chosen event is `timesheet.approved`. The resason I chose this event was because it posed additional problems that we needed to handle like a user double clicking the approve button, multiple admins approving creating a race condition. This gave us a real example of idempotency that needs solving.

# Key implementation notes
The key implementation of the webhook event feature was for a delivery guarantee so the consumer receives the event at least once. Due to the nature of the events providing the consumer a reliable key to use to de-duple requests was a requirement.

## Postgres Outbox
Once an timesheet has been approved, the `WebhookEvent` row and `WebhookDelivery` row for each of the company's active endpoints are written. The key part of this is that they are written in the same database transaction. This ensures that there can be no race condition for two admins marking a timesheet as approved and if there is an issue with either the `TimesheetEntry` UPDATE or either webhook INSERT then everything within the transaction fails. This is in place to ensure that the a webhook event isn't created for a timesheet that is not updated in the DB and vice versa.

## Idempotency and Signing
### Idempotency Consumer Side
Every event has an `id` in the body, this stays the same across every retry and every endpoint, so consumers can dedupe on it. This makes the webhooks at-least-once delivery safe.

### Idempotency Producer Side
The timesheet approval PATCH locks the row, this prevents a race condition with two admins approving a timesheet submission. Using a unique contraint on the DB prevents one event being queued for the same endpoint twice.

### Signing
Three headers are sent with a webhook: `webhook-id`, `webhook-timestamp`, and `webhook-signature`. The signature includes the version, and creates a HMAC of the id, timestamp, and body. The consumer can use this to de-dupe events and ignore events which are too old.

## Worker
The worker polls rows every second in batches of 20, the query uses `SKIP LOCKED` to allow multiple replicas without double sending. The worker is also async so that a slow consumer doesn't slow down the worker.

## Retry Policy
A webhook will try 8 times, each attempt sleeping exponentially longer. A jitter %10 is also added to prevent a stampede of events once the consumer is back online. 

Ideally a customer would be notified if their consumer is down for the full period that an event retries for. They should also be able to replay events (however this is out of the scope of this task).

# My workflow
## Planning
Before even looking at the code I spun up the application locally so I could login and understand the flow for the user.

My next f more in depth read in the routes that this feature would require changes to be made to. Here that is the `webhooks`, and `contracts` routes in the backend.

With an idea for how the code currently looks and the requirements for the feature I brainstorm some ideas and how I want the feature to look:
```
- Design a webhook model
- Being able to create a webhook body
- Signing a webhook
- Create the webhook delivery mechanism, with error handling from a consumer
- Using postgres for the outbox, we don't want to introduce new infrastructure. Allows us to use a single transaction for when marking a timesheet as approved and create a new webhook event. (We have chosen timesheet approved, so that Idempotency is more important)
- Work on retries, using backoff and jitter to prevent a stampede of requests when the webhook consumer comes back online.
- Create a worker to poll the postgres outbox, a worker allows us to scale up more replicas. Using `SKIP LOCKED` to prevent the same event being sent by two workers.
- Making changes to endpoints and adding additional webhook creation and management endpoints
```

I then refine these notes and create a Claude Code plan session, I always ensure that the plan is broken down in to multiple steps so that I can easily manage the output from and any new code that is being written.

## Building
Even after creating the plan I will begin to write some "boilerplate" code and classes to how I want them to be written.

I like to keep the code generation in stages so that I can read and assess every function that is being written, I don't like to feel disconnected from the code in anyway.

As functions are generated I will read them to ensure they are how I want the code to be written. An example here is the generic `http_post` function request in `backend/webhooks/deliver.py` originally used a broad try except which I didn't like because it meant the customer didn't get the full story for why an event was unsuccessful.

## Testing and Verification
I have written out some unit tests for the basic functions of signing and the delivery of webhooks. Given more time I would build out more unit tests to cover more of the feature.

In this case I have carried out mostly manual testing, this included sending test webhooks and verifying the output, approving a timesheet to ensure a webhook is sent correctly, taking down the webhook consumer to test the retry mechanism, and then bringing the consumer back online to ensure webhooks are then sent correctly and marked as successful.

# Next steps
If I had additional time I would add:
- Use a Redis queue in addition to the Postgres Outbox, increasing the pickup speed of a webhook and decreasing the polling load on Postgres.
- Encrypt the Webhook secret at rest, we can't simply use a hash here because we need access to the secret to sign outgoing webhooks.
- Built out more unit tests for this feature, using pytest. Additional tests for race conditions like two admins approving at once, endpoints and testing their access, Postgres outbox rollback if an approval UPDATE fails. There are many more specific tests we could write to catch edge cases.
- Adding Prometheus and Grafana for monitoring, espcially with a queue system like this it's important to have alerts setup to be notified when a queue is growing in size by an abnormal amount.
- Setup alerting when a consumer has died and is no longer receiving so we can manually notify the customer or alternatively setup automatic emailing.
