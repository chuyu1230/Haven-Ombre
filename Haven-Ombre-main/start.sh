#!/usr/bin/env bash

echo "start brain"
python server.py &

echo "start gateway"
python gateway.py &

wait
