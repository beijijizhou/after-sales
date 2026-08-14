# Streamlit Community Cloud deployment

The deployed app runs from the `main` branch of
`beijijizhou/after-sales`. Local files ignored by Git, including
`.streamlit/secrets.toml`, `local_factory_credentials.toml`, and the separate
USPS project, are not available to Streamlit Community Cloud.

## Required cloud secrets

Open the existing app in Streamlit Community Cloud, then choose
`App settings -> Secrets`. Copy the structure from
`.streamlit/secrets.example.toml` and replace every placeholder with the
corresponding local value.

The logistics page requires:

- `SUPABASE_URL`, `SUPABASE_KEY`, and a separate `AUTH_TOKEN_SECRET`;
- `USPS_CLIENT_ID` and `USPS_CLIENT_SECRET`;
- SDS factory and QA credentials for each enabled production line;
- `logistics_s2b_accounts.UV.token` and/or
  `logistics_s2b_accounts.DTF.token` when those accounts are enabled.

The Fangguo platform-finance tab uses
`factory_credentials."方果"`. Configure `username`, `password`, `tenant_id`,
and the tenant-specific `finance_group_ids` list. A short-lived `token` may be
used instead of username/password, but it must remain in Secrets and must
never be pasted into source code or logs. Username/password login tokens are
cached in server memory for 45 minutes by default; configure
`token_cache_seconds` to match the provider session lifetime.
For a fixed reconciliation scope, also configure `finance_customer_ids` and
`finance_customer_names`. The IDs preserve the provider identity while the
names drive the exact order-line filter returned by the finance endpoint.

Never commit real values to GitHub. Streamlit Cloud injects these values only
on the server. Browser users can run authorized operations but cannot read the
secret values from the UI.

## Shared Humbird ERP authorization

Haloo 优先使用蜂鸟官方开放平台。在 Streamlit Secrets 中配置
`HUMBIRD_OPEN_API_KEY`；官方文档与接口清单见
`docs/HUMBIRD_OPEN_API.md`。该模式不需要 Chrome、网页登录或 token 刷新。
原有数据库加密 token 继续保留为生产数据备用通道，官方 API 暂时不可用时
会自动回退；不要在启用 API Key 后删除旧 token。

Run `sql/production/erp_api_credentials.sql` once in Supabase before enabling
Haloo, 莆田, or 隆丰 production synchronization. Their bearer tokens are stored
encrypted in `erp_api_credentials`; the application derives the encryption key
from the server-side `SUPABASE_KEY`, so local and Cloud deployments using the
same service key can share the authorization without copying tokens into every
user's browser or Streamlit Secrets.

Every production API request first calls Humbird's refresh endpoint. If the
platform rotates the token, the replacement is encrypted and written back to
the database automatically. A fully invalidated login that can no longer be
refreshed is marked expired and requires one administrator login; ordinary
users never receive or edit the raw token.

## User access

Users whose Supabase application role is `supervisor`, `after_sales`, or
`admin` can see and directly open the logistics page. Supervisors have query
access only; ERP synchronization, OCR, label download, and USPS usage
calibration remain restricted to `after_sales` and `admin`. Adding secrets does
not grant page access; each employee still needs an application account with
one of those roles.

Before using the admin-only permissions page, run the six scripts in
`sql/access/role_management/` in numeric order. Its `README.md` contains the
installation and verification sequence. These migrations install the dynamic
role and permission catalog, audited user-role updates, administrator-created
role configuration, database-backed login permissions, and both append-only
audit histories.

## S2B limitation

USPS and SDS can authenticate directly from the cloud secrets. S2B currently
uses a captured bearer token. Streamlit Community Cloud cannot open the local
dedicated Chrome profile to refresh an expired S2B login. When an S2B token
expires, update that token in Streamlit Cloud Secrets and reboot the app, or
deploy a separate server-side S2B refresh service.

## Deployment check

GitHub Actions runs `.github/workflows/deployment-gate.yml` for every pull
request and every update to `main`:

1. `Pre-deploy page and unit tests` starts the main app and every Streamlit
   page in Python 3.14, then runs the full unit-test suite.
2. `Post-deploy online page smoke` waits for Community Cloud and opens every
   deployed page in Chromium. A red Streamlit exception, import error, or
   startup failure makes the deployment check fail.

In GitHub repository settings, protect `main`, require pull requests, and make
`Pre-deploy page and unit tests` a required status check. Community Cloud
automatically watches `main`; branch protection is what prevents untested code
from reaching that branch. Direct emergency pushes should remain disabled.

The online check can also be rerun from GitHub Actions with `Run workflow`.

After saving Secrets, reboot the app and verify with an `after_sales` account:

1. The `物流单号追踪` navigation entry is visible.
2. `刷新数据库缓存` returns cached shipment rows.
3. A forced USPS test returns tracking events.
4. SDS synchronization works for each configured line.
5. S2B synchronization works for each configured account.
