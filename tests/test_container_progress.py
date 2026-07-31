from datetime import date
import unittest

import pandas as pd

from db.inventory.container.progress import (
    build_container_progress_choices,
)


class ContainerProgressTests(unittest.TestCase):
    def test_choices_use_stable_container_key_and_clear_label(self):
        progress = pd.DataFrame([{
            "货柜记录ID": "record-26071701",
            "货柜号": "26071701",
            "预计到货日期": date(2026, 7, 29),
            "总件数": 93_000,
            "到货提醒": "已延迟 2 天",
        }])

        choices = build_container_progress_choices(progress)

        self.assertEqual(list(choices), ["record-26071701"])
        self.assertEqual(
            choices["record-26071701"],
            "26071701｜到货 07/29｜93,000 件｜已延迟 2 天",
        )


if __name__ == "__main__":
    unittest.main()
