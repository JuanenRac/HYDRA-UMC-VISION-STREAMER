@echo off
REM HYDRA-UMC-VISION-STREAMER - build.bat: venv + editable install + compile-check
REM Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
REM GPL-3.0 - see LICENSE
REM
REM Bumps the odometer version, creates/updates the local venv, installs the
REM project (editable) with its dependencies, and compile-checks every source
REM file. Run this before run.bat whenever the source changes.
setlocal
cd /d "%~dp0"

echo == HYDRA-UMC-VISION-STREAMER :: build ==

echo -- Odometer version bump --
python bump_version.py
if errorlevel 1 ( echo NATIVE VERSION BUMP FAILED. & pause & exit /b 1 )
python "%~dp0bump_manifest_version.py" --sync
if errorlevel 1 ( echo VERSION SYNCHRONIZATION FAILED. & pause & exit /b 1 )
if errorlevel 1 goto :error

echo -- Creating/using virtual environment (.venv) --
if not exist ".venv" (
    python -m venv .venv
    if errorlevel 1 goto :error
)

set VENV_PY=.venv\Scripts\python.exe

echo -- Installing project + dependencies (editable) --
"%VENV_PY%" -m pip install --quiet --upgrade pip
if errorlevel 1 goto :error
"%VENV_PY%" -m pip install --quiet -e .
if errorlevel 1 goto :error

echo -- Compile-check every source file (python -m compileall) --
"%VENV_PY%" -m compileall -q src
if errorlevel 1 goto :error

echo == Build OK ==
exit /b 0

:error
echo == Build FAILED ==
exit /b 1
