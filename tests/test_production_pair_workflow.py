import unittest

import pandas as pd

from utils.production.pair_workflow import (
    build_pair_workflow_from_detail,
    build_pair_workflow_table,
)


class ProductionPairWorkflowTests(unittest.TestCase):
    def test_summary_keeps_one_row_per_qa_person(self):
        rows = pd.DataFrame([
            segment_row("13:05", "14:25", "吴雪珍", "黄基银", 25),
        ])

        result = build_pair_workflow_table(rows)

        self.assertEqual(len(result), 1)
        self.assertEqual(result.loc[0, "质检人员"], "吴雪珍")
        self.assertEqual(result.loc[0, "主要烫印人员"], "黄基银")
        self.assertEqual(result.loc[0, "总产量"], 25)
        self.assertEqual(result.loc[0, "切换次数"], 0)
        self.assertEqual(
            result.loc[0, "工作流"],
            "09:05–10:25 黄基银（25）",
        )

    def test_platform_changes_do_not_split_pair_workflow(self):
        rows = pd.DataFrame([
            detail_row(1, "13:01", "质检甲", "烫印甲", "Haloo"),
            detail_row(2, "13:40", "质检甲", "烫印甲", "Haloo"),
            detail_row(3, "13:41", "质检甲", "烫印乙", "Haloo"),
            detail_row(4, "13:42", "质检甲", "烫印乙", "SDS", 3),
            detail_row(5, "16:00", "质检甲", "烫印乙", "SDS"),
        ])

        result = build_pair_workflow_from_detail(rows)

        self.assertEqual(len(result), 1)
        self.assertEqual(result.loc[0, "主要烫印人员"], "烫印乙")
        self.assertEqual(result.loc[0, "烫印人员明细"], "烫印乙 5、烫印甲 2")
        self.assertEqual(result.loc[0, "总产量"], 7)
        self.assertEqual(result.loc[0, "切换次数"], 1)
        self.assertIn("09:41–12:00 烫印乙（5）", result.loc[0, "工作流"])


def segment_row(start, end, qa, hotstamp, count):
    work_date = "2026-08-03"
    return {
        "segment_start_at": f"{work_date}T{start}:00+00:00",
        "segment_end_at": f"{work_date}T{end}:00+00:00",
        "qa_person": qa,
        "hotstamp_person": hotstamp,
        "scan_count": count,
    }


def detail_row(row_id, scanned_at, qa, hotstamp, platform, multiple_count=1):
    return {
        "id": row_id,
        "scanned_at": f"2026-08-03T{scanned_at}:00+00:00",
        "scanned_by": qa,
        "hotstamp_by": hotstamp,
        "platform": platform,
        "multiple_count": multiple_count,
    }


if __name__ == "__main__":
    unittest.main()
