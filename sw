#!/usr/bin/env bash
# Wrapper script for softwiki CLI
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHONPATH="$DIR" "$DIR/venv/bin/python" "$DIR/softwiki/cli/main.py" "$@"
