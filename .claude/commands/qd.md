---
description: Compile a rough ask into the repo's gated task prompt, and show it before running.
argument-hint: <rough one-line ask>
---

Compile the request below into SignalGuard's task form. **Print the compiled block, then
stop and wait.** Do not build anything this turn, the point of `/qd` is to let the gate be
corrected before work starts, which is the one thing the always-on rule in `CLAUDE.md` §0
cannot do.

Rough ask: $ARGUMENTS

Produce exactly this, and nothing before it:

```
Task:      <the concrete file or artifact, a path if one exists or should>
Phase:     <0 | 1 | 2 | 2.5 | 3 | 4 | 5, with the reason in four words>
Done when: <an observable that is ALLOWED TO COME OUT FALSE>
Riskiest:  <the single assumption most likely to be wrong, not a list>
Skills:    <the ones that will actually fire, in order>
Reads:     <the file:line ranges you will open, or "none, already in context">
```

Then one line: `Ready, say go, or correct any line.`

Rules for the compile:

- **`Done when:` is the load-bearing line.** It must name a command and its expected
  output, or a specific assertion. "The sizer works" is not a gate. "Sizing a 2xATR MNQ
  swing stop at $8k equity refuses to arm and names the band it violated" is.
- **Prefer a rejection to an acceptance.** This repo's thesis is a harness that can
  honestly reject; a gate phrased as "X is refused / caught / rejected" is stronger
  evidence than one phrased as "X is produced." Where both are available, gate on both.
- **For anything under `risk/`, `execution/`, or reconciliation**, `Done when:` must
  include the failure path, not only the happy path (`CLAUDE.md` §0).
- **Check the tripwires** in `CLAUDE.md` §2 before writing `Riskiest:`. If the ask
  contradicts one, say so in `Riskiest:` and quote the tripwire rather than silently
  proceeding.
- **`Reads:` is a budget, not a wishlist.** Name line ranges. If the answer is
  the whole `docs/` tree, the answer is wrong, grep it instead.
- If the ask is a Phase 0 item, `Task:` is an **artifact** (an email, a questionnaire
  response, a checklist), never an answer, Phase 0 is closed by a human, not by code.
- If you cannot write a falsifiable `Done when:`, print only that problem and the single
  question that would resolve it. Do not invent a gate to fill the slot.
