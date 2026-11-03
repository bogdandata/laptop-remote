"""
Laptop Remote — web server.

Start it by double-clicking start.bat (or with the command:  py server.py ).
On a phone on the same Wi-Fi, open the address the server prints.
Uses only the Python standard library.
"""

import hmac
import ipaddress
import json
import locale
import mimetypes
import queue
import re
import secrets
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import actions

BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = (BASE_DIR / "web").resolve()
CONFIG_FILE = BASE_DIR / "config.ini"

DEFAULT_PORT = 8765
MAX_TEXT_LENGTH = 5000
MAX_WRONG_PINS = 5
LOCKOUT_SECONDS = 300
SHUTDOWN_DELAY_SECONDS = 5

PIN = ""
_wrong_pins = {}  # ip -> (number of wrong attempts, blocked until)
_pin_lock = threading.Lock()


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

    port = DEFAULT_PORT
    if srv.get("port"):
        if srv["port"].isdigit() and 1 <= int(srv["port"]) <= 65535:
            port = int(srv["port"])
        else:
            warnings.append(f"port “{srv['port']}” is not a valid number, using {DEFAULT_PORT}")

    step = 1
    if srv.get("volume_step"):
        if srv["volume_step"].isdigit() and 1 <= int(srv["volume_step"]) <= 10:
            step = int(srv["volume_step"])
        else:
            warnings.append(f"volume_step “{srv['volume_step']}” must be a number from 1 to 10, using 1")

    programs = {}
    for name, target in sections.get("programs", {}).items():
        if target:
            programs[name] = target
        else:
            warnings.append(f"“{name}” has no path or address after the = sign, skipped")

    return {
        "port": port,
        "pin": srv.get("pin", ""),
        "volume_step": step,
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


def save_pin(pin):
    """Write the PIN into config.ini (the  pin =  line in [server]). Return True on success."""
    try:
        try:
            text, encoding = _decode(CONFIG_FILE.read_bytes())
        except FileNotFoundError:
            text, encoding = "", "utf-8"
        newline = "\n" if ("\n" in text and "\r\n" not in text) else "\r\n"
        lines = text.splitlines()
        section, server_line, replaced = None, None, False
        for i, line in enumerate(lines):
            s = line.strip()
            if s.startswith("[") and s.endswith("]"):
                section = s[1:-1].strip().lower()
                if section == "server" and server_line is None:
                    server_line = i
                continue
            if section == "server" and not s.startswith((";", "#")):
                name, equals, _ = s.partition("=")
                if equals and name.strip().lower() == "pin":
                    lines[i] = f"pin = {pin}"
                    replaced = True
                    break
        if not replaced:
            if server_line is not None:
                lines.insert(server_line + 1, f"pin = {pin}")
            else:
                lines[0:0] = ["[server]", f"pin = {pin}", ""]
        CONFIG_FILE.write_bytes((newline.join(lines) + newline).encode(encoding))
        return True
    except (OSError, UnicodeError):
        return False


def prepare_pin(data):
    """Return (pin, note to print)."""
    pin = data["pin"]
    if pin and re.fullmatch(r"[0-9]{4,12}", pin):
        return pin, ""
    new_pin = f"{secrets.randbelow(10 ** 6):06d}"
    if pin:
        return new_pin, ("The PIN in config.ini is not valid (only 4 to 12 digits are allowed).\n"
                         "  The temporary PIN above works this time. Fix the PIN in config.ini.")
    if save_pin(new_pin):
        return new_pin, "First start: a PIN was created and saved in config.ini.\n  It stays the same next time."
    return new_pin, "The PIN could not be saved in config.ini, so it only works while the server runs."


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


def is_home_network(ip):
    """Only devices on the home (private) network are allowed."""
    try:
        a = ipaddress.ip_address(ip)
        if a.version == 6 and a.ipv4_mapped:
            a = a.ipv4_mapped
        return a.is_private or a.is_loopback or a.is_link_local
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# Commands from the phone
# ---------------------------------------------------------------------------

MEDIA = {"previous": "Previous track", "play_pause": "Play / Pause", "next": "Next track"}
VOLUME = {"volume_down": "Volume down", "volume_up": "Volume up", "mute": "Mute on / off"}


def run_command(data):
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

    raise ValueError(f"Unknown command: {command}")


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    server_version = "LaptopRemote/1.1"
    sys_version = ""

    def log_message(self, format, *args):
        pass  # we print our own, shorter log lines

    def _log(self, text):
        log(f"{self.client_address[0]:<15}  {text}")

    def _reply(self, status, body, content_type="application/json; charset=utf-8"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(body)
        except OSError:
            pass  # the phone closed the connection

    # ---- checks ----

    def _device_allowed(self):
        if is_home_network(self.client_address[0]):
            return True
        self._log("REFUSED: device is not on the home network")
        self._reply(403, {"error": "Access is allowed only from the home network."})
        return False

    def _check_pin(self):
        ip = self.client_address[0]
        now = time.time()
        given = self.headers.get("X-PIN", "")
        with _pin_lock:
            count, blocked_until = _wrong_pins.get(ip, (0, 0))
            if blocked_until > now:
                wait = int(blocked_until - now) + 1
            elif PIN and hmac.compare_digest(given.encode("utf-8"), PIN.encode("utf-8")):
                _wrong_pins.pop(ip, None)
                return True
            else:
                wait = 0
                count += 1
                if count >= MAX_WRONG_PINS:
                    _wrong_pins[ip] = (0, now + LOCKOUT_SECONDS)
                    self._log(f"WARNING: {count} wrong PINs, device blocked for {LOCKOUT_SECONDS // 60} min")
                else:
                    _wrong_pins[ip] = (count, 0)
                    self._log("wrong PIN")
        if wait:
            self._reply(429, {"error": f"Too many wrong PINs. Wait {wait} s and try again."})
        else:
            self._reply(401, {"error": "Wrong PIN."})
        return False

    # ---- GET ----

    def do_GET(self):
        try:
            self._get()
        except Exception as e:
            self._unexpected_error(e)

    def _get(self):
        if not self._device_allowed():
            return
        path = self.path.split("?", 1)[0]

        if path == "/api/check":
            if self._check_pin():
                self._log("phone connected")
                self._reply(200, {"ok": True, "laptop": socket.gethostname(), "test_mode": actions.TEST_MODE})
            return

        if path == "/api/programs":
            if self._check_pin():
                c = config()
                self._reply(200, {"programs": list(c["programs"]), "warnings": c["warnings"]})
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

    # ---- POST ----

    def do_POST(self):
        try:
            self._post()
        except Exception as e:
            self._unexpected_error(e)

    def _post(self):
        if not self._device_allowed():
            return
        # The request body is read before the PIN check, so the reply always reaches the phone.
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = -1
        if not 0 <= length <= 100_000:
            self._reply(400, {"error": "Invalid request."})
            return
        raw = self.rfile.read(length) if length else b""

        if self.path.split("?", 1)[0] != "/api/command":
            self._reply(404, {"error": "Not found."})
            return
        if not self._check_pin():
            return
        try:
            data = json.loads(raw.decode("utf-8") or "{}")
            if not isinstance(data, dict):
                raise ValueError
        except ValueError:
            self._reply(400, {"error": "Invalid request."})
            return

        command = data.get("command")
        try:
            message = run_command(data)
        except ValueError as e:
            self._log(f"refused ({command}): {e}")
            self._reply(400, {"error": str(e)})
            return
        except actions.ActionError as e:
            self._log(f"FAILED ({command}): {e}")
            self._reply(500, {"error": str(e)})
            return
        self._reply(200, {"ok": True, "message": message})
        extra = f" → {data.get('name')}" if command == "open" else ""
        if actions.TEST_MODE:
            extra += "   [test mode, nothing was executed]"
        self._log(f"command: {command}{extra}")

    def _unexpected_error(self, e):
        self._log(f"UNEXPECTED ERROR: {type(e).__name__}: {e}")
        self._reply(500, {"error": f"Error on the laptop: {e}"})


# ---------------------------------------------------------------------------
# Start
# ---------------------------------------------------------------------------

def main():
    global PIN
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    actions.disable_quickedit()

    data = config(first_time=True)
    PIN, pin_note = prepare_pin(data)
    data = config(first_time=True)  # again, because the PIN may have just been written to the file
    port = data["port"]

    if already_running(port):
        print(f"\nERROR: the remote is already running on this laptop (port {port}).")
        print("Use the window (or VS Code terminal) where it is already running,")
        print("or stop it there first (Ctrl+C or close the window), then start it again.")
        return 1
    try:
        server = RemoteServer(("0.0.0.0", port), Handler)
    except OSError as e:
        print(f"\nERROR: the server cannot start on port {port} ({e}).")
        print("Another program is using this port. Close it,")
        print("or change the port number in config.ini.")
        return 1
    threading.Thread(target=_writer, daemon=True).start()

    addresses = laptop_addresses()
    line = "=" * 62
    print(line)
    print("  LAPTOP REMOTE — the server is running")
    print(line)
    print("  On your phone (on the same Wi-Fi), open this address in the browser:\n")
    print(f"      http://{addresses[0]}:{port}\n")
    if len(addresses) > 1:
        print("  If that address does not work, try one of these:")
        for a in addresses[1:]:
            print(f"      http://{a}:{port}")
        print()
    print(f"  PIN for the phone:   {PIN}")
    if pin_note:
        print(f"  {pin_note}")
    print(f"\n  Apps on the list: {len(data['programs'])} (the list is in config.ini)")
    for w in data["warnings"]:
        print(f"  WARNING in config.ini, {w}")
    if actions.TEST_MODE:
        print("\n  TEST MODE: this is not Windows, commands are only logged.")
    print(line)
    print("  Keep this window open while you use the remote (you can")
    print("  minimize it). To stop the server, close the window or press Ctrl+C.")
    print(line + "\n", flush=True)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nThe server has stopped.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
