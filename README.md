# DigiFin Radar

数字金融资讯自动聚合，按「CBDC/稳定币/代币化」「监管与合规」「创投与市场格局」三个分类，
定时推送到 Lark 群。纯聚合，不调用任何 LLM。

## 工作原理

1. 并发抓取 `sources.yaml` 里配置的所有源（RSS / Federal Register API / Google News 桥接 / DefiLlama 数据快照）
2. 按标题指纹去重，跨源命中同一事件时只保留 `weight` 最高的源
3. 按 `keywords.yaml` 的关键词打分，过滤掉已经推送过的内容
4. 每个分类按分数排序截断，渲染成 Lark 交互卡片
5. 发送到 Lark 群，发送成功后把本轮内容标记为"已发送"写回 `state/seen.json`

工作日（周一至周五）跑 `daily`，周一额外跑 `weekly`（附带 DefiLlama 稳定币市场周度数据快照）。

## 上线步骤

### 1. 建 Lark 自定义机器人

Lark 群 → 群设置 → 群机器人 → 添加机器人 → 自定义机器人。复制生成的 webhook URL
（形如 `https://open.larksuite.com/open-apis/bot/v2/hook/xxxxxxxx`）。

建议同时开启"签名校验"，拿到对应的 secret——没有签名校验的话，任何人拿到 webhook URL
都能往你的群里发消息。

> **重要**：webhook URL 和 secret 都不要提交进仓库，只放在 GitHub Secrets 里（见下）。

### 2. 配置 GitHub Secrets

仓库 Settings → Secrets and variables → Actions → New repository secret：

| Name | Value |
|---|---|
| `LARK_WEBHOOK_URL` | 上一步复制的 webhook URL |
| `LARK_WEBHOOK_SECRET` | 签名校验的 secret（如果开启了的话，可选） |

### 3. 验证

Actions 页 → 选择 `daily` 或 `weekly` workflow → Run workflow（手动触发一次）。
成功后 Lark 群里应该能收到卡片，仓库里会多一条 `chore: update seen state [skip ci]` 的自动提交。

之后 `daily` 在北京时间工作日早上 8:23 自动跑，`weekly` 在周一早上 9:23 自动跑
（GitHub Actions 只认 UTC，已在 workflow 里换算好；若你不在北京时区，改
`.github/workflows/*.yml` 里的 `cron` 字段即可）。

## 本地调试

```bash
pip install -r requirements.txt

# 只打印，不发送，不改 state/seen.json —— 日常改配置后用这个验证
python run.py --mode daily --dry-run
python run.py --mode weekly --dry-run

# 真实发送到 Lark（需要先设好环境变量）
export LARK_WEBHOOK_URL='https://open.larksuite.com/open-apis/bot/v2/hook/xxx'
export LARK_WEBHOOK_SECRET='xxx'   # 可选
python run.py --mode daily
```

`--dry-run` 会打印三张表：每个源的抓取状态、打分明细（含未入选的条目，方便判断阈值是否合理）、
最终生成的卡片 JSON。

## 调整信噪比

信噪比完全由两个配置文件控制，不需要改代码：

- **`sources.yaml`**：每个源的 `weight`（基础分）。高质量源给高权重，泛内容源给 0 甚至更低，
  让它必须靠关键词命中才能入选。
- **`keywords.yaml`**：
  - `threshold.daily` / `threshold.weekly`：入选门槛，越高越严格
  - `max_per_category`：每个分类每轮最多推送几条
  - 各分类的 `strong` / `weak` 关键词：命中 strong 比 weak 加分更多
  - `domain`（目前只有 `market` 分类用）：额外关卡，防止泛化的创投词汇
    （funding / IPO / valuation）把非金融赛道的新闻也收进来
  - `noise`：命中即大幅扣分，用来过滤散户向内容（price prediction、memecoin 之类）

建议上线一周后，对照实际收到的卡片内容人工评估，哪些源噪音多就调低 weight，
哪些分类覆盖不够就放宽 threshold 或扩充关键词。

## 加新源

在 `sources.yaml` 里加一条即可，不需要改代码。支持的 `type`：

- `rss`：标准 RSS/Atom feed
- `google_news`：没有自己 RSS 的源，用 Google News 搜索代理桥接（见现有的 `gnews-apac-reg` 示例）
- `federal_register`：美国联邦监管机构的规则制定文档，按关键词 + 文档类型 + 机构白名单过滤
- `defillama`：目前只接了稳定币市场快照，`weekly_only: true` 标记为仅周报展示

## 已知限制

- **Fintech Brainfood（Simon Taylor）没有接入**：全站无公开 RSS、无 Substack 镜像，
  保持邮件订阅手动读即可。如果一定要自动化，可以用
  [Kill the Newsletter](https://kill-the-newsletter.com/) 把订阅邮箱转成一个 RSS 地址，
  再按 `type: rss` 加进 `sources.yaml`。
- Google News 桥接源的标题质量参差不齐（同一条新闻可能被多家转载媒体重复收录），
  已有标题指纹去重兜底，但无法做到和一手 RSS 一样干净。
- `state/seen.json` 保留 60 天滚动窗口，超过这个窗口的旧指纹会被自动裁剪。
