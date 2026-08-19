from automation.api.diy19 import (
    DIY19_BASE_URLS,
    load_diy19_credentials,
)
from automation.api.fangguo import load_fangguo_credentials
from automation.api.hansen import load_hansen_credentials
from automation.api.humbird.config import (
    load_humbird_credentials_with_local_refresh,
)
from automation.api.sds import load_sds_credentials
from automation.production import SDS_PLATFORM_PROFILES
from automation.playwright.haloo import ERP_PLATFORM_NAMES
from automation.logistics.config import load_s2b_account


def load_platform_credentials(
    platform, secrets=None, supabase=None, report_progress=None,
    updated_by="production-sync-local-refresh", department="DTF",
):
    configured_secrets = secrets or {}
    if platform in ERP_PLATFORM_NAMES:
        return load_humbird_credentials_with_local_refresh(
            configured_secrets,
            platform,
            supabase=supabase,
            updated_by=updated_by,
            report_progress=report_progress,
        )
    if platform == "S2B":
        account = department if department in {"DTF", "UV", "3D"} else "DTF"
        return load_s2b_account(configured_secrets, account)
    if platform in SDS_PLATFORM_PROFILES:
        return load_sds_credentials(
            configured_secrets, SDS_PLATFORM_PROFILES[platform]
        )
    if platform == "汉森":
        return load_hansen_credentials(configured_secrets)
    if platform == "方果":
        return load_fangguo_credentials(configured_secrets)
    if platform in DIY19_BASE_URLS:
        return load_diy19_credentials(configured_secrets, platform)
    return None
