import re


HANSEN_HOODIE_STYLES = {
    "mao": ("连帽薄款卫衣", "薄款"),
    "yuan": ("圆领薄款卫衣", "薄款"),
    "maohou": ("连帽加绒卫衣", "加绒"),
    "yuanhou": ("圆领加绒卫衣", "加绒"),
    "nvmaobao": ("女款连帽薄款卫衣", "薄款"),
}
HANSEN_UV_STYLES = {
    "tie": ("铁皮画", "铁"),
}
STYLE_PATTERN = re.compile(
    r"(?<![a-z])(" + "|".join(
        sorted(HANSEN_HOODIE_STYLES, key=len, reverse=True)
    ) + r")(?![a-z])",
    re.IGNORECASE,
)


def get_hansen_hoodie_style(style_code):
    return HANSEN_HOODIE_STYLES.get(str(style_code or "").casefold())


def find_hansen_hoodie_style(text):
    match = STYLE_PATTERN.search(str(text or ""))
    if not match:
        return None
    return HANSEN_HOODIE_STYLES[match.group(1).casefold()]


def get_hansen_uv_style(style_code):
    return HANSEN_UV_STYLES.get(str(style_code or "").casefold())


def find_hansen_uv_style(text):
    lowered = str(text or "").casefold()
    for code, style in HANSEN_UV_STYLES.items():
        if re.search(rf"(?<![a-z]){re.escape(code)}(?![a-z])", lowered):
            return style
    return None
