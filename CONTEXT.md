# Domain glossary

The ubiquitous language for beets-inbox. Use these terms in code, docs,
and reviews; sharpen them here when they drift.

- **Inbox** — the watched directory where new music lands (ytdl-sub,
  uploads, manual drops) before being reviewed and imported. The
  filesystem is the source of truth for what exists; the inbox library
  DB annotates it.
- **Category** — a top-level subdirectory of the inbox. Pure labeling
  today; slated to be replaced by one-inbox-per-target-library (see
  STATUS.md design section).
- **Inbox item** — the unit the user reviews and imports: either a
  **single** (a top-level audio file within a category) or an **album
  group** (a directory of audio files imported as one album).
- **Inbox library** (scratchpad) — the beets library that *catalogs* the
  inbox without touching files (`copy/move/write: no`). Its DB stores
  read tags, autotag matches, and the user's pending edits. Disposable.
- **Main library** — the real beets library files are copied into on
  import. Read by navidrome.
- **Cataloging** — running `beet import` against the inbox library so an
  item's tags become visible and editable in the UI. An item is
  **cataloged** when *all* of its audio files have rows in the inbox DB.
- **Cataloger** — the module that owns cataloging. Its interface is an
  idempotent `sync()`: reconcile the inbox directory against the inbox
  DB in both directions — catalog stable items whose files are missing
  from the DB (removing and re-importing partially cataloged groups as
  a unit), prune DB rows whose files vanished, and remember the last
  catalog error per item. Runs at startup and on a periodic sweep;
  there are no filesystem events.
- **Sweep** — one execution of the Cataloger's `sync()`.
- **Stability window** — the minimum mtime age a file must reach before
  a sweep will catalog it, protecting against cataloging mid-write.
- **Sidecar** — a yt-dlp `.info.json` file next to an audio file,
  carrying source URL, uploader, title, and upload date.
- **Import / commit** — copying an item into the main library with
  confirmed tags, then removing it from the inbox (DB row, files,
  sidecars).
- **Discard** — removing an item from the inbox without importing it.
