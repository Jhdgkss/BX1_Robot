# BX1 OS v0.7.1 Hobby Developer Module Platform

## Persistent modules and safe boundary

Bundled examples live in `Robot/modules`, but user modules install to
`/home/arduino/BX1_modules/`. OS replacement never overwrites that directory.
The Module Manager can install a ZIP, reload, enable, disable, remove and clear
fault display for user modules. Bundled modules remain protected.

Only these capabilities are accepted: `events.publish`, `events.subscribe`,
`widgets.publish`, `widgets.action`, and `led.status.request`. Raw GPIO, MCU,
camera, servo, motor, wheel, balance, drive, shell and browser APIs are denied.
The event bus and widget data are bounded; modules cannot supply HTML or JavaScript.

## Manifest and lifecycle

`module.json` is a root ZIP file and uses `bx1.module.manifest.v1`:

```json
{"schema":"bx1.module.manifest.v1","id":"example","name":"Example","version":"1.0.0","entrypoint":"module.py:Module","capabilities":["widgets.publish"],"subscriptions":[]}
```

The class implements `start(context)`, `health()` and `stop()`. The manager
reports load, lifecycle and widget faults without interrupting other modules.

## Declarative widgets

`context.widget()` accepts `metric`, `panel`, `chart`, `button` or `form` with
an id, title, dashboard/modules placement, health and bounded `data`. Charts
have at most 60 numeric values; forms have at most six simple named fields.

```python
def start(self, context):
    context.widget({"id":"state","type":"metric","title":"Example",
                    "placement":"dashboard","data":{"label":"State","value":"Ready"}})
```

For an action, declare `widgets.action`, call `context.action("refresh", fn)`,
and reference that action from a button/form widget. BX1 OS routes it only to
the declaring enabled module and passes bounded validated field values.

## Battery LED walkthrough

`battery_led` subscribes only to `battery.status`, shows battery percentage,
charging state and intended LED state, and may request
`led.status.request(target="status", colour=..., effect="solid")`. BX1 OS
validates only the high-level target, permitted colour and effect, then sends a
loopback request to the Body. The Body must independently validate availability
and applies any physical output. If the Body endpoint is absent/unavailable,
the module reports **Body LED capability unavailable**; it never claims hardware
changed and never uses raw MCU/pin calls.

## PC package/install/update workflow

```powershell
python Robot/tools/scaffold_bx1_module.py my_status
python Robot/tools/bx1_module.py package Robot/modules/my_status my_status.zip
scp my_status.zip arduino@LEO:/tmp/my_status.zip
ssh arduino@LEO "python3 /home/arduino/BX1_OS/tools/bx1_module.py install /tmp/my_status.zip --modules-root /home/arduino/BX1_modules"
```

Uploading a ZIP in Module Manager uses the same safe path and manifest checks.
Install the next ZIP with the same module id to update; then select Reload.
No package may contain absolute paths, `..`, more than 32 files, or exceed 2 MiB.
