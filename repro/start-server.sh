#!/bin/bash
PORT=${1:-6379}
valkey-server --port $PORT --daemonize yes --save "" --protected-mode no --bind 0.0.0.0
echo "Valkey started on port $PORT"
