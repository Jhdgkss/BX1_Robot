# BX1 OS v0.7 Modular Runtime Developer Preview

## Scope and safety boundary

The runtime loads local manifest-first modules from `Robot/modules`. Modules
receive only a bounded in-process event gateway. Direct motor, balance, raw
MCU, raw servo and raw camera access are not capability types and are rejected
at manifest validation. The Module Manager on port 8089 is read-only.

## Module contract

Every module directory has a `module.json` with schema
`bx1.module.manifest.v1`, a lowercase `id`, an `entrypoint` of the form
`module.py:Class`, and declared `events.publish` / `events.subscribe`
capabilities. A class implements `start(context)`, `health()` and `stop()`.
Subscriptions must be declared in the manifest.

The event queue is bounded. On overflow the oldest queued event is discarded
and the drop count is visible in the Module Manager. Module callback failures
are contained so they cannot stop the host runtime.

## Scaffold and local check

```powershell
python Robot/tools/scaffold_bx1_module.py example_indicator
$env:PYTHONPATH = 'Robot/python'
python -m unittest Robot/tools/test_modular_runtime.py -v
```

The included `speech_indicator` example reacts to `speech.started` and
`speech.finished` by publishing display intent only. It controls no LED,
speaker or other hardware.

Developer Preview module installation, enable/disable controls, persistent
configuration and all hardware capabilities are intentionally out of scope.
