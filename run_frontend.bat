@echo off
setlocal
echo Starting AI Knowledge Inbox Frontend...
cd /d "%~dp0frontend"

where npm >nul 2>nul
if errorlevel 1 (
  echo npm is required. Install Node.js LTS first.
  exit /b 1
)
if not exist "node_modules" (
  echo Frontend dependencies are missing. Run setup.bat first.
  exit /b 1
)

npm run dev
endlocal
