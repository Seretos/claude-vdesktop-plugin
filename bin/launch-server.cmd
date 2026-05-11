@echo off
REM vdesktop-plugin MCP server bootstrap (native Windows fallback).
REM Used when bash is unavailable. plugin.json can be edited to point here.

setlocal

if "%VDESKTOP_PLUGIN_ROOT%"=="" (
  if not "%CLAUDE_PLUGIN_ROOT%"=="" (
    set "VDESKTOP_PLUGIN_ROOT=%CLAUDE_PLUGIN_ROOT%"
  ) else (
    set "VDESKTOP_PLUGIN_ROOT=%~dp0.."
  )
)

set "PYTHONPATH=%VDESKTOP_PLUGIN_ROOT%\server;%PYTHONPATH%"

REM Prefer the py launcher (handles multiple Python installs).
where py.exe >nul 2>nul
if %ERRORLEVEL%==0 (
  py.exe -3 -m vdesktop_plugin %*
  exit /b %ERRORLEVEL%
)

python.exe -m vdesktop_plugin %*
exit /b %ERRORLEVEL%
