# TODO

## Bugs

### Files dropped by ytdl-sub get stuck in "Cataloging…" forever

Observed in production (2026-08-28): 5 of 7 inbox items (`live-sets/*.m4a`)
have `cataloged: false` permanently — the UI shows "Cataloging…" with the
import buttons disabled, and there is no way to recover from the UI except
Discard.

Root cause (reproduced locally against a demo server):

1. yt-dlp/ytdl-sub downloads to a temp name (`track.m4a.part`) and then
   renames it to the final name. The watcher's create event fires for the
   `.part` name, which fails the audio-extension check and is ignored.
   The rename emits a `FileMovedEvent`, but `_InboxEventHandler` only
   overrides `on_created` — moves are silently dropped, so the file is
   never cataloged.
2. There is no reconciliation: nothing scans for uncataloged files at
   startup or periodically, so a missed event (moved-in file, catalog
   failure, service down when the file arrived) is never retried.

Candidate fixes (do both):
- Handle `on_moved` in the watcher (schedule the move destination the same
  way as created files).
- Add a reconciliation sweep at startup + periodically: any inbox audio
  file not in the inbox beets DB gets cataloged. This also self-heals the
  existing stuck production entries after a deploy/restart.

Test hook: the `.part`-then-rename repro is scriptable against the demo
server; a watcher-level pytest needs the `InboxWatcher` running (not
covered by the TestClient harness, which skips the lifespan).

### Sidecar lookup never finds yt-dlp info.json files

All items in the production inbox have `source_url: null`. The backend
looks for sidecars by *appending* to the audio filename
(`_parse_sidecar`: `track.m4a` → `track.m4a.info.json`), but yt-dlp's
`--write-info-json` *replaces* the extension (`track.m4a` →
`track.info.json`), so if ytdl-sub writes sidecars at all, beets-inbox
never finds them. Fix: try both naming conventions (and confirm the
ytdl-sub preset actually writes info.json — if it doesn't, enable it).

Without sidecars the UI loses source URL / video ID / uploader — exactly
the metadata needed to tell near-duplicate downloads apart (see the two
`nΦra @ Bucht der Träumer:innnen` entries in production, likely the same
video re-downloaded after a YouTube title edit, or two distinct uploads —
undecidable from the API precisely because source_url is missing).

### Uncataloged items show no tags even when the file has embedded tags

`_read_file_tags` (mutagen direct read) in `services/inbox.py` is dead
code — `_build_item` only reads tags from the beets DB, so an uncataloged
item renders with no metadata at all even though the file itself is tagged.
Either wire it up as a fallback for uncataloged items or delete it.

## Features

- Better progress reporting in the frontend while uploading
- Edit per-track data in the frontend
- Bulk import for multiple albums should be straightforward
- Category selector should default to "uncategorized" instead of empty
- Some sort of duplicate handling
- ytdl-sub interop: figure out discard behaviour — if inbox files are deleted on discard, ytdl-sub archive prevents re-download; consider a "skip/hide" state instead of deleting
