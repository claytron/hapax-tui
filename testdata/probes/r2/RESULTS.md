# Round 2 — one variant per file

Firmware: 3.10 (from `hapax.bin` in the 2026.09.25 SD backup — confirm this is what is installed)

Each file tests exactly one thing, so pass/fail is all that's needed.
Minimal files: `VERSION`, `TRACKNAME`, one section — round 1 showed sections are optional.
Mark `ok` or `err` (the line number is not needed; each file has only one candidate line).

The `C` files map the name character set: each names CC 74 `A<char>B`.
They matter less than `A` and `B`; skip them if short on time.

| File | Tests | Result |
|---|---|---|
| A01_CC_SHORTHAND | `24:100 x` — shorthand default, used by 8 community files | loads fine |
| A02_CC_LEADZERO | `026 x` | loads fine |
| A03_CC_120 | CC 120 in `[CC]` | loads fine |
| A04_CC_127 | CC 127 in `[CC]` | loads fine |
| A05_CC_DUP | CC 31 twice | loads fine |
| A06_CC_NONAME | `74` with no name | SYNTAX ERROR line 6 |
| A07_CC_DEF128 | `DEFAULT=128` | loads fine |
| A08_PC_0 | PC 0 | SYNTAX ERROR line 6 |
| A09_PC_129 | PC 129 | SYNTAX ERROR line 6 |
| A10_DRUM_ON_POLY | drum lane on a POLY track | loads fine |
| A11_UNKNOWN_SECT | `[FOO]` | SYNTAX ERROR line 6 |
| A12_LOWER_SECT | `[cc]` | loads fine |
| A13_NRPN_MSB1_LSB200 | `1:200:7` — LSB over 127 with MSB not 0 | SYNTAX ERROR line 6 |
| A14_ASSIGN_CC120 | `1 CC:120` | SYNTAX ERROR line 6 |
| A15_AUTO_CC120 | `CC:120` | SYNTAX ERROR line 6 |
| B01_TYPE_POLYAT | `TYPE POLYAT` — current-template feature | SYNTAX ERROR line 4 |
| B02_TYPE_lower | `TYPE poly` | loads fine |
| B03_OUTPORT_USBD1 | `OUTPORT USBD1` — current-template feature | loads fine |
| B04_OUTCHAN_17 | `OUTCHAN 17` | SYNTAX ERROR line 4 |
| B05_MAXRATE_5 | `MAXRATE 5` — not in the allowed list | SYNTAX ERROR line 4 |
| B06_VERSION_2 | `VERSION 2` | loads fine |
| B07_DUP_DIRECTIVE | `TYPE POLY` then `TYPE DRUM` | loads fine |
| B08_TRACKNAME_AMP | `TRACKNAME B08 A&B` | SYNTAX ERROR line 3 |
| D01_AUTO_CCPAIR | `CC_PAIR:1:33` automation lane — type found in firmware strings, undocumented | loads fine |
| D02_ASSIGN_CCPAIR | `1 CC_PAIR:1:33` pot assign — same | loads fine |
| C01–C23 | `! " $ % ' * ; < = > ? @ [ \ ] ^ `` ` `` { \| } ~ é abc` | 4, 7, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22 SYNTAX ERROR line 5 |

## Round 2 findings

Name characters (CC names and TRACKNAME):
accepted `! " $ ' ( ) * , . / : < = > ? @` and lowercase, plus the documented space `_ - +`;
rejected ``% & ; [ \ ] ^ ` { | } ~`` and non-ASCII (`é`).
`#` starts a comment, so it truncates rather than errors.

Rejected: CC entry with no name, PC 0, PC 129, `[FOO]` (reported on its first entry, not the header), NRPN `1:200:7`, CC 120 in ASSIGN and AUTOMATION, `TYPE POLYAT`, `OUTCHAN 17`, `MAXRATE 5`, `&` in TRACKNAME.
Accepted: `24:100` CC shorthand, `026`, CC 120 and 127 in `[CC]`, duplicate CC number, drum lane on a POLY track.

The 3.10 firmware keyword table (from `strings hapax.bin`) has no `POLYAT`/`AFTR`: the online template is ahead of 3.10.
It does have `CC_PAIR:` alongside `CC:`/`CV:`/`NRPN:`, i.e. an assign/automation type no template documents (D01, D02).

Also accepted: `DEFAULT=128`, `[cc]`, `TYPE poly`, `OUTPORT USBD1`, `VERSION 2`, a directive given twice, `CC_PAIR:` as an automation and an assign type.
Keywords are case-insensitive throughout: `trackname`, `[cc]`, `TYPE poly`, `Default=`.
