@echo off
rem Shortcut: clawdblock start | stop | status | doctor | mods | apps | connect …
cd /d "%~dp0"
where py >nul 2>nul && (py clawdblock.py %*) || (python clawdblock.py %*)
