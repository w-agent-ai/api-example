#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
go build -o registered_sequence_demo main.go
echo "built: $(pwd)/registered_sequence_demo"
