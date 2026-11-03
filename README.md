# Laptop Remote

Control your Windows laptop from your phone over your home Wi-Fi. Nothing gets
installed on the phone: the laptop runs a small web server, and you open the laptop's
address in the phone's browser (Chrome, Safari…) to get a page with big buttons.

| Section on the phone | Buttons |
|---|---|
| Music | Previous · Play / Pause · Next |
| Volume | Volume down · Mute · Volume up (hold a button to keep changing the volume) |
| Apps & websites | your own list from `config.ini` (e.g. Chrome, YouTube, Netflix…) |
| Type text on the laptop | write text on the phone, and the laptop types it into the active window |
| System | Lock screen · Restart · Shut down (restart and shut down ask for confirmation on the phone) |

All you need is Python. No extra packages are required (no `pip install`).
Music, volume and typing keys are sent with `ctypes` (part of Python). Shut down and
restart use the `shutdown` command that is built into every Windows.

---

## Contents

1. [Install Python](#1-install-python)
2. [Download the project from GitHub (ZIP)](#2-download-the-project-from-github-zip)
3. [Start the server](#3-start-the-server)
4. [Connect your phone](#4-connect-your-phone)
5. [Add your own apps and websites](#5-add-your-own-apps-and-websites)
6. [Windows Firewall — allow it only on private networks](#6-windows-firewall--allow-it-only-on-private-networks)
7. [Make your network "private"](#7-make-your-network-private)
8. [Other settings (port, PIN, volume step)](#8-other-settings-port-pin-volume-step)
9. [Start automatically with Windows](#9-start-automatically-with-windows)
10. [Troubleshooting](#10-troubleshooting)
11. [Security](#11-security)

---

## 1. Install Python

**First, check whether you already have it:**

1. Press the **Windows** key, type `cmd` and press **Enter**. A black window opens.
2. Type `py --version` and press **Enter**. If it says the command was not found,
   also try `python --version`.
3. If it prints something like `Python 3.13.1`, you already have Python. Go to section 2.
   (Version 3.8 or newer is needed.)

**If you don't have it, install it:**

1. Open <https://www.python.org/downloads/> and click the yellow **Download Python …** button.
2. Run the downloaded file and follow the steps:
   - If the first screen has a **"Add python.exe to PATH"** checkbox,
     **make sure to tick it** (at the bottom of the window), then click **Install Now**.
   - If it installs the **"Python install manager"**, just install it to the end. If a black
     window later asks whether to install Python, answer yes (type `Y` and press **Enter**).
3. Close all black `cmd` windows, open a new one and check again with `py --version`.

Another way: open the **Microsoft Store**, search for "Python" and install the latest
**Python 3** published by *Python Software Foundation*.

## 2. Download the project from GitHub (ZIP)

1. On the laptop, open the project page: <https://github.com/bogdandata/laptop-remote>
   (if the repository is private, sign in to GitHub first).
2. Click the green **`<> Code`** button above the list of files.
3. In the menu that opens, click **Download ZIP**. The file `laptop-remote-main.zip` is
   downloaded (usually to your **Downloads** folder).
4. **Unblock the ZIP** (so Windows doesn't stop you with warnings later): right-click the ZIP →
   **Properties** → at the bottom tick **Unblock** → **OK**.
   If there is no such option, that's fine, just continue.
5. Right-click the ZIP → **Extract All…** → choose where (e.g. **Documents**) → **Extract**.
   Don't run the files directly from inside the ZIP; use the extracted folder.

In the extracted `laptop-remote-main` folder you should see:

```
start.bat        ← this is what you run (double-click)
config.ini       ← your settings and the list of apps
server.py        ← the web server
actions.py       ← the actions the laptop performs
web\index.html   ← the page the phone shows
README.md        ← this guide
```

## 3. Start the server

**Double-click `start.bat`.** A black window opens and looks roughly like this:

```
==============================================================
  LAPTOP REMOTE — the server is running
==============================================================
  On your phone (on the same Wi-Fi), open this address in the browser:

      http://192.168.1.23:8765

  PIN for the phone:   482913
  First start: a PIN was created and saved in config.ini.
  It stays the same next time.

  Apps on the list: 5 (the list is in config.ini)
==============================================================
  Keep this window open while you use the remote (you can
  minimize it). To stop the server, close the window or press Ctrl+C.
==============================================================
```

- Your address and PIN will be different. **Write them down**, you need them on the phone.
- The PIN is created only on the first start and saved in `config.ini`, so it stays the same.
- **Keep that window open** while you use the remote (you can minimize it to the taskbar).
  Every command that arrives from the phone shows up in it, e.g.
  `20:15:03  192.168.1.50     command: volume_up`.
- **The first time**, Windows will probably show a Windows Firewall window. Then do what
  [section 6](#6-windows-firewall--allow-it-only-on-private-networks) says.

> If Windows shows a warning when you double-click ("Windows protected your PC" or
> "The publisher could not be verified"), click **More info → Run anyway**, or **Run**.
> The warning does not appear if you unblocked the ZIP (step 4 in section 2).

## 4. Connect your phone

1. The phone must be on the **same Wi-Fi** as the laptop (not on mobile data and not on a "guest" network).
2. On the phone, open the browser and in the address bar (at the top, where you type websites)
   type exactly the address from the black window, e.g. `http://192.168.1.23:8765` — with `http://`
   at the start and the colon and number at the end.
3. Enter the **PIN** from the black window and tap **Connect**.

The phone remembers the PIN, so you don't have to type it again next time.

**Tip:** add the page to your phone's home screen, so it opens like an app:
- Android (Chrome): menu **⋮** → **Add to Home screen**
- iPhone (Safari): the share button **□↑** → **Add to Home Screen**

**How the buttons work:**
- **Music**: works with the program that is currently playing (Spotify, YouTube in a browser, VLC…),
  just like the media keys on a keyboard.
- **Volume**: one tap changes the volume by one step (2%). If you hold **Volume down** or
  **Volume up**, the volume keeps changing until you let go. Tapping **Mute** again turns the sound back on.
- **Type text**: on the laptop, first click into the window where the text should go (e.g. Word or
  the YouTube search box). Then write the text on the phone and tap **Type**. If you tick
  "Press Enter at the end", the laptop presses Enter after the text. Accented letters and emoji work too.
- **Shut down / Restart**: the phone asks "Are you sure?" first. After you confirm, the laptop shuts down
  or restarts in 5 seconds.

## 5. Add your own apps and websites

Open `config.ini`: right-click → **Open with** → **Notepad**. Find the `[programs]` section:

```ini
[programs]
Notepad = notepad.exe
Calculator = calc.exe
Downloads = %USERPROFILE%\Downloads
YouTube = https://www.youtube.com
Google = https://www.google.com
```

Each line is one button on the phone: **left of `=` is the button name, right of it is what opens.**
That can be:

- **a program**: the path to an `.exe` file, e.g. `C:\Program Files\VideoLAN\VLC\vlc.exe`
- **a website**: an address that starts with `https://`
- **a folder or file**: e.g. `D:\Movies` or `C:\Users\Mark\Documents\list.xlsx`

After a change, **save the file (Ctrl+S)**. You don't need to restart the server, just refresh the
page on the phone (pull it down, or open it again).

**How to find the path to a program:**

1. Press the **Windows** key and type the program's name (e.g. `Chrome`).
2. Right-click it → **Open file location**.
   If a folder with a shortcut opens, right-click the shortcut → **Open file location** again.
3. When you see the real `.exe` file, hold **Shift**, right-click the file → **Copy as path**.
4. In `config.ini`, write `Name =` and paste (**Ctrl+V**). You don't have to remove the quotes
   Windows adds, they are removed automatically.

Examples you can copy:

```ini
Chrome = C:\Program Files\Google\Chrome\Application\chrome.exe
VLC = C:\Program Files\VideoLAN\VLC\vlc.exe
Spotify = %APPDATA%\Spotify\Spotify.exe
Netflix = https://www.netflix.com
Movies = D:\Movies
```

Notes:
- A line that starts with `;` is a comment and doesn't create a button. You can use that to turn a line off for a while.
- `%USERPROFILE%` is your user folder (`C:\Users\YourName`), and `%APPDATA%` is the hidden folder
  `C:\Users\YourName\AppData\Roaming`.
- If Spotify was installed from the Microsoft Store, the path above won't work. Then write
  `Spotify = spotify:` (that opens the Spotify app).
- If a line is not written correctly (e.g. the `=` is missing), that line is skipped, and a warning
  with the line number is shown both in the black window and on the phone, below the app buttons.
- The phone can open **only what is on this list**, nothing else.

## 6. Windows Firewall — allow it only on private networks

The firewall has to let the phone connect to the laptop. Allow it **only on private (home)
networks**, not on public networks (café, hotel, airport).

### Option A — when the window appears by itself (on the first start)

When you start `start.bat` for the first time, Windows shows the window
**"Windows Defender Firewall has blocked some features of this app"**:

1. Tick **only** **Private networks**.
2. **Untick** **Public networks**.
3. Click **Allow access**. If Windows asks for an administrator password, enter it.

### Option B — by hand (if the window didn't appear, or you closed it)

1. Press **Windows + R**, type `firewall.cpl` and press **Enter**.
2. On the left, click **Allow an app or feature through Windows Defender Firewall**.
3. Click **Change settings** at the top right.
4. Find **Python** in the list (there may be more than one, e.g. "Python" and "python.exe"). For each one,
   tick the **Private** column and leave the **Public** column **empty**.
5. If Python is not in the list: **Allow another app…** → **Browse…** → choose `python.exe` →
   **Network types…** → tick only **Private** → **OK** → **Add**.
   (Where is `python.exe`? In a black `cmd` window type `where python`; the first path is the one.)
6. Click **OK**.

### Option C — with one command (for advanced users)

Press the **Windows** key, type `powershell`, right-click **Windows PowerShell** →
**Run as administrator**, and paste:

```powershell
New-NetFirewallRule -DisplayName "Laptop Remote" -Direction Inbound -Protocol TCP -LocalPort 8765 -Action Allow -Profile Private
```

This opens only port 8765 and only on private networks. To delete that rule later:

```powershell
Remove-NetFirewallRule -DisplayName "Laptop Remote"
```

### If you clicked "Cancel" in the firewall window

Then Windows creates a rule that **blocks** Python, and a blocking rule is stronger than a rule
that allows. Delete it:

1. Press **Windows + R**, type `wf.msc` and press **Enter**.
2. On the left, click **Inbound Rules**.
3. In the list, look for rules named **Python** (or **python.exe**) that have a **red sign**
   (that means Block). Right-click each of them → **Delete**.
4. Close the black server window and start `start.bat` again. The firewall window appears again;
   then follow option A.

> If you use an antivirus with its own firewall (e.g. ESET, Kaspersky, Bitdefender, Norton),
> give Python the permission (home network only) in that program instead.

## 7. Make your network "private"

The permission from section 6 only works if your home Wi-Fi is marked as a **private** network
in Windows. Sometimes Windows sets it to public.

**Windows 11:**
1. **Start** → **Settings** → **Network & internet** → **Wi-Fi**.
2. Click the item with your network's name (e.g. "**MyNetwork properties**").
3. Under **Network profile type**, choose **Private network**.

**Windows 10:**
1. **Start** → **Settings** → **Network & Internet** → **Wi-Fi**.
2. Click your network's name.
3. Under **Network profile**, choose **Private**.

**With PowerShell (as administrator):**

```powershell
Get-NetConnectionProfile
```

The `NetworkCategory` column says `Public` or `Private`, and the `InterfaceAlias` column shows the
name of the network adapter (usually "Wi-Fi"). To change it to private:

```powershell
Set-NetConnectionProfile -InterfaceAlias "Wi-Fi" -NetworkCategory Private
```

> **Don't** set a network in a café, hotel or airport to private. The remote is meant not to
> work there, and that's how it should be.

## 8. Other settings (port, PIN, volume step)

In `config.ini`, in the `[server]` section. After a change, close the black window and start `start.bat` again.

| Setting | What it does |
|---|---|
| `port = 8765` | The server's port. Change it only if it is already taken. If you change it, also change the number in the firewall rule from option C. |
| `pin = 482913` | The PIN for the phone (digits only, 4 to 12). It is written automatically on the first start. **For a new random PIN**, delete the number (leave just `pin =`) and start `start.bat` again. You can also type your own PIN. |
| `volume_step = 1` | How much one tap changes the volume: 1 = 2%, 2 = 4%… up to 10. |

## 9. Start automatically with Windows

After **Restart** from the phone, the server does not start again by itself, and the phone can't
control the laptop until you start `start.bat` again. To make the server start by itself:

1. Press **Windows + R**, type `shell:startup` and press **Enter**. The **Startup** folder opens.
2. In another window, right-click `start.bat` → **Create shortcut**.
   On Windows 11 it is under **Show more options**.
3. Drag the new shortcut into the **Startup** folder.

From then on, the server starts as soon as you sign in to Windows (after you enter your Windows
password or PIN). While the laptop is on the sign-in screen, the server isn't running yet.

## 10. Troubleshooting

**The phone can't open the page (it keeps loading, or says "site can't be reached"):**
- Is the black server window open?
- Is the phone on the same Wi-Fi, and not on mobile data or a "guest" network?
- Did you type `http://` (not `https://`) and the port, e.g. `http://192.168.1.23:8765`?
- Check the firewall ([section 6](#6-windows-firewall--allow-it-only-on-private-networks)), especially
  the part about clicking Cancel, and that the network is private ([section 7](#7-make-your-network-private)).
- If the server prints more than one address, try each of them. The right one usually starts with `192.168.`.
- If a VPN is turned on on the phone or the laptop, turn it off.
- Some routers have an "AP isolation" / "Client isolation" option turned on, which doesn't let devices
  see each other. Turn it off in the router's settings.

**It worked, then it stopped:**
- The laptop may have gone to sleep, or its lid was closed. While the laptop sleeps, the server doesn't run.
- The router may have given the laptop a new address. Check it in the black window. To keep it always
  the same, set up a "DHCP reservation" (a fixed address) for the laptop in your router.

**Music, volume or typing don't work while the screen is locked:** while the screen is locked, Windows
usually doesn't accept keys from other programs. If any of these don't work then, unlock the laptop.
Shut down and restart work even when the screen is locked.

**"Wrong PIN":** check the PIN in the black window (or in `config.ini`) and enter it again.
There is also a **Change PIN** button at the bottom of the page. After 5 wrong attempts, the phone is
blocked for 5 minutes (protection against guessing).

**A music button doesn't work:** play/pause and next/previous work like the media keys on a keyboard,
with programs that support them (Spotify, YouTube in a browser, VLC, Windows Media Player…). If nothing
is playing, there is nothing for the command to act on.

**Text isn't typed:**
- An input window must be active on the laptop (with a blinking cursor).
- If the active program was started **as administrator**, Windows doesn't let normal programs type into it.
  Then also start `start.bat` with right-click → **Run as administrator**.

**A program opens behind other windows** (it only flashes on the taskbar): Windows sometimes does this to
protect the window you are working in. Click the program on the taskbar.

**An app button shows an error:** check the path in `config.ini` (does the file really exist there?).
The exact error is shown on the phone and in the black window.

**"Python is not installed, or it was not added to PATH":** repeat the installation from
[section 1](#1-install-python). With the classic installer, make sure to tick "Add python.exe to PATH".

**"the remote is already running on this laptop":** it is already running in another black window or
VS Code terminal. Use that one, or stop it there first (Ctrl+C or close the window).

**"the server cannot start on port 8765":** another program is using this port. Close it, or change the
`port` in `config.ini`.

**The phone can still control the laptop after you stopped the server:** another copy is still running
somewhere (e.g. a minimized black window). Press **Ctrl+Shift+Esc** to open Task Manager, click each
**Python** entry and click **End task**.

**You started a shutdown by accident:** shut down and restart begin after 5 seconds. During that time,
on the laptop press **Windows + R**, type `shutdown /a` and press **Enter** to cancel.

## 11. Security

- The server accepts commands **only from devices on the home (private) network**, and only with the right PIN.
- After 5 wrong PINs, the device is blocked for 5 minutes.
- The phone can open only the apps and websites on your list in `config.ini`.
- The PIN is stored in `config.ini`, so don't send that file to other people.
- The connection is plain `http` (not encrypted), which is fine on a home network you trust. Don't use the
  remote on public networks — that's why the firewall permission is for private networks only.
- When you're not using it, just close the black server window.
