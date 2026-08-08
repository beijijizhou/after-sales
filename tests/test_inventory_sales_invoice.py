from datetime import date, datetime
import re
import unittest

import pandas as pd

from db.inventory.sales import (
    allocate_brand_merged_sales,
    build_invoice_number,
    build_sales_adjustments,
    build_sales_draft_signature,
    build_sales_invoice_pdf,
    normalize_sales_lines,
)
from ui.inventory.sales.pdf_preview import render_pdf_pages


class InventorySalesInvoiceTests(unittest.TestCase):
    def test_colored_sale_combines_brands_and_keeps_real_movement_skus(self):
        lines = pd.DataFrame([{
            "品牌": "", "材质": "180g", "颜色": "粉色",
            "尺码": "L", "数量": 10, "单价": 1.6,
        }])
        inventory = pd.DataFrame([
            {"brand": "Haloo", "material": "180g", "color": "粉色",
             "size": "L", "quantity": 8},
            {"brand": "临时进货", "material": "180g", "color": "粉色",
             "size": "L", "quantity": 4},
        ])

        adjustments, issues = allocate_brand_merged_sales(
            lines, inventory, date(2026, 8, 8), "INV-TEST"
        )

        self.assertTrue(issues.empty)
        self.assertEqual(int(adjustments["数量"].sum()), 10)
        self.assertEqual(adjustments.iloc[0]["品牌"], "临时进货")
        self.assertEqual(set(adjustments["品牌"]), {"临时进货", "Haloo"})

    def test_colored_sale_shortage_uses_all_brand_inventory(self):
        lines = pd.DataFrame([{
            "品牌": "", "材质": "180g", "颜色": "绿色",
            "尺码": "M", "数量": 20, "单价": 1.6,
        }])
        inventory = pd.DataFrame([
            {"brand": "A", "material": "180g", "color": "绿色",
             "size": "M", "quantity": 7},
            {"brand": "B", "material": "180g", "color": "绿色",
             "size": "M", "quantity": 5},
        ])

        adjustments, issues = allocate_brand_merged_sales(
            lines, inventory, date(2026, 8, 8), "INV-TEST"
        )

        self.assertTrue(adjustments.empty)
        self.assertEqual(issues.iloc[0]["品牌"], "全部品牌")
        self.assertEqual(issues.iloc[0]["当前库存"], 12)
        self.assertEqual(issues.iloc[0]["缺口"], 8)

    def test_sales_lines_keep_manual_price_and_calculate_amount(self):
        result = normalize_sales_lines(pd.DataFrame([{
            "品牌": "Cotton", "材质": "CVC", "颜色": "白",
            "尺码": "L", "数量": 12, "单价": 2.35,
        }]))

        self.assertEqual(result.loc[0, "数量"], 12)
        self.assertEqual(result.loc[0, "单价"], 2.35)
        self.assertEqual(result.loc[0, "金额"], 28.20)

    def test_sales_adjustment_links_inventory_batch_to_invoice(self):
        lines = pd.DataFrame([{
            "品牌": "Cotton", "材质": "CVC", "颜色": "黑",
            "尺码": "S", "数量": 10, "单价": 2.0,
        }])

        result = build_sales_adjustments(
            lines, date(2026, 8, 8), "INV-20260808-ABC123"
        )

        self.assertEqual(result.loc[0, "操作"], "扣减")
        self.assertEqual(result.loc[0, "数量"], 10)
        self.assertEqual(
            result.loc[0, "备注"],
            "客户销售出库｜INV-20260808-ABC123",
        )

    def test_invoice_number_uses_business_date_and_unique_suffix(self):
        result = build_invoice_number(datetime(2026, 8, 8, 9, 30))

        self.assertRegex(result, r"^INV-20260808-[A-F0-9]{6}$")

    def test_invoice_preview_is_invalidated_when_price_changes(self):
        base = pd.DataFrame([{
            "品牌": "Cotton", "材质": "CVC", "颜色": "白",
            "尺码": "L", "数量": 12, "单价": 2.35,
        }])
        changed = base.copy()
        changed.loc[0, "单价"] = 2.50
        company = {"company_name": "Haloo"}
        customer = {"display_name": "Customer A"}
        invoice = {
            "invoice_number": "INV-20260808-ABC123",
            "invoice_date": date(2026, 8, 8),
        }

        self.assertNotEqual(
            build_sales_draft_signature(
                company, customer, invoice, base
            ),
            build_sales_draft_signature(
                company, customer, invoice, changed
            ),
        )

    def test_invoice_pdf_contains_a_valid_pdf_document(self):
        lines = normalize_sales_lines(pd.DataFrame([{
            "品牌": "Cotton", "材质": "CVC", "颜色": "白",
            "尺码": "L", "数量": 12, "单价": 2.35,
        }]))
        pdf = build_sales_invoice_pdf(
            {
                "invoice_number": "INV-20260808-ABC123",
                "invoice_date": date(2026, 8, 8), "note": "Thank you",
            },
            {
                "company_name": "Haloo", "email": "admin@haloousa.com",
                "address_line1": "25 ranick road", "city": "Happuage",
                "state": "NY", "postal_code": "11788",
            },
            {"display_name": "Customer A", "contact_name": "John"},
            lines,
        )

        self.assertTrue(pdf.startswith(b"%PDF-"))
        self.assertGreater(len(pdf), 1000)

        pages = render_pdf_pages(pdf)
        self.assertEqual(len(pages), 1)
        self.assertGreater(pages[0].width, 500)
        self.assertGreater(pages[0].height, 700)

    def test_invoice_schema_uses_atomic_inventory_rpc(self):
        with open(
            "sql/inventory/sales/01_customer_sales_invoices.sql",
            encoding="utf-8",
        ) as source:
            sql = source.read()

        self.assertIn("create_inventory_sales_invoice", sql)
        self.assertIn("apply_inventory_adjustment_batch", sql)
        self.assertIn("company_snapshot", sql)
        self.assertIn("customer_snapshot", sql)
        self.assertIn("void_inventory_sales_invoice", sql)
        self.assertIn("reverse_inventory_movement_batch", sql)
        self.assertTrue(re.search(r"begin;.*commit;", sql, re.S))


if __name__ == "__main__":
    unittest.main()
