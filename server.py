"""
Laptop Remote — web server.

Start it by double-clicking start.bat (or with the command:  py server.py ).
Stop it with Ctrl+C, by typing Q + Enter in its window, from the phone, or
by double-clicking stop.bat (which runs:  py server.py --stop ).
Uses only the Python standard library.
"""

import hashlib
import hmac
import ipaddress
import json
import locale
import mimetypes
import os
import queue
import secrets
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import actions

BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = (BASE_DIR / "web").resolve()
CONFIG_FILE = BASE_DIR / "config.ini"
DEVICES_FILE = BASE_DIR / "devices.json"

DEFAULT_PORT = 8765
MAX_TEXT_LENGTH = 5000
MAX_FAILURES = 5
LOCKOUT_SECONDS = 300
SHUTDOWN_DELAY_SECONDS = 5
LINK_MINUTES = 15
TAILSCALE_NETWORK = ipaddress.ip_network("100.64.0.0/10")


# ---------------------------------------------------------------------------
# Output to the server window. It goes through a separate thread, so the
# phone never waits for the window (e.g. while text is selected in it).
# ---------------------------------------------------------------------------

_messages = queue.Queue()


def _writer():
    while True:
        text = _messages.get()
        try:
            print(text, flush=True)
        except Exception:
            pass


def log(text):
    _messages.put(f"{time.strftime('%H:%M:%S')}  {text}")


# ---------------------------------------------------------------------------
# config.ini
# ---------------------------------------------------------------------------

def _ansi_encoding():
    """The "ANSI" code page Windows Notepad used for older files (e.g. cp1250 or cp1252)."""
    try:
        encoding = locale.getpreferredencoding(False) or ""
    except Exception:
        encoding = ""
    return "cp1252" if encoding.lower().replace("-", "") in ("", "utf8") else encoding


def _decode(data):
    """Return (text, encoding). Supports UTF-8 (with or without BOM), UTF-16 and ANSI."""
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16"), "utf-16"
    try:
        if data.startswith(b"\xef\xbb\xbf"):
            return data.decode("utf-8-sig"), "utf-8-sig"
        return data.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        encoding = _ansi_encoding()
        return data.decode(encoding, errors="replace"), encoding


def parse_ini(text):
    """
    Parse text in INI format. Return ({section: {name: value}}, [warnings]).
    Invalid lines are skipped with a warning instead of crashing the server.
    """
    sections, warnings, section = {}, [], None
    for number, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith((";", "#")):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip().lower()
            if section not in ("server", "programs"):
                warnings.append(f"line {number}: unknown section “{line}” (only [server] and [programs] exist)")
            sections.setdefault(section, {})
            continue
        name, equals, value = line.partition("=")
        name, value = name.strip(), value.strip()
        if section is None:
            warnings.append(f"line {number}: “{line}” is above the [server] or [programs] heading, skipped")
            continue
        if not equals or not name:
            warnings.append(f"line {number}: “{line}” is not in the form “name = value”, skipped")
            continue
        if name in sections[section]:
            warnings.append(f"line {number}: “{name}” appears more than once, the last line wins")
        sections[section][name] = value
    return sections, warnings


def _number(settings, key, default, low, high, warnings):
    value = settings.get(key, "")
    if not value:
        return default
    if value.isdigit() and low <= int(value) <= high:
        return int(value)
    warnings.append(f"{key} “{value}” must be a number from {low} to {high}, using {default}")
    return default


def _load_config():
    warnings = []
    try:
        text, _ = _decode(CONFIG_FILE.read_bytes())
    except FileNotFoundError:
        text = ""
        warnings.append("config.ini does not exist, default settings are used")
    except OSError as e:
        text = ""
        warnings.append(f"cannot read config.ini ({e})")
    sections, w = parse_ini(text)
    warnings += w

    srv = {k.lower(): v for k, v in sections.get("server", {}).items()}
    programs = {}
    for name, target in sections.get("programs", {}).items():
        if target:
            programs[name] = target
        else:
            warnings.append(f"“{name}” has no path or address after the = sign, skipped")

    return {
        "name": (srv.get("name") or socket.gethostname())[:40],
        "port": _number(srv, "port", DEFAULT_PORT, 1, 65535, warnings),
        "volume_step": _number(srv, "volume_step", 1, 1, 10, warnings),
        "forget_days": _number(srv, "forget_phones_after_days", 30, 0, 3650, warnings),
        "programs": programs,
        "warnings": warnings,
    }


_cache = {"signature": None, "data": None}
_cache_lock = threading.Lock()


def config(first_time=False):
    """Return the settings. The file is read again only when it changes (e.g. after Ctrl+S)."""
    try:
        st = CONFIG_FILE.stat()
        signature = (st.st_mtime_ns, st.st_size)
    except OSError:
        signature = None
    with _cache_lock:
        if _cache["data"] is not None and _cache["signature"] == signature:
            return _cache["data"]
        data = _load_config()
        changed = _cache["data"] is not None
        _cache["signature"], _cache["data"] = signature, data
    if changed and not first_time:
        log(f"config.ini changed — apps on the list: {len(data['programs'])}")
        for w in data["warnings"]:
            log(f"   WARNING in config.ini, {w}")
    return data


# ---------------------------------------------------------------------------
# Connected phones
#
# A phone connects with a link that works only once and only for a few
# minutes. The phone then gets its own secret key. The laptop stores only a
# fingerprint (hash) of that key in devices.json, so the file is of no use
# to anyone who copies it. Disconnecting a phone deletes its entry.
# ---------------------------------------------------------------------------

_devices = []
_devices_lock = threading.Lock()
_link_codes = {}  # code -> valid until (only in memory: links die when the remote stops)


def _fingerprint(key):
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def load_devices():
    global _devices
    try:
        data = json.loads(DEVICES_FILE.read_text(encoding="utf-8"))
        devices = [d for d in data.get("devices", []) if isinstance(d, dict) and d.get("key")]
    except FileNotFoundError:
        devices = []
    except (OSError, ValueError, AttributeError):
        print("  WARNING: devices.json could not be read, phones have to connect again.")
        devices = []
    with _devices_lock:
        _devices = devices


def _save_devices():
    """Call with _devices_lock held."""
    try:
        temp = DEVICES_FILE.with_suffix(".tmp")
        temp.write_text(json.dumps({"devices": _devices}, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(temp, DEVICES_FILE)
    except OSError as e:
        log(f"WARNING: cannot save devices.json ({e})")


def new_link_code():
    code = secrets.token_urlsafe(18)
    now = time.time()
    with _devices_lock:
        for old in [c for c, until in _link_codes.items() if until < now]:
            del _link_codes[old]
        _link_codes[code] = now + LINK_MINUTES * 60
    return code


def connect_device(code, name, via):
    """Use a link code. Return (key, device) or None if the link is not valid."""
    with _devices_lock:
        until = _link_codes.pop(code, None)  # a link works only once
        if not until or until < time.time():
            return None
        key = secrets.token_urlsafe(32)
        device = {
            "id": secrets.token_hex(4),
            "name": name,
            "via": via,
            "key": _fingerprint(key),
            "connected": time.time(),
            "last_used": time.time(),
        }
        _devices.append(device)
        _save_devices()
    return key, device


def find_device(key):
    if not key:
        return None
    fingerprint = _fingerprint(key)
    with _devices_lock:
        for device in _devices:
            if hmac.compare_digest(device["key"], fingerprint):
                if time.time() - device.get("last_used", 0) > 60:
                    device["last_used"] = time.time()
                    _save_devices()
                return device
    return None


def device_list():
    with _devices_lock:
        return [{k: d.get(k) for k in ("id", "name", "via", "connected", "last_used")} for d in _devices]


def forget_device(device_id):
    with _devices_lock:
        before = len(_devices)
        _devices[:] = [d for d in _devices if d["id"] != device_id]
        _save_devices()
        return before - len(_devices)


def forget_all_devices():
    with _devices_lock:
        count = len(_devices)
        _devices.clear()
        _link_codes.clear()  # links that were not used yet stop working too
        _save_devices()
        return count


def forget_unused_devices(days):
    if days <= 0:
        return []
    limit = time.time() - days * 86400
    with _devices_lock:
        old = [d["name"] for d in _devices if d.get("last_used", 0) < limit]
        if old:
            _devices[:] = [d for d in _devices if d.get("last_used", 0) >= limit]
            _save_devices()
        return old


# ---------------------------------------------------------------------------
# Network
# ---------------------------------------------------------------------------

def laptop_addresses():
    """The first address is the one the laptop uses to reach the network (usually Wi-Fi)."""
    addresses = []
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))  # nothing is sent, this only picks the network adapter
            addresses.append(s.getsockname()[0])
    except OSError:
        pass
    try:
        for a in socket.gethostbyname_ex(socket.gethostname())[2]:
            if a not in addresses and not a.startswith(("127.", "169.254.")):
                addresses.append(a)
    except OSError:
        pass
    return addresses or ["127.0.0.1"]


def is_tailscale(ip):
    try:
        return ipaddress.ip_address(ip) in TAILSCALE_NETWORK
    except ValueError:
        return False


def is_allowed_client(ip):
    """Only devices on the home (private) network, or on your Tailscale network, are allowed."""
    try:
        a = ipaddress.ip_address(ip)
        if a.version == 6 and a.ipv4_mapped:
            a = a.ipv4_mapped
        return a.is_private or a.is_loopback or a.is_link_local or a in TAILSCALE_NETWORK
    except ValueError:
        return False


def already_running(port):
    """True if something on this laptop already answers on the port (e.g. another copy of the remote)."""
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return True
    except OSError:
        return False


class RemoteServer(ThreadingHTTPServer):
    daemon_threads = True
    # On Windows, SO_REUSEADDR would let a second copy of the server listen on the
    # same port at the same time, without any error. Windows does not need it to
    # restart the server right away, so it is only used on other systems.
    allow_reuse_address = not actions.ON_WINDOWS


# ---------------------------------------------------------------------------
# Who is watching the screen (shown in the server window)
# ---------------------------------------------------------------------------

_viewers = {}  # device id -> (name, time of the last picture)
_viewers_lock = threading.Lock()


def _update_title():
    with _viewers_lock:
        watching = bool(_viewers)
    actions.set_window_title("Laptop Remote — SCREEN IS BEING VIEWED" if watching else "Laptop Remote")


def screen_viewed_by(device):
    with _viewers_lock:
        new = device["id"] not in _viewers
        _viewers[device["id"]] = (device["name"], time.time())
    if new:
        log(f"SCREEN VIEW started on {device['name']}")
        _update_title()


def _watch_viewers():
    while True:
        time.sleep(2)
        with _viewers_lock:
            gone = [(i, n) for i, (n, seen) in _viewers.items() if time.time() - seen > 6]
            for i, _ in gone:
                del _viewers[i]
        for _, name in gone:
            log(f"screen view stopped on {name}")
        if gone:
            _update_title()


def _forget_unused_regularly():
    while True:
        time.sleep(3600)
        days = config()["forget_days"]
        for name in forget_unused_devices(days):
            log(f"disconnected (not used for {days} days): {name}")


# ---------------------------------------------------------------------------
# Commands from the phone
# ---------------------------------------------------------------------------

MEDIA = {"previous": "Previous track", "play_pause": "Play / Pause", "next": "Next track"}
VOLUME = {"volume_down": "Volume down", "volume_up": "Volume up", "mute": "Mute on / off"}
QUIET = {"mouse_move", "scroll", "mouse_button"}  # too frequent to write into the window


def _fraction(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value <= 1:
        return float(value)
    raise ValueError("Invalid position.")


def _integer(value, low, high):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return max(low, min(high, int(value)))
    raise ValueError("Invalid number.")


def run_command(data, device, server):
    """Run a command and return a message for the phone. ValueError = bad request."""
    command = data.get("command")
    if not isinstance(command, str):
        raise ValueError("Missing command.")

    if command in MEDIA:
        actions.media_key(command)
        return MEDIA[command]

    if command in VOLUME:
        actions.volume(command, config()["volume_step"])
        return VOLUME[command]

    if command == "lock":
        actions.lock_screen()
        return "Screen locked"

    if command in ("shutdown", "restart"):
        if data.get("confirmed") is not True:
            raise ValueError("Confirmation on the phone is required.")
        if command == "shutdown":
            actions.shut_down(SHUTDOWN_DELAY_SECONDS)
            return f"Shutting down in {SHUTDOWN_DELAY_SECONDS} seconds"
        actions.restart(SHUTDOWN_DELAY_SECONDS)
        return f"Restarting in {SHUTDOWN_DELAY_SECONDS} seconds"

    if command == "open":
        name = data.get("name")
        programs = config()["programs"]
        if not isinstance(name, str) or name not in programs:
            raise ValueError(f"“{name}” is not on the list in config.ini. Refresh the page.")
        actions.open_target(programs[name])
        return f"Opening: {name}"

    if command == "type":
        text = data.get("text")
        if not isinstance(text, str) or not text:
            raise ValueError("The text is empty.")
        if len(text) > MAX_TEXT_LENGTH:
            raise ValueError(f"The text is too long (at most {MAX_TEXT_LENGTH} characters).")
        actions.type_text(text, data.get("enter") is True)
        return "Text typed"

    if command == "key":
        name = data.get("key")
        if name not in actions.SPECIAL_KEYS:
            raise ValueError("Unknown key.")
        actions.press_key(name)
        return "Key pressed"

    if command == "mouse_move":
        actions.mouse_move(_integer(data.get("dx", 0), -3000, 3000), _integer(data.get("dy", 0), -3000, 3000))
        return "Moved"

    if command == "click":
        button = data.get("button", "left")
        if button not in actions.MOUSE_BUTTONS:
            raise ValueError("Unknown mouse button.")
        x = y = None
        if data.get("x") is not None or data.get("y") is not None:
            x, y = _fraction(data.get("x")), _fraction(data.get("y"))
        actions.click(button, x, y, data.get("double") is True)
        return "Click"

    if command == "mouse_button":
        button = data.get("button", "left")
        if button not in actions.MOUSE_BUTTONS:
            raise ValueError("Unknown mouse button.")
        actions.mouse_button(button, data.get("pressed") is True)
        return "Holding the button" if data.get("pressed") is True else "Button released"

    if command == "scroll":
        actions.scroll(_integer(data.get("amount", 0), -2400, 2400), data.get("horizontal") is True)
        return "Scrolled"

    if command == "forget_me":
        forget_device(device["id"])
        return "This phone is disconnected"

    if command == "forget_all":
        if data.get("confirmed") is not True:
            raise ValueError("Confirmation on the phone is required.")
        count = forget_all_devices()
        return f"Disconnected phones: {count}"

    if command == "stop_remote":
        if data.get("confirmed") is not True:
            raise ValueError("Confirmation on the phone is required.")
        threading.Thread(target=server.shutdown, daemon=True).start()
        return "The remote on the laptop is stopping"

    raise ValueError(f"Unknown command: {command}")


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

_failures = {}  # ip -> (number of failed attempts, blocked until)
_failures_lock = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    server_version = "LaptopRemote/2.0"
    sys_version = ""
    protocol_version = "HTTP/1.1"  # keep the connection open: the mouse reacts faster
    timeout = 30

    def log_message(self, format, *args):
        pass  # we print our own, shorter log lines

    def _log(self, text):
        log(f"{self.client_address[0]:<15}  {text}")

    def _reply(self, status, body=b"", content_type="application/json; charset=utf-8", headers=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        try:
            self.send_response(status)
            if body or status != 204:
                self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            for name, value in (headers or {}).items():
                self.send_header(name, value)
            self.end_headers()
            if body:
                self.wfile.write(body)
        except OSError:
            self.close_connection = True  # the phone closed the connection

    # ---- checks ----

    def _client_allowed(self):
        if is_allowed_client(self.client_address[0]):
            return True
        self._log("REFUSED: device is not on the home network")
        self.close_connection = True
        self._reply(403, {"error": "Access is allowed only from the home network or your Tailscale network."})
        return False

    def _blocked(self):
        """Seconds this device still has to wait after too many failed attempts (0 = none)."""
        with _failures_lock:
            _, until = _failures.get(self.client_address[0], (0, 0))
        return int(until - time.time()) + 1 if until > time.time() else 0

    def _failed(self, what):
        ip = self.client_address[0]
        with _failures_lock:
            count, _ = _failures.get(ip, (0, 0))
            count += 1
            if count >= MAX_FAILURES:
                _failures[ip] = (0, time.time() + LOCKOUT_SECONDS)
                self._log(f"WARNING: {count} failed attempts, device blocked for {LOCKOUT_SECONDS // 60} min")
            else:
                _failures[ip] = (count, 0)
                self._log(what)

    def _device(self):
        """The connected phone making this request, or None (and an error reply)."""
        wait = self._blocked()
        if wait:
            self._reply(429, {"error": f"Too many failed attempts. Wait {wait} s and try again."})
            return None
        device = find_device(self.headers.get("X-Key", ""))
        if device:
            with _failures_lock:
                _failures.pop(self.client_address[0], None)
            return device
        self._failed("unknown phone (not connected, or disconnected)")
        self._reply(401, {"error": "This phone is not connected to this laptop."})
        return None

    # ---- GET ----

    def do_GET(self):
        try:
            self._get()
        except Exception as e:
            self._unexpected_error(e)

    def _get(self):
        if not self._client_allowed():
            return
        url = urlsplit(self.path)
        path = url.path

        if path == "/api/check":
            device = self._device()
            if device:
                c = config()
                self._reply(200, {"ok": True, "laptop": c["name"], "phone": device["name"], "phone_id": device["id"],
                                  "test_mode": actions.TEST_MODE, "screen": list(actions.screen_size())})
            return

        if path == "/api/programs":
            if self._device():
                c = config()
                self._reply(200, {"programs": list(c["programs"]), "warnings": c["warnings"]})
            return

        if path == "/api/phones":
            if self._device():
                self._reply(200, {"phones": device_list(), "forget_days": config()["forget_days"]})
            return

        if path == "/api/screen":
            device = self._device()
            if device:
                self._screen(device, parse_qs(url.query))
            return

        # The phone page (files from the web folder)
        if path in ("", "/"):
            path = "/index.html"
        try:
            file = (WEB_DIR / path.lstrip("/")).resolve()
            exists = WEB_DIR in file.parents and file.is_file()
        except (OSError, ValueError):
            exists = False
        if not exists:
            self._reply(404, {"error": "Not found."})
            return
        content_type = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type in ("application/javascript", "application/json",
                                                                 "image/svg+xml"):
            content_type += "; charset=utf-8"
        self._reply(200, file.read_bytes(), content_type)

    def _screen(self, device, query):
        try:
            max_width = max(320, min(3840, int(query.get("w", ["1280"])[0])))
        except ValueError:
            max_width = 1280
        last = query.get("last", [""])[0]
        screen_viewed_by(device)
        try:
            pixels, width, height = actions.capture_screen(max_width)
        except actions.ActionError as e:
            self._reply(503, {"error": str(e)})
            return
        frame = f"{zlib.crc32(pixels) & 0xFFFFFFFF:08x}-{width}x{height}"
        headers = {"X-Frame": frame}
        cursor = actions.cursor_position()
        if cursor:
            headers["X-Cursor"] = f"{cursor[0]:.4f},{cursor[1]:.4f}"
        if last == frame:
            self._reply(204, headers=headers)  # the picture did not change
            return
        self._reply(200, actions.encode_png(pixels, width, height), "image/png", headers)

    # ---- POST ----

    def do_POST(self):
        try:
            self._post()
        except Exception as e:
            self._unexpected_error(e)

    def _post(self):
        if not self._client_allowed():
            return
        # The request body is read first, so the reply always reaches the phone.
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = -1
        if not 0 <= length <= 100_000:
            self.close_connection = True
            self._reply(400, {"error": "Invalid request."})
            return
        raw = self.rfile.read(length) if length else b""
        path = urlsplit(self.path).path

        if path == "/api/local/stop":
            # Used by stop.bat on this laptop. The header makes sure no website can do it.
            port = self.server.server_address[1]
            if (self.client_address[0] == "127.0.0.1" and self.headers.get("X-Local-Stop") == "1"
                    and self.headers.get("Host") == f"127.0.0.1:{port}"):
                self._reply(200, {"ok": True})
                log("stop.bat asked the remote to stop")
                threading.Thread(target=self.server.shutdown, daemon=True).start()
            else:
                self._reply(403, {"error": "Not allowed."})
            return

        if path not in ("/api/connect", "/api/command"):
            self._reply(404, {"error": "Not found."})
            return
        try:
            data = json.loads(raw.decode("utf-8") or "{}")
            if not isinstance(data, dict):
                raise ValueError
        except ValueError:
            self._reply(400, {"error": "Invalid request."})
            return

        if path == "/api/connect":
            self._connect(data)
            return

        device = self._device()
        if not device:
            return
        command = data.get("command")
        try:
            message = run_command(data, device, self.server)
        except ValueError as e:
            self._log(f"refused ({command}): {e}")
            self._reply(400, {"error": str(e)})
            return
        except actions.ActionError as e:
            self._log(f"FAILED ({command}): {e}")
            self._reply(500, {"error": str(e)})
            return
        self._reply(200, {"ok": True, "message": message})
        if command in ("forget_me", "forget_all", "stop_remote"):
            self._log(f"{device['name']}: {message}")
        elif command not in QUIET:
            extra = f" → {data.get('name')}" if command == "open" else ""
            if command == "key":
                extra = f" → {data.get('key')}"
            if command == "click":
                extra = f" → {data.get('button', 'left')}"
            if actions.TEST_MODE:
                extra += "   [test mode, nothing was executed]"
            self._log(f"{device['name']}: {command}{extra}")

    def _connect(self, data):
        code = data.get("code")
        name = data.get("name")
        name = name.strip()[:40] if isinstance(name, str) and name.strip() else "Phone"
        result = connect_device(code, name, self.headers.get("Host", "")[:60]) if isinstance(code, str) else None
        if result:
            key, device = result
            with _failures_lock:
                _failures.pop(self.client_address[0], None)
            log(f"PHONE CONNECTED: {device['name']} (via {device['via']})")
            self._reply(200, {"ok": True, "key": key, "laptop": config()["name"], "phone": device["name"]})
            return
        wait = self._blocked()
        if wait:
            self._reply(429, {"error": f"Too many failed attempts. Wait {wait} s and try again."})
            return
        self._failed("a phone used a link that is not valid")
        self._reply(400, {"error": "This link has expired or was already used. "
                                   "On the laptop, type L and press Enter for a new link."})

    def _unexpected_error(self, e):
        self._log(f"UNEXPECTED ERROR: {type(e).__name__}: {e}")
        self.close_connection = True
        self._reply(500, {"error": f"Error on the laptop: {e}"})


# ---------------------------------------------------------------------------
# The server window: links, commands, stopping
# ---------------------------------------------------------------------------

LINE = "=" * 66


def print_link(port):
    """Create a new one-time link for a phone, print it and put it on the clipboard."""
    code = new_link_code()
    addresses = laptop_addresses()
    links = [f"http://{a}:{port}/#connect={code}" for a in addresses]
    copied = actions.copy_to_clipboard(links[0])
    print(f"\n  To connect a phone, open this link on it (it works once, for {LINK_MINUTES} minutes):\n")
    print(f"      {links[0]}\n")
    if len(links) > 1:
        print("  If that address does not work on the phone, use one of these:")
        for a, link in zip(addresses[1:], links[1:]):
            print(f"      {link}" + ("   (Tailscale)" if is_tailscale(a) else ""))
        print()
    if copied:
        print("  The link is already copied: paste it (Ctrl+V) into an e-mail or a message")
        print("  to yourself, and open it on your phone.")
    else:
        print("  Send this link to yourself (e-mail, Viber, WhatsApp...) and open it on your phone.")
    print(flush=True)


def print_commands():
    print("  Type a letter here and press Enter:")
    print("      L   new link for a phone")
    print("      D   disconnect all phones (their access stops working)")
    print("      Q   stop the remote")
    print(flush=True)


def _console_commands(server, port):
    while True:
        try:
            line = input()
        except (EOFError, OSError, ValueError, KeyboardInterrupt):
            return  # no keyboard (e.g. started without a window), or Ctrl+C
        command = line.strip().lower()
        if command == "l":
            print_link(port)
        elif command == "d":
            count = forget_all_devices()
            print(f"\n  Disconnected phones: {count}. Their access does not work any more.")
            print("  To connect a phone again, type L and press Enter.\n", flush=True)
        elif command == "q":
            print("\n  Stopping...", flush=True)
            threading.Thread(target=server.shutdown, daemon=True).start()
            return
        elif command:
            print()
            print_commands()


def stop_running_copy(port):
    """Stop the remote that is running on this laptop (used by stop.bat)."""
    if not already_running(port):
        print("\n  The remote is not running.")
        return 0
    try:  # ask it nicely first
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        request = urllib.request.Request(f"http://127.0.0.1:{port}/api/local/stop", data=b"",
                                         method="POST", headers={"X-Local-Stop": "1"})
        opener.open(request, timeout=3).read()
        for _ in range(20):
            time.sleep(0.25)
            if not already_running(port):
                break
    except Exception:
        pass
    if already_running(port) and actions.ON_WINDOWS:
        # An older version or a stuck copy: end every program listening on the port.
        output = subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True,
                                errors="replace").stdout
        for line in output.splitlines():
            parts = line.split()
            if len(parts) >= 5 and parts[1].endswith(f":{port}") and parts[2] in ("0.0.0.0:0", "[::]:0"):
                subprocess.run(["taskkill", "/F", "/PID", parts[-1]], capture_output=True)
        time.sleep(1)
    if already_running(port):
        print(f"\n  Could not stop the program on port {port}. Close its window, or use")
        print("  Task Manager (Ctrl+Shift+Esc): click Python, then End task.")
        return 1
    print("\n  The remote is stopped.")
    return 0


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    data = config(first_time=True)
    port = data["port"]
    if "--stop" in sys.argv[1:]:
        return stop_running_copy(port)

    actions.make_dpi_aware()
    actions.disable_quickedit()
    if already_running(port):
        print(f"\nERROR: the remote is already running on this laptop (port {port}).")
        print("Use the window (or VS Code terminal) where it is already running,")
        print("or stop it first: Ctrl+C in that window, or double-click stop.bat.")
        return 1
    try:
        server = RemoteServer(("0.0.0.0", port), Handler)
    except OSError as e:
        print(f"\nERROR: the server cannot start on port {port} ({e}).")
        print("Another program is using this port. Close it, or change the port number in config.ini.")
        return 1

    load_devices()
    forgotten = forget_unused_devices(data["forget_days"])
    phones = device_list()
    addresses = laptop_addresses()

    print(LINE)
    print(f"  LAPTOP REMOTE — running on “{data['name']}”")
    print(LINE)
    for name in forgotten:
        print(f"  Disconnected (not used for {data['forget_days']} days): {name}")
    if phones:
        print(f"  Connected phones: {', '.join(p['name'] for p in phones)}")
        print(f"  They can simply open:  http://{addresses[0]}:{port}")
    else:
        print("  No phone is connected to this laptop yet.")
        print_link(port)
    print(f"  Apps on the list: {len(data['programs'])} (the list is in config.ini)")
    for w in data["warnings"]:
        print(f"  WARNING in config.ini, {w}")
    if actions.TEST_MODE:
        print("\n  TEST MODE: this is not Windows, commands are only logged.")
    print(LINE)
    print_commands()
    print("  Keep this window open while you use the remote (you can minimize it).")
    print("  To stop: type Q and Enter, press Ctrl+C, close the window, or run stop.bat.")
    print(LINE + "\n", flush=True)

    threading.Thread(target=_writer, daemon=True).start()
    threading.Thread(target=_watch_viewers, daemon=True).start()
    threading.Thread(target=_forget_unused_regularly, daemon=True).start()
    threading.Thread(target=_console_commands, args=(server, port), daemon=True).start()
    actions.set_window_title("Laptop Remote")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    print("\nThe remote has stopped. Phones stay connected for the next time you start it.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
