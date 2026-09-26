@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Creating Python environment...
  python -m venv .venv || (echo Install Python 3.11+ from python.org first & pause & exit /b 1)
)
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
if not exist tools\ffmpeg\bin\ffmpeg.exe (
  echo Downloading FFmpeg...
  if not exist tools mkdir tools
  powershell -NoProfile -Command "Invoke-WebRequest https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip -OutFile tools\ffmpeg.zip; Expand-Archive tools\ffmpeg.zip tools\_x -Force; Move-Item (Get-ChildItem tools\_x)[0].FullName tools\ffmpeg; Remove-Item tools\_x -Recurse; Remove-Item tools\ffmpeg.zip"
)
if not exist .env copy .env.example .env
echo.
echo Setup done. Double-click run.bat to start.
pause
