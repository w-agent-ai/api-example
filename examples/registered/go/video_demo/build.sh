#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
go build -o registered_video_demo main.go
echo "built: $(pwd)/registered_video_demo"
