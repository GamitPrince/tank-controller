# ADR-0008: Backend and dashboard: languages, login, access, audit trail, live updates and tests

- Status: **Accepted.** Confirmed by the tech lead on 19 Nov 2026, including the four proposed rules, the role meanings and the named-admin-account rule; approved by prinz-assists, a collaborator other than the author, and merged on 20 Nov 2026 in PR #16.
- Date: 18 Nov 2026 (confirmed 19 Nov 2026)
- Story: P1-00 (issue S-002); shapes P1-19, P1-21, P1-26 and the backend and dashboard stories (to be created)
- Deciders: GamitPrince (project manager / tech lead)
- Depends on: ADR-0004 (communications), ADR-0005 (security), ADR-0007 (cloud)
- Phase: Project Phase 1 (read-only monitoring of level and temperature)

## Context

ADR-0007 puts the backend in containers on AWS, with one shared cloud for all customers, Tiger Cloud (PostgreSQL) as the database, and a managed queue in front of the backend. The Phase 1 dashboard comes from the RSD: the main tank screen (FR-HMI-01), the colour code (FR-HMI-05), role-based login with operator, maintenance, admin and service levels (FR-HMI-06) and trend charts with CSV export (FR-HMI-07). Values must be less than 5 s old when the link is up (NFR-01), stale data must show as stale (FR-SAF-04), screens must work with gloves on a tablet and not rely on colour alone (NFR-08), and alarms and audit records are required (FR-SAF-03, NFR-05, NFR-10). ADR-0005 requires a "claim device" step done by a logged-in technician or admin. The customers may be large industrial companies, so users from different customers and plants must never see each other's data. The dashboard developers are ArkinGamit and SHINE-18, and much of the code will be written with AI, so every pull request still needs a human approval and the code must be readable by its reviewers.

## Decisions

1. **Languages:** Python (FastAPI) for the backend, and TypeScript with React for the dashboard. The API is described with OpenAPI, and the TypeScript types are generated from it so the two sides stay in step. The choice was made on merits, not on team skills. Python is the best fit for the analysis work of Phase 2 and 3 (vibration spectra, anomaly detection, energy-loss balances, learned models) and shares code with the simulator (ADR-0004), which is already Python. TypeScript everywhere (a Node backend) was not chosen because it is weaker for that analysis and would probably add a Python service later.
2. **Login:** Amazon Cognito, Essentials tier. It gives username and password sign-in, two-factor login (authenticator app, SMS or email code), passwordless one-time codes and passkeys, a visual editor for the login page, blocking reuse of old passwords, our own values (customer ID, role, plants) in the login token, refresh-token rotation, and company single sign-on (SAML or OIDC) when a customer asks. It is free for the first 10,000 monthly users and $0.015 per user above that; company single sign-on is free for the first 50 users and $0.015 per user above that (AWS pricing page, checked 18 Nov 2026). We build a styled login page and our own user-admin screen, because the built-in screens are plain. The Plus tier (threat protection, adaptive login, activity logs) is an option if a customer asks for it. A separate identity vendor (for example Auth0 or Clerk) was not chosen: it adds a vendor, a bill and a security review, and its prices were not checked. Our own login was rejected.
3. **Roles and scope:** every user belongs to exactly one customer and may be limited to specific plants or tanks. The customer ID, role and allowed plants travel in the login token, and the backend checks them on every request. The browser is never trusted to enforce them. Proposed role meanings: operator sees live values and trends and acknowledges alarms; maintenance adds device and sensor health details; admin (the customer's own admin) manages that customer's users and tank settings such as the geometry table; service (our own staff) can support any customer, and every such access is recorded in the audit trail. Customer-level scope only was not chosen, because adding plant limits later would mean reworking every query.
4. **Audit trail:** an append-only table in the database. The backend can add rows but not edit or delete them, and writes each row in the same step as the change it records, so nothing changes without a record. Each day's entries are also copied to S3 storage with write-once protection (S3 Object Lock), so history cannot be quietly rewritten even by someone with database access. Events recorded in Phase 1: logins and failed logins, alarm acknowledgements, device claims and moves, user and role changes, tank settings changes, and every access by service staff to a customer's data, each with who, what, when and the value before and after. A hash chain on the entries is added in Phase 2, when emission and carbon records may be challenged (NFR-10). A plain table was rejected (changes leave no trace, and NFR-10 asks for tamper evidence). The hash chain from the start was not chosen, because it is more work in Phase 1 for records that mostly matter from Phase 2.
5. **Live updates:** the backend pushes updates to the browser with server-sent events, with automatic fallback to polling every few seconds if a customer's network blocks the push. Every value carries its quality flag and age, so the screen shows stale data as stale (FR-SAF-04, and the 30 s limit of P1-19). The browser never connects to the broker directly, because the backend must do the customer and plant checks on every value. Polling only was not chosen (values can be a few seconds older, using up the 5 s budget).
6. **Tests:** pytest with its coverage plugin for the backend, and Vitest with React Testing Library for the dashboard, each component with a `ci.sh` that writes a Cobertura `coverage.xml`. The 80% gate counts all our code, including the screens. Only third-party and generated code is excluded, and any change to the exclusion list needs the review of all three developers. Browser end-to-end tests (Playwright) run the dashboard against the simulator and are not counted in the 80%. Reviewers check that tests assert real behaviour and are not written just to reach the number. Counting logic only was not chosen.

Proposed rules (not asked in the decision dialog; to be confirmed by the tech lead with the ADR):

7. **API:** REST with OpenAPI, versioned from the start. Every endpoint checks customer and plant scope. CSV export (FR-HMI-07) uses the same API, and PDF reports are left for later.
8. **Dashboard hosting:** the dashboard is a static single-page app served from AWS storage with a content delivery network, with the backend API (in containers, ADR-0007) behind the same domain.
9. **Read-only for plant data:** in Phase 1 the dashboard sends no command to any device. It only writes to the cloud: alarm acknowledgements, tank settings, device claims, user administration. This fits ADR-0004's send-only controller.
10. **Design rules:** the screens follow the P1-26 design. The colour code (FR-HMI-05) always has text beside it (NFR-08), touch targets are large enough for gloves on a tablet, and the UI component and chart libraries are chosen in P1-26.

## Consequences

- Two toolchains in CI (Python and Node), two `ci.sh` files, and two container builds (the backend, and the dashboard build step). The shared pipeline and deployment are decided in the CI tooling ADR.
- Cognito's built-in screens and user management are plain, so a styled login page, a user-admin screen and a role and plant assignment screen are extra work (stories to be created).
- The "claim device" screen of ADR-0005 is an admin permission. Decided by the tech lead on 18 Nov 2026: technicians use admin logins, so there is no separate technician role and ADR-0005's "technician or admin" means an admin account. Claiming and moving a device are written to the audit trail with the person's name. Proposed rule: every technician has their own named admin account, never a shared login, so the audit trail shows who claimed which device. The downside is that an admin account can also manage users and tank settings, so it is more power than claiming needs; a narrower claim-only permission can be added later if a customer asks.
- Counting all code, including screens, adds test work for the dashboard. With AI writing the tests this is cheap, but the review effort rises, because shallow tests must be caught.
- Server push may be blocked or cut by some customer networks and proxies. The polling fallback must be tested, not assumed.
- The audit trail adds a daily job and an S3 Object Lock setting to configure, and the daily copy needs a restore-and-verify test. The audit table is part of the "nothing deleted" rule of ADR-0007.
- New story cards are needed for the backend API, user admin, claim device, the audit trail and live updates. The estimates in the story cards need review.
- RSD FR-HMI-06 lists four roles and NFR-05 mentions an audit trail for setpoint and emission-factor changes. These fit, but the role meanings above should be added to the RSD wording. [Confirm; the RSD is not edited unless the tech lead asks]

## To verify (early)

- Cognito groups and custom token values work with the Essentials tier, in the chosen region (Mumbai or another), and company single sign-on works with the identity systems that Siemens or Astec use.
- Server-sent events work through the content delivery network and the container load balancer (timeouts, buffering), and the polling fallback takes over cleanly.
- The CBOR records are decoded and checked against the CDDL schema in Python (library choice, speed at fleet rate).
- The OpenAPI to TypeScript type generation works in CI.
- pytest-cov and Vitest each write a Cobertura `coverage.xml` that the repo's coverage check accepts.
- S3 Object Lock: cost, retention settings and the daily copy job, and that the backend's database permissions really allow adding audit rows but not editing or deleting them.
- Cognito prices at fleet size, and the Plus tier price if a customer asks for it.

## Not decided here

- UI component and chart libraries, and the screen designs (P1-26).
- How alarms are delivered (email, SMS, push) and with which service (AWS's own services are assumed; not decided).
- Password policy, session lengths and what happens to users when a customer leaves.
- PDF reports and the layout of CSV export.
- The deployment pipeline, infrastructure-as-code and monitoring (CI tooling ADR).
- Languages other than English.

## References

- RSD v0.2: FR-HMI-01, FR-HMI-05, FR-HMI-06, FR-HMI-07, FR-SAF-03, FR-SAF-04, NFR-01, NFR-05, NFR-08, NFR-10
- ADR-0004, ADR-0005, ADR-0007
- Amazon Cognito pricing and tier features (AWS pricing page, checked 18 Nov 2026)
