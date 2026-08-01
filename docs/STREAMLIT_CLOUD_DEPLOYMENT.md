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

Never commit real values to GitHub. Streamlit Cloud injects these values only
on the server. Browser users can run authorized operations but cannot read the
secret values from the UI.

## User access

Only users whose Supabase application role is `after_sales` or `admin` can see
or directly open the logistics page. Adding secrets does not grant page access;
each employee still needs an application account with one of those roles.

## S2B limitation

USPS and SDS can authenticate directly from the cloud secrets. S2B currently
uses a captured bearer token. Streamlit Community Cloud cannot open the local
dedicated Chrome profile to refresh an expired S2B login. When an S2B token
expires, update that token in Streamlit Cloud Secrets and reboot the app, or
deploy a separate server-side S2B refresh service.

## Deployment check

After saving Secrets, reboot the app and verify with an `after_sales` account:

1. The `物流单号追踪` navigation entry is visible.
2. `刷新数据库缓存` returns cached shipment rows.
3. A forced USPS test returns tracking events.
4. SDS synchronization works for each configured line.
5. S2B synchronization works for each configured account.
