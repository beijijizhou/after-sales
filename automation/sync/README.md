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

## 自动运行

`com.after-sales.production-sync.plist` 供 macOS `launchd` 使用，
每天纽约时间 00:30 补齐最近 7 天的缺失数据。

蜂鸟 ERP 和 S2B 依赖本机 Chrome 登录状态；API 平台使用本地凭据。
