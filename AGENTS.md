# Repository workflow

- Read [the native-client specification and QoL roadmap in Linear](https://linear.app/nouvelle-lune-atelier/issue/LUNE-367/publish-native-qol-roadmap-and-revised-player-specification) for native-client scope, interfaces, acceptance gates and ticket links.
- Every implementation task needs its actual assigned LUNE issue before code work starts.
- Two release channels: `experimental` publishes an experimental prerelease on every merge, and `main` publishes the full stable release. Feature work lands on `experimental` first; `main` only receives `experimental` (or an urgent fix) when it is ready to ship.
- Fetch origin and create each ticket branch from origin/experimental, or from the ticket branch below it when stacking. Branch names are exactly the issue identifier (for example LUNE-335). Do not work on or branch from agent/* or add descriptive suffixes.
- Open PRs with `scripts/open-prs.py`, which also waits for the PR checks. One ticket gets one PR. When a request breaks into several small changes, give each its own ticket and open them as an official GitHub stack: `scripts/open-prs.py LUNE-1 LUNE-2 LUNE-3`, bottom first. `--into stable` targets main. Write the PR description as the body of the branch's first commit.
- Commit subjects are LUNE-XXX - Change-specific message, substituting the current issue identifier. The message describes the individual change; it need not repeat the issue title.
- Ticket PRs target experimental and are squash-merged; merge a stack with `gh stack merge --squash`. A full release is a PR from experimental into main merged with a merge commit (never squash or rebase), so both branches keep the same history. Do not push commits directly to experimental or main. Merge only when the issue's work is complete, review concerns are resolved and required PR checks pass for the current head. Agents stop at green PRs and only merge when the owner says to, because merging publishes a signed release automatically.
- The repository is native-only; do not reintroduce the retired Tauri wrapper or its session migration.
- Keep shared Python/PySide6 and QML code portable across Linux, Windows and macOS. Use standard platform paths; isolate OS integrations and test portability early.
- Complete the real-account compatibility gate before substantial native UI work. Do not present fixture success as real-account verification.
- Keep browser sessions, cookies, signed media URLs, private screenshots and account data out of commits, logs and Linear tickets.
