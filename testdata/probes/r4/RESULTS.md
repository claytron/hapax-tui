# Round 4 — open questions

Firmware: 3.10

Same routine as round 2: load onto a scratch track; a successful load renames the track to the probe ID.
Record `loads fine` or `SYNTAX ERROR line N`, plus anything in the "Look for" column.

| File | Tests | Look for | Result |
|---|---|---|---|
| F01_PC_NONAME | `1` in `[PC]`, no name | | |
| F02_PC_MSB_NONAME | `1:1:NULL` in `[PC]`, no name | | |
| F03_DRUM_NONAME | `1:NULL:NULL:36`, no name (sets TYPE DRUM) | If it loads: what row 1 is called | |
| F04_COMMENT_EOF | `[COMMENT]` still open at end of file | If it loads: is the comment shown | |
| F05_CC_EOF | `[CC]` still open at end of file | If it loads: is CC74 named `F05 CUTOFF` | |
| G01_COMMENT_CHARS | ``% & ; [ \ ] ^ ` { \| } ~ é`` in `[COMMENT]`, one per line | If it errors, the line gives the first rejected character; delete that line and reload to find the next. If it loads, which characters display | |
| H01_CC_NAME_LEN | CC names of 8, 12, 16, 20, 24, 32, 48, 64, 100 characters on lines 5–13 | If it errors, the line gives the first length that is too long. If it loads, where each name is cut in the CC list; the digits give the position | |
| H02_TRACKNAME_LEN | 64-character TRACKNAME | Where the track name is cut; the digits give the position | |
| H03_LONG_FILE_NAME_x… | 64-character file name | Does it appear in the file list; does it load | |
