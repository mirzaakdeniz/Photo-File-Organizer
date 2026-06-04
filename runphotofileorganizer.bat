@echo off
title Simple Photo Sorter Launcher
echo Launching Simple Photo Sorter...
python photofileorganizer.py
if %errorlevel% neq 0 (
    echo.
    echo An error occurred while running the photo sorter.
    pause
)
