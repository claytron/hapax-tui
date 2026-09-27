# Round 4 — open questions

Firmware: 3.10

Same routine as round 2: load onto a scratch track; a successful load renames the track to the probe ID.
Record `loads fine` or `SYNTAX ERROR line N`, plus anything in the "Look for" column.

| File | Tests | Look for | Result |
|---|---|---|---|
| F01_PC_NONAME | `1` in `[PC]`, no name | | SYNTAX ERROR line 5 |
| F02_PC_MSB_NONAME | `1:1:NULL` in `[PC]`, no name | | SYNTAX ERROR line 5 |
| F03_DRUM_NONAME | `1:NULL:NULL:36`, no name (sets TYPE DRUM) | If it loads: what row 1 is called | SYNTAX ERROR line 6 |
| F04_COMMENT_EOF | `[COMMENT]` still open at end of file | If it loads: is the comment shown | When I "show info" I see `F04 Open Comment` |
| F05_CC_EOF | `[CC]` still open at end of file | If it loads: is CC74 named `F05 CUTOFF` | yes it is |
| G01_COMMENT_CHARS | ``% & ; [ \ ] ^ ` { \| } ~ é`` in `[COMMENT]`, one per line | If it errors, the line gives the first rejected character; delete that line and reload to find the next. If it loads, which characters display | SYNTAX ERROR line 5 for all |
| H01_CC_NAME_LEN | CC names of 8, 12, 16, 20, 24, 32, 48, 64, 100 characters on lines 5–13 | If it errors, the line gives the first length that is too long. If it loads, where each name is cut in the CC list; the digits give the position | see image |
| H02_TRACKNAME_LEN | 64-character TRACKNAME | Where the track name is cut; the digits give the position | see image |
| H03_LONG_FILE_NAME_x… | 64-character file name | Does it appear in the file list; does it load | shows and loads fine |

## Round 4 findings

Rejected: PC `1` and `1:1:NULL` with no name, a drum lane with no name, and every name-rejected character in `[COMMENT]` (``% & ; [ \ ] ^ ` { | } ~ é``, each reported on its own line as the others were deleted).
Accepted: `[COMMENT]` and `[CC]` still open at end of file (the comment shows, CC74 is named), CC names up to 100 characters, a 64-character TRACKNAME, a 64-character file name.
Display: the CC list shows the first 15 characters of a name (L16 through L100 all read `…012345`); the track header shows the first 9 of the track name (`H02-56789`), the NAME field 8 before it scrolls.
The file list shows about 27 characters of a file name (`H03_LONG_FILE_NAME_xxxxxxxx`); on the selected row the LOAD button covers the tail.
A 64-character name still loads.
