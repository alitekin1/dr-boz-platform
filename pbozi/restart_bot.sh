#!/bin/bash
echo "Stopping all bot processes..."
pkill -9 -f "app.bot"
pkill -9 -f "bot_watcher.py"
sleep 2
echo "Starting bot watcher..."
nohup python3 bot_watcher.py > watcher.log 2>&1 &
echo "Bot watcher started in background."
