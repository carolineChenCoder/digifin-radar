"""构建 Lark interactive 卡片 JSON，按 30KB 上限分片。"""

import datetime
import json

MAX_CARD_BYTES = 28000  # Lark 卡片体上限约 30KB，留余量


def _escape_md(text):
    return (text or "").replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")


def _format_time_ago(published_iso):
    if not published_iso:
        return ""
    try:
        dt = datetime.datetime.fromisoformat(published_iso)
    except ValueError:
        return ""
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    seconds = (now - dt).total_seconds()
    if seconds < 0:
        return ""
    if seconds < 3600:
        return f"{max(int(seconds // 60), 1)}分钟前"
    if seconds < 86400:
        return f"{int(seconds // 3600)}小时前"
    days = int(seconds // 86400)
    if days <= 14:
        return f"{days}天前"
    return dt.strftime("%Y-%m-%d")


def _entry_line(entry):
    title = _escape_md(entry.get("title", "(无标题)"))
    link = entry.get("link", "")
    meta = " · ".join(
        filter(None, [entry.get("source_name"), _format_time_ago(entry.get("published"))])
    )
    content = f"[{title}]({link})"
    if meta:
        content += f"\n<font color='grey'>{meta}</font>"
    return {"tag": "div", "text": {"tag": "lark_md", "content": content}}


def _category_blocks(category, items, keywords_cfg):
    label = keywords_cfg["category_labels"].get(category, category)
    blocks = [{"tag": "div", "text": {"tag": "lark_md", "content": f"**{label}**"}}]
    blocks.extend(_entry_line(e) for e in items)
    blocks.append({"tag": "hr"})
    return blocks


def _build_footer(results, total_entries):
    failed = [r for r in results if not r["ok"]]
    text = f"共 {total_entries} 条 / 扫描 {len(results)} 源"
    if failed:
        text += f" · {len(failed)} 源抓取失败"
    return {"tag": "note", "elements": [{"tag": "plain_text", "content": text}]}


def _build_header(mode):
    label = "数字金融雷达 · 每日快报" if mode == "daily" else "数字金融雷达 · 周报"
    date_str = datetime.datetime.now().strftime("%m月%d日")
    return {"title": {"tag": "plain_text", "content": f"{label} · {date_str}"}, "template": "blue"}


def _wrap(header, elements):
    return {
        "msg_type": "interactive",
        "card": {"config": {"wide_screen_mode": True}, "header": header, "elements": elements},
    }


def _card_size(card):
    return len(json.dumps(card, ensure_ascii=False).encode("utf-8"))


def build_cards(by_category, keywords_cfg, mode, results):
    """返回卡片 JSON 列表（通常为 1 条，内容过多时按分类边界拆分为多条）。"""
    total_entries = sum(len(v) for v in by_category.values())
    header = _build_header(mode)
    footer = _build_footer(results, total_entries)

    if total_entries == 0:
        return [
            _wrap(
                header,
                [
                    {"tag": "div", "text": {"tag": "lark_md", "content": "本轮没有新内容满足筛选阈值。"}},
                    footer,
                ],
            )
        ]

    category_chunks = [
        _category_blocks(cat, by_category[cat], keywords_cfg)
        for cat in keywords_cfg["category_order"]
        if by_category.get(cat)
    ]

    cards = []
    current = []
    for blocks in category_chunks:
        candidate = current + blocks
        if current and _card_size(_wrap(header, candidate)) > MAX_CARD_BYTES:
            cards.append(_wrap(header, current))
            current = blocks
        else:
            current = candidate
    if current:
        cards.append(_wrap(header, current))

    cards[-1]["card"]["elements"].append(footer)
    return cards
