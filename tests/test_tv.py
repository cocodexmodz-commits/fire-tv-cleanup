import io
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from helpers import FakeDevice, ROOT, import_tool


class TvMainTest(unittest.TestCase):
    def setUp(self):
        self.tv = import_tool("tv")

    def run_main(self, argv, responder=None, stdin=""):
        dev = FakeDevice(responder)
        out = io.StringIO()
        with mock.patch.object(self.tv, "connect", return_value=dev), \
                mock.patch.object(sys, "argv", ["tv.py"] + argv), \
                mock.patch.object(sys, "stdin", io.StringIO(stdin)), \
                mock.patch.object(sys, "stdout", out):
            self.tv.main()
        return dev, out.getvalue()

    def test_probe_prints_each_property(self):
        dev, out = self.run_main(["--probe"], lambda cmd: f"val:{cmd.split()[1]}\n")
        self.assertIn("ro.product.model = val:ro.product.model", out.splitlines())
        self.assertEqual(len(dev.commands), 6)
        self.assertTrue(all(c.startswith("getprop ") for c in dev.commands))
        self.assertTrue(dev.closed)

    def test_no_args_probes(self):
        dev, _ = self.run_main([])
        self.assertEqual(dev.commands[0], "getprop ro.product.model")

    def test_single_command_joins_args(self):
        dev, out = self.run_main(["pm", "list", "packages"], lambda cmd: "package:a\n")
        self.assertEqual(dev.commands, ["pm list packages"])
        self.assertEqual(out, "package:a\n")

    def test_batch_skips_blanks_and_comments(self):
        dev, out = self.run_main(["--batch"], lambda cmd: "done", stdin="# note\n\n  echo hi  \nls\n")
        self.assertEqual(dev.commands, ["echo hi", "ls"])
        # output without a trailing newline gets one, so commands don't run together
        self.assertEqual(out, "$ echo hi\ndone\n$ ls\ndone\n")

    def test_batch_empty_output(self):
        _, out = self.run_main(["--batch"], stdin="true\n")
        self.assertEqual(out, "$ true\n")

    def test_push_and_pull(self):
        dev, out = self.run_main(["--push", "a.apk", "/data/local/tmp/a.apk"])
        self.assertEqual(dev.pushed, [("a.apk", "/data/local/tmp/a.apk")])
        self.assertIn("pushed a.apk -> /data/local/tmp/a.apk", out)
        dev, out = self.run_main(["--pull", "/sdcard/s.png", "s.png"])
        self.assertEqual(dev.pulled, [("/sdcard/s.png", "s.png")])

    def test_push_with_wrong_arg_count_falls_through_to_shell(self):
        dev, _ = self.run_main(["--push", "only-one"])
        self.assertEqual(dev.commands, ["--push only-one"])
        self.assertEqual(dev.pushed, [])


class TvKeyTest(unittest.TestCase):
    def test_get_signer_generates_key_once(self):
        tv = import_tool("tv")
        with tempfile.TemporaryDirectory() as d:
            keydir = os.path.join(d, "adbkey")
            key = os.path.join(keydir, "adbkey")
            with mock.patch.object(tv, "KEYDIR", keydir), mock.patch.object(tv, "KEY", key):
                signer = tv.get_signer()
                self.assertEqual((signer.pub, signer.priv), ("PUBLIC", "PRIVATE"))
                with open(key, "w") as f:
                    f.write("EXISTING")
                self.assertEqual(tv.get_signer().priv, "EXISTING")  # not regenerated


class TvEnvTest(unittest.TestCase):
    def test_missing_tv_host_exits_with_help(self):
        env = {k: v for k, v in os.environ.items() if k != "TV_HOST"}
        env["PYTHONPATH"] = os.path.join(ROOT, "tests")
        code = "import helpers; helpers.install_adb_stubs(); import runpy; " \
               f"runpy.run_path({os.path.join(ROOT, 'tools', 'tv.py')!r})"
        p = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True,
                           encoding="utf-8")
        self.assertEqual(p.returncode, 1)
        self.assertIn("Set TV_HOST", p.stderr)


if __name__ == "__main__":
    unittest.main()
