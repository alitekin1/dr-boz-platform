#!/bin/bash
# Stop all bot related processes
pkill -9 -f "app.bot"
pkill -9 -f "bot_watcher.py"
pkill -9 -f "uvicorn_watcher.py"
pkill -9 -f "uvicorn"

# Clean logs
rm *.log

# Start them once
nohup python3 uvicorn_watcher.py > uvicorn_watcher.log 2>&1 &
nohup python3 bot_watcher.py > bot_watcher.log 2>&1 &
