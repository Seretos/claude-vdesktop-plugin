#!/usr/bin/env bash
# vdesktop-plugin MCP server bootstrap.
#
# Always launches the Python MCP server as a *Windows process* so it can talk to
# IVirtualDesktopManagerInternal, COM, and Win32. Two cases:
#
#   1) Caller is inside WSL: re-exec via the Windows-side python.exe (interop).
#      Stdin/stdout flow transparently between the WSL caller and the Windows
#      child process — exactly what MCP needs over stdio.
#
#   2) Caller is native Windows running this script via Git-Bash or MSYS bash:
#      run `python -m vdesktop_plugin` directly (python on PATH).
#
# CLAUDE_PLUGIN_ROOT / VDESKTOP_PLUGIN_ROOT points at the plugin install dir.

set -euo pipefail

PLUGIN_ROOT="${VDESKTOP_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-}}"
if [[ -z "${PLUGIN_ROOT}" ]]; then
  # Last-resort: derive from this script's location.
  PLUGIN_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fi

is_wsl() {
  [[ -n "${WSL_DISTRO_NAME:-}" ]] && return 0
  if [[ -r /proc/sys/kernel/osrelease ]]; then
    grep -qiE 'microsoft|wsl' /proc/sys/kernel/osrelease && return 0
  fi
  return 1
}

if is_wsl; then
  # Translate the plugin path to a Windows path so the Windows Python process
  # can import the package.
  PLUGIN_ROOT_WIN="$(wslpath -w "${PLUGIN_ROOT}")"
  SERVER_DIR_WIN="${PLUGIN_ROOT_WIN}\\server"

  # PYTHONPATH for the child must be in Windows format; export it via cmd.exe's
  # environment by using `env` directly on the python.exe call.
  export PYTHONPATH="${SERVER_DIR_WIN}"
  export VDESKTOP_PLUGIN_ROOT="${PLUGIN_ROOT_WIN}"

  # Prefer the `py` launcher if available (more robust to multiple Python installs).
  if command -v py.exe >/dev/null 2>&1; then
    exec py.exe -3 -m vdesktop_plugin "$@"
  fi
  exec python.exe -m vdesktop_plugin "$@"
fi

# Native (Git-Bash / MSYS / Cygwin) — assume python on PATH points at Windows Python.
export PYTHONPATH="${PLUGIN_ROOT}/server${PYTHONPATH:+:${PYTHONPATH}}"
export VDESKTOP_PLUGIN_ROOT="${PLUGIN_ROOT}"
exec python -m vdesktop_plugin "$@"
