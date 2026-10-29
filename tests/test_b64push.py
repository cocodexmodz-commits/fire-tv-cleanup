import io
import os
import sys
import tempfile
import unittest
from unittest import mock

from helpers import FakeDevice, FakeShellFS, import_tool


class B64PushTest(unittest.TestCase):
    def setUp(self):
        self.b64push = import_tool("b64push")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def push(self, data, fs):
        local = os.path.join(self.tmp.name, "app.apk")
        with open(local, "wb") as f:
            f.write(data)
        dev = FakeDevice(fs)
        out = io.StringIO()
        with mock.patch.object(self.b64push.tv, "connect", return_value=dev), \
                mock.patch.object(sys, "argv", ["b64push.py", local, "/data/local/tmp/app.apk"]), \
                mock.patch.object(sys, "stdout", out), \
                self.assertRaises(SystemExit) as exit_:
            self.b64push.main()
        return exit_.exception.code, out.getvalue(), dev

    def test_multi_chunk_roundtrip(self):
        data = os.urandom(self.b64push.CHUNK * 2 + 123)  # 3 chunks, the last one partial
        fs = FakeShellFS()
        code, out, dev = self.push(data, fs)
        self.assertEqual(code, 0)
        self.assertIn("MATCH", out)
        self.assertIn("chunk 3/3", out)
        self.assertEqual(fs.files["/data/local/tmp/app.apk"], data)
        self.assertNotIn("/data/local/tmp/app.apk.b64", fs.files)  # temp file cleaned up
        self.assertEqual(dev.commands[0], "rm -f /data/local/tmp/app.apk /data/local/tmp/app.apk.b64")
        self.assertTrue(dev.closed)

    def test_exact_chunk_multiple_has_no_empty_chunk(self):
        fs = FakeShellFS()
        code, out, dev = self.push(b"a" * self.b64push.CHUNK, fs)
        self.assertEqual(code, 0)
        self.assertEqual(sum(c.startswith("echo '") for c in dev.commands), 1)

    def test_failed_chunk_aborts(self):
        code, out, dev = self.push(os.urandom(self.b64push.CHUNK * 3), FakeShellFS(fail_chunk=1))
        self.assertEqual(code, 1)
        self.assertIn("chunk 1 failed", out)
        self.assertFalse(any(c.startswith("base64 -d") for c in dev.commands))

    def test_md5_mismatch_exits_nonzero(self):
        code, out, _ = self.push(b"hello", FakeShellFS(corrupt=True))
        self.assertEqual(code, 1)
        self.assertIn("MISMATCH", out)

    def test_empty_remote_output_is_mismatch(self):
        responder = FakeShellFS()

        def no_md5(cmd):
            out = responder(cmd)
            return "" if cmd.startswith("base64 -d") else out

        code, out, _ = self.push(b"hello", no_md5)
        self.assertEqual(code, 1)
        self.assertIn("MISMATCH", out)


if __name__ == "__main__":
    unittest.main()
