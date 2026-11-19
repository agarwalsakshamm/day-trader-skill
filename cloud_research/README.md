# Cloud research upgrade — inactive development component

Status: notification safety filter implemented; standalone research runner,
database migration, dashboard, push delivery and unattended scheduling are not
implemented or activated by this commit. No Render resources are provisioned.

Authorized operating design: collect and assess completed bars every five minutes
during verified market sessions. Persist non-actionable checks silently. A BUY
decision requires the original fresh first ORB, verified material news and every
downstream source tool and exact-order risk gate. SELL decisions require actual
user-confirmed holdings; research alerts and model outcomes are not executions.
Keep all original cash/risk limits, weekly NEW alert limit, fallback hold and
deduplication. Do not change the swing trial, INR account or existing schedules.

The private cloud database is the proposed live journal, with explicit versioned
imports from and exports to the existing ChatGPT journal identity. No account
data, user identity, journal content or service credentials belong in this repo.
Migration is not complete until a guarded import, readback, journal identity and
writer handover have been verified. The old daily writer stays active until then.

The immediate-alert design is a private dashboard plus browser push, subject to
device support, a user notification permission and successful test delivery.
No working push channel is claimed. No automatic email address is inferred from
the SEC identification or hosting account. Technical failures may still require
a notification; routine WAIT observations do not.

The notification filter accepts only evidence from a trusted research engine.
It does not fetch or validate prices, run research, independently establish risk,
send notifications, or transact a journal. It must not be exposed as a public
endpoint or treated as a substitute for the upstream risk/source tools. BUY keys
preserve the legacy cloud_guard encoding to prevent duplicate migration alerts.
Actual sending requires a durable transactional outbox, unique alert/session/key
constraints, serialization and reconciliation of uncertain writes/deliveries.

Before activation: complete the runner and storage, verify a named
America/New_York scheduler with NYSE holidays and early closes, execute real live
checks and any genuinely applicable calculations in the intended Render host,
test persistence/restarts/alert delivery, and review the actual paid resource plan.
No automatic brokerage access, order transmission, order approval or fill records.

Run safety tests with `python3 -m unittest discover -s cloud_research -v`.
