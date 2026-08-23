ROLE_VISITOR = "visitor"
ROLE_SUPERVISOR = "supervisor"
ROLE_PRODUCER = "producer"
ROLE_WAREHOUSE = "warehouse"
ROLE_AFTER_SALES = "after_sales"
ROLE_FINANCE = "finance"
ROLE_ADMIN = "admin"

ROLE_LABELS = {
    ROLE_VISITOR: "游客",
    ROLE_SUPERVISOR: "主管",
    ROLE_PRODUCER: "生产人员",
    ROLE_WAREHOUSE: "仓库",
    ROLE_AFTER_SALES: "售后",
    ROLE_FINANCE: "财务",
    ROLE_ADMIN: "管理员",
}

PUBLIC_ACCESS = {
    "can_view_app",
    "can_register",
    "can_view_qa",
    "can_view_hotstamp",
    "can_view_platform",
    "can_view_operation_tracking",
    "can_use_image_stretch",
}
PRODUCTION_ACCESS = {
    "can_view_production_data",
}
LOGISTICS_ACCESS = {"can_view_logistics"}
LOGISTICS_MANAGE = {"can_manage_logistics"}
ACCESS_MANAGE = {"can_manage_access"}
PEOPLE_MANAGE = {"can_manage_people"}
DAILY_WORK_ACCESS = {"can_view_daily_work"}
INVENTORY_VIEW = {
    "can_view_inventory",
    "can_view_container",
}
INVENTORY_MANAGE = {
    "can_edit_inventory",
    "can_edit_container",
    "can_manage_sku",
}
CONSUMABLE_VIEW = {
    "can_view_consumables",
}
CONSUMABLE_MANAGE = {
    "can_edit_consumables",
    "can_manage_consumable_sku",
}
CONSUMABLE_REPORT = {
    "can_report_consumables",
}
AFTER_SALES_MANAGE = {
    "can_input_after_sales",
    "can_mark_barcode_operations",
}
COST_VIEW = {
    "can_view_cost",
}
COST_MANAGE = {
    "can_manage_cost",
}
FINANCE_REPORTS = {
    "can_view_finance_reports",
}
FINANCE_DASHBOARD = {
    "can_view_finance_dashboard",
}

ALL_PERMISSIONS = set().union(
    PUBLIC_ACCESS,
    PRODUCTION_ACCESS,
    INVENTORY_VIEW,
    INVENTORY_MANAGE,
    CONSUMABLE_VIEW,
    CONSUMABLE_MANAGE,
    CONSUMABLE_REPORT,
    AFTER_SALES_MANAGE,
    COST_VIEW,
    COST_MANAGE,
    FINANCE_REPORTS,
    FINANCE_DASHBOARD,
    LOGISTICS_ACCESS,
    LOGISTICS_MANAGE,
    ACCESS_MANAGE,
    PEOPLE_MANAGE,
    DAILY_WORK_ACCESS,
)

ROLE_PERMISSIONS = {
    ROLE_VISITOR: PUBLIC_ACCESS,
    ROLE_SUPERVISOR: (
        PUBLIC_ACCESS | PRODUCTION_ACCESS | INVENTORY_VIEW | CONSUMABLE_VIEW
        | PEOPLE_MANAGE | {"can_mark_barcode_operations"}
    ),
    ROLE_PRODUCER: (
        PUBLIC_ACCESS | PRODUCTION_ACCESS | INVENTORY_VIEW
        | CONSUMABLE_VIEW | CONSUMABLE_REPORT
        | LOGISTICS_MANAGE
    ),
    ROLE_WAREHOUSE: (
        INVENTORY_VIEW | (INVENTORY_MANAGE - {"can_edit_inventory"})
        | CONSUMABLE_VIEW
        | CONSUMABLE_MANAGE | {"can_use_image_stretch"}
    ),
    ROLE_AFTER_SALES: (
        ALL_PERMISSIONS
        - COST_VIEW - COST_MANAGE
        - FINANCE_REPORTS - FINANCE_DASHBOARD
        - ACCESS_MANAGE - PEOPLE_MANAGE
    ),
    ROLE_FINANCE: (
        INVENTORY_VIEW | CONSUMABLE_VIEW | COST_VIEW | FINANCE_REPORTS
    ),
    ROLE_ADMIN: ALL_PERMISSIONS,
}

PAGE_ACCESS = {
    "app": "can_view_app",
    "after_sales_manual_analysis": "can_input_after_sales",
    "register": ("can_register", "can_manage_people"),
    "qa": "can_view_qa",
    "hotstamp": "can_view_hotstamp",
    "platform": "can_view_platform",
    "production_data": "can_view_production_data",
    "logistics": ("can_view_logistics", "can_manage_logistics"),
    "logistics_summary": "can_manage_logistics",
    "logistics_rules": "can_manage_logistics",
    "inventory": "can_view_inventory",
    "customer_sales": "can_view_inventory",
    "inventory_transfer": "can_view_inventory",
    "sku_management": "can_view_inventory",
    "inventory_dashboard": "can_view_inventory",
    "consumables": "can_view_consumables",
    "container": "can_view_container",
    "finance": "can_view_finance_dashboard",
    "operation_tracking": "can_view_operation_tracking",
    "image_stretch": "can_use_image_stretch",
    "access_management": "can_manage_access",
    "daily_work": "can_view_daily_work",
}

PUBLIC_PERMISSIONS = PUBLIC_ACCESS

NAV_SECTIONS = [
    ("日常管理", [
        ("daily_work", "每日工作", "pages/17_每日工作.py"),
    ]),
    (None, [
        ("register", "人员管理", "pages/0_注册.py"),
    ]),
    ("生产管理", [
        ("qa", "质检", "pages/1_质检.py"),
        ("hotstamp", "烫印", "pages/2_烫印.py"),
        ("platform", "平台", "pages/3_平台.py"),
        ("production_data", "生产数据", "pages/7_生产数据.py"),
        ("operation_tracking", "问题件追踪", "app.py"),
    ]),
    ("售后查询", [
        ("app", "订单与条码查询", "pages/6_售后查询.py"),
        (
            "after_sales_manual_analysis", "人工登记分析",
            "pages/6_人工登记分析.py",
        ),
    ]),
    ("物流单号追踪", [
        (
            "logistics", "物流单号获取与USPS核查",
            "pages/11_物流追踪.py",
        ),
        (
            "logistics_summary", "物流数据总结",
            "pages/15_物流数据总结.py",
        ),
        (
            "logistics_rules", "审核规则",
            "pages/16_物流审核规则.py",
        ),
    ]),
    ("库存", [
        ("inventory_dashboard", "库存总结", "pages/4_库存总结.py"),
        ("inventory", "生产库存", "pages/4_库存.py"),
        ("consumables", "耗材库存", "pages/9_耗材库存.py"),
        ("container", "货柜安排", "pages/5_货柜安排.py"),
        ("inventory_transfer", "仓库调拨", "pages/14_仓库调拨.py"),
        ("customer_sales", "客户销售出库", "pages/13_客户销售出库.py"),
        ("sku_management", "SKU 管理", "pages/4_SKU管理.py"),
    ]),
    (None, [
        ("finance", "财务", "pages/10_财务.py"),
        ("image_stretch", "手机壳图片处理", "pages/8_图片拉伸.py"),
    ]),
    ("系统管理", [
        ("access_management", "权限管理", "pages/12_权限管理.py"),
    ]),
]

NAV_ITEMS = [
    item for _, section_items in NAV_SECTIONS for item in section_items
]

AUTH_QUERY_KEY = "auth"
