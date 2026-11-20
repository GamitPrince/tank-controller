# P1-20: Role-based login with audit trail for configuration changes

- Story ID: `[Confirm]` — not yet issued.
- Epic: E4. Points: 5. Priority: Must. Component: dashboard (backend). Review flag: none.

## Goal
Each user signs in as themselves, sees only their own organisation's data, and every configuration change is attributable.

## Phase check
Phase 1. Access control only.

## Decisions already made
- **ADR-0008:** login is **Amazon Cognito Essentials**. A user belongs to **one customer**, optionally limited to plants or tanks. Roles: **operator, maintenance, admin** (the customer's) and **service** (our staff, audited). The **backend checks every request**. There is **no technician role** — each technician has a **named admin account, never shared**. Audit trail is an append-only table plus a daily write-once S3 copy with Object Lock.
- **ADR-0007:** one shared multi-tenant cloud, modelled customer > plant > tank > device. Users from different customers must never see each other's data.
- **ADR-0005:** the QR code carries **only the device ID**; an admin claims a device once and assigns it to a tank.

## Differences from the card worth noting
- The card says "**passwords are stored hashed**". With Cognito we do not store passwords at all — Cognito does. The criterion is met by not holding credentials; reword rather than implement.
- The card's four roles match ADR-0008, but the **service** role carries an auditing obligation the card does not mention, and the no-technician-role rule is an explicit ADR-0008 decision.

## Acceptance criteria (card, re-pointed)
- Four roles exist with distinct permissions.
- A restricted action is **blocked for a lower role** — enforced in the backend, not only hidden in the UI.
- Each configuration change is **logged with user and time**.
- ~~Passwords are stored hashed.~~ Replace with: no credential material is stored by us; Cognito holds it.
- Plus: a user of customer A cannot read customer B's data by any request, including by guessing IDs. This is the multi-tenant isolation test and matters most to Siemens and Astec.
- Plus: service-role access is recorded in the audit trail as our staff acting.

## Test plan
pytest: each role against each endpoint, a lower role attempting a restricted action, direct-ID access across customer boundaries, plant and tank limited users, service-role action appears in the audit trail, audit record cannot be altered. Multi-tenant isolation deserves its own test file.

## Dependency
P1-17. Blocks P1-18's "who acknowledged" and the device-claim flow.

## Out of scope
The QR device-claim flow (ADR-0005) — it has **no story** and needs one. Customer self-service user management `[Confirm]`.

## Open questions
- `[Confirm]` Who creates customer admin accounts initially: us, or the customer?
- `[Confirm]` Is MFA required? Siemens and Astec will likely ask.
- `[Confirm]` Does the device-claim flow belong here or in a new story?
