@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\streamlit.exe (
  echo Run setup.bat first.
  pause
  exit /b 1
)
.venv\Scripts\streamlit.exe run app.py --server.maxUploadSize 1024 --browser.gatherUsageStats false
