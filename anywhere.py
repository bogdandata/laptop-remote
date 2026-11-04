"""
Control from anywhere: the laptop connects OUT to the internet, so it works on
any network (5G, another country, behind any router), and everything between
the phone and the laptop is end-to-end encrypted.

  phone/laptop browser  ──https──►  Cloudflare tunnel  ──►  this laptop
  (app on GitHub Pages)             (sees only locked data)

- Tunnel: Cloudflare's free "quick tunnel" (cloudflared.exe, downloaded once from
  Cloudflare's official GitHub page). It gives the laptop a public https address
  that changes every time it starts.
- Finding the laptop: the laptop leaves an encrypted note with its current address
  on a free message service (ntfy.sh). The phone reads it and opens it with its key.
- Every request and answer is locked with AES-256-GCM (remote_crypto.py). Cloudflare
  and ntfy see only locked data. Each phone has its own key; disconnecting a phone
  deletes its key.
- New phone: an invitation link that contains only the phone's PUBLIC key. The
  laptop asks "Allow …?" (or the person types the invitation into the window), then
  locks the access keys for that phone only and leaves them on the message service.
"""

import hashlib
import json
import os
import platform
import re
import secrets
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import remote_crypto as rc

VERSION = 1
APP_URL = "https://bogdandata.github.io/laptop-remote/"
DEFAULT_RELAY = "https://ntfy.sh"
INVITE_DAYS = 7
CLOCK_WINDOW_MS = 10 * 60 * 1000
POINTER_EVERY_SECONDS = 3 * 3600
CLOUDFLARED_URL = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-{arch}.exe"
TUNNEL_URL = re.compile(r"https://[-a-z0-9]+\.trycloudflare\.com")

REQUEST_INFO = b"laptop-remote v3 request"
RESPONSE_INFO = b"laptop-remote v3 response"
INVITE_INFO = b"laptop-remote v3 invite"

TEST_MODE = os.name != "nt"


def _test_env(name):
    """Settings used only by the tests on other systems (never on Windows)."""
    return os.environ.get(name) if TEST_MODE else None


class AnywhereError(Exception):
    """Shown to the user."""


# ---------------------------------------------------------------------------
# Message service (ntfy): tiny encrypted notes, by topic
# ---------------------------------------------------------------------------

_opener = urllib.request.build_opener()


def relay_publish(relay, topic, message, timeout=20):
    request = urllib.request.Request(f"{relay.rstrip('/')}/{topic}", data=message.encode("ascii"), method="POST",
                                     headers={"Content-Type": "text/plain", "User-Agent": "LaptopRemote"})
    with _opener.open(request, timeout=timeout) as response:
        response.read()


def relay_poll(relay, topic, since="12h", timeout=20):
    """All cached messages of a topic (newest last)."""
    url = f"{relay.rstrip('/')}/{topic}/json?poll=1&since={urllib.parse.quote(since)}"
    request = urllib.request.Request(url, headers={"User-Agent": "LaptopRemote"})
    with _opener.open(request, timeout=timeout) as response:
        lines = response.read().decode("utf-8", "replace").splitlines()
    messages = []
    for line in lines:
        try:
            item = json.loads(line)
        except ValueError:
            continue
        if item.get("event") == "message" and isinstance(item.get("message"), str):
            messages.append(item["message"])
    return messages


# ---------------------------------------------------------------------------
# Encrypted requests from the app
#
# Request body:  1 byte version | 8 bytes device id | nonce + ciphertext + tag
# Inside:        {"m": "GET"/"POST", "p": "/api/...", "b": {...}, "t": ms, "r": request id}
# Answer:        nonce + ciphertext + tag of  4-byte length | {"s","c","h","r"} | body bytes
# ---------------------------------------------------------------------------

def device_keys(secret):
    return rc.hkdf(secret, REQUEST_INFO), rc.hkdf(secret, RESPONSE_INFO)


class ReplayGuard:
    """Refuses a request that was already used (someone could try to send a copy again)."""

    def __init__(self):
        self._seen = {}
        self._lock = threading.Lock()

    def check(self, device_id, request_id, sent_ms):
        now = time.time() * 1000
        if abs(now - sent_ms) > CLOCK_WINDOW_MS:
            raise AnywhereError("The clock of the phone and of the laptop differ by more than 10 minutes. "
                                "Set both to the right time (automatic time).")
        key = (device_id, request_id)
        with self._lock:
            for old in [k for k, t in self._seen.items() if now - t > 2 * CLOCK_WINDOW_MS]:
                del self._seen[old]
            if key in self._seen:
                raise AnywhereError("This request was already used.")
            self._seen[key] = now


def open_request(raw, secret_for_device, guard):
    """Return (device id, request) or raise rc.CryptoError / AnywhereError."""
    if len(raw) < 1 + 8 + rc.NONCE_SIZE + rc.TAG_SIZE or raw[0] != VERSION:
        raise rc.CryptoError("not a request of Laptop Remote")
    device_id = raw[1:9].hex()
    secret = secret_for_device(device_id)
    if secret is None:
        raise rc.CryptoError("unknown device")
    request_key, _ = device_keys(secret)
    plain = rc.decrypt(request_key, raw[9:], aad=b"lr3-req" + raw[1:9])
    request = json.loads(plain.decode("utf-8"))
    if not isinstance(request, dict) or not isinstance(request.get("r"), str) or not isinstance(request.get("t"), (int, float)):
        raise rc.CryptoError("broken request")
    guard.check(device_id, request["r"], request["t"])
    return device_id, request


def seal_response(secret, device_id, request_id, status, body, content_type, headers=None):
    header = json.dumps({"s": status, "c": content_type, "h": headers or {}, "r": request_id}).encode("utf-8")
    payload = len(header).to_bytes(4, "big") + header + body
    _, response_key = device_keys(secret)
    return rc.encrypt(response_key, payload, aad=b"lr3-resp" + bytes.fromhex(device_id) + request_id.encode("ascii"))


# ---------------------------------------------------------------------------
# Invitations
# ---------------------------------------------------------------------------

def parse_invite(text):
    """
    An invitation is a link like  https://…/setup.html#i=TOKEN  (or just the TOKEN).
    TOKEN = base64url of {"v":1, "pk": phone public key, "x": inbox topic, "n": phone name,
                          "r": message service, "t": created (unix time)}.
    """
    text = (text or "").strip()
    match = re.search(r"[#?&]i=([A-Za-z0-9_-]+)", text)
    token = match.group(1) if match else text
    try:
        invite = json.loads(rc.unb64(token).decode("utf-8"))
        public_key = rc.unb64(invite["pk"])
        inbox = str(invite["x"])
        name = str(invite.get("n") or "Phone").strip()[:40] or "Phone"
        relay = str(invite.get("r") or DEFAULT_RELAY)
        created = float(invite.get("t") or 0)
    except (ValueError, KeyError, TypeError, AttributeError):
        raise AnywhereError("This is not a Laptop Remote invitation. Copy the whole link from the e-mail.")
    if not re.fullmatch(r"[A-Za-z0-9_-]{16,64}", inbox):
        raise AnywhereError("This invitation is broken. Make a new one in the app.")
    if not (relay.startswith("https://") or (TEST_MODE and relay.startswith("http://127.0.0.1"))):
        raise AnywhereError("This invitation is broken. Make a new one in the app.")
    if created and time.time() - created > INVITE_DAYS * 86400:
        raise AnywhereError(f"This invitation is older than {INVITE_DAYS} days. Make a new one in the app.")
    return {"public_key": public_key, "inbox": inbox, "name": name, "relay": relay, "token": token}


def seal_announcement(app_public_key, payload):
    """Lock the access keys so that only the phone that made the invitation can open them."""
    laptop_public_key, shared = rc.ecdh_shared_secret(app_public_key)
    key = rc.hkdf(shared, INVITE_INFO)
    locked = rc.encrypt(key, json.dumps(payload).encode("utf-8"), aad=b"lr3-ann")
    return f"lr3a.{rc.b64(laptop_public_key)}.{rc.b64(locked)}"


# ---------------------------------------------------------------------------
# The tunnel (Cloudflare quick tunnel)
# ---------------------------------------------------------------------------

def _cloudflared_arch():
    machine = platform.machine().lower()
    if machine in ("x86", "i386", "i686"):
        return "386"
    return "amd64"  # also on ARM64 Windows, which runs it through emulation


def _end_together_with_this_program(process):
    """
    Windows: put the child into a "job" that ends it when this program ends, however it
    ends (window closed, Task Manager, crash). Returns the job handle, which must stay open.
    """
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class IoCounters(ctypes.Structure):
            _fields_ = [(name, ctypes.c_ulonglong) for name in (
                "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

        class BasicLimits(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_longlong), ("PerJobUserTimeLimit", ctypes.c_longlong),
                        ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                        ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                        ("SchedulingClass", wintypes.DWORD)]

        class ExtendedLimits(ctypes.Structure):
            _fields_ = [("BasicLimitInformation", BasicLimits), ("IoInfo", IoCounters),
                        ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                        ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        kernel32.CreateJobObjectW.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR)
        kernel32.SetInformationJobObject.restype = wintypes.BOOL
        kernel32.SetInformationJobObject.argtypes = (wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD)
        kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
        kernel32.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
        job = kernel32.CreateJobObjectW(None, None)
        if not job:
            return None
        limits = ExtendedLimits()
        limits.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not kernel32.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            return None  # 9 = JobObjectExtendedLimitInformation
        if not kernel32.AssignProcessToJobObject(job, int(process._handle)):
            return None
        return job
    except Exception:
        return None  # not important: the next start ends a leftover cloudflared anyway


class Tunnel:
    def __init__(self, port, folder, on_url, log):
        self.port, self.folder, self.on_url, self.log = port, Path(folder), on_url, log
        self.url = None
        self._process = None
        self._job = None
        self._stopping = False
        self.pid_file = self.folder / "cloudflared.pid"

    @property
    def program(self):
        return self.folder / "cloudflared.exe"

    def _download(self):
        url = CLOUDFLARED_URL.format(arch=_cloudflared_arch())
        self.log("Anywhere: downloading cloudflared (Cloudflare's official tunnel program, once)...")
        part = self.program.with_suffix(".part")
        request = urllib.request.Request(url, headers={"User-Agent": "LaptopRemote"})
        with _opener.open(request, timeout=120) as response, open(part, "wb") as out:
            total = int(response.headers.get("Content-Length") or 0)
            done, shown = 0, 0
            while True:
                chunk = response.read(256 * 1024)
                if not chunk:
                    break
                out.write(chunk)
                done += len(chunk)
                if total and done * 10 // total > shown:
                    shown = done * 10 // total
                    self.log(f"Anywhere: downloading cloudflared... {shown * 10}%")
        if done < 1_000_000:
            part.unlink(missing_ok=True)
            raise AnywhereError("The download of cloudflared was incomplete.")
        os.replace(part, self.program)
        self.log("Anywhere: cloudflared downloaded.")

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        fake = _test_env("LAPTOP_REMOTE_TEST_TUNNEL")
        if fake:  # tests: pretend the tunnel address is the laptop itself
            self.url = fake
            self.on_url(fake)
            return
        delay = 5
        while not self._stopping:
            try:
                if not self.program.exists():
                    self._download()
                self._run_once()
                delay = 5
            except Exception as e:
                self.log(f"Anywhere: the tunnel is not working ({e}). Trying again in {delay} s.")
            if self._stopping:
                return
            time.sleep(delay)
            delay = min(delay * 2, 300)

    def _run_once(self):
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self._process = subprocess.Popen(
            [str(self.program), "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{self.port}"],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL,
            text=True, errors="replace", creationflags=flags)
        self._job = _end_together_with_this_program(self._process)
        try:
            self.pid_file.write_text(str(self._process.pid))
        except OSError:
            pass
        for line in self._process.stderr:
            found = TUNNEL_URL.search(line)
            if found and found.group(0) != self.url:
                self.url = found.group(0)
                self.on_url(self.url)
        self._process.wait()
        self.url = None
        if not self._stopping:
            raise AnywhereError(f"cloudflared stopped (code {self._process.returncode})")

    def stop(self):
        self._stopping = True
        if self._process and self._process.poll() is None:
            try:
                self._process.terminate()
                self._process.wait(timeout=5)
            except Exception:
                pass
        try:
            self.pid_file.unlink()
        except OSError:
            pass


def kill_leftover_tunnel(folder):
    """End a cloudflared that an earlier, stopped copy of the remote may have left running."""
    pid_file = Path(folder) / "cloudflared.pid"
    try:
        pid = int(pid_file.read_text().strip())
    except (OSError, ValueError):
        return
    if os.name == "nt":
        listing = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                                 capture_output=True, text=True, errors="replace").stdout.lower()
        if "cloudflared" in listing:  # make sure it is really cloudflared, not another program
            subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
    try:
        pid_file.unlink()
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Everything together
# ---------------------------------------------------------------------------

class Anywhere:
    """
    port, folder        where the remote runs
    settings()          -> dict with "name" and "relay"
    devices             object with add(device), secret(device_id) -> bytes|None
    log(text)           write a line into the remote's window
    ask(title, text)    Yes/No question on the laptop -> bool
    """

    def __init__(self, port, folder, settings, devices, log, ask):
        self.port, self.folder = port, Path(folder)
        self.settings, self.devices, self.log, self.ask = settings, devices, log, ask
        self.state_file = self.folder / "anywhere.json"
        self.invite_file = self.folder / "invite.txt"
        self.state = self._load_state()
        self.guard = ReplayGuard()
        self.tunnel = Tunnel(port, folder, self._tunnel_ready, log)
        self._last_pointer = 0
        self._lock = threading.Lock()

    # ---- state ----

    def _load_state(self):
        try:
            state = json.loads(self.state_file.read_text(encoding="utf-8"))
            rc.unb64(state["pointer_key"])
            if state.get("laptop_id") and state.get("topic"):
                return state
        except (OSError, ValueError, KeyError, TypeError):
            pass
        state = {"laptop_id": secrets.token_hex(8), "topic": "lr" + rc.b64(secrets.token_bytes(18)),
                 "pointer_key": rc.b64(rc.new_key())}
        self._save_state(state)
        return state

    def _save_state(self, state):
        temp = self.state_file.with_suffix(".tmp")
        temp.write_text(json.dumps(state, indent=2), encoding="utf-8")
        os.replace(temp, self.state_file)

    @property
    def relay(self):
        return _test_env("LAPTOP_REMOTE_TEST_RELAY") or self.settings().get("relay") or DEFAULT_RELAY

    # ---- start / stop ----

    def start(self):
        kill_leftover_tunnel(self.folder)
        self.tunnel.start()
        threading.Thread(target=self._refresh_pointer_regularly, daemon=True).start()

    def stop(self):
        self.tunnel.stop()

    @property
    def url(self):
        return self.tunnel.url

    # ---- the encrypted note with the current address ----

    def _tunnel_ready(self, url):
        self.log(f"Anywhere: ON — reachable through an encrypted tunnel ({url})")
        self.publish_pointer()
        if self.invite_file.exists():
            threading.Thread(target=self._use_invite_file, daemon=True).start()

    def pointer_message(self, url):
        state = self.state
        note = json.dumps({"u": url, "t": time.time(), "id": state["laptop_id"]}).encode("utf-8")
        locked = rc.encrypt(rc.unb64(state["pointer_key"]), note, aad=b"lr3-ptr" + state["laptop_id"].encode("ascii"))
        return "lr3p." + rc.b64(locked)

    def publish_pointer(self):
        url = self.url
        if not url:
            return False
        try:
            relay_publish(self.relay, self.state["topic"], self.pointer_message(url))
            self._last_pointer = time.time()
            return True
        except Exception as e:
            self.log(f"Anywhere: could not leave the address note on {self.relay} ({e}). Trying again later.")
            return False

    def _refresh_pointer_regularly(self):
        while True:
            time.sleep(60)
            if self.url and time.time() - self._last_pointer > (POINTER_EVERY_SECONDS if self._last_pointer else 60):
                self.publish_pointer()
            self._repeat_answers()

    # ---- invitations ----

    @staticmethod
    def _invite_id(invite):
        return rc.b64(hashlib.sha256(invite["token"].encode("ascii")).digest()[:12])

    def was_used(self, invite):
        return self._invite_id(invite) in self.state.get("used_invites", [])

    def _use_invite_file(self):
        try:
            text = self.invite_file.read_text(encoding="utf-8")
        except OSError:
            return
        try:
            invite = parse_invite(text)
        except AnywhereError as e:
            self.log(f"Anywhere: the invitation from the installer cannot be used: {e}")
            self._remove_invite_file()
            return
        if self.was_used(invite):  # e.g. the setup file was started again
            self.log(f"Anywhere: the invitation from “{invite['name']}” was already used. Nothing to do.")
            self._remove_invite_file()
            return
        question = (f"Allow “{invite['name']}” to control this laptop from anywhere?\n\n"
                    "It will be able to see the screen, use the mouse and the keyboard, open programs,\n"
                    "and shut down or restart the laptop.\n\n"
                    "Choose Yes only if you know this person and you started Laptop Remote for them.\n"
                    "You can take the access away at any time (type D in the Laptop Remote window).")
        if self.ask("Laptop Remote — allow access?", question):
            try:
                self.accept_invite(invite, approved_by="the person at this laptop")
            except Exception as e:
                self.log(f"Anywhere: the invitation could not be used ({e}). It is kept; restart the remote to try again.")
                return
            self.log("Done. You can minimize this window. Do not close it: that stops Laptop Remote "
                     "until you sign in to Windows again.")
        else:
            self.log(f"Anywhere: access for “{invite['name']}” was NOT allowed.")
        self._remove_invite_file()

    def _remove_invite_file(self):
        try:
            self.invite_file.unlink()
        except OSError:
            pass

    def accept_invite(self, invite, approved_by):
        """Give the phone of the invitation its own key and leave it (locked for that phone only)."""
        if self.was_used(invite):
            raise AnywhereError(f"This invitation was already used: “{invite['name']}” has access. "
                                "For another device, make a new invitation in the app.")
        if not self.url:
            raise AnywhereError("The tunnel is not ready yet. Wait a few seconds and try again.")
        device_id = secrets.token_hex(8)
        secret = rc.new_key()
        state = self.state
        payload = {"v": VERSION, "id": state["laptop_id"], "name": self.settings().get("name") or "Laptop",
                   "dev": device_id, "s": rc.b64(secret), "pk": state["pointer_key"], "pt": state["topic"],
                   "relay": self.relay, "u": self.url, "t": time.time()}
        message = seal_announcement(invite["public_key"], payload)
        relay_publish(invite["relay"], invite["inbox"], message)
        self.devices.add({"id": device_id, "name": invite["name"], "via": "anywhere", "kind": "anywhere",
                          "secret": rc.b64(secret), "connected": time.time(), "last_used": time.time()})
        # The message service keeps messages only for some hours. Until the phone uses its
        # access for the first time, the laptop leaves the (same, locked) answer again now and then.
        with self._lock:
            pending = [p for p in self.state.get("pending", []) if time.time() - p["t"] < INVITE_DAYS * 86400]
            pending.append({"dev": device_id, "relay": invite["relay"], "inbox": invite["inbox"],
                            "message": message, "t": time.time(), "sent": time.time()})
            self.state["pending"] = pending
            self.state["used_invites"] = (self.state.get("used_invites", []) + [self._invite_id(invite)])[-200:]
            self._save_state(self.state)
        self.log(f"PHONE CONNECTED (anywhere): {invite['name']} — allowed by {approved_by}")
        return device_id

    def _repeat_answers(self):
        with self._lock:
            pending = self.state.get("pending", [])
            keep = []
            for item in pending:
                device = self.devices.get(item["dev"])
                if not device or device.get("used") or time.time() - item["t"] > INVITE_DAYS * 86400:
                    continue  # used, disconnected or too old
                if time.time() - item["sent"] > 6 * 3600:
                    try:
                        relay_publish(item["relay"], item["inbox"], item["message"])
                        item["sent"] = time.time()
                    except Exception:
                        pass
                keep.append(item)
            if keep != pending:
                self.state["pending"] = keep
                self._save_state(self.state)

    # ---- encrypted requests ----

    def secret_for_device(self, device_id):
        return self.devices.secret(device_id)

    def mark_used(self, device_id):
        """The phone has used its access: no need to repeat its answer any more."""
        self.devices.mark_used(device_id)
