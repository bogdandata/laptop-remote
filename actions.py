"""
Actions the laptop performs: media keys, volume, lock screen, shut down and
restart, opening programs, typing text, special keys, the mouse and the
picture of the screen.

On Windows only the Python standard library is used:
  - ctypes        -> SendInput (keys and mouse), LockWorkStation, the screen
                     picture (GDI), the clipboard and the window title
  - os.startfile  -> opening programs, folders and websites
  - shutdown.exe  -> shut down and restart (a command built into every Windows)
  - zlib, struct  -> turning the screen picture into a PNG image

On other systems (e.g. when the program is tested on Linux) it runs in
TEST MODE: actions are only recorded, nothing is actually executed, and the
"screen" is a generated test picture.
"""

import ctypes
import os
import struct
import subprocess
import threading
import time
import zlib
from ctypes import wintypes

ON_WINDOWS = os.name == "nt"
TEST_MODE = not ON_WINDOWS

# In test mode, this records what would have been executed (used by tests).
test_log = []


class ActionError(Exception):
    """An error whose message is shown on the phone."""


# ---------------------------------------------------------------------------
# Windows structures
# The types have fixed sizes, exactly as in Windows (LONG/DWORD = 4 bytes,
# WORD = 2 bytes, ULONG_PTR = pointer size). With 64-bit Python INPUT is
# 40 bytes, with 32-bit Python 28 bytes — the same as in the Windows SDK.
# ---------------------------------------------------------------------------

LONG = ctypes.c_int32
DWORD = ctypes.c_uint32
WORD = ctypes.c_uint16
UINT = ctypes.c_uint32
ULONG_PTR = ctypes.c_size_t

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_HWHEEL = 0x1000
MOUSE_BUTTONS = {
    "left": (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP),
    "right": (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP),
    "middle": (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP),
}

VK_BACK = 0x08
VK_TAB = 0x09
VK_RETURN = 0x0D
VK_CONTROL = 0x11
VK_MENU = 0x12  # Alt
VK_ESCAPE = 0x1B
VK_SPACE = 0x20
VK_LEFT = 0x25
VK_UP = 0x26
VK_RIGHT = 0x27
VK_DOWN = 0x28
VK_DELETE = 0x2E
VK_LWIN = 0x5B
VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP = 0xAF
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_PLAY_PAUSE = 0xB3
EXTENDED_KEYS = {VK_LEFT, VK_UP, VK_RIGHT, VK_DOWN, VK_DELETE, VK_LWIN}

# Special keys the phone can press: name -> (modifier keys, key)
SPECIAL_KEYS = {
    "esc": ([], VK_ESCAPE),
    "tab": ([], VK_TAB),
    "enter": ([], VK_RETURN),
    "backspace": ([], VK_BACK),
    "delete": ([], VK_DELETE),
    "space": ([], VK_SPACE),
    "left": ([], VK_LEFT),
    "up": ([], VK_UP),
    "right": ([], VK_RIGHT),
    "down": ([], VK_DOWN),
    "win": ([], VK_LWIN),
    "alt_tab": ([VK_MENU], VK_TAB),
    "ctrl_c": ([VK_CONTROL], ord("C")),
    "ctrl_v": ([VK_CONTROL], ord("V")),
    "ctrl_z": ([VK_CONTROL], ord("Z")),
}

ASFW_ANY = 0xFFFFFFFF
STD_INPUT_HANDLE = 0xFFFFFFF6  # (DWORD)-10
ENABLE_QUICK_EDIT_MODE = 0x0040
ENABLE_EXTENDED_FLAGS = 0x0080
ERROR_SHUTDOWN_IS_SCHEDULED = 1190

SM_CXSCREEN = 0
SM_CYSCREEN = 1
SRCCOPY = 0x00CC0020
HALFTONE = 4
BI_RGB = 0
DIB_RGB_COLORS = 0
GMEM_MOVEABLE = 0x0002
CF_UNICODETEXT = 13


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", LONG),
        ("dy", LONG),
        ("mouseData", DWORD),
        ("dwFlags", DWORD),
        ("time", DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", WORD),
        ("wScan", WORD),
        ("dwFlags", DWORD),
        ("time", DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", DWORD),
        ("wParamL", WORD),
        ("wParamH", WORD),
    ]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", DWORD), ("u", _INPUTUNION)]


class POINT(ctypes.Structure):
    _fields_ = [("x", LONG), ("y", LONG)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", DWORD),
        ("biWidth", LONG),
        ("biHeight", LONG),
        ("biPlanes", WORD),
        ("biBitCount", WORD),
        ("biCompression", DWORD),
        ("biSizeImage", DWORD),
        ("biXPelsPerMeter", LONG),
        ("biYPelsPerMeter", LONG),
        ("biClrUsed", DWORD),
        ("biClrImportant", DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", DWORD * 3)]


class SYSTEM_POWER_STATUS(ctypes.Structure):
    _fields_ = [("ACLineStatus", ctypes.c_ubyte), ("BatteryFlag", ctypes.c_ubyte),
                ("BatteryLifePercent", ctypes.c_ubyte), ("SystemStatusFlag", ctypes.c_ubyte),
                ("BatteryLifeTime", DWORD), ("BatteryFullLifeTime", DWORD)]


if ON_WINDOWS:
    HANDLE = wintypes.HANDLE
    INT = ctypes.c_int
    BOOL = wintypes.BOOL
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

    def _declare(function, argtypes, restype):
        function.argtypes = argtypes
        function.restype = restype

    # keyboard and mouse
    _declare(user32.SendInput, (UINT, ctypes.POINTER(INPUT), INT), UINT)
    _declare(user32.LockWorkStation, (), BOOL)
    _declare(user32.AllowSetForegroundWindow, (DWORD,), BOOL)
    _declare(user32.GetSystemMetrics, (INT,), INT)
    _declare(user32.GetCursorPos, (ctypes.POINTER(POINT),), BOOL)
    _declare(user32.SetCursorPos, (INT, INT), BOOL)
    # the screen picture
    _declare(user32.GetDC, (HANDLE,), HANDLE)
    _declare(user32.ReleaseDC, (HANDLE, HANDLE), INT)
    _declare(gdi32.CreateCompatibleDC, (HANDLE,), HANDLE)
    _declare(gdi32.CreateCompatibleBitmap, (HANDLE, INT, INT), HANDLE)
    _declare(gdi32.SelectObject, (HANDLE, HANDLE), HANDLE)
    _declare(gdi32.SetStretchBltMode, (HANDLE, INT), INT)
    _declare(gdi32.SetBrushOrgEx, (HANDLE, INT, INT, ctypes.c_void_p), BOOL)
    _declare(gdi32.StretchBlt, (HANDLE, INT, INT, INT, INT, HANDLE, INT, INT, INT, INT, DWORD), BOOL)
    _declare(gdi32.GetDIBits, (HANDLE, HANDLE, UINT, UINT, ctypes.c_void_p, ctypes.POINTER(BITMAPINFO), UINT), INT)
    _declare(gdi32.DeleteObject, (HANDLE,), BOOL)
    _declare(gdi32.DeleteDC, (HANDLE,), BOOL)
    # clipboard
    _declare(user32.OpenClipboard, (HANDLE,), BOOL)
    _declare(user32.EmptyClipboard, (), BOOL)
    _declare(user32.SetClipboardData, (UINT, HANDLE), HANDLE)
    _declare(user32.CloseClipboard, (), BOOL)
    _declare(kernel32.GlobalAlloc, (UINT, ctypes.c_size_t), HANDLE)
    _declare(kernel32.GlobalLock, (HANDLE,), ctypes.c_void_p)
    _declare(kernel32.GlobalUnlock, (HANDLE,), BOOL)
    _declare(kernel32.GlobalFree, (HANDLE,), HANDLE)
    # the server window
    _declare(kernel32.GetStdHandle, (DWORD,), HANDLE)
    _declare(kernel32.GetConsoleMode, (HANDLE, ctypes.POINTER(DWORD)), BOOL)
    _declare(kernel32.SetConsoleMode, (HANDLE, DWORD), BOOL)
    _declare(kernel32.SetConsoleTitleW, (wintypes.LPCWSTR,), BOOL)
    # questions on the laptop (Yes / No)
    _declare(user32.MessageBoxW, (HANDLE, wintypes.LPCWSTR, wintypes.LPCWSTR, UINT), INT)
    # no sleep while the remote runs (on the charger)
    _declare(kernel32.SetThreadExecutionState, (DWORD,), DWORD)
    _declare(kernel32.GetSystemPowerStatus, (ctypes.POINTER(SYSTEM_POWER_STATUS),), BOOL)

# Only one action at a time may send keys or mouse events (e.g. typing and
# volume), otherwise they would get mixed up.
_input_lock = threading.Lock()
_screen_lock = threading.Lock()


def _clamp(value, low, high):
    return max(low, min(high, value))


def _key(vk, up=False, extended=False):
    flags = (KEYEVENTF_KEYUP if up else 0) | (KEYEVENTF_EXTENDEDKEY if extended else 0)
    event = INPUT(type=INPUT_KEYBOARD)
    event.ki = KEYBDINPUT(wVk=vk, wScan=0, dwFlags=flags, time=0, dwExtraInfo=0)
    return event


def _unicode_char(code_unit, up=False):
    flags = KEYEVENTF_UNICODE | (KEYEVENTF_KEYUP if up else 0)
    event = INPUT(type=INPUT_KEYBOARD)
    event.ki = KEYBDINPUT(wVk=0, wScan=code_unit, dwFlags=flags, time=0, dwExtraInfo=0)
    return event


def _mouse(flags, dx=0, dy=0, data=0):
    event = INPUT(type=INPUT_MOUSE)
    event.mi = MOUSEINPUT(dx=dx, dy=dy, mouseData=data & 0xFFFFFFFF, dwFlags=flags, time=0, dwExtraInfo=0)
    return event


def _send(events):
    """Send a list of INPUT structures to Windows (SendInput)."""
    if not events:
        return
    array = (INPUT * len(events))(*events)
    sent = user32.SendInput(len(events), array, ctypes.sizeof(INPUT))
    if sent != len(events):
        code = ctypes.get_last_error()
        raise ActionError(
            "Windows did not accept the key press or mouse action"
            + (f" (error {code})" if code else "")
            + ". If the laptop screen is locked, unlock it first."
        )


def _send_locked(events):
    with _input_lock:
        _send(events)


def _press(vk, times=1):
    events = []
    for _ in range(times):
        events.append(_key(vk, extended=True))
        events.append(_key(vk, up=True, extended=True))
    _send_locked(events)


def _record(description):
    test_log.append(description)


# ---------------------------------------------------------------------------
# Helpers for the server window
# ---------------------------------------------------------------------------

def make_dpi_aware():
    """
    Work with real screen pixels even when Windows display scaling is 125%,
    150%... Without this the screen picture and the clicks would be off.
    """
    if not ON_WINDOWS:
        return
    try:
        ctypes.WinDLL("shcore").SetProcessDpiAwareness(2)  # per-monitor aware
        return
    except Exception:
        pass
    try:
        user32.SetProcessDPIAware()
    except Exception:
        pass


def disable_quickedit():
    """
    In a classic Windows console window, clicking inside the window turns on
    text selection (QuickEdit) and the program pauses until Esc is pressed —
    the phone would then wait without an answer. So we turn it off.
    """
    if not ON_WINDOWS:
        return
    try:
        handle = kernel32.GetStdHandle(STD_INPUT_HANDLE)
        mode = DWORD()
        if handle and kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            new_mode = (mode.value & ~ENABLE_QUICK_EDIT_MODE) | ENABLE_EXTENDED_FLAGS
            kernel32.SetConsoleMode(handle, new_mode)
    except Exception:
        pass


def set_window_title(title):
    if TEST_MODE:
        return _record(f"window title: {title}")
    try:
        kernel32.SetConsoleTitleW(title)
    except Exception:
        pass


MB_YESNO = 0x00000004
MB_ICONQUESTION = 0x00000020
MB_SYSTEMMODAL = 0x00001000
MB_SETFOREGROUND = 0x00010000
MB_TOPMOST = 0x00040000
IDYES = 6


def ask_yes_no(title, text):
    """Ask the person at the laptop a Yes / No question in a window on top of everything."""
    if TEST_MODE:
        answer = os.environ.get("LAPTOP_REMOTE_TEST_CONSENT", "yes").lower() == "yes"
        _record(f"question: {title} -> {'yes' if answer else 'no'}")
        return answer
    flags = MB_YESNO | MB_ICONQUESTION | MB_SYSTEMMODAL | MB_SETFOREGROUND | MB_TOPMOST
    return user32.MessageBoxW(None, text, title, flags) == IDYES


ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001


def plugged_in():
    """True if the laptop is on its charger (desktop PCs count as plugged in)."""
    if TEST_MODE:
        return True
    status = SYSTEM_POWER_STATUS()
    try:
        if not kernel32.GetSystemPowerStatus(ctypes.byref(status)):
            return True
    except Exception:
        return True
    return status.ACLineStatus != 0  # 0 = on battery, 1 = plugged in, 255 = unknown


def keep_awake_while_plugged_in():
    """
    Runs in its own thread for as long as the remote runs: while the laptop is on its
    charger, Windows does not go to sleep by itself (the screen may still turn off).
    On battery, Windows' normal sleep settings apply. Closing the lid still works as set.
    """
    awake = None
    while True:
        wanted = plugged_in()
        if wanted != awake:
            flags = ES_CONTINUOUS | (ES_SYSTEM_REQUIRED if wanted else 0)
            if TEST_MODE:
                _record(f"keep awake: {'on' if wanted else 'off'}")
            else:
                try:
                    kernel32.SetThreadExecutionState(flags)
                except Exception:
                    return
            awake = wanted
        time.sleep(60)


def copy_to_clipboard(text):
    """Put text on the Windows clipboard. Return True if it worked."""
    if TEST_MODE:
        _record(f"clipboard: {text}")
        return False
    data = (text + "\0").encode("utf-16-le")
    try:
        if not user32.OpenClipboard(None):
            return False
    except Exception:
        return False
    try:
        user32.EmptyClipboard()
        memory = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
        if not memory:
            return False
        pointer = kernel32.GlobalLock(memory)
        if not pointer:
            kernel32.GlobalFree(memory)
            return False
        ctypes.memmove(pointer, data, len(data))
        kernel32.GlobalUnlock(memory)
        if not user32.SetClipboardData(CF_UNICODETEXT, memory):
            kernel32.GlobalFree(memory)
            return False
        return True  # the clipboard owns the memory now
    except Exception:
        return False
    finally:
        user32.CloseClipboard()


def _allow_new_window_in_front():
    """
    Windows sometimes opens a new program behind other windows (it only
    flashes on the taskbar). An empty mouse input (no movement, no click)
    gives this process the right to let the new program come to the front.
    """
    try:
        user32.SendInput(1, ctypes.byref(_mouse(0)), ctypes.sizeof(INPUT))
        user32.AllowSetForegroundWindow(ASFW_ANY)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Music, volume, system
# ---------------------------------------------------------------------------

def media_key(which):
    codes = {
        "previous": VK_MEDIA_PREV_TRACK,
        "play_pause": VK_MEDIA_PLAY_PAUSE,
        "next": VK_MEDIA_NEXT_TRACK,
    }
    if TEST_MODE:
        return _record(f"media key: {which}")
    _press(codes[which])


def volume(which, step=1):
    codes = {
        "volume_down": VK_VOLUME_DOWN,
        "volume_up": VK_VOLUME_UP,
        "mute": VK_VOLUME_MUTE,
    }
    times = 1 if which == "mute" else max(1, step)
    if TEST_MODE:
        return _record(f"volume: {which} x{times}")
    _press(codes[which], times)


def lock_screen():
    if TEST_MODE:
        return _record("lock screen")
    if not user32.LockWorkStation():
        raise ActionError(f"Locking the screen failed (error {ctypes.get_last_error()}).")


def _shutdown(arguments, description):
    try:
        result = subprocess.run(
            ["shutdown", *arguments],
            capture_output=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError as e:
        raise ActionError(f"Cannot run the Windows shutdown command ({e}).")
    if result.returncode == ERROR_SHUTDOWN_IS_SCHEDULED:
        raise ActionError("A shutdown or restart is already scheduled.")
    if result.returncode != 0:
        raise ActionError(f"Windows did not accept the {description} (code {result.returncode}).")


def shut_down(seconds=5):
    if TEST_MODE:
        return _record(f"shut down in {seconds} s")
    _shutdown(["/s", "/t", str(seconds)], "shutdown")


def restart(seconds=5):
    if TEST_MODE:
        return _record(f"restart in {seconds} s")
    _shutdown(["/r", "/t", str(seconds)], "restart")


def clean_target(target):
    """Remove quotes and spaces, and expand %USERPROFILE% and similar variables."""
    target = target.strip().strip('"').strip()
    if ON_WINDOWS:
        target = os.path.expandvars(target)
    return target


def open_target(target):
    """Open a program, file, folder or web address (same as double-clicking in Windows)."""
    target = clean_target(target)
    if TEST_MODE:
        return _record(f"open: {target}")
    _allow_new_window_in_front()
    try:
        os.startfile(target)
    except FileNotFoundError:
        raise ActionError(f"Not found: {target} — check the path in config.ini.")
    except OSError as e:
        raise ActionError(f"Cannot open {target} ({e.strerror or e}).")


# ---------------------------------------------------------------------------
# Keyboard
# ---------------------------------------------------------------------------

def type_text(text, press_enter=False):
    """Type text into the active window (accented letters and emoji work too)."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if TEST_MODE:
        return _record(f"type: {text!r}" + (" + Enter" if press_enter else ""))

    # For each character, a list of key events (down/up). Unicode input does
    # not depend on the keyboard layout set on the laptop.
    characters = []
    for char in text:
        if char == "\n":
            characters.append([_key(VK_RETURN), _key(VK_RETURN, up=True)])
        elif char == "\t":
            characters.append([_key(VK_TAB), _key(VK_TAB, up=True)])
        else:
            events = []
            data = char.encode("utf-16-le")  # emoji = 2 parts (surrogate pair)
            for i in range(0, len(data), 2):
                code_unit = int.from_bytes(data[i:i + 2], "little")
                events += [_unicode_char(code_unit), _unicode_char(code_unit, up=True)]
            characters.append(events)
    if press_enter:
        characters.append([_key(VK_RETURN), _key(VK_RETURN, up=True)])

    # Sent 20 characters at a time with a short pause, so no program "drops" letters.
    with _input_lock:
        for i in range(0, len(characters), 20):
            _send([e for c in characters[i:i + 20] for e in c])
            time.sleep(0.01)


def press_key(name):
    """Press a special key or shortcut from SPECIAL_KEYS, e.g. "enter" or "alt_tab"."""
    modifiers, vk = SPECIAL_KEYS[name]
    if TEST_MODE:
        return _record(f"key: {name}")
    events = [_key(m, extended=m in EXTENDED_KEYS) for m in modifiers]
    events.append(_key(vk, extended=vk in EXTENDED_KEYS))
    events.append(_key(vk, up=True, extended=vk in EXTENDED_KEYS))
    events += [_key(m, up=True, extended=m in EXTENDED_KEYS) for m in reversed(modifiers)]
    _send_locked(events)


# ---------------------------------------------------------------------------
# Mouse
# ---------------------------------------------------------------------------

TEST_SCREEN = (1920, 1080)
_test_cursor = [960, 540]


def screen_size():
    """Size of the main screen in real pixels."""
    if TEST_MODE:
        return TEST_SCREEN
    return user32.GetSystemMetrics(SM_CXSCREEN), user32.GetSystemMetrics(SM_CYSCREEN)


def cursor_position():
    """Where the mouse cursor is, as fractions of the screen size (0..1), or None."""
    width, height = screen_size()
    if width <= 0 or height <= 0:
        return None
    if TEST_MODE:
        x, y = _test_cursor
    else:
        point = POINT()
        if not user32.GetCursorPos(ctypes.byref(point)):
            return None
        x, y = point.x, point.y
    return _clamp(x / width, 0.0, 1.0), _clamp(y / height, 0.0, 1.0)


def _move_cursor_to(fx, fy):
    """Put the cursor at a place given as fractions of the screen size (0..1)."""
    width, height = screen_size()
    x = _clamp(int(round(fx * (width - 1))), 0, max(width - 1, 0))
    y = _clamp(int(round(fy * (height - 1))), 0, max(height - 1, 0))
    if TEST_MODE:
        _test_cursor[:] = [x, y]
        return
    if not user32.SetCursorPos(x, y):
        raise ActionError("Windows did not accept the mouse position. If the screen is locked, unlock it first.")


def mouse_move(dx, dy):
    """Move the mouse by dx, dy (like a touchpad)."""
    dx, dy = _clamp(int(dx), -3000, 3000), _clamp(int(dy), -3000, 3000)
    if TEST_MODE:
        width, height = TEST_SCREEN
        _test_cursor[0] = _clamp(_test_cursor[0] + dx, 0, width - 1)
        _test_cursor[1] = _clamp(_test_cursor[1] + dy, 0, height - 1)
        return _record(f"mouse move {dx},{dy}")
    _send_locked([_mouse(MOUSEEVENTF_MOVE, dx, dy)])


def click(button="left", x=None, y=None, double=False):
    """Click a mouse button, optionally first moving to x, y (fractions of the screen)."""
    down, up = MOUSE_BUTTONS[button]
    if x is not None and y is not None:
        _move_cursor_to(x, y)
    if TEST_MODE:
        where = f" at {x:.3f},{y:.3f}" if x is not None and y is not None else ""
        return _record(f"{'double ' if double else ''}click {button}{where}")
    events = [_mouse(down), _mouse(up)] * (2 if double else 1)
    _send_locked(events)


def mouse_button(button, pressed):
    """Hold a mouse button down (pressed=True) or let it go (for dragging)."""
    down, up = MOUSE_BUTTONS[button]
    if TEST_MODE:
        return _record(f"mouse {button} {'down' if pressed else 'up'}")
    _send_locked([_mouse(down if pressed else up)])


def scroll(amount, horizontal=False):
    """Turn the mouse wheel. 120 = one notch; positive = up (or right)."""
    amount = _clamp(int(amount), -2400, 2400)
    if not amount:
        return
    if TEST_MODE:
        return _record(f"scroll {'horizontal ' if horizontal else ''}{amount}")
    _send_locked([_mouse(MOUSEEVENTF_HWHEEL if horizontal else MOUSEEVENTF_WHEEL, data=amount)])


# ---------------------------------------------------------------------------
# Screen picture
# ---------------------------------------------------------------------------

def _test_picture(width, height):
    """A generated picture for test mode: a gradient, a "window" and a moving block."""
    row = bytearray()
    for x in range(width):
        v = x * 255 // max(width - 1, 1)
        row += bytes((200, 120 + v // 4, v, 255))  # B, G, R, A
    picture = bytearray(bytes(row) * height)

    def rectangle(x0, y0, x1, y1, color):
        line = bytes(color) * (x1 - x0)
        for y in range(y0, y1):
            start = (y * width + x0) * 4
            picture[start:start + len(line)] = line

    rectangle(width // 10, height // 8, width // 2, height // 2, (245, 245, 245, 255))
    rectangle(width // 10, height // 8, width // 2, height // 8 + max(height // 20, 1), (160, 90, 40, 255))
    step = int(time.time() * 2) % 10
    block_x = step * (width - width // 10) // 10
    rectangle(block_x, height * 3 // 4, block_x + width // 10, height * 3 // 4 + height // 10, (40, 40, 220, 255))
    return bytes(picture)


def capture_screen(max_width):
    """
    Take a picture of the main screen, scaled down to at most max_width pixels
    wide. Return (pixels as B,G,R,A bytes, width, height).
    """
    screen_width, screen_height = screen_size()
    if screen_width <= 0 or screen_height <= 0:
        raise ActionError("Cannot read the screen size.")
    scale = min(1.0, max_width / screen_width)
    width, height = max(1, int(screen_width * scale)), max(1, int(screen_height * scale))
    if TEST_MODE:
        return _test_picture(width, height), width, height

    with _screen_lock:
        screen_dc = user32.GetDC(None)
        if not screen_dc:
            raise ActionError("Cannot read the screen.")
        memory_dc = bitmap = old_object = None
        try:
            memory_dc = gdi32.CreateCompatibleDC(screen_dc)
            bitmap = gdi32.CreateCompatibleBitmap(screen_dc, width, height)
            if not memory_dc or not bitmap:
                raise ActionError("Cannot read the screen.")
            old_object = gdi32.SelectObject(memory_dc, bitmap)
            gdi32.SetStretchBltMode(memory_dc, HALFTONE)  # smooth scaling
            gdi32.SetBrushOrgEx(memory_dc, 0, 0, None)
            if not gdi32.StretchBlt(memory_dc, 0, 0, width, height,
                                    screen_dc, 0, 0, screen_width, screen_height, SRCCOPY):
                raise ActionError("The laptop screen cannot be shown right now. It may be locked.")
            gdi32.SelectObject(memory_dc, old_object)  # GetDIBits needs the bitmap unselected
            old_object = None

            info = BITMAPINFO()
            header = info.bmiHeader
            header.biSize = ctypes.sizeof(BITMAPINFOHEADER)
            header.biWidth = width
            header.biHeight = -height  # negative = rows from top to bottom
            header.biPlanes = 1
            header.biBitCount = 32
            header.biCompression = BI_RGB
            pixels = ctypes.create_string_buffer(width * height * 4)
            if gdi32.GetDIBits(screen_dc, bitmap, 0, height, pixels, ctypes.byref(info), DIB_RGB_COLORS) != height:
                raise ActionError("Cannot read the screen.")
            return pixels.raw, width, height
        finally:
            if old_object:
                gdi32.SelectObject(memory_dc, old_object)
            if bitmap:
                gdi32.DeleteObject(bitmap)
            if memory_dc:
                gdi32.DeleteDC(memory_dc)
            user32.ReleaseDC(None, screen_dc)


def _png_chunk(kind, data):
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def encode_png(bgra, width, height):
    """Turn B,G,R,A pixels into a PNG image (standard library only)."""
    rgb = bytearray(width * height * 3)
    rgb[0::3] = bgra[2::4]
    rgb[1::3] = bgra[1::4]
    rgb[2::3] = bgra[0::4]
    stride = width * 3
    view = memoryview(rgb)
    parts = []
    for start in range(0, len(rgb), stride):
        parts.append(b"\x00")  # filter type 0 for every row
        parts.append(view[start:start + stride])
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)  # 8-bit RGB
    return (b"\x89PNG\r\n\x1a\n" + _png_chunk(b"IHDR", header)
            + _png_chunk(b"IDAT", zlib.compress(b"".join(parts), 1)) + _png_chunk(b"IEND", b""))
