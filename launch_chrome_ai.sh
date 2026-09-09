#!/usr/bin/env bash
# Launches your existing Chrome with Remote Debugging enabled so PDF Translator can use your active logins
google-chrome --remote-debugging-port=9222 --disable-dev-shm-usage --no-first-run --no-default-browser-check &
