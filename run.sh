#!/bin/bash
# Обёртка для запуска дайджеста (в т.ч. из launchd, где PATH урезан).
set -euo pipefail

# Добавляем типичные места установки uv/claude. Поправь под свою систему,
# если which uv / which claude показывают другой путь.
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"

cd "$(dirname "$0")"
exec uv run python -m hn_digest "$@"
