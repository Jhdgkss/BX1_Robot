# BX1 OS Management Interface

## Purpose

The BX1 OS Management Interface is the long-term operating-system management
surface for BX1. It is a new application served by the side-by-side BX1 OS
service on port 8089.

It is not the existing Robot Body interface. The existing application remains
on port 8088 and its `web_control.py` implementation, routes, HTML, JavaScript
and styles are not imported or modified by the management application.

## v0.2.0 scope

This release establishes architecture only:

- responsive application shell;
- collapsible desktop navigation and mobile drawer;
- reusable panels, metrics, tables, badges, empty states, forms and timelines;
- Dashboard, System, Services, Hardware, Brain, Configuration, Logs,
  Deployment, Diagnostics, Updates and About routes;
- read-only bootstrap and qualification status endpoints;
- placeholders for future privileged integrations; and
- explicit fail-closed handling for management actions.

No service restart, host power, configuration write, log streaming, update or
rollback action is implemented.

## v0.3.0 Core integration

The application shell is unchanged, but its runtime values now come only from
BX1 OS Core. Host observation moved from `bx1_management` into Core plugins.
The browser requests `/api/core/state`, `/api/core/health`,
`/api/core/plugins`, `/api/core/services` and `/api/core/system`.

The v0.2.0 bootstrap endpoint remains as a compatibility projection generated
from Core state; it is no longer a dashboard data source.

## v0.4.0 hardware and audio integration

The Hardware, Audio and Diagnostics pages render BX1 Core observations. The
browser polls the new read-only hardware/audio/Robot Body endpoints every five
seconds. Device cards expose presence, state, ownership, source, last update,
health and safe details. Audio control surfaces are disabled and labelled
`Future controlled operation`.

## Folder structure

```text
Robot/
  python/
    bx1_management/
      __init__.py
      __main__.py
      server.py
      static/
        index.html
        styles.css
        app.js
    bx1_core/
      core.py
      state.py
      events.py
      telemetry.py
      registry.py
      plugins/
  service/
    bx1-os-alpha.service
  tools/
    run_bx1_os_management.sh
    test_management_interface.py
```

The release builder includes the package and its static files through the
existing recursive `Robot/python` payload selection.

## Runtime architecture

```text
bx1-os-alpha.service
  -> tools/run_bx1_os_management.sh
    -> .venv/bin/python -m bx1_management
      -> BX1Core observer runtime
      -> ManagementApplication
      -> ManagementServer
      -> static management SPA
```

`ManagementApplication` starts only the BX1 OS digital-twin core and retains
the reviewed observer-only configuration. It does not import `web_control`,
start Robot Body loops or request physical hardware access.

`ManagementServer` uses Python's standard threaded HTTP server. It refuses
port 8088, serves only a fixed static-file allowlist and returns 501 for all
POST requests in this milestone.

## HTTP surface

| Route | Purpose |
|---|---|
| `/` and management page routes | Management application shell |
| `/assets/styles.css` | Management theme |
| `/assets/app.js` | Navigation and reusable page components |
| `/api/status` | Existing Alpha observer-canary qualification contract |
| `/api/management/bootstrap` | Read-only interface, system and release scaffold |
| `/api/core/state` | Full state snapshot or incremental changes |
| `/api/core/health` | Aggregate and plugin health |
| `/api/core/plugins` | Discovered plugin inventory |
| `/api/core/services` | Core service projection |
| `/api/core/system` | System, network and robot projection |
| `/api/core/hardware` | Hardware state projection |
| `/api/core/hardware/inventory` | Device inventory and diagnostics |
| `/api/core/audio` | Audio state and devices |
| `/api/core/audio/devices` | Microphone and speaker inventory |
| `/api/core/robot-body` | Sanitised existing Robot Body telemetry |
| `/api/core/robot-body/health` | Existing Robot Body health |

The page routes are:

```text
/dashboard
/system
/services
/hardware
/audio
/brain
/configuration
/logs
/deployment
/diagnostics
/updates
/about
```

## UI design system

The interface uses a self-contained dark theme with no external fonts,
frameworks, CDNs or Bootstrap dependency.

Core tokens cover:

- backgrounds and raised surfaces;
- panel and strong borders;
- primary, muted and secondary text;
- teal, blue, purple, amber, green and red semantic accents;
- spacing, radii, shadows and transitions; and
- expanded and collapsed sidebar widths.

Reusable JavaScript renderers create panels, status badges, buttons, metric
cards, definition lists and empty states. Page definitions are kept separate
from navigation metadata so future API adapters can replace placeholder values
without restructuring the shell.

## Local development

From the repository root in PowerShell:

```powershell
$env:PYTHONPATH = 'Robot/python'
python -m bx1_management `
  --config Robot/python/config.alpha-qualification.json `
  --host 127.0.0.1 `
  --port 18089
```

Open `http://127.0.0.1:18089`.

Port 18089 is used only for local development. The installed Alpha service uses
8089. Never use 8088 for this application.

## Tests

```powershell
python -m unittest Robot/tools/test_management_interface.py -v
python -m unittest Robot/tools/test_bx1_core_telemetry.py -v
python -m unittest Robot/tools/test_hardware_audio_integration.py -v
python -m unittest Robot/tools/test_deployment_system.py -v
```

The tests cover:

- observer-only status and canary compatibility;
- disabled management capabilities;
- all required routes, pages, cards and actions;
- static assets and responsive layout markers;
- reserved port rejection;
- fail-closed POST handling;
- separation from the legacy web application; and
- dedicated systemd launcher selection.

## Future integration rules

Future functionality must be implemented through explicit backend capability
adapters. UI controls must remain disabled until the corresponding capability
is authorised, tested and exposed by the backend.

Privileged functionality must include authentication, authorisation, audit
logging, confirmation and rollback design before activation. It must never
gain control by importing or rewriting the existing Robot Body web interface.
