@echo off
rem ClawdBlock installer for Windows — double-click me.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
pause
