# Hardware probe results

Firmware: _____

Load each file onto a scratch track in a scratch project.
A successful load renames the track to the probe ID.
Ports and channels are all `NULL`, so routing is untouched; only P05 changes the track type (to DRUM).

Where to look:
- CC, NRPN and CC_PAIR names: the destination list when creating an automation lane.
- Pot assignments: `2ND` + `fill`.
- COMMENT: hold the `2ND`-`TRACK` INSTRUMENT DEF encoder.

Run P00 first. If it doesn't load, stop — everything else depends on it.

| File | Question | Look for | Result |
|---|---|---|---|
| P00_BASE | Control: does a clean current-template file load? | Renamed `P00 BASE`; pots 1–2 assigned; lanes CC74 and PB; new lanes default to 24ppqn max rate | loads fine |
| P01_NAMES | Which characters survive in names? | How N01–N14 display; is N09 cut at `#`; is N11 truncated and where; COMMENT punctuation | syntax error line 23 |
| P02_TRKNAME | Punctuation in TRACKNAME | Loads at all? Name shown as `P02/Nm.x,y` or mangled? | loads fine |
| P03_CCSYN | CC syntax variants | Which of S01–S11 appear; do S02/S03/S05 get default 100; S04 default; S10 or S11 wins for CC31 | syntax error line 20 |
| P04_NRPN | NRPN variants | Which of R01–R06 appear; R03 default 64?; R04 shows as 8:2, R05 as 15:80? | loads fine |
| P05_DRUM16 | Drum rows 9–16, duplicate row | 16 lanes or 8; row 16 named `L16` or `L16 SECOND` | loads fine |
| P06_ASSIGN | Pot assign variants | Which of pots 1–8 are assigned; pot 3 default 127?; pot 4 default 100? |  loads fine |
| P07_AUTO | Automation types, DEFAULT on a lane | Six lanes created; CC71 lane starts at 20? | loads fine |
| P08_AUTO65 | 65 lanes, limit 64 | Rejected, or 64 lanes (is CC64 missing)? | syntax error line 90 |
| P09_PC129 | 129 PCs, limit 128 | Rejected, or does PC129 appear? | loads fine |
| P10_CCPAIR | CC_PAIR section | Loads; `Mod 14bit` / `Vol 14bit` offered as CC-pair destinations | loads fine |
| P11_UNKDIR | Unknown directive `OUTAN 4` | Rejected, or loads with U01 present? | syntax error line 9 |
| P12_BADENT | CC 128 entry | Rejected, or loads with B01/B03 but not B02? | syntax error line 18 |
| P13_MINIMAL | Are sections optional? | Loads with only VERSION and TRACKNAME? | loads fine |
| P14_NOVER | Missing VERSION | Rejected, or loads with V01? | loads fine |
| P15_UNTERM | `[CC]` never closed | Rejected? C01 present? C02 (after the unclosed section) present? | syntax error line 19 |
| P16_LOWER | Lowercase `trackname` | Renamed `P16 LOWER`, ignored, or rejected? | loads fine |
| P17_CRLF | CRLF line endings, tab separator | Loads like P00, renamed `P17 CRLF` | loads fine |

Also note how the Hapax reports a rejected file, since the validator's message could mirror it.

## Round 1 findings

The Hapax rejects the whole file at the first bad line, reporting `syntax error line N`.
N is the 1-based physical line number, comments included — every report landed exactly on the probed line.
So "loads fine" proves every variant in that file was accepted; a rejection proves only the reported line.

Rejected: `&` in a CC name, `DEFAULT=NULL`, a 65th automation lane, unknown directive `OUTAN`, CC 128, an unclosed `[CC]` (reported at the next section header).
Accepted: `/ , ( ) . :` in names, lowercase `Default=`, missing `VERSION`, lowercase `trackname`, 129 PCs, drum rows 9–16, a duplicate drum row, NRPN bare 4th field, omitted MSB, LSB over 127 with MSB 0, `CC:16:127`, name text before `DEFAULT=` in ASSIGN, CV voltage default, `DEFAULT=` on an automation lane, `CC_PAIR`, CRLF, tabs, a file with no sections.
