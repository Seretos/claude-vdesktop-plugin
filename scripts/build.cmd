@echo off
REM Build wrapper for CMD environments. Delegates to the PowerShell script,
REM which contains the actual build logic.
REM
REM Usage: scripts\build.cmd [-Clean] [-Package]

setlocal
set "ROOT=%~dp0.."
pwsh -NoProfile -ExecutionPolicy Bypass -File "%ROOT%\scripts\build.ps1" %*
exit /b %ERRORLEVEL%
