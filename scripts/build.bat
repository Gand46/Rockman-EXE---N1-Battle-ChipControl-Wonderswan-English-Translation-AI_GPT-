@echo off
setlocal
if "%~1"=="" goto usage
where py >nul 2>nul
if not errorlevel 1 goto run_py
where python >nul 2>nul
if not errorlevel 1 goto run_python
echo Python 3.11 or newer is required.
exit /b 2
:run_py
py -3 "%~dp0project.py" build --source %*
exit /b %ERRORLEVEL%
:run_python
python "%~dp0project.py" build --source %*
exit /b %ERRORLEVEL%
:usage
echo Usage: build.bat "C:\path\original.wsc" [--variant qa09^|chip-control^|all]
exit /b 2
