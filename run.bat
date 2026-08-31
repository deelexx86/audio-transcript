@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo Audio Transcript is not set up yet.
  echo Follow the Initial setup steps in README.md.
  pause
  exit /b 1
)
".venv\Scripts\pythonw.exe" -m audio_transcript %*
exit /b %errorlevel%
