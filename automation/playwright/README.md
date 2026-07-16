# Haloo Playwright

## 第一次运行

安装项目依赖：

```bash
.venv/bin/python -m pip install -r requirements.txt
```

从 Haloo 工厂端登录入口打开，并采集已筛选订单页面：

```bash
.venv/bin/python -m automation.playwright.haloo_capture
```

1. 脚本会优先连接已经打开的专用 Chrome，不会重复打开页面。
2. 在 Chrome 中手动完成滑块验证和登录。
3. 进入订单页面并筛选目标日期。
4. 回到终端按 Enter。

脚本结束后 Chrome 会继续保持打开。后续同步会自动寻找 URL 中包含
`haloopod.merchant.hihumbird.com` 的标签页并直接复用。

Chrome 登录状态保存在本机 `automation/playwright/.auth/`，页面截图和 HTML 保存在
`output/automation/haloo/`。这两个目录都不会提交到 Git。

下一步根据采集页面确定订单表格、日期筛选和导出按钮的稳定定位方式。
