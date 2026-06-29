<role>
You are setting up a "cross-model review" harness inside my Claude Code. Once installed, every time I finish writing an implementation plan or spec, you (Claude) must peer-review it with Codex before the turn can end, looping until both models reach consensus. The harness has two parts: a Stop hook that acts as a gate, and a codex-peer-review skill that runs the actual review. Install both, wired to my setup.
</role>

<context-gathering>
Work through this in order. Do not write any files until everything below is answered and confirmed.

1. Pre-check the prerequisite first, because the whole harness depends on a working codex CLI. Run "codex --version" (it must be recent enough to support codex exec, --json, and resume by session id). Then run a tiny smoke test to prove codex actually responds and is logged in: printf 'Reply with exactly: OK' | codex exec --sandbox read-only - and confirm it returns without error. If codex is not installed, not logged in (fix with codex login), or too old, STOP here and walk me through fixing it. Do not continue the install on a broken reviewer.

2. Once codex is confirmed, ask me these three setup questions and wait for my answers:
 a. Do you use the superpowers skill framework? If yes, the hook will watch docs/superpowers/specs/ and docs/superpowers/plans/ by default.
 b. Install globally (~/.claude, every project) or for this project only (.claude in the current repo)?
 c. Which folder(s) hold the plans/specs you want reviewed? Default for superpowers users: docs/superpowers/specs/ and docs/superpowers/plans/.

3. Echo back the install location and the watched path(s) you understood, and wait for my confirmation before writing anything.
</context-gathering>

<execution>
Pick the base dir from my answers: ~/.claude for global, or .claude in the current repo for project-only. Then:

1. Set up the reviewer's codex config. The skill calls codex with no -m flag and reads the model and reasoning from ~/.codex/config.toml, so these values are what make the review identical:
 model = "gpt-5.5"
 service_tier = "fast"
 model_reasoning_effort = "xhigh"
 model_context_window = 1000000
 Before you change anything, tell me this plainly: these are GLOBAL codex settings, so setting model = "gpt-5.5" changes the model for ALL my codex usage, not only these reviews. If ~/.codex/config.toml already sets a different model, show me the current value and ask whether to overwrite it before you do. If I do not have access to gpt-5.5, set model to the strongest reasoning model I can use instead, and note that review quality depends on it. MERGE these keys in, preserving every other setting and every [section] already there.

2. Download the Stop hook into <base>/hooks/codex-review-gate.py:
 curl -fsSL https://garytalksstuff.com/kits/codex-review-gate.py -o <base>/hooks/codex-review-gate.py
 If the download fails, tell me and I will paste the source from the kit page so you can write it instead.

3. In codex-review-gate.py, set WATCHED_DIR_SUBSTRS to the folder(s) I gave you, keeping trailing slashes, for example ("docs/superpowers/specs/", "docs/superpowers/plans/").

4. Register the hook in <base>/settings.json:
 - Back up the file first. If it is not valid JSON, stop and tell me.
 - Add to hooks.Stop, MERGING with any existing Stop hooks, never overwriting them:
   { "matcher": "", "hooks": [ { "type": "command", "command": "python3 <base>/hooks/codex-review-gate.py" } ] }

5. Download and unpack the skill:
 curl -fsSL https://garytalksstuff.com/kits/codex-peer-review.zip -o /tmp/codex-peer-review.zip
 Unzip it into <base>/skills so the result is <base>/skills/codex-peer-review/SKILL.md.

6. Align paths: make the watched-path references inside the skill's SKILL.md match the folder(s) you set in step 3, so the hook and skill agree.

7. Verify: create a throwaway one-line plan with no review marker under one watched folder, then try to end the turn. Confirm the hook blocks and asks for review. Then delete the throwaway file. (Or paste the separate verification prompt from the kit page, which dry-runs the gate without calling Codex.)

8. Report every file you created or edited, the watched paths you set, and exactly how I can test it myself.
</execution>

<guardrails>
- Back up settings.json before touching it. Never clobber an existing hook; merge into the Stop array.
- If the codex CLI is missing, not logged in, or fails the smoke test, stop and give me fix steps. Do not proceed with a broken reviewer.
- When editing ~/.codex/config.toml, merge the reviewer keys in. Never delete or overwrite my other codex settings, marketplaces, or MCP servers.
- Keep the hook's WATCHED_DIR_SUBSTRS and the skill's path references identical. If they drift, the marker handshake breaks and reviews stop triggering.
- Do not invent paths or settings I did not confirm. If anything is ambiguous, ask before writing.
- If any download fails, stop and ask me to paste the source from the kit page rather than guessing the file contents.
</guardrails>