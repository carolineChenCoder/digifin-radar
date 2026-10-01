"""关键词打分 + 分类归属 + 阈值筛选。"""


def _hits(text, keywords):
    return sum(1 for k in keywords if k.lower() in text)


def score_entry(entry, keywords_cfg):
    """返回 (score, category)。category 为 None 表示该条目没有命中任何合法分类
    （理论上不会发生，因为每个 source 至少声明一个 category）。"""
    title = (entry.get("title") or "").lower()
    summary = (entry.get("summary") or "").lower()
    text = f"{title} {summary}"

    noise_hit = _hits(text, keywords_cfg["noise"]) > 0

    best_category = None
    best_cat_score = None
    for category in entry["categories"]:
        cfg = keywords_cfg["categories"].get(category, {})
        strong = cfg.get("strong", [])
        weak = cfg.get("weak", [])
        domain = cfg.get("domain")

        title_strong = min(_hits(title, strong), 2)
        summary_strong = min(_hits(summary, strong), 2)
        title_weak = min(_hits(title, weak), 1)

        cat_score = 3 * title_strong + 1 * summary_strong + 1 * title_weak

        # domain 关卡：泛化的 VC/创投词汇必须搭配金融领域词才算数，
        # 否则任何赛道的融资新闻都会被收进 market 分类
        if domain and _hits(text, domain) == 0:
            cat_score = 0

        if best_cat_score is None or cat_score > best_cat_score:
            best_cat_score = cat_score
            best_category = category

    score = entry.get("weight", 0) + (best_cat_score or 0)
    if noise_hit:
        score -= 6
    return score, best_category


def select_entries(entries, keywords_cfg, mode):
    """对已去重的条目打分，按阈值和每类上限筛选。

    返回 (by_category, all_scored):
      by_category: {category: [entry, ...]}，已按 score 降序截断，仅含过线的条目
      all_scored: 全部条目（含未过线的），每条附带 score/category，供 dry-run 诊断
    """
    threshold = keywords_cfg["threshold"][mode]
    max_per_category = keywords_cfg["max_per_category"]

    all_scored = []
    for entry in entries:
        score, category = score_entry(entry, keywords_cfg)
        scored_entry = dict(entry)
        scored_entry["score"] = score
        scored_entry["category"] = category
        all_scored.append(scored_entry)

    by_category = {cat: [] for cat in keywords_cfg["category_order"]}
    for entry in all_scored:
        if entry["category"] is None:
            continue
        if entry["score"] >= threshold:
            by_category[entry["category"]].append(entry)

    for cat, items in by_category.items():
        items.sort(key=lambda e: e["score"], reverse=True)
        by_category[cat] = items[:max_per_category]

    return by_category, all_scored
