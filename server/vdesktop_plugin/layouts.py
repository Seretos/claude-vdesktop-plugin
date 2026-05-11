"""Layout presets and custom spec parser → concrete slot rectangles.

A LayoutSpec is either a single-monitor dict or a list of single-monitor dicts.
Each single-monitor dict has a `type` discriminator:

  preset:  {"type": "preset",  "name": "three-columns", "monitor": 0}
  columns: {"type": "columns", "monitor": 0, "splits": [15, 35, 50]}
  rows:    {"type": "rows",    "monitor": 0, "splits": [50, 50]}
  grid:    {"type": "grid",    "monitor": 0, "cols": 2, "rows": 2}
  regions: {"type": "regions", "monitor": 0,
            "regions": [{"id": "left", "x_pct": 0, "y_pct": 0, "w_pct": 30, "h_pct": 100}, ...]}

Result: list of {"slot_id": str, "monitor": int, "bounds": {x,y,w,h}}.
"""
from __future__ import annotations

import logging
from typing import Any, Optional, Union

from .monitors import Monitor, get_monitor, list_monitors

log = logging.getLogger("vdesktop.layouts")

LayoutSpec = Union[dict, list]

# Preset catalog. Values are functions monitor → list of {slot_id, bounds_pct}.
_Slot = dict


def _columns(splits: list[float], slot_prefix: str = "col") -> list[_Slot]:
    total = sum(splits)
    if total <= 0:
        raise ValueError("column splits must sum to > 0")
    norm = [s / total * 100 for s in splits]
    slots: list[_Slot] = []
    x = 0.0
    for i, w in enumerate(norm):
        slots.append(
            {
                "slot_id": f"{slot_prefix}-{i}",
                "x_pct": x,
                "y_pct": 0.0,
                "w_pct": w,
                "h_pct": 100.0,
            }
        )
        x += w
    return slots


def _rows(splits: list[float], slot_prefix: str = "row") -> list[_Slot]:
    total = sum(splits)
    if total <= 0:
        raise ValueError("row splits must sum to > 0")
    norm = [s / total * 100 for s in splits]
    slots: list[_Slot] = []
    y = 0.0
    for i, h in enumerate(norm):
        slots.append(
            {
                "slot_id": f"{slot_prefix}-{i}",
                "x_pct": 0.0,
                "y_pct": y,
                "w_pct": 100.0,
                "h_pct": h,
            }
        )
        y += h
    return slots


def _grid(cols: int, rows: int) -> list[_Slot]:
    if cols <= 0 or rows <= 0:
        raise ValueError("grid cols/rows must be positive")
    w_pct = 100 / cols
    h_pct = 100 / rows
    slots: list[_Slot] = []
    for r in range(rows):
        for c in range(cols):
            slots.append(
                {
                    "slot_id": f"r{r}c{c}",
                    "x_pct": c * w_pct,
                    "y_pct": r * h_pct,
                    "w_pct": w_pct,
                    "h_pct": h_pct,
                }
            )
    return slots


def _named_columns(names: list[str], splits: list[float]) -> list[_Slot]:
    slots = _columns(splits)
    for slot, name in zip(slots, names):
        slot["slot_id"] = name
    return slots


PRESETS: dict[str, callable] = {
    "fullscreen": lambda: [
        {"slot_id": "full", "x_pct": 0, "y_pct": 0, "w_pct": 100, "h_pct": 100}
    ],
    "two-columns": lambda: _named_columns(["left", "right"], [50, 50]),
    "two-columns-golden": lambda: _named_columns(["left", "right"], [38, 62]),
    "three-columns": lambda: _named_columns(
        ["left", "center", "right"], [33.34, 33.33, 33.33]
    ),
    "three-columns-wide-center": lambda: _named_columns(
        ["left", "center", "right"], [25, 50, 25]
    ),
    "four-columns": lambda: _columns([25, 25, 25, 25]),
    "grid-2x2": lambda: _grid(2, 2),
    "grid-3x2": lambda: _grid(3, 2),
    "grid-3x3": lambda: _grid(3, 3),
    "main-sidebar": lambda: _named_columns(["main", "sidebar"], [70, 30]),
    "main-stack": lambda: [
        {"slot_id": "main", "x_pct": 0, "y_pct": 0, "w_pct": 75, "h_pct": 100},
        {"slot_id": "stack-top", "x_pct": 75, "y_pct": 0, "w_pct": 25, "h_pct": 50},
        {"slot_id": "stack-bottom", "x_pct": 75, "y_pct": 50, "w_pct": 25, "h_pct": 50},
    ],
    "top-bottom-split": lambda: _rows([50, 50]),
}


PRESET_DESCRIPTIONS: dict[str, str] = {
    "fullscreen": "single window covers the entire work area",
    "two-columns": "50/50 vertical split (slots: left, right)",
    "two-columns-golden": "38/62 vertical split (slots: left, right)",
    "three-columns": "33/33/33 vertical split (slots: left, center, right)",
    "three-columns-wide-center": "25/50/25 (slots: left, center, right)",
    "four-columns": "25/25/25/25 (slots: col-0..col-3)",
    "grid-2x2": "2x2 grid (slots: r0c0, r0c1, r1c0, r1c1)",
    "grid-3x2": "3 columns x 2 rows",
    "grid-3x3": "3x3 grid",
    "main-sidebar": "70/30 split (slots: main, sidebar)",
    "main-stack": "75% main + two stacked 25%-wide panels right (slots: main, stack-top, stack-bottom)",
    "top-bottom-split": "50/50 horizontal split (slots: row-0, row-1)",
}


def _bounds_from_pct(monitor: Monitor, pct: dict) -> dict:
    w = monitor.work_area
    x = int(round(w["x"] + (pct["x_pct"] / 100.0) * w["w"]))
    y = int(round(w["y"] + (pct["y_pct"] / 100.0) * w["h"]))
    width = int(round((pct["w_pct"] / 100.0) * w["w"]))
    height = int(round((pct["h_pct"] / 100.0) * w["h"]))
    return {"x": x, "y": y, "w": width, "h": height}


def _resolve_single(spec: dict, mon_lookup: dict[int, Monitor]) -> list[dict]:
    spec_type = spec.get("type", "").lower()
    mon_idx = int(spec.get("monitor", 0))
    if mon_idx not in mon_lookup:
        raise ValueError(f"Monitor {mon_idx} unknown (have {sorted(mon_lookup)})")
    monitor = mon_lookup[mon_idx]

    if spec_type == "preset":
        name = spec.get("name")
        if name not in PRESETS:
            raise ValueError(
                f"Unknown preset {name!r}; available: {sorted(PRESETS)}"
            )
        pct_slots = PRESETS[name]()
    elif spec_type == "columns":
        pct_slots = _columns(list(spec.get("splits", [])))
    elif spec_type == "rows":
        pct_slots = _rows(list(spec.get("splits", [])))
    elif spec_type == "grid":
        pct_slots = _grid(int(spec.get("cols", 0)), int(spec.get("rows", 0)))
    elif spec_type == "regions":
        regions = spec.get("regions", [])
        pct_slots = [
            {
                "slot_id": str(r["id"]),
                "x_pct": float(r["x_pct"]),
                "y_pct": float(r["y_pct"]),
                "w_pct": float(r["w_pct"]),
                "h_pct": float(r["h_pct"]),
            }
            for r in regions
        ]
    else:
        raise ValueError(f"Unknown layout spec type: {spec_type!r}")

    return [
        {
            "slot_id": slot["slot_id"],
            "monitor": monitor.index,
            "bounds": _bounds_from_pct(monitor, slot),
        }
        for slot in pct_slots
    ]


def compute_slots(spec: LayoutSpec) -> list[dict]:
    """Resolve a LayoutSpec into concrete slot rectangles. Does not move anything."""
    monitors = {m.index: m for m in list_monitors()}
    if isinstance(spec, list):
        slots: list[dict] = []
        seen: set[tuple[int, str]] = set()
        for sub in spec:
            for s in _resolve_single(sub, monitors):
                key = (s["monitor"], s["slot_id"])
                if key in seen:
                    # Disambiguate same slot-id across monitors with a suffix.
                    s["slot_id"] = f"{s['slot_id']}@m{s['monitor']}"
                    key = (s["monitor"], s["slot_id"])
                seen.add(key)
                slots.append(s)
        return slots
    return _resolve_single(spec, monitors)


def find_slot(slots: list[dict], slot_id: str, monitor: Optional[int] = None) -> dict:
    candidates = [s for s in slots if s["slot_id"] == slot_id]
    if monitor is not None:
        candidates = [s for s in candidates if s["monitor"] == monitor]
    if not candidates:
        raise KeyError(
            f"Slot {slot_id!r} not found{' on monitor ' + str(monitor) if monitor is not None else ''}"
        )
    return candidates[0]


# In-memory cache of the last layout per (desktop_guid). Set by apply_layout,
# read by launchers/move_window when slot is referenced by id.
_LAST_LAYOUT: dict[str, list[dict]] = {}
_GLOBAL_LAST: list[dict] = []


def remember_layout(desktop_guid: Optional[str], slots: list[dict]) -> None:
    global _GLOBAL_LAST
    _GLOBAL_LAST = slots
    if desktop_guid:
        _LAST_LAYOUT[desktop_guid] = slots


def lookup_slot(slot_id: str, desktop_guid: Optional[str] = None) -> Optional[dict]:
    """Look up a slot by id from the most recently applied layout. Tries the
    desktop-specific cache first, then falls back to the global last layout."""
    if desktop_guid and desktop_guid in _LAST_LAYOUT:
        slots = _LAST_LAYOUT[desktop_guid]
        for s in slots:
            if s["slot_id"] == slot_id:
                return s
    for s in _GLOBAL_LAST:
        if s["slot_id"] == slot_id:
            return s
    return None


def register(mcp) -> None:
    @mcp.tool(name="list_monitors")
    def _list_monitors() -> list[dict]:
        """List all physical monitors with their bounds, work area, DPI, and primary flag.
        Indices are 0-based; the primary monitor is always index 0."""
        return [m.to_dict() for m in list_monitors()]

    @mcp.tool()
    def list_layout_presets() -> list[dict]:
        """List built-in layout preset names with a short description."""
        return [
            {"name": name, "description": PRESET_DESCRIPTIONS.get(name, "")}
            for name in PRESETS
        ]

    @mcp.tool()
    def compute_layout(spec: LayoutSpec) -> list[dict]:
        """Resolve a LayoutSpec into concrete slot rectangles WITHOUT moving any
        windows. Useful for previewing a layout. See the module docstring for
        spec grammar."""
        return compute_slots(spec)

    @mcp.tool()
    def apply_layout(
        spec: LayoutSpec,
        target_desktop: Optional[Union[int, str]] = None,
    ) -> list[dict]:
        """Compute the layout and remember it as the active layout for the given
        desktop (default: current). Returns the list of slot rectangles that
        subsequent launcher / move_window calls can target by slot_id.

        This does NOT move any existing windows — call move_window or launch_*
        to fill the slots.
        """
        slots = compute_slots(spec)
        # Resolve desktop GUID for cache scoping.
        desktop_guid: Optional[str] = None
        try:
            from .desktops import resolve_desktop

            desktop = resolve_desktop(target_desktop)
            desktop_guid = str(desktop.id)
        except Exception as exc:  # noqa: BLE001
            log.debug("apply_layout: could not resolve desktop: %s", exc)
        remember_layout(desktop_guid, slots)
        return slots
