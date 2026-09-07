@echo off
rem Launches Google Chrome (or Edge) with remote debugging enabled for PDF Translator
start "" chrome --remote-debugging-port=9222
if %errorlevel% neq 0 (
    start "" msedge --remote-debugging-port=9222
)
