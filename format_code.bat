@echo off
echo ===============================================
echo Code Formatting with Black
echo ===============================================
echo.


echo Formatting Python files in: %~dp0
echo.

REM Format all Python files in the current directory and subdirectories
python -m black . --line-length=88 --diff --color

echo.
echo ===============================================
echo Applying formatting changes...
echo ===============================================

REM Actually apply the changes
python -m black . --line-length=88

echo.
echo ===============================================
echo Code formatting complete!
echo =============================================== 