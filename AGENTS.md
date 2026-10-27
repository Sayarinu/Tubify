# Repository workflow

- Read [the native-client specification and QoL roadmap in Linear](https://linear.app/nouvelle-lune-atelier/issue/LUNE-367/publish-native-qol-roadmap-and-revised-player-specification) for native-client scope, interfaces, acceptance gates and ticket links.
- Every implementation task needs its actual assigned LUNE issue before code work starts.
- Fetch origin/main and create each ticket branch directly from origin/main. Branch names are exactly the issue identifier (for example LUNE-335). Do not work on or branch from agent/*, add descriptive suffixes or stack unmerged ticket branches.
- Commit subjects are LUNE-XXX - Change-specific message, substituting the current issue identifier. The message describes the individual change; it need not repeat the issue title.
- PRs target main only. Do not push implementation commits directly to main. Merge only when the issue's work is complete, review concerns are resolved and required PR checks pass for the current head.
- The repository is native-only; do not reintroduce the retired Tauri wrapper or its session migration.
- Keep shared Python/PySide6 and QML code portable across Linux, Windows and macOS. Use standard platform paths; isolate OS integrations and test portability early.
- Complete the real-account compatibility gate before substantial native UI work. Do not present fixture success as real-account verification.
- Keep browser sessions, cookies, signed media URLs, private screenshots and account data out of commits, logs and Linear tickets.
