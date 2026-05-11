# vdesktop-plugin

A Claude Code plugin that lets the agent control **Microsoft Virtual Desktops**
on Windows 11: create / delete / switch desktops, apply column / row / grid /
preset layouts (multi-monitor), launch Chrome / Windows Terminal / VS Code into
specific layout slots with full argument configuration, pin apps across
desktops, and address previously launched windows by label or content query.

Works whether Claude Code runs natively on Windows or inside WSL — the MCP
server is a self-contained Windows `.exe` that has direct access to
`IVirtualDesktopManagerInternal`, Win32, and UI Automation. WSL invokes it
transparently via interop.

## Install (end users)

1. Download `vdesktop-plugin-<version>.zip` from the GitHub Releases page.
2. Unpack to a stable location (e.g. `C:\Users\<you>\.claude\plugins\vdesktop-plugin\`
   or any other path Claude Code can reach).
3. In Claude Code, add it as a local plugin:

   ```
   /plugin install <path-to-unpacked-folder>
   ```

   Or pass it on the command line for local development:

   ```
   claude --plugin-dir <path-to-unpacked-folder>
   ```

That's it. No Python install, no `pip install`, no dependencies. The plugin
ships a self-contained `bin/vdesktop.exe` that includes the Python interpreter
and every library it needs.

### From WSL

The plugin can sit on the Windows side (e.g. `E:\...\vdesktop-plugin`) and be
referenced from WSL via `/mnt/e/...`. WSL's `binfmt_misc` handler intercepts
every `.exe` invocation and runs it on the Windows host — `vdesktop.exe`
ends up as a real Windows process with full COM access, while stdin/stdout
flow back to WSL transparently.

## Components

- `bin/vdesktop.exe` — single-file Windows binary (PyInstaller-built).
  Contains the FastMCP server, pyvda, pywin32, comtypes, uiautomation.
- `.claude-plugin/plugin.json` — the manifest. Points the `vdesktop` MCP
  server at `${CLAUDE_PLUGIN_ROOT}/bin/vdesktop.exe`.
- `skills/vdesktop/SKILL.md` — teaches the agent when and how to use the
  MCP tools; provides workflow recipes.
- `server/vdesktop_plugin/` — the Python source for the MCP server. Only
  needed for development or building the .exe.
- `bin/launch-server.sh`, `bin/launch-server.cmd` — alternate launchers
  for source-mode development (see below).

## Smoke test

In Claude Code, with the plugin loaded:

```
> list the virtual desktops and the monitors
```

The `vdesktop` skill should trigger and Claude should call `list_desktops` +
`list_monitors` and report results.

End-to-end:

```
> create a new desktop called "demo", apply a three-column layout, open a
  WSL terminal in /home/test on the left, Chrome with youtube.de in the
  center, and VS Code on E:\development on the right
```

Expected tool sequence: `create_desktop` → `apply_layout` → three `launch_*`
calls (each placing the new window in its slot) → `switch_to_desktop`.

## Build from source (for plugin developers)

Required: Python 3.11+ with the `py.exe` launcher (standard Python.org installer).

```powershell
git clone <repo>
cd vdesktop-plugin

# One-time: install plugin + build deps in editable mode.
py -3 -m pip install -e ".[build]"

# Build the .exe. Outputs dist/vdesktop.exe AND copies to bin/vdesktop.exe.
pwsh -File scripts/build.ps1

# Optional: produce a release zip ready for GitHub Releases.
pwsh -File scripts/build.ps1 -Clean -Package
# → dist/vdesktop-plugin-<version>.zip
```

The build script runs PyInstaller against `vdesktop.spec`, copies the result
to `bin/vdesktop.exe`, then smoke-tests it with an MCP `initialize`
handshake. If the handshake fails the build is rejected.

### Iterating without rebuilding the .exe

While developing the server, rebuilding the `.exe` for every code change is
slow (~30 s). The shipped `bin/launch-server.sh` (and `.cmd`) bootstrap a
Python interpreter against the source tree directly. To use it, temporarily
edit `.claude-plugin/plugin.json`:

```jsonc
"mcpServers": {
  "vdesktop": {
    "command": "bash",
    "args": ["${CLAUDE_PLUGIN_ROOT}/bin/launch-server.sh"],
    "env": { "VDESKTOP_PLUGIN_ROOT": "${CLAUDE_PLUGIN_ROOT}" }
  }
}
```

This requires `pip install -e .` to have run once.

## Release workflow (maintainers)

The intended release path:

1. Bump `version` in `.claude-plugin/plugin.json` and `pyproject.toml`.
2. Run `pwsh -File scripts/build.ps1 -Clean -Package` locally to produce
   `dist/vdesktop-plugin-<version>.zip` and smoke-test it.
3. Tag the release and push: `git tag v<version> && git push --tags`.
4. CI (when configured) re-builds on the tag and uploads the zip as a
   GitHub Release asset. Until CI is set up, upload `dist/*.zip` manually.

Users install by downloading the zip — they don't touch the source repo.

## Why a frozen binary?

The MCP server needs access to undocumented COM interfaces in Explorer
(`IVirtualDesktopManagerInternal`) and to Win32 / UI Automation. That's
Python (`pyvda`, `pywin32`, `comtypes`, `uiautomation`) territory. Asking
end users to `pip install` those manually breaks the plug-and-play
expectation. PyInstaller bundles the interpreter and every dependency into
a 25 MB executable; the plugin just ships it and points the manifest at it.

WSL doesn't change this — `binfmt_misc` runs the .exe on the Windows host
in both cases, identically.

## Known limitations

- `IVirtualDesktopManagerInternal` vtable changes between Windows builds.
  If `list_desktops` raises `OSError` or `COMError`, the bundled `pyvda` is
  older than the OS — wait for a plugin release with an updated pyvda
  pin, or build from source with `pip install -U pyvda` first.
- `FancyZones` (PowerToys) has no public automation surface — out of scope.
- Multiple Chrome windows: `new_user_data_dir=True` (default) is required
  for reliable per-window HWND resolution.
- Windows Terminal is a singleton — identification uses an auto-injected
  `--title` tag.
- Registry state (handle_id / label mappings) is in-memory. After an
  MCP-server restart use `list_unmanaged_windows` + `adopt_window` to
  recover previously launched windows.
- Windows 10 is **not** supported — `IVirtualDesktopManagerInternal`
  semantics differ.

## Files of interest (for developers)

- `server/vdesktop_plugin/server.py` — FastMCP entry point.
- `server/vdesktop_plugin/desktops.py` — `pyvda` wrappers + pinning.
- `server/vdesktop_plugin/layouts.py` — preset catalog + spec parser.
- `server/vdesktop_plugin/windows.py` — `SetWindowPos` with DWM shadow correction.
- `server/vdesktop_plugin/launchers/_common.py` — spawn + HWND-resolve pipeline.
- `server/vdesktop_plugin/pathmap.py` — POSIX↔Windows path conversion.
- `vdesktop.spec` — PyInstaller config.
- `scripts/build.ps1` — local build + smoke test + optional release packaging.
- `skills/vdesktop/SKILL.md` — workflows the agent learns from.
