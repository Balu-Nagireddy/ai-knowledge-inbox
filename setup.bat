@echo off
setlocal
set "ROOT=%~dp0"
set "BACKEND=%ROOT%backend"
set "FRONTEND=%ROOT%frontend"

where py >nul 2>nul
if errorlevel 1 (echo Python launcher not found. Install Python 3.10+ and enable PATH.& exit /b 1)
where npm >nul 2>nul
if errorlevel 1 (echo npm not found. Install Node.js LTS.& exit /b 1)

if not exist "%BACKEND%\.venv\Scripts\python.exe" (
  py -3 -m venv "%BACKEND%\.venv"
  if errorlevel 1 exit /b 1
)
"%BACKEND%\.venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 exit /b 1
"%BACKEND%\.venv\Scripts\python.exe" -m pip install -r "%BACKEND%\requirements.txt"
if errorlevel 1 exit /b 1

if not exist "%BACKEND%\.env" (
  copy "%BACKEND%\.env.example" "%BACKEND%\.env" >nul
  echo Created backend\.env. Add GEMINI_API_KEY to enable Gemini.
)
cd /d "%FRONTEND%"
if exist package-lock.json (npm ci) else (npm install)
if errorlevel 1 exit /b 1

echo.
echo Setup complete.
echo Open two terminals and run run_backend.bat and run_frontend.bat.
echo API docs: http://127.0.0.1:8000/docs
endlocal
