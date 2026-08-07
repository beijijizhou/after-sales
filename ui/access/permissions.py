import pandas as pd

from utils.auth.constants import (
    ALL_PERMISSIONS,
    ROLE_LABELS,
    ROLE_PERMISSIONS,
)


PERMISSION_LABELS = {
    "can_view_logistics": "查看物流查询",
    "can_manage_logistics": "同步ERP、OCR与物流管理",
    "can_manage_access": "管理用户角色",
    "can_view_app": "查看售后查询",
    "can_register": "使用注册页面",
    "can_view_qa": "查看质检",
    "can_view_hotstamp": "查看烫印",
    "can_view_platform": "查看平台",
    "can_view_operation_tracking": "查看问题件追踪",
    "can_mark_barcode_operations": "处理问题件",
    "can_view_production_data": "查看生产数据",
    "can_view_inventory": "查看库存",
    "can_edit_inventory": "修改库存",
    "can_manage_sku": "管理SKU",
    "can_view_container": "查看货柜",
    "can_edit_container": "修改货柜",
    "can_view_consumables": "查看耗材",
    "can_edit_consumables": "修改耗材",
    "can_manage_consumable_sku": "管理耗材SKU",
    "can_report_consumables": "登记耗材",
    "can_input_after_sales": "录入售后",
    "can_view_cost": "查看成本",
    "can_manage_cost": "管理成本",
    "can_view_finance_reports": "查看财务报表",
    "can_view_finance_dashboard": "查看财务页面",
    "can_use_image_stretch": "使用图片处理",
}


def permission_matrix():
    rows = []
    for role, label in ROLE_LABELS.items():
        permissions = ROLE_PERMISSIONS.get(role, set())
        rows.append({
            "角色": label,
            **{
                PERMISSION_LABELS.get(permission, permission): (
                    "✓" if permission in permissions else ""
                )
                for permission in sorted(ALL_PERMISSIONS)
            },
        })
    return pd.DataFrame(rows)


def permission_names(permissions):
    return "、".join(PERMISSION_LABELS.get(item, item) for item in permissions)
