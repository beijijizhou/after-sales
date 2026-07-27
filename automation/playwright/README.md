# 蜂鸟 ERP 登录会话

## 第一次运行

安装项目依赖：

```bash
.venv/bin/python -m pip install -r requirements.txt
```

从 Haloo 工厂端登录入口打开专用 Chrome：

```bash
.venv/bin/python -m automation.playwright.haloo_capture
```

1. 脚本会优先连接已经打开的专用 Chrome。
2. 在 Chrome 中手动完成滑块验证和登录。
3. Haloo、莆田、隆丰分别登录一次后会保留各自会话。

后续生产数据同步只复用登录状态，并直接调用 ERP 自带 API。正常同步不会
点击筛选控件、切换页面或导出 Excel。登录失效时，系统才会提示重新登录。

Chrome 登录状态保存在本机 `automation/playwright/.auth/`。令牌只在浏览器
内存中使用，不写入代码、缓存或日志。

S2B 暂时仍使用原来的导出流程，后续会独立迁移到它自己的 API。
