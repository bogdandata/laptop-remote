# Laptop Remote

Control a Windows laptop from your phone or from another computer: music, volume, apps, typing —
and you can also **see the laptop screen, click on it, and use your phone as a touchpad and keyboard**.

There are two ways to use it:

- **From anywhere** — any network, 5G, another country — **end-to-end encrypted** (new in version 3).
  Open the app at **<https://bogdandata.github.io/laptop-remote/>**, make an invitation and send it by e-mail.
  On the laptop, someone opens the link, downloads one file, starts it and clicks **Yes**. That's all.
  → [section 8](#8-control-from-anywhere-any-network-end-to-end-encrypted)
- **At home**, on the same Wi-Fi: start `start.bat` on the laptop and type a one-time code on the phone.
  → sections 1–6

Nothing gets installed on the phone: it uses its browser (Chrome, Safari…). There is **no PIN**: a device
is connected once, and after that it just works — until you disconnect it.

| Tab in the app | What you can do |
|---|---|
| **Remote** | Music (previous / play-pause / next) · Volume (down / mute / up, hold to keep changing) · your apps and websites from `config.ini` · Lock screen · Restart · Shut down (restart and shut down ask first) |
| **Screen** | A live picture of the laptop screen, and **a touchpad right under it**: tap the picture = click there, hold = right click; slide on the touchpad = move the mouse; Left / Hold / Right click and Scroll buttons; a keyboard button for keys and typing |
| **Touchpad** | A big touchpad for when you look at the laptop (or a TV) itself, with mouse buttons, speed, keys (Esc, Tab, Win, Alt+Tab, arrows, Backspace, Enter, Ctrl+C, Ctrl+V) and typing text |
| **Settings** | Devices connected to the laptop · Disconnect · Stop the remote · from anywhere also: your laptops, give another device access, update or remove Laptop Remote on the laptop |

On the laptop it needs only Python (the setup from an invitation brings its own private copy), with no extra
packages (no `pip install`). Keys and the mouse are sent with `ctypes` (part of Python), the screen picture is made
with Windows' own drawing functions, and shut down / restart use the `shutdown` command that is built into every
Windows. For control from anywhere it also uses Cloudflare's tunnel program, which it downloads by itself (section 8).

**New in version 3:** control from anywhere, end-to-end encrypted, with invitations by e-mail; several laptops in one
app; a one-file setup for a laptop far away; update and remove from far away; the laptop does not fall asleep on its charger.

---

## Contents

1. [Install Python](#1-install-python)
2. [Download the project](#2-download-the-project)
3. [Start the remote](#3-start-the-remote)
4. [Connect your phone](#4-connect-your-phone)
5. [Using the remote](#5-using-the-remote)
6. [Stop the remote, disconnect phones](#6-stop-the-remote-disconnect-phones)
7. [More laptops](#7-more-laptops)
8. [Control from anywhere (any network, end-to-end encrypted)](#8-control-from-anywhere-any-network-end-to-end-encrypted)
9. [Away from home without the app: hotspot or Tailscale](#9-away-from-home-without-the-app-hotspot-or-tailscale)
10. [Add your own apps and websites](#10-add-your-own-apps-and-websites)
11. [Windows Firewall — allow it only on private networks](#11-windows-firewall--allow-it-only-on-private-networks)
12. [Make your network "private"](#12-make-your-network-private)
13. [Other settings](#13-other-settings)
14. [Start automatically with Windows](#14-start-automatically-with-windows)
15. [Update to a new version](#15-update-to-a-new-version)
16. [Troubleshooting](#16-troubleshooting)
17. [Security](#17-security)

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

Run this long command only the first time (to update later, see [section 15](#15-update-to-a-new-version)).

In the project folder you should see:

```
start.bat            ← double-click to start the remote
stop.bat             ← double-click to stop it (even if you can't find its window)
update.bat           ← double-click to get the newest version (keeps your settings and phones)
tailscale-https.bat  ← double-click once for the secure link with Tailscale (section 9)
run.bat              ← used by the setup from an invitation (section 8)
uninstall.bat        ← removes Laptop Remote from the laptop: no autostart, all access deleted
config.ini           ← your settings and the list of apps
server.py            ← the program itself
actions.py           ← the actions the laptop performs
anywhere.py          ← control from anywhere (the tunnel, invitations, encrypted requests)
remote_crypto.py     ← the encryption (AES-256-GCM, with the OpenSSL that comes with Python)
docs\index.html      ← the app (the laptop serves it at home; GitHub Pages publishes it for anywhere)
docs\setup.html      ← the page an invitation opens: it makes the setup file
README.md            ← this guide
```

## 3. Start the remote

**Double-click `start.bat`.** You don't need VS Code or any other program for it. Tip: right-click `start.bat` →
**Send to** → **Desktop (create shortcut)**, then you can start the remote from the desktop.
A black window opens. The first time it looks roughly like this:

```
==================================================================
  LAPTOP REMOTE 3.0 — running on “MY-LAPTOP”
==================================================================
  No phone is connected to this laptop yet.

  CONNECT A PHONE (the code works once, for 15 minutes):

    1. On the phone, open:
         http://192.168.1.23:8765          at home (the same Wi-Fi as the laptop)
         Away from home (5G, another country)? Control from anywhere, below (README, section 8).

    2. Type this code:   K7PQ-4XMZ

  Or open this link on the phone (it is already copied, e.g. to e-mail it):
      http://192.168.1.23:8765/?code=K7PQ-4XMZ


  CONTROL FROM ANYWHERE (any network, end-to-end encrypted): starting...
      The app for your phone or another laptop:  https://bogdandata.github.io/laptop-remote/
      To add one: in the app tap “Add a laptop”, then type A here and paste the invitation.

  Apps on the list: 5 (the list is in config.ini)
  While it runs and the laptop is on its charger, the laptop does not go to sleep by itself.
==================================================================
  Type a letter here and press Enter:
      A   add a phone or laptop for control from anywhere (paste its invitation)
      L   new code for a phone
      D   disconnect all phones (their access stops working)
      Q   stop the remote

  Keep this window open while you use the remote (you can minimize it).
  To stop: type Q and Enter, press Ctrl+C, close the window, or run stop.bat.
==================================================================
```

- **Keep that window open** while you use the remote (you can minimize it). Every action from the phone
  shows up in it, e.g. `20:15:03  192.168.1.50     Android phone: volume_up`.
- A few seconds later it shows `Anywhere: ON — reachable through an encrypted tunnel (https://….trycloudflare.com)`.
  The first time it downloads Cloudflare's tunnel program first (section 8). To switch that off: `anywhere = no` in `config.ini`.
- **The first time**, Windows will probably show a Windows Firewall window: follow
  [section 11](#11-windows-firewall--allow-it-only-on-private-networks).
- If Windows warns you when you double-click ("Windows protected your PC" or "The publisher could not be
  verified"), click **More info → Run anyway**, or **Run**. This doesn't happen if you unblocked the ZIP.

## 4. Connect your phone

You do this **once per phone**. There is no PIN.

> **From anywhere** (also at home, with no code): use the app and an invitation, [section 8](#8-control-from-anywhere-any-network-end-to-end-encrypted).
> The steps below are for a phone on the same Wi-Fi as the laptop.

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

**Screen tab** — see the laptop and control it, all in one place.
- At the top: a live picture of the laptop's main screen. The blue circle shows where the laptop's mouse cursor is.
- **On the picture:** tap = left click exactly there · hold = right click · two quick taps = double click · pinch to zoom.
- **Right under the picture: a touchpad.** Slide 1 finger = move the mouse · tap = click where the cursor is ·
  tap with 2 fingers = right click · slide 2 fingers = scroll.
- Under the touchpad: **Left click**, **Hold left** (keeps the button pressed so you can drag; tap **Let go** when done),
  **Right click**, **Scroll up**, **Scroll down**.
- **Fast / Normal / Sharp** picks the picture quality (Fast is smoother on a slow connection, Sharp shows small text
  better). Expect a few pictures per second, like a slow video — fine for clicking, not for films.
- **Pause** stops the picture. It also stops by itself when you leave the tab or lock the phone, so it doesn't use data.
- The **keyboard** button shows the keys and the text box under it.
- **Turn the phone sideways:** the picture is on the left and the touchpad on the right.

**Touchpad tab** — a big touchpad, for when you look at the laptop (or a TV connected to it) and not at the phone.
- The same gestures and buttons as above, plus **Slow / Normal / Fast** cursor speed.
- Under it are the **keys** (Esc, Tab, Win = Start menu, Alt+Tab = switch window, arrows, Backspace, Enter, Ctrl+C = copy,
  Ctrl+V = paste) and **Type text**: click into the right place on the laptop first, then write the text on the phone and
  tap **Type** ("Press Enter at the end" presses Enter after it). Accented letters and emoji work too.

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
- A phone that is not used for **30 days** is disconnected automatically (you can change this, see section 13).

## 7. More laptops

**Easiest: the app from anywhere** (section 8). All your laptops are in one app, with a choice at the top. Add each one
with an invitation.

**At home on the Wi-Fi:** do sections 2–4 on each laptop: download the project, start it, and type that laptop's code on
your phone. You can send yourself the GitHub link (or the command from section 2) by e-mail and open it on the other
laptop. Each laptop gets its own page and its **own icon** on the phone, named after the laptop.

To change a laptop's name, set `name =` in that laptop's `config.ini` (section 13).

A web page alone can't control a computer (browsers don't allow that, for safety), so the remote must run on
each laptop you want to control.

## 8. Control from anywhere (any network, end-to-end encrypted)

Control a laptop from another network — 5G, another Wi-Fi, another country — from your phone's browser or from
another laptop's browser. Nobody has to change anything on a router, and nothing is installed on the phone.

```
 your phone / laptop     ── https ──►   Cloudflare tunnel   ──►   the laptop (Laptop Remote)
 (the app, a web page)                  sees only locked data
```

- The laptop connects **out** to the internet through Cloudflare's free tunnel. Laptop Remote downloads Cloudflare's
  official tunnel program `cloudflared.exe` once (from Cloudflare's GitHub page) and runs it while it runs.
- The tunnel gets a new address every time the laptop starts. The laptop leaves that address as an **encrypted note**
  on a free message service, ntfy.sh. Only your devices can open the note.
- **Every request and every answer is locked with AES-256-GCM** on one side and opened only on the other. Each device
  has its own key. Cloudflare and ntfy.sh see only locked data — not the screen, not what you type, not the address.
- **An invitation contains only a public key.** If someone else reads the e-mail, it is of no use to them: only the
  device that made the invitation can open the laptop's answer. And the laptop gives access only after someone at the
  laptop clicks **Yes** (or types the invitation into its window).

### Once: switch on the app's address (only the owner of the GitHub project)

The app is the page `docs/index.html`, published from this project by GitHub Pages:

1. On GitHub, open the project → **Settings** → **Pages** (on the left).
2. Under **Build and deployment**: **Source: Deploy from a branch**, **Branch: main**, folder **/docs** → **Save**.
3. After a minute or two, <https://bogdandata.github.io/laptop-remote/> opens the app.

### Add a laptop that is far away (for example your family's)

1. **On your phone**, open **<https://bogdandata.github.io/laptop-remote/>**. (Add it to the home screen: Chrome menu
   **⋮** → **Add to Home screen**; Safari **□↑** → **Add to Home Screen**. On iPhone, then use only the icon.)
2. Tap **Add a laptop**, write your name (the laptop will ask "Allow *your name* …?"), tap **Make the invitation**,
   then **E-mail** (or **Copy** and send it by Viber, WhatsApp…).
3. **On that laptop** (Windows 10 or 11), someone opens the link from the e-mail, clicks **Download the setup** and
   opens the downloaded file `LaptopRemote-setup.cmd`:
   - If the browser warns about the file: **Keep** (Edge: **…** → **Keep** → **Show more** → **Keep anyway**).
   - If Windows shows **"Windows protected your PC"**: **More info** → **Run anyway**.
   - A black window downloads everything (a minute or two), and the laptop asks
     **"Allow *your name* to control this laptop from anywhere?"** → **Yes**.
   - The black window can be minimized, but it should stay open.
4. **Your phone finds the laptop by itself** within a few seconds while the app is open. (Closed it? Open it later:
   the invitation waits for 7 days.)

What the setup does — it is a short text file, anyone can read it in Notepad first:
- Everything goes into **one folder, `%LOCALAPPDATA%\LaptopRemote`**. No administrator rights; nothing else is changed.
- It downloads this project from GitHub and a private copy of Python from python.org (the official "embeddable
  package", used only by Laptop Remote; it does not touch an installed Python). Then Laptop Remote downloads `cloudflared`.
- It starts Laptop Remote, and makes it start by itself (minimized) whenever someone signs in to Windows
  (a file `Laptop Remote.cmd` in the Startup folder).
- **This copy listens only to the laptop itself**: nothing on the home network can connect to it, and the Windows
  Firewall does not ask anything. It is controlled only through the app, encrypted.

### Add a laptop where Laptop Remote already runs (for example your own)

Start it as in section 3 (`start.bat`; an older copy: update it first, section 15). In the app tap **Add a laptop** →
**Make the invitation** → **Copy**. In the laptop's black window type **A**, press **Enter**, paste the invitation
(right-click in the window) and press **Enter**. The app shows the laptop a few seconds later.

### Another device for the same laptop

For example your laptop in Germany, too: open the app in its browser → **Add a laptop** → **Make the invitation** →
**Copy**, and send it to your phone. On the phone (already connected to that laptop): **Settings** →
**Give another device access** → paste → **Give access**. Nobody at the far laptop has to do anything.

### Using it

The same tabs as at home. With more than one laptop, choose it at the top (the app remembers the choice). The
**Screen** picture over the internet is slower than at home: choose **Fast**.

In **Settings** (for a laptop set up from an invitation):
- **Update Laptop Remote on the laptop** — downloads the newest version from GitHub and restarts it (about a minute).
- **Remove Laptop Remote from the laptop** — it stops, does not start by itself any more, and every device loses access.
- **Stop the remote** — from far away nobody can start it again; it starts again at the next sign-in to Windows.

### Taking the access away

- In the app: **Settings → Disconnect this device**, or **Disconnect all devices**.
- On the laptop: type **D** in the black window (all devices). Closing the window stops Laptop Remote (until the
  next sign-in).
- To remove it completely: double-click **`uninstall.bat`** in `%LOCALAPPDATA%\LaptopRemote\app` (or in the
  project folder), or use **Remove Laptop Remote from the laptop** in the app. Then the folder can be deleted.
- A device that is not used for **180 days** is disconnected automatically (`forget_anywhere_after_days`, section 13).

### So that the laptop can always be reached

- It must be **on, with internet**, and **someone must be signed in to Windows**: Laptop Remote starts at sign-in,
  not on the sign-in screen. After a **Restart** from far away, a laptop with a password waits on the sign-in screen
  until someone signs in (the app warns about this). With Windows set to sign in automatically, it comes back by itself.
- **On its charger it does not go to sleep by itself** while Laptop Remote runs (`keep_awake`, section 13). On battery
  Windows' normal sleep settings apply. **Closing the lid** usually still makes it sleep: leave it open, or set
  Control Panel → **Power Options** → **Choose what closing the lid does** → **Plugged in: Do nothing**.
- After it was off or offline, it leaves its new address within a minute of starting; the app then finds it.

### Good to know

- Free services in between, no accounts needed: **GitHub Pages** (the app's page), a **Cloudflare quick tunnel**
  (the connection) and **ntfy.sh** (the encrypted address notes, kept there for about 12 hours). Like any website,
  they see that someone uses them and from which internet address, but only locked data.
- Cloudflare's quick tunnels are made for trying things out, with no uptime guarantee. If it stops working, starting
  Laptop Remote again gets a new tunnel.
- The setup needs Windows 10 version 1803 (April 2018) or newer: it uses Windows' own `curl` and `tar`.
- Don't want it at all? `anywhere = no` in `config.ini`: then Laptop Remote works only at home, as in sections 3–6.

## 9. Away from home without the app: hotspot or Tailscale

**Without home Wi-Fi — the phone's hotspot** (no extra programs):
1. Turn on the hotspot on the phone and connect the laptop to it.
2. When Windows asks whether the PC should be discoverable on this network, choose **Yes** (that makes it private).
3. Start the remote **after** connecting. It shows the laptop's new address.
4. The first time, connect the phone again with a new code (type **L** + **Enter**). The address is different
   from home, so the phone gets a separate page for it.

The laptop then uses the phone's mobile data for its own internet. On Android, USB tethering (cable) works the same way.

**From anywhere over the internet (5G, another Wi-Fi) — Tailscale** (the app from section 8 is simpler; Tailscale
is another good way, if you already use it)

When the phone is on 5G, your home router lets nobody in from outside, so something has to connect the phone and the
laptop. Tailscale does that: it makes a private, **encrypted** network of your own devices, without changing anything on
the router. It is free for personal use. With it you also get a **secure https link with no code at all**: every device
signed in to your Tailscale account just opens the link and can control the laptop.

1. **On the laptop:** open <https://tailscale.com/download>, download Tailscale for Windows, install it and sign in
   (with a Google, Microsoft or Apple account).
2. **On the phone:** install **Tailscale** from the App Store / Google Play, open it, sign in with the **same account**,
   and allow it to add a VPN configuration. Leave it switched on (it runs in the background).
3. **On the laptop, double-click `tailscale-https.bat`** (only once). It asks Tailscale for a secure link.
   - If Tailscale shows a link (because HTTPS is not turned on for your account yet), open it, click **Enable**, and
     double-click `tailscale-https.bat` again. (The same switch is at <https://login.tailscale.com/admin/dns> →
     **HTTPS Certificates** → **Enable HTTPS**.)
   - If it says "Access denied", right-click `tailscale-https.bat` → **Run as administrator**.
   - At the end it shows the link, like `https://my-laptop.tail1234.ts.net`.
4. **Start the remote** (`start.bat`). Its window shows that link marked **BEST: from anywhere, encrypted, no code**.
   It is also copied, so you can e-mail it to yourself.
5. **On the phone, open that link.** That's all: no code, nothing to type. Add it to the home screen — it works there too.

It works on Wi-Fi and on 5G, at home and away. The laptop has to be switched on, connected to the internet, and the remote
has to run on it. Only devices signed in to **your** Tailscale account are let in this way (to turn that off, set
`tailscale_auto_connect = no` in `config.ini`; then they need a code like any other phone).

Without step 3 you can still use Tailscale: open the address that starts with `100.` (also shown in the window) and
type a code once. If that `100.…` address doesn't open, Windows may count the Tailscale network as public: allow the
remote on it as in section 11, or make it private (section 12 — its name in `Get-NetConnectionProfile` is usually "Tailscale").

Don't open a port on your router to reach the remote from the internet: then anyone could try to reach it.
Use control from anywhere (section 8) or Tailscale instead.

## 10. Add your own apps and websites

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

## 11. Windows Firewall — allow it only on private networks

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

## 12. Make your network "private"

The permission from section 11 only works if your home Wi-Fi is marked as **private** in Windows.

- **Windows 11:** Start → Settings → Network & internet → Wi-Fi → click your network → **Network profile type: Private network**.
- **Windows 10:** Start → Settings → Network & Internet → Wi-Fi → click your network → **Network profile: Private**.
- **PowerShell (as administrator):** `Get-NetConnectionProfile` shows the networks; then
  `Set-NetConnectionProfile -InterfaceAlias "Wi-Fi" -NetworkCategory Private`

> Don't set a café, hotel or airport network to private. The remote is meant not to work there.

## 13. Other settings

In `config.ini`, section `[server]`. After a change, stop the remote and start it again.

| Setting | What it does |
|---|---|
| `name =` | The laptop's name on the phone (and on its home screen icon). Empty = the Windows computer name. |
| `port = 8765` | The port. Change it only if it is taken (then also in the firewall rule from option C). |
| `volume_step = 1` | How much one tap changes the volume: 1 = 2%, 2 = 4%… up to 10. |
| `forget_phones_after_days = 30` | A phone not used for this many days is disconnected automatically. `0` = never. |
| `forget_anywhere_after_days = 180` | The same for devices that control the laptop from anywhere (section 8). `0` = never. |
| `tailscale_auto_connect = yes` | Devices signed in to your Tailscale account open the secure link with no code (section 9). `no` = they need a code too. |
| `anywhere = yes` | Control from anywhere through the encrypted tunnel (section 8). `no` = only at home. |
| `keep_awake = yes` | While Laptop Remote runs and the laptop is on its charger, it does not go to sleep by itself. `no` = Windows' normal sleep settings. |

The connected phones are stored in `devices.json` in the project folder. It holds only a fingerprint of each
phone's key, not the key itself. Deleting the file disconnects all phones.

## 14. Start automatically with Windows

After **Restart** from the phone, the remote does not start again by itself. To make it start whenever you sign in:

1. Press **Windows + R**, type `shell:startup` and press **Enter**. The **Startup** folder opens.
2. Right-click `start.bat` → **Create shortcut** (Windows 11: under **Show more options**).
3. Drag the shortcut into the **Startup** folder.

A laptop set up from an invitation (section 8) does this by itself.

The remote starts when you sign in to Windows (not on the sign-in screen itself). Its window is always visible
on the laptop — the remote never runs hidden.

## 15. Update to a new version

**A laptop set up from an invitation:** in the app, **Settings → Update Laptop Remote on the laptop** — from anywhere.
(Or start the setup file on the laptop again; nobody loses access.)

**Otherwise, double-click `update.bat`.** It stops the remote if it runs, downloads the newest version from GitHub and replaces the
program files. Your `config.ini` (apps and settings) and `devices.json` (connected phones) are kept. Then start the remote
again with `start.bat`.

(If you have a very old copy without `update.bat`, download the ZIP again as in section 2 and copy your `config.ini`
into the new folder.)

## 16. Troubleshooting

**The phone can't open the page (it keeps loading, or "site can't be reached"):**
- Is the remote running on the laptop (black window, or the VS Code terminal)?
- Is the phone on the same Wi-Fi (not mobile data, not a "guest" network)? Is a VPN on? Turn it off.
- Check the firewall ([section 11](#11-windows-firewall--allow-it-only-on-private-networks)), especially the part
  about "Cancel", and that the network is private ([section 12](#12-make-your-network-private)).
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

**From anywhere (section 8):**
- **"… is not online" / "No connection to the laptop":** the laptop is off, asleep (lid closed?), without internet,
  or nobody is signed in to Windows. Laptop Remote must be running there. After it starts, wait a minute and tap
  **Try again**.
- **The app waits for the laptop, but nothing comes:** keep the app open (it checks every 10 seconds), or open it again
  later — the invitation waits for 7 days. On the laptop, the black window shows what happens (lines starting with
  `Anywhere:`). Without a question "Allow …?" on the laptop, the invitation did not arrive there: send it again.
- **The setup says "Something did not work":** check the internet on the laptop and start the setup file again.
  Antivirus programs sometimes block downloads or `cloudflared.exe`: allow them there.
- **"The clock of the phone and of the laptop differ by more than 10 minutes":** set both to the automatic time.
- **"This invitation was already used":** make a new invitation for each new device.
- **"This device was disconnected":** someone disconnected it (Settings or **D** on the laptop), or it was not used for
  180 days. Add the laptop again with a new invitation.

## 17. Security

**Why the browser says "Not Secure" / "not encrypted":** addresses that start with `http://` (like `http://192.168.1.23:8765`)
are not encrypted by the browser.
- **At home on Wi-Fi** this means: someone else connected to the **same Wi-Fi** could, with special tools, see the screen
  pictures and what you type, and even copy the phone's key and then control the laptop. With a strong Wi-Fi password at
  home the risk is small. On a public Wi-Fi it would be real — that's why the remote works only on private networks.
- **With Tailscale** (`http://100.…`) the connection **is** encrypted by Tailscale; the browser just doesn't know it, so it
  still shows the warning.
- **With the secure link** (`https://….ts.net`, section 9) it is encrypted twice (Tailscale + https with a real
  certificate), the browser shows the padlock and no warning. This is the best way.

**From anywhere (section 8)** the app and the laptop encrypt everything end to end:
- Each device gets its own random 256-bit key from the laptop. Requests and answers are locked with **AES-256-GCM**
  (keys derived with HKDF-SHA256). A request that was changed, copied and sent again (replay), or locked with a wrong
  key, is refused; 5 attempts with a wrong key block the sender for 5 minutes.
- The key reaches the device locked with **ECDH (P-256)**: the invitation holds only the device's public key, so a copy of
  the e-mail is of no use. The laptop sends the key only after **Yes** on the laptop, or after a device that already has
  access confirms it in **Give another device access**.
- From the internet, the laptop accepts only these encrypted requests (`/e2e`) — nothing else works through the tunnel.
  A laptop set up from an invitation does not listen on the home network at all.
- Cloudflare and ntfy.sh see only locked data. The keys are stored only on the laptop (`devices.json`) and in the
  browser of each device (its storage for the app's page).
- The app's page comes from GitHub Pages, so whoever can change this GitHub project could change the app. Protect the
  GitHub account with a strong password and two-factor authentication.
- On the laptop, the window shows every action from every device, and its title says **"SCREEN IS BEING VIEWED"** while
  someone watches the screen.

**What else protects you:**
- **No PIN to guess.** A phone connects with a code (or link) that works **once**, for **15 minutes**; then it gets its own
  long secret key, and the laptop stores only a fingerprint of it. With the secure link, Tailscale itself checks that the
  device is yours.
- **You can take access away at any time:** disconnect one phone or all phones (phone Settings, or **D** in the window).
  Phones not used for 30 days are disconnected automatically. If you lose your phone: type **D** in the window, and also
  remove the phone from Tailscale (<https://login.tailscale.com/admin/machines>).
- **The remote is always visible on the laptop.** Its window shows every action. While a phone watches the screen, the
  window says `SCREEN VIEW started on …` and its title changes to **"SCREEN IS BEING VIEWED"**.
- Only devices on your home network or your own Tailscale network can reach it. 5 wrong codes block a device for 5 minutes.
- The phone can open only the apps on your list.
- Don't open a port on your router for it, and use the remote only on your own computers.
