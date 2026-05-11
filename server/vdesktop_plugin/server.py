"""FastMCP application entry point — wires up the tool modules."""
from __future__ import annotations

import logging
import os
import sys

from mcp.server.fastmcp import FastMCP

log = logging.getLogger("vdesktop")

mcp = FastMCP("vdesktop")


def _init_com() -> None:
    """Initialize COM on the main thread.

    pyvda / IVirtualDesktopManagerInternal require COM. FastMCP runs synchronous
    tool handlers on the asyncio loop's default executor; we need apartment-init
    on the main thread before any virtual-desktop call.
    """
    try:
        import comtypes
        comtypes.CoInitialize()
    except Exception as exc:  # noqa: BLE001
        log.warning("CoInitialize failed: %s", exc)


def main() -> None:
    level_name = os.environ.get("VDESKTOP_LOG", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, level_name, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )
    log.info(
        "vdesktop MCP server starting (plugin_root=%s, python=%s)",
        os.environ.get("VDESKTOP_PLUGIN_ROOT", "?"),
        sys.version.split()[0],
    )

    _init_com()

    # Import + register all tool modules. Order is meaningful only insofar as
    # later modules can call helpers from earlier ones (no circular wiring).
    from . import adoption, desktops, layouts, query
    from . import windows as window_ops
    from .launchers import register as register_launchers

    desktops.register(mcp)
    layouts.register(mcp)
    window_ops.register(mcp)
    register_launchers(mcp)
    adoption.register(mcp)
    query.register(mcp)

    mcp.run()
