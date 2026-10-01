"""去重：URL 规范化、标题指纹、seen.json 状态读写与裁剪。"""

import hashlib
import json
import os
import re
import string
import urllib.parse
import datetime

RETENTION_DAYS = 60

_TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "ref", "fbclid", "gclid", "source", "mc_cid", "mc_eid",
}

_STOPWORDS = {
    "a", "an", "the", "of", "in", "on", "for", "to", "and", "or", "is", "are",
    "with", "at", "by", "from", "as", "its", "this", "that", "amid", "after",
    "over", "into", "new", "says",
}


def normalize_url(url):
    if not url:
        return ""
    parsed = urllib.parse.urlsplit(url)
    query = [
        (k, v) for k, v in urllib.parse.parse_qsl(parsed.query)
        if k.lower() not in _TRACKING_PARAMS
    ]
    path = parsed.path.rstrip("/")
    normalized = parsed._replace(
        scheme=parsed.scheme.lower(),
        netloc=parsed.netloc.lower(),
        path=path,
        query=urllib.parse.urlencode(query),
        fragment="",
    )
    return urllib.parse.urlunsplit(normalized)


def title_fingerprint(title):
    lowered = (title or "").lower()
    no_punct = lowered.translate(str.maketrans("", "", string.punctuation))
    words = [w for w in re.split(r"\s+", no_punct) if w and w not in _STOPWORDS]
    key = " ".join(words[:8])
    return hashlib.sha1(key.encode("utf-8")).hexdigest()


def collapse_duplicates(entries):
    """同一事件被多家源报道时，只保留 source weight 最高的那条。
    若本批次条目尚未打分，用 weight 排序；entries 顺序中先出现者在平手时胜出。"""
    best_by_fingerprint = {}
    order = []
    for entry in entries:
        fp = title_fingerprint(entry.get("title", ""))
        entry["_fingerprint"] = fp
        existing = best_by_fingerprint.get(fp)
        if existing is None:
            best_by_fingerprint[fp] = entry
            order.append(fp)
        elif entry.get("weight", 0) > existing.get("weight", 0):
            best_by_fingerprint[fp] = entry
    return [best_by_fingerprint[fp] for fp in order]


def load_seen(path):
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}


def save_seen(path, seen, retention_days=RETENTION_DAYS):
    cutoff = datetime.datetime.now(tz=datetime.timezone.utc) - datetime.timedelta(
        days=retention_days
    )
    pruned = {}
    for fp, iso_date in seen.items():
        try:
            dt = datetime.datetime.fromisoformat(iso_date)
        except ValueError:
            continue
        if dt >= cutoff:
            pruned[fp] = iso_date
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(pruned, f, ensure_ascii=False, indent=2, sort_keys=True)


def filter_unseen(entries, seen):
    """丢弃已经在 seen.json 里出现过的条目（即之前某一轮已经推送过）。"""
    return [e for e in entries if e.get("_fingerprint") not in seen]


def filter_fresh(entries, max_age_days):
    """丢弃发布时间早于 max_age_days 的条目。

    周更/月更的源（如 Net Interest）的 RSS feed 里常年带着几个月前的旧文章，
    "没在 seen.json 里出现过"不代表"新鲜"——没有这层过滤，老文章会挤占
    本该属于当天新内容的名额。没有 published 字段的条目视为无法判断，予以保留。
    """
    if not max_age_days:
        return entries
    cutoff = datetime.datetime.now(tz=datetime.timezone.utc) - datetime.timedelta(
        days=max_age_days
    )
    fresh = []
    for e in entries:
        published = e.get("published")
        if not published:
            fresh.append(e)
            continue
        try:
            pub_dt = datetime.datetime.fromisoformat(published)
        except ValueError:
            fresh.append(e)
            continue
        if pub_dt >= cutoff:
            fresh.append(e)
    return fresh


def mark_seen(seen, entries):
    now_iso = datetime.datetime.now(tz=datetime.timezone.utc).isoformat()
    for entry in entries:
        fp = entry.get("_fingerprint") or title_fingerprint(entry.get("title", ""))
        seen[fp] = now_iso
    return seen
