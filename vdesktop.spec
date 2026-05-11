# PyInstaller spec for the vdesktop-plugin MCP server.
#
# Produces a single-file Windows .exe under dist/vdesktop.exe that contains
# the Python interpreter, all dependencies (mcp, pyvda, pywin32, comtypes,
# uiautomation), and the package itself.
#
# Build:    py -3 -m PyInstaller vdesktop.spec --clean --noconfirm
# Output:   dist\vdesktop.exe
# Copy to:  bin\vdesktop.exe  (handled by scripts/build.ps1)

# ruff: noqa
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

block_cipher = None
ROOT = Path(SPECPATH)

# pyvda generates COM interface stubs lazily; bundle the whole package
# including any pre-generated comtypes.gen modules.
pyvda_datas, pyvda_binaries, pyvda_hiddenimports = collect_all("pyvda")
comtypes_datas, comtypes_binaries, comtypes_hiddenimports = collect_all("comtypes")
uia_datas, uia_binaries, uia_hiddenimports = collect_all("uiautomation")

# `mcp.cli` requires optional `typer`/`rich` deps we don't need for the server.
# Collect mcp manually, filtering out the CLI subpackage so PyInstaller doesn't
# fail trying to import it.
def _not_cli(name: str) -> bool:
    return not name.startswith("mcp.cli")

mcp_hiddenimports = collect_submodules("mcp", filter=_not_cli)
mcp_datas, mcp_binaries = [], []

win32_datas, win32_binaries, win32_hiddenimports = collect_all("win32")

# pywin32 splits across several top-level modules; add the ones we use.
extra_hidden = [
    "win32api",
    "win32con",
    "win32gui",
    "win32process",
    "pywintypes",
    "pythoncom",
    # FastMCP runtime:
    "anyio",
    "pydantic",
    "pydantic_core",
    "starlette",
]
extra_hidden += collect_submodules("vdesktop_plugin")
extra_hidden += collect_submodules("comtypes")  # interface enumerators

a = Analysis(
    ["server/vdesktop_plugin/__main__.py"],
    pathex=[str(ROOT / "server")],
    binaries=pyvda_binaries + comtypes_binaries + uia_binaries + mcp_binaries + win32_binaries,
    datas=pyvda_datas + comtypes_datas + uia_datas + mcp_datas + win32_datas,
    hiddenimports=(
        pyvda_hiddenimports
        + comtypes_hiddenimports
        + uia_hiddenimports
        + mcp_hiddenimports
        + win32_hiddenimports
        + extra_hidden
    ),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "matplotlib",
        "numpy",
        "PIL",
        "test",
        "unittest",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="vdesktop",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,            # don't compress — slower startup, no real size win on stdio binaries
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,          # MUST be console=True for stdio MCP transport
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
