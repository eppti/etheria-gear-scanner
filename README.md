# Etheria Gear Extractor

Export your **Etheria Restart** gear inventory to signed JSON by passively reading the
game's network traffic — no game files touched, no process injection, no memory reading.

It captures the gear-inventory packet the game sends at login (TCP port 20001), decodes
every piece (main stat, 4 substats with values + roll counts, matrix/set, level, lock
status), and writes an `EtheriaGearBundle` JSON file that Etheria Optimizer can verify
and import.

> **How it works (and why it's safe-by-design):** this tool *only* reads network packets,
> exactly like Wireshark. It never reads or writes the game's files, never touches the game
> process, and never sends anything to the game servers. It is 100% read-only/passive.
> Use it responsibly and at your own risk with respect to the game's Terms of Service.

---

## Requirements

- **Python 3.8+** — <https://www.python.org/downloads/> (standard library only, no pip installs)
- **Wireshark** (provides `tshark`) — <https://www.wireshark.org/download.html>
  - On **Windows**, also install **Npcap** when the installer offers it (so capturing works).

## Simple mode

Download `etheria_gear.exe` from the latest GitHub Release and double-click it to
start the wizard.

The wizard will:

1. List your network interfaces.
2. Ask which interface to capture from.
3. Capture packets while you log in to Etheria Restart.
4. Decode and sign the capture.
5. Save `mygear.json`.

Paste `mygear.json` into Etheria Optimizer's **Import gear** modal. The web app
verifies the server signature and validates the decoded gear before uploading it.

<details>
<summary>Advanced CLI mode</summary>

```bash
# List network interfaces and note the number for your active connection.
python etheria_gear.py interfaces

# Capture packets while logging in to the game.
# Replace 5 with the interface number from the first command.
python etheria_gear.py capture --iface 5 --seconds 180 --out mygear.pcap

# Decode and server-sign the capture.
python etheria_gear.py parse mygear.pcap --out mygear.json --sign
```

You can also start the same interactive wizard from a terminal:

```bash
python etheria_gear.py wizard
```

Or capture, decode, and sign in one command:

```bash
python etheria_gear.py grab --iface 5 --seconds 180 --out mygear.json --sign
```

</details>

### Signing and verification

`--sign` asks `https://api.etheriaoptimizer.com` to sign the export hash. The scanner
does **not** upload your full gear bundle while signing; it sends a hash plus scanner
version, receives an Ed25519 signature, and writes that signature into `mygear.json`.

The signing service may issue a short-lived one-time code automatically. That OTP is for
rate-limiting signing requests; the actual authenticity check is the Ed25519 signature
verified by the web app.

If you want to request a code yourself, run:

```bash
python etheria_gear.py otp
python etheria_gear.py parse mygear.pcap --out mygear.json --sign --otp ABCD1234
```

### Tips
- ⏱️ **Be logging in while it captures.** Gear is only sent at login — opening the gear
  screen mid-session does *not* re-send it. Start the command first, then log in.
- 🌐 **Pick the interface for how the game device connects.** The first command lists
  numbered interfaces. Use the number for `Ethernet` on a wired PC, `WLAN`/`Wi-Fi` on a
  wireless PC, or `bridge100` when your phone is connected through your computer.
- 📈 **Check the decoded piece count.** After the parse command, the printed `Decoded N pieces`
  number should be above zero and should increase when you capture a login with more gear.
- 🔐 **Permission error when capturing?** Run your terminal as Administrator (Windows can
  install Npcap admin-only), or reinstall Npcap with the "non-admin" option.
- 🌐 **Wrong interface?** If the JSON comes out empty, you picked the wrong adapter — try
  another number from `interfaces` (usually `Ethernet` if wired, `Wi-Fi` if wireless).
- 📦 **Already have a `.pcap`?** Use the web app command:
  `python etheria_gear.py parse mygear.pcap --out mygear.json --sign`.

## Output

```json
{
  "v": 1,
  "scannerVersion": "1.0.0",
  "pieceCount": 5865,
  "hash": "64-character export hash",
  "signature": "base64 Ed25519 signature",
  "signedAt": 1760000000000,
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

- `valueRaw` is the **true** number — the game UI rounds it (28.8 shows as 29).
- `value` is banker's-rounded for app compatibility.
- `rolls` = how many times that substat was upgraded. Unrolled substats have `rolls: 0`.
- `statWire` is the 5 raw stat varints from the packet. Other apps can ignore it; verifiers
  can use it to confirm the readable stats match the captured wire data.
- `hash`, `signature`, and `signedAt` are present when you use `--sign`.

## How the decoding works

See **[LEGEND.md](LEGEND.md)** for the full protocol/decoding spec (packet framing, the
stat marker → name table with scales, matrix ids, slot rules, worked examples), and
**[legend.json](legend.json)** for the same maps in machine-readable form.

## Notes

- Port 20001, the message framing, the stat encoding, and the matrix ids are the **same for
  every player** — they're the game's network protocol. Only your tshark path (auto-detected)
  and capture interface (a CLI flag) are machine-specific.
- It captures your full inventory as the game sends it at login.
- The scanner does not validate game balance rules. Etheria Optimizer validates uploaded
  gear during import.
- The old direct upload flow has been removed. Import by pasting signed JSON into the
  web app.

## Attribution

Original Etheria gear decoding research by Falkon100.
This public project intentionally credits the GitHub handle only and avoids private contact
details in source files, docs, and commit metadata.

## License

MIT — see [LICENSE](LICENSE).
