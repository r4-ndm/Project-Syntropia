# 🧱 Code Quality & Technology Choice

**Rule:** Code is written for the **next agent or developer**, not for the moment
it lands. Syntropia outlives any single session — every file must be easy to
pick up, reason about, and maintain months from now.

## Golden rules

1. **Well-modulated or nothing.** Code must be organised into small, focused
   units — modules, functions, components — each with a single responsibility
   and a clear name. No god-files, no copy-paste sprawl, no 600-line scripts
   where 6 functions would do. If a file grows past what a reader can hold in
   one screen, it needs splitting.
2. **Maintainability over cleverness.** Favour the boring, obvious implementation
   that a future agent can read in one pass. Comments explain **why**, not what
   (the code says what). Leave no dead code, no commented-out blocks, no
   half-finished refactors.
3. **Battle-tested open source first.** Prefer established, widely-used
   libraries and tools over hand-rolled solutions. If a problem has a mature
   OSS answer, use it — don't reinvent it. New dependencies are evaluated
   through `software-inclusion-policy.md` (Tier 2 tooling, declared where used).
4. **Rust where practically possible.** New code should be written in Rust
   unless a pragmatic reason says otherwise (the language of the surrounding
   project, a library that only exists elsewhere, prototype speed, or the
   toolchain not being available in the build environment). State the reason
   when deviating — don't silently pick something else.
5. **Test what you build.** Behaviour worth shipping is behaviour worth pinning.
   Follow the project's existing test conventions; a change isn't done until
   the relevant tests pass.

## What this means in practice

- **Refactoring is part of the work.** If you touch a file and it's already
  bloated or tangled, leave it *more* modular than you found it — or flag it
  for a follow-up. Don't paper over it.
- **Naming is documentation.** Module, function, and variable names should read
  like a description of intent. If a name needs a comment to make sense, the
  name is wrong.
- **The Rust rule is a preference, not a religion.** `iso/build.sh` is bash
  because it orchestrates a bash ecosystem; the TUI is Go because that's its
  stack; the wizard driver is bash for the same reason. Those are documented
  deviations. The default for *new* standalone code is Rust.
- **When in doubt, ask.** If a choice between languages or libraries could go
  either way, present the options and the trade-off rather than guessing.

*The best code is the code the next agent doesn't have to debug.* 😈
