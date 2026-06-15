# COCKPIT — Learnings

Seeded 2026-06-11 from house-wide lessons that bind this project. Append new ones as they occur.

- **sqlite3.connect() creates files.** A typo'd path silently creates an empty .db (stray 0-byte `dealroom/dealroom.db` exists from this). ALL connections to foreign DBs use `file:...?mode=ro` URI; own DB connections go through one db.py factory that validates the path.
- **journal_mode=DELETE, never WAL** — WAL sidecar files corrupt under OneDrive sync.
- **Never `open(path, 'w')` on an original file** — temp → verify → `os.replace`. TASKS.md-class trust damage is real.
- **Never blank .env values** — read before write, preserve non-empty keys.
- **openpyxl: read-only is fine; never write deliverable xlsx with it** (COM only, house rule). Seed import reads xlsx — allowed.
- **Excel COM fails on OneDrive paths** — if COM is ever needed, stage to local temp first. (Seed import uses openpyxl read, so not affected.)
- **Test against real data before claiming done** — report N/M/K counts from actual runs, not fixtures only.
- **Background/review agents are blind** — pre-load file paths, rules, and context into every agent prompt.
- **Lazy cleanup must run on EVERY entry point that depends on the cleaned state** — expired-lease reaping only on read paths let a dead lease accept results (PM M1 recheck).
- **Server children die with the session** — anything Roman opens later needs a detached Start-Process + Startup-folder launcher (schtasks needs admin). PS1: ASCII only, no backtick continuations.
- **Formatter hook strips "unused" imports between two same-message edits** — add import and usage in ONE edit, or re-add after.
