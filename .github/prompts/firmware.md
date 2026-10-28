# New Hapax firmware

Squarp has released Hapax OS firmware `$VERSION`, which `hapax/rules.py` doesn't know about yet.
Add support for it and open a pull request.

## Sources

- Changelog: https://squarp.net/hapax/firmware/ (find the `$VERSION` entry).
- Binaries: `https://squarp.net/hapax/hapaxOS/<version>/hapax.bin`.
  Diff `strings` of the `$VERSION` bin against the previous release's bin to find new or removed definition-parser keywords.

Only the changelog and the bin strings count as evidence.
Ignore changes that don't touch instrument definition files (sequencer, UI and MIDI-handling fixes).

## Changes

1. Create branch `firmware/$VERSION`.
2. Add `$VERSION` to `RELEASES` and update `LATEST` in `hapax/rules.py`.
3. For each definition change, add or change the rule in `hapax/rules.py` gated on `fw >= (major, minor)`, following the existing style.
   Cite the source in a comment, as the file already does: `# $VERSION changelog` or `# $VERSION bin strings`.
4. Add tests for each rule change in `tests/test_rules.py`, and update tests that hard-code the latest firmware.
5. Run `uv run python -m pytest` until it passes.

## Pull request

Commit, push and open a PR against `main` with `gh pr create`.

- Title: `feat: support Hapax OS $VERSION` if any rule changed, otherwise `fix: recognise Hapax OS $VERSION`.
- Commit message: the same as the title.
- Body: a short summary, then one bullet per rule change with its source (quote the changelog line or name the keyword).
  End with a "Check on hardware" checklist of each rule change, since none of them have been probed.
  If nothing changed for definitions, say so and quote the changelog headings you ruled out.
