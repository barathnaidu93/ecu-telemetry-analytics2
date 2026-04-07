@echo off
echo Starting ECU Telemetry Analytics Platform...

:: Launch Backend on Port 8889
start "ECU Backend" cmd /k "cd backend && venv\Scripts\python -m uvicorn main:app --host 0.0.0.0 --port 8889 --reload"

:: Launch Frontend on Port 3000
start "ECU Frontend" cmd /k "cd frontend && npm run dev -- -p 3000"

echo Servers are launching in separate windows.
echo You can close this window now.
pause
