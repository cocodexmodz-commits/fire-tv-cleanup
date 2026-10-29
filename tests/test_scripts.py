"""Run disable.sh / restore.sh against a fake venv python that captures the batch it is fed."""
import os
import shutil
import subprocess
import tempfile
import unittest

from helpers import ROOT

BASH = shutil.which("bash")

LIST = """\
# header comment

com.example.ads      # trailing comment
  com.example.telemetry
\t# indented comment
com.example.promo
"""


@unittest.skipUnless(BASH, "bash not available")
class ScriptTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        tools = os.path.join(self.tmp, "tools")
        os.makedirs(os.path.join(tools, "venv", "bin"))
        for name in ("disable.sh", "restore.sh"):
            shutil.copy(os.path.join(ROOT, "tools", name), tools)
        self.captured = os.path.join(self.tmp, "batch.txt")
        fake = os.path.join(tools, "venv", "bin", "python")
        with open(fake, "w", newline="\n") as f:
            f.write(f'#!/usr/bin/env bash\necho "$@" > "{self.posix(self.captured)}.args"\n'
                    f'cat > "{self.posix(self.captured)}"\n')
        os.chmod(fake, 0o755)
        self.list = os.path.join(self.tmp, "debloat.txt")
        with open(self.list, "w", newline="\n") as f:
            f.write(LIST)

    def posix(self, path):
        return subprocess.run([BASH, "-c", 'cygpath -u "$1" 2>/dev/null || echo "$1"', "_", path],
                              capture_output=True, text=True).stdout.strip()

    def run_script(self, *args):
        script = self.posix(os.path.join(self.tmp, "tools", args[0]))
        p = subprocess.run([BASH, script, *[self.posix(a) if os.path.exists(a) else a for a in args[1:]]],
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        with open(self.captured) as f:
            batch = f.read().splitlines()
        with open(self.captured + ".args") as f:
            self.assertEqual(f.read().split(), ["-I", "tools/tv.py", "--batch"])
        return batch

    def test_disable(self):
        self.assertEqual(self.run_script("disable.sh", self.list), [
            "pm disable-user --user 0 com.example.ads",
            "pm disable-user --user 0 com.example.telemetry",
            "pm disable-user --user 0 com.example.promo",
            "pm list packages -d",
        ])

    def test_restore_default_launcher(self):
        batch = self.run_script("restore.sh", self.list)
        self.assertEqual(batch[:3], ["pm enable com.example.ads", "pm enable com.example.telemetry",
                                     "pm enable com.example.promo"])
        self.assertIn("pm enable com.google.android.tvlauncher", batch)
        self.assertIn("cmd package set-home-activity --user 0 com.google.android.tvlauncher", batch)
        self.assertIn("settings put global animator_duration_scale 1.0", batch)
        self.assertEqual(batch[-1], "pm list packages -d")

    def test_restore_custom_launcher(self):
        batch = self.run_script("restore.sh", self.list, "com.amazon.tv.launcher")
        self.assertIn("cmd package set-home-activity --user 0 com.amazon.tv.launcher", batch)
        self.assertNotIn("pm enable com.google.android.tvlauncher", batch)

    def test_disable_without_venv_explains_setup(self):
        shutil.rmtree(os.path.join(self.tmp, "tools", "venv"))
        p = subprocess.run([BASH, self.posix(os.path.join(self.tmp, "tools", "disable.sh")),
                            self.posix(self.list)], capture_output=True, text=True)
        self.assertEqual(p.returncode, 1)
        self.assertIn("python3 -m venv tools/venv", p.stdout)

    def test_missing_list_argument(self):
        p = subprocess.run([BASH, self.posix(os.path.join(self.tmp, "tools", "disable.sh"))],
                           capture_output=True, text=True)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("usage: disable.sh", p.stderr)


if __name__ == "__main__":
    unittest.main()
