"""文档流水线里的并发行为测试。

图片描述与关系抽取都是独立的模型调用，串行会按张数/块数线性拖长整条流水线。
这里验证它们真的并发执行，且失败项不影响其他项。
"""
from __future__ import annotations

import threading
import time
import unittest

from .service import DocImage, DocumentError, ParsedDocument, caption_images


class _Captioner:
    """记录并发度：同一时刻在跑的 describe 越多，说明确实并行。"""

    def __init__(self, fail_on: str = "", delay: float = 0.05):
        self.fail_on = fail_on
        self.delay = delay
        self.live = 0
        self.peak = 0
        self.lock = threading.Lock()

    def describe(self, path):
        with self.lock:
            self.live += 1
            self.peak = max(self.peak, self.live)
        try:
            time.sleep(self.delay)
            if self.fail_on and self.fail_on in str(path):
                raise DocumentError("描述失败")
            return f"描述 {path.name}"
        finally:
            with self.lock:
                self.live -= 1


class CaptionImagesTests(unittest.TestCase):
    def _parsed(self, count: int) -> ParsedDocument:
        images = [
            DocImage(src=f"images/{index}.jpg", object_name="", url="",
                     local_path=__import__("pathlib").Path(f"/tmp/{index}.jpg"),
                     tag=f"![{index}](images/{index}.jpg)")
            for index in range(count)
        ]
        return ParsedDocument(markdown="\n\n".join(image.tag for image in images),
                              images=images)

    def test_images_are_captioned_in_parallel(self):
        parsed = self._parsed(4)
        captioner = _Captioner()
        started = time.monotonic()
        warnings = caption_images(parsed, captioner)
        elapsed = time.monotonic() - started
        self.assertEqual(warnings, [])
        self.assertEqual(captioner.peak, 4)
        self.assertLess(elapsed, 0.2)

    def test_failure_of_one_image_does_not_stop_the_others(self):
        parsed = self._parsed(3)
        captioner = _Captioner(fail_on="1.jpg")
        warnings = caption_images(parsed, captioner)
        self.assertEqual(len(warnings), 1)
        self.assertIn("1.jpg", warnings[0])
        self.assertTrue(parsed.images[0].caption)
        self.assertTrue(parsed.images[2].caption)

    def test_images_without_local_file_are_skipped(self):
        parsed = self._parsed(1)
        parsed.images[0].local_path = None
        captioner = _Captioner()
        self.assertEqual(caption_images(parsed, captioner), [])
        self.assertEqual(captioner.peak, 0)


if __name__ == "__main__":
    unittest.main()
