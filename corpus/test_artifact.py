# SPDX-License-Identifier: MIT
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from artifact import write_idempotent


class PublicationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.target = self.root / "model.json"

    def test_idempotent_and_no_overwrite(self):
        write_idempotent(self.target, b"complete")
        before = self.target.stat().st_mtime_ns
        write_idempotent(self.target, b"complete")
        self.assertEqual(self.target.stat().st_mtime_ns, before)
        with self.assertRaises(ValueError):
            write_idempotent(self.target, b"different")
        self.assertEqual(self.target.read_bytes(), b"complete")

    def test_interrupt_before_publication_and_retry(self):
        with patch("artifact.os.fsync", side_effect=KeyboardInterrupt), self.assertRaises(KeyboardInterrupt):
            write_idempotent(self.target, b"complete")
        self.assertEqual(list(self.root.iterdir()), [])
        write_idempotent(self.target, b"complete")
        self.assertEqual(self.target.read_bytes(), b"complete")

    def test_link_failure_does_not_fall_back_to_partial_write(self):
        with patch("artifact.os.link", side_effect=OSError("unsupported filesystem")), self.assertRaises(OSError):
            write_idempotent(self.target, b"complete")
        self.assertEqual(list(self.root.iterdir()), [])

    def test_concurrent_identical_publishers(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda _: write_idempotent(self.target, b"same"), range(16)))
        self.assertEqual(self.target.read_bytes(), b"same")
        self.assertEqual(list(self.root.iterdir()), [self.target])

    def test_concurrent_different_publishers(self):
        def publish(data):
            try:
                write_idempotent(self.target, data)
                return True
            except ValueError:
                return False
        choices = [b"one", b"two", b"three", b"four"]
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(publish, choices))
        self.assertEqual(sum(results), 1)
        self.assertEqual(self.target.read_bytes(), choices[results.index(True)])
        self.assertEqual(list(self.root.iterdir()), [self.target])

    def test_empty_and_nested_artifacts(self):
        path = self.root / "nested" / "empty"
        write_idempotent(path, b"")
        write_idempotent(path, b"")
        self.assertEqual(path.read_bytes(), b"")

    def test_unrelated_staging_file_is_preserved(self):
        stale = self.root / ".model.json.old.tmp"
        stale.write_bytes(b"unfinished")
        write_idempotent(self.target, b"complete")
        self.assertEqual(stale.read_bytes(), b"unfinished")


if __name__ == "__main__":
    unittest.main()
