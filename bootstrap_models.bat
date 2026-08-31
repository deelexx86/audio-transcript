@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Audio Transcript is not set up yet.
  echo Follow the Initial setup steps in README.md.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m audio_transcript.bootstrap_models %*
if errorlevel 1 pause
exit /b %errorlevel%
