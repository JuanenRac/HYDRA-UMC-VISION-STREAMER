@echo off
REM HYDRA-UMC-VISION-STREAMER - run.bat: runs the entry point from the local venv
REM Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
REM GPL-3.0 - see LICENSE
REM
REM Runs the project entry point from the local venv created by build.bat.
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    set VENV_PY=.venv\Scripts\python.exe
) else (
    echo No .venv found - run build.bat first. 1>&2
    exit /b 1
)

"%VENV_PY%" -m hydra_umc_vision_streamer.main
exit /b %errorlevel%
