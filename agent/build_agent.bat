@echo off
REM =============================================================================
REM  AuditVault Agent — Build Script
REM  Packages agent.py into AuditVaultAgent.exe using PyInstaller.
REM  The EXE is placed in dist/AuditVaultAgent/ alongside config and modules.
REM =============================================================================

echo.
echo  ============================================
echo   AuditVault Agent - Build Tool
echo  ============================================
echo.

REM --- Check PyInstaller ---
where pyinstaller >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [!] PyInstaller not found. Installing...
    pip install pyinstaller
)

REM --- Clean previous build ---
if exist "dist" rmdir /s /q dist
if exist "build" rmdir /s /q build

echo [*] Building AuditVaultAgent.exe ...

pyinstaller ^
    --onefile ^
    --name AuditVaultAgent ^
    --hidden-import=win32timezone ^
    --console ^
    --icon=NONE ^
    agent.py

if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] Build failed!
    exit /b 1
)

REM --- Assemble distribution folder ---
echo [*] Assembling distribution package...

set DIST=dist\AuditVaultAgent

REM EXE is already at dist\AuditVaultAgent.exe from --onefile, move it into a folder
mkdir "%DIST%" 2>nul
move "dist\AuditVaultAgent.exe" "%DIST%\AuditVaultAgent.exe" >nul

REM Copy external config
copy "config.json" "%DIST%\config.json" >nul

REM Copy modules
xcopy "modules" "%DIST%\modules\" /E /I /Q >nul

REM Create empty dirs
mkdir "%DIST%\logs" 2>nul
mkdir "%DIST%\queue" 2>nul

REM --- Clean build artifacts ---
rmdir /s /q build 2>nul
del /q *.spec 2>nul

echo.
echo  ============================================
echo   BUILD COMPLETE
echo  ============================================
echo.
echo   Output: dist\AuditVaultAgent\
echo.
echo   Contents:
echo     AuditVaultAgent.exe   (Service binary)
echo     config.json           (Editable config)
echo     modules\              (PowerShell modules)
echo     logs\                 (Created at runtime)
echo     queue\                (Offline queue)
echo.
echo   Deploy this entire folder to the target machine.
echo.
echo   Commands:
echo     AuditVaultAgent.exe install
echo     AuditVaultAgent.exe start
echo     AuditVaultAgent.exe status
echo     AuditVaultAgent.exe stop
echo     AuditVaultAgent.exe uninstall
echo.
