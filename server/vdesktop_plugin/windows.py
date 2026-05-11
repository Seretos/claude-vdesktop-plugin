"""Window-positioning primitives: SetWindowPos with DWM-shadow correction,
focus, close, minimize/maximize/restore. Plus the public MCP move_window tool."""
from __future__ import annotations

import ctypes
import logging
import time
from ctypes import byref, wintypes
from typing import Optional, Union

from . import desktops as desktops_mod
from .layouts import lookup_slot
from .monitors import monitor_for_hwnd
from .tracking import REGISTRY

log = logging.getLogger("vdesktop.windows")

_user32 = ctypes.windll.user32
_dwmapi = ctypes.windll.dwmapi

DWMWA_EXTENDED_FRAME_BOUNDS = 9

SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040
SWP_ASYNCWINDOWPOS = 0x4000

WM_CLOSE = 0x0010

SW_RESTORE = 9
SW_MINIMIZE = 6
SW_MAXIMIZE = 3
SW_SHOWNORMAL = 1


def _get_window_rect(hwnd: int) -> wintypes.RECT:
    rect = wintypes.RECT()
    _user32.GetWindowRect(hwnd, byref(rect))
    return rect


def _get_extended_frame(hwnd: int) -> Optional[wintypes.RECT]:
    rect = wintypes.RECT()
    hr = _dwmapi.DwmGetWindowAttribute(
        hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, byref(rect), ctypes.sizeof(rect)
    )
    if hr != 0:
        return None
    return rect


def _shadow_margins(hwnd: int) -> tuple[int, int, int, int]:
    """Return (left, top, right, bottom) invisible margin sizes.

    Positive value means the window-rect extends *past* the visible frame on
    that side by that many pixels (drop shadow / DWM compositor inset).
    """
    win = _get_window_rect(hwnd)
    ext = _get_extended_frame(hwnd)
    if ext is None:
        return (0, 0, 0, 0)
    return (
        ext.left - win.left,
        ext.top - win.top,
        win.right - ext.right,
        win.bottom - ext.bottom,
    )


def move_to_bounds(hwnd: int, bounds: dict) -> dict:
    """Move/resize a window so its **visible** frame matches `bounds` exactly,
    compensating for DWM drop-shadow margins. Returns the bounds actually
    applied (visible).
    """
    sx, sy, sr, sb = _shadow_margins(hwnd)
    x = int(bounds["x"]) - sx
    y = int(bounds["y"]) - sy
    w = int(bounds["w"]) + sx + sr
    h = int(bounds["h"]) + sy + sb
    flags = SWP_NOZORDER | SWP_NOACTIVATE | SWP_SHOWWINDOW
    _user32.SetWindowPos(hwnd, 0, x, y, w, h, flags)
    return {
        "x": int(bounds["x"]),
        "y": int(bounds["y"]),
        "w": int(bounds["w"]),
        "h": int(bounds["h"]),
    }


def focus_window_hwnd(hwnd: int) -> None:
    """Bring an HWND to the foreground, switching its virtual desktop first if needed."""
    # Switch desktops if necessary.
    try:
        import pyvda  # type: ignore

        view = pyvda.AppView(hwnd=hwnd)
        if not view.is_on_current_desktop():
            view.switch_to()
    except Exception as exc:  # noqa: BLE001
        log.debug("focus: desktop switch fallback: %s", exc)
    # Restore if minimized.
    placement = ctypes.create_string_buffer(44)
    try:
        _user32.ShowWindow(hwnd, SW_RESTORE)
    except Exception:  # noqa: BLE001
        pass
    _user32.SetForegroundWindow(hwnd)


def close_window_hwnd(hwnd: int, *, force: bool = False) -> None:
    if force:
        _user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
        time.sleep(0.3)
        # If still alive, terminate the process. (Best-effort; we don't have the PID here.)
    else:
        _user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)


def _resolve_target(handle_id: str, target: dict) -> tuple[Optional[dict], Optional[str]]:
    """Translate a move target into (bounds, desktop_ref).

    Accepted target shapes:
      {"slot": "<slot_id>", "monitor": <int>?}   → bounds from last layout
      {"bounds": {"x":..,"y":..,"w":..,"h":..}}  → explicit bounds
      {"desktop": <ref>}                          → move across desktops only
    Combinations possible: {"slot": "right", "desktop": "test-1"}.
    """
    bounds: Optional[dict] = None
    desktop_ref: Optional[str] = None

    if "bounds" in target:
        bounds = dict(target["bounds"])
    elif "slot" in target:
        tw = REGISTRY.get(handle_id)
        guid = tw.desktop_guid if tw else None
        slot = lookup_slot(target["slot"], desktop_guid=guid)
        if slot is None:
            raise KeyError(f"Slot {target['slot']!r} unknown — apply_layout first")
        bounds = slot["bounds"]
    if "desktop" in target:
        desktop_ref = target["desktop"]
    return bounds, desktop_ref


def register(mcp) -> None:
    @mcp.tool()
    def list_windows(
        desktop: Optional[Union[int, str]] = None,
        include_unmanaged: bool = False,
    ) -> list[dict]:
        """List tracked windows (and optionally unmanaged top-level windows).

        Filters by desktop GUID if `desktop` is given. Each entry includes
        handle_id, label, app_type, title, hwnd, pid, desktop_guid, monitor,
        bounds, and is_pinned.
        """
        from . import adoption  # late import to avoid cycles

        desktop_guid: Optional[str] = None
        if desktop is not None:
            d = desktops_mod.resolve_desktop(desktop)
            desktop_guid = str(d.id)

        results: list[dict] = []
        for tw in REGISTRY.all():
            if desktop_guid and tw.desktop_guid and tw.desktop_guid != desktop_guid:
                continue
            try:
                rect = _get_window_rect(tw.hwnd)
                bounds = {
                    "x": rect.left,
                    "y": rect.top,
                    "w": rect.right - rect.left,
                    "h": rect.bottom - rect.top,
                }
            except Exception:  # noqa: BLE001
                bounds = tw.bounds
            try:
                title_buf = ctypes.create_unicode_buffer(512)
                _user32.GetWindowTextW(tw.hwnd, title_buf, 512)
                title = title_buf.value
            except Exception:  # noqa: BLE001
                title = tw.title
            results.append(
                {
                    "handle_id": tw.handle_id,
                    "label": tw.label,
                    "app_type": tw.app_type,
                    "title": title,
                    "hwnd": tw.hwnd,
                    "pid": tw.pid,
                    "desktop_guid": tw.desktop_guid,
                    "slot_id": tw.slot_id,
                    "bounds": bounds,
                }
            )

        if include_unmanaged:
            results.extend(adoption.list_unmanaged_windows_impl(desktop_guid))

        return results

    @mcp.tool()
    def move_window(handle_id: str, target: dict) -> dict:
        """Move a tracked window.

        `target` keys (combinable):
          - "slot": slot_id from the last apply_layout (uses last layout for the
            window's current desktop, or the global last layout).
          - "bounds": explicit {x, y, w, h}.
          - "desktop": move the window to a different desktop (int index, name,
            or GUID).
        """
        tw = REGISTRY.require(handle_id)
        bounds, desktop_ref = _resolve_target(handle_id, target)

        if desktop_ref is not None:
            new_guid = desktops_mod.move_hwnd_to_desktop(tw.hwnd, desktop_ref)
            tw.desktop_guid = new_guid

        if bounds is not None:
            applied = move_to_bounds(tw.hwnd, bounds)
            slot_id = target.get("slot") if "slot" in target else tw.slot_id
            REGISTRY.update_bounds(handle_id, applied, slot_id=slot_id)
            return {"handle_id": handle_id, "bounds": applied, "desktop_guid": tw.desktop_guid}

        return {"handle_id": handle_id, "bounds": tw.bounds, "desktop_guid": tw.desktop_guid}

    @mcp.tool()
    def resize_window(handle_id: str, bounds: dict) -> dict:
        """Resize/reposition a tracked window to the given visible bounds
        (DWM shadows compensated)."""
        tw = REGISTRY.require(handle_id)
        applied = move_to_bounds(tw.hwnd, bounds)
        REGISTRY.update_bounds(handle_id, applied)
        return {"handle_id": handle_id, "bounds": applied}

    @mcp.tool()
    def close_window(handle_id: str, force: bool = False) -> dict:
        """Send WM_CLOSE to the window. Removes it from the registry."""
        tw = REGISTRY.require(handle_id)
        close_window_hwnd(tw.hwnd, force=force)
        REGISTRY.remove(handle_id)
        return {"handle_id": handle_id, "closed": True}

    @mcp.tool()
    def focus_window(handle_id: str) -> dict:
        """Bring a tracked window to the foreground. Switches virtual desktops
        first if the window is on a different one."""
        tw = REGISTRY.require(handle_id)
        focus_window_hwnd(tw.hwnd)
        return {"handle_id": handle_id, "focused": True}

    @mcp.tool()
    def relabel_window(handle_id: str, new_label: Optional[str]) -> dict:
        """Change (or clear) a tracked window's label."""
        REGISTRY.require(handle_id)
        REGISTRY.relabel(handle_id, new_label)
        return {"handle_id": handle_id, "label": new_label}

    @mcp.tool()
    def minimize_window(handle_id: str) -> dict:
        tw = REGISTRY.require(handle_id)
        _user32.ShowWindow(tw.hwnd, SW_MINIMIZE)
        return {"handle_id": handle_id, "state": "minimized"}

    @mcp.tool()
    def maximize_window(handle_id: str) -> dict:
        tw = REGISTRY.require(handle_id)
        _user32.ShowWindow(tw.hwnd, SW_MAXIMIZE)
        return {"handle_id": handle_id, "state": "maximized"}

    @mcp.tool()
    def restore_window(handle_id: str) -> dict:
        tw = REGISTRY.require(handle_id)
        _user32.ShowWindow(tw.hwnd, SW_RESTORE)
        return {"handle_id": handle_id, "state": "restored"}
