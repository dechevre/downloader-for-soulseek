#!/bin/bash
DOWNLOAD_DIR="/Users/aneurinquinnevans/Music/slskd"
echo "[flatten] triggered at $(date)" >> /tmp/flatten_debug.log
echo "[flatten] SLSKD_SCRIPT_DATA=$SLSKD_SCRIPT_DATA" >> /tmp/flatten_debug.log

FILE_PATH=$(echo "$SLSKD_SCRIPT_DATA" | python3 -c "import sys, json; print(json.load(sys.stdin)['localPath'])")
echo "[flatten] FILE_PATH=$FILE_PATH" >> /tmp/flatten_debug.log

if [ -n "$FILE_PATH" ]; then
    mv "$FILE_PATH" "$DOWNLOAD_DIR/$(basename "$FILE_PATH")"
    echo "[flatten] moved to $DOWNLOAD_DIR/$(basename "$FILE_PATH")" >> /tmp/flatten_debug.log
fi