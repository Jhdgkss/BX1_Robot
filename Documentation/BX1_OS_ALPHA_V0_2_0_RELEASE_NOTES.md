# BX1 OS Alpha v0.2.0 Release Notes

BX1 OS Alpha v0.2.0 introduces the first architecture release of the BX1 OS
Management Interface.

## Added

- Independent management web application on the BX1 OS port.
- Responsive dark application shell with collapsible sidebar.
- Dashboard, System, Services, Hardware, Brain, Configuration, Logs,
  Deployment, Diagnostics, Updates and About pages.
- Reusable UI components and a self-contained CSS design system.
- Read-only management bootstrap API.
- Observer-canary-compatible status endpoint.
- Dedicated management service launcher.
- Focused backend, routing, safety and interface tests.

## Safety

- The existing Robot Body interface on port 8088 is unchanged.
- The management server refuses port 8088.
- Observer-only hardware isolation remains required.
- Every privileged capability is disabled.
- POST requests fail closed with an architecture-only response.
- No service, power, configuration, log, update or rollback action is
  implemented.

## Release identity

- Version: `0.2.0`
- Tag: `BX1_OS_ALPHA_v0.2.0`
- Service: `bx1-os-alpha.service`
- Management port: `8089`
- Existing protected port: `8088`
