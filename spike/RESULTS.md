# Lark spike — results

Run: `uv run spike/spike.py` (lark 1.x, LALR, contextual lexer, one start rule per line kind).
Verdict: **Lark holds.** No fallback to a hand-written parser.

## Probes (68 files, OS 3.10 outcomes)

The grammar and structure pass never disagree with the hardware in the dangerous direction: nothing the Hapax loaded is rejected.
Every hardware rejection the grammar owns is caught on the reported line: `DEFAULT=NULL` (P03), no name (A06), unclosed section (P15), unknown section (A11).
The other 22 rejections are ranges, enumerations, the name charset, the 64-lane cap and the unknown directive — rule territory, by design.

## Names

11,550 community names and 682 of the author's split cleanly from their fields.
Only two contain `:`, `=` or `DEFAULT`, both correctly kept whole: `Out Clock Default`, `Paz <==> Zap`.
Names that start with digits (`1A1`, `17-Kaddish`, `1 Layer`) are unaffected: after the first whitespace only `NAME` is lexable.
Contextual lexing is what makes this work; `NAME: /\S.*/` and `JUNK: /\S+/` never compete with field tokens.

## Corpus

The author's 14 files: no grammar or structure errors.
Community, 154 files: 36 failing lines in 14 files, all genuine mistakes, no grammar bugs:

- Entry with no name: PC `1:1:NULL`, bare CC `22`, drum lanes whose name is entirely a `#` comment (sherman/filterbank_v2).
- `DEFAULT=NULL`: pandamidi/future_impact.
- `105:LPF VEL`: toraiz/as-1.
- Markdown in the file, `**TYPE** POLY`: gotharman/spazedrum_black, sequencial-dsi/prophet-xl.
- `[COMMENT]` never closed before EOF: empress/reverb, pandamidi/future_impact.

## Spans and tokens

Token columns map straight to on-screen spans: `:2000:7 BAR` gives LSB at 1–5 (0-based, end exclusive) with leading whitespace kept.
`DEFAULT.2` priority beats `JUNK` in ASSIGN/AUTOMATION tails, so `CC:71 junk here DEFAULT=100` yields two JUNK tokens then the default.

## Timing

`Novation_Peak.txt`, 364 lines: 3.9 ms cold cache, 0.11 ms warm — well inside the 50 ms guard.

## Follow-ups for the real implementation

- Expected-token lists name internal terminals (`_COLON`, `_WS`, `KEY`); they need the friendly-name map the spec already plans.
- Nameless PC and drum entries are assumed rejected like CC (A06); only CC was probed.
- `[COMMENT]` unclosed at EOF is unprobed; the spike reports it as a structure error.
