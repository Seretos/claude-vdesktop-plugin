"""Virtual-desktop operations via pyvda."""
from __future__ import annotations

import logging
from typing import Optional, Union

from .tracking import REGISTRY

log = logging.getLogger("vdesktop.desktops")

try:
    import pyvda  # type: ignore
except ImportError as exc:  # pragma: no cover
    pyvda = None  # type: ignore
    _pyvda_error: Optional[Exception] = exc
else:
    _pyvda_error = None


DesktopRef = Union[int, str]


def _require() -> None:
    if pyvda is None:
        raise RuntimeError(
            f"pyvda is required but failed to import: {_pyvda_error}. "
            "Install on the Windows host with: pip install pyvda"
        )


def _current_guid() -> str:
    return str(pyvda.VirtualDesktop.current().id)


def _info(desktop, index: int, current_guid: Optional[str] = None) -> dict:
    name = getattr(desktop, "name", None) or f"Desktop {index + 1}"
    guid = str(desktop.id)
    return {
        "index": index,
        "name": name,
        "guid": guid,
        "is_current": (current_guid is not None and guid == current_guid),
    }


def list_desktops_impl() -> list[dict]:
    _require()
    desktops = pyvda.get_virtual_desktops()
    cur = _current_guid()
    return [_info(d, i, cur) for i, d in enumerate(desktops)]


def resolve_desktop(target: Optional[DesktopRef]):
    """Resolve a 0-based index, a name, or a GUID to a pyvda VirtualDesktop.

    `None` returns the current desktop.
    """
    _require()
    if target is None:
        return pyvda.VirtualDesktop.current()
    desktops = pyvda.get_virtual_desktops()
    if isinstance(target, int):
        if not (0 <= target < len(desktops)):
            raise ValueError(f"Desktop index {target} out of range (have {len(desktops)})")
        return desktops[target]
    if isinstance(target, str):
        stripped = target.strip()
        if stripped.lstrip("-").isdigit():
            idx = int(stripped)
            if not (0 <= idx < len(desktops)):
                raise ValueError(f"Desktop index {idx} out of range (have {len(desktops)})")
            return desktops[idx]
        for d in desktops:
            if getattr(d, "name", None) == stripped or str(d.id) == stripped:
                return d
    raise ValueError(f"Unknown desktop reference: {target!r}")


def _rename(desktop, name: str) -> None:
    # pyvda exposes either rename(name) or a settable .name property depending
    # on version — try both.
    try:
        if hasattr(desktop, "rename"):
            desktop.rename(name)
            return
        desktop.name = name  # type: ignore[attr-defined]
    except Exception as exc:  # noqa: BLE001
        log.warning("Renaming desktop failed: %s", exc)


def register(mcp) -> None:
    @mcp.tool()
    def list_desktops() -> list[dict]:
        """List all virtual desktops with their index (0-based), name, GUID,
        and whether each is the currently active desktop."""
        return list_desktops_impl()

    @mcp.tool()
    def get_current_desktop() -> dict:
        """Return the currently active virtual desktop."""
        _require()
        current = pyvda.VirtualDesktop.current()
        desktops = pyvda.get_virtual_desktops()
        index = next(
            (i for i, d in enumerate(desktops) if str(d.id) == str(current.id)),
            0,
        )
        return _info(current, index, str(current.id))

    @mcp.tool()
    def create_desktop(name: Optional[str] = None) -> dict:
        """Create a new virtual desktop and return its info. If `name` is given,
        the desktop is renamed immediately (Windows 11)."""
        _require()
        new_desktop = pyvda.VirtualDesktop.create()
        if name:
            _rename(new_desktop, name)
        desktops = pyvda.get_virtual_desktops()
        index = next(
            (i for i, d in enumerate(desktops) if str(d.id) == str(new_desktop.id)),
            len(desktops) - 1,
        )
        return _info(new_desktop, index, _current_guid())

    @mcp.tool()
    def delete_desktop(
        target: DesktopRef,
        fallback_desktop: Optional[DesktopRef] = None,
    ) -> dict:
        """Delete a virtual desktop. Windows moves its windows to `fallback_desktop`
        (or to the desktop on the left by default)."""
        _require()
        desktop = resolve_desktop(target)
        fallback = resolve_desktop(fallback_desktop) if fallback_desktop is not None else None
        try:
            if fallback is not None and hasattr(desktop, "remove"):
                desktop.remove(fallback)
            else:
                desktop.remove()
        except TypeError:
            # Some pyvda versions: remove() takes no args; the windows go to
            # the desktop on the left automatically.
            desktop.remove()
        return {"deleted_guid": str(desktop.id), "remaining": list_desktops_impl()}

    @mcp.tool()
    def switch_to_desktop(target: DesktopRef) -> dict:
        """Switch the foreground to the given desktop."""
        _require()
        desktop = resolve_desktop(target)
        desktop.go()
        return get_current_desktop()  # type: ignore[no-any-return]

    @mcp.tool()
    def rename_desktop(target: DesktopRef, new_name: str) -> dict:
        """Rename a virtual desktop. Windows 11 only."""
        _require()
        desktop = resolve_desktop(target)
        _rename(desktop, new_name)
        desktops = pyvda.get_virtual_desktops()
        index = next(
            (i for i, d in enumerate(desktops) if str(d.id) == str(desktop.id)),
            0,
        )
        return _info(desktop, index, _current_guid())

    # -- Pinning (cross-desktop visibility) ---------------------------------

    @mcp.tool()
    def pin_window_all_desktops(handle_id: str) -> dict:
        """Pin a tracked window so it is visible on every virtual desktop."""
        _require()
        tw = REGISTRY.require(handle_id)
        view = pyvda.AppView(hwnd=tw.hwnd)
        view.pin()
        return {"handle_id": handle_id, "window_pinned": bool(view.is_pinned())}

    @mcp.tool()
    def unpin_window(handle_id: str) -> dict:
        """Unpin a tracked window."""
        _require()
        tw = REGISTRY.require(handle_id)
        view = pyvda.AppView(hwnd=tw.hwnd)
        view.unpin()
        return {"handle_id": handle_id, "window_pinned": bool(view.is_pinned())}

    @mcp.tool()
    def pin_app_all_desktops(handle_id: str) -> dict:
        """Pin the application (every window of its app-user-model-ID) to all
        desktops, not just one window. Use `pin_window_all_desktops` for a
        single-window pin."""
        _require()
        tw = REGISTRY.require(handle_id)
        view = pyvda.AppView(hwnd=tw.hwnd)
        view.pin_app()
        return {"handle_id": handle_id, "app_pinned": bool(view.is_pinned_app())}

    @mcp.tool()
    def unpin_app(handle_id: str) -> dict:
        """Unpin the application of the given window."""
        _require()
        tw = REGISTRY.require(handle_id)
        view = pyvda.AppView(hwnd=tw.hwnd)
        view.unpin_app()
        return {"handle_id": handle_id, "app_pinned": bool(view.is_pinned_app())}

    @mcp.tool()
    def is_pinned(handle_id: str) -> dict:
        """Return both the window-pinned and app-pinned state for a tracked window."""
        _require()
        tw = REGISTRY.require(handle_id)
        view = pyvda.AppView(hwnd=tw.hwnd)
        return {
            "handle_id": handle_id,
            "window_pinned": bool(view.is_pinned()),
            "app_pinned": bool(view.is_pinned_app()),
        }


def desktop_guid_for_hwnd(hwnd: int) -> Optional[str]:
    """Return the GUID of the desktop currently holding the given HWND."""
    _require()
    try:
        view = pyvda.AppView(hwnd=hwnd)
        return str(view.desktop.id)
    except Exception as exc:  # noqa: BLE001
        log.debug("desktop_guid_for_hwnd failed for %s: %s", hwnd, exc)
        return None


def move_hwnd_to_desktop(hwnd: int, desktop_ref: DesktopRef) -> str:
    """Move an HWND to the given desktop. Returns the new desktop GUID."""
    _require()
    desktop = resolve_desktop(desktop_ref)
    view = pyvda.AppView(hwnd=hwnd)
    view.move(desktop)
    return str(desktop.id)
