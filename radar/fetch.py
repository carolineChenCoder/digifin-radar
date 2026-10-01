"""并发抓取所有配置源，单源失败不影响整轮。"""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from radar.collectors import collect


def _fetch_one(source, defaults):
    started = time.monotonic()
    try:
        entries = collect(source, defaults)
        for e in entries:
            e["source_id"] = source["id"]
            e["source_name"] = source["name"]
            e["categories"] = source["categories"]
            e["weight"] = source.get("weight", 0)
        return {
            "source_id": source["id"],
            "source_name": source["name"],
            "ok": True,
            "count": len(entries),
            "entries": entries,
            "error": None,
            "elapsed": time.monotonic() - started,
        }
    except Exception as exc:  # noqa: BLE001 - 单源失败必须被捕获，不能让整轮中断
        return {
            "source_id": source["id"],
            "source_name": source["name"],
            "ok": False,
            "count": 0,
            "entries": [],
            "error": f"{type(exc).__name__}: {exc}",
            "elapsed": time.monotonic() - started,
        }


def fetch_all(sources, defaults, max_workers=10):
    """返回 (all_entries, results)。
    all_entries: 所有源抓到的条目拼成一个列表，已打好 source 元信息。
    results: 每个源的抓取状态（成功/失败/耗时/条数），用于诊断与卡片底部统计。
    """
    results = []
    all_entries = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_fetch_one, src, defaults): src for src in sources}
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            all_entries.extend(result["entries"])
    return all_entries, results
