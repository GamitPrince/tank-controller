# ADR-0007: Cloud architecture: hosting, provider, databases, retention, backend and updates

- Status: Confirmed by the tech lead on 18 Nov 2026 as the direction, including the three proposed rules; becomes Accepted when all three developers approve the PR. No account is opened and nothing is bought until three gates pass: the customers' answers (see Questions for the customers), the early cloud test (see To verify), and a Tiger Cloud quote for 100 and 1,000 devices. If a gate fails, we use the fallback in decision 4 or reopen the decision. Not yet pushed to GitHub.
- Date: 17 Nov 2026
- Story: P1-00 (issue S-002); shapes P1-12, P1-13, P1-14, P1-16 and the cloud-side stories (to be created)
- Deciders: GamitPrince (project manager / tech lead)
- Depends on: ADR-0004 (communications), ADR-0005 (security), ADR-0006 (ESP32 firmware)
- Phase: Project Phase 1 (read-only monitoring of level and temperature)

## Context

Devices send CBOR records over MQTT over TLS with per-device certificates, outbound only (ADR-0004, 0005). The cloud must receive them, check device identity against our own CA and block list, publish only to each device's own topic (ADR-0005), calculate volume and mass from tank geometry (ADR-0004 decision 10), store the readings, and feed the dashboard. The customers may be large industrial companies (Siemens and Astec Industries were named as the intended customers). The RSD leaves cloud provider and retention open (story cards section 7). Clients need to look back over years to see degradation or a drop in performance.

## Decisions

1. **Hosting model:** managed services from a large cloud provider, not one server that we run ourselves. This means the provider runs the broker, databases, container hosting, backups and patching. The tech lead chose this over the recommended single server in containers. The cost is a monthly bill that grows with devices and data, earlier lock-in to the provider, and learning its tools. Our own code stays in containers and our data in standard formats to limit the lock-in.
2. **Who runs the cloud:** one shared cloud (multi-tenant) in our own account for all customers, not a separate cloud per customer. The data model has a customer, plant, tank, device hierarchy, and every user, query and device is restricted to its own customer. We pay the bill and recharge it to customers. If a customer later requires its own cloud account, the container design keeps that possible but it is extra work.
3. **Provider:** AWS, with AWS IoT Core as the MQTT broker. Our own CA from ADR-0005 is registered with IoT Core, so certificates signed by it are accepted, and devices can register on first connect. Azure (Event Grid MQTT broker) was the close alternative: it also supports X.509 client certificates, per-client topic permissions, QoS 0 and 1, and 1 MB messages. Google Cloud was not chosen: it has no managed MQTT broker since its IoT Core service shut down on 16 Aug 2023. Facts checked on 17 Nov 2026 against AWS and Azure documentation. AWS list prices (US East, from secondary sources verified June 2025, so possibly out of date, and the Mumbai region usually costs more): $1.00 per million messages, metered in 5 KB steps; $0.08 per million connection minutes; $0.15 per million rule triggers plus $0.15 per million actions. Estimated cost for messaging, rules and connection: about $3.40 per device per month at one message per second, about $0.70 if records are batched every 5 s (about $340 or $70 a month for 100 devices; $3,400 or $700 for 1,000). Not priced: Azure, the databases, backend hosting, storage growth, data transfer and the SIM data plan.
4. **Databases:** Tiger Cloud (TigerData, managed TimescaleDB, which is PostgreSQL with time-series features) on AWS in the Mumbai region (ap-south-1), for both the readings and the records (customers, plants, tanks, devices and their claim status, tank geometry tables, users and roles). The tech lead wanted a database built for long-term time series, chosen now so that no migration is needed later. Its documentation describes compression of older data, automatic roll-ups (continuous aggregates) that remain after the detail is dropped, and tiering of old data to cheap object storage that stays queryable with SQL (tiering is a Tiger Cloud feature). It is also sold through the AWS Marketplace (the billing arrangement is to be checked). Chosen over Timestream for InfluxDB 3 plus managed PostgreSQL, which is the recorded fallback: it keeps everything with one vendor and stores data as files in S3, but its roll-up and retention features, price and Mumbai availability are unverified, and it needs a second database for the records. Amazon Timestream for LiveAnalytics is closed to new customers since 20 June 2025. TimescaleDB is not among the extensions listed for Amazon RDS for PostgreSQL (versions 15 to 19), so it comes from the third-party vendor. The cost of this choice is a second vendor, with its own contract, bill and security review, and customer data that sits in the vendor's AWS account. If Siemens or Astec requires a single vendor or data inside our own account, we switch to the fallback.
5. **Retention:** nothing is ever deleted, because clients need years of history to check for degradation. Three layers: (a) every original record is archived in cheap, compressed file storage forever; (b) per-minute summaries (average, minimum, maximum) are kept in the readings database forever; (c) per-second readings are kept in the readings database for 90 days. A deep check on older detail reloads records from the archive first. In Tiger Cloud, the per-minute summaries are continuous aggregates, and the 90-day rule drops per-second chunks only after their aggregates exist and the raw archive holds the originals (a retention rule that is too short can remove the aggregates too). The 90 days and the per-minute step are settings, proposed values [Confirm], and can be changed per customer. Keeping per-second detail in the database forever was not chosen because the cost grows with every device and year (about 2 million values per device per day).
6. **Backend runtime:** the backend runs as containers on a managed container service, fed by a managed queue. IoT Core hands each message to the queue and to the raw archive, so nothing is lost while the backend restarts. The backend decodes the CBOR records, checks them against the signal list, calculates volume and mass, flags stale data, and writes to the database. Serverless functions (AWS Lambda) were not chosen: tied tightly to AWS, harder to test locally, and costs rise with message rate.
7. **Firmware update delivery:** in Phase 1, updates are loaded by a technician on site with a cable, for both the FRDM and the ESP32. Signature checking and rollback work as in ADR-0003, 0005 and 0006. Network updates (OTA) are designed in Phase 2 in their own ADR, with staged release, a stop mechanism, flash space for a second image and a review of the new path. The controller therefore still has no inbound path in Phase 1. The cost is that every fix is a site visit.

Proposed rules (not asked in the decision dialog; to be confirmed by the tech lead with the ADR):

8. **Encryption:** data is encrypted in transit (TLS everywhere) and at rest (the provider's managed encryption for the databases, queue and file storage). [Confirm]
9. **Volume and mass:** calculated in the backend from the tank geometry table (in PostgreSQL) and a temperature-corrected density, with the calculation version stored beside each result, so figures can be reproduced from the raw archive. [Confirm]
10. **Cost control:** a monthly budget and alert is set on the cloud account from the first day, and the cost per device is reviewed at the pilot. [Confirm]

## Consequences

- The data model and every query need customer separation from the start (customer, plant, tank, device). The dashboard needs login and roles per customer (dashboard ADR), and the "claim device" screen of ADR-0005.
- We are tied to AWS earlier than the single-server option would have been. IoT Core and the queue are AWS services. Keeping the backend in containers and the data in PostgreSQL limits this to the broker and the queue.
- Cost grows with devices and data, and our message pricing depends on batching (5 KB metering). Records per message, and how often to send, are therefore also a cost and 4G data decision (open in ADR-0004).
- A second vendor (Tiger Cloud) means a second contract, bill and security review, and the customer data sits in the vendor's AWS account. Large customers may ask for a list of sub-processors or approve only certain vendors, so Siemens and Astec are asked early (see Questions for the customers). If they require one vendor, we switch to the fallback in decision 4.
- Estimated monthly cost for the whole cloud (US East list prices from secondary sources, plus my own estimates, so uncertain): about $130 to $200 for a pilot of 5 devices, $370 to $860 for 100 devices, and $1,900 to $5,300 for 1,000 devices (the all-AWS route is about $230 to $300, $480 to $820 and $1,900 to $5,000). MQTT messaging dominates at fleet size, so how often records are batched matters more than the database. Not included: Tiger Cloud compute prices at 100 and 1,000 devices (not published, estimated), Mumbai uplift, the SIM plans, GST, support plans and people costs.
- The raw archive of every record is a new data store to look after. Reloading old detail from it needs a tool and a procedure (a story).
- Phase 1 fixes need site visits. The pilot site's distance affects this.
- A story card is needed for the cloud (broker setup with our CA and per-device rules, queue, backend, databases, archive, roll-ups), and for cost monitoring. Estimates need review. [Confirm]
- RSD NFR-09 (one gateway for several tanks) is replaced by the customer, plant, tank, device hierarchy, and the RSD wording on FR-COM-01 and FR-COM-05 still needs updating (ADR-0004, 0005).

## To verify (early, in the cloud spike)

- IoT Core registers our own CA, accepts devices that register on first connect, enforces per-device topic rules, and supports cancelling a certificate (the block list of ADR-0005), with exact setup steps.
- IoT Core supports QoS 1, MQTT over TLS on its standard secure port, and MQTT over WebSocket on port 443 (ADR-0004 decision 7).
- IoT Core's rules cannot decode CBOR themselves, so the backend decodes the records. Check how IoT Core passes binary messages to the queue and the archive.
- Prices in the chosen region (Mumbai or Hyderabad), for IoT Core, Tiger Cloud, container hosting, the queue, storage and data transfer, with a calculator run for 10, 100 and 1,000 devices. Check that all the chosen services are available in an India region.
- Tiger Cloud: compute sizes and prices for 100 and 1,000 devices (not published, so a quote is needed); the AWS Marketplace billing arrangement; a private network connection from our backend (no public database endpoint); the security and compliance documents we can show customers; per-minute continuous aggregates kept forever, with tiering, at acceptable cost; point-in-time recovery length (3 days on the Performance plan, 14 on Scale); and an exit test by dump and restore to another PostgreSQL.
- Fallback check, only if needed: Timestream for InfluxDB 3 roll-ups, retention settings, price (about $0.132 per medium node-hour in US East, from a secondary source) and Mumbai availability.
- Reloading raw records from the archive for a deep check works and is fast enough.
- Azure Event Grid pricing and custom-CA setup, if the choice of AWS is ever reopened.

## Not decided here

- Topic layout and the exact message batching (records per message, send rate).
- Backend language and framework, dashboard login and roles, the audit trail (dashboard ADR).
- Infrastructure-as-code tool, monitoring, alerting and backup and restore tests.
- The AWS region and data location. [Confirm: India, for example Mumbai or Hyderabad]
- The pipeline for the cloud code and its tests (CI tooling ADR).
- Network firmware updates (Phase 2 ADR).
- Whether to support a customer's own cloud account later.

## Questions for the customers (Siemens, Astec)

- Which cloud providers and third-party vendors are allowed, and is there an approved-supplier list?
- Must the data stay in India?
- Do they need a list of sub-processors, and what review does each vendor go through?
- Do they accept a shared cloud in our own account, or require their own account or a single vendor?
- Do they have their own industrial platform that the system must feed?

## References

- RSD v0.2: FR-COM-01, FR-COM-03, FR-COM-04, FR-SAF-04, NFR-01, NFR-04, NFR-09, NFR-10
- ADR-0004, ADR-0005, ADR-0006
- AWS IoT Core documentation on own client certificates; Amazon Timestream for LiveAnalytics availability change; Azure Event Grid MQTT broker overview; Amazon RDS for PostgreSQL extension versions
