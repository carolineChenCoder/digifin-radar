"""发送卡片到 Lark webhook：可选签名、失败重试、多卡间隔发送。"""

import base64
import hashlib
import hmac
import time

import requests


def _gen_sign(timestamp, secret):
    # Lark 自定义机器人签名算法：key=f"{timestamp}\n{secret}"，对空消息体做 HMAC-SHA256
    string_to_sign = f"{timestamp}\n{secret}"
    hmac_code = hmac.new(string_to_sign.encode("utf-8"), digestmod=hashlib.sha256).digest()
    return base64.b64encode(hmac_code).decode("utf-8")


def send_card(webhook_url, card, secret=None, max_retries=3, timeout=15):
    payload = dict(card)
    if secret:
        timestamp = str(int(time.time()))
        payload["timestamp"] = timestamp
        payload["sign"] = _gen_sign(timestamp, secret)

    last_error = None
    for attempt in range(max_retries):
        try:
            resp = requests.post(webhook_url, json=payload, timeout=timeout)
            resp.raise_for_status()
            body = resp.json()
            # Lark 常见坑：HTTP 200 但 body.code != 0 代表业务失败（签名错误、群已解散等）
            if body.get("code", 0) != 0:
                raise RuntimeError(f"Lark API 返回错误: {body}")
            return body
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt < max_retries - 1:
                time.sleep(2**attempt)
    raise RuntimeError(f"发送 Lark 消息失败，已重试 {max_retries} 次: {last_error}")


def send_cards(webhook_url, cards, secret=None, interval=3):
    """依次发送多张卡片，间隔 interval 秒以避开限流（约 20 次/分钟）。"""
    results = []
    for i, card in enumerate(cards):
        if i > 0:
            time.sleep(interval)
        results.append(send_card(webhook_url, card, secret=secret))
    return results
