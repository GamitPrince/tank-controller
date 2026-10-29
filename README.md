# tank-controller

Tank-AI: monitoring and (in later phases) control for hot-liquid storage tanks. One repository holds firmware, gateway, dashboard, simulator, hardware files and docs.

**Current scope: Phase 1, read-only monitoring of level and temperature.** The software never writes to the hardwired safety chain.

| Folder | Contents |
| --- | --- |
| `firmware/` | Controller board code. `firmware/src/safety/` needs the EE's approval |
| `gateway/` | Data pipeline, Modbus, MQTT, OPC UA, buffering |
| `dashboard/` | Web interface |
| `simulator/` | Tank and heater simulator used by everyone for testing |
| `hardware/` | Schematics, BOM, wiring diagrams |
| `interfaces/` | Register map, MQTT topics, API contract. Changes need all three developers |
| `docs/` | RSD, ADRs, runbook, setup guide, safety docs |

Start here: [CONTRIBUTING.md](CONTRIBUTING.md). Repository setup: [docs/github-setup.md](docs/github-setup.md).

Governing documents: SDLC Playbook (SOP-SDLC-001) and the GitHub Workflow Guide.

Tool versions (SDK, compiler, runtimes) are pinned here once the tech-stack ADRs (story P1-00) are accepted.

<!-- Verified initial setup and CI workflow -->
