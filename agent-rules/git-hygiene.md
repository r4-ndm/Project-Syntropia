# 🧼 Git Hygiene

**Rule:** Git is a tool for the Final Boss, not for agents to improvise with.
When in doubt about a git operation, **don't** — ask first.

## Golden rules

1. **Never commit unless asked.** The Final Boss (or the task) must explicitly request a commit. "Tidy up" is not permission.
2. **Never push without asking.** Especially never push to `main` unprompted.
3. **Never force-push. Ever.** `--force` rewrites history and can destroy work irreversibly. If a push fails because of divergence, STOP and ask.
4. **Never discard what you didn't create.** No `git reset --hard`, no `git stash` of others' changes, no `git clean`. Prefer `git revert` for undoing.
5. **Never stage blindly.** No `git add -A` / `git add .` in a shared checkout. Stage only the files *you* changed and that belong to the task.
6. **Shared checkout awareness.** Other agents, the user, or an IDE may be editing the same files — check `git status` and the current branch before any consequential git operation. If ownership of a change is ambiguous, leave it uncommitted and say so.
7. **Secrets never enter git.** `.freebuff/` (app database), tokens, keys, and passwords must not be committed. `agent-rules/` and the repo are public-facing: re-read before committing.

## What committing *does* look like

When the Final Boss asks for a commit:

1. `git diff` (review exactly what changed) and `git log` (match the repo's message style).
2. Stage **only** the relevant files — never unrelated untracked files.
3. Write a concise message that explains **why**, not just what. No generic "Update" or "Fix".
4. Commit. Do not push unless asked.

## Recovery when something breaks

- Broken commit → `git revert <sha>` (safe, creates a new commit).
- Untracked junk in the tree → leave it; mention it.
- Diverged from remote → ask before anything.

*History is the swarm's memory. Don't erase it.* 😈
