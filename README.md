# tank-controller

Tank-AI: monitoring and (in later phases) control for hot-liquid storage tanks. One repository holds firmware, gateway, dashboard, simulator, hardware files and docs.

**Current scope: Phase 1, read-only monitoring of level and temperature.** The software never writes to the hardwired safety chain.

| Folder | Contents |
| --- | --- |
| `firmware/` | Controller board code. `firmware/src/safety/` needs the EE's approval |
| `gateway/` | Empty and probably obsolete: ADR-0004 removed the separate gateway, so the controller collects and communicates itself. Do not add code here |
| `dashboard/` | Web interface |
| `simulator/` | Tank and heater simulator used by everyone for testing |
| `hardware/` | Bill of materials and wiring notes. Schematics and hardware review records stay in a private location, never in this public repo |
| `interfaces/` | Versioned YAML signal list, CDDL record schema, MQTT topics, API contract. Changes need one approval from a collaborator other than the author |
| `docs/` | RSD, ADRs, runbook, setup guide, safety docs |

Start here: [CONTRIBUTING.md](CONTRIBUTING.md). Repository setup: [docs/github-setup.md](docs/github-setup.md).

Governing documents: SDLC Playbook (SOP-SDLC-001) and the GitHub Workflow Guide.

Tool versions (SDK, compiler, runtimes) are pinned here once the tech-stack ADRs (story P1-00) are accepted.
