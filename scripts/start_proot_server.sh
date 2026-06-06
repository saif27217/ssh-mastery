#!/bin/bash
cd /root
/root/oneminai-venv/bin/python3 -m uvicorn proot_oneminai_server:app --host 0.0.0.0 --port 9001 > proot_server.log 2>&1 &
echo "Started with PID $!"
sleep 5
cat proot_server.log
