import re


_SOURCE_NAME_PATTERN = re.compile(
    r"表格(?P<name>[^；｜，,:：]+柜)"
)
_UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def get_container_business_name(container_key, container_no="", notes=None):
    """Return the human batch/remark name used as the primary UI identity."""
    key = str(container_key or "").strip()
    number = str(container_no or "").strip()
    for note in notes or []:
        match = _SOURCE_NAME_PATTERN.search(str(note or ""))
        if match:
            return match.group("name").strip()
    if key and not key.startswith("record-") and not _UUID_PATTERN.match(key):
        return key
    return number or key or "未命名货柜"


def get_container_display_label(
    container_key, container_no="", notes=None, business_name="",
):
    """Show the business name first and physical container number second."""
    name = str(business_name or "").strip() or get_container_business_name(
        container_key, container_no, notes
    )
    number = str(container_no or "").strip()
    if number and number not in {name, str(container_key or "").strip()}:
        return f"{name}｜柜号 {number}"
    return name
