"""
Actions the laptop performs: media keys, volume, lock screen, shut down and
restart, opening programs and typing text.

On Windows only the Python standard library is used:
  - ctypes        -> SendInput (keys), LockWorkStation (lock screen)
  - os.startfile  -> opening programs, folders and websites
  - shutdown.exe  -> shut down and restart (a command built into every Windows)

On other systems (e.g. when the program is tested on Linux) it runs in
TEST MODE: actions are only recorded, nothing is actually executed.
"""

import ctypes
import os
import subprocess
import threading
import time
from ctypes import wintypes

ON_WINDOWS = os.name == "nt"
TEST_MODE = not ON_WINDOWS

# In test mode, this records what would have been executed (used by tests).
test_log = []


class ActionError(Exception):
    """An error whose message is shown on the phone."""


# ---------------------------------------------------------------------------
# Windows structures for SendInput
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

VK_TAB = 0x09
VK_RETURN = 0x0D
VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP = 0xAF
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_PLAY_PAUSE = 0xB3

ASFW_ANY = 0xFFFFFFFF
STD_INPUT_HANDLE = 0xFFFFFFF6  # (DWORD)-10
ENABLE_QUICK_EDIT_MODE = 0x0040
ENABLE_EXTENDED_FLAGS = 0x0080
ERROR_SHUTDOWN_IS_SCHEDULED = 1190


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


if ON_WINDOWS:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    user32.SendInput.argtypes = (UINT, ctypes.POINTER(INPUT), ctypes.c_int)
    user32.SendInput.restype = UINT
    user32.LockWorkStation.argtypes = ()
    user32.LockWorkStation.restype = wintypes.BOOL
    user32.AllowSetForegroundWindow.argtypes = (DWORD,)
    user32.AllowSetForegroundWindow.restype = wintypes.BOOL

    kernel32.GetStdHandle.argtypes = (DWORD,)
    kernel32.GetStdHandle.restype = wintypes.HANDLE
    kernel32.GetConsoleMode.argtypes = (wintypes.HANDLE, ctypes.POINTER(DWORD))
    kernel32.GetConsoleMode.restype = wintypes.BOOL
    kernel32.SetConsoleMode.argtypes = (wintypes.HANDLE, DWORD)
    kernel32.SetConsoleMode.restype = wintypes.BOOL

# Two actions must not send keys at the same time (e.g. typing and volume),
# otherwise the letters would get mixed up.
_keyboard_lock = threading.Lock()


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


def _send(events):
    """Send a list of INPUT structures to Windows (SendInput)."""
    if not events:
        return
    array = (INPUT * len(events))(*events)
    sent = user32.SendInput(len(events), array, ctypes.sizeof(INPUT))
    if sent != len(events):
        code = ctypes.get_last_error()
        raise ActionError(
            "Windows did not accept the key press"
            + (f" (error {code})" if code else "")
            + ". If the laptop screen is locked, unlock it first."
        )


def _press(vk, times=1):
    events = []
    for _ in range(times):
        events.append(_key(vk, extended=True))
        events.append(_key(vk, up=True, extended=True))
    with _keyboard_lock:
        _send(events)


def _record(description):
    test_log.append(description)


# ---------------------------------------------------------------------------
# Helpers for the server window
# ---------------------------------------------------------------------------

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


def _allow_new_window_in_front():
    """
    Windows sometimes opens a new program behind other windows (it only
    flashes on the taskbar). An empty mouse input (no movement, no click)
    gives this process the right to let the new program come to the front.
    """
    try:
        empty = INPUT(type=INPUT_MOUSE)  # all zeros: no movement and no click
        user32.SendInput(1, ctypes.byref(empty), ctypes.sizeof(INPUT))
        user32.AllowSetForegroundWindow(ASFW_ANY)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Actions
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
    with _keyboard_lock:
        for i in range(0, len(characters), 20):
            _send([e for c in characters[i:i + 20] for e in c])
            time.sleep(0.01)
