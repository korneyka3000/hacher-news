"""Сводка расхода токенов/цены курации из state/usage.jsonl.

Запуск: `python -m hn_digest.usage_report` (или `task usage`).
Помогает прикинуть стоимость перед возможным переходом на платный Anthropic API.
"""

from __future__ import annotations

import json

from .config import Settings


def _num(x: object) -> float:
    return float(x) if isinstance(x, (int, float)) else 0.0


def main() -> None:
    settings = Settings.from_env()
    path = settings.usage_path
    if not path.exists():
        print(f"Леджер пуст или не найден: {path}")
        return

    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    if not rows:
        print(f"Нет записей в {path}")
        return

    total_in = sum(_num(r.get("input_tokens")) for r in rows)
    total_out = sum(_num(r.get("output_tokens")) for r in rows)
    total_cost = sum(_num(r.get("cost_usd")) for r in rows)
    runs = len(rows)

    print(f"Прогонов: {runs}")
    print(f"Токены суммарно: in={total_in:,.0f}  out={total_out:,.0f}")
    print(f"Цена суммарно: ${total_cost:.4f}  (в среднем ${total_cost / runs:.4f}/прогон)")
    print("\nПоследние прогоны:")
    for r in rows[-5:]:
        cost = r.get("cost_usd")
        cost_str = f"${cost:.4f}" if isinstance(cost, (int, float)) else "—"
        print(
            f"  {r.get('ts', '?')}  "
            f"кандидатов={r.get('candidates')} выбрано={r.get('selected')}  "
            f"in={r.get('input_tokens')} out={r.get('output_tokens')}  {cost_str}"
        )


if __name__ == "__main__":
    main()
