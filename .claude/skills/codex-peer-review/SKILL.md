---
name: codex-peer-review
description: Use after writing a spec (docs/superpowers/specs/) or plan (docs/superpowers/plans/) to peer-review it with Codex CLI via single-thread iterative dialogue. Loops until codex returns APPROVED. Pushbacks require codex's explicit concession; no round cap; no rubber-stamping; no walk-away with unresolved disagreements.
---

# Codex Peer Review

Peer-review a freshly written spec or plan with Codex (different model = different blind spots). **Single iterative dialogue with ONE codex session that remembers every round.** Terminate only when codex returns `## Verdict\nAPPROVED`. Pushbacks must reach explicit consensus (codex says CONCEDE).

The Stop hook `codex-review-gate.py` will tell you when this is needed by blocking turn-end and naming the unreviewed file.

**Announce at start:** "I'm using codex-peer-review to peer-review <path> with Codex."

## When This Skill Runs

- The Stop hook blocked turn-end with a reason naming a spec/plan path without the `<!-- codex-peer-reviewed: ... -->` marker
- Or you (Claude) just wrote a spec/plan and want to proactively review
- Or the user explicitly invoked this skill on an existing file

## Termination

**Single condition: codex returns `## Verdict\nAPPROVED`.**

No round cap. No escalation to user. No walk-away with disagreements. If codex maintains a pushback you disagree with, keep arguing — rephrase, give stronger evidence, dig into why your reasoning is sound. If codex raises new issues each round, fix or push back on those too. Loop until consensus.

## Per-review isolation & never trusting stale output

Two failure modes this section prevents. Both end the same catastrophic way — you read an `APPROVED` that isn't this round's, and stamp the marker on a document codex never actually passed:

1. **Stale read (the higher-probability one).** If a `codex exec` round errors (e.g. the model returns a 400) it may not write its `-o` file at all. A naive "run, then Read the `-o` file" then silently reads the PREVIOUS round's file — or a leftover from an earlier review — and treats it as this round's verdict.
   **Guard: capture codex's exit code after every call and check it. On non-zero: stop, report the error, do NOT read the `-o` file, do NOT write the marker.**
2. **Cross-review collision (lower-probability).** Hardcoded `/tmp/codex-rN.txt` is a global path two concurrent reviews share. And `resume --last` resumes the newest session *in the current cwd* — not globally (the `--all` flag exists precisely to "disable cwd filtering"), so separate worktrees do NOT cross-contaminate. The residual window is two reviews in the SAME cwd, or a Codex.app / other codex session spawned in that dir between round 1 and round N, making `--last` grab the wrong session.
   **Guard: each review gets its own fresh temp dir (`mktemp -d`, so it can never reuse a prior review's files), and resumes by the session id captured in round 1 — never `--last`.**

Set up once at the start of round 1, then look it back up in later rounds:

```bash
REVIEW_PATH="<ABSOLUTE PATH of the file under review>"
KEY=$(printf '%s' "$REVIEW_PATH" | { command -v shasum >/dev/null 2>&1 && shasum -a 256 || sha256sum; } | cut -c1-16)

# round 1 — fresh unique dir, record a pointer to it keyed by the reviewed file
DIR=$(mktemp -d "/tmp/codex-review.XXXXXXXX")
printf '%s' "$DIR" > "/tmp/codex-review.$KEY.dir"

# rounds 2+ — read back THIS review's dir
DIR=$(cat "/tmp/codex-review.$KEY.dir")
```

**zsh note:** use `rc` (or any name) for `$?` — NOT `status`, which is a read-only special variable in zsh and will error on assignment.

## The Protocol

### Step 1: Decide whether to brief codex

The spec/plan document should be self-contained — both `brainstorming` and `writing-plans` skills enforce this. **In ~99% of cases, no briefing is needed.** Just hand codex the absolute path; codex reads the file directly.

**Compose a short context note ONLY if there's material context the document doesn't capture, such as:**

- The document iterates on a prior spec/plan that codex won't see on its own
- A constraint the user surfaced verbally that didn't land in the document
- An approach that was discussed and explicitly rejected but isn't documented

If none of these apply: skip briefing entirely; go to Step 2 with just the path.

If you decide briefing IS needed: in Step 2's prompt template, insert a `# Material context` block (a short paragraph, under ~150 words) immediately above the `# Document to review` block. Keep it factual — do NOT lead codex toward issues you think matter; that defeats the fresh-eyes value of peer review.

### Step 2: Round 1 — start the codex session (fresh)

Set up the per-review dir, then start codex with `--json` so we can capture THIS review's session id (we resume by id in later rounds, never `--last`):

```bash
REVIEW_PATH="<INSERT ABSOLUTE PATH>"
KEY=$(printf '%s' "$REVIEW_PATH" | { command -v shasum >/dev/null 2>&1 && shasum -a 256 || sha256sum; } | cut -c1-16)
DIR=$(mktemp -d "/tmp/codex-review.XXXXXXXX")
printf '%s' "$DIR" > "/tmp/codex-review.$KEY.dir"

codex exec --json --sandbox read-only -o "$DIR/r1.txt" - <<'CODEX_EOF' > "$DIR/r1.events.jsonl"
You are peer-reviewing a spec or plan document. Claude (the user's main agent) wrote it and self-reviewed it. This is a single iterative dialogue — I (Claude) will fix or push back on each issue you raise; you re-evaluate in later rounds, and we continue until consensus. Don't rubber-stamp, and don't manufacture issues to drag it out.

# Why this review exists
This document drives real implementation: a plan is executed step-by-step by a zero-context engineer who will not notice its mistakes; a spec is the foundation every downstream plan and line of code inherits. Whatever it gets wrong propagates uncaught. The author wrote and self-reviewed it, so every flaw rooted in the author's own assumptions is still in it, invisible to the author by construction. Your job is exactly the review the author cannot do on themselves: independently decide whether this document, built on as written, yields correct, complete, and maintainable software.

# How to review
Treat the document as a hypothesis to falsify — not a description to follow. It is written to look complete and correct; read it forwards and its own narrative carries you to "looks fine." So don't review the document — review reality, with the document as the claim under test. Work only from primary sources:

- The real codebase. You have the repository — read it. Verify every claim the document makes about existing code, types, and behavior — especially completeness claims (that a set is exhaustive, that nothing else is affected). Never accept the document's description of the code as given.
- The document's own stated scope. Every goal it commits to must be fully accounted for by the document itself — in a plan, by a concrete step plus a check that proves the new behavior works (not merely that nothing broke); in a spec, by a mechanism that coherently achieves it. A committed goal that nothing delivers is a gap.

Also judge the design the document prescribes: the executor has no taste and builds exactly what is written, so unsound or debt-laden design is itself a finding. If you genuinely cannot break the document from primary sources, it passes.

# Document to review
<INSERT ABSOLUTE PATH>

Report every issue that would ship a bug, a regression, or real long-term debt if the document were taken as written — whatever its category. Skip pure style, naming, and wording preferences, and don't demand premature abstraction or gold-plating. The bar is impact, not how interesting the issue is.

Output in this exact format:

## Verdict
APPROVED  (or)  ISSUES FOUND

## Major issues (omit if APPROVED)
- [issue]: [why it matters]
- ...

## Recommendations (advisory, do not block)
- [optional suggestion]
- ...
CODEX_EOF
rc=$?
if [ "$rc" -ne 0 ]; then
  echo "codex exec FAILED (exit $rc). Do NOT read r1.txt; do NOT write the marker. Last events:"
  tail -n 20 "$DIR/r1.events.jsonl"
  exit "$rc"
fi

# Capture THIS review's codex session id (resume by id later, never --last)
grep -m1 '"thread.started"' "$DIR/r1.events.jsonl" | sed -E 's/.*"thread_id":"([^"]+)".*/\1/' > "$DIR/thread_id"
echo "review dir: $DIR   codex session: $(cat "$DIR/thread_id")"
```

Read `$DIR/r1.txt` (only because `rc` was 0 — a failed round must never reach a Read).

- **If verdict is `APPROVED`** → **Step 4: Finalize** with `rounds=1`.
- **If verdict is `ISSUES FOUND`** → Step 3.

> If `$DIR/thread_id` came out empty (codex didn't emit a `thread.started` event), fall back to `resume --last` for round 2+ AND run the rest of the review without launching any other codex session in between, so `--last` still points at this one. Note this limitation in your final report.

### Step 3: Iterate — judge, fix-or-pushback, then resume the same codex session

For each issue codex raised, decide:

- **Fix**: issue is valid → use Edit tool to update the spec/plan
- **Push back**: you disagree → record your reasoning; do NOT change the file

Don't rubber-stamp. If codex flagged something you genuinely think is wrong, push back with specific reasoning. Don't capitulate for the sake of finalizing — capitulation only happens when codex's MAINTAIN reasoning genuinely convinces you.

Then resume the SAME codex session for round N **by its captured id** (so codex remembers everything it said in earlier rounds — never start a fresh session for rounds 2+, and never use `--last`, which could grab a different review's session):

```bash
REVIEW_PATH="<INSERT ABSOLUTE PATH>"
KEY=$(printf '%s' "$REVIEW_PATH" | { command -v shasum >/dev/null 2>&1 && shasum -a 256 || sha256sum; } | cut -c1-16)
DIR=$(cat "/tmp/codex-review.$KEY.dir")
THREAD_ID=$(cat "$DIR/thread_id")

codex exec --sandbox read-only -o "$DIR/r<N>.txt" resume "$THREAD_ID" - <<'CODEX_EOF'
Round <N>. I responded to your previous round as follows:

FIXED (these are now updated in the document — please re-read):
- [issue X]: [brief description of what I changed]
- ...

PUSHED BACK (need your explicit CONCEDE or MAINTAIN on each):
- [issue Y]: [my reasoning, addressing your specific concern]
- ...

Please:
1. Re-read the document — FIXED items have been edited
2. For each PUSHED BACK item: say either CONCEDE (you accept my reasoning) or MAINTAIN (your concern stands — explain specifically what my reasoning misses)
3. Verify the FIXED items actually address what you originally raised
4. Raise any genuinely new major issues you spot (don't manufacture — only real ones)

Output in this exact format:

## Verdict
APPROVED  (or)  REMAINING ISSUES

## On Claude's pushbacks
- [issue Y]: CONCEDE  (or)  MAINTAIN — [if maintain, what my reasoning missed]
- ...

## Remaining or new issues (omit if APPROVED)
- [issue]: [why concerned]
- ...
CODEX_EOF
rc=$?
if [ "$rc" -ne 0 ]; then
  echo "codex exec FAILED (exit $rc). Do NOT read r<N>.txt; do NOT write the marker."
  exit "$rc"
fi
```

Read `$DIR/r<N>.txt`.

- **If verdict is `APPROVED`** → **Step 4: Finalize** with `rounds=<N>`.
- **If verdict is `REMAINING ISSUES`** → repeat Step 3 with N+1.

**On MAINTAIN responses:** that pushback is unresolved. In the next iteration, you MUST either:
- (a) Strengthen your reasoning — be more specific, cite the contradiction codex missed, or
- (b) Capitulate and fix it — because codex's MAINTAIN reasoning genuinely convinced you

Do NOT pretend MAINTAIN issues are resolved. Do NOT shortcut to APPROVED by withdrawing pushbacks just to end the loop.

### Step 4: Finalize

1. Append the marker to the document footer:

```bash
cat >> <ABSOLUTE_PATH> <<MARKER

<!-- codex-peer-reviewed: $(date -u +%Y-%m-%dT%H:%M:%SZ) rounds=<N> verdict=approved -->
MARKER
```

`<N>` is the round count where APPROVED was reached. The only verdict value is `approved` — under this protocol there's no walk-away state.

2. Report back to user:
   - Rounds completed
   - Codex's main original concerns (1-3 bullets)
   - What was changed (with reasoning)
   - What you pushed back on AND codex eventually conceded (with reasoning) — shows where your judgment held
   - What you capitulated on because codex's reasoning was sound (transparency about where you changed mind)

Keep the report tight. User reads the diff for full detail.

## Failure Modes

| Symptom | Action |
|---|---|
| `codex exec` returns non-zero (the `rc` guard fires) | Report the error to the user. Do NOT read the `-o` file; do NOT write the marker. (The Stop hook re-blocks only on its first trigger — once `stop_hook_active` is set it fails open — so don't assume a failed review is hard-gated; surface it.) |
| Codex output unparseable (no `## Verdict`) | Treat as `ISSUES FOUND`, dump raw text as the issue list, continue. |
| `$DIR/thread_id` is empty after round 1 | Codex emitted no `thread.started` event. Fall back to `resume --last` for rounds 2+, and don't start any other codex session mid-review so `--last` still targets this one. Flag it in the final report. |
| You find yourself wanting to brief codex on lots of context outside the document | That's a signal the document itself is incomplete. Fix the document, not the briefing — the spec/plan should stand on its own. |
| Codex keeps MAINTAINing despite strong reasoning | Keep iterating — find a sharper angle, cite a specific contradiction, give a concrete example. Don't shortcut by capitulating. Don't shortcut by inventing a fake CONCEDE on codex's behalf. |
| Codex raises trivially new issues each round (sounds like dragging) | Push back: tell codex its calibration is off and these aren't MAJOR. Force it to reach APPROVED or to explain why a "minor" issue is actually load-bearing. |
| Document was massively rewritten between rounds | Mention this in the round prompt so codex re-reads carefully instead of diffing against memory. |

## Don't

- **Don't use `codex exec` (fresh session) for rounds 2+** — you MUST use `codex exec ... resume "$THREAD_ID" ...` so codex maintains memory of every previous round. Fresh sessions break the single-thread principle and force codex to start cold each round (losing memory of prior fix/pushback exchanges).
- **Don't resume with `--last`** — it resumes whatever codex session is globally newest, which under parallel worktrees (or any other codex usage on the machine) can be a DIFFERENT review's session. Always resume by the `thread_id` you captured in round 1.
- **Don't share temp files across reviews** — each review writes only under its own `$DIR` (derived from the reviewed file's absolute path). Never hardcode `/tmp/codex-r1.txt`.
- **Don't rubber-stamp.** If codex raises a non-issue, push back. If you disagree, push back hard.
- **Don't capitulate just to finalize.** Only fix-after-pushback because codex's MAINTAIN reasoning convinced you, not because the loop is dragging.
- **Don't pretend MAINTAIN is APPROVED.** Walk-away with codex maintaining = breach of the protocol. Either argue better or capitulate honestly.
- **Don't fix things codex didn't raise.** This skill reviews what's there; don't sneak in scope creep.
- **Don't skip the marker write** — the Stop hook depends on it; without it you'll get re-triggered forever.
- **Don't pass `-m` to `codex exec`** — `~/.codex/config.toml` already sets `model = "gpt-5.5"`, `service_tier = "fast"`, `model_reasoning_effort = "xhigh"`. Let those defaults apply.
