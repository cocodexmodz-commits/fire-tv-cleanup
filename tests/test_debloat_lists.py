"""Sanity checks for every examples/*/debloat.txt, so a bad contribution fails before it reaches a TV."""
import glob
import os
import re
import unittest

from helpers import ROOT

PACKAGE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z0-9_]+)+$")
# Disabling these leaves the TV without a home screen, settings or input. (The stock Google TV
# launcher is fine to disable on Android TV: launcher/ replaces it and restore.sh re-enables it.
# Fire OS, by contrast, needs com.amazon.tv.launcher enabled.)
NEVER_DISABLE = {
    "com.amazon.tv.launcher",
    "com.android.settings",
    "com.android.systemui",
    "com.android.tv.settings",
    "com.google.android.inputmethod.latin",
    "com.gathin.tvhome",
}
LISTS = sorted(glob.glob(os.path.join(ROOT, "examples", "*", "debloat.txt")))


def packages(path):
    """Mirror the parsing in tools/disable.sh: drop comment/blank lines and trailing comments."""
    out = []
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            line = re.sub(r"\s+#.*$", "", line.strip())
            if line and not line.startswith("#"):
                out.append((n, line))
    return out


class DebloatListTest(unittest.TestCase):
    def test_lists_exist(self):
        self.assertTrue(LISTS)

    def test_each_list(self):
        for path in LISTS:
            name = os.path.relpath(path, ROOT)
            with self.subTest(list=name):
                pkgs = packages(path)
                self.assertTrue(pkgs, "list has no packages")
                seen = set()
                for n, pkg in pkgs:
                    self.assertRegex(pkg, PACKAGE, f"line {n}: not a single package name")
                    self.assertNotIn(pkg, seen, f"line {n}: duplicate {pkg}")
                    self.assertNotIn(pkg, NEVER_DISABLE, f"line {n}: {pkg} must stay enabled")
                    seen.add(pkg)


if __name__ == "__main__":
    unittest.main()
