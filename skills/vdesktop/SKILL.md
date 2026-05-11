---
name: vdesktop
description: Use to create/manage Windows Virtual Desktops, apply layouts (presets or custom percent splits, multi-monitor), launch Chrome / Windows Terminal / VS Code / generic apps into specific layout slots, and refer back to previously launched windows by label or via title/URL queries. Trigger on requests like "create a desktop with X left and Y right", "open Chrome with these tabs", "move the terminal to the right slot", "pin VS Code to all desktops", or any utterance that combines virtual-desktop, layout, and app-launching concepts. Works whether Claude Code runs natively on Windows or inside WSL — the MCP server bridges to the Windows host automatically.
---

# vdesktop — Virtual Desktop, Layout, and App Orchestration

You have an MCP server (`vdesktop`) that controls Microsoft Virtual Desktops on
the Windows host. Use these tools when the user asks for desktop-level
orchestration: creating desktops, arranging windows into layouts, launching
apps with specific configurations, or addressing previously launched windows.

## Mental model

1. **Desktops** are containers. Operate on them by 0-based `index`, by `name`,
   or by `guid`. The currently active desktop is implicit when no target is
   given.
2. **Monitors** are physical screens. Index 0 is always primary. A layout is
   always associated with one or more monitors.
3. **Layouts** carve a monitor's work area into named **slots**. `apply_layout`
   computes the slot rectangles and remembers them for that desktop —
   subsequent `launch_*` / `move_window` calls can reference slots by id.
4. **Windows** in the registry have a stable `handle_id` and an optional human
   `label`. Always pass a label when you launch — it makes later turns
   addressable without queries.
5. **Pinning** makes a window or its app visible on every virtual desktop
   (Windows 11 native feature, surfaced via `pin_window_all_desktops` /
   `pin_app_all_desktops`).

## Tool inventory

### Desktops
- `list_desktops` — enumerate all desktops
- `get_current_desktop` — which desktop is active
- `create_desktop(name?)` — make a new one
- `delete_desktop(target, fallback_desktop?)` — remove; windows flow to fallback
- `switch_to_desktop(target)` — set foreground desktop
- `rename_desktop(target, new_name)` — Windows 11 only

### Pinning
- `pin_window_all_desktops(handle_id)` — this window appears everywhere
- `unpin_window(handle_id)`
- `pin_app_all_desktops(handle_id)` — every window of the same app appears everywhere
- `unpin_app(handle_id)`
- `is_pinned(handle_id)` — query state

### Monitors and Layouts
- `list_monitors` — physical screens with bounds, work area, DPI
- `list_layout_presets` — built-in preset names
- `compute_layout(spec)` — preview slot rectangles (does NOT move windows)
- `apply_layout(spec, target_desktop?)` — compute + remember as active layout

### Launchers (each returns `{handle_id, hwnd, pid, label, bounds, ...}`)
- `launch_chrome(urls[], slot?, desktop?, label?, new_user_data_dir=True, incognito=False)`
- `launch_terminal(tabs[], slot?, desktop?, label?, window_title?)`
- `launch_vscode(folder, files?, slot?, desktop?, label?, reuse_window=False)`
- `launch_app(executable, args?, cwd?, slot?, desktop?, label?, identification?)`

### Window management
- `list_windows(desktop?, include_unmanaged=False)`
- `move_window(handle_id, target)` — target can mix `slot`, `bounds`, `desktop`
- `resize_window(handle_id, bounds)`
- `close_window(handle_id, force=False)`
- `focus_window(handle_id)` — switches desktop if needed
- `relabel_window(handle_id, new_label)`
- `minimize_window` / `maximize_window` / `restore_window`

### Adoption and query
- `list_unmanaged_windows(desktop?)` — visible windows not in the registry
- `adopt_window(hwnd, label?, app_type_hint?)` — pull external window into registry
- `release_window(handle_id)` — drop from registry, do not close
- `find_window_by_title(pattern, desktop?, regex=False)`
- `find_chrome_tab(pattern, regex=False)` — searches tab strips across all Chrome windows

## Layout spec grammar

Single-monitor layouts:

```jsonc
{"type": "preset",  "name": "three-columns", "monitor": 0}
{"type": "columns", "monitor": 0, "splits": [15, 35, 50]}
{"type": "rows",    "monitor": 1, "splits": [60, 40]}
{"type": "grid",    "monitor": 0, "cols": 2, "rows": 2}
{"type": "regions", "monitor": 0, "regions": [
  {"id": "main",   "x_pct": 0,  "y_pct": 0, "w_pct": 70, "h_pct": 100},
  {"id": "top",    "x_pct": 70, "y_pct": 0, "w_pct": 30, "h_pct": 50},
  {"id": "bottom", "x_pct": 70, "y_pct": 50, "w_pct": 30, "h_pct": 50}
]}
```

Multi-monitor: pass an **array** of single-monitor specs. Slot IDs that collide
across monitors are auto-suffixed with `@m<idx>`.

Built-in presets: `fullscreen`, `two-columns`, `two-columns-golden`,
`three-columns`, `three-columns-wide-center`, `four-columns`, `grid-2x2`,
`grid-3x2`, `grid-3x3`, `main-sidebar`, `main-stack`, `top-bottom-split`.

## Canonical workflows

### "Create a desktop with terminal left, Chrome center, VS Code right"

```
1. create_desktop(name="work")           → {index, guid, ...}
2. apply_layout(
     spec={"type":"preset","name":"three-columns","monitor":0},
     target_desktop="work")              → [{slot_id:"left",...}, "center", "right"]
3. launch_terminal(
     tabs=[{"shell":"powershell","cwd":"E:\\dev"}],
     slot="left", desktop="work", label="dev-term")
4. launch_chrome(
     urls=["https://example.com"],
     slot="center", desktop="work", label="main-browser")
5. launch_vscode(
     folder="E:\\dev",
     slot="right", desktop="work", label="editor")
6. switch_to_desktop("work")
```

### "Open Chrome with 3 tabs"

```
launch_chrome(
  urls=["https://youtube.de","https://google.de","https://gidf.de"],
  label="research-browser")
```

Chrome's CLI opens all URLs as tabs in the new window automatically.

### "Terminal with 2 tabs: WSL in /home/test and PowerShell in e:/dev running claude"

```
launch_terminal(tabs=[
  {"shell": "wsl", "wsl_distro": "Ubuntu", "cwd": "/home/test"},
  {"shell": "powershell", "cwd": "E:\\development", "command": "claude"}
], label="dev-term")
```

### "Pin VS Code to all desktops"

```
1. (assuming you have its handle_id, e.g. "editor")
2. pin_window_all_desktops(handle_id="editor")
```

Use `pin_app_all_desktops` if the user means "every VS Code window" instead of
"this specific window".

### "Move the editor to the right slot"

```
move_window(handle_id="editor", target={"slot": "right"})
```

Add `"desktop": "<ref>"` to the target dict to also move it to another desktop.

### "Custom layout: 15/35/50 columns"

```
apply_layout(spec={"type": "columns", "monitor": 0, "splits": [15, 35, 50]})
```

The resulting slot IDs are `col-0`, `col-1`, `col-2`.

### "Find the Chrome window with YouTube"

```
find_chrome_tab("youtube")
→ [{handle_id, hwnd, tab_index, tab_title, window_title}]
```

The window is automatically adopted into the registry, so the returned
`handle_id` is immediately usable with `move_window` / `focus_window` etc.

### Recovering windows after a server restart

Tracking state is in-memory. After an MCP-server restart, your previously
launched windows are unmanaged:

```
1. list_unmanaged_windows()                    → see the orphans
2. adopt_window(hwnd=<int>, label="main-browser", app_type_hint="chrome")
```

Now you can move/focus/close them by their new handle_id.

## Conventions and rules of thumb

- **Always pass `label`** on every launch. Subsequent turns can address the
  window by label without queries: `move_window("main-browser", ...)` works
  because `REGISTRY.get` resolves labels too.
- **Custom splits** like "15/35/50" → `{type:"columns", splits:[15,35,50]}`.
  Numbers don't need to sum to 100; they're normalized.
- **Multi-monitor**: confirm monitor indices with `list_monitors` first if the
  user mentions "the right screen" or similar. The primary monitor is always
  index 0.
- **Paths**: pass paths as the user gave them. The MCP server auto-translates
  POSIX↔Windows so `/home/test` from a WSL caller becomes `\\wsl$\Ubuntu\home\test`
  for Windows apps. WSL-shell tabs in `launch_terminal` keep their POSIX cwd.
- **When `launch_*` fails to resolve an HWND** (timeout error), retry once,
  then fall back to `find_window_by_title` with a unique title fragment.
- **Don't enumerate every desktop** — `list_desktops` is cheap, but if the user
  said "the current desktop", just operate without an explicit `desktop=` arg.
- **`apply_layout` before launching**: launchers reference slots by id from the
  *most recently applied* layout for the window's destination desktop. If you
  haven't applied one, pass explicit `bounds` to `move_window` instead.

## Failure modes to expect

- `pyvda` import / COM init failure — usually means the Windows build broke
  the internal interface vtable. Report the error verbatim; the user may need
  to update the `pyvda` package.
- "Slot X unknown — call apply_layout first" — you forgot the layout step.
- HWND-resolve timeout — Chrome may have IPC'd to an existing instance
  (re-launch with `new_user_data_dir=True`, which is the default), or
  `wt.exe` may have failed to spawn a new window — confirm Windows Terminal
  is installed.
