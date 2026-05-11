"""Adoption — pulling existing top-level windows (not spawned by the MCP) into
the handle registry so they can be addressed like first-class tracked windows."""
from __future__ import annotations

import ctypes
import logging
from ctypes import byref, wintypes
from typing import Optional, Union

from . import desktops as desktops_mod
from .tracking import REGISTRY

log = logging.getLogger("vdesktop.adoption")

_user32 = ctypes.windll.user32
_EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)


def _window_pid(hwnd: int) -> int:
    pid = wintypes.DWORD()
    _user32.GetWindowThreadProcessId(hwnd, byref(pid))
    return int(pid.value)


def _window_title(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(512)
    _user32.GetWindowTextW(hwnd, buf, 512)
    return buf.value


def _window_classname(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    _user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def _window_rect(hwnd: int) -> dict:
    rect = wintypes.RECT()
    _user32.GetWindowRect(hwnd, byref(rect))
    return {
        "x": rect.left,
        "y": rect.top,
        "w": rect.right - rect.left,
        "h": rect.bottom - rect.top,
    }


def _classify(class_name: str, title: str) -> str:
    cn = class_name.lower()
    if cn == "chrome_widgetwin_1":
        if "visual studio code" in title.lower():
            return "vscode"
        return "chrome"
    if "cascadia" in cn:
        return "terminal"
    return "unknown"


def list_unmanaged_windows_impl(desktop_guid: Optional[str] = None) -> list[dict]:
    """Return all top-level, visible, non-owned, *titled* windows not already
    in the registry. If desktop_guid is given, filter by current desktop GUID."""
    known: set[int] = {tw.hwnd for tw in REGISTRY.all()}
    results: list[dict] = []

    def callback(hwnd, _lparam):
        if hwnd in known:
            return True
        if not _user32.IsWindowVisible(hwnd):
            return True
        if _user32.GetWindow(hwnd, 4) != 0:  # GW_OWNER
            return True
        title = _window_title(hwnd)
        if not title:
            return True
        class_name = _window_classname(hwnd)
        guid = desktops_mod.desktop_guid_for_hwnd(hwnd)
        if desktop_guid is not None and guid != desktop_guid:
            return True
        results.append(
            {
                "hwnd": int(hwnd),
                "pid": _window_pid(hwnd),
                "title": title,
                "class_name": class_name,
                "app_type": _classify(class_name, title),
                "desktop_guid": guid,
                "bounds": _window_rect(hwnd),
            }
        )
        return True

    _user32.EnumWindows(_EnumWindowsProc(callback), 0)
    return results


def register(mcp) -> None:
    @mcp.tool()
    def list_unmanaged_windows(
        desktop: Optional[Union[int, str]] = None,
    ) -> list[dict]:
        """List visible top-level windows that are NOT currently in the
        registry. Useful before adopting external windows. Filter by desktop
        if given."""
        desktop_guid: Optional[str] = None
        if desktop is not None:
            d = desktops_mod.resolve_desktop(desktop)
            desktop_guid = str(d.id)
        return list_unmanaged_windows_impl(desktop_guid)

    @mcp.tool()
    def adopt_window(
        hwnd: int,
        label: Optional[str] = None,
        app_type_hint: Optional[str] = None,
    ) -> dict:
        """Add an existing HWND to the registry so it can be moved, focused,
        labeled, and tracked like a launched window. Returns the new handle_id.

        `app_type_hint` overrides the auto-classification (chrome / vscode /
        terminal / unknown) — pass it when you know the window's identity."""
        existing = REGISTRY.find_by_hwnd(int(hwnd))
        if existing is not None:
            if label:
                REGISTRY.relabel(existing.handle_id, label)
            return {"handle_id": existing.handle_id, "already_tracked": True}

        title = _window_title(int(hwnd))
        class_name = _window_classname(int(hwnd))
        app_type = app_type_hint or _classify(class_name, title)
        desktop_guid = desktops_mod.desktop_guid_for_hwnd(int(hwnd))
        bounds = _window_rect(int(hwnd))
        pid = _window_pid(int(hwnd))

        tw = REGISTRY.register(
            hwnd=int(hwnd),
            pid=pid,
            app_type=app_type,
            label=label,
            desktop_guid=desktop_guid,
            bounds=bounds,
            title=title,
        )
        return {
            "handle_id": tw.handle_id,
            "hwnd": tw.hwnd,
            "pid": tw.pid,
            "label": tw.label,
            "app_type": tw.app_type,
            "desktop_guid": tw.desktop_guid,
            "bounds": tw.bounds,
            "title": tw.title,
        }

    @mcp.tool()
    def release_window(handle_id: str) -> dict:
        """Remove a window from the registry. The window itself stays open."""
        tw = REGISTRY.remove(handle_id)
        return {"handle_id": handle_id, "released": tw is not None}
