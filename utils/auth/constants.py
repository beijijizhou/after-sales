ROLE_VISITOR = "visitor"
ROLE_SUPERVISOR = "supervisor"
ROLE_WAREHOUSE = "warehouse"
ROLE_AFTER_SALES = "after_sales"
ROLE_ADMIN = "admin"

ROLE_LABELS = {
    ROLE_VISITOR: "游客",
    ROLE_SUPERVISOR: "主管",
    ROLE_WAREHOUSE: "仓库",
    ROLE_AFTER_SALES: "售后",
    ROLE_ADMIN: "管理员",
}

PAGE_ACCESS = {
    "app": "can_view_app",
    "register": "can_register",
    "qa": "can_view_qa",
    "hotstamp": "can_view_hotstamp",
    "platform": "can_view_platform",
    "inventory": "can_view_inventory",
    "container": "can_view_container",
}

PUBLIC_PERMISSIONS = {
    "can_register",
    "can_view_qa",
    "can_view_hotstamp",
    "can_view_platform",
}

NAV_ITEMS = [
    ("app", "售后查询", "app.py"),
    ("register", "注册", "pages/0_注册.py"),
    ("qa", "质检", "pages/1_质检.py"),
    ("hotstamp", "烫印", "pages/2_烫印.py"),
    ("platform", "平台", "pages/3_平台.py"),
    ("inventory", "库存", "pages/4_库存.py"),
    ("container", "货柜安排", "pages/5_货柜安排.py"),
]

AUTH_QUERY_KEY = "auth"
