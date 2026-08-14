# 蜂鸟官方开放 API

官方文档入口：<https://open.hihumbird.com/api/>

本项目的 Haloo、莆田和隆丰生产数据在配置各自的开放平台 Key 后，优先使用
蜂鸟官方开放平台，不依赖 Chrome、Playwright、网页登录状态或网页登录
token。尚未配置开放平台 Key 的平台继续使用原有服务器 token 适配器。

Haloo 原有 Bearer token + HMAC 生产接口继续保留。系统会同时加载官方 API
Key 与数据库中的旧 token；官方生产接口无权限、限流或临时故障时，自动切换
到旧接口备用通道，并在页面进度和数据来源中明确显示。旧接口当前不提供开放
平台的物流面单能力，因此物流读取不会伪造回退结果。

## 部署配置

在本地 `.streamlit/secrets.toml` 或 Streamlit Community Cloud 的 Secrets 中按
平台分别配置。真实 Key 不得写入 Git、日志或页面：

```toml
[humbird_open_api."Haloo"]
api_key = "Haloo 账号在蜂鸟商家后台生成的 API Key"

[humbird_open_api."隆丰"]
api_key = "隆丰账号在蜂鸟商家后台生成的 API Key"
```

## 已接入链路

统一网关：`https://open.hihumbird.com/api/router`

所有请求使用 `x-api-key` 请求头，并在请求参数中带 `api_type`。

| 能力 | `api_type` | 项目用途 |
| --- | --- | --- |
| 生产项查询 | `oc.production.item.page` | 按纽约日期读取生产项、订单、数量、状态和生产/发货时间 |
| 商品详情 | `spu.selection.spu.get` | 用 `spu_id + sku_id` 补齐商品名称、颜色和尺码；同一商品会缓存复用 |
| 获取物流面单 | `logistics.waybill.get` | 按订单号获取物流商、物流单号、面单 PDF 和面单尺寸 |
| 确认发货 | `logistics.delivery.confirm` | 写操作；当前只记录文档能力，系统不会在读取链路中自动调用 |

生产数据入口位于“生产数据”页面；Haloo 和隆丰的物流入口均位于“物流单号
追踪 → 从 ERP 自动读取”，并复用同一个蜂鸟开放平台适配器。物流结果继续进入
共享的物流识别、USPS 筛选、面单 OCR 和数据库缓存流程，不为不同蜂鸟账号
建立重复页面或数据表。

## 状态口径

- 生产项 `status = -1 / 1 / 5 / 9` 分别表示待接单、已接单、生产中、已生产。
- `delivery_time` 有值表示蜂鸟记录中已经发货。
- 蜂鸟“已发货”不等同于 USPS 已揽收；USPS 是否仍为 Pre-Shipment 必须继续
  通过 USPS Tracking API 核验。
- `logistics.delivery.confirm` 会改变外部订单状态，未经用户明确确认不得调用。

## 查询限制

蜂鸟生产项接口的 `created_range` 单次最多 30 天，每页最多 200 条。项目会在
取得总数后并行分页读取完整结果，按生产项编码去重，并按订单号去重后查询面单。
