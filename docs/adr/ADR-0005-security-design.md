# ADR-0005: Security design for devices, certificates, firmware updates and remote access

- Status: **Accepted.** Confirmed by the tech lead on 17 Nov 2026; approved by prinz-assists, a collaborator other than the author, and merged on 20 Nov 2026 in PR #13.
- Date: 17 Nov 2026
- Story: P1-00 (issue S-002); shapes P1-12, P1-16 and the firmware-update work
- Deciders: GamitPrince (project manager / tech lead)
- Depends on: ADR-0002 (hardware), ADR-0003 (firmware), ADR-0004 (communications)
- Phase: Project Phase 1 (read-only monitoring of level and temperature)

## Context

ADR-0004 removed the separate gateway. The FRDM-MCXN947 and the ESP32 now sit directly on the client's network, send data to the cloud over MQTT over TLS with per-device certificates, and accept nothing from outside. RSD FR-COM-05 requires "remote access only through VPN; no open internet access to field devices", and NFR-05 requires VPN-only remote access, role-based login, an audit trail, secure firmware update with rollback, and backup and restore. ADR-0004 left open how device certificates are made and handled, how firmware updates are signed, and whether the VPN rule still applies. Devices are identified by a unique ID on a QR code, and a technician assigns each one to a tank at installation. The repository is public (ADR-0001).

## Decisions

1. **Device key:** each device creates its own key pair on the board, and the secret key never leaves it. We receive only the public part, and sign it for that device ID. If the MCXN947's secure key storage cannot be used from Zephyr, the fallback is a key made on a provisioning PC and loaded onto the device, and this ADR is amended. One shared key for all devices was rejected.
2. **QR claim:** the QR code carries only the device ID, never a secret. A device is "unclaimed" until a logged-in technician or admin scans the QR and assigns it to a tank. An unclaimed device may connect, but its data is held and not shown anywhere. A device can be claimed once; moving it to another tank needs an admin. A one-time code in the label was not chosen for Phase 1.
3. **Certificate authority:** our own private CA, free tools. The CA key stays offline (encrypted drive or hardware token) and is used only when devices are provisioned. It has an encrypted backup in a separate place and a short written procedure that does not depend on one person. A cloud provider's device service was not chosen, so that the cloud ADR is not forced and we are not tied to a provider. The broker trusts the CA's public certificate.
4. **Firmware signing:** firmware images are signed with a key separate from the CA key, and the bootloader (MCUboot) verifies the signature before installing, with rollback. The signing key is stored as a secret in the GitHub pipeline, and releases are signed automatically. Safeguards, all four required: (a) signing runs only for a release tag created from `main`, never for ordinary pull requests; (b) the key sits in a GitHub environment that needs approval from a second person before the signing job runs; (c) `.github/` stays under CODEOWNERS, so changing the pipeline needs a reviewed PR; (d) an encrypted offline backup of the key is kept, because GitHub cannot return a secret. An offline key signed by hand was the recommended alternative, and the tech lead chose the pipeline for convenience and plans to make the repo private later.
5. **Remote access (VPN):** devices make outbound connections only, over TLS with their own certificate, and accept nothing from outside, so Phase 1 needs no VPN. The controller accepts no commands or configuration (ADR-0004). Any future way into a device (remote configuration, service access) needs its own ADR and a VPN or an equivalent protection. Proposed new wording, not applied to the RSD: FR-COM-05 "No open internet access to field devices: devices make outbound, mutually authenticated TLS connections only, and accept no inbound connections in Phase 1"; NFR-05 "Outbound-only TLS with per-device certificates, role-based login, audit trail for setpoint and emission-factor changes, secure firmware update with rollback, backup and restore". [Confirm; the RSD is not edited unless the tech lead asks]
6. **ESP32 as a network path:** the ESP32 has its own certificate from the same CA, linked to the DAQ's device ID at provisioning, so the cloud sees two identities (FRDM and ESP32) for one DAQ. The ESP32 only makes outbound connections. A compromised ESP32 could forge readings on its path, so its firmware is locked down (signed updates, no inbound ports), and signing every record in the FRDM is revisited in Phase 2. A plain-pipe design with one identity, and a design where the FRDM signs every record, were not chosen for Phase 1.
7. **Certificate lifetime:** about 5 years, renewed by hand before expiry (in the field or at the bench), with an expiry reminder in the dashboard. Cancelled devices are put on a block list at the broker. Short-lived certificates with automatic renewal are left for Phase 2, when remote updates exist. A long lifetime also avoids lock-outs when the clock is not yet set after a power cut.
8. **Device lock:** signed boot on all units. The debug port is locked on units that go to a client site, as a release step with a written procedure, using a reversible lock level if the chip offers one. Development boards stay open. Leaving the port open until after the pilot was not chosen.

Standing rules (added as proposals in the final step, confirmed by the tech lead with the ADR):

9. **Secrets in a public repository:** no keys, certificates or passwords are ever committed. GitHub secret scanning and push protection are switched on. The CA key and the firmware signing key each have an encrypted offline backup in a separate place.
10. **Broker access:** each device may publish only to its own topic and may not read other devices' data. The topic layout is set in the cloud ADR.

## Consequences

- The cloud ADR must support our own CA, a block list and per-device topic rules, and must not assume a provider-managed device registry.
- Provisioning is a bench step per device: create the key on the board, sign it, load the certificate, record the device ID, print the QR label. It needs a script, a procedure and a record of every device. This is new work, and needs a story card.
- The dashboard needs a "claim device" screen with login and role checks, and a device state "unclaimed" in the data model (cloud and dashboard ADRs).
- Firmware signing in the pipeline is convenient but weaker than an offline key. Anyone who can change the pipeline or approve the environment could sign firmware, and a leaked secret allows forged firmware. If the repo goes private, GitHub's free plan may not enforce rulesets and required checks on private repositories (not verified). That would weaken the rules verified on 29 Oct 2026, and must be checked before the switch.
- The RSD wording of FR-COM-05 and NFR-05 and story P1-16 (VPN-only access) no longer match and must be updated (story cards and RSD).
- Locked debug ports make field debugging harder. Faulty site units are reflashed on the bench.
- The ESP32 carries a key and a certificate and handles all data on the Wi-Fi and 4G path, so its security matters as much as the FRDM's. Its own ADR must cover secure boot and update signing.
- The expiry of the 5-year certificates needs a reminder process, or a tank will go silent.

## To verify (early, in the communications and provisioning spike)

- The MCXN947's secure key storage works from Zephyr 4.5, can create a key pair on the device, and the secret key cannot be read out.
- MCUboot in Zephyr 4.5 supports signed images, rollback and the chosen key type on this board.
- Which debug-lock levels the MCXN947 offers, and whether one is reversible.
- The ESP32-S3's secure boot, flash encryption and key storage options.
- TLS certificate checking before the time is known (ADR-0004 decision 11): how a device validates dates after a power cut, with a long lifetime and an unsynchronised clock.
- The broker supports a block list and per-device topic rules.
- GitHub environments with required reviewers work on the current plan for this repository, and what changes if it becomes private (rulesets and required checks).
- The certificate and TLS stack fit within the FRDM's memory next to MQTT (ADR-0003 and 0004 check).

## Not decided here

- Dashboard user login, roles and the audit trail (dashboard and cloud ADRs).
- Encryption of stored data, backups and retention (cloud ADR).
- The ESP32's own secure boot and update signing (ESP32 firmware ADR).
- Signing every record on the FRDM (revisited in Phase 2).
- Automatic certificate renewal and any remote access to devices (Phase 2 and later, own ADR).
- Whether to move the firmware signing key offline, or to make the repository private (see consequences).

## References

- RSD v0.2: FR-COM-01, FR-COM-05, FR-SAF-01, NFR-03, NFR-05
- ADR-0001, ADR-0002, ADR-0003, ADR-0004
