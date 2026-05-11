"""Monitor enumeration and bounds queries."""
from __future__ import annotations

import ctypes
from ctypes import byref, c_int, c_uint, wintypes
from dataclasses import asdict, dataclass

try:
    import win32api  # type: ignore
    import win32con  # type: ignore
except ImportError:  # pragma: no cover
    win32api = None
    win32con = None


@dataclass
class Monitor:
    index: int
    name: str
    bounds: dict
    work_area: dict
    is_primary: bool
    dpi: int

    def to_dict(self) -> dict:
        return asdict(self)


_MDT_EFFECTIVE_DPI = 0


def _dpi_for_monitor(hmon: int) -> int:
    try:
        dpi_x = c_uint(96)
        dpi_y = c_uint(96)
        ctypes.windll.shcore.GetDpiForMonitor(hmon, _MDT_EFFECTIVE_DPI, byref(dpi_x), byref(dpi_y))
        return int(dpi_x.value)
    except (OSError, AttributeError):
        return 96


def list_monitors() -> list[Monitor]:
    if win32api is None:
        raise RuntimeError("pywin32 is required on Windows")
    monitors: list[Monitor] = []
    for index, mon_tuple in enumerate(win32api.EnumDisplayMonitors()):
        hmon = int(mon_tuple[0])
        info = win32api.GetMonitorInfo(hmon)
        m = info["Monitor"]
        w = info["Work"]
        primary = bool(info["Flags"] & win32con.MONITORINFOF_PRIMARY)
        monitors.append(
            Monitor(
                index=index,
                name=info.get("Device", f"\\\\.\\DISPLAY{index + 1}"),
                bounds={"x": m[0], "y": m[1], "w": m[2] - m[0], "h": m[3] - m[1]},
                work_area={"x": w[0], "y": w[1], "w": w[2] - w[0], "h": w[3] - w[1]},
                is_primary=primary,
                dpi=_dpi_for_monitor(hmon),
            )
        )
    monitors.sort(key=lambda mon: (not mon.is_primary, mon.index))
    # Re-assign indices so the primary is monitor 0.
    for i, mon in enumerate(monitors):
        mon.index = i
    return monitors


def get_monitor(index: int) -> Monitor:
    monitors = list_monitors()
    if not (0 <= index < len(monitors)):
        raise ValueError(f"Monitor {index} not found (have {len(monitors)})")
    return monitors[index]


def monitor_for_hwnd(hwnd: int) -> Monitor:
    """Return the monitor whose work area contains the given HWND."""
    if win32api is None:
        raise RuntimeError("pywin32 is required on Windows")
    rect = win32api.GetWindowRect(hwnd) if hasattr(win32api, "GetWindowRect") else _user32_window_rect(hwnd)
    cx = (rect[0] + rect[2]) // 2
    cy = (rect[1] + rect[3]) // 2
    monitors = list_monitors()
    for mon in monitors:
        b = mon.bounds
        if b["x"] <= cx < b["x"] + b["w"] and b["y"] <= cy < b["y"] + b["h"]:
            return mon
    return monitors[0]


def _user32_window_rect(hwnd: int) -> tuple[int, int, int, int]:
    rect = wintypes.RECT()
    ctypes.windll.user32.GetWindowRect(hwnd, byref(rect))
    return rect.left, rect.top, rect.right, rect.bottom
