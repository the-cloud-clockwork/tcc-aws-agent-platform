# TODO.md — Minor Items & Pending Decisions

> **Purpose:** Small items, notes, and things to not forget. Not major blocks — those go in BLOCKS.md.

---

## Execution Order

**Block 1 → Block 2 → Block 3 → Block 4**

| Block | Theme | Must-Haves | Total Items | Effort |
|-------|-------|-----------|-------------|--------|
| 1 | Schema & Blueprint Hardening | 2 | 2 | Medium |
| 2 | Security & Production Hardening | 3 | 7 | Large (IAM) + 4 Low |
| 3 | Runtime & Observability | 3 | 5 | 2 Low + 2 Medium + 1 monitor |
| 4 | Infrastructure Modules & Cleanup | 1 | 8 | 1 Medium + 4 Low + 3 sweep |

**Total:** 22 items across 4 blocks. 9 must-have, 5 sweep remainders, 3 nice-to-have, 5 someday/low.

---

## Pending Decisions

- [ ] ENH-019 scope: tackle all 17 IAM items at once or split into sub-phases? (Large effort block)
- [ ] Block 3 ordering: Cedar policies (ENH-001) before or after middleware (ENH-003)?
- [ ] KI-001: check AWS Issue #809 status before starting Block 3 — may affect Cedar/Gateway work

---

## Notes

- 2026-03-31: Project initialized with operator pattern
- 2026-04-08: Organized 20 enhancements + 8 sweep remainders + 1 known issue into 4 execution blocks
- 6 enhancements deferred to backlog (ENH-004, 005, 006, 009, 010, 020) — nice-to-have/someday

---

## Don't Forget

- [ ] ENHANCEMENTS.md status field should be updated as items move through blocks (proposed → scheduled → in-progress → done)
- [ ] MVP.md needs populating once Block 1 starts — track release criteria there
