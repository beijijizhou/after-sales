import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

import pandas as pd

from automation.logistics.s2b import (
    PENDING_STATUS,
    _normalize_order,
    _order_payload,
)
from automation.logistics.carriers import (
    classify_carrier,
    classify_usps_subtype,
    extract_service_provider,
    is_usps_shipment,
    usps_pickup_name,
)
from automation.logistics.s2b_workbook import parse_s2b_logistics_frame
from automation.logistics.usps import USPSClient, classify_usps_response
from automation.logistics.label_ocr import parse_usps_label_lines
from automation.logistics.sds import _qa_token
from db.logistics.repository import _merge_shipment_rows
from ui.logistics.page import (
    _classify_carrier_rows,
    _cache_status,
    _is_target_usps_review,
    _shipment_cache_signature,
    _tracking_lookup_import_rows,
    _split_cache,
)
from ui.logistics.tracking_lookup import (
    _merge_order_context,
    _merge_label_details,
    _missing_label_row,
    _apply_usps_origin_fallback,
    _extract_usps_origin,
    _raw_response_rows,
    _tracking_event_rows,
    normalize_order_tracking_rows,
    parse_tracking_numbers,
    split_tracking_cache,
)
from utils.auth.constants import ROLE_PERMISSIONS


class LogisticsTrackingTests(unittest.TestCase):
    def test_logistics_page_is_limited_to_after_sales_and_admin(self):
        allowed = {"after_sales", "admin"}
        for role, permissions in ROLE_PERMISSIONS.items():
            with self.subTest(role=role):
                self.assertEqual(
                    "can_view_logistics" in permissions,
                    role in allowed,
                )
                self.assertEqual(
                    "can_manage_logistics" in permissions,
                    role in allowed,
                )

    def test_usps_oauth_token_is_reused_within_expiry_window(self):
        USPSClient._TOKEN_CACHE.clear()
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "access_token": "cached-token", "expires_in": 28800,
        }
        client = USPSClient("client-for-cache-test", "secret")

        with patch("automation.logistics.usps.requests.post", return_value=response) as post:
            first = client._token()
            second = client._token()

        self.assertEqual(first, "cached-token")
        self.assertEqual(second, "cached-token")
        self.assertEqual(post.call_count, 1)

    def test_empty_order_tracking_editor_keeps_expected_columns(self):
        normalized = normalize_order_tracking_rows(pd.DataFrame([{
            "订单号": "", "物流单号": "",
        }]))

        self.assertEqual(
            normalized.columns.tolist(),
            [
                "ERP", "账号", "部门", "订单号", "ERP状态", "订单阶段",
                "tracking_number",
            ],
        )
        self.assertTrue(normalized.empty)

    def test_order_tracking_import_preserves_multiple_orders_for_one_label(self):
        imported = normalize_order_tracking_rows(pd.DataFrame([
            {"订单号": "ORDER-A", "物流单号": "9400", "ERP状态": "生产中"},
            {"订单号": "ORDER-B", "物流单号": "9400", "ERP状态": "已发货"},
        ]))
        result = _merge_order_context(pd.DataFrame([{
            "tracking_number": "9400", "provider_status": "In Transit",
        }]), imported)

        self.assertEqual(result["订单号"].tolist(), ["ORDER-A", "ORDER-B"])
        self.assertEqual(result["provider_status"].tolist(), [
            "In Transit", "In Transit",
        ])
        self.assertEqual(result["ERP状态"].tolist(), ["生产中", "已发货"])

    def test_platform_without_label_reports_address_unavailable(self):
        row = _missing_label_row("9400", "平台未提供面单下载")

        self.assertEqual(row["发货地址"], "无法获取")
        self.assertEqual(row["地址来源"], "无可用面单")

    def test_tracking_result_merges_shipping_address(self):
        tracking = pd.DataFrame([{
            "tracking_number": "9400", "provider_status": "In Transit",
        }])
        labels = pd.DataFrame([{
            "tracking_number": "9400", "发货地址": "25 RYANIC RD NY",
        }])

        result = _merge_label_details(tracking, labels)

        self.assertEqual(result.iloc[0]["发货地址"], "25 RYANIC RD NY")

    def test_raw_usps_response_is_available_for_page_display(self):
        payload = {
            "trackingNumber": "9200190417705008519077",
            "status": "Shipping Label Created",
        }
        frame = pd.DataFrame([{
            "tracking_number": "9200190417705008519077",
            "response_payload": payload,
        }])

        self.assertEqual(
            _raw_response_rows(frame),
            [("9200190417705008519077", payload)],
        )

    def test_usps_origin_location_fills_missing_label_address(self):
        payload = {
            "trackingNumber": "9200190417705008519077",
            "originCity": "HAUPPAUGE",
            "originState": "NY",
            "originZIPCode": "11788",
        }
        frame = pd.DataFrame([{
            "tracking_number": "9200190417705008519077",
            "response_payload": payload,
            "发货地址": "无法获取",
            "地址来源": "无可用面单",
            "地址获取状态": "ERP未找到面单记录",
            "无法获取原因": "ERP未找到面单记录",
        }])

        result = _apply_usps_origin_fallback(frame)

        self.assertEqual(result.iloc[0]["发货地址"], "HAUPPAUGE, NY 11788")
        self.assertIn("USPS Tracking API", result.iloc[0]["地址来源"])

    def test_usps_origin_location_supports_nested_response(self):
        payload = {"package": {"originLocation": {
            "city": "HAUPPAUGE", "state": "NY", "ZIPCode": "11788",
        }}}

        self.assertEqual(
            _extract_usps_origin(payload), "HAUPPAUGE, NY 11788"
        )

    def test_shipping_label_created_event_is_used_as_origin_location(self):
        payload = {"trackingEvents": [{
            "eventCity": "BUFORD", "eventCode": "GX",
            "eventState": "GA", "eventType": "Shipping Label Created",
            "eventZIPCode": "30518",
        }]}
        frame = pd.DataFrame([{
            "tracking_number": "9200190417705008519077",
            "response_payload": payload,
            "发货地址": "无法获取",
        }])

        result = _apply_usps_origin_fallback(frame)

        self.assertEqual(result.iloc[0]["发货地址"], "BUFORD, GA 30518")
        self.assertEqual(
            result.iloc[0]["USPS面单创建地点"], "BUFORD, GA 30518"
        )
        self.assertEqual(
            result.iloc[0]["始发地点判断"], "异常：不是纽约工厂地址"
        )

    def test_usps_origin_takes_priority_and_keeps_ocr_as_supplement(self):
        frame = pd.DataFrame([{
            "tracking_number": "9200",
            "response_payload": {"trackingEvents": [{
                "eventCode": "GX", "eventType": "Shipping Label Created",
                "eventCity": "BUFORD", "eventState": "GA",
                "eventZIPCode": "30518",
            }]},
            "发货地址": "25 RYANIC RD HAUPPAUGE NY 11788",
        }])

        result = _apply_usps_origin_fallback(frame)

        self.assertEqual(result.iloc[0]["发货地址"], "BUFORD, GA 30518")
        self.assertEqual(
            result.iloc[0]["面单OCR地址"],
            "25 RYANIC RD HAUPPAUGE NY 11788",
        )

    def test_all_usps_tracking_events_are_kept_for_display(self):
        frame = pd.DataFrame([{
            "tracking_number": "9200",
            "response_payload": {"trackingEvents": [
                {"eventCode": "GX", "eventType": "Shipping Label Created",
                 "eventCity": "BUFORD", "eventState": "GA",
                 "eventZIPCode": "30518", "eventTimestamp": "2026-08-01"},
                {"eventCode": "01", "eventType": "Accepted",
                 "eventCity": "BUFORD", "eventState": "GA",
                 "eventZIPCode": "30518", "eventTimestamp": "2026-08-02"},
            ]},
        }])

        events = _tracking_event_rows(frame)

        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["事件地点"], "BUFORD, GA 30518")
        self.assertEqual(events[1]["事件类型"], "Accepted")

    def test_label_ocr_extracts_sender_address_and_weight(self):
        lines = [
            {"text": "0 lb 5 oz", "score": 0.94, "x": 200, "y": 250},
            {"text": "TIKTOK INC", "score": 0.99, "x": 40, "y": 360},
            {"text": "Created 08/01/2026", "score": 0.99, "x": 600, "y": 360},
            {"text": "55 KENNEDY DR", "score": 0.98, "x": 40, "y": 390},
            {"text": "RDC 01", "score": 0.99, "x": 650, "y": 390},
            {"text": "HAUPPAUGE NY 11788", "score": 0.97, "x": 40, "y": 420},
            {"text": "AIMEE LONG", "score": 0.99, "x": 140, "y": 600},
            {"text": "GLENWOOD WV 25520", "score": 0.99, "x": 140, "y": 660},
        ]

        parsed = parse_usps_label_lines(lines)

        self.assertEqual(parsed["extracted_street"], "55 KENNEDY DR")
        self.assertEqual(parsed["extracted_city"], "HAUPPAUGE")
        self.assertEqual(parsed["extracted_state"], "NY")
        self.assertEqual(parsed["extracted_postal_code"], "11788")
        self.assertEqual(parsed["extracted_weight_oz"], 5)

    def test_tracking_lookup_parses_common_separators_and_removes_duplicates(self):
        numbers = parse_tracking_numbers("9400, 9500\n9400；9600")

        self.assertEqual(numbers, ["9400", "9500", "9600"])

    def test_tracking_lookup_uses_cache_then_requests_missing_numbers(self):
        future = datetime.now(timezone.utc) + timedelta(minutes=30)
        latest = pd.DataFrame([{
            "tracking_number": "9500",
            "cache_expires_at": future.isoformat(),
        }])

        cached, pending = split_tracking_cache(
            ["9500", "9700", "9800"], latest
        )

        self.assertEqual(cached["tracking_number"].tolist(), ["9500"])
        self.assertEqual(pending, ["9700", "9800"])

    def test_tracking_lookup_force_mode_bypasses_database_cache(self):
        future = datetime.now(timezone.utc) + timedelta(minutes=30)
        latest = pd.DataFrame([{
            "tracking_number": "9500",
            "cache_expires_at": future.isoformat(),
        }])

        cached, pending = split_tracking_cache(["9500"], latest, True)

        self.assertTrue(cached.empty)
        self.assertEqual(pending, ["9500"])

    def test_sds_qa_accepts_current_access_token_field(self):
        self.assertEqual(
            _qa_token({"ret": 0, "data": {"accessToken": "qa-token"}}),
            "qa-token",
        )

    def test_s2b_export_contains_and_normalizes_tracking_numbers(self):
        source = pd.DataFrame([{
            "订单编码": "FDKLYT",
            "商户订单号": "PO-211",
            "物流方式": "Temu在线下单_USPS",
            "物流单号": "9200190419690850384769",
            "订单状态": "已发货",
        }])

        rows = parse_s2b_logistics_frame(source, "DTF")

        self.assertEqual(rows[0]["external_order_id"], "FDKLYT")
        self.assertEqual(
            rows[0]["tracking_number"], "9200190419690850384769"
        )
        self.assertEqual(rows[0]["department"], "DTF")

    def test_s2b_workbook_excludes_non_usps_tracking(self):
        source = pd.DataFrame([
            {
                "订单编码": "USPS-1", "商户订单号": "A",
                "物流方式": "USPS Ground Advantage",
                "物流单号": "9400111122223333444455",
                "订单状态": "排单中",
            },
            {
                "订单编码": "UPS-1", "商户订单号": "B",
                "物流方式": "UPS", "物流单号": "1Z999AA10123456784",
                "订单状态": "排单中",
            },
        ])

        rows = parse_s2b_logistics_frame(source, "DTF")

        self.assertEqual([row["external_order_id"] for row in rows], ["USPS-1"])

    def test_usps_tracking_pattern_is_used_when_carrier_is_blank(self):
        self.assertTrue(is_usps_shipment("", "9400111122223333444455"))
        self.assertFalse(is_usps_shipment("", "1Z999AA10123456784"))

    def test_gofo_gfus_is_not_usps_even_when_channel_name_says_usps(self):
        self.assertFalse(is_usps_shipment(
            "美国tiktok在线下单USPS（自动自动同步面单，需绑定店铺）",
            "GFUS01065019925830",
        ))

    def test_cbs_channel_remains_in_usps_family(self):
        self.assertEqual(
            classify_carrier(
                "CBS物流商", "9400111122223333444455"
            ),
            "USPS",
        )

    def test_usps_subtype_uses_tiktok_service_provider_for_cbt(self):
        payload = {"items": [{"parcel": {
            "serviceProviderName": "TIKTOK线上物流",
        }}]}

        subtype = classify_usps_subtype(
            "USPS Ground Advantage™.", "9200190390471825712253", payload,
        )

        self.assertEqual(subtype, "CBT")
        self.assertEqual(usps_pickup_name(subtype), "TikTok指定物流商")

    def test_usps_subtype_uses_gofo_service_provider_for_cbs(self):
        payload = {"record": {"parcel": {
            "serviceProviderName": "GOFO",
        }}}

        self.assertEqual(
            classify_usps_subtype(
                "USPS Ground Advantage", "9400111122223333444455", payload,
            ),
            "CBS",
        )

    def test_service_provider_is_read_from_merged_source_payload(self):
        payload = {"items": [
            {"parcel": {"serviceProviderName": "TIKTOK线上物流"}},
        ]}

        self.assertEqual(
            extract_service_provider(payload), "TIKTOK线上物流"
        )

    def test_only_ordinary_usps_is_selected_for_database_import(self):
        ordinary = {"系统判断": "USPS", "USPS子类型": "普通USPS"}
        cbt = {"系统判断": "USPS", "USPS子类型": "CBT"}
        cbs = {"系统判断": "USPS", "USPS子类型": "CBS"}

        self.assertTrue(_is_target_usps_review(ordinary))
        self.assertFalse(_is_target_usps_review(cbt))
        self.assertFalse(_is_target_usps_review(cbs))

    def test_cbs_and_cbt_are_excluded_from_default_usps_review(self):
        rows = _classify_carrier_rows([
            {
                "carrier": "USPS Ground Advantage",
                "tracking_number": "9200190390471825712253",
                "source_payload": {"parcel": {
                    "serviceProviderName": "TIKTOK线上物流",
                }},
            },
            {
                "carrier": "USPS Ground Advantage",
                "tracking_number": "9400111122223333444455",
                "source_payload": {},
            },
        ])

        self.assertFalse(_is_target_usps_review(rows[0]))
        self.assertTrue(_is_target_usps_review(rows[1]))

    def test_synced_usps_rows_are_queued_for_order_tracking_review(self):
        imported = _tracking_lookup_import_rows([
            {
                "external_order_id": "ORDER-1", "tracking_number": "9400",
                "erp_status": "排单中", "local_acceptance_status": "待排产/未接单",
                "erp_platform": "SDS", "erp_account": "2号线", "department": "DTF",
            },
            {
                "external_order_id": "ORDER-1", "tracking_number": "9400",
                "erp_status": "排单中", "local_acceptance_status": "待排产/未接单",
                "erp_platform": "SDS", "erp_account": "2号线", "department": "DTF",
            },
        ])

        self.assertEqual(
            imported, [{
                "ERP": "SDS", "账号": "2号线", "部门": "DTF",
                "订单号": "ORDER-1", "物流单号": "9400",
                "ERP状态": "排单中", "订单阶段": "待排产/未接单",
            }]
        )

    def test_cache_status_uses_latest_database_storage_time(self):
        frame = pd.DataFrame([
            {"last_seen_at": "2026-08-01T15:00:00+00:00"},
            {"last_seen_at": "2026-08-01T17:30:00+00:00"},
        ])

        status = _cache_status(frame)

        self.assertEqual(status["count"], 2)
        self.assertEqual(status["stored_at"], "2026-08-01 13:30:00")

    def test_cache_signature_changes_when_erp_cache_updates(self):
        before = pd.DataFrame([{
            "last_seen_at": "2026-08-01T17:30:00+00:00",
        }])
        after = pd.DataFrame([{
            "last_seen_at": "2026-08-01T18:00:00+00:00",
        }])

        self.assertNotEqual(
            _shipment_cache_signature(before),
            _shipment_cache_signature(after),
        )

    def test_known_non_usps_carriers_are_classified_separately(self):
        cases = [
            ("FedEx Ground", "123456789012", "FedEx"),
            ("SwiftX美国专线", "SW123", "SwiftX"),
            ("UniUni", "UUS123", "UniUni"),
            ("", "1Z999AA10123456784", "UPS"),
        ]

        for carrier, tracking, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(
                    classify_carrier(carrier, tracking), expected
                )

    def test_s2b_accounts_keep_separate_department_identity(self):
        order = {
            "code": "ORDER-1",
            "status": 4,
            "order_logistics": {
                "logisticss_track_number": "9400000000000000000000"
            },
        }

        uv = _normalize_order(order, "UV")
        dtf = _normalize_order(order, "DTF")

        self.assertEqual(uv["department"], "UV")
        self.assertEqual(dtf["department"], "DTF")
        self.assertEqual(uv["tracking_number"], "9400000000000000000000")

    def test_s2b_new_order_api_normalizes_pending_order(self):
        order = {
            "id": 9,
            "order_data": {
                "order_code": "S2B-9",
                "third_order_id": "SHOP-9",
                "logisticss_track_number": "94001111",
                "logistics_platform_name": "USPS",
                "status": 1,
                "status_text": "排单中",
            },
        }

        row = _normalize_order(order, "DTF")

        self.assertEqual(row["external_order_id"], "S2B-9")
        self.assertEqual(row["merchant_order_id"], "SHOP-9")
        self.assertEqual(row["tracking_number"], "94001111")
        self.assertEqual(row["erp_status"], "排单中")

    def test_s2b_pending_payload_uses_current_status(self):
        payload = _order_payload(3)

        self.assertEqual(payload["status"], PENDING_STATUS)
        self.assertEqual(payload["page"], 3)
        self.assertEqual(payload["per_page"], 100)

    def test_s2b_payload_accepts_production_and_shipped_stages(self):
        self.assertEqual(_order_payload(1, 2)["status"], 2)
        self.assertEqual(_order_payload(1, 6)["status"], 6)

    def test_multi_item_order_merges_into_one_shipment(self):
        common = {
            "tenant_code": "default",
            "erp_platform": "S2B",
            "erp_account": "DTF",
            "external_order_id": "ORDER-1",
            "tracking_number": "9400",
            "department": "DTF",
            "merchant_order_id": "SHOP-1",
            "carrier": "USPS",
            "erp_status": "排单中",
            "label_url": None,
            "backup_label_url": None,
            "local_acceptance_status": "未接单",
        }
        rows = [
            {**common, "source_payload": {"item": "shirt-S"}},
            {**common, "source_payload": {"item": "shirt-L"}},
        ]

        merged = _merge_shipment_rows(rows)

        self.assertEqual(len(merged), 1)
        self.assertEqual(
            [item["item"] for item in merged[0]["source_payload"]["items"]],
            ["shirt-S", "shirt-L"],
        )

    def test_different_tracking_numbers_remain_separate_shipments(self):
        base = {
            "tenant_code": "default", "erp_platform": "S2B",
            "erp_account": "DTF", "external_order_id": "ORDER-1",
            "source_payload": {},
        }

        merged = _merge_shipment_rows([
            {**base, "tracking_number": "9400"},
            {**base, "tracking_number": "9500"},
        ])

        self.assertEqual(len(merged), 2)

    def test_usps_record_marks_order_for_compliance_review(self):
        result = classify_usps_response({
            "trackingNumber": "9400",
            "status": "Pre-Shipment",
            "trackingEvents": [],
        })

        self.assertTrue(result["has_postal_record"])
        self.assertTrue(result["has_pre_scan"])

    def test_fresh_database_check_avoids_paid_provider_request(self):
        future = datetime.now(timezone.utc) + timedelta(minutes=30)
        latest = pd.DataFrame([{
            "tracking_number": "9400",
            "cache_expires_at": future.isoformat(),
        }])

        cached, pending = _split_cache(["9400", "9500"], latest, False)

        self.assertEqual(cached["tracking_number"].tolist(), ["9400"])
        self.assertEqual(pending, ["9500"])


if __name__ == "__main__":
    unittest.main()
