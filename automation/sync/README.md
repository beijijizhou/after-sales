# 每日生产数据同步

该任务只更新本地生产数据缓存，不读取或修改库存数量。

## 手动检查

```bash
.venv/bin/python -m automation.sync.daily --status
```

## 手动补齐

默认补齐最近 7 天中缺失的完整日期，截止到纽约时间的昨天：

```bash
.venv/bin/python -m automation.sync.daily
```

补指定日期：

```bash
.venv/bin/python -m automation.sync.daily --date 2026-07-25
```

已有完整缓存会直接跳过。失败的平台会保留为部分缓存，下次运行时只补缺少的平台。

库存总结中的彩色短袖补录也复用这套按日同步：完整缓存存在时直接
使用；缓存缺失或不完整时，自动逐日请求生产平台并写回缓存。多日补录
最多同时处理 2 天，避免把整个日期区间作为一次大请求。补齐后的每日
缓存同时供库存扣减预览和最近 14 天消耗模型使用。
彩色短袖的主要平台快速缓存会立即进入消耗模型；后续全平台缓存完成后，
同一生产日期按最新缓存重新计算，不叠加成两份数据。

## 自动运行

`com.after-sales.production-sync.plist` 供 macOS `launchd` 使用，
每天纽约时间 00:30 补齐最近 7 天的缺失数据。

蜂鸟 ERP 和 S2B 依赖本机 Chrome 登录状态；API 平台使用本地凭据。
