#!/bin/bash
# Start 1minAI FastAPI server on OnePlus 5 Termux
cd /data/data/com.termux/files/home
export FASTAPI_HOST=0.0.0.0
export FASTAPI_PORT=9000
export TERMUX_WAKE_LOCK=true

# Start with nohup to keep running after SSH disconnect
nohup python3 oneminai_server.py > /data/data/com.termux/files/home/oneminai.log 2>&1 &
echo "Server PID: $!"
sleep 3
# Check if it started
ps aux | grep oneminai_server | grep -v grep
