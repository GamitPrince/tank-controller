# tank-controller

Tank-AI: monitoring and (in later phases) control for hot-liquid storage tanks. One repository holds the controller and ESP32 firmware, the dashboard, the simulator, hardware notes and docs.

**Current scope: Phase 1, read-only monitoring of level and temperature.** The software never writes to the hardwired safety chain.

| Folder | Contents |
| --- | --- |
| `firmware/` | FRDM-MCXN947 controller firmware (Zephyr 4.5.0, C11). `firmware/src/safety/` needs the EE's approval |
| `esp32/` | ESP32-S3 communications helper firmware (ESP-IDF, C); logic tested on the host with Unity |
| `shared/link-protocol/` | The FRDM-to-ESP32 UART link library (COBS framing, sequence numbers, CRC, delivery confirmation), built by both firmwares and tested by the `firmware` job |
| `dashboard/` | Web interface |
| `simulator/` | Tank and heater simulator used by everyone for testing |
| `hardware/` | Bill of materials and wiring notes. Schematics and hardware review records stay in a private location, never in this public repo |
| `interfaces/` | Versioned YAML signal list, CDDL record schema, MQTT topics, API contract. Changes need one approval from a collaborator other than the author |
| `docs/` | ADRs, story specs, the [setup guide](docs/setup-guide.md), the [Feature Registry](docs/features/README.md), safety docs. The runbook comes with the cloud |

Start here: [CONTRIBUTING.md](CONTRIBUTING.md). Repository setup: [docs/github-setup.md](docs/github-setup.md).

Governing documents: SDLC Playbook (SOP-SDLC-001) and the GitHub Workflow Guide.

Tool versions: Zephyr 4.5.0 is pinned in `firmware/west.yml`, Unity v2.6.1 in `esp32/ci.sh`, and the Python tools in each component's `requirements-dev.txt`. How to set up a machine: [docs/setup-guide.md](docs/setup-guide.md).
