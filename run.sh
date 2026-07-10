#!/bin/bash
# Обёртка для запуска дайджеста (в т.ч. из launchd, где PATH урезан).
set -euo pipefail

# Добавляем типичные места установки uv/claude. Поправь под свою систему,
# если which uv / which claude показывают другой путь.
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"

cd "$(dirname "$0")"
# --scheduled включает гард окна запуска: если Mac спал и проснулся сильно позже
# 9:00, прогон тихо пропускается (поздняя выжимка не нужна).
exec uv run python -m hn_digest --scheduled "$@"
