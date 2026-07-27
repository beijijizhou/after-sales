from automation.api.diy19 import (
    DIY19_BASE_URLS,
    load_diy19_credentials,
)
from automation.api.fangguo import load_fangguo_credentials
from automation.api.hansen import load_hansen_credentials
from automation.api.sds import load_sds_credentials
from automation.production import SDS_PLATFORM_PROFILES


def load_platform_credentials(platform):
    empty_secrets = {}
    if platform in SDS_PLATFORM_PROFILES:
        return load_sds_credentials(
            empty_secrets, SDS_PLATFORM_PROFILES[platform]
        )
    if platform == "汉森":
        return load_hansen_credentials(empty_secrets)
    if platform == "方果":
        return load_fangguo_credentials(empty_secrets)
    if platform in DIY19_BASE_URLS:
        return load_diy19_credentials(empty_secrets, platform)
    return None
