# SPDX-License-Identifier: MIT
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import subprocess
import sys
import time
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

    def test_process_killed_at_publication_boundary_can_retry(self):
        # Stop a real child without allowing its finally block to clean up.
        # Synchronize at the link boundary instead of racing a timed kill.
        child = """
import sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, sys.argv[1])
import artifact
target, ready = map(Path, sys.argv[2:4])
phase = sys.argv[4]
link = artifact.os.link
def pause_at_link(source, destination):
    if phase == 'after':
        link(source, destination)
    ready.write_text('ready', encoding='ascii')
    sys.stdin.buffer.read(1)
    if phase == 'before':
        link(source, destination)
with patch('artifact.os.link', side_effect=pause_at_link):
    artifact.write_idempotent(target, b'complete')
"""
        for phase in ("before", "after"):
            with self.subTest(phase=phase):
                directory = self.root / phase
                directory.mkdir()
                target = directory / "model.json"
                ready = directory / "ready"
                process = subprocess.Popen(
                    [sys.executable, "-I", "-c", child,
                     str(Path(__file__).resolve().parent), str(target), str(ready), phase],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                )
                try:
                    deadline = time.monotonic() + 15
                    while not ready.exists():
                        if process.poll() is not None:
                            self.fail(f"child exited before checkpoint: {process.communicate()!r}")
                        if time.monotonic() >= deadline:
                            self.fail("child did not reach publication checkpoint")
                        time.sleep(0.01)
                    process.kill()
                    process.communicate(timeout=5)
                    self.assertNotEqual(process.returncode, 0)
                    staged = list(directory.glob(".model.json.*.tmp"))
                    self.assertEqual(len(staged), 1)
                    self.assertEqual(staged[0].read_bytes(), b"complete")
                    self.assertEqual(target.exists(), phase == "after")
                    if target.exists():
                        self.assertEqual(target.read_bytes(), b"complete")
                    write_idempotent(target, b"complete")
                    self.assertEqual(target.read_bytes(), b"complete")
                    before = target.stat().st_mtime_ns
                    write_idempotent(target, b"complete")
                    self.assertEqual(target.stat().st_mtime_ns, before)
                    with self.assertRaises(ValueError):
                        write_idempotent(target, b"different")
                    self.assertEqual(target.read_bytes(), b"complete")
                    self.assertEqual(list(directory.glob(".model.json.*.tmp")), staged)
                    self.assertEqual(staged[0].read_bytes(), b"complete")
                finally:
                    if process.poll() is None:
                        process.kill()
                    process.communicate(timeout=5)


if __name__ == "__main__":
    unittest.main()
