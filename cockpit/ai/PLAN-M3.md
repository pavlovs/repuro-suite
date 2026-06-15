# M3: Agent skills + deals.md generated section + trial readiness

## Summary
RC/FC can sync any session with the cockpit in one command; deals.md carries an auto-generated,
never-stale pipeline block. The local trial (Roman as daily driver + curation pass) starts after
this ships — the trial itself is Roman's part, not buildable.

## Delivered
1. `/cockpit-pull` + `/cockpit-push` skills — `~/.claude/commands/` (RC) + `CLAUDE_REPURO/.claude/commands/` (FC).
   Push protocol: pull-first (versions), codename lint against local glossary, dry-run diff, apply.
2. `scripts/generate_deals_md.py` — replaces the `<!-- cockpit:begin -->` block in deals.md:
   stage snapshot of all mirrored deals (master: dealroom.db, synced timestamp) + open next steps
   for cockpit-owned deals. temp→verify→os.replace. Ran live: 14-deal block written.
3. Server persistence (pulled forward — trial precondition): `start_cockpit.ps1` detached start +
   Startup-folder `RepuroCockpit.cmd` (schtasks denied, no admin). Survives session end + reboot.

## Deferred to the trial (Roman)
- Curation pass: promote/kill the 43 staging tasks, add prereq links, flip deals to cockpit-owned.
- Trial exit criterion (ROADMAP): Roman stops opening TASKS.md for workstream items.

## Validation results
- Skills registered and visible in both RC (`~/.claude/commands/`) and FC (workspace) locations;
  push protocol covered by M1 import tests (version-required, fail-closed, dry-run).
- generate_deals_md.py ran live: 22-line block in deals.md (14 deals, synced stamp). Fail-closed
  verified: duplicate markers → exit 1; missing markers without --init → exit 1; nothing written.
- deals.md claimed/released via .active protocol during edits.
- Reviewed within the M2-M4 PM review (generator findings R4/R5 fixed + re-review PASS).

### Verdict
PASS (trial + curation = Roman's part, open)
