@echo off
setlocal
echo Starting AI Knowledge Inbox Backend...
cd /d "%~dp0backend"

if not exist ".venv\Scripts\python.exe" (
  echo Backend virtual environment not found. Run setup.bat first.
  exit /b 1
)

".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
endlocal
