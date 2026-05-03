#!/usr/bin/env python3
"""
参照テキスト（目次・論点リストに相当）からテーマをランダムに選び、
Google シート用のコピペ案と used 記録を出す。

著作権メモ: テーマ名は論点のラベルに過ぎず、本文は教材から転載しない。
図解HTMLは別途オリジナルで作成する。
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
THEMES_PATH = ROOT / "data" / "far_themes.json"
USED_PATH = ROOT / "data" / "far_themes_used.json"


def load_themes() -> list[dict]:
    data = json.loads(THEMES_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise SystemExit("far_themes.json must be a JSON array")
    return data


def load_used() -> list[dict]:
    if not USED_PATH.exists():
        return []
    raw = json.loads(USED_PATH.read_text(encoding="utf-8") or "[]")
    return raw if isinstance(raw, list) else []


def save_used(entries: list[dict]) -> None:
    USED_PATH.write_text(json.dumps(entries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def pick_unused(themes: list[dict], used: list[dict]) -> list[dict]:
    used_slugs = {e.get("slug") for e in used if isinstance(e, dict)}
    pool = [t for t in themes if t.get("slug") not in used_slugs]
    return pool


def cmd_list() -> int:
    themes = load_themes()
    for t in themes:
        print(f"- {t.get('slug')}: {t.get('title')}")
    print(f"\n計 {len(themes)} テーマ")
    return 0


def cmd_pick(allow_repeat: bool) -> int:
    themes = load_themes()
    used = load_used()
    pool = pick_unused(themes, used)
    if not pool and allow_repeat:
        print("未使用テーマが無いため、全テーマから選びます (--allow-repeat)。", file=sys.stderr)
        pool = themes
    elif not pool:
        print(
            "未使用テーマがありません。data/far_themes_used.json を確認するか、\n"
            "  python scripts/pick_theme.py --reset-used\n"
            "  python scripts/pick_theme.py --pick --allow-repeat\n",
            file=sys.stderr,
        )
        return 1

    choice = random.choice(pool)
    slug = choice.get("slug", "")
    title = choice.get("title", "")
    summary = choice.get("summary_hint", "")
    note = choice.get("source_note", "")

    pages_url = "https://haitokutaishi-lgtm.github.io/far-discord-delivery/far/"
    print("=== 今回の候補テーマ（ランダム） ===\n")
    print(f"slug:          {slug}")
    print(f"title:         {title}")
    print(f"summary_hint:  {summary}")
    print(f"source_note:   {note}")
    print()
    print("【次の作業】")
    print("1) 図解HTMLをオリジナル作成し docs/far/<slug>.html としてコミット（または Netlify 等に配置）")
    print(f"2) public_url 例: {pages_url}{slug}.html")
    print("3) Google シート Queue に 1 行追加: title / summary / public_url / status=approved / sent_at 空")
    print("4) 配信後: python scripts/pick_theme.py --mark-used " + slug)
    print()
    return 0


def cmd_mark_used(slug: str) -> int:
    used = load_used()
    if any(isinstance(e, dict) and e.get("slug") == slug for e in used):
        print(f"すでに記録済み: {slug}", file=sys.stderr)
        return 0
    entry = {
        "slug": slug,
        "used_at": datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M %Z"),
    }
    used.append(entry)
    save_used(used)
    print(f"記録しました: {slug}")
    return 0


def cmd_reset_used() -> int:
    save_used([])
    print("far_themes_used.json を空にしました。")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="FAR 図解テーマをランダム抽出・使用済み記録")
    p.add_argument("--list", action="store_true", help="テーマ一覧")
    p.add_argument("--pick", action="store_true", help="未使用からランダムに1件提示")
    p.add_argument("--allow-repeat", action="store_true", help="未使用が無いとき全件から選ぶ")
    p.add_argument("--mark-used", metavar="SLUG", help="使用済みスラッグを記録")
    p.add_argument("--reset-used", action="store_true", help="使用済み一覧をクリア")
    args = p.parse_args()

    if args.list:
        return cmd_list()
    if args.pick:
        return cmd_pick(allow_repeat=args.allow_repeat)
    if args.mark_used:
        return cmd_mark_used(args.mark_used.strip())
    if args.reset_used:
        return cmd_reset_used()

    p.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
