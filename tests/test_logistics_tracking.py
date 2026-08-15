import unittest
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier
from zipfile import ZipFile
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from unittest.mock import MagicMock, Mock, patch

import pandas as pd

from automation.api.s2b.shipments import (
    PENDING_STATUS,
    S2BAuthenticationError,
    _normalize_order,
    _order_payload,
    fetch_s2b_pending_shipments,
)
from automation.logistics.config import load_s2b_account
from automation.production import PLATFORMS_BY_DEPARTMENT, production_data_key
from automation.playwright.s2b.account_session import (
    _connection_port,
    normalize_s2b_account,
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
from automation.logistics.label_ocr import parse_usps_label_lines, _weight_ounces
from automation.logistics.label_ocr import extract_label_content_fields
from automation.logistics.label_cache import (
    cached_label_content as _cached_label_content,
    clear_label_cache,
)
from automation.logistics.label_downloads import build_label_archive
from automation.api.sds.shipments import _qa_token
from automation.api.sds.shipments import _parcel_rows as _sds_parcel_rows
from automation.api.humbird.shipments import (
    HumbirdBrowserRefreshRequired,
    _stage_items,
    fetch_humbird_shipments,
    fetch_humbird_shipments_legacy,
    fetch_humbird_shipments_with_fallback,
)
from automation.api.humbird.open_client import HumbirdOpenApiError
from automation.logistics.stages import (
    IN_PRODUCTION,
    SHIPPED,
    STAGE_CODES,
    STAGE_OPTIONS,
    UNACCEPTED,
)
from automation.logistics.imports import (
    parse_logistics_frame,
    parse_logistics_paste,
    parse_logistics_upload,
)
from automation.logistics.diy19 import (
    _list_form as _diy19_list_form,
    _normalize_record as _normalize_diy19_record,
)
from db.logistics.repository import _merge_shipment_rows
from db.logistics.repository import save_label_review
from db.logistics.tracking_sources import save_tracking_check_sources
from db.logistics.usps_usage import record_usps_usage
from ui.logistics.page import render_logistics_page
from ui.logistics.review.model import (
    carrier_filter_name as _carrier_filter_name,
    classify_carrier_rows as _classify_carrier_rows,
    default_logistics_platforms,
    is_target_usps_review as _is_target_usps_review,
    label_documents as _label_documents,
    label_ocr_candidates as _label_ocr_candidates,
    ocr_address as _ocr_address,
    order_tracking_pairs as _order_tracking_pairs,
    review_selection_defaults as _review_selection_defaults,
)
from ui.logistics.review.ocr_format import (
    format_duration as _format_duration,
    ocr_progress_text as _ocr_progress_text,
    ocr_summary_text as _ocr_summary_text,
    resolve_ocr_workers as _resolve_ocr_workers,
)
from ui.logistics.review.state import (
    store_review_ocr_results as _store_review_ocr_results,
)
from ui.logistics.sync_view import (
    CONNECTED_PLATFORMS,
    _fetch_selected_sources,
    _load_selected_sources,
)
from ui.logistics.source_gateway import (
    fetch_humbird_shipments_with_fallback as gateway_humbird,
    fetch_source,
)
from ui.logistics.tracking.input import (
    normalize_suggested_rows,
    parse_order_tracking_table,
    parse_tracking_numbers,
    parse_tracking_table,
)
from ui.logistics.tracking.labels import (
    extract_live_label_details as _extract_live_label_details,
    live_label_row as _live_label_row,
    merge_label_details as _merge_label_details,
    missing_label_row as _missing_label_row,
)
from ui.logistics.tracking.origin_view import (
    apply_usps_origin_fallback as _apply_usps_origin_fallback,
    extract_usps_origin as _extract_usps_origin,
    raw_response_rows as _raw_response_rows,
    tracking_event_rows as _tracking_event_rows,
)
from ui.logistics.tracking.query import (
    query_usps as _query_usps,
    split_tracking_cache,
    tracking_query_plan as _tracking_query_plan,
)
from ui.logistics.usps_usage import summarize_usps_usage
from ui.logistics.summary.detail import build_platform_activity_detail
from ui.logistics.summary.model import build_daily_platform_summary
from utils.auth.constants import NAV_SECTIONS, ROLE_PERMISSIONS


class LogisticsTrackingTests(unittest.TestCase):
    def test_daily_logistics_summary_groups_erp_usps_pdf_and_ocr(self):
        shipments, checks, sources, reviews = _logistics_summary_frames()

        result = build_daily_platform_summary(
            shipments, checks, sources, reviews
        ).iloc[0]

        self.assertEqual(result["日期"].isoformat(), "2026-08-13")
        self.assertEqual(result["部门"], "DTF")
        self.assertEqual(result["平台"], "Haloo")
        self.assertEqual(result["ERP订单数"], 1)
        self.assertEqual(result["物流单号数"], 1)
        self.assertEqual(result["PDF面单数"], 1)
        self.assertEqual(result["OCR记录数"], 1)
        self.assertEqual(result["USPS查询次数"], 1)
        self.assertEqual(result["USPS查询单号"], 1)

    def test_logistics_summary_detail_keeps_order_pdf_and_ocr(self):
        shipments, checks, sources, reviews = _logistics_summary_frames()
        selected = build_daily_platform_summary(
            shipments, checks, sources, reviews
        ).iloc[0].to_dict()

        detail = build_platform_activity_detail(
            selected, shipments, checks, sources, reviews
        )

        self.assertEqual(set(detail["记录类型"]), {"ERP读取", "USPS查询"})
        self.assertEqual(set(detail["ERP订单号"]), {"ORDER-1"})
        self.assertEqual(set(detail["面单PDF"]), {"https://labels.test/1.pdf"})
        self.assertEqual(set(detail["OCR状态"]), {"已识别"})
        self.assertEqual(set(detail["OCR地址"]), {"25 Ranic Rd NY 11788"})

    def test_unassigned_historical_usps_check_remains_visible(self):
        checks = pd.DataFrame([{
            "id": "check-old", "tracking_number": "92000",
            "checked_at": "2026-08-13T15:00:00Z",
            "provider_status": "Shipping Label Created",
            "has_postal_record": True, "error_code": "", "created_by": "Andy",
        }])

        result = build_daily_platform_summary(
            pd.DataFrame(), checks, pd.DataFrame(), pd.DataFrame()
        ).iloc[0]

        self.assertEqual(result["平台"], "未归属")
        self.assertEqual(result["USPS查询单号"], 1)

    def test_label_review_persists_pdf_ocr_status_and_supported_fields(self):
        supabase = Mock()
        supabase.table.return_value.insert.return_value.execute.return_value.data = []

        save_label_review(
            supabase, "shipment-1", {
                "extracted_street": "25 Ranic Rd",
                "extracted_city": "Hauppauge",
                "extracted_state": "NY",
                "extracted_postal_code": "11788",
                "extracted_weight_oz": 4,
                "extracted_weight_lb": 0.25,
                "label_content_hash": "hash",
                "ocr_confidence": 0.98,
            }, "Andy", label_url="https://labels.test/1.pdf",
            ocr_status="已识别", engine_version="rapidocr-v4",
        )

        payload = supabase.table.return_value.insert.call_args.args[0]
        self.assertEqual(payload["label_url"], "https://labels.test/1.pdf")
        self.assertEqual(payload["ocr_status"], "已识别")
        self.assertEqual(payload["extracted_weight_oz"], 4)
        self.assertNotIn("extracted_weight_lb", payload)

    def test_logistics_persistence_migration_is_focused(self):
        script = (
            Path(__file__).resolve().parents[1]
            / "sql" / "logistics" / "03_tracking_sources_and_ocr.sql"
        )
        sql = script.read_text()
        self.assertLess(len(sql.splitlines()), 200)
        self.assertIn("logistics_tracking_check_sources", sql)
        self.assertIn("ocr_engine_version", sql)

    def test_usps_check_source_keeps_order_platform_account_and_pdf(self):
        supabase = Mock()
        execute = (
            supabase.table.return_value.upsert.return_value.execute
        )
        execute.return_value.data = [{"id": "source-1"}]
        shipments = pd.DataFrame([{
            "id": "shipment-1", "tracking_number": "92001",
            "department": "DTF", "erp_platform": "Haloo",
            "erp_account": "Haloo", "external_order_id": "ORDER-1",
            "merchant_order_id": "SHOP-1",
            "label_url": "https://labels.test/1.pdf",
            "backup_label_url": None,
        }])

        saved = save_tracking_check_sources(
            supabase,
            [{"id": "check-1", "tracking_number": "92001"}],
            shipments,
        )

        payload = supabase.table.return_value.upsert.call_args.args[0][0]
        self.assertEqual(saved, [{"id": "source-1"}])
        self.assertEqual(payload["external_order_id"], "ORDER-1")
        self.assertEqual(payload["erp_platform"], "Haloo")
        self.assertEqual(payload["erp_account"], "Haloo")
        self.assertEqual(payload["label_url"], "https://labels.test/1.pdf")

    def test_logistics_gateway_imports_humbird_adapter_directly(self):
        self.assertIs(gateway_humbird, fetch_humbird_shipments_with_fallback)

    @patch("ui.logistics.source_gateway.load_humbird_credentials")
    @patch(
        "ui.logistics.source_gateway.fetch_humbird_shipments_with_fallback"
    )
    def test_longfeng_routes_through_shared_humbird_logistics_adapter(
        self, fetch, credentials
    ):
        credentials.return_value = {"api_key": "longfeng-key"}
        fetch.return_value = [{"tracking_number": "9400"}]
        start = datetime(2026, 8, 13).date()

        rows = fetch_source("隆丰", "DTF", 6, start, start)

        self.assertEqual(rows, [{"tracking_number": "9400"}])
        fetch.assert_called_once_with(
            "隆丰", {"api_key": "longfeng-key"}, start, start,
            status=6, department="DTF",
        )

    def test_usps_lookup_does_not_start_ocr_for_unreviewed_label(self):
        context = pd.DataFrame([{
            "物流单号": "92001",
            "面单PDF": "https://labels.test/92001.pdf",
            "OCR状态": "",
        }])
        self.assertTrue(_extract_live_label_details(context).empty)

    def test_usps_lookup_reuses_existing_ocr_without_reprocessing(self):
        context = pd.DataFrame([{
            "物流单号": "92001",
            "面单PDF": "https://labels.test/92001.pdf",
            "面单OCR地址": "25 Ranic Road, Hauppauge, NY 11788",
            "重量（oz）": 4.0,
            "重量（lb）": 0.25,
            "OCR状态": "已识别",
        }])
        result = _extract_live_label_details(context)
        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]["地址获取状态"], "已识别")

    def test_s2b_account_reads_fresh_local_secrets_before_browser(self):
        with TemporaryDirectory() as directory:
            secrets_path = Path(directory) / "secrets.toml"
            secrets_path.write_text(
                '[logistics_s2b_accounts.DTF]\ntoken = "saved-token"\n'
            )
            with patch(
                "automation.logistics.config.LOCAL_SECRETS", secrets_path
            ), patch(
                "automation.logistics.config.LEGACY_SECRETS",
                Path(directory) / "missing.toml",
            ):
                self.assertEqual(
                    load_s2b_account({}, "DTF")["token"], "saved-token"
                )

    @patch("automation.api.s2b.shipments.requests.Session")
    def test_s2b_http_auth_failure_requests_browser_refresh(self, session):
        response = session.return_value.post.return_value
        response.status_code = 401
        with self.assertRaises(S2BAuthenticationError):
            fetch_s2b_pending_shipments("DTF", {"token": "expired"})
        response.raise_for_status.assert_not_called()

    @patch(
        "automation.playwright.s2b.account_session._chrome_has_s2b_page",
        return_value=True,
    )
    def test_dtf_reuses_existing_shared_s2b_chrome(self, has_s2b_page):
        self.assertEqual(_connection_port("DTF"), 9222)
        has_s2b_page.assert_called_once_with(9222)

    @patch(
        "automation.playwright.s2b.account_session._chrome_has_s2b_page",
        return_value=False,
    )
    def test_dtf_uses_dedicated_chrome_without_shared_page(self, _has_page):
        self.assertEqual(_connection_port("DTF"), 9223)

    def test_uv_and_3d_never_reuse_shared_s2b_chrome(self):
        with patch(
            "automation.playwright.s2b.account_session._chrome_has_s2b_page"
        ) as has_s2b_page:
            self.assertEqual(_connection_port("UV"), 9224)
            self.assertEqual(_connection_port("3D"), 9225)
            has_s2b_page.assert_not_called()

    def test_sds_shared_logistics_interface_preserves_uv_platform_scope(self):
        client = Mock()
        client.get.return_value.json.return_value = {
            "detailList": [{
                "carriageNo": "92001",
                "carriageName": "USPS",
                "pdfUrl": "label.pdf",
            }]
        }
        client.get.return_value.raise_for_status.return_value = None

        rows = _sds_parcel_rows(
            client,
            {"access-token": "token"},
            {"orderId": "1", "no": "ORDER-1"},
            "忆点万象",
            platform_name="忆点万象",
            department="UV",
        )

        self.assertEqual(rows[0]["erp_platform"], "忆点万象")
        self.assertEqual(rows[0]["erp_account"], "忆点万象")
        self.assertEqual(rows[0]["department"], "UV")

    def test_uv_department_exposes_its_s2b_account_platform(self):
        self.assertIn("S2B", PLATFORMS_BY_DEPARTMENT["UV"])
        self.assertEqual(production_data_key("UV", "S2B"), "UV::S2B")
        self.assertEqual(production_data_key("DTF", "S2B"), "S2B")
        self.assertEqual(normalize_s2b_account("uv"), "UV")

    def test_3d_department_exposes_independent_s2b_account(self):
        self.assertEqual(
            PLATFORMS_BY_DEPARTMENT["3D"], ("S2B", "3D热转印")
        )
        self.assertEqual(production_data_key("3D", "S2B"), "3D::S2B")
        self.assertEqual(normalize_s2b_account("3d"), "3D")

    def test_logistics_business_stage_terms_are_shared(self):
        self.assertEqual(
            STAGE_OPTIONS, ("未接单", "已接单（生产中）", "已发货")
        )
        self.assertEqual(STAGE_CODES["未接单"], UNACCEPTED)
        self.assertEqual(STAGE_CODES["已接单（生产中）"], IN_PRODUCTION)
        self.assertEqual(STAGE_CODES["已发货"], SHIPPED)

    def test_humbird_completed_stage_uses_production_status(self):
        client = Mock()

        def production_items(_start, _end, statuses):
            if statuses == (1, 5):
                return [
                    {"code": "accepted", "status": 1},
                    {"code": "shipped-5", "status": 5, "delivery_time": 10},
                ]
            return [
                {"code": "produced", "status": 9},
                {"code": "shipped-9", "status": 9, "delivery_time": 20},
            ]

        client.production_items.side_effect = production_items
        start = datetime(2026, 8, 14).date()

        in_production = _stage_items(client, start, start, IN_PRODUCTION)
        shipped = _stage_items(client, start, start, SHIPPED)

        self.assertEqual(
            {item["code"] for item in in_production},
            {"accepted", "shipped-5"},
        )
        self.assertEqual(
            {item["code"] for item in shipped},
            {"produced", "shipped-9"},
        )

    def test_3d_secret_template_has_s2b_factory_and_qa_sections(self):
        template = (
            Path(__file__).resolve().parents[1]
            / ".streamlit" / "secrets.example.toml"
        ).read_text()

        self.assertIn('[logistics_s2b_accounts."3D"]', template)
        self.assertIn('[factory_credentials."3D热转印"]', template)
        self.assertIn('[qa_credentials."3D热转印"]', template)

    def test_usps_usage_event_records_user_without_tenant_code(self):
        supabase = Mock()
        execute = (
            supabase.table.return_value.insert.return_value.execute
        )
        execute.return_value.data = [{"id": "usage-1"}]

        record_usps_usage(supabase, 10, 1, 9, 1, "Andy")

        payload = supabase.table.return_value.insert.call_args.args[0]
        self.assertEqual(payload["created_by"], "Andy")
        self.assertNotIn("tenant_code", payload)

    def test_usps_usage_uses_official_baseline_and_daily_query_counts(self):
        events = pd.DataFrame([
            {
                "event_type": "query", "tracking_count": 100,
                "request_count": 3, "created_at": "2026-08-02T10:00:00Z",
            },
            {
                "event_type": "query", "tracking_count": 25,
                "request_count": 1, "created_at": "2026-08-02T14:00:00Z",
            },
        ])
        baseline = {
            "official_count": 408,
            "created_at": "2026-08-02T12:00:00Z",
        }
        now = datetime(2026, 8, 2, 12, tzinfo=ZoneInfo("America/New_York"))

        summary, daily = summarize_usps_usage(events, baseline, now, 100000)

        self.assertEqual(summary["today"], 125)
        self.assertEqual(summary["month_used"], 433)
        self.assertEqual(summary["remaining"], 99567)
        self.assertEqual(summary["request_count"], 4)
        self.assertEqual(daily.iloc[0]["查询面单数"], 125)

    @patch("ui.logistics.tracking.query.save_tracking_checks")
    @patch("ui.logistics.tracking.query.record_usps_usage")
    @patch("ui.logistics.tracking.query.get_current_operator_name", return_value="Andy")
    @patch("ui.logistics.tracking.query.load_usps_credentials")
    @patch("ui.logistics.tracking.query.USPSClient")
    def test_live_usps_query_records_tracking_and_batch_usage(
        self, client_class, credentials, _operator, record_usage,
        save_checks,
    ):
        credentials.return_value = {"client_id": "id", "client_secret": "secret"}
        client_class.return_value.track.return_value = [
            {"trackingNumber": "92001", "status": "Created"},
            {"trackingNumber": "92002", "status": "Created"},
        ]
        supabase = Mock()

        rows = _query_usps(["92001", "92002"], supabase=supabase)

        self.assertEqual(len(rows), 2)
        record_usage.assert_called_once_with(
            supabase, 2, 1, 2, 0, "Andy"
        )
        saved_rows = save_checks.call_args.args[1]
        self.assertEqual(len(saved_rows), 2)
        self.assertEqual(
            saved_rows[0]["response_payload"]["trackingNumber"], "92001"
        )
        self.assertEqual(save_checks.call_args.args[2], "Andy")

    @patch("ui.logistics.tracking.query.load_latest_tracking_checks")
    def test_tracking_query_plan_uses_database_before_usps(self, load_latest):
        future = datetime.now(timezone.utc) + timedelta(minutes=30)
        load_latest.return_value = pd.DataFrame([{
            "tracking_number": "92001",
            "cache_expires_at": future.isoformat(),
        }])

        cached, pending = _tracking_query_plan(
            Mock(), ["92001", "92002"], False
        )

        self.assertEqual(cached["tracking_number"].tolist(), ["92001"])
        self.assertEqual(pending, ["92002"])

    @patch("ui.logistics.tracking.query.load_latest_tracking_checks")
    def test_tracking_query_plan_force_mode_refreshes_every_number(
        self, load_latest
    ):
        future = datetime.now(timezone.utc) + timedelta(minutes=30)
        load_latest.return_value = pd.DataFrame([{
            "tracking_number": "92001",
            "cache_expires_at": future.isoformat(),
        }])

        cached, pending = _tracking_query_plan(Mock(), ["92001"], True)

        self.assertTrue(cached.empty)
        self.assertEqual(pending, ["92001"])

    @patch("ui.logistics.tracking.query.save_tracking_checks")
    @patch("ui.logistics.tracking.query.record_usps_usage")
    @patch(
        "ui.logistics.tracking.query.get_current_operator_name",
        return_value="Andy",
    )
    @patch("ui.logistics.tracking.query.load_usps_credentials")
    @patch("ui.logistics.tracking.query.USPSClient")
    def test_usps_missing_response_is_saved_as_failed_check(
        self, client_class, credentials, _operator, record_usage,
        save_checks,
    ):
        credentials.return_value = {"client_id": "id", "client_secret": "secret"}
        client_class.return_value.track.return_value = [
            {"trackingNumber": "92001", "status": "Created"},
        ]

        rows = _query_usps(["92001", "92002"], supabase=Mock())

        missing = next(row for row in rows if row["tracking_number"] == "92002")
        self.assertEqual(missing["error_code"], "USPS_NO_RESPONSE")
        self.assertEqual(len(save_checks.call_args.args[1]), 2)
        record_usage.assert_called_once()
        self.assertEqual(record_usage.call_args.args[3:5], (1, 1))

    @patch("ui.logistics.review.state.st.session_state", new_callable=dict)
    def test_ocr_completion_refreshes_review_and_usps_context(self, state):
        row = {
            "external_order_id": "ORDER-1",
            "tracking_number": "92001",
            "ocr_address": "25 RYANIC RD HEWLETT NY 11557",
            "ocr_weight_oz": 4,
            "ocr_status": "已识别",
        }
        reviewed = [{
            "系统判断": "USPS",
            "USPS子类型": "普通USPS",
            "row": row,
        }]

        _store_review_ocr_results(reviewed, None)

        self.assertIs(state["logistics_carrier_review_rows"], reviewed)
        self.assertEqual(
            state["logistics_usps_candidates"][0]["面单OCR地址"],
            "25 RYANIC RD HEWLETT NY 11557",
        )
        self.assertEqual(state["logistics_review_data_version"], 1)
        self.assertIn("已回填", state["logistics_review_ocr_notice"])

    def test_review_selection_supports_all_and_repeatable_random_sample(self):
        rows = [
            {"row": {"label_url": f"{index}.pdf"}} for index in range(5)
        ] + [{"row": {}}]

        self.assertEqual(
            _review_selection_defaults(rows, "全选可下载", 5, 0),
            [True, True, True, True, True, False],
        )
        first = _review_selection_defaults(rows, "随机抽查", 2, 7)
        second = _review_selection_defaults(rows, "随机抽查", 2, 7)
        self.assertEqual(first, second)
        self.assertEqual(sum(first), 2)
        self.assertFalse(first[-1])

    def test_all_label_download_builds_one_zip_and_deduplicates_urls(self):
        documents = [
            {"url": "https://x.test/a.pdf", "order_id": "ORDER/1"},
            {"url": "https://x.test/a.pdf", "order_id": "DUPLICATE"},
            {"url": "https://x.test/b", "tracking_number": "92002"},
        ]

        archive, errors, count = build_label_archive(
            documents,
            lambda url: b"%PDF-label" if url.endswith("a.pdf") else b"\x89PNG",
            max_workers=2,
        )

        self.assertEqual(errors, [])
        self.assertEqual(count, 2)
        with ZipFile(BytesIO(archive)) as output:
            self.assertEqual(len(output.namelist()), 2)
            self.assertTrue(any(name.endswith(".pdf") for name in output.namelist()))
            self.assertTrue(any(name.endswith(".png") for name in output.namelist()))

    def test_label_documents_include_all_carriers_with_downloads(self):
        reviewed = [
            {"平台": "S2B", "Order ID": "1", "Tracking Number": "A",
             "row": {"label_url": "a.pdf"}},
            {"平台": "七创", "Order ID": "2", "Tracking Number": "B",
             "row": {"backup_label_url": "b.png"}},
            {"平台": "SDS", "Order ID": "3", "row": {}},
        ]

        documents = _label_documents(reviewed)

        self.assertEqual([item["url"] for item in documents], ["a.pdf", "b.png"])

    def test_suspicious_ocr_candidates_include_any_carrier_with_label(self):
        rows = [
            {"系统判断": "USPS", "row": {"label_url": "usps.pdf"}},
            {"系统判断": "CBS", "row": {"backup_label_url": "cbs.png"}},
            {"系统判断": "UPS", "row": {}},
        ]

        candidates = _label_ocr_candidates(rows)

        self.assertEqual(candidates, rows[:2])

    def test_cbs_and_cbt_have_independent_carrier_filters(self):
        self.assertEqual(_carrier_filter_name({
            "系统判断": "USPS", "USPS子类型": "CBS",
        }), "CBS")
        self.assertEqual(_carrier_filter_name({
            "系统判断": "USPS", "USPS子类型": "CBT",
        }), "CBT")
        self.assertEqual(_carrier_filter_name({
            "系统判断": "USPS", "USPS子类型": "普通USPS",
        }), "USPS")

    def test_label_download_is_reused_from_server_cache(self):
        clear_label_cache()
        with patch(
            "automation.logistics.label_cache.download_label_content",
            return_value=b"label-pdf",
        ) as download:
            first = _cached_label_content("http://labels.test/92001.pdf")
            second = _cached_label_content("http://labels.test/92001.pdf")

        self.assertEqual(first, b"label-pdf")
        self.assertEqual(second, b"label-pdf")
        self.assertEqual(download.call_count, 1)

    def test_diy19_logistics_maps_ui_stage_to_customer_order_state(self):
        form = _diy19_list_form(
            1, 1000, datetime(2026, 8, 1), datetime(2026, 8, 2), 6
        )

        self.assertEqual(form["QueryItems[2][FieldName]"], "OrderState")
        self.assertEqual(form["QueryItems[2][FieldValue]"], "2")
        self.assertEqual(
            form["QueryItems[0][FieldValue]"], "2026/08/01 00:00:00"
        )

    def test_diy19_order_normalizes_tracking_and_label_without_excel(self):
        record = {
            "OrderNo": "PO-1",
            "CustomerOrderNo": "SHOP-1",
            "LogisticsTrackingNo": "92001",
            "LogisticsMethonAliseName": "USPS",
            "LogisticsLabelFileOrign": "http://labels.test/92001.pdf",
            "LogisticsLabelFileImage": "OrderAttachment/92001.png",
            "OrderState": "2",
            "OrderState_Name": "已发货",
        }

        rows = _normalize_diy19_record(
            record, "七创", "http://us.qcpod.19diy.com"
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["external_order_id"], "PO-1")
        self.assertEqual(rows[0]["merchant_order_id"], "SHOP-1")
        self.assertEqual(rows[0]["tracking_number"], "92001")
        self.assertEqual(rows[0]["carrier"], "USPS")
        self.assertEqual(rows[0]["label_url"], "http://labels.test/92001.pdf")
        self.assertEqual(
            rows[0]["backup_label_url"],
            "http://us.qcpod.19diy.com/OrderAttachment/92001.png",
        )

    def test_erp_suggestion_preserves_label_for_live_ocr(self):
        rows = normalize_suggested_rows([{
            "订单号": "PO-1",
            "物流单号": "92001",
            "面单PDF": "http://labels.test/92001.pdf",
            "ERP平台": "七创",
        }])

        self.assertEqual(rows[0]["物流单号"], "92001")
        self.assertEqual(rows[0]["面单PDF"], "http://labels.test/92001.pdf")
        self.assertEqual(rows[0]["ERP平台"], "七创")

    def test_erp_candidate_preserves_existing_ocr_result(self):
        pairs = _order_tracking_pairs([{
            "external_order_id": "PO-1",
            "tracking_number": "92001",
            "label_url": "http://labels.test/92001.pdf",
            "ocr_address": "25 RYANIC RD HEWLETT NY 11557",
            "ocr_weight_oz": 4,
            "ocr_status": "已识别",
        }])

        self.assertEqual(pairs[0]["面单OCR地址"], "25 RYANIC RD HEWLETT NY 11557")
        self.assertEqual(pairs[0]["重量（oz）"], 4)
        self.assertEqual(pairs[0]["OCR状态"], "已识别")

    def test_ocr_address_joins_return_address_fields(self):
        self.assertEqual(_ocr_address({
            "extracted_street": "25 RYANIC RD",
            "extracted_city": "HEWLETT",
            "extracted_state": "NY",
            "extracted_postal_code": "11557",
        }), "25 RYANIC RD HEWLETT NY 11557")

    def test_ocr_status_has_multiple_operational_dimensions(self):
        text = _ocr_summary_text({
            "available": 12, "processed": 5, "skipped": 7,
            "missing": 2, "cache_hits": 5,
            "downloaded": 7, "address_ok": 10, "weight_ok": 9,
            "failed": 2,
        })

        self.assertIn("面单可下载 12", text)
        self.assertIn("本次OCR 5", text)
        self.assertIn("未解析 7", text)
        self.assertIn("缓存命中 5", text)
        self.assertIn("OCR地址成功 10", text)
        self.assertIn("重量成功 9", text)
        self.assertIn("失败 2", text)

    def test_ocr_status_displays_elapsed_time_and_average(self):
        text = _ocr_summary_text({
            "available": 10, "processed": 10, "skipped": 0,
            "missing": 0, "cache_hits": 0, "downloaded": 10,
            "address_ok": 10, "weight_ok": 10, "failed": 0,
            "total_seconds": 125, "ocr_seconds": 95,
        })

        self.assertIn("总耗时 2分5秒", text)
        self.assertIn("OCR耗时 1分35秒", text)
        self.assertIn("下载及等待 30秒", text)
        self.assertIn("新面单平均 12.5秒/张", text)
        self.assertEqual(_format_duration(3661), "1小时1分1秒")

    @patch("ui.logistics.review.ocr_format.perf_counter", return_value=20)
    def test_ocr_progress_displays_eta_and_thread_mode(self, _clock):
        text = _ocr_progress_text(
            "S2B", completed=20, total=100, started_at=0, ocr_workers=2
        )

        self.assertIn("已处理 20/100", text)
        self.assertIn("剩余 80", text)
        self.assertIn("平均 1.0秒/张", text)
        self.assertIn("预计还需 1分20秒", text)
        self.assertIn("OCR双线程加速模式", text)

    def test_double_ocr_is_guarded_on_python_314_and_large_batches(self):
        workers, reason = _resolve_ocr_workers(2, (3, 14), False, 5)
        self.assertEqual(workers, 1)
        self.assertIn("Python 3.14", reason)

        workers, reason = _resolve_ocr_workers(2, (3, 12), True, 5)
        self.assertEqual(workers, 1)
        self.assertIn("最多20张", reason)

        workers, reason = _resolve_ocr_workers(2, (3, 12), False, 5)
        self.assertEqual(workers, 2)
        self.assertEqual(reason, "")

    def test_live_ocr_result_exposes_address_weight_and_label(self):
        row = _live_label_row("92001", "http://labels.test/92001.pdf", {
            "extracted_street": "25 RYANIC RD",
            "extracted_city": "HEWLETT",
            "extracted_state": "NY",
            "extracted_postal_code": "11557",
            "extracted_weight_oz": 4,
        }, "已从平台面单OCR识别")

        self.assertEqual(row["发货地址"], "25 RYANIC RD HEWLETT NY 11557")
        self.assertEqual(row["重量（oz）"], 4)
        self.assertEqual(row["面单PDF"], "http://labels.test/92001.pdf")

    @patch("automation.logistics.label_ocr.ocr_pdf_lines")
    def test_downloaded_label_content_can_be_ocr_parsed(self, ocr_lines):
        ocr_lines.return_value = [
            {"text": "25 RYANIC RD", "score": 0.98, "x": 1, "y": 1},
            {"text": "HEWLETT NY 11557", "score": 0.99, "x": 1, "y": 2},
            {"text": "0 LB 4 OZ", "score": 0.97, "x": 1, "y": 3},
        ]

        fields = extract_label_content_fields(b"pdf-content")

        self.assertEqual(fields["extracted_state"], "NY")
        self.assertEqual(fields["extracted_weight_oz"], 4)
        ocr_lines.assert_called_once_with(b"pdf-content", crop_ratio=0.62)

    @patch("automation.logistics.label_ocr.ocr_pdf_lines")
    def test_label_ocr_falls_back_to_full_page_when_crop_misses(self, ocr_lines):
        good_lines = [
            {"text": "25 RYANIC RD", "score": 0.98, "x": 1, "y": 1},
            {"text": "HEWLETT NY 11557", "score": 0.99, "x": 1, "y": 2},
            {"text": "0 LB 4 OZ", "score": 0.97, "x": 1, "y": 3},
        ]
        ocr_lines.side_effect = [[], good_lines]

        fields = extract_label_content_fields(b"pdf-content")

        self.assertEqual(fields["extracted_weight_oz"], 4)
        self.assertEqual(ocr_lines.call_count, 2)
        self.assertEqual(ocr_lines.call_args_list[1].args, (b"pdf-content",))

    def test_customer_can_paste_excel_cells_into_fixed_table(self):
        rows, issues = parse_logistics_frame(pd.DataFrame([
            {"订单号": "ORDER-1", "物流单号": "9400111122223333444455"},
            {"订单号": "ORDER-2", "物流单号": "1Z999AA10123456784"},
        ]))

        self.assertEqual(issues, [])
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1]["external_order_id"], "ORDER-2")

    def test_customer_can_paste_any_header_names(self):
        rows, issues = parse_logistics_paste(
            "客户自己的订单抬头\t客户自己的物流抬头\n"
            "ORDER-1\t9400111122223333444455\n",
            has_header=True,
        )

        self.assertEqual(issues, [])
        self.assertEqual(rows[0]["external_order_id"], "ORDER-1")
        self.assertEqual(rows[0]["tracking_number"], "9400111122223333444455")

    def test_customer_can_import_order_and_tracking_only(self):
        rows, issues = parse_logistics_upload(
            "订单号,物流单号\nORDER-1,9400111122223333444455\n".encode(),
            "orders.csv",
            {"erp_platform": "客户A", "erp_account": "账号1"},
        )

        self.assertEqual(issues, [])
        self.assertEqual(rows[0]["external_order_id"], "ORDER-1")
        self.assertEqual(rows[0]["tracking_number"], "9400111122223333444455")
        self.assertEqual(rows[0]["erp_platform"], "客户A")

    def test_customer_import_reports_incomplete_row(self):
        rows, issues = parse_logistics_upload(
            "订单号,物流单号\nORDER-1,\n".encode(), "orders.csv"
        )

        self.assertEqual(rows, [])
        self.assertEqual(issues, ["第 2 行缺少物流单号"])

    def test_logistics_page_allows_supervisor_query_without_management(self):
        view_allowed = {"supervisor", "after_sales", "admin"}
        manage_allowed = {"after_sales", "admin"}
        for role, permissions in ROLE_PERMISSIONS.items():
            with self.subTest(role=role):
                self.assertEqual(
                    "can_view_logistics" in permissions,
                    role in view_allowed,
                )
                self.assertEqual(
                    "can_manage_logistics" in permissions,
                    role in manage_allowed,
                )

    def test_supervisor_logistics_page_hides_erp_and_ocr_workbench(self):
        with patch("ui.logistics.page.has_permission", return_value=False), patch(
            "ui.logistics.page.render_sync"
        ) as render_sync, patch(
            "ui.logistics.page.render_tracking_lookup"
        ) as render_lookup, patch(
            "ui.logistics.page.render_logistics_summary"
        ) as render_summary, patch(
            "ui.logistics.page.st.session_state", new_callable=dict
        ):
            render_logistics_page(Mock())

        render_sync.assert_not_called()
        self.assertIsNone(render_lookup.call_args.args[2])
        render_summary.assert_not_called()

    def test_logistics_sidebar_only_loads_selected_summary(self):
        with patch("ui.logistics.page.has_permission", return_value=True), patch(
            "ui.logistics.page.render_sync"
        ) as render_sync, patch(
            "ui.logistics.page.render_tracking_lookup"
        ) as render_lookup, patch(
            "ui.logistics.page.render_logistics_summary"
        ) as render_summary:
            render_logistics_page(Mock(), selected_view="summary")

        render_sync.assert_not_called()
        render_lookup.assert_not_called()
        render_summary.assert_called_once()
        self.assertTrue(render_summary.call_args.args[1])

    def test_logistics_navigation_is_a_real_sidebar_group(self):
        section = next(
            items for title, items in NAV_SECTIONS
            if title == "物流单号追踪"
        )

        self.assertEqual(
            [item[1] for item in section],
            ["物流单号获取与USPS核查", "物流数据总结", "审核规则"],
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
        self.assertEqual(parsed["extracted_weight_lb"], 0.3125)
        self.assertEqual(parsed["extracted_weight_display"], "5 oz")

    def test_label_weight_distinguishes_pounds_and_ounces(self):
        self.assertEqual(_weight_ounces("1 LB 4 OZ"), 20)
        self.assertEqual(_weight_ounces("WEIGHT 6 OZ"), 6)
        self.assertEqual(_weight_ounces("WEIGHT 1.5 LB"), 24)

    def test_tracking_lookup_parses_common_separators_and_removes_duplicates(self):
        numbers = parse_tracking_numbers("9400, 9500\n9400；9600")

        self.assertEqual(numbers, ["9400", "9500", "9600"])

    def test_tracking_table_accepts_pasted_column_and_removes_duplicates(self):
        frame = pd.DataFrame({
            "物流单号": ["9400", "9500", "9400", "9600\n9700"],
        })

        self.assertEqual(
            parse_tracking_table(frame), ["9400", "9500", "9600", "9700"]
        )

    def test_order_and_tracking_number_stay_together(self):
        frame = pd.DataFrame([
            {"订单号": "ORDER-A", "物流单号": "9400"},
            {"订单号": "ORDER-B", "物流单号": "9400"},
        ])

        self.assertEqual(parse_order_tracking_table(frame), [
            {"订单号": "ORDER-A", "物流单号": "9400"},
            {"订单号": "ORDER-B", "物流单号": "9400"},
        ])

    def test_erp_candidates_include_order_and_tracking_number(self):
        pairs = _order_tracking_pairs([{
            "external_order_id": "ORDER-A", "tracking_number": "9400",
        }])

        self.assertEqual(
            pairs, [{"订单号": "ORDER-A", "物流单号": "9400"}]
        )

    def test_logistics_platform_default_reuses_department_platforms(self):
        self.assertIn("Haloo", CONNECTED_PLATFORMS)
        self.assertIn("隆丰", CONNECTED_PLATFORMS)
        dtf_pending = [
            platform for platform in PLATFORMS_BY_DEPARTMENT["DTF"]
            if platform not in CONNECTED_PLATFORMS
        ]
        self.assertEqual(dtf_pending, ["莆田", "汉森", "方果"])
        self.assertEqual(
            default_logistics_platforms(
                ("汉森", "S2B", "SDS2"), CONNECTED_PLATFORMS
            ),
            ["S2B", "SDS2"],
        )

    def test_logistics_platform_default_falls_back_when_s2b_is_unavailable(self):
        self.assertEqual(
            default_logistics_platforms(
                ("汉森", "SDS1", "SDS2"), CONNECTED_PLATFORMS
            ),
            ["SDS1", "SDS2"],
        )

    def test_erp_logistics_sync_keeps_one_latest_status_row_per_platform(self):
        row = {
            "external_order_id": "ORDER-1",
            "tracking_number": "92001",
            "label_url": "label.pdf",
        }
        reviewed = [{
            "row": row, "系统判断": "USPS", "USPS子类型": "普通USPS",
        }]
        status = Mock()
        state_table = Mock()
        with patch(
            "ui.logistics.sync_view.fetch_source", return_value=[row]
        ), patch(
            "ui.logistics.sync_view.upsert_shipments",
            return_value=[{"id": "shipment-1"}],
        ), patch(
            "ui.logistics.sync_view.backfill_tracking_check_sources"
        ), patch(
            "ui.logistics.sync_view.classify_carrier_rows",
            return_value=reviewed,
        ), patch(
            "ui.logistics.sync_view.is_target_usps_review", return_value=True
        ), patch(
            "ui.logistics.sync_view.label_ocr_candidates", return_value=[row]
        ), patch(
            "ui.logistics.sync_view.order_tracking_pairs", return_value=[]
        ), patch(
            "ui.logistics.sync_view.reset_review_selection"
        ), patch(
            "ui.logistics.sync_view.st.status", return_value=status
        ), patch(
            "ui.logistics.sync_view.st.progress"
        ), patch(
            "ui.logistics.sync_view.st.empty", return_value=state_table
        ), patch(
            "ui.logistics.sync_view.st.session_state", new_callable=dict
        ):
            _load_selected_sources(
                Mock(), ["隆丰"], "DTF", "未接单",
                datetime(2026, 8, 14).date(), datetime(2026, 8, 15).date(),
            )

        states = "｜".join(
            call.args[0].iloc[0]["最新状态"]
            for call in state_table.dataframe.call_args_list
        )
        self.assertIn("正在请求订单和面单数据", states)
        self.assertIn("正在保存", states)
        self.assertIn("正在识别物流商", states)
        final = state_table.dataframe.call_args.args[0]
        self.assertEqual(final.iloc[0]["平台"], "隆丰")
        self.assertEqual(final.iloc[0]["最新状态"], "处理完成")
        self.assertEqual(final.iloc[0]["读取"], 1)
        self.assertEqual(final.iloc[0]["普通USPS"], 1)
        self.assertEqual(
            status.update.call_args.kwargs["state"], "complete"
        )
        self.assertIn(
            "已准备 1 条普通USPS待核查数据",
            status.update.call_args.kwargs["label"],
        )

    @patch("automation.api.humbird.shipments.HumbirdOpenApiClient")
    def test_humbird_waybill_uses_shared_shipment_shape(self, client_type):
        client = client_type.return_value
        client.production_items.return_value = [{
            "code": "ITEM-1",
            "order_no": "ORDER-1",
            "order_third_id": "SHOP-1",
            "status": 9,
            "delivery_time": 1786590000000,
        }]
        client.waybill.return_value = {
            "track_number": "9400111122223333444455",
            "logistics_method_name": "USPS",
            "logistics_method_id": "USPS-GA",
            "url": "https://labels.test/ORDER-1.pdf",
            "width": 100,
            "height": 150,
        }

        rows = fetch_humbird_shipments(
            "Haloo", {"api_key": "key"},
            datetime(2026, 8, 12).date(),
            datetime(2026, 8, 12).date(),
            status=6,
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["erp_platform"], "Haloo")
        self.assertEqual(rows[0]["external_order_id"], "ORDER-1")
        self.assertEqual(rows[0]["tracking_number"], "9400111122223333444455")
        self.assertEqual(rows[0]["label_url"], "https://labels.test/ORDER-1.pdf")
        self.assertEqual(rows[0]["erp_status"], "已生产/已发货")

    @patch("automation.api.humbird.shipments.fetch_humbird_shipments_legacy")
    @patch("automation.api.humbird.shipments.fetch_humbird_shipments")
    def test_humbird_rate_limit_switches_to_database_token(
        self, official, legacy,
    ):
        official.side_effect = RuntimeError("蜂鸟开放平台接口限流")
        legacy.return_value = [{"tracking_number": "9400"}]
        progress = []
        day = datetime(2026, 8, 12).date()

        rows = fetch_humbird_shipments_with_fallback(
            "Haloo",
            {"api_key": "official", "token": "database-token"},
            day,
            day,
            report_progress=progress.append,
        )

        self.assertEqual(rows, [{"tracking_number": "9400"}])
        legacy.assert_called_once()
        self.assertTrue(any("切换数据库" in item for item in progress))

    @patch("automation.api.humbird.shipments.fetch_humbird_shipments_legacy")
    @patch("automation.api.humbird.shipments.fetch_humbird_shipments")
    def test_humbird_rate_limit_backoff_avoids_immediate_retry(
        self, official, legacy,
    ):
        from automation.api.humbird import shipments

        shipments._OFFICIAL_BACKOFF_UNTIL.clear()
        official.side_effect = HumbirdOpenApiError(
            "蜂鸟开放平台接口限流，请稍后重试"
        )
        legacy.return_value = []
        credentials = {"api_key": "official", "token": "database-token"}
        day = datetime(2026, 8, 12).date()
        progress = []
        try:
            fetch_humbird_shipments_with_fallback(
                "隆丰", credentials, day, day,
                report_progress=progress.append,
            )
            fetch_humbird_shipments_with_fallback(
                "隆丰", credentials, day, day,
                report_progress=progress.append,
            )
        finally:
            shipments._OFFICIAL_BACKOFF_UNTIL.clear()

        self.assertEqual(official.call_count, 1)
        self.assertEqual(legacy.call_count, 2)
        self.assertTrue(any("不再重复请求" in item for item in progress))

    @patch("ui.logistics.sync_view._attach_script_context")
    @patch("ui.logistics.sync_view._script_context", return_value=None)
    @patch("ui.logistics.sync_view.fetch_source")
    def test_multiple_erp_platforms_are_fetched_in_parallel(
        self, fetch, _context, _attach,
    ):
        barrier = Barrier(2)

        def read(source, *_args, **_kwargs):
            barrier.wait(timeout=1)
            return [{"erp_platform": source}]

        fetch.side_effect = read
        status, progress = Mock(), Mock()
        day = datetime(2026, 8, 15).date()

        result = _fetch_selected_sources(
            ["Haloo", "隆丰"], "DTF", SHIPPED,
            day, day, status, progress,
        )

        self.assertEqual(set(result), {"Haloo", "隆丰"})
        self.assertEqual(fetch.call_count, 2)
        self.assertIn("并行读取", status.update.call_args.kwargs["label"])

    @patch("automation.api.humbird.shipments.fetch_humbird_shipments_legacy")
    @patch("automation.api.humbird.shipments.fetch_humbird_shipments")
    def test_humbird_zero_rows_does_not_trigger_fallback(
        self, official, legacy,
    ):
        official.return_value = []
        day = datetime(2026, 8, 12).date()

        rows = fetch_humbird_shipments_with_fallback(
            "Haloo",
            {"api_key": "official", "token": "database-token"},
            day,
            day,
        )

        self.assertEqual(rows, [])
        legacy.assert_not_called()

    @patch("automation.api.humbird.shipments.fetch_humbird_shipments")
    def test_humbird_missing_database_token_requests_browser_refresh(
        self, official,
    ):
        official.side_effect = RuntimeError("蜂鸟开放平台接口限流")
        day = datetime(2026, 8, 12).date()

        with self.assertRaises(HumbirdBrowserRefreshRequired):
            fetch_humbird_shipments_with_fallback(
                "Haloo", {"api_key": "official"}, day, day
            )

    @patch(
        "automation.api.humbird.shipments.fetch_humbird_order_details_http"
    )
    @patch(
        "automation.api.humbird.shipments.fetch_humbird_production_records_http"
    )
    def test_humbird_database_token_normalizes_order_tracking_relation(
        self, production, details,
    ):
        production.return_value = [{
            "code": "ITEM-1",
            "rel_id": 11,
            "order_no": "ORDER-1",
            "order_third_id": "SHOP-1",
            "status": 9,
            "delivery_time": 1786590000000,
        }]
        details.return_value = [{
            "id": 11,
            "third_detail": {
                "track_number_list": [{
                    "tracking_no": "9400111122223333444455",
                    "logistics_name": "USPS",
                    "waybill_url": "https://labels.test/ORDER-1.pdf",
                }],
            },
        }]
        day = datetime(2026, 8, 12).date()

        rows = fetch_humbird_shipments_legacy(
            "Haloo", {"token": "database-token"}, day, day,
            status=SHIPPED,
        )

        self.assertEqual(rows[0]["external_order_id"], "ORDER-1")
        self.assertEqual(rows[0]["tracking_number"], "9400111122223333444455")
        self.assertEqual(rows[0]["carrier"], "USPS")
        self.assertEqual(
            rows[0]["label_url"], "https://labels.test/ORDER-1.pdf"
        )

    def test_live_usps_workflow_does_not_require_database_rows(self):
        display = pd.DataFrame([classify_usps_response({
            "trackingNumber": "9200",
            "status": "Shipping Label Created",
            "trackingEvents": [{
                "eventCode": "GX", "eventType": "Shipping Label Created",
                "eventCity": "BUFORD", "eventState": "GA",
                "eventZIPCode": "30518",
            }],
        })])

        result = _apply_usps_origin_fallback(display)

        self.assertEqual(result.iloc[0]["发货地址"], "BUFORD, GA 30518")
        self.assertEqual(
            result.iloc[0]["始发地点判断"], "异常：不是纽约工厂地址"
        )

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
        self.assertEqual(payload["per_page"], 1000)

    def test_s2b_payload_accepts_production_and_shipped_stages(self):
        self.assertEqual(_order_payload(1, 2)["status"], 2)
        self.assertEqual(_order_payload(1, 6)["status"], 6)

    def test_s2b_shipped_payload_uses_production_completion_dates(self):
        payload = _order_payload(
            1,
            SHIPPED,
            start_date=datetime(2026, 8, 14).date(),
            end_date=datetime(2026, 8, 15).date(),
        )

        self.assertEqual(
            payload["produced_time_before"], "2026-08-14 00:00:00"
        )
        self.assertEqual(
            payload["produced_time_after"], "2026-08-15 23:59:59"
        )
        self.assertNotIn("delivery_time_before", payload)

    @patch("automation.api.s2b.shipments.requests.Session")
    def test_s2b_verifies_selected_dates_after_api_response(self, session):
        response = session.return_value.post.return_value
        response.status_code = 200
        response.json.return_value = {
            "data": {
                "data": [
                    {"order_data": {
                        "order_code": "IN-RANGE",
                        "logisticss_track_number": "94001",
                        "produced_time": "2026-08-15 12:00:00",
                    }},
                    {"order_data": {
                        "order_code": "OLD",
                        "logisticss_track_number": "94002",
                        "produced_time": "2026-08-10 12:00:00",
                    }},
                ],
                "total": 2,
                "last_page": 1,
            },
        }
        start = datetime(2026, 8, 14).date()
        end = datetime(2026, 8, 15).date()

        rows = fetch_s2b_pending_shipments(
            "3D",
            {"token": "saved"},
            status=SHIPPED,
            start_date=start,
            end_date=end,
        )

        self.assertEqual(
            [row["external_order_id"] for row in rows], ["IN-RANGE"]
        )
        payload = session.return_value.post.call_args.kwargs["json"]
        self.assertEqual(payload["produced_time_before"], "2026-08-14 00:00:00")

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


def _logistics_summary_frames():
    shipments = pd.DataFrame([{
        "id": "shipment-1", "department": "DTF", "erp_platform": "Haloo",
        "erp_account": "Haloo", "external_order_id": "ORDER-1",
        "merchant_order_id": "SHOP-1", "tracking_number": "92001",
        "carrier": "USPS", "erp_status": "已发货",
        "label_url": "https://labels.test/1.pdf", "backup_label_url": None,
        "last_seen_at": "2026-08-13T15:00:00Z",
    }])
    checks = pd.DataFrame([{
        "id": "check-1", "tracking_number": "92001",
        "checked_at": "2026-08-13T16:00:00Z",
        "provider_status": "Shipping Label Created",
        "has_postal_record": True, "error_code": "", "created_by": "Andy",
    }])
    sources = pd.DataFrame([{
        "check_id": "check-1", "shipment_id": "shipment-1",
        "department": "DTF", "erp_platform": "Haloo",
        "erp_account": "Haloo", "external_order_id": "ORDER-1",
        "merchant_order_id": "SHOP-1",
        "label_url": "https://labels.test/1.pdf", "backup_label_url": None,
    }])
    reviews = pd.DataFrame([{
        "shipment_id": "shipment-1", "ocr_status": "已识别",
        "automatic_result": "OCR已识别", "extracted_street": "25 Ranic Rd",
        "extracted_city": "", "extracted_state": "NY",
        "extracted_postal_code": "11788", "extracted_weight_oz": 4,
    }])
    return shipments, checks, sources, reviews


if __name__ == "__main__":
    unittest.main()
