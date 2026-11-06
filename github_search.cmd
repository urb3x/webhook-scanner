@echo off
setlocal enabledelayedexpansion
title GitHub Hosted Site Searcher - CMD Edition
chcp 65001 >nul

rem Find working python executable
set "PY_BIN="

rem Check 1: python in PATH
where python >nul 2>nul
if %ERRORLEVEL% equ 0 (
    set "PY_BIN=python"
    goto :found_python
)

rem Check 2: py launcher in PATH
where py >nul 2>nul
if %ERRORLEVEL% equ 0 (
    set "PY_BIN=py"
    goto :found_python
)

rem Check 3: User AppData local python installs
if exist "%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe" (
    set "PY_BIN=%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe"
    goto :found_python
)
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
    set "PY_BIN=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    goto :found_python
)
if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
    set "PY_BIN=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    goto :found_python
)
if exist "%LOCALAPPDATA%\Programs\Python\Python310\python.exe" (
    set "PY_BIN=%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
    goto :found_python
)

rem Check 4: Program Files
if exist "%ProgramFiles%\Python312\python.exe" (
    set "PY_BIN=%ProgramFiles%\Python312\python.exe"
    goto :found_python
)
if exist "%ProgramFiles%\Python311\python.exe" (
    set "PY_BIN=%ProgramFiles%\Python311\python.exe"
    goto :found_python
)

echo [!] Error: Python executable not found in PATH or standard installation folders.
echo Please ensure Python is installed and available in PATH.
echo.
pause
exit /b 1

:found_python
"%PY_BIN%" "%~dp0github_cmd.py" %*

rem If executed by double-click without arguments and terminated, keep window open
if "%~1"=="" (
    pause
)
