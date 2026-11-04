"""
Laptop Remote — web server.

Start it by double-clicking start.bat (or with the command:  py server.py ).
Stop it with Ctrl+C, by typing Q + Enter in its window, from the phone, or
by double-clicking stop.bat (which runs:  py server.py --stop ).
Uses only the Python standard library.

Installed from an invitation (setup.html), it is started by run.bat with
--anywhere-only: then it listens only on this laptop itself (127.0.0.1) and is
reachable only through the encrypted tunnel (control from anywhere).
"""

import hashlib
import hmac
import io
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
import zipfile
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import actions
import anywhere
import remote_crypto as rc

BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = (BASE_DIR / "docs").resolve()  # the phone page (also published on GitHub Pages)
CONFIG_FILE = BASE_DIR / "config.ini"
DEVICES_FILE = BASE_DIR / "devices.json"

VERSION = "3.0"
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
        "forget_days_anywhere": _number(srv, "forget_anywhere_after_days", 180, 0, 3650, warnings),
        "tailscale_auto": srv.get("tailscale_auto_connect", "yes").strip().lower() not in ("no", "0", "false", "off"),
        "anywhere": srv.get("anywhere", "yes").strip().lower() not in ("no", "0", "false", "off"),
        "keep_awake": srv.get("keep_awake", "yes").strip().lower() not in ("no", "0", "false", "off"),
        "relay": (srv.get("relay") or anywhere.DEFAULT_RELAY).strip(),
        "app_url": (srv.get("app_url") or anywhere.APP_URL).strip(),
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
        devices = [d for d in data.get("devices", []) if isinstance(d, dict) and (d.get("key") or d.get("secret"))]
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


CODE_LETTERS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no I, O, 0, 1: easy to read and type


def normalize_code(text):
    """Turn what the user typed (or the link) into the stored form: capitals, no dashes or spaces."""
    return "".join(ch for ch in str(text).upper() if ch.isalnum())


def new_link_code():
    """A new one-time code for connecting a phone, e.g. "K7PQ-4XMZ" (works once, for 15 minutes)."""
    code = "".join(secrets.choice(CODE_LETTERS) for _ in range(8))
    now = time.time()
    with _devices_lock:
        for old in [c for c, until in _link_codes.items() if until < now]:
            del _link_codes[old]
        _link_codes[code] = now + LINK_MINUTES * 60
    return f"{code[:4]}-{code[4:]}"


def connect_device(code, name, via):
    """Use a code (typed, or from a link). Return (key, device) or None if it is not valid."""
    with _devices_lock:
        until = _link_codes.pop(normalize_code(code), None)  # a code works only once
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
            if device.get("key") and hmac.compare_digest(device["key"], fingerprint):
                if time.time() - device.get("last_used", 0) > 60:
                    device["last_used"] = time.time()
                    _save_devices()
                return device
    return None


def device_list():
    with _devices_lock:
        return [{k: d.get(k) for k in ("id", "name", "via", "connected", "last_used", "kind")} for d in _devices]


class AnywhereDevices:
    """The connected-phones list, as the anywhere module needs it."""

    @staticmethod
    def add(device):
        with _devices_lock:
            _devices.append(device)
            _save_devices()

    @staticmethod
    def secret(device_id):
        with _devices_lock:
            for device in _devices:
                if device["id"] == device_id and device.get("secret"):
                    if time.time() - device.get("last_used", 0) > 60:
                        device["last_used"] = time.time()
                        _save_devices()
                    return rc.unb64(device["secret"])
        return None

    @staticmethod
    def get(device_id):
        with _devices_lock:
            for device in _devices:
                if device["id"] == device_id:
                    return device
        return None

    @staticmethod
    def mark_used(device_id):
        with _devices_lock:
            for device in _devices:
                if device["id"] == device_id and not device.get("used"):
                    device["used"] = True
                    _save_devices()


ANYWHERE = None  # the Anywhere object, when control from anywhere is on
ONLY_ANYWHERE = False  # installed from an invitation: nothing listens on the home network
RESTART = False  # set after an update from the app: run.bat starts the new version


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


def forget_unused_devices(days, anywhere_days):
    """
    Disconnect devices that were not used for a long time (0 days = never).
    Devices for control from anywhere have their own, longer time. Returns [(name, days)].
    """
    now = time.time()

    def limit(device):
        return anywhere_days if device.get("kind") == "anywhere" else days

    def too_old(device):
        return limit(device) > 0 and device.get("last_used", 0) < now - limit(device) * 86400

    with _devices_lock:
        old = [d for d in _devices if too_old(d)]
        if old:
            _devices[:] = [d for d in _devices if not too_old(d)]
            _save_devices()
        return [(d["name"], limit(d)) for d in old]


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
    if not any(is_tailscale(a) for a in addresses):
        tailscale = _tailscale_address()
        if tailscale:
            addresses.append(tailscale)
    return addresses or ["127.0.0.1"]


TAILSCALE_PROGRAMS = ("tailscale", r"C:\Program Files\Tailscale\tailscale.exe")


def _run_tailscale(*arguments, timeout=5):
    """Run the Tailscale command line program, if Tailscale is installed. Return the result or None."""
    for program in TAILSCALE_PROGRAMS:
        try:
            return subprocess.run([program, *arguments], capture_output=True, text=True, timeout=timeout,
                                  errors="replace", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except (OSError, subprocess.SubprocessError):
            continue
    return None


def _tailscale_address():
    """If Tailscale is installed and on, ask it for this laptop's Tailscale address."""
    result = _run_tailscale("ip", "-4", timeout=3)
    for word in (result.stdout.split() if result else []):
        if is_tailscale(word):
            return word
    return None


# Tailscale: this laptop's name in Tailscale (e.g. my-laptop.tail1234.ts.net), the
# login of its owner, and whether Tailscale can give it a real https certificate.
TAILSCALE = {"name": None, "login": None, "https": False}


def detect_tailscale():
    fake = os.environ.get("LAPTOP_REMOTE_TEST_TAILSCALE") if actions.TEST_MODE else None
    if fake:  # only for tests on other systems: "name|login|https"
        name, login, https = (fake.split("|") + ["", "", ""])[:3]
        TAILSCALE.update(name=name.lower() or None, login=login.lower() or None, https=https == "1")
        return
    result = _run_tailscale("status", "--json")
    if not result or result.returncode != 0:
        return
    try:
        status = json.loads(result.stdout)
        me = status.get("Self") or {}
        name = (me.get("DNSName") or "").rstrip(".").lower()
        user = (status.get("User") or {}).get(str(me.get("UserID")), {}) or {}
        login = (user.get("LoginName") or "").lower()
        domains = [d.rstrip(".").lower() for d in (status.get("CertDomains") or [])]
    except (ValueError, AttributeError, TypeError):
        return
    if name:
        TAILSCALE.update(name=name, login=login or None, https=name in domains)


def secure_link():
    """https://my-laptop.tail1234.ts.net when Tailscale can give the laptop a secure link, else None."""
    return f"https://{TAILSCALE['name']}" if TAILSCALE["name"] and TAILSCALE["https"] else None


def turn_on_tailscale_https(port):
    """Used by tailscale-https.bat: let Tailscale serve this remote at a secure https link."""
    print("\n  Turning on the secure link (https) through Tailscale...\n", flush=True)
    for program in TAILSCALE_PROGRAMS:
        try:
            result = subprocess.run([program, "serve", "--bg", str(port)])  # shows its own messages
            break
        except OSError:
            continue
    else:
        print("  Tailscale is not installed on this laptop. See README, section 9.")
        return 1
    detect_tailscale()
    if result.returncode == 0 and TAILSCALE["name"]:
        print(f"\n  Done. The secure link is:   https://{TAILSCALE['name']}")
        print("  Open it on your phone (with Tailscale switched on in the phone). No code is needed.")
        print("  It keeps working after a restart; just start the remote (start.bat) as usual.")
        return 0
    print("\n  It did not work yet. If Tailscale showed a link above, open it, allow HTTPS (Enable),")
    print("  and then double-click tailscale-https.bat again. If it says \"Access denied\",")
    print("  right-click tailscale-https.bat and choose Run as administrator.")
    return 1


def phone_addresses(port):
    """(addresses at home, addresses from anywhere with Tailscale) as http://... texts."""
    addresses = laptop_addresses()
    home = [f"http://{a}:{port}" for a in addresses if not is_tailscale(a)]
    anywhere = [f"http://{a}:{port}" for a in addresses if is_tailscale(a)]
    return home or [f"http://127.0.0.1:{port}"], anywhere


def print_addresses(port, indent="      "):
    home, anywhere = phone_addresses(port)
    secure = secure_link()
    if secure:
        print(f"{indent}{secure:<32}  BEST: from anywhere, encrypted, no code (Tailscale)")
    print(f"{indent}{home[0]:<32}  at home (the same Wi-Fi as the laptop)")
    for address in anywhere:
        print(f"{indent}{address:<32}  from anywhere, also on 5G (Tailscale)")
    for address in home[1:]:
        print(f"{indent}{address:<32}  (another address, if the first one does not work)")
    if not anywhere and not TAILSCALE["name"]:
        if ANYWHERE:
            print(f"{indent}Away from home (5G, another country)? Control from anywhere, below (README, section 8).")
        else:
            print(f"{indent}Away from home (5G)? See README, sections 8 and 9.")
    elif not secure:
        print(f"{indent}For a secure https link with no code: double-click tailscale-https.bat once (README, section 9).")


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
        c = config()
        for name, days in forget_unused_devices(c["forget_days"], c["forget_days_anywhere"]):
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

    if command == "invite_device":
        if data.get("confirmed") is not True:
            raise ValueError("Confirmation on the phone is required.")
        if not ANYWHERE:
            raise ValueError("Control from anywhere is off on this laptop (anywhere = no in config.ini).")
        try:
            invite = anywhere.parse_invite(data.get("invite"))
            ANYWHERE.accept_invite(invite, approved_by=device["name"])
        except anywhere.AnywhereError as e:
            raise ValueError(str(e))
        except Exception as e:
            raise actions.ActionError(f"The invitation could not be used ({e}).")
        return f"Access given to {invite['name']}"

    if command == "forget_me" and device["id"] == "tailscale":
        raise ValueError("This phone is let in by your Tailscale account. To stop that, sign it out of "
                         "Tailscale, or set tailscale_auto_connect = no in config.ini.")

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

    if command == "update_app":
        if data.get("confirmed") is not True:
            raise ValueError("Confirmation on the phone is required.")
        if not can_update_from_app():
            raise ValueError("On this laptop, update with update.bat (it cannot restart by itself).")
        try:
            changed = apply_update(download_update(), keep={"run.bat"})
        except Exception as e:
            raise actions.ActionError(f"The update did not work ({e}). Nothing was changed.")
        if not changed:
            return f"Laptop Remote {VERSION} is already the newest version"
        log(f"UPDATED from GitHub ({changed} files changed, asked by {device['name']}). Restarting...")
        restart_soon(server)
        return f"Updated ({changed} files). Laptop Remote restarts on the laptop — about a minute"

    if command == "uninstall":
        if data.get("confirmed") is not True:
            raise ValueError("Confirmation on the phone is required.")
        log(f"{device['name']} REMOVED Laptop Remote from this laptop: all access deleted, no more autostart.")
        threading.Thread(target=lambda: (time.sleep(1), uninstall(), server.shutdown()), daemon=True).start()
        return "Laptop Remote is removed from the laptop. All access is deleted."

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

    _capture = None         # used for encrypted (anywhere) requests: the answer is collected, not sent
    _virtual_device = None  # the device of an encrypted request

    def _reply(self, status, body=b"", content_type="application/json; charset=utf-8", headers=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        if self._capture is not None:
            self._capture.append((status, body, content_type, dict(headers or {})))
            return
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

    def _client_ip(self):
        """The real address of the device (behind the tunnel, Cloudflare tells it)."""
        if self.client_address[0] == "127.0.0.1" and self.headers.get("Cf-Connecting-Ip"):
            return self.headers.get("Cf-Connecting-Ip")[:64]
        return self.client_address[0]

    def _via_tunnel(self):
        host = (self.headers.get("Host") or "").split(":")[0].lower()
        return bool(self.headers.get("Cf-Connecting-Ip")) or host.endswith(".trycloudflare.com")

    def _blocked(self):
        """Seconds this device still has to wait after too many failed attempts (0 = none)."""
        with _failures_lock:
            _, until = _failures.get(self._client_ip(), (0, 0))
        return int(until - time.time()) + 1 if until > time.time() else 0

    def _failed(self, what):
        ip = self._client_ip()
        with _failures_lock:
            count, _ = _failures.get(ip, (0, 0))
            count += 1
            if count >= MAX_FAILURES:
                _failures[ip] = (0, time.time() + LOCKOUT_SECONDS)
                self._log(f"WARNING: {count} failed attempts, device blocked for {LOCKOUT_SECONDS // 60} min")
            else:
                _failures[ip] = (count, 0)
                self._log(what)

    def _tailscale_device(self):
        """
        A device signed in to the same Tailscale account as this laptop, coming through
        the secure https link. Tailscale itself has checked who it is, so no code is needed.
        (`tailscale serve` connects from this laptop itself and adds the Tailscale-User-Login
        header; the Host check makes sure the request really came through that link.)
        """
        if not (TAILSCALE["name"] and TAILSCALE["login"] and config()["tailscale_auto"]):
            return None
        if self.client_address[0] != "127.0.0.1":
            return None
        host = (self.headers.get("Host") or "").split(":")[0].lower()
        login = (self.headers.get("Tailscale-User-Login") or "").strip().lower()
        if host != TAILSCALE["name"] or login != TAILSCALE["login"]:
            return None
        return {"id": "tailscale", "name": f"Tailscale ({login})", "via": host}

    def _device(self):
        """The connected phone making this request, or None (and an error reply)."""
        if self._virtual_device:
            return self._virtual_device
        device = self._tailscale_device()
        if device:
            return device
        wait = self._blocked()
        if wait:
            self._reply(429, {"error": f"Too many failed attempts. Wait {wait} s and try again."})
            return None
        given = self.headers.get("X-Key", "")
        device = find_device(given)
        if device:
            with _failures_lock:
                _failures.pop(self._client_ip(), None)
            return device
        if given:  # a page opened without any key is not an attempt to guess one
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
        if self._via_tunnel() and self._capture is None:
            self._reply(404, {"error": "Not found."})  # from the internet only encrypted requests (/e2e)
            return

        if path == "/api/check":
            device = self._device()
            if device:
                c = config()
                self._reply(200, {"ok": True, "laptop": c["name"], "phone": device["name"], "phone_id": device["id"],
                                  "test_mode": actions.TEST_MODE, "screen": list(actions.screen_size()),
                                  "version": VERSION, "can_update": can_update_from_app(),
                                  "installed": ONLY_ANYWHERE})
            return

        if path == "/api/programs":
            if self._device():
                c = config()
                self._reply(200, {"programs": list(c["programs"]), "warnings": c["warnings"]})
            return

        if path == "/api/phones":
            device = self._device()
            if device:
                phones = device_list()
                if TAILSCALE["login"] and config()["tailscale_auto"]:
                    phones.insert(0, {"id": "tailscale", "name": f"Your Tailscale devices ({TAILSCALE['login']})",
                                      "via": secure_link() or "", "connected": None, "last_used": None})
                days = config()["forget_days_anywhere" if device.get("kind") == "anywhere" else "forget_days"]
                self._reply(200, {"phones": phones, "forget_days": days})
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
        body = file.read_bytes()
        if file.name == "index.html":  # tell the page that it was opened from the laptop itself
            body = body.replace(b"<head>", b'<head>\n<meta name="laptop-remote-local" content="1">', 1)
        self._reply(200, body, content_type)

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
        if path == "/e2e":
            self._e2e(raw)
            return
        if self._via_tunnel():
            self._reply(404, {"error": "Not found."})  # from the internet only encrypted requests (/e2e)
            return
        self._post_body(path, raw)

    def _post_body(self, path, raw):
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

    # ---- encrypted requests (control from anywhere) ----

    CORS = {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type", "Access-Control-Max-Age": "86400"}

    def do_OPTIONS(self):
        self._reply(204, headers=self.CORS)

    def _e2e(self, raw):
        if not ANYWHERE:
            self._reply(404, {"error": "Control from anywhere is off on this laptop."}, headers=self.CORS)
            return
        wait = self._blocked()
        if wait:
            self._reply(429, {"error": f"Too many failed attempts. Wait {wait} s and try again."}, headers=self.CORS)
            return
        try:
            device_id, request = anywhere.open_request(raw, ANYWHERE.secret_for_device, ANYWHERE.guard)
        except rc.CryptoError:
            self._failed("anywhere: a request that cannot be opened (unknown or disconnected device)")
            self._reply(401, {"error": "This device is not connected to this laptop."}, headers=self.CORS)
            return
        except (anywhere.AnywhereError, ValueError) as e:
            self._reply(400, {"error": str(e)}, headers=self.CORS)
            return
        with _failures_lock:
            _failures.pop(self._client_ip(), None)
        device = AnywhereDevices.get(device_id)
        secret = AnywhereDevices.secret(device_id)  # taken now: "disconnect this phone" deletes it
        ANYWHERE.mark_used(device_id)
        method, inner = str(request.get("m", "GET")).upper(), str(request.get("p", ""))
        inner_path = urlsplit(inner).path
        if not inner_path.startswith("/api/") or inner_path in ("/api/connect", "/api/local/stop"):
            status, body, content_type, headers = 404, b'{"error": "Not found."}', "application/json", {}
        else:
            status, body, content_type, headers = self._inner(method, inner, request.get("b"), device)
        sealed = anywhere.seal_response(secret, device_id, request["r"], status, body, content_type, headers)
        self._reply(200, sealed, "application/octet-stream", self.CORS)

    def _inner(self, method, path, body, device):
        """Run an API request inside this one, and collect its answer instead of sending it."""
        saved_path = self.path
        self._capture, self._virtual_device = [], device
        try:
            self.path = path
            if method == "GET":
                self._get()
            else:
                self._post_body(urlsplit(path).path, json.dumps(body if body is not None else {}).encode("utf-8"))
        finally:
            self.path = saved_path
            captured, self._capture, self._virtual_device = self._capture, None, None
        return captured[0] if captured else (500, b'{"error": "No answer."}', "application/json", {})

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
        self._failed("a phone used a code that is not valid")
        self._reply(400, {"error": "This code is wrong, has expired or was already used. "
                                   "On the laptop, type L and press Enter for a new code."})

    def _unexpected_error(self, e):
        self._log(f"UNEXPECTED ERROR: {type(e).__name__}: {e}")
        self.close_connection = True
        self._reply(500, {"error": f"Error on the laptop: {e}"})


# ---------------------------------------------------------------------------
# The server window: links, commands, stopping
# ---------------------------------------------------------------------------

LINE = "=" * 66


def print_link(port):
    """Create a new one-time code for a phone, print it with its link and copy the link."""
    code = new_link_code()
    home, anywhere = phone_addresses(port)
    link = f"{(anywhere or home)[0]}/?code={code}"
    secure = secure_link()
    copied = actions.copy_to_clipboard(secure or link)
    if secure and TAILSCALE["login"] and config()["tailscale_auto"]:
        print(f"\n  YOUR TAILSCALE DEVICES ({TAILSCALE['login']}) NEED NO CODE. Just open on the phone:")
        print(f"      {secure}" + ("   (already copied, e.g. to e-mail it)" if copied else ""))
        copied = False
    print(f"\n  CONNECT A PHONE (the code works once, for {LINK_MINUTES} minutes):\n")
    print("    1. On the phone, open:")
    print_addresses(port, indent="         ")
    print(f"\n    2. Type this code:   {code}\n")
    print("  Or open this link on the phone" + (" (it is already copied, e.g. to e-mail it):" if copied else ":"))
    print(f"      {link}")
    print(flush=True)


def print_commands():
    print("  Type a letter here and press Enter:")
    if ANYWHERE:
        print("      A   add a phone or laptop for control from anywhere (paste its invitation)")
    if not ONLY_ANYWHERE:
        print("      L   new code for a phone")
    print(f"      D   disconnect all {'devices' if ONLY_ANYWHERE else 'phones'} (their access stops working)")
    print("      Q   stop the remote")
    print(flush=True)


def _console_commands(server, port):
    while True:
        try:
            line = input()
        except (EOFError, OSError, ValueError, KeyboardInterrupt):
            return  # no keyboard (e.g. started without a window), or Ctrl+C
        command = line.strip().lower()
        if command == "l" and not ONLY_ANYWHERE:
            print_link(port)
        elif command == "a" and ANYWHERE:
            print("\n  Paste the invitation (the whole link from the app) and press Enter:", flush=True)
            try:
                text = input()
                invite = anywhere.parse_invite(text)
                ANYWHERE.accept_invite(invite, approved_by="the person at this laptop (typed in the window)")
                print(f"\n  Done. “{invite['name']}” can now control this laptop from anywhere.\n", flush=True)
            except anywhere.AnywhereError as e:
                print(f"\n  {e}\n", flush=True)
            except (EOFError, OSError, ValueError, KeyboardInterrupt):
                return
            except Exception as e:
                print(f"\n  It did not work ({e}). Check the internet connection and try again.\n", flush=True)
        elif command == "d":
            count = forget_all_devices()
            print(f"\n  Disconnected phones: {count}. Their access does not work any more.")
            print("  To connect a phone again, type L and press Enter for a new code.\n", flush=True)
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
    anywhere.kill_leftover_tunnel(BASE_DIR)
    if already_running(port):
        print(f"\n  Could not stop the program on port {port}. Close its window, or use")
        print("  Task Manager (Ctrl+Shift+Esc): click Python, then End task.")
        return 1
    print("\n  The remote is stopped.")
    return 0


UPDATE_URL = "https://github.com/bogdandata/laptop-remote/archive/refs/heads/main.zip"
KEEP_WHEN_UPDATING = {"config.ini", "devices.json", "update.bat",  # your settings, your phones
                      "anywhere.json", "invite.txt", "cloudflared.exe"}


def download_update():
    url = (os.environ.get("LAPTOP_REMOTE_TEST_UPDATE_URL") if actions.TEST_MODE else None) or UPDATE_URL
    with urllib.request.urlopen(url, timeout=60) as response:
        return zipfile.ZipFile(io.BytesIO(response.read()))


def apply_update(archive, keep=()):
    """Write the program files from the ZIP of GitHub. Returns how many files changed."""
    files = {}
    for name in archive.namelist():
        _, _, relative = name.partition("/")  # inside the ZIP everything is in laptop-remote-main/
        if relative and not name.endswith("/"):
            files[relative] = name
    if "server.py" not in files:
        raise ValueError("the download did not contain the program")
    base = BASE_DIR.resolve()
    changed = 0
    for relative, name in files.items():
        if relative in KEEP_WHEN_UPDATING or relative in keep:
            continue
        target = (base / relative).resolve()
        if base not in target.parents:
            continue  # never write outside the program folder
        data = archive.read(name)
        try:
            if target.read_bytes() == data:
                continue  # unchanged files are not touched (e.g. a .bat file that is running)
        except OSError:
            pass
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        changed += 1
    return changed


def update_from_github(port):
    """Used by update.bat: download the newest version and replace the program files."""
    print("\n  Updating Laptop Remote. Your config.ini and your connected phones are kept.\n")
    if already_running(port):
        print("  1) Stopping the remote...")
        stop_running_copy(port)
    print("  2) Downloading the newest version from GitHub...")
    try:
        archive = download_update()
    except Exception as e:
        print(f"\n  The download did not work ({e}).")
        print("  Check the internet connection and try again.")
        return 1
    try:
        changed = apply_update(archive)
    except (OSError, ValueError, zipfile.BadZipFile) as e:
        print(f"\n  The update did not work ({e}). Nothing was changed.")
        return 1
    if changed:
        print(f"  3) Done: {changed} files updated. Start the remote with start.bat.")
    else:
        print("  3) You already have the newest version. Start the remote with start.bat.")
    return 0


def can_update_from_app():
    """Only when run.bat started the remote: it starts the new version after an update."""
    return os.environ.get("LAPTOP_REMOTE_LAUNCHER") == "run.bat"


def restart_soon(server):
    """Stop in a second (the answer still reaches the app); run.bat then starts the new version."""
    global RESTART
    RESTART = True
    threading.Thread(target=lambda: (time.sleep(1), server.shutdown()), daemon=True).start()


# ---------------------------------------------------------------------------
# Installed from an invitation (setup.html makes the installer, which runs
# run.bat --setup): start by itself at sign-in; remove again with uninstall.bat
# ---------------------------------------------------------------------------

STARTUP_FILE_NAME = "Laptop Remote.cmd"


def _startup_file():
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return None
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / STARTUP_FILE_NAME


def install_autostart():
    """Start Laptop Remote (minimized) every time someone signs in to Windows."""
    target = _startup_file()
    if not target or not target.parent.is_dir():
        return False
    run = BASE_DIR / "run.bat"
    local = os.environ.get("LOCALAPPDATA")
    if local and run == (Path(local) / "LaptopRemote" / "app" / "run.bat").resolve():
        run_text = r"%LOCALAPPDATA%\LaptopRemote\app\run.bat"  # no special letters inside the file
    else:
        run_text = str(run)
    text = ("@echo off\r\n"
            "rem Starts Laptop Remote (control from anywhere, end-to-end encrypted) when you sign in.\r\n"
            "rem To stop that: delete this file, or run uninstall.bat in the Laptop Remote folder.\r\n"
            f'start "Laptop Remote" /min "{run_text}" --autostart\r\n')
    try:
        target.write_bytes(text.encode("oem" if os.name == "nt" else "utf-8", errors="replace"))
        return True
    except OSError:
        return False


def setup_after_install(port):
    """Used by the installer, right before the remote starts for the first time."""
    if already_running(port):
        print("  Laptop Remote is already running on this laptop. It is stopped; the new one starts now.")
        stop_running_copy(port)
    if install_autostart():
        print("  Laptop Remote now starts by itself (minimized) every time you sign in to Windows.\n")


def uninstall():
    """No more autostart, and every phone and laptop loses its access. Returns True if autostart was on."""
    target = _startup_file()
    removed = False
    if target and target.exists():
        try:
            target.unlink()
            removed = True
        except OSError:
            pass
    forget_all_devices()
    for name in ("devices.json", "anywhere.json", "invite.txt"):
        try:
            (BASE_DIR / name).unlink()
        except OSError:
            pass
    return removed


def uninstall_from_window(port):
    """Used by uninstall.bat."""
    print("\n  Removing Laptop Remote from this laptop...")
    if already_running(port):
        stop_running_copy(port)
    load_devices()
    uninstall()
    print("\n  Done. Laptop Remote does not start by itself any more,")
    print("  and every phone and laptop has lost its access to this laptop.")
    local = os.environ.get("LOCALAPPDATA")
    folder = BASE_DIR.parent if local and BASE_DIR.parent == (Path(local) / "LaptopRemote").resolve() else BASE_DIR
    print(f"\n  You can now delete this folder too:  {folder}")
    if actions.ON_WINDOWS:
        subprocess.Popen(["explorer", f"/select,{folder}"])
    return 0


def main():
    global ANYWHERE, ONLY_ANYWHERE
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    data = config(first_time=True)
    port = data["port"]
    args = sys.argv[1:]
    if "--stop" in args:
        return stop_running_copy(port)
    if "--tailscale-https" in args:
        return turn_on_tailscale_https(port)
    if "--update" in args:
        return update_from_github(port)
    if "--uninstall" in args:
        return uninstall_from_window(port)
    ONLY_ANYWHERE = "--anywhere-only" in args  # run.bat: installed from an invitation

    actions.make_dpi_aware()
    actions.disable_quickedit()
    if "--setup" in args:
        setup_after_install(port)
    if already_running(port):
        print(f"\nERROR: the remote is already running on this laptop (port {port}).")
        print("Use the window (or VS Code terminal) where it is already running,")
        print("or stop it first: Ctrl+C in that window, or double-click stop.bat.")
        return 1
    if ONLY_ANYWHERE and not rc.available():
        print("\nERROR: control from anywhere is not available (OpenSSL was not found in this Python).")
        return 1
    try:
        # Installed from an invitation: only this laptop itself (the tunnel) can connect.
        server = RemoteServer(("127.0.0.1" if ONLY_ANYWHERE else "0.0.0.0", port), Handler)
    except OSError as e:
        print(f"\nERROR: the server cannot start on port {port} ({e}).")
        print("Another program is using this port. Close it, or change the port number in config.ini.")
        return 1

    load_devices()
    if not ONLY_ANYWHERE:
        detect_tailscale()
    if data["anywhere"] or ONLY_ANYWHERE:
        if rc.available():
            ANYWHERE = anywhere.Anywhere(port, BASE_DIR, config, AnywhereDevices(), log, actions.ask_yes_no)
        else:
            print("  NOTE: control from anywhere is not available (OpenSSL was not found in this Python).")
    forgotten = forget_unused_devices(data["forget_days"], data["forget_days_anywhere"])
    phones = device_list()

    print(LINE)
    print(f"  LAPTOP REMOTE {VERSION} — running on “{data['name']}”")
    print(LINE)
    for name, days in forgotten:
        print(f"  Disconnected (not used for {days} days): {name}")
    if ONLY_ANYWHERE:
        print("  CONTROL FROM ANYWHERE (any network, end-to-end encrypted): starting...")
        names = ", ".join(p["name"] for p in phones)
        print(f"  Allowed to control this laptop: {names or 'nobody yet'}")
        print("  Only devices that were allowed here can connect, through the encrypted app.")
        print("  Nothing on the home network can connect directly.")
        if ANYWHERE and ANYWHERE.invite_file.exists():
            print("\n  In a moment the laptop asks “Allow … to control this laptop?”.")
            print("  Click Yes if you know that person (the first start downloads cloudflared: wait a minute).")
    else:
        tailscale_phones = bool(secure_link() and TAILSCALE["login"] and data["tailscale_auto"])
        if phones or tailscale_phones:
            if phones:
                print(f"  Connected phones: {', '.join(p['name'] for p in phones)}")
            if tailscale_phones:
                print(f"  Your Tailscale devices ({TAILSCALE['login']}) are let in with no code.")
            print("  Open on the phone:")
            print_addresses(port)
            print("  New phone without Tailscale? Type L and press Enter for a code.")
        else:
            print("  No phone is connected to this laptop yet.")
            print_link(port)
        if ANYWHERE:
            print("\n  CONTROL FROM ANYWHERE (any network, end-to-end encrypted): starting...")
            print(f"      The app for your phone or another laptop:  {data['app_url']}")
            print("      To add one: in the app tap “Add a laptop”, then type A here and paste the invitation.\n")
        print(f"  Apps on the list: {len(data['programs'])} (the list is in config.ini)")
    for w in data["warnings"]:
        print(f"  WARNING in config.ini, {w}")
    if data["keep_awake"]:
        print("  While it runs and the laptop is on its charger, the laptop does not go to sleep by itself.")
    if actions.TEST_MODE:
        print("\n  TEST MODE: this is not Windows, commands are only logged.")
    print(LINE)
    print_commands()
    if ONLY_ANYWHERE:
        print("  Keep this window open (you can minimize it). It starts by itself when you sign in.")
        print("  To stop: type Q and Enter, or close the window.")
        print(f"  To remove Laptop Remote from this laptop: uninstall.bat in {BASE_DIR}")
    else:
        print("  Keep this window open while you use the remote (you can minimize it).")
        print("  To stop: type Q and Enter, press Ctrl+C, close the window, or run stop.bat.")
    print(LINE + "\n", flush=True)

    threading.Thread(target=_writer, daemon=True).start()
    threading.Thread(target=_watch_viewers, daemon=True).start()
    threading.Thread(target=_forget_unused_regularly, daemon=True).start()
    threading.Thread(target=_console_commands, args=(server, port), daemon=True).start()
    if data["keep_awake"]:
        threading.Thread(target=actions.keep_awake_while_plugged_in, daemon=True).start()
    actions.set_window_title("Laptop Remote")
    if ANYWHERE:
        ANYWHERE.start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if ANYWHERE:
            ANYWHERE.stop()
        server.server_close()
    if RESTART:
        print("\nRestarting with the new version...", flush=True)
        return 3  # run.bat starts the remote again
    print("\nThe remote has stopped. Phones stay connected for the next time you start it.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
