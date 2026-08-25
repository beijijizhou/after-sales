import re
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from ui.production.summary import load_rpc_summary
from utils.production.loaders import (
    load_daily_production_rows,
    load_period_person_platform_rows,
    load_summary_rpc,
)


class _Response:
    def __init__(self, data):
        self.data = data


class _RpcCall:
    def __init__(self, data):
        self.data = data

    def execute(self):
        return _Response(self.data)


class _TableQuery:
    def __init__(self, data):
        self.data = data
        self.calls = []

    def __getattr__(self, name):
        def record(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            return self

        return record

    def execute(self):
        return _Response(self.data)


class _Supabase:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.rpc_calls = []
        self.table_query = _TableQuery(self.rows)

    def rpc(self, name, params):
        self.rpc_calls.append((name, params))
        return _RpcCall(self.rows)

    def table(self, name):
        self.table_query.calls.append(("table", (name,), {}))
        return self.table_query


class ProductionDepartmentSummaryTests(unittest.TestCase):
    def test_daily_summary_rpc_sends_department_to_avoid_overload(self):
        supabase = _Supabase([{"scan_count": 1}])
        snapshot = datetime.fromisoformat("2026-08-24T12:00:00-04:00")

        load_summary_rpc(
            supabase,
            "get_daily_qa_person_platform_summary",
            date(2026, 8, 24),
            snapshot,
            "UV",
        )

        self.assertEqual(supabase.rpc_calls[0][1], {
            "target_date": "2026-08-24",
            "snapshot_at": snapshot.isoformat(),
            "p_department": "UV",
        })

    def test_legacy_detail_query_is_scoped_to_department(self):
        supabase = _Supabase([{
            "id": 1,
            "production_department": "UV",
        }])

        rows = load_daily_production_rows(
            supabase, date(2026, 8, 24), "scanned_by",
            department="UV",
        )

        self.assertEqual(rows["production_department"].tolist(), ["UV"])
        self.assertIn(
            ("eq", ("production_department", "UV"), {}),
            supabase.table_query.calls,
        )

    def test_period_summary_rpc_sends_department(self):
        supabase = _Supabase()

        load_period_person_platform_rows(
            supabase,
            date(2026, 8, 11),
            date(2026, 8, 24),
            "scanned_by",
            department="UV",
        )

        self.assertEqual(
            supabase.rpc_calls[0][1]["p_department"], "UV"
        )

    @patch("ui.production.summary.load_pair_platform_workflow_rows")
    @patch("ui.production.summary.load_hourly_person_client_rows")
    @patch("ui.production.summary.load_hourly_summary_rows")
    @patch("ui.production.summary.load_person_platform_summary_rows")
    def test_uv_skips_platform_switch_and_hotstamp_workflow_queries(
        self, load_people, load_hourly, load_hourly_people, load_pair,
    ):
        load_people.return_value = pd.DataFrame([{
            "person": "UV质检甲",
            "platform": "任意来源",
            "scan_count": 12,
            "multiple_order_count": 1,
            "first_scan_at": "2026-08-24T13:00:00+00:00",
            "last_scan_at": "2026-08-24T14:00:00+00:00",
        }])
        load_hourly.return_value = pd.DataFrame([{
            "hour_start_at": "2026-08-24T13:00:00+00:00",
            "scan_count": 12,
            "haloo_count": 0,
        }])

        result = load_rpc_summary(
            _Supabase(), date(2026, 8, 24), "scanned_by", None, "UV"
        )

        self.assertEqual(result[0].loc[0, "scan_count"], 12)
        load_hourly_people.assert_not_called()
        load_pair.assert_not_called()

    def test_missing_department_hourly_rpc_uses_filtered_detail(self):
        people = pd.DataFrame([{
            "person": "UV质检甲",
            "platform": "任意来源",
            "scan_count": 12,
            "multiple_order_count": 1,
            "first_scan_at": "2026-08-24T13:00:00+00:00",
            "last_scan_at": "2026-08-24T14:00:00+00:00",
        }])
        expected_hourly = pd.DataFrame([{"scan_count": 12}])
        missing_rpc = Exception(
            "{'code': 'PGRST202', 'message': 'missing p_department'}"
        )
        with (
            patch(
                "ui.production.summary.load_person_platform_summary_rows",
                return_value=people,
            ),
            patch(
                "ui.production.summary.load_hourly_summary_rows",
                side_effect=missing_rpc,
            ),
            patch(
                "ui.production.summary.load_daily_production_rows",
                return_value=pd.DataFrame([{"id": 1}]),
            ) as load_detail,
            patch(
                "ui.production.summary.prepare_production_df",
                return_value=pd.DataFrame([{"prepared": True}]),
            ),
            patch(
                "ui.production.summary.summarize_by_hour",
                return_value=expected_hourly,
            ),
        ):
            result = load_rpc_summary(
                _Supabase(), date(2026, 8, 24),
                "scanned_by", None, "UV",
            )

        self.assertTrue(result[2].equals(expected_hourly))
        self.assertEqual(load_detail.call_args.args[-1], "UV")

    def test_qa_summary_sql_replaces_legacy_overloads(self):
        root = Path(__file__).resolve().parents[1]
        sql_files = [
            "01_person_platform.sql",
            "02_hourly_totals.sql",
            "03_hourly_people.sql",
            "04_pair_workflow.sql",
            "05_qa_period.sql",
        ]
        for filename in sql_files:
            sql = (root / "sql/production/summaries" / filename).read_text()
            self.assertIn("p_department text default null", sql)
            self.assertRegex(
                sql,
                re.compile(r"coalesce\(production_department, 'DTF'\)\s*="),
            )


if __name__ == "__main__":
    unittest.main()
