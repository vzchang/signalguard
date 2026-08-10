#!/bin/bash
# UserPromptSubmit hook: deterministic skill routing for SignalGuard.
#
# CLAUDE.md §0 carries the routing table, but a table is a suggestion. This fires the
# highest-value routes off the prompt text itself, so they don't depend on the model
# noticing. Emits AT MOST 3 lines, ~60 tokens worst case -- the whole point is to be
# cheaper than the mistake it prevents. Silent when nothing matches, which is most turns.
#
# Design rules, learned from v1:
#   - Word boundaries, never bare substrings. v1's `*fail*` matched "failure path" -- a
#     phrase in half the legitimate prompts in this repo -- so it fired constantly.
#   - Collect all matches, then print the top N by priority. v1 used `case`, which stops
#     at the first match, so "the chart is broken" got debugging and never got dataviz.
#   - Match intent, not vocabulary. "Broken / traceback / not working" means a bug.
#     "Prove the failure path" does not.
#
# Input: hook JSON on stdin. Output: stdout is injected as context. Exit 0 always.

set -u

_raw=$(cat)
_p=$(printf '%s' "$_raw" | /usr/bin/python3 -c 'import json,sys
try:
    d = json.load(sys.stdin)
    print(d.get("prompt","").replace("\n"," "))
    print(d.get("session_id",""))
except Exception:
    print(""); print("")' 2>/dev/null)
prompt=$(printf '%s\n' "$_p" | sed -n 1p)
sid=$(printf '%s\n' "$_p" | sed -n 2p)
[ -z "${prompt:-}" ] && exit 0

m() { printf '%s' "$prompt" | grep -Eqi -- "$1"; }

hits=()
add() { hits+=("$1"); }
fs_hit=""        # find-skills line, printed FIRST so an explicit ask is never cut by the cap

# --- 1. Facts that must come from a tool, never from memory (CLAUDE.md §1.6) ---
if m '\b(nautilus(trader)?|databento|ibkr|interactive brokers|ib gateway|ibapi|rithmic|tradovate|nautilus_trader)\b'; then
  add "[SKILL REQUIRED] Invoke context7 for this API's real docs. Memory is not a tool that verified it (§1.6)."
fi

# --- 2. A real defect, not the word "fail" ---
if m '\b(broken|traceback|stack ?trace|exception|regression|crashe?[sd]?|hangs?)\b|\b(does ?n.?t|is ?n.?t|not) +(work|working|running)\b|\b(test|tests|it|this|that) +(is |are )?fail(s|ed|ing)\b|\bwhy (is|does|did|are)\b|\bunexpected\b|\bsurprising\b|\bwrong (number|value|answer|result)\b'; then
  add "[SKILL REQUIRED] Invoke Skill(superpowers:systematic-debugging) before continuing. Reproduce it before proposing a fix."
fi

# --- 3. A completion claim is about to be made ---
if m '\b(is|are) (it|we|this|they|the tests?) (all )?(done|passing|working|ready|finished|complete)\b|\ball tests? pass|\bready to (ship|merge|commit|push)\b|\bdid it work\b|\bconfirm (it|that|this)\b|\bverify\b'; then
  add "[SKILL REQUIRED] Invoke Skill(superpowers:verification-before-completion) before continuing. Run the command, paste the output, then claim."
fi

# --- 4. Math where a falsifying test comes first, and the failure path IS the feature ---
if m '\b(siz(er|ing)|risk|kill ?switch|stop ?loss|margin|reconcil|position cap|order.?rate|dead.?man)\b|\b(dsr|deflated sharpe|purge|embargo|walk.?forward|pbo|cpcv|trial (count|budget|ledger))\b|\b(continuous contract|roll (rule|date|schedule)|backward_spread|back.?adjust)\b'; then
  add "[SKILL REQUIRED] Invoke Skill(superpowers:test-driven-development) before continuing. Falsifying test first. In risk/ and execution/, 'done' requires a test that proves the FAILURE path (§0)."
fi

# --- 5. Silent fallbacks are live incidents here ---
if m '\b(except|try/|catch|fall ?back|default(s|ing)? to|retry|retries|swallow|suppress|pass silently|error handling)\b'; then
  add "[SKILL REQUIRED] Invoke Skill(pr-review-toolkit:silent-failure-hunter) before continuing. A silent fallback in this repo is a live incident."
fi

# --- 6. Charts ---
if m '\b(chart|plot(s|ting)?|graph|figure|axis|axes|colou?r ?(map|scheme|palette)|visuali[sz]|dashboard|heatmap|sparkline)\b'; then
  add "[SKILL REQUIRED] Invoke Skill(dataviz) before writing any chart code."
fi

# --- 7. Decisions that are closed unless new arithmetic shows up ---
if m '\b(mnq|crypto|bitcoin|coinbase|kraken|binance|ib_async|ib.insync|prop firm|apex|topstep)\b.*\b(instead|switch|reconsider|why not|should we|use)\b|\b(reconsider|revisit|re.?open|change) (the )?(instrument|engine|broker|data ?vendor)\b'; then
  add "[route] Decided on measured arithmetic. New arithmetic can reopen it; preference cannot."
fi

# --- 8. The big-doc trap ---
if m '\b(read|summari[sz]e|go through|review|ingest|look through) ((the|all|every|this|my) )?((whole|entire|full|complete) )?(research|raw|docs?|documentation|everything|codebase|repo|all the (files|docs))\b|\bdocs/research\b'; then
  add "[route] The research archive is large and private. GREP for the claim; never read it."
fi

# --- 9a. EXPLICIT ask for a skill. Always fires, never deduped, and not gated on
#         other routes: if the user asks outright, that outranks everything.
if m '\b(find|is there|any|need|want|looking for|install|add) (an? )?(agent )?(skill|plugin|extension)\b|\bskill (for|that|to)\b|\bis there a skill\b'; then
  fs_hit="[SKILL REQUIRED] Invoke Skill(find-skills). The user is asking for a skill directly."

# --- 9b. SPECULATIVE domain match. Fallback only, and deduped per (session, domain) so a
#         long session still gets one nudge per NEW topic instead of one nudge total.
elif [ ${#hits[@]} -eq 0 ]; then
  dom=$(printf '%s' "$prompt" | grep -Eoi -m1 '\b(docker|kubernetes|k8s|terraform|ansible|helm|github actions|ci/cd|oauth|auth|accessibility|a11y|seo|lint(er|ing)?|changelog|release notes|monorepo|e2e|scrap(e|ing)|pdf|excel|spreadsheet|slack|notion|jira|figma|benchmark|profiling|animation|design system|migration|deploy(ment)?|grafana|prometheus|webhook|graphql|websocket|cron|regex|i18n|localization)\b' | head -1 | tr '[:upper:]' '[:lower:]' | tr -cd 'a-z0-9')
  if [ -n "$dom" ]; then
    marker="${TMPDIR:-/tmp}/claude-fs-${sid:-nosess}-${dom}"
    if [ ! -e "$marker" ]; then
      : > "$marker" 2>/dev/null
      fs_hit="[SKILL REQUIRED] Invoke Skill(find-skills) for '$dom' before hand-rolling it. First time this topic has come up this session."
    fi
  fi
fi

# Priority is source order. Cap at 3 so the hook never becomes the expensive thing.
# The explicit empty guard is required: macOS ships bash 3.2, where "${arr[@]}" on an
# empty array is an unbound-variable error under `set -u`.
out=()
[ -n "$fs_hit" ] && out+=("$fs_hit")
[ ${#hits[@]} -gt 0 ] && out+=("${hits[@]}")
[ ${#out[@]} -eq 0 ] && exit 0
printf '%s\n' "${out[@]:0:3}"
exit 0
