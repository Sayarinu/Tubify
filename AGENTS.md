# Repository workflow

- Read docs/native-client-spec.md for native-client scope, interfaces, acceptance gates and Linear ticket links.
- Every implementation task needs its actual assigned LUNE issue before code work starts.
- Fetch origin/main and create each ticket branch directly from origin/main. Branch names are exactly the issue identifier (for example LUNE-335). Do not work on or branch from agent/*, add descriptive suffixes or stack unmerged ticket branches.
- Commit subjects are LUNE-XXX - Change-specific message, substituting the current issue identifier. The message describes the individual change; it need not repeat the issue title.
- PRs target main only. Do not push implementation commits directly to main. Merge only when the issue's work is complete, review concerns are resolved and required PR checks pass for the current head.
- Preserve the existing Tauri wrapper while building the separate native client.
- Keep shared Python/PySide6 and QML code portable across Linux, Windows and macOS. Use standard platform paths; isolate OS integrations and test portability early.
- Complete the real-account compatibility gate before substantial native UI work. Do not present fixture success as real-account verification.
- Keep browser sessions, cookies, signed media URLs, private screenshots and account data out of commits, logs and Linear tickets.
