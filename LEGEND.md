# Etheria Restart — Gear Decoding Legend

How to read a gear piece from the game's network data (passive capture, TCP port **20001**).

---

## 1. Packet / message framing

The TCP stream is a series of messages, each:

```
[ 4 bytes flags ][ 4 bytes msg_type (LE uint32) ][ 4 bytes payload_len (LE uint32) ][ payload ]
```

Relevant message types (payload = protobuf):
| msg_type | meaning |
|----------|---------|
| `0x1133` | gear inventory (one entry per piece) |
| `0x12A2` | inventory list |
| `0x1520` | roster/loadout-ish (not full gear stats) |
| `0x1204` | lock/unlock action: field[2]=state, field[3]=piece instance id |

Gear is **only sent on login** (opening the gear screen does not re-send it).

---

## 2. Gear piece structure (protobuf entry inside `0x1133`, repeated field [1])

| field | name | meaning |
|-------|------|---------|
| `[1]` | instance_id | unique id of this physical piece |
| `[2]` | template_id | piece-type id (encodes slot + main family) |
| `[3]` | level | 0–15 |
| `[4]` | **stats** | 5 packed varints = 1 main + 4 substats (see §3) |
| `[5]` | f5 | `(matrix_slots << 16) | matrix_id` (see §5) |
| `[6]` | flag | 0 or 1 (lock/equip flag) |

There are always **5 stats** (1 main + 4 subs), even at low level (unrolled subs read as value 0).

---

## 3. Stat encoding — the core formula

`field[4]` is a flat list of **5 varints**. Each varint = ONE stat:

```
high   = varint // 4096          (the value, scaled)
marker = varint  % 4096          (stat type + roll count)
base   = the stat's base marker  (nearest base ≤ marker, within +0..+6)
rolls  = marker - base           (times this substat was upgraded, 0–4; 4 = "yellow"/maxed)
value  = high / scale            (scale depends on the stat, see §4)
```

Order is **random** — the stat type is identified by `marker`, not position.
The **main stat** is the one whose value is near its cap (see §4 caps); SPD is never a main.

### Worked example
varint `1351680064`:
- `high = 1351680064 // 4096 = 330000`
- `marker = 1351680064 % 4096 = 64` → base **64** = HP, rolls 0
- `value = 330000 / 100 = 3300` → **HP 3300**

varint `11796673`:
- `high = 2880`, `marker = 193` → base **192** = DEF, rolls 1
- `value = 2880 / 100 = 28.8` → **DEF 28.8** (game shows **29**)

---

## 4. Stat table (base marker → name, scale, main cap)

| base | stat | scale (÷) | main cap | example |
|------|------|-----------|----------|---------|
| 64  | HP (flat)   | 100  | 3300 | 330000→3300 |
| 128 | ATK (flat)  | 100  | 330  | 33000→330 |
| 192 | DEF (flat)  | 100  | 250  | 25000→250 |
| 256 | SPD         | 100  | (never main) | 300→3.0 |
| 48  | HP%         | 10   | 50 | 27→2.7 |
| 112 | ATK%        | 10   | 50 | 500→50 |
| 176 | DEF%        | 10   | 50 | 50→5.0 |
| 304 | CRIT Rate   | 10   | 40 | 40→4.0 |
| 352 | CRIT DMG    | 10   | 60 | 104→10.4 |
| 400 | Eff ACC     | 10   | 60 | 36→3.6 |
| 448 | Eff RES     | 10   | 60 | 600→60 |

**Reading values / decimals:** the stored value is more precise than the UI. After dividing by the scale you get up to ~1 decimal of real precision (e.g. 28.8); the **game rounds to a whole number** for display (28.8 → 29, 3.6 → 4%). Percent stats are stored as their face number (4% is value 4, scale ÷10 → high 40), not as 0.04.

**The 3 flat stats (HP, ATK, DEF) all use scale ÷100.** Magnitudes differ a lot (HP main ~3300, ATK ~330, DEF ~250) — HP is the biggest, so HP is the marker (64) carrying the largest values.

---

## 5. f5 → matrix & slots

```
matrix_id    = f5 & 0xFFFF        (low 16 bits)
matrix_slots = (f5 >> 16) & 0xFFFF  (high 16 bits)  -> 2 or 3 (the "2 or 3 matrix")
```

### Matrix id → name
| id | matrix | | id | matrix |
|----|--------|--|----|--------|
| 1 | Onslaught | | 18 | Overflow |
| 2 | Wellspring | | 19 | Profanation |
| 3 | Unbreakable | | 20 | Virulent Toxin |
| 4 | Swiftrush | | 21 | Chasing Dawn |
| 5 | Bulwark | | 30 | Momentum |
| 6 | Battlewill | | 32 | Bloodbath |
| 8 | Bramble | | 33 | Timeweave |
| 10 | Cure | | 34 | Keeneye |
| 12 | Strive | | 39 | Unyielding Oath |
| 15 | Harvest | | 40 | Ebullition Strike |
| 17 | Fury | | 61 | Furyedge 🔥 |
| | | | 62 | Etherplague 🔥 |
| | | | 63 | Colossguard 🔥 |
| | | | 64 | Swiftraid 🔥 |
| | | | 65 | Swiftsmite 🔥 |
| | | | 66 | Evolguard 🔥 |

🔥 = the 6 INFERNO-only matrices (ids 61–66). Matrix list in-game is shown in this id order.

---

## 6. Slots (6 total)

- **Left side (1–3): fixed flat main.** Slot 1 = ATK flat, Slot 2 = HP flat, Slot 3 = DEF flat (ring).
- **Right side (4–6): rolled main** (any %/CRIT/SPD-as-sub-only/Eff stat). SPD is never a main.
- A matrix can appear on either side.

---

## 7. JSON output (gear_final.json / etheria_gear_export.json)
```json
{ "instance": 115088, "template": 17832, "level": 15, "locked": false,
  "matrix_slots": 3, "matrix_id": 66, "matrix": "Evolguard",
  "main": { "stat": "ATK%", "value": 50.0 },
  "subs": [ {"stat":"CRIT Rate","value":4.4,"rolls":1},
            {"stat":"CRIT DMG","value":13.2,"rolls":3},
            {"stat":"SPD","value":2.7,"rolls":0},
            {"stat":"DEF","value":27.2,"rolls":1} ] }
```
- `value` = true value (UI rounds it). `rolls` = upgrade count of that sub (4 = maxed).
- Note: this dataset is the **unequipped** inventory sync; equipped pieces sync separately.
