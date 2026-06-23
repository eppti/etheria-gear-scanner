# Etheria Gear Extractor

Export your **Etheria Restart** gear inventory to JSON by passively reading the game's
network traffic — no game files touched, no process injection, no memory reading.

It captures the gear-inventory packet the game sends at login (TCP port 20001), decodes
every piece (main stat, 4 substats with values + roll counts, matrix/set, level, lock
status), and writes a JSON file you can paste into Etheria Optimizer.

> **How it works (and why it's safe-by-design):** this tool *only* reads network packets,
> exactly like Wireshark. It never reads or writes the game's files, never touches the game
> process, and never sends anything to the game servers. It is 100% read-only/passive.
> Use it responsibly and at your own risk with respect to the game's Terms of Service.

---

## Step-by-step guide

You will run **three terminal commands** with Python, or use a Windows `.exe` if you prefer.
Pick the section for your OS below.

---

### Windows

#### Option A — Python (recommended)

##### Step 1 — Install Python and Wireshark

1. **Python 3.8+** — <https://www.python.org/downloads/>
   - Check **"Add python.exe to PATH"** during install.
2. **Wireshark** — <https://www.wireshark.org/download.html>
   - Also install **Npcap** when the Wireshark installer offers it.

No other pip packages are required.

##### Step 2 — Verify the tools work

Open **PowerShell** or **Command Prompt** (search "PowerShell" in the Start menu).

```powershell
python --version
tshark --version
```

If `python` is not found, try `py --version`. If `tshark` is not found, re-run the Wireshark
installer — it is usually at `C:\Program Files\Wireshark\tshark.exe`.

Both commands must succeed before continuing.

##### Step 3 — Get `etheria_gear.py`

Pick one:

**Option A — download just the script**

1. Open <https://github.com/eppti/etheria-gear-scanner/blob/main/etheria_gear.py>
2. Click **Raw**, then save the page as `etheria_gear.py`

**Option B — clone the whole repo**

```bash
git clone https://github.com/eppti/etheria-gear-scanner.git
cd etheria-gear-scanner
```

Remember where you saved the file — you need that folder in the next step.

##### Step 4 — Open a terminal in that folder

The terminal must be **in the same folder as `etheria_gear.py`**.

If the file is in `Downloads`:

```powershell
cd $HOME\Downloads
```

If you cloned the repo:

```powershell
cd $HOME\Downloads\etheria-gear-scanner
```

Tip: in File Explorer, go to the folder, click the address bar, type `powershell`, and press
Enter — that opens PowerShell already in that folder.

Confirm the script is there: `dir etheria_gear.py`

##### Step 5 — List your network interfaces

```powershell
python etheria_gear.py interfaces
```

You will see a numbered list, for example:

```text
Available Network Interfaces:
[1] Wi-Fi
[2] Ethernet
[5] bridge100
```

##### Step 6 — Pick the right interface number

Use the number for **how the game device connects to the internet**:

| Your setup | Look for |
|------------|----------|
| PC on Wi-Fi | `Wi-Fi`, `WLAN`, or similar |
| PC on ethernet cable | `Ethernet` |
| Phone tethered through your PC | often `bridge100` or another `bridge` entry |

Write down the number — you need it in the next command.

##### Step 7 — Capture while you log in

Replace `5` with your interface number from step 6.

```powershell
python etheria_gear.py capture --iface 5 --seconds 180 --out mygear.pcap
```

**Important:** start this command **first**, then open Etheria Restart and **log in**.
Gear is only sent at login — opening the gear screen mid-session does not re-send it.

While it runs you should see capture activity (packet counts increasing in the output).
Wait until it says **Capture finished.** and returns to the prompt (~3 minutes by default).

If you get a permission error on Windows, close the terminal, open PowerShell **as
Administrator**, `cd` back to the folder, and try again. Or reinstall Npcap with the
"non-admin" capture option.

##### Step 8 — Decode the capture to JSON

```powershell
python etheria_gear.py parse mygear.pcap --out mygear.json
```

When it finishes, check the last line:

```text
Decoded 5865 pieces -> mygear.json
```

**If it says `Decoded 0 pieces`, something went wrong** — usually the wrong interface in step 6,
or you were not logging in during the capture. Go back to step 5 and try another interface
number.

The scanner also prints warnings if individual pieces could not be decoded. Read those lines
if the piece count looks too low.

Then continue to [Step 9](#step-9--import-into-etheria-optimizer).

#### Option B — `.exe` wizard (no terminal)

`etheria_gear.exe` is built automatically by **GitHub Actions** on each release tag and
uploaded to [GitHub Releases](https://github.com/eppti/etheria-gear-scanner/releases/latest)
alongside a checksum file.

1. Download **`etheria_gear.exe`** and **`etheria_gear.exe.sha256`** from the latest release.
2. Verify the download (recommended). Open PowerShell in your Downloads folder and run:

```powershell
Get-FileHash .\etheria_gear.exe -Algorithm SHA256
Get-Content .\etheria_gear.exe.sha256
```

The hash from `Get-FileHash` should match the hash in `etheria_gear.exe.sha256`.

3. Double-click **`etheria_gear.exe`** to start the wizard.

You still need **Wireshark** (with **Npcap**) installed — the `.exe` uses `tshark` to capture
packets. The wizard walks you through interface selection, capture, decode, and export to
`mygear.json`.

**If Windows SmartScreen or your antivirus blocks the download or deletes the file**, use
**Option A (Python)** above instead.

When finished, paste `mygear.json` into Etheria Optimizer's **Import gear** modal (see
[Step 9](#step-9--import-into-etheria-optimizer) below).

---

### Mac and Linux

##### Step 1 — Install Python and Wireshark

1. **Python 3.8+** — <https://www.python.org/downloads/> (macOS may already have it; Linux:
   use your package manager or python.org)
2. **Wireshark** — <https://www.wireshark.org/download.html>

No other pip packages are required.

##### Step 2 — Verify the tools work

Open **Terminal**.

```bash
python3 --version
tshark --version
```

On Mac, if `tshark` is not found, install Wireshark — it is usually at
`/Applications/Wireshark.app/Contents/MacOS/tshark`.

Both commands must succeed before continuing.

##### Step 3 — Get `etheria_gear.py`

Pick one:

**Option A — download just the script**

1. Open <https://github.com/eppti/etheria-gear-scanner/blob/main/etheria_gear.py>
2. Click **Raw**, then save the page as `etheria_gear.py`

**Option B — clone the whole repo**

```bash
git clone https://github.com/eppti/etheria-gear-scanner.git
cd etheria-gear-scanner
```

##### Step 4 — Open a terminal in that folder

```bash
cd ~/Downloads                  # or wherever you saved the file
ls etheria_gear.py              # confirm it is here
```

##### Step 5 — List your network interfaces

```bash
python3 etheria_gear.py interfaces
```

You will see a numbered list, for example:

```text
Available Network Interfaces:
[1] Wi-Fi
[2] Ethernet
[5] bridge100
```

##### Step 6 — Pick the right interface number

Use the number for **how the game device connects to the internet**:

| Your setup | Look for |
|------------|----------|
| PC on Wi-Fi | `Wi-Fi`, `WLAN`, or similar |
| PC on ethernet cable | `Ethernet` |
| Phone tethered through your PC | often `bridge100` or another `bridge` entry |

##### Step 7 — Capture while you log in

Replace `5` with your interface number.

```bash
python3 etheria_gear.py capture --iface 5 --seconds 180 --out mygear.pcap
```

Start this command **first**, then open Etheria Restart and **log in**. Wait until it says
**Capture finished.**

##### Step 8 — Decode the capture to JSON

```bash
python3 etheria_gear.py parse mygear.pcap --out mygear.json
```

Check the last line — **`Decoded 0 pieces` means something went wrong**. Re-run step 5 with a
different interface number.

Then continue to Step 9 below.

---

### Step 9 — Import into Etheria Optimizer

1. Open `mygear.json` in a text editor (Notepad on Windows, TextEdit on Mac, etc.)
2. Select all and copy the full contents
3. Paste into Etheria Optimizer's **Import gear** modal

Each piece in the JSON includes an `instanceId` — a unique id from the game server — so two
pieces that look identical can still be told apart.

---

## All three commands at a glance (Python)

Replace `5` with your interface number from `interfaces`. On Mac/Linux, use `python3` instead
of `python`.

```bash
# 1) List interfaces
python etheria_gear.py interfaces

# 2) Capture while logging in (~3 min)
python etheria_gear.py capture --iface 5 --seconds 180 --out mygear.pcap

# 3) Decode to JSON
python etheria_gear.py parse mygear.pcap --out mygear.json
```

<details>
<summary>Other ways to run (wizard / one command)</summary>

**Interactive wizard** (same steps, but prompts you):

```bash
python etheria_gear.py
# or
python etheria_gear.py wizard
```

**Capture + decode in one command:**

```bash
python etheria_gear.py grab --iface 5 --seconds 180 --out mygear.json
```

</details>

---

## Troubleshooting

- **Windows blocked or deleted the `.exe`** — use **Option A (Python)** in the Windows
  section instead. The `.exe` is built by GitHub Actions from the public source; SmartScreen
  often blocks PyInstaller builds even when the checksum matches.
- **0 pieces decoded** — wrong network interface, or you did not log in during capture. Re-run
  `interfaces` and try another number.
- **Permission error when capturing (Windows)** — run the terminal as Administrator, or
  reinstall Npcap with non-admin capture enabled.
- **tshark not found** — reinstall Wireshark; on Windows make sure Npcap was installed too.
- **python not found (Windows)** — reinstall Python and check "Add to PATH", or use `py` instead
  of `python`.
- **Already have a `.pcap`?** Skip capture and run only the parse command from step 8.

---

## Output

```json
{
  "v": 1,
  "scannerVersion": "1.0.0",
  "pieceCount": 5865,
  "pieces": [
    {
      "instanceId": 115088,
      "templateId": 17832,
      "setId": "evolguard",
      "matrixId": 66,
      "matrixLevel": 3,
      "gearType": "special",
      "mainStat": "atk_pct",
      "mainStatValue": 50.0,
      "level": 15,
      "locked": false,
      "substats": [
        { "stat": "crit_rate", "value": 4, "valueRaw": 4.4, "rolls": 1 },
        { "stat": "crit_dmg", "value": 13, "valueRaw": 13.2, "rolls": 3 },
        { "stat": "spd", "value": 3, "valueRaw": 2.7, "rolls": 0 },
        { "stat": "flat_def", "value": 27, "valueRaw": 27.2, "rolls": 1 }
      ],
      "statWire": [204800112, 54067, 1105953, 11008, 111411392]
    }
  ]
}
```

- `instanceId` — unique per piece in your inventory; use this to tell apart identical-looking gear.
- `valueRaw` is the **true** number — the game UI rounds it (28.8 shows as 29).
- `value` is banker's-rounded for app compatibility.
- `rolls` = how many times that substat was upgraded. Unrolled substats have `rolls: 0`.
- `statWire` is the 5 raw stat varints from the packet. Other apps can ignore it.

---

## How the decoding works

See **[LEGEND.md](LEGEND.md)** for the full protocol/decoding spec (packet framing, the
stat marker → name table with scales, matrix ids, slot rules, worked examples), and
**[legend.json](legend.json)** for the same maps in machine-readable form.

---

## Notes

- Port 20001, the message framing, the stat encoding, and the matrix ids are the **same for
  every player** — they're the game's network protocol. Only your tshark path (auto-detected)
  and capture interface (a CLI flag) are machine-specific.
- It captures your full inventory as the game sends it at login.
- The scanner does not validate game balance rules. Etheria Optimizer applies its own
  import rules when you paste JSON into the web app.
- Import by pasting JSON into the web app.

---

## Attribution

Original Etheria gear decoding research by Falkon100.
This public project intentionally credits the GitHub handle only and avoids private contact
details in source files, docs, and commit metadata.

## License

MIT — see [LICENSE](LICENSE).
