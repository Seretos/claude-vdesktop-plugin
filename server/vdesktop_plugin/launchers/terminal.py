"""Windows Terminal launcher.

`wt.exe` is a stub that forwards to a singleton WindowsTerminal.exe. The spawn
PID exits immediately, so we always identify the resulting window by a unique
``--title`` tag that we assign at launch time.
"""
from __future__ import annotations

import logging
import uuid
from typing import Optional, Union

from ..pathmap import to_posix, to_windows
from ._common import launch_and_register

log = logging.getLogger("vdesktop.launcher.terminal")


def _tab_args(tab: dict, *, is_first: bool) -> list[str]:
    """Build the wt.exe command tokens for a single tab.

    Each non-first tab begins with the subcommand separator ';' and 'new-tab'.
    """
    parts: list[str] = []
    if not is_first:
        parts.extend([";", "new-tab"])

    shell = (tab.get("shell") or "").lower() or None
    profile = tab.get("profile")
    cwd = tab.get("cwd")
    command = tab.get("command")
    wsl_distro = tab.get("wsl_distro")

    if profile:
        parts.extend(["-p", profile])
    elif shell == "wsl":
        parts.extend(["-p", wsl_distro or "Ubuntu"])
    elif shell == "powershell":
        parts.extend(["-p", "PowerShell"])
    elif shell == "cmd":
        parts.extend(["-p", "Command Prompt"])

    if cwd:
        if shell == "wsl":
            # WSL tab: cwd must be a Windows path that maps into the WSL filesystem.
            if cwd.startswith("/"):
                # POSIX path under the WSL distro → \\wsl$\<distro>\...
                cwd_arg = to_windows(cwd, wsl_distro=wsl_distro)
            else:
                cwd_arg = to_windows(cwd)
        else:
            cwd_arg = to_windows(cwd)
        parts.extend(["-d", cwd_arg])

    if command:
        if shell == "wsl":
            wsl_cmd = ["wsl.exe"]
            if wsl_distro:
                wsl_cmd.extend(["-d", wsl_distro])
            wsl_cmd.extend(["--", "bash", "-lc", command])
            parts.extend(wsl_cmd)
        elif shell == "powershell":
            parts.extend(["powershell.exe", "-NoExit", "-Command", command])
        elif shell == "cmd":
            parts.extend(["cmd.exe", "/K", command])
        else:
            # Profile-default shell — best-effort raw append.
            parts.append(command)

    return parts


def build_wt_args(tabs: list[dict], window_title: str) -> list[str]:
    """Compose the full wt.exe argv: window-creation + per-tab subcommands."""
    args: list[str] = ["wt.exe", "--window", "new"]
    if window_title:
        args.extend(["--title", window_title])
    for i, tab in enumerate(tabs):
        args.extend(_tab_args(tab, is_first=(i == 0)))
    return args


def register(mcp) -> None:
    @mcp.tool()
    def launch_terminal(
        tabs: list[dict],
        slot: Optional[str] = None,
        desktop: Optional[Union[int, str]] = None,
        label: Optional[str] = None,
        window_title: Optional[str] = None,
    ) -> dict:
        """Launch Windows Terminal (wt.exe) with one or more tabs.

        Each tab is a dict:
          {"profile": str?, "cwd": str?, "command": str?,
           "shell": "powershell"|"cmd"|"wsl"|None, "wsl_distro": str?}

        Examples:
          tabs=[{"shell": "wsl", "wsl_distro": "Ubuntu", "cwd": "/home/test"}]
          tabs=[{"shell": "powershell", "cwd": "E:\\\\development", "command": "claude"}]

        A unique --title tag is injected so we can reliably resolve the new
        window (wt.exe forwards to a singleton; the spawn PID exits).
        """
        if not tabs:
            raise ValueError("launch_terminal requires at least one tab")
        title = window_title or f"vdesktop-term-{uuid.uuid4().hex[:6]}"
        args = build_wt_args(tabs, title)
        return launch_and_register(
            args=args,
            app_type="terminal",
            label=label,
            slot=slot,
            desktop=desktop,
            title_hint=title,
            class_filter="CASCADIA_HOSTING_WINDOW_CLASS",
            resolve_timeout_ms=10000,
            pre_spawn_snapshot=True,
        )
