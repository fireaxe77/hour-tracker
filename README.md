# Game-time tracker

Background tracker for non-Steam games. Polls processes every 15 s (psutil), no hooks.

**Install:** needs Python 3 on PATH. Right-click `install.bat` → *Run as administrator*. It installs
`psutil pystray pillow pywin32` and registers a logon task (`GameTimeTracker`, pythonw, no console,
restarts on failure, keeps running on battery/idle). **Remove:** `uninstall.bat`.

**Output** (real Desktop, OneDrive-aware):
- `auto_game_sessions.txt` – one appended line per session
- `auto_game_totals.txt` – rewritten after each session, sorted by time

**Files in this folder**
- `mappings.json` – `exe → display name` (edit freely)
- `config.json` – `blocklist` of ignored exes, plus poll/merge/min-length settings
- `state.json` – 60 s heartbeat; an unfinished session is closed at its last heartbeat on next start
- `totals.json` – exact totals backing the totals txt; `tracker.log` – errors only

**Behavior**
- Exes under `\steamapps\common\` and anything in the blocklist are ignored.
- An unmapped app fullscreen/borderless in the foreground for 5 min total triggers a *Track / Ignore*
  popup (asked once per exe; Track backfills time since first seen; closing the popup = Ignore).
- Same game restarting within 5 min merges into one session; sessions under 2 min are dropped;
  midnight-crossing sessions are logged under the start date.
- Tray menu: track current app (last unmapped foreground app seen), pause/resume, open logs folder, quit.

`python test_core.py` checks the merge/recovery/totals logic (platform independent).
