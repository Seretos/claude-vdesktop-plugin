"""Chrome launcher.

Key insight: passing a fresh ``--user-data-dir`` per launch forces Chrome to
spawn a brand-new master/browser process. Otherwise chrome.exe IPCs to the
existing instance and exits, breaking PID-based HWND resolution.
"""
from __future__ import annotations

import logging
import os
import tempfile
from typing import Optional, Union

from ._common import launch_and_register

log = logging.getLogger("vdesktop.launcher.chrome")

_CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
]


def find_chrome() -> str:
    for path in _CHROME_CANDIDATES:
        if path and os.path.isfile(path):
            return path
    raise FileNotFoundError(
        "chrome.exe not found. Install Google Chrome or set the path explicitly via launch_app."
    )


def register(mcp) -> None:
    @mcp.tool()
    def launch_chrome(
        urls: list[str],
        slot: Optional[str] = None,
        desktop: Optional[Union[int, str]] = None,
        label: Optional[str] = None,
        new_user_data_dir: bool = True,
        incognito: bool = False,
    ) -> dict:
        """Launch Google Chrome with one or more tabs in a NEW window.

        Args:
            urls: List of URLs to open as separate tabs.
            slot: Optional slot_id from the last apply_layout to place the window in.
            desktop: Optional target desktop (index, name, or GUID).
            label: Optional human-readable label for later reference.
            new_user_data_dir: REQUIRED True (default) to guarantee a distinct
                browser process — without this, Chrome may IPC to an existing
                instance and the spawn PID exits before HWND resolution.
            incognito: Open in private mode.
        Returns:
            {handle_id, hwnd, pid, label, app_type, desktop_guid, slot_id, bounds, title}
        """
        if not urls:
            raise ValueError("launch_chrome requires at least one URL")
        chrome = find_chrome()
        args = [chrome, "--new-window"]
        if incognito:
            args.append("--incognito")
        if new_user_data_dir:
            udd = tempfile.mkdtemp(prefix="vdesktop-chrome-")
            args.extend(
                [
                    f"--user-data-dir={udd}",
                    "--no-first-run",
                    "--no-default-browser-check",
                ]
            )
        args.extend(urls)

        return launch_and_register(
            args=args,
            app_type="chrome",
            label=label,
            slot=slot,
            desktop=desktop,
            class_filter="Chrome_WidgetWin_1",
            resolve_timeout_ms=10000,
        )
