import re


def is_usps_shipment(carrier, tracking_number):
    return classify_carrier(carrier, tracking_number) == "USPS"


def classify_carrier(carrier, tracking_number):
    carrier_text = str(carrier or "").casefold()
    tracking = re.sub(r"\s+", "", str(tracking_number or "")).upper()
    if tracking.startswith("GFUS") or "gofo" in carrier_text:
        return "GOFO"
    if "fedex" in carrier_text or "联邦快递" in carrier_text:
        return "FedEx"
    if "swiftx" in carrier_text or "swift x" in carrier_text:
        return "SwiftX"
    if "uniuni" in carrier_text or "uni uni" in carrier_text:
        return "UniUni"
    if "ups" in carrier_text or tracking.startswith("1Z"):
        return "UPS"
    if (
        re.fullmatch(r"9\d{19,21}", tracking)
        or re.fullmatch(r"[A-Z]{2}\d{9}US", tracking)
        or re.fullmatch(r"82\d{8}", tracking)
    ):
        return "USPS"
    return "其他待确认"


def classify_usps_subtype(carrier, tracking_number, source_payload=None):
    """Classify the pickup channel inside the USPS tracking family."""
    if classify_carrier(carrier, tracking_number) != "USPS":
        return ""
    service_provider = extract_service_provider(source_payload)
    provider_text = service_provider.casefold()
    carrier_text = str(carrier or "").casefold()
    if "tiktok" in provider_text or "cbt" in provider_text:
        return "CBT"
    if "gofo" in provider_text or "cbs" in provider_text:
        return "CBS"
    if "cbt" in carrier_text or "tiktok" in carrier_text:
        return "CBT"
    if "cbs" in carrier_text:
        return "CBS"
    return "普通USPS"


def extract_service_provider(source_payload):
    """Return the ERP service-provider name from current or merged payloads."""
    names = []

    def visit(value):
        if isinstance(value, dict):
            for key, item in value.items():
                normalized = re.sub(r"[^a-z]", "", str(key).casefold())
                if normalized in {"serviceprovider", "serviceprovidername"}:
                    if item not in (None, ""):
                        names.append(str(item).strip())
                elif isinstance(item, (dict, list)):
                    visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(source_payload)
    return next((name for name in names if name), "")


def usps_pickup_name(subtype):
    return {
        "CBT": "TikTok指定物流商",
        "CBS": "GOFO",
        "普通USPS": "USPS",
    }.get(str(subtype or ""), "")
