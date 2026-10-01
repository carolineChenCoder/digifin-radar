"""每种 source.type 对应一个 collector，统一返回条目列表：
    [{"title": str, "link": str, "summary": str, "published": iso8601str|None}, ...]
抓取相关的网络细节（超时、UA、重试）都在这里，fetch.py 只负责编排与容错。
"""

import calendar
import datetime
import urllib.parse

import feedparser
import requests


def _struct_to_iso(struct_time):
    if not struct_time:
        return None
    return datetime.datetime.fromtimestamp(
        calendar.timegm(struct_time), tz=datetime.timezone.utc
    ).isoformat()


def _parse_feed_bytes(content):
    parsed = feedparser.parse(content)
    entries = []
    for e in parsed.entries:
        published = _struct_to_iso(
            getattr(e, "published_parsed", None) or getattr(e, "updated_parsed", None)
        )
        entries.append(
            {
                "title": getattr(e, "title", "").strip(),
                "link": getattr(e, "link", "").strip(),
                "summary": getattr(e, "summary", "").strip(),
                "published": published,
            }
        )
    return entries


def fetch_rss(url, timeout, user_agent):
    resp = requests.get(url, timeout=timeout, headers={"User-Agent": user_agent})
    resp.raise_for_status()
    return _parse_feed_bytes(resp.content)


def fetch_google_news(query, timeout, user_agent):
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode(
        {"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"}
    )
    return fetch_rss(url, timeout, user_agent)


def fetch_federal_register(terms, doc_types, agencies, timeout, user_agent):
    """按关键词 + 文档类型 + 机构白名单检索。

    Federal Register 的 conditions[term] 是全文模糊检索，不加机构限制时，
    "digital asset"/"tokenization" 这类词会在无关领域的文档里命中
    （例如核反应堆监管文档讨论"数字化仪表资产"），必须用机构白名单收窄。
    """
    entries = []
    seen_links = set()
    for term in terms:
        # conditions[type][] / conditions[agencies][] 需要重复键，requests 的 dict 参数无法表达，手动拼 query string
        query_parts = [
            ("per_page", 20),
            ("order", "newest"),
            ("conditions[term]", term),
        ]
        for dt in doc_types:
            query_parts.append(("conditions[type][]", dt))
        for agency in agencies:
            query_parts.append(("conditions[agencies][]", agency))
        url = "https://www.federalregister.gov/api/v1/documents.json?" + urllib.parse.urlencode(
            query_parts
        )
        resp = requests.get(url, timeout=timeout, headers={"User-Agent": user_agent})
        resp.raise_for_status()
        data = resp.json()
        for r in data.get("results", []):
            link = r.get("html_url", "")
            if not link or link in seen_links:
                continue
            seen_links.add(link)
            agency_names = ", ".join(a.get("name", "") for a in r.get("agencies", []))
            pub_date = r.get("publication_date")
            published = None
            if pub_date:
                published = datetime.datetime.strptime(pub_date, "%Y-%m-%d").replace(
                    tzinfo=datetime.timezone.utc
                ).isoformat()
            entries.append(
                {
                    "title": r.get("title", "").strip(),
                    "link": link,
                    "summary": f"{r.get('type', '')} · {agency_names}".strip(" ·"),
                    "published": published,
                }
            )
    return entries


def fetch_defillama():
    """返回一条汇总性的数据快照条目，供周报展示稳定币总量变化。"""
    resp = requests.get(
        "https://stablecoins.llama.fi/stablecoincharts/all",
        timeout=15,
        headers={"User-Agent": "Mozilla/5.0 (compatible; DigiFinRadar/1.0)"},
    )
    resp.raise_for_status()
    points = resp.json()
    if len(points) < 8:
        return []

    def total_usd(point):
        return point.get("totalCirculating", {}).get("peggedUSD", 0)

    latest = points[-1]
    week_ago = points[-8]
    latest_total = total_usd(latest)
    prev_total = total_usd(week_ago)
    if prev_total == 0:
        return []
    pct = (latest_total - prev_total) / prev_total * 100
    direction = "增长" if pct >= 0 else "下降"
    summary = (
        f"全球稳定币流通总量约 ${latest_total / 1e9:,.1f}B，"
        f"较一周前{direction} {abs(pct):.2f}%"
    )
    return [
        {
            "title": "稳定币市场周度快照（DefiLlama）",
            "link": "https://defillama.com/stablecoins",
            "summary": summary,
            "published": datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
        }
    ]


def collect(source, defaults):
    """按 source["type"] 分派到对应 collector，返回条目列表。"""
    timeout = source.get("timeout", defaults.get("timeout", 15))
    user_agent = defaults.get("user_agent", "Mozilla/5.0 (compatible; DigiFinRadar/1.0)")
    stype = source["type"]

    if stype == "rss":
        return fetch_rss(source["url"], timeout, user_agent)
    if stype == "google_news":
        return fetch_google_news(source["query"], timeout, user_agent)
    if stype == "federal_register":
        return fetch_federal_register(
            source["terms"], source["doc_types"], source["agencies"], timeout, user_agent
        )
    if stype == "defillama":
        return fetch_defillama()
    raise ValueError(f"unknown source type: {stype}")
