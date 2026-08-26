from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ReadmeAssetsTest(unittest.TestCase):
    def test_local_images_exist(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        sources = re.findall(r'<img\s+[^>]*src="([^"]+)"', readme)
        local_sources = [source for source in sources if "://" not in source]

        self.assertTrue(local_sources, "README 中没有本地图片")
        for source in local_sources:
            self.assertTrue(
                (ROOT / source).is_file(),
                f"README 引用的本地图片不存在：{source}",
            )


if __name__ == "__main__":
    unittest.main()
