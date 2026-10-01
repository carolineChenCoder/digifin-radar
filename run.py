#!/usr/bin/env python3
"""DigiFin Radar 入口：抓取 -> 去重 -> 打分 -> 渲染 -> 发送。"""

import argparse
import json
import os
import sys

import yaml

from radar.dedupe import (
    collapse_duplicates,
    filter_fresh,
    filter_unseen,
    load_seen,
    mark_seen,
    save_seen,
)
from radar.fetch import fetch_all
from radar.notify import send_cards
from radar.render import build_cards
from radar.score import select_entries

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SEEN_PATH = os.path.join(BASE_DIR, "state", "seen.json")


def load_yaml(name):
    with open(os.path.join(BASE_DIR, name), "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def print_fetch_report(results):
    print("\n=== 抓取状态 ===")
    for r in sorted(results, key=lambda x: x["source_id"]):
        status = "OK  " if r["ok"] else "FAIL"
        detail = f"{r['count']} 条" if r["ok"] else r["error"]
        print(f"[{status}] {r['source_name']:<30} {detail}  ({r['elapsed']:.2f}s)")


def print_score_report(all_scored, threshold):
    print("\n=== 打分明细（按分数降序，仅显示前 40 条） ===")
    ranked = sorted(all_scored, key=lambda e: e["score"], reverse=True)
    for e in ranked[:40]:
        mark = "✓" if e["category"] and e["score"] >= threshold else " "
        print(
            f"[{mark}] {e['score']:>3}  {(e['category'] or '-'):<13} "
            f"{e['source_name']:<28} {e['title'][:60]}"
        )


def main():
    parser = argparse.ArgumentParser(description="DigiFin Radar")
    parser.add_argument("--mode", choices=["daily", "weekly"], default="daily")
    parser.add_argument("--dry-run", action="store_true", help="只打印，不发送到 Lark，也不写 seen.json")
    args = parser.parse_args()

    sources_cfg = load_yaml("sources.yaml")
    keywords_cfg = load_yaml("keywords.yaml")

    sources = [
        s for s in sources_cfg["sources"] if args.mode == "weekly" or not s.get("weekly_only")
    ]
    defaults = sources_cfg["defaults"]

    print(f"开始抓取（mode={args.mode}），共 {len(sources)} 个源...")
    all_entries, results = fetch_all(sources, defaults)
    print_fetch_report(results)

    seen = load_seen(SEEN_PATH)
    deduped = collapse_duplicates(all_entries)
    unseen = filter_unseen(deduped, seen)
    max_age_days = keywords_cfg.get("max_age_days", {}).get(args.mode)
    fresh = filter_fresh(unseen, max_age_days)
    print(
        f"\n抓到 {len(all_entries)} 条，去重后 {len(deduped)} 条，"
        f"排除已发送后剩 {len(unseen)} 条，排除 {max_age_days} 天前的旧内容后剩 {len(fresh)} 条"
    )

    by_category, all_scored = select_entries(fresh, keywords_cfg, args.mode)
    print_score_report(all_scored, keywords_cfg["threshold"][args.mode])

    total_selected = sum(len(v) for v in by_category.values())
    print(f"\n=== 本轮入选 {total_selected} 条 ===")
    for cat in keywords_cfg["category_order"]:
        label = keywords_cfg["category_labels"].get(cat, cat)
        print(f"{label}: {len(by_category.get(cat, []))} 条")

    cards = build_cards(by_category, keywords_cfg, args.mode, results)
    print(f"\n生成 {len(cards)} 张卡片")

    if args.dry_run:
        print("\n=== dry-run：卡片 JSON（不会发送） ===")
        for i, card in enumerate(cards):
            print(f"--- card {i + 1}/{len(cards)} ---")
            print(json.dumps(card, ensure_ascii=False, indent=2))
        return

    webhook_url = os.environ.get("LARK_WEBHOOK_URL")
    if not webhook_url:
        print("错误：未设置 LARK_WEBHOOK_URL 环境变量", file=sys.stderr)
        sys.exit(1)
    secret = os.environ.get("LARK_WEBHOOK_SECRET")

    send_cards(webhook_url, cards, secret=secret)
    print("已发送到 Lark")

    selected_entries = [e for items in by_category.values() for e in items]
    mark_seen(seen, selected_entries)
    save_seen(SEEN_PATH, seen)
    print(f"已更新 seen.json（{len(seen)} 条历史指纹）")


if __name__ == "__main__":
    main()
