# How to drive this project with Claude Code

Most of the work is done by machinery, not by what you type. This file explains the
machinery, then gives you the small amount you still have to say.

---

## The four layers, and what each one guarantees

Prompting advice usually stops at "write a good prompt." That fails on the day you write a
lazy one. These four layers are ordered by how little they depend on you remembering.

| Layer | Where | Cost | Guarantees |
|---|---|---|---|
| **1. Always-loaded rules** | `CLAUDE.md` (~170 lines, ~2.5k tok) | every session | The protocol, the 6 directives, and 13 facts that can't be silently contradicted |
| **2. Prompt compilation** | `CLAUDE.md` §0, "Compile the request before acting" | ~40 tok/task | Every ask becomes Task / Phase / **Done when** / Riskiest before any work starts |
| **3. Deterministic routing** | `.claude/hooks/route.sh` | 0 to 60 tok/turn | 10 skill routes fire on your prompt text, whether or not the model was going to reach for them |
| **4. On-demand facts** | the domain constitution, grepped, kept private | 0 unless needed | The arithmetic behind every rule, without paying for it every session |

Layer 3 is the one that matters most and the one people skip. A routing *table* in a
steering file is a suggestion the model can rationalize past. A `UserPromptSubmit` hook is
not, it runs before the model sees anything.

---

## The kickoff prompt

`CLAUDE.md` is already loaded and §0 compiles whatever you type. So the prompt is now
genuinely just the task:

```
Phase 1, next unblocked item on the build plan. Tell me which and why the ones before it
are satisfied, then build it.
```

That's a complete prompt. You do not need to restate the project, the rules, or the
stack, restating them wastes tokens and adds nothing.

Add a `Done when:` line **only when you know the gate better than the repo does**:

```
Task: src/signalguard/risk/sizing.py, ATR-unit stops to contracts or shares.
Done when: a 2xATR MNQ swing stop at $8k equity REFUSES to arm and names the band it
violated, and a 0.25xATR M2K intraday stop returns 1 contract at 0.74%.
```

That gate encodes a *rejection*, which is the thesis of the project. The sizer that quietly
rounds to 1 contract instead of refusing is exactly the bug that produced the original wrong
MNQ decision.

**When you want to see the compiled prompt before it runs**, use the escape hatch:

```
/qd write the sizer
```

`/qd` prints the compiled block, Task, Phase, Done when, Riskiest, Skills, Reads, and
stops. Correct any line, then say go. Use it when the task is expensive or ambiguous;
skip it when it's obvious.

---

## The four sentences that do the most work

Each maps to a rule already loaded, so the short form triggers the long behavior.

| Say this | And you get |
|---|---|
| **"Done when: `<observable>`"** | A verifiable gate instead of a vibe. Triggers `verification-before-completion`. |
| **"Name the assumption most likely to be wrong."** | The adversarial pass that overturned five decisions in this repo, applied *before* the work instead of after. |
| **"Prove the failure path."** | Tests for the kill switch firing and the sizer refusing, not just the happy path. |
| **"Cite the file:line, don't restate it."** | Answers grounded in the repo at a fraction of the tokens. |

---

## What the hook actually catches

`.claude/hooks/route.sh` matches on intent, with word boundaries, and emits at most 3 lines.
It is silent on most turns.

| You write | It injects |
|---|---|
| anything naming Nautilus / Databento / IBKR / Rithmic | use `context7`, not memory (§1.6) |
| "broken", "traceback", "not working", "why is…" | `systematic-debugging`, reproduce first |
| "is it done", "all tests pass", "ready to ship" | `verification-before-completion` |
| sizer, risk, kill switch, DSR, purge, walk-forward, roll | `test-driven-development` + the failure-path rule |
| `except`, fallback, retry, "defaults to" | `silent-failure-hunter` |
| chart, plot, axis, palette, heatmap | `dataviz`, before the first line of chart code |
| "use MNQ instead", "reconsider the broker" | The instrument decision is closed to preference, open to arithmetic |
| "read the research and summarize" | 1.7 MB / 51 files, grep it |
| non-display, licensing, Section 1256, CPA | Phase 0: produce the artifact, not the answer |
| "commit" | `commit-commands:commit` + the §1.6 reminder |

Two bugs from the first version are worth knowing about, because they are the failure mode
of every naive routing hook: it matched bare substrings, so `*fail*` fired on the phrase
"prove the failure path", which appears in half the legitimate prompts here, and it used
`case`, which stops at the first match, so "the chart is broken" got debugging and never got
`dataviz`. Both are fixed; there's a test battery at the bottom of this file.

---

## Plugins: what's on, what's off, and why

26 plugins were installed globally. Their skill descriptions are advertised to the model at
session start, so an unused plugin is a standing tax on every conversation, and a "do not
load this" line in `CLAUDE.md` **saves nothing**, because the descriptions were already paid
for. Only disabling removes the cost.

`.claude/settings.json` disables 14 **for this project only**. They stay available everywhere
else you work.

**Kept, each is named in `CLAUDE.md` §0 or does real work here:**

| Plugin | Why it stays |
|---|---|
| `superpowers` | brainstorming, TDD, systematic-debugging, verification, the process spine |
| `pr-review-toolkit` | `silent-failure-hunter` is a named §0 route; a silent fallback here is a live incident |
| `context7` | the only sanctioned source for Nautilus/Databento/IBKR API facts |
| `commit-commands`, `code-review` | committing and reviewing |
| `claude-md-management` | keeping this steering system honest as it drifts |
| `remember` | end-of-session state so the next one starts warm |
| `security-guidance` | secrets, and the publishing one-way door |
| `skill-creator` | you are now maintaining skills in this repo |
| `github` | needed at Phase 5, cheap until then |

**Disabled here:**

| Plugin | Reason |
|---|---|
| `vercel` | ~35 skills, the single largest offender. No web deploy in this project. |
| `figma`, `supabase`, `playwright`, `chrome-devtools-mcp`, `typescript-lsp`, `frontend-design`, `playground` | wrong stack entirely, this is Python 3.12 + numpy + NautilusTrader |
| `feature-dev` | duplicates `superpowers` brainstorming → writing-plans → executing-plans, and its agents are cold-start subagents, which `CLAUDE.md` §0 warns against in a repo with docs this large |
| `code-simplifier` | duplicated three ways, `pr-review-toolkit:code-simplifier` and the built-in `/simplify` both exist |
| `agent-sdk-dev` | you are not building an Agent SDK app |
| `ralph-loop` | autonomous looping is a poor fit where "done" means a specific gate passed |
| `greptile` | sends repo content to an external service. This repo is private and not yet published. Not worth the exposure. |
| `serena` | semantic code toolkit, largely redundant against built-in search on a 1,711-line codebase |

The one to reconsider later: **`github`** becomes load-bearing at Phase 5, and
**`chrome-devtools-mcp`** stays off permanently, the single browser task in the plan
(reading CME MBT/MET specs) is explicitly a human in a browser, because every
automated attempt was blocked.

---

## Phase-shaped prompts

### Phase 0, the blocking, no-code phase

Phase 0 is phone calls, emails, and a browser. Claude cannot close those items; it can only
prepare them. Ask for the artifact, not the answer:

```
Draft the Databento licensing questionnaire response and the email to
marketdata@cmegroup.com. Both must ask for a determination in writing, and must name
the specific tier options ($208/$457/$609 per exchange per year) so the reply is a
number and not a brochure.
```

### Phase 1, the harness

Dependency order matters more than the module. Anchor on the gate:

```
Phase 1, next unblocked item on the build plan. Read the checklist, tell me which item is
next and why the ones before it are satisfied, then build it.

Done when: the Phase 1 gate for that item passes. For the validation module specifically
the gate is the PAIRED check, a noise strategy REJECTED at N=200 and ACCEPTED at N=5.
```

That paired check is the load-bearing test in the
phase, because it proves the harness works *and* why the trial counter must be
tamper-evident.

### Phase 2, the hunt

Pre-registration is mechanical and must happen before any fitting:

```
Pre-register hypothesis <X> as a manifest in the trial ledger BEFORE any fitting: stated
economic rationale, trial budget (cap 10), seeded starting count for published-literature
prior trials, data range, cost band. Then run it. If it exceeds budget, stop and log the
rejection, that IS the deliverable.
```

### Writeups and the portfolio surface

```
Write the Phase <N> writeup into docs/writeups/. Lead with what got REJECTED and why.
Every number cites its manifest UUID. No dollar signs on any axis.
Normalized metrics only, and include the CFTC 4.41(b)(1)(i) statement.
```

---

## Anti-patterns, specific to this repo

| Don't say | Because |
|---|---|
| "Make the backtest look better." | The gate exists to reject. A better-looking number is a defect report. |
| "Try 1/5/15/30/60-minute bars and see what works." | Timeframe-shopping multiplies trial count and the DSR gate must absorb it. Also: there is no 5-minute Databento bar. |
| "Read the research directory and summarize." | 1.7 MB, 51 files. Grep for the claim you need. The hook will stop you. |
| "Just get it working, skip the tests." | In `risk/` and `execution/` the failure path *is* the feature. |
| "Add a dashboard so we can see it." | Explicitly on Phase 1's skip list. Observability arrives in Phase 2.5, fully designed, at 13 to 15 hours and zero containers. |
| "Should we reconsider MNQ / crypto / Coinbase?" | Decided on measured arithmetic. Bring new arithmetic or don't reopen it. |
| "Read CLAUDE.md and the constitution and PLAN and DECISIONS first." | That's ~34k tokens to answer a question that needed one grep. §0 exists so this never has to be typed. |

---

## Session hygiene

- **Start narrow.** One task per session. `CLAUDE.md` costs ~2.5k tokens before you type a
  word; everything after that should earn its place.
- **End with `/remember`.** Writes session state so the next one starts warm instead of
  re-deriving where you were.
- **Log as you go.** `DECISIONS.md` is written during the session, never reconstructed. It
  costs minutes and it is the strongest portfolio artifact per unit of effort.
- **Run `/fewer-permission-prompts` once**, early. It scans your transcripts and allowlists
  the read-only commands you actually use.
- **When `CLAUDE.md` drifts**, run `claude-md-management:revise-claude-md` rather than
  editing by hand, drift in the router is worse than drift in the constitution, because
  the router is what's always loaded.

---

## Regression test for the hook

The hook is the layer most likely to rot silently. Re-run this after editing it:

```bash
t(){ printf '%s\n' "--- $1"; python3 -c "import json,sys;print(json.dumps({'prompt':sys.argv[1]}))" "$1" \
     | ./.claude/hooks/route.sh | sed 's/^/    /'; }

t "prove the failure path for the sizer"        # TDD only, NOT debugging
t "download the databento history"              # context7 only, NOT verification
t "the chart is broken, why is the axis wrong"  # debugging AND dataviz, both
t "next unblocked Phase 1 item"                 # silent
```

The first two are the v1 false positives; the third is the v1 false negative. If any of
them changes behavior, the routing regexes have drifted.
