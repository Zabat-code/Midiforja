@echo off
REM Midiforja backend launcher (FastAPI on port 8000)
cd /d %~dp0backend
call .venv\Scripts\activate.bat
python server.py
pause
