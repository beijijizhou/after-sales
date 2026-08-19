# 蜂鸟官方开放 API

官方文档入口：<https://open.hihumbird.com/api/>

本项目的 Haloo、莆田和隆丰生产数据在配置各自的开放平台 Key 后，优先使用
蜂鸟官方开放平台，不依赖 Chrome、Playwright、网页登录状态或网页登录
token。尚未配置开放平台 Key 的平台继续使用原有服务器 token 适配器。

Haloo 原有 Bearer token 接口继续保留。生产与物流读取采用三级授权链：先请求官方
开放 API；遇到无权限、限流或临时故障时，从 `erp_api_credentials` 读取加密的
共享 token，直接请求生产项与订单物流详情，不启动浏览器；只有共享 token
缺失或确实失效时，才在管理员本机启动专用 Chrome。登录完成后，新 token 会
从真实 API 请求的 `Authorization` 请求头捕获，同时写入本地忽略文件和数据库，
再用备用 API 继续读取。登录流程最长等待三分钟，捕获和回写成功后会在同一次
同步中继续执行，不要求用户再次点击。云端不能启动本地 Chrome，因此会明确
提示管理员回到本地刷新授权。

查询成功但返回 0 条属于有效业务结果，不触发备用通道，也不会打开浏览器。
页面状态会显示当前使用的级别、切换原因、订单详情读取批次和最终物流关系数。
官方接口明确返回限流后，该平台会冷却十分钟；冷却期内直接进入数据库 token
通道，避免短时间重复撞限流。备用生产列表单页最多读取 10,000 条，订单详情
按接口限制每批最多 200 个订单，并复用同一次已验证的 token。

## 部署配置

在本地 `.streamlit/secrets.toml` 或 Streamlit Community Cloud 的 Secrets 中按
平台分别配置。真实 Key 不得写入 Git、日志或页面：

```toml
[humbird_open_api."Haloo"]
api_key = "Haloo 账号在蜂鸟商家后台生成的 API Key"

[humbird_open_api."莆田"]
api_key = "莆田账号在蜂鸟商家后台生成的 API Key"

[humbird_open_api."隆丰"]
api_key = "隆丰账号在蜂鸟商家后台生成的 API Key"
```

每个 Key 只代表生成它的蜂鸟商家账号，不能用 Haloo Key 读取莆田或隆丰。
未配置某个平台的独立 Key 时，该平台才会回退到数据库加密保存的 Bearer token。

## 已接入链路

统一网关：`https://open.hihumbird.com/api/router`

所有请求使用 `x-api-key` 请求头，并在请求参数中带 `api_type`。

| 能力 | `api_type` | 项目用途 |
| --- | --- | --- |
| 生产项查询 | `oc.production.item.page` | 按纽约日期读取生产项、订单、数量、状态和生产/发货时间 |
| 商品详情 | `spu.selection.spu.get` | 用 `spu_id + sku_id` 补齐商品名称、颜色和尺码；同一商品会缓存复用 |
| 获取物流面单 | `logistics.waybill.get` | 官方通道按订单号获取物流商、物流单号、面单 PDF 和面单尺寸 |
| 确认发货 | `logistics.delivery.confirm` | 写操作；当前只记录文档能力，系统不会在读取链路中自动调用 |

生产数据入口位于“生产数据”页面；Haloo 和隆丰的物流入口均位于“物流单号
追踪 → 从 ERP 自动读取”，并复用同一个蜂鸟开放平台适配器。物流结果继续进入
共享的物流识别、USPS 筛选、面单 OCR 和数据库缓存流程，不为不同蜂鸟账号
建立重复页面或数据表。

备用通道使用蜂鸟商家端现有只读接口：生产项接口取得内部订单 ID，再由订单详情
接口的 `third_detail.track_number_list` 恢复订单号与物流单号关系。若旧接口
响应本身不提供面单 PDF，系统保留物流关系但不会虚构链接，OCR 仍只处理实际
存在的面单文件。

## 状态口径

- 生产项 `status = -1 / 1 / 5 / 9` 分别表示待接单、已接单、生产中、已生产。
- `status=9` 表示生产与质检已完成，对应本系统的 `已生产/已发货` 阶段；
  `delivery_time` 是时间证据，但面单存在与否不是该阶段的定义。
- 蜂鸟“已发货”不等同于 USPS 已揽收；USPS 是否仍为 Pre-Shipment 必须继续
  通过 USPS Tracking API 核验。
- `logistics.delivery.confirm` 会改变外部订单状态，未经用户明确确认不得调用。

## 查询限制

蜂鸟生产项接口的 `created_range` 单次最多 30 天，每页最多 200 条。项目会在
取得总数后并行分页读取完整结果，按生产项编码去重，并按订单号去重后查询面单。
