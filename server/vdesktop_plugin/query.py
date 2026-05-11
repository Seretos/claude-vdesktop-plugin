"""Title/URL-based window queries — fallback identification when labels aren't
known yet. find_chrome_tab uses UI Automation to walk Chrome's tab strip."""
from __future__ import annotations

import ctypes
import logging
import re
from ctypes import byref, wintypes
from typing import Optional, Union

from . import desktops as desktops_mod
from .tracking import REGISTRY

log = logging.getLogger("vdesktop.query")

_user32 = ctypes.windll.user32
_EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)


def _window_title(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(512)
    _user32.GetWindowTextW(hwnd, buf, 512)
    return buf.value


def _window_classname(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    _user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def register(mcp) -> None:
    @mcp.tool()
    def find_window_by_title(
        pattern: str,
        desktop: Optional[Union[int, str]] = None,
        regex: bool = False,
    ) -> list[dict]:
        """Enumerate visible top-level windows whose title matches `pattern`.

        Args:
            pattern: Substring (default) or regex (if regex=True).
            desktop: Optional desktop filter.
            regex: Treat pattern as a Python regex.
        Returns:
            List of {hwnd, title, class_name, desktop_guid, handle_id?}.
            handle_id is set when the window is already in the registry.
        """
        compiled = re.compile(pattern) if regex else None
        desktop_guid: Optional[str] = None
        if desktop is not None:
            d = desktops_mod.resolve_desktop(desktop)
            desktop_guid = str(d.id)

        results: list[dict] = []

        def callback(hwnd, _lparam):
            if not _user32.IsWindowVisible(hwnd):
                return True
            if _user32.GetWindow(hwnd, 4) != 0:  # GW_OWNER
                return True
            title = _window_title(hwnd)
            if not title:
                return True
            matched = (
                bool(compiled.search(title)) if compiled else (pattern in title)
            )
            if not matched:
                return True
            guid = desktops_mod.desktop_guid_for_hwnd(hwnd)
            if desktop_guid is not None and guid != desktop_guid:
                return True
            tracked = REGISTRY.find_by_hwnd(int(hwnd))
            results.append(
                {
                    "hwnd": int(hwnd),
                    "title": title,
                    "class_name": _window_classname(hwnd),
                    "desktop_guid": guid,
                    "handle_id": tracked.handle_id if tracked else None,
                    "label": tracked.label if tracked else None,
                }
            )
            return True

        _user32.EnumWindows(_EnumWindowsProc(callback), 0)
        return results

    @mcp.tool()
    def find_chrome_tab(
        pattern: str,
        regex: bool = False,
    ) -> list[dict]:
        """Search the tab strips of *all* Chrome windows for a tab whose title
        contains (or matches as regex) `pattern`. Uses UI Automation.

        Returns:
            List of {handle_id, hwnd, tab_index, tab_title, window_title}.
            Adopts the matching Chrome window into the registry if it wasn't
            tracked yet (so the returned handle_id is immediately usable).
        """
        try:
            import uiautomation as uia  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "find_chrome_tab requires the `uiautomation` package on Windows."
            ) from exc

        compiled = re.compile(pattern) if regex else None
        results: list[dict] = []

        for win in uia.GetRootControl().GetChildren():
            if win.ClassName != "Chrome_WidgetWin_1":
                continue
            title = win.Name or ""
            if "Google Chrome" not in title and "Chromium" not in title:
                continue
            try:
                tab_strip = win.TabControl()
                if not tab_strip.Exists(0.5, 0.1):
                    continue
                tabs = tab_strip.GetChildren()
            except Exception as exc:  # noqa: BLE001
                log.debug("Chrome tab strip access failed: %s", exc)
                continue

            for idx, tab in enumerate(tabs):
                tab_title = tab.Name or ""
                matched = (
                    bool(compiled.search(tab_title))
                    if compiled
                    else (pattern.lower() in tab_title.lower())
                )
                if not matched:
                    continue
                hwnd = int(win.NativeWindowHandle)
                tracked = REGISTRY.find_by_hwnd(hwnd)
                if tracked is None:
                    desktop_guid = desktops_mod.desktop_guid_for_hwnd(hwnd)
                    tracked = REGISTRY.register(
                        hwnd=hwnd,
                        pid=0,
                        app_type="chrome",
                        desktop_guid=desktop_guid,
                        title=title,
                    )
                results.append(
                    {
                        "handle_id": tracked.handle_id,
                        "hwnd": hwnd,
                        "tab_index": idx,
                        "tab_title": tab_title,
                        "window_title": title,
                    }
                )

        return results
