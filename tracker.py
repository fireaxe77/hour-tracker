"""Lightweight game-time tracker for Windows. See README.md."""
import json
import logging
import os
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

APP = Path(__file__).resolve().parent
SESSIONS_TXT = "auto_game_sessions.txt"
TOTALS_TXT = "auto_game_totals.txt"
STEAM = "\\steamapps\\common\\"


def load_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def save_json(path, data):
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def fmt_dur(sec):
    h, m = divmod(int(sec) // 60, 60)
    return f"{h}h {m}m" if h else f"{m}m"


def desktop_dir():
    try:
        from win32com.shell import shell, shellcon
        return Path(shell.SHGetKnownFolderPath(shellcon.FOLDERID_Desktop, 0, 0))
    except Exception:
        return Path.home() / "Desktop"


class Tracker:
    def __init__(self, app_dir, out_dir):
        self.app, self.out = Path(app_dir), Path(out_dir)
        self.cfg = load_json(self.app / "config.json", {})
        self.maps = load_json(self.app / "mappings.json", {})
        self._index()
        self.poll = self.cfg.get("poll_seconds", 15)
        self.merge_gap = self.cfg.get("merge_minutes", 5) * 60
        self.min_len = self.cfg.get("min_session_minutes", 2) * 60
        self.unknown_secs = self.cfg.get("unknown_minutes", 5) * 60
        self.sessions = {}   # display name -> {start, last, active, running}
        self.seen = {}       # unknown exe (lower) -> {first, fs, last}
        self.asked = set()
        self.last_app = None  # (exe name, path) of last unmapped foreground app
        self.paused = False
        self.last_hb = 0
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.recover()

    def _index(self):
        self.mlow = {k.lower(): v for k, v in self.maps.items()}
        self.block = {x.lower() for x in self.cfg.get("blocklist", [])}

    # ---- crash safety -------------------------------------------------
    def save_state(self):
        save_json(self.app / "state.json", {"saved": time.time(), "sessions": self.sessions})

    def recover(self):
        """Close sessions left unfinished by a crash at their last heartbeat."""
        st = load_json(self.app / "state.json", {})
        for name, s in st.get("sessions", {}).items():
            self.finish(name, s)
        self.save_state()

    # ---- sessions -----------------------------------------------------
    def tick(self, now, running):
        """running: set of display names of mapped processes alive right now."""
        finished = False
        for name in running:
            s = self.sessions.get(name)
            if s is None:
                self.sessions[name] = dict(start=now, last=now, active=0.0, running=True)
                continue
            if s["running"]:  # cap dt so sleep/hibernate isn't counted as play
                s["active"] += min(now - s["last"], 3 * self.poll)
            s["running"], s["last"] = True, now
        for name, s in list(self.sessions.items()):
            if name in running:
                continue
            s["running"] = False
            if now - s["last"] >= self.merge_gap:
                del self.sessions[name]
                self.finish(name, s)
                finished = True
        if finished:
            self.save_state()

    def finish(self, name, s):
        if s["active"] < self.min_len:
            return
        start, end = datetime.fromtimestamp(s["start"]), datetime.fromtimestamp(s["last"])
        day = f"{start:%Y-%m-%d}"
        self.out.mkdir(parents=True, exist_ok=True)
        with open(self.out / SESSIONS_TXT, "a", encoding="utf-8") as f:
            f.write(f"{day} | {start:%H:%M}-{end:%H:%M} | {name} | {fmt_dur(s['active'])}\n")
        totals = load_json(self.app / "totals.json", {})
        e = totals.setdefault(name, dict(secs=0, n=0, first=day, last=day))
        e["secs"] += s["active"]
        e["n"] += 1
        e["first"], e["last"] = min(e["first"], day), max(e["last"], day)
        save_json(self.app / "totals.json", totals)
        rows = sorted(totals.items(), key=lambda kv: -kv[1]["secs"])
        lines = [f"Grand total: {fmt_dur(sum(e['secs'] for _, e in rows))} | "
                 f"updated: {datetime.now():%Y-%m-%d %H:%M}"]
        lines += [f"{n} - {fmt_dur(e['secs'])} | sessions: {e['n']} | "
                  f"first: {e['first']} | last: {e['last']}" for n, e in rows]
        (self.out / TOTALS_TXT).write_text("\n".join(lines) + "\n", encoding="utf-8")

    # ---- unknown games ------------------------------------------------
    def watch(self, now, fg):
        """fg: (exe name, path, covers_monitor) or None. Returns a popup request or None."""
        if not fg:
            return None
        name, path, full = fg
        key = name.lower()
        if key in self.mlow or key in self.block or STEAM in path.lower():
            return None
        self.last_app = (name, path)
        if not full or key in self.asked:
            return None
        e = self.seen.setdefault(key, dict(first=now, fs=0.0, last=now))
        e["fs"] += min(now - e["last"], 3 * self.poll)
        e["last"] = now
        if e["fs"] >= self.unknown_secs:
            self.asked.add(key)
            return name, path, e["first"]
        return None

    def decide(self, exe, track, display, first):
        with self.lock:
            self.asked.add(exe.lower())
            if track:
                display = display or Path(exe).stem
                self.maps[exe] = display
                save_json(self.app / "mappings.json", self.maps)
                now = time.time()
                if display not in self.sessions:  # backfill time since first seen
                    self.sessions[display] = dict(start=first, last=now,
                                                  active=now - first, running=True)
            else:
                self.cfg.setdefault("blocklist", []).append(exe)
                save_json(self.app / "config.json", self.cfg)
            self._index()
            self.save_state()

    def ask(self, exe, path, first):
        import tkinter as tk
        root = tk.Tk()
        root.title("Game tracker")
        root.attributes("-topmost", True)
        tk.Label(root, text=f"New game detected: {exe}").pack(padx=12, pady=(12, 4))
        var = tk.StringVar(value=Path(path).parent.name)
        tk.Entry(root, textvariable=var, width=36).pack(padx=12)
        res = {}

        def done(track):
            res["track"], res["name"] = track, var.get().strip()
            root.destroy()

        row = tk.Frame(root)
        row.pack(pady=10)
        tk.Button(row, text="Track", width=10, command=lambda: done(True)).pack(side="left", padx=4)
        tk.Button(row, text="Ignore", width=10, command=lambda: done(False)).pack(side="left", padx=4)
        root.protocol("WM_DELETE_WINDOW", lambda: done(False))
        root.mainloop()
        self.decide(exe, res.get("track", False), res.get("name"), first)

    def track_current(self):
        app = self.last_app
        if app:
            threading.Thread(target=self.ask, args=(app[0], app[1], time.time()), daemon=True).start()

    # ---- polling (Windows) --------------------------------------------
    def running_names(self):
        import psutil
        found = set()
        for p in psutil.process_iter(["name"]):
            display = self.mlow.get((p.info["name"] or "").lower())
            if display and display not in found:
                try:
                    path = p.exe().lower()
                except (psutil.Error, OSError):
                    path = ""
                if STEAM not in path:
                    found.add(display)
        return found

    def step(self):
        now = time.time()
        with self.lock:
            if self.paused:
                return
            self.tick(now, self.running_names())
            hit = self.watch(now, foreground())
            if now - self.last_hb >= 60:
                self.save_state()
                self.last_hb = now
        if hit:
            threading.Thread(target=self.ask, args=hit, daemon=True).start()


def foreground():
    import psutil
    import win32api
    import win32con
    import win32gui
    import win32process
    hwnd = win32gui.GetForegroundWindow()
    if not hwnd or win32gui.GetClassName(hwnd) in ("Progman", "WorkerW"):
        return None
    pid = win32process.GetWindowThreadProcessId(hwnd)[1]
    try:
        p = psutil.Process(pid)
        name, path = p.name(), p.exe()
    except psutil.Error:
        return None
    mon = win32api.GetMonitorInfo(
        win32api.MonitorFromWindow(hwnd, win32con.MONITOR_DEFAULTTONEAREST))["Monitor"]
    l, t, r, b = win32gui.GetWindowRect(hwnd)
    return name, path, l <= mon[0] and t <= mon[1] and r >= mon[2] and b >= mon[3]


def start_tray(tr):
    import pystray
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (64, 64), "#1e1e2e")
    ImageDraw.Draw(img).polygon([(22, 16), (22, 48), (50, 32)], fill="#a6e3a1")

    def toggle(icon, item):
        tr.paused = not tr.paused

    def quit_(icon, item):
        tr.stop.set()
        icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem("Track current foreground app", lambda i, m: tr.track_current()),
        pystray.MenuItem(lambda item: "Resume" if tr.paused else "Pause", toggle),
        pystray.MenuItem("Open logs folder", lambda i, m: os.startfile(tr.out)),
        pystray.MenuItem("Quit", quit_),
    )
    icon = pystray.Icon("GameTracker", img, "Game tracker", menu)
    icon.run_detached()
    return icon


def main():
    import win32api
    import win32event
    import winerror
    logging.basicConfig(filename=APP / "tracker.log", level=logging.ERROR)
    mutex = win32event.CreateMutex(None, False, "Local\\GameTimeTracker")  # keep reference
    if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
        sys.exit(0)
    tr = Tracker(APP, desktop_dir())
    icon = start_tray(tr)
    while not tr.stop.is_set():
        try:
            tr.step()
        except Exception:
            logging.exception("step failed")
        tr.stop.wait(tr.poll)
    with tr.lock:
        tr.save_state()
    icon.stop()


if __name__ == "__main__":
    main()
