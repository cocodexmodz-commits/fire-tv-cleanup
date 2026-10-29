"""Shared test helpers: stub out adb_shell so tools/ can be imported without it or a TV."""
import base64
import hashlib
import importlib
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")


def install_adb_stubs():
    """Register fake adb_shell modules in sys.modules (only the names tools/tv.py imports)."""
    if "adb_shell" in sys.modules and getattr(sys.modules["adb_shell"], "_is_stub", False):
        return
    pkg = types.ModuleType("adb_shell")
    pkg._is_stub = True
    adb_device = types.ModuleType("adb_shell.adb_device")
    auth = types.ModuleType("adb_shell.auth")
    keygen_mod = types.ModuleType("adb_shell.auth.keygen")
    signer_mod = types.ModuleType("adb_shell.auth.sign_pythonrsa")

    class AdbDeviceTcp:
        def __init__(self, *a, **kw):
            raise AssertionError("tests must patch tv.connect; no real ADB connection allowed")

    def keygen(path):
        with open(path, "w") as f:
            f.write("PRIVATE")
        with open(path + ".pub", "w") as f:
            f.write("PUBLIC")

    class PythonRSASigner:
        def __init__(self, pub, priv):
            self.pub, self.priv = pub, priv

    adb_device.AdbDeviceTcp = AdbDeviceTcp
    keygen_mod.keygen = keygen
    signer_mod.PythonRSASigner = PythonRSASigner
    sys.modules.update({
        "adb_shell": pkg,
        "adb_shell.adb_device": adb_device,
        "adb_shell.auth": auth,
        "adb_shell.auth.keygen": keygen_mod,
        "adb_shell.auth.sign_pythonrsa": signer_mod,
    })


def import_tool(name, host="10.0.0.5"):
    """Import (or re-import) a module from tools/ with TV_HOST set and adb_shell stubbed."""
    install_adb_stubs()
    os.environ["TV_HOST"] = host
    if TOOLS not in sys.path:
        sys.path.insert(0, TOOLS)
    for mod in (name, "tv"):
        sys.modules.pop(mod, None)
    return importlib.import_module(name)


class FakeDevice:
    """Records shell commands; answers with canned output or a callable."""

    def __init__(self, responder=None):
        self.commands = []
        self.pushed = []
        self.pulled = []
        self.closed = False
        self.responder = responder or (lambda cmd: "")

    def shell(self, cmd, **kw):
        self.commands.append(cmd)
        return self.responder(cmd)

    def push(self, local, remote, **kw):
        self.pushed.append((local, remote))

    def pull(self, remote, local, **kw):
        self.pulled.append((remote, local))

    def close(self):
        self.closed = True


class FakeShellFS:
    """A responder that emulates the shell commands b64push.py sends, on an in-memory filesystem."""

    def __init__(self, fail_chunk=None, corrupt=False):
        self.files = {}
        self.fail_chunk = fail_chunk
        self.corrupt = corrupt

    def __call__(self, cmd):
        if cmd.startswith("rm -f "):
            for path in cmd.split()[2:]:
                self.files.pop(path, None)
            return ""
        if cmd.startswith("echo '"):
            # echo '<b64>' >> <tmp> && echo ok<i>
            part, rest = cmd[len("echo '"):].split("' >> ", 1)
            tmp, marker = rest.split(" && echo ")
            if self.fail_chunk is not None and marker == f"ok{self.fail_chunk}":
                return "sh: write error: No space left on device\n"
            self.files[tmp] = self.files.get(tmp, "") + part + "\n"
            return marker + "\n"
        if cmd.startswith("base64 -d "):
            # base64 -d <tmp> > <remote> && rm <tmp> && md5sum <remote>
            tmp = cmd.split()[2]
            remote = cmd.split(" > ")[1].split(" && ")[0]
            data = b"".join(base64.b64decode(line) for line in self.files.pop(tmp).splitlines())
            if self.corrupt:
                data += b"x"
            self.files[remote] = data
            return f"{hashlib.md5(data).hexdigest()}  {remote}\n"
        raise AssertionError(f"unexpected command: {cmd}")
