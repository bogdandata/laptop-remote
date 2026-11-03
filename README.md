# Laptop Remote

Control your Windows laptop from your phone over your home Wi-Fi: music, volume, apps, typing —
and you can also **see the laptop screen, click on it, and use your phone as a touchpad and keyboard**.

Nothing gets installed on the phone. The laptop runs a small program, and the phone opens it in
its browser (Chrome, Safari…). There is **no PIN**: you connect a phone once with a one-time code
(or a link), and after that it just works — until you disconnect it.

| Tab on the phone | What you can do |
|---|---|
| **Remote** | Music (previous / play-pause / next) · Volume (down / mute / up, hold to keep changing) · your apps and websites from `config.ini` · Lock screen · Restart · Shut down (restart and shut down ask first) |
| **Screen** | A live picture of the laptop screen. Tap = click there · Hold = right click · Scroll buttons · Pinch to zoom |
| **Mouse** | The phone becomes a touchpad: slide to move, tap to click, tap with 2 fingers for a right click, slide 2 fingers to scroll, "Hold left" to drag |
| **Keyboard** | Esc, Tab, Win, Alt+Tab, arrows, Backspace, Enter, Ctrl+C, Ctrl+V, and typing any text into the active window |
| **Settings** | Phones connected to the laptop · Disconnect this phone · Disconnect all phones · Stop the remote |

All you need is Python. No extra packages are required (no `pip install`). Keys and the mouse are
sent with `ctypes` (part of Python), the screen picture is made with Windows' own drawing functions,
and shut down / restart use the `shutdown` command that is built into every Windows.

**New in version 2:** no PIN (a one-time code or link instead), screen view with clicking, touchpad,
keyboard keys, disconnecting phones, stopping from the phone or with `stop.bat`, several laptops, Tailscale.

---

## Contents

1. [Install Python](#1-install-python)
2. [Download the project](#2-download-the-project)
3. [Start the remote](#3-start-the-remote)
4. [Connect your phone](#4-connect-your-phone)
5. [Using the remote](#5-using-the-remote)
6. [Stop the remote, disconnect phones](#6-stop-the-remote-disconnect-phones)
7. [More laptops](#7-more-laptops)
8. [Away from home: hotspot or Tailscale](#8-away-from-home-hotspot-or-tailscale)
9. [Add your own apps and websites](#9-add-your-own-apps-and-websites)
10. [Windows Firewall — allow it only on private networks](#10-windows-firewall--allow-it-only-on-private-networks)
11. [Make your network "private"](#11-make-your-network-private)
12. [Other settings](#12-other-settings)
13. [Start automatically with Windows](#13-start-automatically-with-windows)
14. [Update to a new version](#14-update-to-a-new-version)
15. [Troubleshooting](#15-troubleshooting)
16. [Security](#16-security)

---

## 1. Install Python

**First, check whether you already have it:**

1. Press the **Windows** key, type `cmd` and press **Enter**. A black window opens.
2. Type `py --version` and press **Enter**. If it says the command was not found, also try `python --version`.
3. If it prints something like `Python 3.13.1`, you already have Python. Go to section 2.
   (Version 3.8 or newer is needed.)

**If you don't have it, install it:**

1. Open <https://www.python.org/downloads/> and click the yellow **Download Python …** button.
2. Run the downloaded file and follow the steps:
   - If the first screen has a **"Add python.exe to PATH"** checkbox, **make sure to tick it**
     (at the bottom of the window), then click **Install Now**.
   - If it installs the **"Python install manager"**, just install it to the end. If a black window
     later asks whether to install Python, answer yes (type `Y` and press **Enter**).
3. Close all black `cmd` windows, open a new one and check again with `py --version`.

Another way: open the **Microsoft Store**, search for "Python" and install the latest **Python 3**
published by *Python Software Foundation*.

## 2. Download the project

**Option A — in the browser (ZIP):**

1. On the laptop, open <https://github.com/bogdandata/laptop-remote>.
2. Click the green **`<> Code`** button above the list of files, then **Download ZIP**.
   The file `laptop-remote-main.zip` is downloaded (usually to **Downloads**).
3. **Unblock the ZIP** (so Windows doesn't stop you with warnings later): right-click the ZIP →
   **Properties** → at the bottom tick **Unblock** → **OK**. If there is no such option, just continue.
4. Right-click the ZIP → **Extract All…** → **Extract**. Use the extracted folder, not the ZIP itself.

**Option B — with one command** (in a PowerShell window or the VS Code terminal). It downloads the project
into **Downloads\laptop-remote-main** and starts it:

```powershell
[Net.ServicePointManager]::SecurityProtocol = 'Tls12'; cd $HOME\Downloads; Invoke-WebRequest https://github.com/bogdandata/laptop-remote/archive/refs/heads/main.zip -OutFile laptop-remote.zip -UseBasicParsing; Expand-Archive laptop-remote.zip -DestinationPath . -Force; cd laptop-remote-main; py server.py
```

Run this long command only the first time (to update later, see [section 14](#14-update-to-a-new-version)).

In the project folder you should see:

```
start.bat        ← double-click to start the remote
stop.bat         ← double-click to stop it (even if you can't find its window)
config.ini       ← your settings and the list of apps
server.py        ← the program itself
actions.py       ← the actions the laptop performs
web\index.html   ← the page the phone shows
README.md        ← this guide
```

## 3. Start the remote

**Double-click `start.bat`** (or, in the VS Code terminal, inside the project folder: `py server.py`).
A black window opens. The first time it looks roughly like this:

```
==================================================================
  LAPTOP REMOTE — running on “MY-LAPTOP”
==================================================================
  No phone is connected to this laptop yet.

  CONNECT A PHONE (the code works once, for 15 minutes):

    1. On the phone, open:
         http://192.168.1.23:8765          at home (the same Wi-Fi as the laptop)
         Away from home (5G)? Install Tailscale on the laptop and the phone (README, section 8).

    2. Type this code:   K7PQ-4XMZ

  Or open this link on the phone (it is already copied, e.g. to e-mail it):
      http://192.168.1.23:8765/?code=K7PQ-4XMZ

  Apps on the list: 5 (the list is in config.ini)
==================================================================
  Type a letter here and press Enter:
      L   new code for a phone
      D   disconnect all phones (their access stops working)
      Q   stop the remote

  Keep this window open while you use the remote (you can minimize it).
  To stop: type Q and Enter, press Ctrl+C, close the window, or run stop.bat.
==================================================================
```

- **Keep that window open** while you use the remote (you can minimize it). Every action from the phone
  shows up in it, e.g. `20:15:03  192.168.1.50     Android phone: volume_up`.
- **The first time**, Windows will probably show a Windows Firewall window: follow
  [section 10](#10-windows-firewall--allow-it-only-on-private-networks).
- If Windows warns you when you double-click ("Windows protected your PC" or "The publisher could not be
  verified"), click **More info → Run anyway**, or **Run**. This doesn't happen if you unblocked the ZIP.

## 4. Connect your phone

You do this **once per phone**. There is no PIN.

1. The phone must be on the **same Wi-Fi** as the laptop (not on mobile data, not on a "guest" network).
2. On the phone, open the browser and type the address from the black window, e.g. `http://192.168.1.23:8765`
   (with `http://` and the `:8765` at the end). The page **Connect this phone** opens.
3. **Type the code** from the black window (e.g. `K7PQ-4XMZ`, small or capital letters, the dash is optional)
   and tap **Connect**. The page says "Connected to …" and the remote opens.
4. **Add the page to your home screen**, so it opens like an app:
   - Android (Chrome): menu **⋮** → **Add to Home screen**
   - iPhone (Safari): the share button **□↑** → **Add to Home Screen**.
     **On iPhone the icon has its own memory**, so it asks to connect once more: open the icon, type
     **L** + **Enter** on the laptop for a new code, and type that code in the icon. (Tip: on iPhone you can
     add the icon first and connect only there.)

From now on just open the page or the icon. The phone stays connected, also after you restart the laptop.

About the code:
- It **works only once** and **only for 15 minutes**, and also stops working when the remote stops.
- Need a new one (it expired, or for another phone)? In the black window type **L** and press **Enter**.
- Instead of typing it, you can open the **link** from the window on the phone (it contains the code).
  It is already copied on the laptop, so you can paste it (Ctrl+V) into an e-mail or a message to yourself.
  Open it in the browser you use for the remote (on iPhone: Safari).
- Private mode, or a browser that deletes its data (like the DuckDuckGo flame button), forgets the connection.
- If the phone can't open the address, the window lists other addresses of the laptop. Try those
  (the right one usually starts with `192.168.`).

## 5. Using the remote

**Remote tab** — music, volume, apps, lock, restart, shut down.
- Music buttons work with the program that is playing (Spotify, YouTube in a browser, VLC…), like the media keys of a keyboard.
- Volume: one tap = one step (2%). Hold **Volume down** or **Volume up** to keep changing it. **Mute** again turns the sound back on.
- Restart and Shut down ask "Are you sure?" first, then happen after 5 seconds.

**Screen tab** — a live picture of the laptop's main screen.
- **Tap** on the picture = left click exactly there. **Hold** = right click. Two quick taps = double click.
- **Scroll up / Scroll down** buttons turn the mouse wheel.
- **Fast / Normal / Sharp** picks the picture quality. Fast is smoother on a slow Wi-Fi, Sharp shows small text better.
  Expect a few pictures per second, like a slow video — fine for clicking, not for films.
- **Pause** stops the picture. The picture also stops by itself when you leave the tab or lock the phone, so it doesn't use data.
- Pinch to zoom; turn the phone sideways for a bigger picture.
- The keyboard button shows the keys and the text box under the picture.
- The blue circle shows where the laptop's mouse cursor is.

**Mouse tab** — the phone is a touchpad.
- Slide 1 finger = move the cursor · Tap = left click · Tap with 2 fingers = right click · Slide 2 fingers = scroll.
- **Hold left** keeps the left button pressed, so you can drag (move a window, select text). Tap **Let go** when you are done.
- **Slow / Normal / Fast** sets the cursor speed.

**Keyboard tab** — special keys and typing.
- Keys: Esc, Tab, Win (Start menu), Alt+Tab (switch window), arrows, Backspace, Enter, Ctrl+C (copy), Ctrl+V (paste).
- **Type text**: first click into the right place on the laptop (or tap it on the Screen tab), then write the text on the
  phone and tap **Type**. "Press Enter at the end" presses Enter after the text. Accented letters and emoji work too.

**Settings tab** — which phones are connected, disconnecting, stopping (see section 6).

## 6. Stop the remote, disconnect phones

There are two different things:
- **Stop the remote** = the program on the laptop stops. Phones **stay connected** for the next time you start it.
- **Disconnect a phone** = that phone **loses access**. To use it again it needs a new code.

**Stop the remote** — any of these:
- In its window (or the VS Code terminal): type **Q** and press **Enter**, or press **Ctrl+C**, or close the window.
- **Double-click `stop.bat`** in the project folder. It finds and stops the remote even if you can't see its
  window (for example a minimized or hidden VS Code terminal).
- On the phone: **Settings → Stop the remote**.

**Disconnect phones:**
- On the phone: **Settings → Disconnect this phone**, or **Disconnect all phones**.
- On the laptop, in the remote's window: type **D** and press **Enter** (all phones; links that were not used yet stop working too).
- A phone that is not used for **30 days** is disconnected automatically (you can change this, see section 12).

## 7. More laptops

Do sections 2–4 on each laptop: download the project, start it, and type that laptop's code on your phone.
You can send yourself the GitHub link (or the command from section 2) by e-mail and open it on the other laptop.

Each laptop gets its own page and its **own icon** on the phone, named after the laptop. To change the name,
set `name =` in that laptop's `config.ini` (section 12).

A web page alone can't control a computer (browsers don't allow that, for safety), so the remote must run on
each laptop you want to control.

## 8. Away from home: hotspot or Tailscale

**Without home Wi-Fi — the phone's hotspot** (no extra programs):
1. Turn on the hotspot on the phone and connect the laptop to it.
2. When Windows asks whether the PC should be discoverable on this network, choose **Yes** (that makes it private).
3. Start the remote **after** connecting. It shows the laptop's new address.
4. The first time, connect the phone again with a new code (type **L** + **Enter**). The address is different
   from home, so the phone gets a separate page for it.

The laptop then uses the phone's mobile data for its own internet. On Android, USB tethering (cable) works the same way.

**From anywhere over the internet (5G, another Wi-Fi) — Tailscale** (a free extra program, installed by you):

When the phone is on 5G, your home router lets nobody in from outside, so something has to connect the phone and the
laptop. Tailscale does that: it makes a private, encrypted network of your own devices, without changing anything on
the router. It is free for personal use.

1. **On the laptop:** open <https://tailscale.com/download>, download Tailscale for Windows, install it and sign in
   (with a Google, Microsoft or Apple account).
2. **On the phone:** install **Tailscale** from the App Store / Google Play, open it, sign in with the **same account**,
   and allow it to add a VPN configuration. Leave it switched on (it runs in the background).
3. **Start the remote again** on the laptop. Its window now shows a second address, which starts with `100.` and says
   **from anywhere, also on 5G (Tailscale)**. A code is shown too (if not, type **L** + **Enter**).
4. **On the phone, open that `100.…` address** and type the code. Add it to the home screen (on iPhone: add the icon
   first, open it, and type the code there).

Tip: use the `100.…` address always, also at home — it works on Wi-Fi and on 5G, so you need only one icon.
The laptop has to be switched on, connected to the internet, and the remote has to run on it.

If the `100.…` address doesn't open, Windows may count the Tailscale network as public. Allow the remote on it as in
section 10, or make it private (section 11 — its name in `Get-NetConnectionProfile` is usually "Tailscale").

Don't open a port on your router to reach the remote from the internet: then anyone could try to reach it.
Use Tailscale instead.

## 9. Add your own apps and websites

Open `config.ini`: right-click → **Open with** → **Notepad**. Find the `[programs]` section:

```ini
[programs]
Notepad = notepad.exe
Calculator = calc.exe
Downloads = %USERPROFILE%\Downloads
YouTube = https://www.youtube.com
Google = https://www.google.com
```

Each line is one button on the phone: **left of `=` is the button name, right of it is what opens** —
a program (`C:\Program Files\VideoLAN\VLC\vlc.exe`), a website (`https://…`), or a folder or file (`D:\Movies`).

After a change, **save the file (Ctrl+S)** and refresh the page on the phone. No restart needed.

**How to find the path to a program:** press the **Windows** key, type its name, right-click it →
**Open file location** (if you get a shortcut, right-click it → **Open file location** again). Hold **Shift**,
right-click the `.exe` file → **Copy as path**, and paste it after `Name =`. The quotes are removed automatically.

```ini
Chrome = C:\Program Files\Google\Chrome\Application\chrome.exe
VLC = C:\Program Files\VideoLAN\VLC\vlc.exe
Spotify = %APPDATA%\Spotify\Spotify.exe
Netflix = https://www.netflix.com
Movies = D:\Movies
```

- A line that starts with `;` is a comment (no button).
- Spotify from the Microsoft Store: write `Spotify = spotify:`.
- A line written wrongly (e.g. without `=`) is skipped, and a warning with its line number is shown in the black
  window and on the phone.
- The phone can open **only what is on this list**.

## 10. Windows Firewall — allow it only on private networks

The firewall has to let the phone connect to the laptop. Allow it **only on private (home) networks**.

**Option A — when the window appears by itself (first start):** in the window
**"Windows Defender Firewall has blocked some features of this app"** tick **only Private networks**,
untick **Public networks**, and click **Allow access**.

**Option B — by hand:**
1. Press **Windows + R**, type `firewall.cpl` and press **Enter**.
2. On the left, click **Allow an app or feature through Windows Defender Firewall** → **Change settings**.
3. Find **Python** (there may be several). Tick **Private**, leave **Public** empty. If Python is not in the list:
   **Allow another app…** → **Browse…** → `python.exe` (in a `cmd` window, `where python` shows where it is) →
   **Network types…** → only **Private** → **Add**.
4. Click **OK**.

**Option C — one command** (Windows key → type `powershell` → right-click **Windows PowerShell** → **Run as administrator**):

```powershell
New-NetFirewallRule -DisplayName "Laptop Remote" -Direction Inbound -Protocol TCP -LocalPort 8765 -Action Allow -Profile Private
```

To remove it later: `Remove-NetFirewallRule -DisplayName "Laptop Remote"`

**If you clicked "Cancel" in the firewall window**, Windows created a rule that **blocks** Python (and it is
stronger than an allowing rule). Press **Windows + R**, type `wf.msc`, open **Inbound Rules**, right-click every
**Python** rule with a **red sign** → **Delete**. Start the remote again and follow option A.

> If your antivirus has its own firewall (ESET, Kaspersky, Bitdefender, Norton…), allow Python there (home network only).

## 11. Make your network "private"

The permission from section 10 only works if your home Wi-Fi is marked as **private** in Windows.

- **Windows 11:** Start → Settings → Network & internet → Wi-Fi → click your network → **Network profile type: Private network**.
- **Windows 10:** Start → Settings → Network & Internet → Wi-Fi → click your network → **Network profile: Private**.
- **PowerShell (as administrator):** `Get-NetConnectionProfile` shows the networks; then
  `Set-NetConnectionProfile -InterfaceAlias "Wi-Fi" -NetworkCategory Private`

> Don't set a café, hotel or airport network to private. The remote is meant not to work there.

## 12. Other settings

In `config.ini`, section `[server]`. After a change, stop the remote and start it again.

| Setting | What it does |
|---|---|
| `name =` | The laptop's name on the phone (and on its home screen icon). Empty = the Windows computer name. |
| `port = 8765` | The port. Change it only if it is taken (then also in the firewall rule from option C). |
| `volume_step = 1` | How much one tap changes the volume: 1 = 2%, 2 = 4%… up to 10. |
| `forget_phones_after_days = 30` | A phone not used for this many days is disconnected automatically. `0` = never. |

The connected phones are stored in `devices.json` in the project folder. It holds only a fingerprint of each
phone's key, not the key itself. Deleting the file disconnects all phones.

## 13. Start automatically with Windows

After **Restart** from the phone, the remote does not start again by itself. To make it start whenever you sign in:

1. Press **Windows + R**, type `shell:startup` and press **Enter**. The **Startup** folder opens.
2. Right-click `start.bat` → **Create shortcut** (Windows 11: under **Show more options**).
3. Drag the shortcut into the **Startup** folder.

The remote starts when you sign in to Windows (not on the sign-in screen itself). Its window is always visible
on the laptop — the remote never runs hidden.

## 14. Update to a new version

1. Stop the remote (double-click `stop.bat`).
2. Download the new ZIP (section 2, option A) and extract it.
3. Copy **`config.ini`** and **`devices.json`** from your old folder into the new one (replace). This keeps your apps,
   settings and connected phones.
4. Start the remote from the new folder.

## 15. Troubleshooting

**The phone can't open the page (it keeps loading, or "site can't be reached"):**
- Is the remote running on the laptop (black window, or the VS Code terminal)?
- Is the phone on the same Wi-Fi (not mobile data, not a "guest" network)? Is a VPN on? Turn it off.
- Check the firewall ([section 10](#10-windows-firewall--allow-it-only-on-private-networks)), especially the part
  about "Cancel", and that the network is private ([section 11](#11-make-your-network-private)).
- Try the other addresses the window shows. Some routers have "AP isolation" / "Client isolation" turned on,
  which hides devices from each other — turn it off in the router.

**"This code is wrong, has expired or was already used":** in the remote's window type **L** + **Enter** and use the new code.

**"Connect this phone" appears although the phone was connected:** the phone was disconnected (from Settings,
with **D**, or after 30 days unused), the laptop got a new address from the router, or (on iPhone) you opened the
home screen icon, which has its own memory. Get a new code (**L** + **Enter**) and type it.
To keep the address always the same, set a "DHCP reservation" for the laptop in your router.

**The phone keeps forgetting the connection:** the connection is saved in the phone's browser. Private mode, or a
browser that deletes its data (for example the flame button in DuckDuckGo), deletes it too. Open the link in the browser
you use for the remote (on iPhone: Safari, then Add to Home Screen) and don't use private mode for it. In an e-mail app,
a tap on a link can open it in the app's own small browser — then long-press the link, choose **Copy**, and paste it into
the address bar of your normal browser.

**"No connection to the laptop":** the remote is stopped, the laptop is asleep (or its lid is closed), or the
phone is on another network.

**The phone can still control the laptop after you stopped it:** another copy is still running somewhere.
Double-click `stop.bat`, it stops every copy.

**Screen picture is black, or says the screen may be locked:** the laptop screen is locked or asleep. Windows
doesn't let programs see the lock screen, the sign-in screen or "Do you want to allow this app to make changes"
windows. Unlock the laptop.

**The screen picture is slow:** choose **Fast**. A weak Wi-Fi signal makes it slower.

**Only one screen is shown:** with several monitors, the remote shows and clicks on the main one.

**Music, volume, keys or the mouse don't work while the screen is locked:** Windows doesn't accept them then. Unlock it.

**Typing, keys or clicks don't work in one program:** if that program runs **as administrator**, Windows doesn't let
normal programs control it. Then also start `start.bat` with right-click → **Run as administrator**.

**A program opens behind other windows:** Windows sometimes protects the window you are working in. Click it on the taskbar.

**"the remote is already running on this laptop":** use the window where it already runs, or double-click `stop.bat` and start again.

**"the server cannot start on port 8765":** another program uses that port. Close it, or change `port` in `config.ini`.

**"Python is not installed, or it was not added to PATH":** repeat [section 1](#1-install-python).

**A shutdown started by accident:** within 5 seconds, on the laptop press **Windows + R**, type `shutdown /a`, press **Enter**.

## 16. Security

- **No PIN to guess.** A phone connects with a code (or link) that works **once**, for **15 minutes**. Then the phone gets
  its own long secret key. The laptop stores only a fingerprint of it.
- **You can take access away at any time:** disconnect one phone or all phones (phone Settings, or **D** in the window).
  Phones not used for 30 days are disconnected automatically.
- **The remote is always visible on the laptop.** Its window shows every action. While a phone watches the screen,
  the window says `SCREEN VIEW started on …` and its title changes to **"SCREEN IS BEING VIEWED"**.
- Only devices on your home network (or your own Tailscale network) can reach it. 5 failed attempts block a device for 5 minutes.
- The phone can open only the apps on your list.
- On the home Wi-Fi the connection is plain `http` (not encrypted). That is fine on a home network you trust; don't use the
  remote on public networks. Over Tailscale the connection is encrypted.
- Use the remote only on your own computers.
