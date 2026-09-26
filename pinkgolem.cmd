@echo off
rem Shortcut: pinkgolem start | stop | status | doctor | mods | apps | connect …
cd /d "%~dp0"
where py >nul 2>nul && (py pinkgolem.py %*) || (python pinkgolem.py %*)
