@echo off
REM ============================================================
REM EDIFACT Orders Generator - Build Script
REM ============================================================
SETLOCAL

echo [BUILD] Starting EDIFACT_Orders_Generator build process...
echo.

REM --- Step 1: Clean previous build ---
echo [STEP 1] Cleaning previous build artifacts...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist EDIFACT_Orders_Generator.spec del EDIFACT_Orders_Generator.spec
echo [OK] Clean complete.
echo.

REM --- Step 2: Run pytest ---
echo [STEP 2] Running pytest test suite...
python -m pytest tests\ -v --tb=short
IF %ERRORLEVEL% NEQ 0 (
    echo [FAIL] Tests failed. Aborting build.
    exit /b 1
)
echo [OK] All tests passed.
echo.

REM --- Step 3: Run validate_project.py ---
echo [STEP 3] Running project validation...
python validate_project.py
IF %ERRORLEVEL% NEQ 0 (
    echo [FAIL] Project validation failed. Aborting build.
    exit /b 1
)
echo [OK] Project validation passed.
echo.

REM --- Step 4: Build executable with PyInstaller ---
echo [STEP 4] Building executable with PyInstaller...
pyinstaller ^
  --onefile ^
  --name EDIFACT_Orders_Generator ^
  --add-data "config.ini;." ^
  --add-data "lookups;lookups" ^
  --hidden-import pandas ^
  --hidden-import PyPDF2 ^
  --hidden-import openpyxl ^
  --hidden-import paramiko ^
  src\edifact_orders_engine.py

IF %ERRORLEVEL% NEQ 0 (
    echo [FAIL] PyInstaller build failed.
    exit /b 1
)

echo.
echo [SUCCESS] Build complete.
echo [INFO] Executable: dist\EDIFACT_Orders_Generator.exe
echo.

ENDLOCAL
