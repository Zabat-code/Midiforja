@echo off
REM Midiforja frontend launcher (Vite dev server on port 5174)
cd /d %~dp0frontend
call npm install
call npx vite --port 5174
pause
