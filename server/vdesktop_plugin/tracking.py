"""Handle registry — maps short string IDs (and optional user-given labels)
to the OS-level facts about a tracked window."""
from __future__ import annotations

import threading
import uuid
from dataclasses import asdict, dataclass, field
from typing import Optional


@dataclass
class TrackedWindow:
    handle_id: str
    hwnd: int
    pid: int
    app_type: str
    label: Optional[str] = None
    desktop_guid: Optional[str] = None
    slot_id: Optional[str] = None
    bounds: Optional[dict] = None  # {"x": int, "y": int, "w": int, "h": int}
    title: Optional[str] = None
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


class Registry:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._by_id: dict[str, TrackedWindow] = {}
        self._by_hwnd: dict[int, str] = {}

    def register(
        self,
        *,
        hwnd: int,
        pid: int,
        app_type: str,
        label: Optional[str] = None,
        desktop_guid: Optional[str] = None,
        slot_id: Optional[str] = None,
        bounds: Optional[dict] = None,
        title: Optional[str] = None,
    ) -> TrackedWindow:
        with self._lock:
            existing_id = self._by_hwnd.get(hwnd)
            if existing_id is not None:
                tw = self._by_id[existing_id]
                if label is not None:
                    tw.label = label
                if desktop_guid is not None:
                    tw.desktop_guid = desktop_guid
                if slot_id is not None:
                    tw.slot_id = slot_id
                if bounds is not None:
                    tw.bounds = bounds
                if title is not None:
                    tw.title = title
                if app_type and tw.app_type in ("adopted", "unknown"):
                    tw.app_type = app_type
                return tw

            handle_id = uuid.uuid4().hex[:8]
            tw = TrackedWindow(
                handle_id=handle_id,
                hwnd=hwnd,
                pid=pid,
                app_type=app_type,
                label=label,
                desktop_guid=desktop_guid,
                slot_id=slot_id,
                bounds=bounds,
                title=title,
            )
            self._by_id[handle_id] = tw
            self._by_hwnd[hwnd] = handle_id
            return tw

    def get(self, handle_or_label: str) -> Optional[TrackedWindow]:
        """Resolve by handle_id first, then by exact-label match."""
        with self._lock:
            tw = self._by_id.get(handle_or_label)
            if tw is not None:
                return tw
            for candidate in self._by_id.values():
                if candidate.label == handle_or_label:
                    return candidate
            return None

    def require(self, handle_or_label: str) -> TrackedWindow:
        tw = self.get(handle_or_label)
        if tw is None:
            raise KeyError(f"No tracked window for handle/label {handle_or_label!r}")
        return tw

    def all(self) -> list[TrackedWindow]:
        with self._lock:
            return list(self._by_id.values())

    def remove(self, handle_id: str) -> Optional[TrackedWindow]:
        with self._lock:
            tw = self._by_id.pop(handle_id, None)
            if tw is not None:
                self._by_hwnd.pop(tw.hwnd, None)
            return tw

    def relabel(self, handle_id: str, label: Optional[str]) -> None:
        with self._lock:
            tw = self._by_id.get(handle_id)
            if tw is not None:
                tw.label = label

    def update_bounds(self, handle_id: str, bounds: dict, slot_id: Optional[str] = None) -> None:
        with self._lock:
            tw = self._by_id.get(handle_id)
            if tw is not None:
                tw.bounds = bounds
                if slot_id is not None:
                    tw.slot_id = slot_id

    def find_by_hwnd(self, hwnd: int) -> Optional[TrackedWindow]:
        with self._lock:
            hid = self._by_hwnd.get(hwnd)
            return self._by_id.get(hid) if hid else None


REGISTRY = Registry()
