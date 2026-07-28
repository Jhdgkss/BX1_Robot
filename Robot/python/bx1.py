"""BX1 OS public entry point.

The stable ``bx1`` proxy is lazy and initially resolves to a safe Digital Twin.
Runtime bootstrap atomically binds it to the validated BX1 OS Alpha graph.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Iterable, Mapping, Optional

from bx1_core import (
    BX1,
    BootstrapResult,
    ServiceFactory,
    bootstrap_runtime,
    create_bx1,
)


class BX1RootProxy:
    """Stable public reference whose service graph can be bound at bootstrap."""

    def __init__(self) -> None:
        self._instance: Optional[BX1] = None

    @property
    def instance(self) -> BX1:
        if self._instance is None:
            self._instance = create_bx1()
        return self._instance

    def bind(self, instance: BX1) -> BX1:
        if not isinstance(instance, BX1):
            raise TypeError("BX1 root proxy can only bind a BX1 instance")
        self._instance = instance
        return instance

    def __getattr__(self, name: str) -> Any:
        return getattr(self.instance, name)


bx1 = BX1RootProxy()


def bootstrap_bx1_runtime(
    config: Optional[Mapping[str, Any]] = None,
    *,
    config_loader: Optional[Callable[[], Mapping[str, Any]]] = None,
    config_source: str = "mapping",
    service_factories: Optional[Mapping[str, ServiceFactory]] = None,
    service_dependencies: Optional[Mapping[str, Iterable[str]]] = None,
    required_services: Optional[Iterable[str]] = None,
    monotonic_clock: Callable[[], float] = time.monotonic,
    wall_clock: Callable[[], float] = time.time,
) -> BootstrapResult:
    result = bootstrap_runtime(
        config,
        config_loader=config_loader,
        config_source=config_source,
        service_factories=service_factories,
        service_dependencies=service_dependencies,
        required_services=required_services,
        monotonic_clock=monotonic_clock,
        wall_clock=wall_clock,
    )
    bx1.bind(result.bx1)
    return result


__all__ = [
    "BX1",
    "BX1RootProxy",
    "BootstrapResult",
    "bootstrap_bx1_runtime",
    "bx1",
    "create_bx1",
]
