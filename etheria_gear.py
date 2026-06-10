#!/usr/bin/env python3
"""
etheria_gear.py - Extract your Etheria Restart gear inventory into JSON,
                  from a passive network capture (no game files touched).

WHAT IT DOES
  Reads a packet capture of the game's traffic (TCP port 20001), finds the gear
  inventory message, and decodes every piece (main stat, 4 substats, matrix, level...)
  into a clean JSON file.

REQUIREMENTS
  - Wireshark installed (provides 'tshark'): https://www.wireshark.org/
      On Windows also install Npcap (bundled with Wireshark) so capture works.
  - Python 3.8+  (standard library only - no pip packages needed)

HOW TO USE  (typical flow)
  Double-click etheria_gear.exe, or run with no arguments, to start the wizard.

  Advanced CLI:
  1) List your network interfaces:
        python etheria_gear.py interfaces
  2) Start a capture, then LOG IN to the game (gear is sent on login):
        python etheria_gear.py capture --iface 5 --seconds 120 --out mygear.pcap
     (open Etheria and log in while it runs; it stops after --seconds)
  3) Decode and sign the capture (OTP only rate-limits signing; security is Ed25519):
        python etheria_gear.py parse mygear.pcap --out mygear.json --sign
  4) Paste mygear.json into the Etheria Optimizer webapp Import gear modal.

  Or do capture+parse in one go:
        python etheria_gear.py grab --iface 5 --seconds 120 --out mygear.json

NOTES
  - Gear is only sent at LOGIN (opening the gear screen mid-session does not re-send it).
  - This is 100% passive: it only reads network packets, never the game process or files.
  - Port 20001 and the decoding tables below are the same for every player.
  - This captures your UNEQUIPPED + EQUIPPED inventory as the game sends it.
"""

import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
import urllib.error
import urllib.request
from collections import defaultdict

# ---------------------------------------------------------------------------
# Protocol constants (universal - same for all players)
# ---------------------------------------------------------------------------
SERVER_PORT = 20001          # game data port
DEFAULT_API_BASE = "https://api.etheriaoptimizer.com"
HEADER_SIZE = 12             # [4B flags][4B msg_type LE][4B payload_len LE]
GEAR_MSG = 0x1133            # message type that carries the gear inventory
SCANNER_VERSION = "1.0.0"
SCANNER_USER_AGENT = f"EtheriaGearScanner/{SCANNER_VERSION}"

# Stat type table: base marker -> (display name, divisor scale).
# A stat's value = (varint // 4096) / scale.  The marker (varint % 4096) identifies
# the stat; marker minus its base = how many times the substat was upgraded (0-4).
STATS = {
    48:  ("HP%",        10),
    64:  ("HP",         100),
    112: ("ATK%",       10),
    128: ("ATK",        100),
    176: ("DEF%",       10),
    192: ("DEF",        100),
    256: ("SPD",        100),
    304: ("CRIT Rate",  10),
    352: ("CRIT DMG",   10),
    400: ("Eff ACC",    10),
    448: ("Eff RES",    10),
}
BASE_MARKERS = sorted(STATS)

# Main-stat cap per marker (used to pick which of the 5 stats is the main).
# SPD (256) is never a main stat, so it is intentionally absent.
MAIN_CAP = {64: 3300, 128: 330, 192: 250, 48: 50, 112: 50, 176: 50,
            304: 40, 352: 60, 400: 60, 448: 60}

# Matrix ("set") id -> name. ids 61-66 are the [INFERNO ONLY] matrices.
MATRICES = {
    1: "Onslaught", 2: "Wellspring", 3: "Unbreakable", 4: "Swiftrush",
    5: "Bulwark", 6: "Battlewill", 8: "Bramble", 10: "Cure", 12: "Strive",
    15: "Harvest", 17: "Fury", 30: "Momentum", 32: "Bloodbath", 33: "Timeweave",
    34: "Keeneye", 61: "Furyedge", 62: "Etherplague", 63: "Colossguard",
    64: "Swiftraid", 65: "Swiftsmite", 66: "Evolguard",
}

STAT_SLUGS = {
    "HP": "flat_hp", "ATK": "flat_atk", "DEF": "flat_def",
    "HP%": "hp_pct", "ATK%": "atk_pct", "DEF%": "def_pct",
    "CRIT Rate": "crit_rate", "CRIT DMG": "crit_dmg",
    "Eff ACC": "effect_acc", "Eff RES": "effect_res", "SPD": "spd",
}

SET_SLUGS = {name: name.lower().replace(" ", "-") for name in MATRICES.values()}

# Derived from observed Etheria template ids. Template ids are emitted as odd/even
# pairs for the same gear slot; some captures only observed one side of a pair.
# Unknown templates fall back to main-stat inference, which is safe for normal
# left-side pieces and conservative for specials.
TEMPLATE_GEAR_TYPES = {
    15012: "atk", 15032: "hp", 15052: "def", 15071: "special", 15072: "special",
    15091: "atk", 15092: "atk", 15111: "hp", 15112: "hp", 15132: "def",
    15151: "special", 15152: "special", 15171: "atk", 15172: "atk",
    15191: "hp", 15192: "hp", 15211: "def", 15212: "def", 15231: "special",
    15232: "special", 15251: "atk", 15252: "atk", 15271: "hp", 15272: "hp",
    15291: "def", 15292: "def", 15311: "special", 15312: "special",
    15331: "atk", 15332: "atk", 15351: "hp", 15352: "hp", 15371: "def",
    15372: "def", 15391: "special", 15392: "special", 15411: "atk",
    15412: "atk", 15431: "hp", 15432: "hp", 15451: "def", 15452: "def",
    15471: "special", 15472: "special", 15571: "atk", 15572: "atk",
    15591: "hp", 15592: "hp", 15611: "def", 15612: "def", 15631: "special",
    15632: "special", 15731: "atk", 15732: "atk", 15751: "hp", 15752: "hp",
    15771: "def", 15772: "def", 15791: "special", 15792: "special",
    15891: "atk", 15892: "atk", 15911: "hp", 15912: "hp", 15931: "def",
    15932: "def", 15951: "special", 15952: "special", 16131: "atk",
    16132: "atk", 16151: "hp", 16152: "hp", 16171: "def", 16172: "def",
    16191: "special", 16192: "special", 16291: "atk", 16292: "atk",
    16311: "hp", 16312: "hp", 16331: "def", 16332: "def", 16351: "special",
    16352: "special", 17011: "atk", 17012: "atk", 17031: "hp", 17032: "hp",
    17052: "def", 17071: "special", 17072: "special", 17171: "atk",
    17172: "atk", 17191: "hp", 17192: "hp", 17211: "def", 17212: "def",
    17231: "special", 17232: "special", 17252: "atk", 17271: "hp",
    17272: "hp", 17291: "def", 17292: "def", 17311: "special",
    17312: "special", 17331: "atk", 17332: "atk", 17352: "hp",
    17371: "def", 17372: "def", 17392: "special", 17732: "special",
    17752: "special", 17772: "special", 17792: "special", 17812: "special",
    17832: "special",
}


# ---------------------------------------------------------------------------
# tshark discovery
# ---------------------------------------------------------------------------
def find_tshark(explicit=None):
    """Locate the tshark executable. Checks --tshark, PATH, then common installs."""
    candidates = [explicit] if explicit else []
    candidates.append(shutil.which("tshark"))
    candidates += [
        r"C:\Program Files\Wireshark\tshark.exe",
        r"C:\Program Files (x86)\Wireshark\tshark.exe",
        "/Applications/Wireshark.app/Contents/MacOS/tshark",
        "/usr/bin/tshark", "/usr/local/bin/tshark",
    ]
    for c in candidates:
        if c and os.path.exists(c):
            return c
    sys.exit("ERROR: tshark not found. Install Wireshark, or pass --tshark <path>.")


# ---------------------------------------------------------------------------
# protobuf / varint helpers
# ---------------------------------------------------------------------------
def read_varint(data, pos):
    result = shift = 0
    while pos < len(data):
        b = data[pos]; pos += 1
        result |= (b & 0x7F) << shift
        if not (b & 0x80):
            return result, pos
        shift += 7
    return None, pos


def decode_fields(data):
    """Shallow protobuf decode -> list of (field_number, kind, value).
    kind is 'int' or 'raw' (raw bytes for length-delimited fields)."""
    pos, out = 0, []
    while pos < len(data):
        tag, pos = read_varint(data, pos)
        if tag is None or tag == 0:
            break
        field, wire = tag >> 3, tag & 7
        try:
            if wire == 0:                       # varint
                val, pos = read_varint(data, pos)
                out.append((field, "int", val))
            elif wire == 2:                     # length-delimited
                ln, pos = read_varint(data, pos)
                if ln is None or pos + ln > len(data):
                    break
                out.append((field, "raw", data[pos:pos + ln])); pos += ln
            elif wire == 5:                     # 32-bit
                out.append((field, "int", struct.unpack_from("<I", data, pos)[0])); pos += 4
            elif wire == 1:                     # 64-bit
                out.append((field, "int", struct.unpack_from("<Q", data, pos)[0])); pos += 8
            else:
                break
        except Exception:
            break
    return out


def varint_list(data):
    """Decode field[4] (the packed stats) into a flat list of varints."""
    pos, out = 0, []
    while pos < len(data):
        v, pos = read_varint(data, pos)
        if v is None:
            break
        out.append(v)
    return out


def base_of(marker):
    """Return the base marker (stat type) for a raw marker, or None."""
    for b in BASE_MARKERS:
        if b <= marker <= b + 6:
            return b
    return None


def decode_stat(varint):
    """Decode one stat varint -> {stat, value, rolls} or None if unknown."""
    high, marker = varint // 4096, varint % 4096
    base = base_of(marker)
    if base is None:
        return None
    name, scale = STATS[base]
    return {"stat": name, "value": round(high / scale, 3), "rolls": marker - base, "_base": base, "_high": high}


# ---------------------------------------------------------------------------
# capture stream -> messages -> gear pieces
# ---------------------------------------------------------------------------
def reassemble_server_payloads(tshark, pcap):
    """Use tshark to pull the TCP payloads sent BY the server (srcport 20001),
    reassembled per stream. Returns {stream_id: bytes}."""
    cmd = [tshark, "-r", pcap, "-T", "fields",
           "-e", "tcp.stream", "-e", "tcp.srcport", "-e", "tcp.len", "-e", "data.data",
           "-E", "separator=|"]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0 and not res.stdout:
        sys.exit(f"ERROR running tshark:\n{res.stderr.strip()}")
    streams = defaultdict(bytes)
    for line in res.stdout.splitlines():
        parts = line.strip().split("|")
        if len(parts) < 4:
            continue
        sid, sport, tlen, hexdata = parts
        try:
            if int(sport) != SERVER_PORT or not hexdata or int(tlen) == 0:
                continue
            streams[sid] += bytes.fromhex(hexdata.replace(":", ""))
        except ValueError:
            continue
    return streams


def split_messages(data):
    """Split a reassembled stream into (msg_type, payload) messages."""
    out, pos = [], 0
    while pos + HEADER_SIZE <= len(data):
        msg_type = struct.unpack_from("<I", data, pos + 4)[0]
        length = struct.unpack_from("<I", data, pos + 8)[0]
        pos += HEADER_SIZE
        if length > len(data) - pos:
            out.append((msg_type, data[pos:]))
            break
        out.append((msg_type, data[pos:pos + length])); pos += length
    return out


def pick_main(stats):
    """Choose the main stat = the one closest to its cap (SPD never main)."""
    best, best_ratio = None, -1.0
    for s in stats:
        cap = MAIN_CAP.get(s["_base"])
        if cap is None:
            continue
        ratio = s["value"] / cap
        if ratio > best_ratio:
            best_ratio, best = ratio, s
    return best or stats[0]


def bankers_round(value):
    """Round half to even, matching the game's displayed stat values."""
    sign = -1 if value < 0 else 1
    value = abs(value)
    floor = int(value)
    frac = value - floor
    if frac < 0.5:
        return sign * floor
    if frac > 0.5:
        return sign * (floor + 1)
    return sign * (floor if floor % 2 == 0 else floor + 1)


def gear_type_for(template_id, main_stat):
    if template_id in TEMPLATE_GEAR_TYPES:
        return TEMPLATE_GEAR_TYPES[template_id]
    if isinstance(template_id, int):
        paired_template_id = template_id + 1 if template_id % 2 else template_id - 1
        if paired_template_id in TEMPLATE_GEAR_TYPES:
            return TEMPLATE_GEAR_TYPES[paired_template_id]
    return {"HP": "hp", "ATK": "atk", "DEF": "def"}.get(main_stat, "special")


def clean_stat(stat):
    return {
        "stat": STAT_SLUGS[stat["stat"]],
        "value": bankers_round(stat["value"]),
        "valueRaw": stat["value"],
        "rolls": stat["rolls"],
    }


def bundle_piece(piece):
    return {
        "instanceId": piece["instance"],
        "templateId": piece["template"],
        "setId": SET_SLUGS.get(piece["matrix"]),
        "matrixId": piece["matrix_id"],
        "matrixLevel": piece["matrix_slots"],
        "gearType": gear_type_for(piece["template"], piece["main"]["stat"]),
        "mainStat": STAT_SLUGS[piece["main"]["stat"]],
        "mainStatValue": piece["main"]["value"],
        "mainStatValueRaw": piece["main"]["value"],
        "level": piece["level"],
        "locked": piece["locked"],
        "substats": [clean_stat(s) for s in piece["subs"]],
        "statWire": piece["statWire"],
    }


def extract_gear(tshark, pcap):
    """Decode all gear pieces from the capture. Returns a list of piece dicts."""
    pieces, seen = [], set()
    for data in reassemble_server_payloads(tshark, pcap).values():
        for msg_type, payload in split_messages(data):
            if msg_type != GEAR_MSG:
                continue
            for field, kind, raw in decode_fields(payload):
                if field != 1 or kind != "raw":      # repeated field[1] = one piece
                    continue
                f = decode_fields(raw)
                get = lambda n, k: next((v for a, b, v in f if a == n and b == k), None)
                stat_raw = get(4, "raw")
                if not stat_raw:
                    continue
                varints = varint_list(stat_raw)
                if len(varints) != 5:
                    continue
                stats = [s for s in (decode_stat(v) for v in varints) if s]
                if len(stats) != 5:
                    continue
                inst = get(1, "int")
                if inst in seen:
                    continue
                seen.add(inst)
                f5 = get(5, "int") or 0
                main = pick_main(stats)
                subs = [s for s in stats if s is not main]
                clean = lambda s: {"stat": s["stat"], "value": s["value"], "rolls": s["rolls"]}
                pieces.append({
                    "instance": inst,
                    "template": get(2, "int"),
                    "level": get(3, "int"),
                    "locked": (get(6, "int") or 0) == 1,
                    "matrix_slots": (f5 >> 16) & 0xFFFF,
                    "matrix_id": f5 & 0xFFFF,
                    "matrix": MATRICES.get(f5 & 0xFFFF),
                    "main": {"stat": main["stat"], "value": main["value"]},
                    "subs": [clean(s) for s in subs],
                    "statWire": varints,
                })
    return pieces


def canonical_json(value):
    if value is None or isinstance(value, (bool, str, int)):
        return json.dumps(value, separators=(",", ":"), ensure_ascii=False)
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return json.dumps(value, separators=(",", ":"), ensure_ascii=False)
    if isinstance(value, list):
        return "[" + ",".join(canonical_json(v) for v in value) + "]"
    if isinstance(value, dict):
        return "{" + ",".join(
            json.dumps(k, separators=(",", ":"), ensure_ascii=False) + ":" + canonical_json(value[k])
            for k in sorted(value)
        ) + "}"
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def build_sign_payload(bundle):
    pieces = sorted(bundle["pieces"], key=lambda p: p["instanceId"])
    return {
        "scannedAt": bundle["scannedAt"],
        "scannerVersion": bundle["scannerVersion"],
        "pieces": pieces,
    }


def hash_export(bundle):
    payload = build_sign_payload(bundle)
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def post_json(url, payload):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", SCANNER_USER_AGENT)
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            body = res.read().decode("utf-8")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        sys.exit(f"ERROR {e.code} from {url}: {detail}")


def request_otp(api_base):
    return post_json(f"{api_base.rstrip('/')}/gear-export/otp", {})


def request_sign(api_base, export_hash, scanner_version, code):
    return post_json(
        f"{api_base.rstrip('/')}/gear-export/sign",
        {"hash": export_hash, "scannerVersion": scanner_version, "code": code},
    )


def sign_bundle(bundle, api_base, code=None):
    export_hash = hash_export(bundle)
    if not code:
        otp = request_otp(api_base)
        code = otp.get("code")
        if not code:
            sys.exit("ERROR: failed to obtain signing OTP from server")
        print(f"Signing OTP: {code} (valid for 5 minutes)")
    result = request_sign(api_base, export_hash, bundle["scannerVersion"], code)
    bundle["hash"] = export_hash
    bundle["signature"] = result.get("signature")
    bundle["signedAt"] = result.get("issuedAt")
    if not bundle["signature"]:
        sys.exit("ERROR: server did not return a signature")


def make_bundle(pieces):
    return {
        "v": 1,
        "game": "Etheria Restart",
        "source": "passive packet capture (TCP port 20001, message 0x1133)",
        "scannerVersion": SCANNER_VERSION,
        "scannedAt": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "pieceCount": len(pieces),
        "pieces": [bundle_piece(p) for p in pieces],
    }


def write_json(pieces, out_path, raw=False, sign=False, api_base=DEFAULT_API_BASE, otp_code=None):
    if raw:
        export = {
            "_about": {
                "game": "Etheria Restart",
                "source": "passive packet capture (TCP port 20001, message 0x1133)",
                "piece_count": len(pieces),
                "note": "Legacy debug shape. Use default output for EtheriaGearBundle v1.",
            },
            "_matrices": MATRICES,
            "_stats": [name for name, _ in STATS.values()],
            "pieces": pieces,
        }
    else:
        export = make_bundle(pieces)
        if sign:
            sign_bundle(export, api_base, code=otp_code)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(export, fh, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# live capture
# ---------------------------------------------------------------------------
def get_interfaces(tshark):
    res = subprocess.run([tshark, "-D"], capture_output=True, text=True)
    if res.returncode != 0:
        sys.exit(f"ERROR listing interfaces:\n{res.stderr.strip()}")

    interfaces = []
    for idx, line in enumerate(res.stdout.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        number, _, name = line.partition(".")
        if number.isdigit() and name:
            interfaces.append((number, name.strip()))
        else:
            interfaces.append((str(idx), line))
    return interfaces


def list_interfaces(tshark):
    print("Available Network Interfaces:")
    for number, name in get_interfaces(tshark):
        print(f"[{number}] {name}")


def capture(tshark, iface, seconds, out_pcap):
    print(f"Capturing on interface {iface} for {seconds}s -> {out_pcap}")
    print("  >>> Open Etheria and LOG IN now (gear is sent on login). <<<")
    cmd = [tshark, "-i", str(iface), "-f", f"tcp port {SERVER_PORT}",
           "-a", f"duration:{seconds}", "-w", out_pcap]
    subprocess.run(cmd)
    print("Capture finished.")


def parse_capture(tshark, pcap, out_json, raw=False, sign=False,
                  api_base=DEFAULT_API_BASE, otp_code=None, only_level_15=False):
    pieces = extract_gear(tshark, pcap)
    if only_level_15:
        pieces = [piece for piece in pieces if piece.get("level") == 15]
    write_json(pieces, out_json, raw=raw, sign=sign, api_base=api_base, otp_code=otp_code)
    return len(pieces)


def prompt_yes_no(question, default=False):
    default_hint = "Y/n" if default else "y/N"
    while True:
        answer = input(f"{question} [{default_hint}]: ").strip().lower()
        if not answer:
            return default
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False
        print("Please answer yes or no.")


def prompt_enter_to_exit():
    try:
        input("Press Enter to exit...")
    except EOFError:
        pass


def wizard(tshark_path=None):
    try:
        tshark = find_tshark(tshark_path)

        interfaces = get_interfaces(tshark)
        if not interfaces:
            sys.exit("ERROR: no network interfaces found.")

        print("Available Network Interfaces:")
        valid = {number for number, _ in interfaces}
        for number, name in interfaces:
            print(f"[{number}] {name}")

        while True:
            iface = input("Select interface number: ").strip()
            if iface in valid:
                break
            print("Please enter one of the listed interface numbers.")

        raw_seconds = input("Enter capture duration in seconds [default 180]: ").strip()
        if raw_seconds:
            try:
                seconds = int(raw_seconds)
                if seconds <= 0:
                    raise ValueError
            except ValueError:
                print("Invalid duration; using default 180 seconds.")
                seconds = 180
        else:
            seconds = 180

        pcap = "mygear.pcap"
        out_json = "mygear.json"

        print("Capturing packets... (do not close this window)")
        capture(tshark, iface, seconds, pcap)

        only_level_15 = prompt_yes_no("Only scan +15 gear?", default=False)
        print("A signature lets etheriaoptimizer.com validate the gear.")
        print("It is entirely optional for uploading gear.")
        sign = prompt_yes_no("Get signature for verified gear?", default=True)

        print("Parsing capture...")
        if sign:
            print("Signing data...")
        count = parse_capture(tshark, pcap, out_json, sign=sign, only_level_15=only_level_15)
        print(f"Done! Output saved to {out_json}")
        print(f"Decoded {count} pieces.")
    except KeyboardInterrupt:
        print("\nCancelled.")
    except SystemExit as exc:
        if exc.code:
            print(exc.code)
    finally:
        prompt_enter_to_exit()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    if len(sys.argv) == 1:
        wizard()
        return

    ap = argparse.ArgumentParser(
        description="Extract Etheria Restart gear into JSON from a packet capture.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Run with no command to start the wizard. See the file header for the full guide.")
    ap.add_argument("--tshark", help="path to tshark (auto-detected if omitted)")
    sub = ap.add_subparsers(dest="cmd")

    sub.add_parser("interfaces", help="list capture interfaces (pick a number for --iface)")

    sub.add_parser("wizard", help="interactive capture + parse wizard")

    o = sub.add_parser("otp", help="request a one-time signing code from the server")
    o.add_argument("--api", default=DEFAULT_API_BASE, help=f"API base URL (default: {DEFAULT_API_BASE})")

    sign_opts = argparse.ArgumentParser(add_help=False)
    sign_opts.add_argument("--sign", action="store_true", help="request server signature after export")
    sign_opts.add_argument("--otp", help="signing OTP (omit to request a new one)")
    sign_opts.add_argument("--api", default=DEFAULT_API_BASE, help=f"API base URL (default: {DEFAULT_API_BASE})")

    c = sub.add_parser("capture", help="capture traffic to a .pcap (log in while it runs)")
    c.add_argument("--iface", required=True, help="interface number/name from 'interfaces'")
    c.add_argument("--seconds", type=int, default=120, help="capture duration (default 120)")
    c.add_argument("--out", default="mygear.pcap", help="output .pcap (default mygear.pcap)")

    p = sub.add_parser("parse", help="decode a .pcap into gear JSON", parents=[sign_opts])
    p.add_argument("pcap", help="the .pcap file to decode")
    p.add_argument("--out", default="etheria_gear.json", help="output JSON (default etheria_gear.json)")
    p.add_argument("--raw", action="store_true", help="write legacy debug JSON instead of bundle v1")

    g = sub.add_parser("grab", help="capture + parse in one step", parents=[sign_opts])
    g.add_argument("--iface", required=True, help="interface number/name")
    g.add_argument("--seconds", type=int, default=120)
    g.add_argument("--out", default="etheria_gear.json", help="output JSON")
    g.add_argument("--raw", action="store_true", help="write legacy debug JSON instead of bundle v1")

    args = ap.parse_args()
    if not args.cmd:
        wizard(args.tshark)
        return
    if args.cmd == "wizard":
        wizard(args.tshark)
        return

    tshark = find_tshark(args.tshark)

    if args.cmd == "interfaces":
        list_interfaces(tshark)
    elif args.cmd == "otp":
        otp = request_otp(args.api)
        print(json.dumps(otp, indent=2))
    elif args.cmd == "capture":
        capture(tshark, args.iface, args.seconds, args.out)
    elif args.cmd == "parse":
        count = parse_capture(tshark, args.pcap, args.out, raw=args.raw, sign=args.sign,
                              api_base=args.api, otp_code=args.otp)
        print(f"Decoded {count} pieces -> {args.out}" + (" (signed)" if args.sign else ""))
    elif args.cmd == "grab":
        tmp = "mygear.pcap"
        capture(tshark, args.iface, args.seconds, tmp)
        count = parse_capture(tshark, tmp, args.out, raw=args.raw, sign=args.sign,
                              api_base=args.api, otp_code=args.otp)
        print(f"Decoded {count} pieces -> {args.out}" + (" (signed)" if args.sign else ""))


if __name__ == "__main__":
    main()
