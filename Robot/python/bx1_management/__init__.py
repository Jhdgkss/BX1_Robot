"""BX1 OS Management Interface.

This package is intentionally separate from the legacy Robot Body web
interface. It owns the BX1 OS management surface on the side-by-side port.
"""

from .server import ManagementApplication, ManagementServer

__all__ = ["ManagementApplication", "ManagementServer"]
