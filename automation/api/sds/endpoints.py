FACTORY_PRIMARY_BASE_URL = "https://g-factory-api.sdspod.com"
POD_PRIMARY_BASE_URL = "https://g-pod-api.sdspod.com"
FACTORY_COMPAT_BASE_URL = "https://factory-api.sdspod.com"
PARCEL_COMPAT_BASE_URL = "https://pod-api.sdspod.com"


def sds_endpoint_urls(path, *, primary_base_url, compatibility_base_url):
    normalized_path = f"/{str(path).lstrip('/')}"
    return (
        f"{primary_base_url}{normalized_path}",
        f"{compatibility_base_url}{normalized_path}",
    )
