# Round 3 — defaults, and firmware 2.21

## Part 1: on 3.10 (now)

These three need observing, not just loading.
After loading, open the CC74 automation lane and note the value it starts at.

| File | Tests | 3.10: lane starts at |
|---|---|---|
| E01_CC_SECTION_DEFAULT | `74:DEFAULT=100` in `[CC]` — changelog says 3.10 ignores it | |
| E02_AUTO_LINE_DEFAULT | `CC:74 DEFAULT=100` on the `[AUTOMATION]` line — control, should be 100 | |
| E03_CC_SHORTHAND_DEFAULT | `74:100` shorthand in `[CC]` | |

## Part 2: on 2.21

Back up the SD card first: projects saved on 3.x may not open on 2.21.
Run the three E files again, then P05 and every r2 file.
The 3.10 column is the recorded result, for comparison; only differences matter.

| File | 3.10 | 2.21 |
|---|---|---|
| r3/E01_CC_SECTION_DEFAULT | see part 1 | loads; lane `E01 CUTOFF` DEFAULT 100 — section default honoured |
| r3/E02_AUTO_LINE_DEFAULT | see part 1 | loads; lane `E02 CUTOFF` DEFAULT 100 — control as expected |
| r3/E03_CC_SHORTHAND_DEFAULT | see part 1 | loads; lane `E03 CUTOFF` DEFAULT 100 — shorthand is a default |
| r3/E04_NRPN_BARE_DEFAULT | — | lane value: 64k |
| r3/E05_ASSIGN_EXTRA_FIELD | — | pot 1 default: 0 / pot 2 default: 100 |
| P05_DRUM16 | ok | SYNTAX ERROR line 11 |
| r2/A01_CC_SHORTHAND | ok | |
| r2/A02_CC_LEADZERO | ok | |
| r2/A03_CC_120 | ok | |
| r2/A04_CC_127 | ok | |
| r2/A05_CC_DUP | ok | |
| r2/A06_CC_NONAME | err |  |
| r2/A07_CC_DEF128 | ok | SYNTAX ERROR line 6 |
| r2/A08_PC_0 | err |  |
| r2/A09_PC_129 | err |  |
| r2/A10_DRUM_ON_POLY | ok | |
| r2/A11_UNKNOWN_SECT | err | |
| r2/A12_LOWER_SECT | ok | |
| r2/A13_NRPN_MSB1_LSB200 | err | |
| r2/A14_ASSIGN_CC120 | err | |
| r2/A15_AUTO_CC120 | err | |
| r2/B01_TYPE_POLYAT | err | |
| r2/B02_TYPE_lower | ok | |
| r2/B03_OUTPORT_USBD1 | ok | SYNTAX ERROR line 4 |
| r2/B04_OUTCHAN_17 | err |  |
| r2/B05_MAXRATE_5 | err | |
| r2/B06_VERSION_2 | ok | |
| r2/B07_DUP_DIRECTIVE | ok | |
| r2/B08_TRACKNAME_AMP | err | |
| r2/C01_BANG | ok | |
| r2/C02_DQUOTE | ok | |
| r2/C03_DOLLAR | ok | |
| r2/C04_PCT | err | |
| r2/C05_APOS | ok | |
| r2/C06_STAR | ok | |
| r2/C07_SEMI | err | |
| r2/C08_LT | ok | |
| r2/C09_EQ | ok | |
| r2/C10_GT | ok | |
| r2/C11_QUEST | ok | |
| r2/C12_AT | ok | |
| r2/C13_LBRACK | err | |
| r2/C14_BSLASH | err | |
| r2/C15_RBRACK | err | |
| r2/C16_CARET | err | |
| r2/C17_BTICK | err | |
| r2/C18_LBRACE | err | |
| r2/C19_PIPE | err | |
| r2/C20_RBRACE | err | |
| r2/C21_TILDE | err | |
| r2/C22_UNICODE | err | |
| r2/C23_LOWER | ok | |
| r2/D01_AUTO_CCPAIR | ok | |
| r2/D02_ASSIGN_CCPAIR | ok | |

## Findings

E01 on 2.21: the `[AUTOMATION]` lane came up as `E01 CUTOFF` with DEFAULT 100, and CC74 was renamed in the CC destination list and listed under a new `INSTR DEF` group.
Section defaults therefore worked on 2.21, broke in 3.00, and were fixed in 3.20 (changelog: "present in 3.00 and 3.10 alike").
Names display upper-cased: `E01 cutoff` in the file shows as `E01 CUTOFF`.
The `74:100` shorthand (E03) behaves exactly like `74:DEFAULT=100`: an undocumented but working spelling of a section default.

Round 3 on 2.21, differences from 3.10 only:
P05 row 16 rejected (rows 9–16 arrived in 3.10); B03 `USBD1` rejected (virtual ports arrived in 3.00); A07 `DEFAULT=128` rejected (3.00–3.10 stopped checking section defaults along with applying them).
All 23 name-character results match 3.10.
E04: the NRPN bare fourth field set the lane default (screen showed "64k") — it is a shorthand, like E03.
E05: `1 CC:74:100` left pot 1 at default 0; the control `2 CC:71 DEFAULT=100` gave 100 — the extra field is silently dropped.
