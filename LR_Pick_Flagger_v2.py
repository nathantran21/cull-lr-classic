#!/usr/bin/env python3
"""
LR Pick Flagger v2
==================
Brand-new implementation matching the Claude Design prototype.
Run:  python3 "/Users/natha/Documents/LR Tools/LR_Pick_Flagger_v2.py"
"""

import tkinter as tk
import tkinter.font as tkfont
from tkinter import messagebox
import sqlite3, os, re, shutil, threading, json, time, math
from datetime import datetime
from pathlib import Path

# ─── CATALOG PATH ─────────────────────────────────────────────────────────────
CATALOG = (
    "/Users/natha/Pictures/Lightroom Catalog-v13-v13-3/"
    "Old Lightroom Catalogs/"
    "Lightroom Catalog-v13-v13-3_2025-10-29 0911/"
    "Lightroom Catalog-v13-v13-3.lrcat"
)

# ─── DESIGN TOKENS ────────────────────────────────────────────────────────────
BG      = "#1C1C1E"
SURF    = "#2A2A2C"
SURFD   = "#232325"
SURFH   = "#323234"
TBAR    = "#242425"
TBLINE  = "#111112"
BORDER  = "#2E2E30"
BORDERS = "#3A3A3C"
TEXT    = "#F5F5F7"
TEXTD   = "#8E8E93"
TEXTF   = "#636366"
ACCENT  = "#0A84FF"
ACCENTH = "#3395FF"
ACCDIM  = "#1A2A3F"
SUCCESS = "#30D158"
SUCCD   = "#0D3321"
SUCCB   = "#1B5C32"
WARN    = "#FFD60A"
WARND   = "#3A2E00"
ERR     = "#FF453A"
ERRD    = "#3A1212"
ERRB    = "#7A2020"
F       = "Helvetica Neue"
FM      = "Menlo"
G       = 28   # gutter
SEC     = 22   # section gap

# ─── HISTORY ──────────────────────────────────────────────────────────────────
HIST_FILE = Path.home() / ".lr_pick_flagger_v2.json"

def _load_hist():
    try:
        d = json.loads(HIST_FILE.read_text())
        return d[:50] if isinstance(d, list) else []
    except:
        return []

def _save_hist(e):
    try: HIST_FILE.write_text(json.dumps(e[:50], indent=2))
    except: pass

def _fmt_rel(ts):
    d = time.time() - ts
    if d < 60:      return "just now"
    if d < 3600:    return f"{int(d/60)}m ago"
    if d < 86400:   return f"{int(d/3600)}h ago"
    if d < 86400*6: return f"{int(d/86400)}d ago"
    return datetime.fromtimestamp(ts).strftime("%b %-d")

def _bname(ts=None):
    d = datetime.fromtimestamp(ts or time.time())
    return f"Lightroom Catalog-v13-v13-3_backup_{d.strftime('%Y%m%d_%H%M%S')}.lrcat"

# ─── DB / IO ──────────────────────────────────────────────────────────────────
def _strip(name):
    name = re.sub(r'\.[^.]+$', '', name)
    return re.sub(r'(_[A-Za-z]+){1,2}$', '', name)

def _parse(raw):
    out, seen = [], set()
    for tok in re.split(r'[\s,\n\r]+', raw.strip()):
        tok = tok.strip().strip('"\'')
        if not tok: continue
        b = _strip(tok)
        if b and b not in seen:
            seen.add(b); out.append(b)
    return out

def _short(path):
    return path.rstrip("/").split("/")[-1] or path

def _search_db(kw):
    if not os.path.exists(CATALOG):
        raise FileNotFoundError(f"Catalog not found:\n{CATALOG}")
    with sqlite3.connect(CATALOG, timeout=5, check_same_thread=False) as con:
        rows = con.execute(
            "SELECT id_local, absolutePath FROM AgLibraryFolder "
            "WHERE lower(absolutePath) LIKE ? ORDER BY absolutePath",
            (f"%{kw.lower()}%",)
        ).fetchall()
    return [(r[0], r[1]) for r in rows]

def _backup_db():
    stem = Path(CATALOG).stem
    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
    dst  = Path(CATALOG).parent / f"{stem}_backup_{ts}.lrcat"
    shutil.copy2(CATALOG, dst)
    return dst.name

def _flag_db(folder_id, filenames, progress_cb):
    matched, not_found = [], []
    with sqlite3.connect(CATALOG, timeout=10, check_same_thread=False) as con:
        ph = ",".join("?" * len(filenames))
        rows = con.execute(
            f"SELECT ai.id_local, arf.baseName "
            f"FROM AgLibraryFile arf "
            f"JOIN Adobe_images ai ON ai.rootFile = arf.id_local "
            f"WHERE arf.folder = ? AND arf.baseName IN ({ph})",
            [folder_id] + filenames
        ).fetchall()
        found = {r[1]: r[0] for r in rows}
        for i, fn in enumerate(filenames):
            if fn in found:
                con.execute("UPDATE Adobe_images SET pick = 1 WHERE id_local = ?",
                            (found[fn],))
                matched.append(fn)
            else:
                not_found.append(fn)
            progress_cb(i + 1, len(filenames))
        con.commit()
    return matched, not_found

# ─── CANVAS UTILITIES ─────────────────────────────────────────────────────────
def _rr(c, x0, y0, x1, y1, r, fill):
    c.create_arc(x0,     y0,     x0+2*r, y0+2*r, start=90,  extent=90, fill=fill, outline=fill)
    c.create_arc(x1-2*r, y0,     x1,     y0+2*r, start=0,   extent=90, fill=fill, outline=fill)
    c.create_arc(x0,     y1-2*r, x0+2*r, y1,     start=180, extent=90, fill=fill, outline=fill)
    c.create_arc(x1-2*r, y1-2*r, x1,     y1,     start=270, extent=90, fill=fill, outline=fill)
    c.create_rectangle(x0+r, y0,   x1-r, y1,   fill=fill, outline=fill)
    c.create_rectangle(x0,   y0+r, x1,   y1-r, fill=fill, outline=fill)

def _draw_flag(c, cx, cy, size, color):
    sc = size / 14.0
    ox = cx - 7*sc; oy = cy - 7*sc
    pw = max(1.5, sc * 1.5)
    px = ox + 3*sc
    c.create_rectangle(px-pw/2, oy+2*sc, px+pw/2, oy+12*sc, fill=color, outline="")
    c.create_polygon(
        ox+3*sc, oy+2*sc,  ox+10*sc, oy+2*sc,
        ox+9*sc, oy+4.5*sc, ox+10*sc, oy+7*sc,
        ox+3*sc, oy+7*sc,
        fill=color, outline=""
    )

def _draw_check(c, cx, cy, r, color, w=1.8):
    c.create_line(cx-r*0.5, cy+r*0.1, cx-r*0.05, cy+r*0.5,
                  fill=color, width=w, capstyle="round")
    c.create_line(cx-r*0.05, cy+r*0.5, cx+r*0.55, cy-r*0.4,
                  fill=color, width=w, capstyle="round")

def _draw_x(c, cx, cy, r, color, w=1.5):
    c.create_line(cx-r, cy-r, cx+r, cy+r, fill=color, width=w, capstyle="round")
    c.create_line(cx+r, cy-r, cx-r, cy+r, fill=color, width=w, capstyle="round")

# ─── STEP BADGE ───────────────────────────────────────────────────────────────
class StepBadge(tk.Canvas):
    SZ = 20
    def __init__(self, parent, number, bg=BG, **kw):
        super().__init__(parent, width=self.SZ, height=self.SZ,
                         bg=bg, highlightthickness=0, **kw)
        self._n = str(number)
        self._done = False
        self._bg = bg
        self._font = tkfont.Font(family=F, size=11, weight="bold")
        self._redraw()

    def set_done(self, v):
        if v != self._done:
            self._done = v; self._redraw()

    def _redraw(self):
        self.delete("all")
        s = self.SZ
        fill = ACCENT if self._done else SURFD
        _rr(self, 0, 0, s, s, s//2, fill)
        if self._done:
            _draw_check(self, s//2, s//2, s//2-3, "#fff", w=1.6)
        else:
            self.create_text(s//2, s//2, text=self._n, fill=TEXTD,
                             font=self._font, anchor="center")

# ─── COUNT CHIP ───────────────────────────────────────────────────────────────
class CountChip(tk.Canvas):
    PX, PY = 8, 3
    def __init__(self, parent, bg=BG, **kw):
        self._font = tkfont.Font(family=F, size=11, weight="bold")
        self._count = 0
        self._pbg = bg
        lbl = "empty"
        w = self._font.measure(lbl) + self.PX*2
        h = self._font.metrics("linespace") + self.PY*2
        super().__init__(parent, width=w, height=h, bg=bg,
                         highlightthickness=0, **kw)
        self._redraw()

    def set_count(self, n):
        self._count = n
        lbl = "empty" if n == 0 else f"{n} {'file' if n==1 else 'files'}"
        w = self._font.measure(lbl) + self.PX*2
        h = self._font.metrics("linespace") + self.PY*2
        self.config(width=w, height=h)
        self._redraw()

    def _redraw(self):
        self.delete("all")
        n = self._count
        lbl = "empty" if n == 0 else f"{n} {'file' if n==1 else 'files'}"
        bg = ACCDIM if n > 0 else SURFD
        fg = ACCENT if n > 0 else TEXTF
        w = int(self.cget("width")); h = int(self.cget("height"))
        _rr(self, 0, 0, w, h, h//2, bg)
        self.create_text(w//2, h//2, text=lbl, fill=fg,
                         font=self._font, anchor="center")

# ─── ROUNDED BUTTON ───────────────────────────────────────────────────────────
class RBtn(tk.Canvas):
    def __init__(self, parent, text, cmd, height=36, width=None,
                 fill=SURF, hover=SURFH, fg=TEXT, radius=8,
                 font_spec=(F, 12, "bold"), bg=BG, **kw):
        self._text  = text
        self._cmd   = cmd
        self._fill  = fill
        self._hover = hover
        self._fg    = fg
        self._r     = radius
        self._font  = tkfont.Font(family=font_spec[0], size=font_spec[1],
                                  weight=font_spec[2] if len(font_spec)>2 else "normal")
        self._h     = height
        self._w     = width or (self._font.measure(text) + 32)
        self._cur   = fill
        self._disabled = False
        super().__init__(parent, width=self._w, height=self._h,
                         bg=bg, highlightthickness=0, cursor="hand2", **kw)
        self.bind("<Enter>",    self._on_enter)
        self.bind("<Leave>",    self._on_leave)
        self.bind("<Button-1>", self._on_click)
        self._redraw()

    def _on_enter(self, e):
        if not self._disabled:
            self._cur = self._hover; self._redraw()

    def _on_leave(self, e):
        if not self._disabled:
            self._cur = self._fill; self._redraw()

    def _on_click(self, e):
        if not self._disabled and self._cmd:
            self._cmd()

    def enable(self, fill=None, hover=None, fg=None):
        if fill:  self._fill  = fill
        if hover: self._hover = hover
        if fg:    self._fg    = fg
        self._disabled = False
        self._cur = self._fill
        self.config(cursor="hand2")
        self._redraw()

    def disable(self, fill=None, fg=None):
        if fill: self._fill = fill
        if fg:   self._fg   = fg
        self._disabled = True
        self._cur = self._fill
        self.config(cursor="")
        self._redraw()

    def _redraw(self):
        self.delete("all")
        _rr(self, 0, 0, self._w, self._h, self._r, self._cur)
        self.create_text(self._w//2, self._h//2, text=self._text,
                         fill=self._fg, font=self._font, anchor="center")

# ─── INSET BORDER FRAME ───────────────────────────────────────────────────────
class BorderFrame(tk.Frame):
    """Frame with a thin inset border line."""
    def __init__(self, parent, color=BORDERS, **kw):
        super().__init__(parent, highlightthickness=1,
                         highlightbackground=color, **kw)

# ─── PROGRESS BAR ─────────────────────────────────────────────────────────────
class ProgressBar(tk.Canvas):
    def __init__(self, parent, bg=SURFD, **kw):
        kw.setdefault("height", 4)
        super().__init__(parent, bg=bg, highlightthickness=0, **kw)
        self._pct   = 0.0
        self._bg    = bg
        self._ready = False
        self.bind("<Configure>", self._on_cfg)

    def _on_cfg(self, e):
        self._ready = True
        self._redraw()

    def set_pct(self, pct):
        self._pct = max(0.0, min(1.0, pct))
        self._redraw()

    def _redraw(self):
        if not self._ready: return
        self.delete("all")
        w = self.winfo_width(); h = self.winfo_height()
        _rr(self, 0, 0, w, h, h//2, self._bg)
        if self._pct > 0:
            fw = max(h, int(w * self._pct))
            _rr(self, 0, 0, fw, h, h//2, ACCENT)

# ─── ICON BUTTON (title bar) ──────────────────────────────────────────────────
class IconBtn(tk.Canvas):
    SZ = 24
    def __init__(self, parent, draw_fn, cmd, tooltip="", bg=TBAR, **kw):
        super().__init__(parent, width=self.SZ, height=self.SZ,
                         bg=bg, highlightthickness=0, cursor="hand2", **kw)
        self._draw_fn = draw_fn
        self._cmd     = cmd
        self._bg      = bg
        self._hovered = False
        self.bind("<Enter>",    lambda e: self._hover(True))
        self.bind("<Leave>",    lambda e: self._hover(False))
        self.bind("<Button-1>", lambda e: cmd() if cmd else None)
        self._redraw()

    def _hover(self, on):
        self._hovered = on; self._redraw()

    def _redraw(self):
        self.delete("all")
        if self._hovered:
            _rr(self, 1, 1, self.SZ-1, self.SZ-1, 5, SURFD)
        self._draw_fn(self)

    def set_badge(self, n):
        self._badge = n; self._redraw()


# ─── MAIN APP ─────────────────────────────────────────────────────────────────
class App(tk.Tk):
    W, H = 560, 800

    def __init__(self):
        super().__init__()
        self.title("LR Pick Flagger")
        self.resizable(False, False)
        self.configure(bg=BG)
        self.geometry(f"{self.W}x{self.H}")

        # ── State ──────────────────────────────────────────────────────────────
        self._filenames   = []          # parsed from paste box
        self._folder_id   = None        # selected folder id
        self._folder_path = ""          # selected folder path
        self._matches     = []          # last search results
        self._history     = _load_hist()
        self._hist_open   = False
        self._toast_after = None

        # ── Build ──────────────────────────────────────────────────────────────
        self._build_titlebar()
        self._build_body()
        self._build_footer()
        self._build_history_overlay()
        self._update_run_btn()
        self._update_hist_badge()

    # ═══ TITLE BAR ════════════════════════════════════════════════════════════
    def _build_titlebar(self):
        tb = tk.Frame(self, bg=TBAR, height=38)
        tb.pack(fill="x"); tb.pack_propagate(False)

        # Traffic lights
        dots = tk.Frame(tb, bg=TBAR)
        dots.pack(side="left", padx=14, pady=13)
        for col in ("#FF5F57", "#FEBC2E", "#28C840"):
            c = tk.Canvas(dots, width=12, height=12, bg=TBAR, highlightthickness=0)
            c.pack(side="left", padx=4)
            c.create_oval(0, 0, 12, 12, fill=col, outline="")

        # Centered title
        tk.Label(tb, text="LR Pick Flagger", bg=TBAR, fg=TEXT,
                 font=(F, 13, "bold")).place(relx=0.5, rely=0.5, anchor="center")

        # Right icon buttons
        right = tk.Frame(tb, bg=TBAR)
        right.pack(side="right", padx=10)

        def _draw_hist(c):
            cx, cy = 12, 12
            c.create_arc(cx-6, cy-6, cx+6, cy+6, start=30, extent=300,
                         outline=TEXTD, width=1.3, style="arc")
            c.create_line(cx, cy, cx+4, cy-2, fill=TEXTD, width=1.3, capstyle="round")
            c.create_line(cx, cy-5, cx, cy, fill=TEXTD, width=1.3, capstyle="round")

        def _draw_reset(c):
            cx, cy = 12, 12
            c.create_arc(cx-5, cy-5, cx+5, cy+5, start=40, extent=280,
                         outline=TEXTD, width=1.3, style="arc")
            c.create_line(cx+4, cy-5, cx+5, cy-8, fill=TEXTD, width=1.3, capstyle="round")
            c.create_line(cx+4, cy-5, cx+8, cy-3, fill=TEXTD, width=1.3, capstyle="round")

        self._hist_btn = IconBtn(right, _draw_hist, self._toggle_history, bg=TBAR)
        self._hist_btn.pack(side="left")
        self._badge_canvas = tk.Canvas(right, width=10, height=10, bg=TBAR,
                                       highlightthickness=0)
        self._badge_canvas.pack(side="left")

        IconBtn(right, _draw_reset, self._reset, bg=TBAR).pack(side="left", padx=(2,0))

        # Bottom border
        tk.Frame(self, bg=TBLINE, height=1).pack(fill="x")

    def _update_hist_badge(self):
        c = self._badge_canvas
        c.delete("all")
        n = len(self._history)
        if n > 0:
            c.configure(width=16, height=16)
            _rr(c, 0, 0, 16, 16, 8, ACCENT)
            f = tkfont.Font(family=F, size=9, weight="bold")
            c.create_text(8, 8, text=str(min(n, 99)), fill="#fff",
                          font=f, anchor="center")
        else:
            c.configure(width=6, height=6)

    # ═══ SCROLLABLE BODY ══════════════════════════════════════════════════════
    def _build_body(self):
        self._body_container = tk.Frame(self, bg=BG)
        self._body_container.pack(fill="both", expand=True)

        self._sc = tk.Canvas(self._body_container, bg=BG,
                             highlightthickness=0, bd=0)
        self._sc.pack(fill="both", expand=True)

        self._cf = tk.Frame(self._sc, bg=BG)
        self._cw = self._sc.create_window(0, 0, window=self._cf, anchor="nw")

        self._cf.bind("<Configure>", lambda e:
            self._sc.configure(scrollregion=self._sc.bbox("all")))
        self._sc.bind("<Configure>", lambda e:
            self._sc.itemconfig(self._cw, width=e.width))
        self.bind_all("<MouseWheel>", lambda e:
            self._sc.yview_scroll(int(-1*(e.delta/120)), "units"))

        # Build content sections
        self._build_hero()
        self._build_step1()
        self._build_step2()
        self._build_run_section()
        self._build_helper_text()

    # ═══ FOOTER ═══════════════════════════════════════════════════════════════
    def _build_footer(self):
        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")
        ft = tk.Frame(self, bg=BG, height=34)
        ft.pack(fill="x"); ft.pack_propagate(False)

        inner = tk.Frame(ft, bg=BG)
        inner.pack(fill="x", padx=G, pady=7)

        # Folder icon
        fi = tk.Canvas(inner, width=13, height=13, bg=BG, highlightthickness=0)
        fi.pack(side="left")
        fi.bind("<Configure>", lambda e, c=fi: (
            c.delete("all"),
            c.create_polygon(1,4, 4,4, 5,2, 10,2, 10,11, 1,11,
                             fill="", outline=TEXTD, width=1),
        ))

        # Catalog name
        cat = Path(CATALOG).name
        tk.Label(inner, text=cat, bg=BG, fg=TEXTD,
                 font=(FM, 10)).pack(side="left", padx=(6,0))

        # Ready indicator
        rframe = tk.Frame(inner, bg=BG)
        rframe.pack(side="right")
        dot = tk.Canvas(rframe, width=6, height=6, bg=BG, highlightthickness=0)
        dot.pack(side="left")
        dot.create_oval(0, 0, 6, 6, fill=SUCCESS, outline="")
        tk.Label(rframe, text="Ready", bg=BG, fg=SUCCESS,
                 font=(F, 10, "bold")).pack(side="left", padx=(4,0))

    # ═══ HERO ═════════════════════════════════════════════════════════════════
    def _build_hero(self):
        hero = tk.Frame(self._cf, bg=BG)
        hero.pack(fill="x", padx=G, pady=(SEC, 0))

        # Icon: 44x44 accent rounded square + flag glyph
        icon = tk.Canvas(hero, width=44, height=44, bg=BG, highlightthickness=0)
        icon.pack(side="left")
        icon.bind("<Configure>", lambda e, c=icon: (
            c.delete("all"),
            _rr(c, 0, 0, 44, 44, 10, ACCENT),
            _draw_flag(c, 22, 22, 22, "#fff"),
        ))

        # Title + subtitle
        txt = tk.Frame(hero, bg=BG)
        txt.pack(side="left", padx=(12,0))
        tk.Label(txt, text="LR Pick Flagger", bg=BG, fg=TEXT,
                 font=(F, 22, "bold"), anchor="w").pack(anchor="w")
        tk.Label(txt, text="Flag Pixieset favorites as picks in Lightroom Classic",
                 bg=BG, fg=TEXTD, font=(F, 12), anchor="w").pack(anchor="w", pady=(3,0))

        # Separator
        tk.Frame(self._cf, bg=BORDER, height=1).pack(fill="x", pady=(SEC,0))

    # ═══ STEP 1 ═══════════════════════════════════════════════════════════════
    def _build_step1(self):
        p = self._cf

        # Header row
        hdr = tk.Frame(p, bg=BG)
        hdr.pack(fill="x", padx=G, pady=(SEC, 8))
        self._b1 = StepBadge(hdr, "1", bg=BG)
        self._b1.pack(side="left")
        tk.Label(hdr, text="  Paste Pixieset list", bg=BG, fg=TEXT,
                 font=(F, 13, "bold")).pack(side="left")
        self._chip = CountChip(hdr, bg=BG)
        self._chip.pack(side="right")

        # Paste box
        pb = BorderFrame(p, bg=SURF, bd=0)
        pb.pack(fill="x", padx=G)
        self.paste_box = tk.Text(
            pb, height=8, wrap="word", bg=SURF, fg=TEXT,
            insertbackground=TEXT, relief="flat", bd=0,
            font=(FM, 11), padx=14, pady=12,
            selectbackground=ACCDIM, selectforeground=TEXT,
        )
        self.paste_box.pack(fill="x")

        _PH = ("Paste your Pixieset Lightroom Copy List, "
               "or drop a .txt / .csv file\n\n"
               "DSC_4823_LR_Edit.jpg\nDSC_4825_LR_Edit.jpg\n...")
        self.paste_box.insert("1.0", _PH)
        self.paste_box.config(fg=TEXTF)
        self.paste_box.edit_modified(False)
        self._paste_ph = True

        self.paste_box.bind("<FocusIn>",    self._paste_focus_in)
        self.paste_box.bind("<<Modified>>", self._paste_changed)

        # Drag-and-drop
        self.paste_box.bind("<Drop>",      self._on_drop)
        self.paste_box.bind("<DragEnter>", lambda e: e.widget.config(bg=ACCDIM))
        self.paste_box.bind("<DragLeave>", lambda e: e.widget.config(bg=SURF))

    def _paste_focus_in(self, e):
        if self._paste_ph:
            self.paste_box.delete("1.0", "end")
            self.paste_box.config(fg=TEXT)
            self._paste_ph = False

    def _paste_changed(self, e):
        self.paste_box.edit_modified(False)
        if self._paste_ph:
            return
        raw = self.paste_box.get("1.0", "end-1c")
        self._filenames = _parse(raw)
        self._chip.set_count(len(self._filenames))
        self._b1.set_done(len(self._filenames) > 0)
        self._update_run_btn()

    def _on_drop(self, e):
        try:
            path = e.data.strip("{}")
            if path.lower().endswith((".txt", ".csv")):
                text = Path(path).read_text()
                if self._paste_ph:
                    self.paste_box.delete("1.0", "end")
                    self.paste_box.config(fg=TEXT)
                    self._paste_ph = False
                self.paste_box.insert("1.0", text)
                self.paste_box.event_generate("<<Modified>>")
        except Exception:
            pass

    # ═══ STEP 2 ═══════════════════════════════════════════════════════════════
    def _build_step2(self):
        p = self._cf

        # Header
        hdr = tk.Frame(p, bg=BG)
        hdr.pack(fill="x", padx=G, pady=(SEC, 8))
        self._b2 = StepBadge(hdr, "2", bg=BG)
        self._b2.pack(side="left")
        tk.Label(hdr, text="  Shoot folder keyword", bg=BG, fg=TEXT,
                 font=(F, 13, "bold")).pack(side="left")

        # Search row
        row = tk.Frame(p, bg=BG)
        row.pack(fill="x", padx=G)
        row.columnconfigure(0, weight=1)

        # Input with magnifier
        inp_border = BorderFrame(row, bg=SURF, bd=0)
        inp_border.grid(row=0, column=0, sticky="ew")
        inp_inner = tk.Frame(inp_border, bg=SURF)
        inp_inner.pack(fill="x")

        mg = tk.Canvas(inp_inner, width=20, height=36, bg=SURF, highlightthickness=0)
        mg.pack(side="left", padx=(10,0))
        mg.bind("<Configure>", lambda e, c=mg: (
            c.delete("all"),
            c.create_oval(4, 10, 14, 20, outline=TEXTD, width=1.4),
            c.create_line(13, 19, 18, 24, fill=TEXTD, width=1.4, capstyle="round"),
        ))

        _FPH = "e.g. Tea Garden, Sarah, Wedding"
        self.folder_entry = tk.Entry(
            inp_inner, bg=SURF, fg=TEXTF, relief="flat", bd=0,
            insertbackground=TEXT, font=(F, 13),
        )
        self.folder_entry.pack(side="left", fill="x", expand=True, ipady=9)
        self.folder_entry.insert(0, _FPH)
        self.folder_entry.bind("<FocusIn>",  self._folder_focus_in)
        self.folder_entry.bind("<Return>",   lambda e: self._do_search())
        self._folder_ph = True

        self._search_btn = RBtn(
            row, "Search", self._do_search,
            height=36, width=84,
            fill=SURFH, hover=BORDERS, fg=TEXT,
            font_spec=(F, 12, "bold"), bg=BG,
        )
        self._search_btn.grid(row=0, column=1, padx=(8,0), sticky="ns")

        # Result area (rebuilt on each search)
        self._result_area = tk.Frame(p, bg=BG)
        self._result_area.pack(fill="x", padx=G, pady=(6, 0))

    def _folder_focus_in(self, e):
        if self._folder_ph:
            self.folder_entry.delete(0, "end")
            self.folder_entry.config(fg=TEXT)
            self._folder_ph = False

    def _do_search(self):
        kw = self.folder_entry.get().strip()
        if self._folder_ph or not kw:
            return
        # Clear previous results
        self._clear_result_area()
        self._folder_id   = None
        self._folder_path = ""
        self._b2.set_done(False)
        self._update_run_btn()

        # Show searching state
        sf = tk.Frame(self._result_area, bg=BG)
        sf.pack(fill="x", pady=(8,0))
        self._spinner_label = tk.Label(sf, text="Searching catalog…",
                                       bg=BG, fg=TEXTD, font=(F, 12))
        self._spinner_label.pack(side="left", padx=(0,0))
        self._spinner_phase = 0
        self._animate_spinner()

        def run():
            try:
                matches = _search_db(kw)
                self.after(0, lambda: self._on_search_done(matches))
            except Exception as ex:
                self.after(0, lambda: self._on_search_err(str(ex)))

        threading.Thread(target=run, daemon=True).start()

    def _animate_spinner(self):
        try:
            dots = "." * ((self._spinner_phase % 3) + 1)
            self._spinner_label.config(text=f"Searching catalog{dots}")
            self._spinner_phase += 1
            self._spinner_id = self.after(350, self._animate_spinner)
        except tk.TclError:
            pass

    def _cancel_spinner(self):
        try:
            self.after_cancel(self._spinner_id)
        except (AttributeError, tk.TclError):
            pass

    def _clear_result_area(self):
        self._cancel_spinner()
        for w in self._result_area.winfo_children():
            w.destroy()

    def _on_search_done(self, matches):
        self._cancel_spinner()
        self._clear_result_area()
        self._matches = matches

        if not matches:
            # No matches
            ef = tk.Frame(self._result_area, bg=BG)
            ef.pack(fill="x", pady=(8,0))
            err_ic = tk.Canvas(ef, width=14, height=14, bg=BG, highlightthickness=0)
            err_ic.pack(side="left")
            err_ic.create_oval(0, 0, 14, 14, fill=ERRD, outline=ERRB)
            _draw_x(err_ic, 7, 7, 3.5, ERR, w=1.5)
            tk.Label(ef, text="  No folders match this keyword.",
                     bg=BG, fg=ERR, font=(F, 12)).pack(side="left")
            return

        if len(matches) == 1:
            self._select_folder(matches[0][0], matches[0][1])
        else:
            # Multiple matches — show picker
            self._show_picker(matches)

    def _on_search_err(self, msg):
        self._cancel_spinner()
        self._clear_result_area()
        tk.Label(self._result_area, text=f"Error: {msg}",
                 bg=BG, fg=ERR, font=(F, 11),
                 wraplength=460, anchor="w", justify="left"
                 ).pack(fill="x", pady=(8,0))

    def _select_folder(self, fid, fpath):
        self._folder_id   = fid
        self._folder_path = fpath
        self._b2.set_done(True)
        self._update_run_btn()
        self._clear_result_area()
        self._show_single_card(fid, fpath)

    def _show_single_card(self, fid, fpath):
        card = tk.Frame(self._result_area, bg=SUCCD,
                        highlightthickness=1, highlightbackground=SUCCB)
        card.pack(fill="x", pady=(8, 0))
        inner = tk.Frame(card, bg=SUCCD)
        inner.pack(fill="x", padx=10, pady=8)

        ck = tk.Canvas(inner, width=14, height=14, bg=SUCCD, highlightthickness=0)
        ck.pack(side="left")
        ck.create_oval(0, 0, 14, 14, fill=SUCCESS+"28", outline=SUCCB)
        _draw_check(ck, 7, 7, 4, SUCCESS, w=1.6)

        short = _short(fpath)
        tk.Label(inner, text=f"  {short}", bg=SUCCD, fg=TEXT,
                 font=(F, 12, "bold")).pack(side="left")
        tk.Label(inner, text=f"id {fid}", bg=SUCCD, fg=TEXTD,
                 font=(FM, 10)).pack(side="right")

    def _show_picker(self, matches):
        warn = tk.Frame(self._result_area, bg=BG)
        warn.pack(fill="x", pady=(8,0))
        wi = tk.Canvas(warn, width=14, height=14, bg=BG, highlightthickness=0)
        wi.pack(side="left")
        wi.create_oval(0, 0, 14, 14, fill=WARND, outline="#5A4800")
        wi.create_text(7, 7, text="!", fill=WARN, font=tkfont.Font(family=F, size=9, weight="bold"))
        tk.Label(warn, text=f"  {len(matches)} folders match — pick one:",
                 bg=BG, fg=WARN, font=(F, 11)).pack(side="left")

        picker = BorderFrame(self._result_area, bg=SURF, bd=0)
        picker.pack(fill="x", pady=(6,0))

        for i, (fid, fpath) in enumerate(matches):
            short = _short(fpath)
            if i > 0:
                tk.Frame(picker, bg=BORDERS, height=1).pack(fill="x")
            card = tk.Frame(picker, bg=SURF, cursor="hand2")
            card.pack(fill="x")
            inner = tk.Frame(card, bg=SURF)
            inner.pack(fill="x", padx=12, pady=8)
            name_l = tk.Label(inner, text=short, bg=SURF, fg=TEXT,
                              font=(F, 12, "bold"), anchor="w")
            name_l.pack(fill="x")
            path_l = tk.Label(inner, text=fpath, bg=SURF, fg=TEXTF,
                              font=(FM, 10), anchor="w", wraplength=460)
            path_l.pack(fill="x", pady=(2,0))

            widgets = [card, inner, name_l, path_l]

            def _click(e=None, fid=fid, fpath=fpath, ws=widgets):
                for w in ws: w.config(bg=SURF)
                self._select_folder(fid, fpath)

            def _enter(e, ws=widgets):
                for w in ws: w.config(bg=SURFD)

            def _leave(e, ws=widgets):
                for w in ws: w.config(bg=SURF)

            for w in widgets:
                w.bind("<Button-1>", _click)
                w.bind("<Enter>",    _enter)
                w.bind("<Leave>",    _leave)

    # ═══ RUN SECTION ══════════════════════════════════════════════════════════
    def _build_run_section(self):
        self._run_sec = tk.Frame(self._cf, bg=BG)
        self._run_sec.pack(fill="x", padx=G, pady=(20, 0))

        # Run button
        self._btn_panel = tk.Frame(self._run_sec, bg=BG)
        self._btn_panel.pack(fill="x")
        self.run_btn = RBtn(
            self._btn_panel, "Flag Picks in Lightroom", self._do_run,
            height=44, fill=SURFH, hover=SURFH, fg=TEXTF,
            radius=10, font_spec=(F, 14, "bold"), bg=BG,
        )
        self.run_btn.pack(fill="x")
        self.run_btn._w = 1  # will resize on pack

        # Make button fill width via Frame resize binding
        self._btn_panel.bind("<Configure>", self._resize_run_btn)

        # Progress card (hidden initially)
        self._card_panel = tk.Frame(self._run_sec, bg=BG)
        self._build_card_panel()

        # Result panel (hidden initially)
        self._result_sec = tk.Frame(self._run_sec, bg=BG)
        self._build_result_section()

        # Error panel (hidden initially)
        self._err_sec = tk.Frame(self._run_sec, bg=BG)
        self._build_error_section()

    def _resize_run_btn(self, e):
        w = e.width
        if w > 1:
            self.run_btn.config(width=w)
            self.run_btn._w = w
            self.run_btn._redraw()

    def _build_card_panel(self):
        card = tk.Frame(self._card_panel, bg=SURF,
                        highlightthickness=1, highlightbackground=BORDERS)
        card.pack(fill="x")

        top = tk.Frame(card, bg=SURF)
        top.pack(fill="x", padx=18, pady=(16, 10))

        self._card_lbl = tk.Label(top, text="Backing up catalog…",
                                   bg=SURF, fg=TEXT, font=(F, 13, "bold"))
        self._card_lbl.pack(side="left")
        self._card_pct = tk.Label(top, text="0%", bg=SURF, fg=TEXTD,
                                   font=(FM, 11))
        self._card_pct.pack(side="right")

        pb_wrap = tk.Frame(card, bg=SURF)
        pb_wrap.pack(fill="x", padx=18, pady=(0, 10))
        self._progress = ProgressBar(pb_wrap, bg=SURFD)
        self._progress.pack(fill="x", ipady=2)

        self._card_sub = tk.Label(card, bg=SURF, fg=TEXTF, font=(F, 11),
                                   wraplength=460, justify="left",
                                   text="Writing a timestamped .lrcat backup before any changes.")
        self._card_sub.pack(anchor="w", padx=18, pady=(0, 14))

    def _build_result_section(self):
        """Pre-build placeholder; rebuilt dynamically on result."""
        pass  # built dynamically in _show_result()

    def _build_error_section(self):
        """Pre-build placeholder; rebuilt dynamically on error."""
        pass

    def _build_helper_text(self):
        self._helper = tk.Label(
            self._cf,
            text="A timestamped backup of your catalog is written before any change.\n"
                 "Close Lightroom before running.",
            bg=BG, fg=TEXTF, font=(F, 11),
            wraplength=460, justify="left", anchor="w",
        )
        self._helper.pack(fill="x", padx=G, pady=(14, SEC))

    # ─── Run state management ─────────────────────────────────────────────────
    def _update_run_btn(self):
        if self._filenames and self._folder_id:
            self.run_btn.enable(ACCENT, ACCENTH, "#fff")
        else:
            self.run_btn.disable(SURFH, TEXTF)

    def _show_state(self, state):
        """state: 'idle' | 'running' | 'result' | 'error'"""
        self._btn_panel.pack_forget()
        self._card_panel.pack_forget()
        self._result_sec.pack_forget()
        self._err_sec.pack_forget()
        self._helper.pack_forget()

        if state == "idle":
            self._btn_panel.pack(fill="x")
            self._helper.pack(fill="x", padx=G, pady=(14, SEC))
        elif state == "running":
            self._card_panel.pack(fill="x")
        elif state == "result":
            self._result_sec.pack(fill="x")
        elif state == "error":
            self._err_sec.pack(fill="x")
            self._helper.pack(fill="x", padx=G, pady=(14, SEC))

    # ─── Run execution ────────────────────────────────────────────────────────
    def _do_run(self):
        if not (self._filenames and self._folder_id):
            return
        if not os.path.exists(CATALOG):
            messagebox.showerror("Catalog not found",
                                 f"Cannot find:\n{CATALOG}")
            return

        self._show_state("running")
        fnames = list(self._filenames)
        fid    = self._folder_id

        def run():
            try:
                # Backup phase
                self.after(0, lambda: (
                    self._card_lbl.config(text="Backing up catalog…"),
                    self._card_sub.config(
                        text="Writing a timestamped .lrcat backup before any changes."),
                    self._progress.set_pct(0.0),
                    self._card_pct.config(text="0%"),
                ))
                bname = _backup_db()
                self.after(0, lambda: (
                    self._progress.set_pct(1.0),
                    self._card_pct.config(text="100%"),
                ))

                # Flag phase
                def on_prog(done, total):
                    pct = done / total
                    label = f"Flagging picks · {done} of {total}"
                    self.after(0, lambda: (
                        self._card_lbl.config(text=label),
                        self._card_sub.config(
                            text="Setting pick=1 in Adobe_images for each match."),
                        self._progress.set_pct(pct),
                        self._card_pct.config(text=f"{int(pct*100)}%"),
                    ))

                matched, not_found = _flag_db(fid, fnames, on_prog)
                ts = time.time()

                entry = {
                    "id":        f"run-{int(ts)}",
                    "timestamp": ts,
                    "folder":    {"id": fid, "path": self._folder_path},
                    "matched":   matched,
                    "notFound":  not_found,
                    "backupName": bname,
                }
                self._history.insert(0, entry)
                self._history = self._history[:50]
                _save_hist(self._history)

                self.after(0, lambda: (
                    self._on_result(matched, not_found, bname),
                    self._update_hist_badge(),
                ))

            except Exception as ex:
                self.after(0, lambda: self._on_error(str(ex)))

        threading.Thread(target=run, daemon=True).start()

    def _on_result(self, matched, not_found, bname):
        # Clear and rebuild result section
        for w in self._result_sec.winfo_children():
            w.destroy()

        total     = len(matched) + len(not_found)
        all_match = len(not_found) == 0
        none_match = len(matched) == 0

        # Summary header
        header = tk.Frame(self._result_sec, bg=SURF,
                          highlightthickness=1, highlightbackground=BORDERS)
        header.pack(fill="x")

        # Summary row
        sumrow = tk.Frame(header, bg=SURF)
        sumrow.pack(fill="x", padx=18, pady=(14,6))

        icon_c = tk.Canvas(sumrow, width=22, height=22, bg=SURF, highlightthickness=0)
        icon_c.pack(side="left")
        ibg = SUCCD if not none_match else ERRD
        ibdr = SUCCB if not none_match else ERRB
        icon_c.create_oval(0, 0, 22, 22, fill=ibg, outline=ibdr)
        if none_match:
            _draw_x(icon_c, 11, 11, 5, ERR, w=1.6)
        else:
            _draw_check(icon_c, 11, 11, 6, SUCCESS, w=1.8)

        if none_match:
            summary = "No photos flagged"
        elif all_match:
            summary = f"{len(matched)} photo{'s' if len(matched)!=1 else ''} flagged"
        else:
            summary = f"{len(matched)} of {total} flagged"

        tk.Label(sumrow, text=f"  {summary}", bg=SURF, fg=TEXT,
                 font=(F, 15, "bold")).pack(side="left")

        sub_text = ("None of the pasted filenames matched files in this folder."
                    if none_match else
                    "Open Lightroom and filter by Pick to verify.")
        tk.Label(header, text=sub_text, bg=SURF, fg=TEXTD,
                 font=(F, 11), anchor="w", padx=18, pady=0
                 ).pack(anchor="w", padx=(40,18), pady=(0,12))

        # Divider
        tk.Frame(header, bg=BORDERS, height=1).pack(fill="x")

        # Tabs + chip area
        tab_var = tk.StringVar(value="matched")
        tabs_row = tk.Frame(header, bg=SURF)
        tabs_row.pack(fill="x", padx=10, pady=(8,4))

        chip_scroll = tk.Frame(header, bg=SURF)
        chip_scroll.pack(fill="x", padx=14, pady=(0,12))

        chip_inner = tk.Frame(chip_scroll, bg=SURF)
        chip_inner.pack(fill="x")

        def _rebuild_chips(tab):
            for w in chip_inner.winfo_children():
                w.destroy()
            lst = matched if tab == "matched" else not_found
            if not lst:
                msg = ("Clean run — every filename was found in the folder."
                       if tab == "matched" else
                       "No misses — every filename was found in the folder."
                       if tab != "matched" else
                       "No matches in this run.")
                tk.Label(chip_inner, text=msg, bg=SURF, fg=TEXTF,
                         font=(F, 11)).pack(anchor="w", pady=8)
                return
            row = None
            for i, fn in enumerate(lst):
                if i % 3 == 0:
                    row = tk.Frame(chip_inner, bg=SURF)
                    row.pack(fill="x", pady=1)
                cbg = (SUCCD if tab == "matched" else ERRD)
                cfg = (SUCCESS if tab == "matched" else ERR)
                tk.Label(row, text=fn, bg=cbg, fg=cfg,
                         font=(FM, 10), padx=6, pady=4,
                         relief="flat", bd=0
                         ).pack(side="left", padx=(0,4))

        def _set_tab(t, tabs_row=tabs_row):
            tab_var.set(t)
            for w in tabs_row.winfo_children():
                if hasattr(w, "_tab_id"):
                    active = w._tab_id == t
                    w.config(bg=SURFD if active else SURF,
                             fg=TEXT if active else TEXTD)
            _rebuild_chips(t)

        for label, tab_id, count, color in [
            ("Matched",   "matched",  len(matched),   SUCCESS),
            ("Not found", "notfound", len(not_found),  ERR),
        ]:
            btn = tk.Frame(tabs_row, bg=SURF, cursor="hand2",
                           padx=8, pady=4)
            btn._tab_id = tab_id
            btn.pack(side="left", padx=2)
            dot = tk.Canvas(btn, width=6, height=6, bg=SURF, highlightthickness=0)
            dot.pack(side="left", padx=(0,4))
            dot.create_oval(0, 0, 6, 6, fill=color)
            tk.Label(btn, text=f"{label} ", bg=SURF, fg=TEXTD,
                     font=(F, 11)).pack(side="left")
            tk.Label(btn, text=str(count), bg=SURF, fg=TEXTF,
                     font=(FM, 10)).pack(side="left")
            btn.bind("<Button-1>", lambda e, t=tab_id: _set_tab(t))
            for w in btn.winfo_children():
                w.bind("<Button-1>", lambda e, t=tab_id: _set_tab(t))

        # Restore backup button (right side of tabs)
        rb = tk.Label(tabs_row, text="Restore backup", bg=SURF, fg=TEXTD,
                      font=(F, 11), cursor="hand2", padx=6, pady=4)
        rb.pack(side="right", padx=4)
        rb.bind("<Button-1>", lambda e: messagebox.showinfo(
            "Restore Backup",
            f"To restore, copy this file back to the catalog directory:\n\n{bname}"))
        rb.bind("<Enter>", lambda e: rb.config(fg=TEXT))
        rb.bind("<Leave>", lambda e: rb.config(fg=TEXTD))

        _rebuild_chips("matched")
        _set_tab("matched")

        # Footer: Run another
        foot = tk.Frame(header, bg=SURF)
        foot.pack(fill="x", padx=14, pady=(4,14))
        again = RBtn(foot, "Run another", self._reset,
                     height=36, fill=ACCENT, hover=ACCENTH, fg="#fff",
                     font_spec=(F, 12, "bold"), bg=SURF)
        again.pack(side="right")

        self._show_state("result")
        self._sc.yview_moveto(0.5)  # scroll to show result

    def _on_error(self, msg):
        # Rebuild error section
        for w in self._err_sec.winfo_children():
            w.destroy()

        banner = tk.Frame(self._err_sec, bg=ERRD,
                          highlightthickness=1, highlightbackground=ERRB)
        banner.pack(fill="x")
        inner = tk.Frame(banner, bg=ERRD)
        inner.pack(fill="x", padx=14, pady=12)

        xi = tk.Canvas(inner, width=14, height=14, bg=ERRD, highlightthickness=0)
        xi.pack(side="left", anchor="n", pady=1)
        xi.create_oval(0, 0, 14, 14, fill=ERR+"40", outline=ERRB)
        _draw_x(xi, 7, 7, 3.5, ERR, w=1.5)

        txt_frame = tk.Frame(inner, bg=ERRD)
        txt_frame.pack(side="left", padx=(10,24), fill="x", expand=True)
        tk.Label(txt_frame, text="Couldn't write to catalog",
                 bg=ERRD, fg=ERR, font=(F, 12, "bold"), anchor="w"
                 ).pack(anchor="w")
        tk.Label(txt_frame, text=msg, bg=ERRD, fg=TEXT,
                 font=(FM, 10), anchor="w", wraplength=380, justify="left"
                 ).pack(anchor="w", pady=(3,0))

        # Dismiss button
        def dismiss():
            self._show_state("idle")

        xbtn = tk.Label(inner, text="✕", bg=ERRD, fg=TEXTD,
                        font=(F, 13), cursor="hand2")
        xbtn.pack(side="right", anchor="n")
        xbtn.bind("<Button-1>", lambda e: dismiss())
        xbtn.bind("<Enter>", lambda e: xbtn.config(fg=TEXT))
        xbtn.bind("<Leave>", lambda e: xbtn.config(fg=TEXTD))

        # Try again button
        try_frame = tk.Frame(self._err_sec, bg=BG)
        try_frame.pack(fill="x", pady=(10,0))
        try_btn = RBtn(try_frame, "Try again", self._do_run,
                       height=36, fill=SURFH, hover=BORDERS, fg=TEXT,
                       font_spec=(F, 12, "bold"), bg=BG)
        try_btn.pack(side="left")

        self._show_state("error")

    # ─── Reset ────────────────────────────────────────────────────────────────
    def _reset(self):
        # Clear paste box
        self.paste_box.config(state="normal")
        self.paste_box.delete("1.0", "end")
        _PH = ("Paste your Pixieset Lightroom Copy List, "
               "or drop a .txt / .csv file\n\n"
               "DSC_4823_LR_Edit.jpg\nDSC_4825_LR_Edit.jpg\n...")
        self.paste_box.insert("1.0", _PH)
        self.paste_box.config(fg=TEXTF)
        self._paste_ph = True

        # Clear folder
        self.folder_entry.delete(0, "end")
        self.folder_entry.insert(0, "e.g. Tea Garden, Sarah, Wedding")
        self.folder_entry.config(fg=TEXTF)
        self._folder_ph = True

        # Clear state
        self._filenames   = []
        self._folder_id   = None
        self._folder_path = ""
        self._matches     = []

        # Reset badges
        self._b1.set_done(False)
        self._b2.set_done(False)
        self._chip.set_count(0)

        # Clear result area
        self._clear_result_area()

        # Clear result/error sections
        for w in self._result_sec.winfo_children():
            w.destroy()
        for w in self._err_sec.winfo_children():
            w.destroy()

        self._show_state("idle")
        self._update_run_btn()
        self._sc.yview_moveto(0)

    # ═══ HISTORY PANEL ════════════════════════════════════════════════════════
    def _build_history_overlay(self):
        self._hist_overlay = tk.Frame(self._body_container, bg=BG)
        # Not placed yet

    def _toggle_history(self):
        self._hist_open = not self._hist_open
        if self._hist_open:
            self._open_history()
        else:
            self._close_history()

    def _open_history(self):
        self._hist_overlay.place(x=0, y=0, relwidth=1, relheight=1)
        self._hist_overlay.lift()
        self._rebuild_history()

    def _close_history(self):
        self._hist_overlay.place_forget()

    def _rebuild_history(self):
        for w in self._hist_overlay.winfo_children():
            w.destroy()

        # Sub-header
        hdr = tk.Frame(self._hist_overlay, bg=BG)
        hdr.pack(fill="x", padx=G, pady=(14,0))

        # Back arrow
        back = tk.Label(hdr, text="‹", bg=BG, fg=TEXTD,
                        font=(F, 20), cursor="hand2")
        back.pack(side="left")
        back.bind("<Button-1>", lambda e: self._toggle_history())
        back.bind("<Enter>", lambda e: back.config(fg=TEXT))
        back.bind("<Leave>", lambda e: back.config(fg=TEXTD))

        tk.Label(hdr, text="  History", bg=BG, fg=TEXT,
                 font=(F, 17, "bold")).pack(side="left")
        tk.Label(hdr, text=f"  {len(self._history)} runs",
                 bg=BG, fg=TEXTF, font=(FM, 11)).pack(side="left", pady=(3,0))

        if self._history:
            clear = tk.Label(hdr, text="Clear all", bg=BG, fg=TEXTD,
                             font=(F, 12), cursor="hand2")
            clear.pack(side="right")
            clear.bind("<Button-1>", self._clear_history)
            clear.bind("<Enter>", lambda e: clear.config(fg=ERR))
            clear.bind("<Leave>", lambda e: clear.config(fg=TEXTD))

        tk.Frame(self._hist_overlay, bg=BORDER, height=1).pack(fill="x", pady=(12,0))

        # Scrollable list
        sc = tk.Canvas(self._hist_overlay, bg=BG, highlightthickness=0, bd=0)
        sc.pack(fill="both", expand=True)
        cf = tk.Frame(sc, bg=BG)
        cw = sc.create_window(0, 0, window=cf, anchor="nw")
        cf.bind("<Configure>", lambda e: sc.configure(scrollregion=sc.bbox("all")))
        sc.bind("<Configure>", lambda e: sc.itemconfig(cw, width=e.width))
        sc.bind_all("<MouseWheel>", lambda e: sc.yview_scroll(int(-1*(e.delta/120)), "units"))

        if not self._history:
            # Empty state
            ef = tk.Frame(cf, bg=BG)
            ef.pack(expand=True, pady=60)
            ec = tk.Canvas(ef, width=44, height=44, bg=BG, highlightthickness=0)
            ec.pack()
            _rr(ec, 0, 0, 44, 44, 10, SURFD)
            ec.create_arc(8,8,36,36, start=30, extent=300, outline=TEXTF, width=1.5, style="arc")
            ec.create_line(22,12,22,22, fill=TEXTF, width=1.5, capstyle="round")
            ec.create_line(22,22,29,26, fill=TEXTF, width=1.5, capstyle="round")
            tk.Label(ef, text="No runs yet", bg=BG, fg=TEXT,
                     font=(F, 13, "bold")).pack(pady=(10,0))
            tk.Label(ef, text="Once you flag picks, each run is logged here.",
                     bg=BG, fg=TEXTD, font=(F, 11),
                     wraplength=280).pack(pady=(4,0))
            return

        rows_frame = tk.Frame(cf, bg=BG)
        rows_frame.pack(fill="x", padx=G, pady=8)
        for entry in self._history:
            self._build_hist_row(rows_frame, entry)

    def _build_hist_row(self, parent, entry):
        matched   = entry.get("matched", [])
        not_found = entry.get("notFound", [])
        total     = len(matched) + len(not_found)
        all_match = len(not_found) == 0
        none_match = len(matched) == 0
        ratio     = (len(matched) / total) if total > 0 else 0
        ring      = (ERR if none_match else SUCCESS if all_match else WARN)
        short     = _short(entry["folder"]["path"])
        ts        = entry.get("timestamp", 0)
        bname     = entry.get("backupName", "")

        card = tk.Frame(parent, bg=SURF,
                        highlightthickness=1, highlightbackground=BORDERS)
        card.pack(fill="x", pady=(0,8))

        # Collapsed header
        hdr = tk.Frame(card, bg=SURF, cursor="hand2")
        hdr.pack(fill="x")

        status_c = tk.Canvas(hdr, width=28, height=28, bg=SURF, highlightthickness=0)
        status_c.pack(side="left", padx=(12,0), pady=10)
        sbg = (ERRD if none_match else SUCCD if all_match else WARND)
        status_c.create_oval(0,0,28,28, fill=sbg, outline="")
        if none_match:
            _draw_x(status_c, 14, 14, 5, ring, w=1.6)
        else:
            _draw_check(status_c, 14, 14, 6, ring, w=1.8)

        meta = tk.Frame(hdr, bg=SURF)
        meta.pack(side="left", fill="x", expand=True, padx=(10,0), pady=8)
        tk.Label(meta, text=short, bg=SURF, fg=TEXT,
                 font=(F, 12, "bold"), anchor="w").pack(fill="x")
        subrow = tk.Frame(meta, bg=SURF)
        subrow.pack(fill="x", pady=(2,0))
        tk.Label(subrow, text=_fmt_rel(ts), bg=SURF, fg=TEXTD, font=(F,11)).pack(side="left")
        tk.Label(subrow, text=" · ", bg=SURF, fg=TEXTF, font=(F,11)).pack(side="left")
        tk.Label(subrow, text=f"{len(matched)} of {total} flagged",
                 bg=SURF, fg=(ERR if none_match else TEXT),
                 font=(F,11, "bold")).pack(side="left")

        # Mini progress bar
        pb_wrap = tk.Frame(meta, bg=SURF)
        pb_wrap.pack(fill="x", pady=(4,0))
        pb = ProgressBar(pb_wrap, bg=SURFD)
        pb.pack(fill="x", ipady=1)
        pb.bind("<Configure>", lambda e, pb=pb, r=ratio: pb.set_pct(r))
        # Also force-draw after layout:
        parent.after(50, lambda pb=pb, r=ratio: pb.set_pct(r))

        # Expand/collapse
        expand_var = [False]
        body_frame  = [None]

        chev = tk.Label(hdr, text="›", bg=SURF, fg=TEXTF, font=(F, 14))
        chev.pack(side="right", padx=(0,12))

        def toggle_expand(e=None):
            expand_var[0] = not expand_var[0]
            if expand_var[0]:
                chev.config(text="⌄")
                _build_body()
            else:
                chev.config(text="›")
                if body_frame[0]:
                    body_frame[0].destroy()
                    body_frame[0] = None

        def _build_body():
            bf = tk.Frame(card, bg=SURF)
            bf.pack(fill="x")
            tk.Frame(bf, bg=BORDERS, height=1).pack(fill="x")
            body_frame[0] = bf

            inner = tk.Frame(bf, bg=SURF)
            inner.pack(fill="x", padx=14, pady=(8,0))

            # Full path
            tk.Label(inner, text=entry["folder"]["path"],
                     bg=SURF, fg=TEXTF, font=(FM, 10),
                     anchor="w", wraplength=460
                     ).pack(fill="x", pady=(0,8))

            # Chip tabs
            ctab_var = [{"val": "matched"}]
            tab_row = tk.Frame(inner, bg=SURF)
            tab_row.pack(fill="x")
            chips_wrap = tk.Frame(inner, bg=SURF)
            chips_wrap.pack(fill="x", pady=(6,0))

            def _rebuild_chips_hist(tab):
                for w in chips_wrap.winfo_children():
                    w.destroy()
                lst = matched if tab == "matched" else not_found
                if not lst:
                    tk.Label(chips_wrap,
                             text=("No misses." if tab=="matched" else "No matches."),
                             bg=SURF, fg=TEXTF, font=(F,11)).pack(anchor="w")
                    return
                row = None
                for i, fn in enumerate(lst):
                    if i % 4 == 0:
                        row = tk.Frame(chips_wrap, bg=SURF)
                        row.pack(fill="x", pady=1)
                    cbg = SUCCD if tab == "matched" else ERRD
                    cfg = SUCCESS if tab == "matched" else ERR
                    tk.Label(row, text=fn, bg=cbg, fg=cfg,
                             font=(FM, 10), padx=5, pady=3
                             ).pack(side="left", padx=(0,3))

            def _set_ctab(t):
                ctab_var[0]["val"] = t
                for w in tab_row.winfo_children():
                    if hasattr(w, "_tab_id"):
                        w.config(bg=SURFD if w._tab_id==t else SURF,
                                 fg=TEXT if w._tab_id==t else TEXTD)
                _rebuild_chips_hist(t)

            for lbl, tid, cnt, col in [
                ("Matched", "matched", len(matched), SUCCESS),
                ("Not found", "notfound", len(not_found), ERR),
            ]:
                btn = tk.Frame(tab_row, bg=SURF, cursor="hand2", padx=6, pady=3)
                btn._tab_id = tid
                btn.pack(side="left", padx=2)
                dot = tk.Canvas(btn, width=6, height=6, bg=SURF, highlightthickness=0)
                dot.pack(side="left", padx=(0,3))
                dot.create_oval(0,0,6,6, fill=col)
                tk.Label(btn, text=f"{lbl} ", bg=SURF, fg=TEXTD, font=(F,11)).pack(side="left")
                tk.Label(btn, text=str(cnt), bg=SURF, fg=TEXTF, font=(FM,10)).pack(side="left")
                btn.bind("<Button-1>", lambda e, t=tid: _set_ctab(t))
                for w in btn.winfo_children():
                    w.bind("<Button-1>", lambda e, t=tid: _set_ctab(t))

            _rebuild_chips_hist("matched")
            _set_ctab("matched")

            # Backup + actions
            tk.Frame(inner, bg=BORDERS, height=1).pack(fill="x", pady=(10,8))
            act_row = tk.Frame(inner, bg=SURF)
            act_row.pack(fill="x", pady=(0,12))

            bk_info = tk.Frame(act_row, bg=SURF)
            bk_info.pack(side="left", fill="x", expand=True)
            tk.Label(bk_info, text="CATALOG BACKUP", bg=SURF, fg=TEXTF,
                     font=(F, 9), anchor="w").pack(anchor="w")
            tk.Label(bk_info, text=bname or "—", bg=SURF, fg=TEXTD,
                     font=(FM, 10), anchor="w", wraplength=280
                     ).pack(anchor="w")

            def _restore():
                messagebox.showinfo("Restore Backup",
                    f"To restore, copy this backup back to the catalog directory:\n\n{bname}")

            def _reuse():
                self._close_history()
                self._hist_open = False
                # Populate paste box
                self.paste_box.config(state="normal")
                self.paste_box.delete("1.0", "end")
                all_files = [f + ".jpg" for f in matched + not_found]
                self.paste_box.insert("1.0", "\n".join(all_files))
                self.paste_box.config(fg=TEXT)
                self._paste_ph = False
                self._filenames = matched + not_found
                self._chip.set_count(len(self._filenames))
                self._b1.set_done(True)
                # Set folder
                self._folder_id   = entry["folder"]["id"]
                self._folder_path = entry["folder"]["path"]
                self._b2.set_done(True)
                self._clear_result_area()
                self._show_single_card(self._folder_id, self._folder_path)
                self._update_run_btn()
                self._show_state("idle")
                self._show_toast(f"Loaded {len(self._filenames)} filenames from {short}")

            restore_btn = tk.Frame(act_row, bg=SURFH, cursor="hand2",
                                   highlightthickness=1,
                                   highlightbackground=BORDERS)
            restore_btn.pack(side="right", padx=(4,0))
            restore_lbl = tk.Label(restore_btn, text="Restore", bg=SURFH, fg=TEXTD,
                                   font=(F, 11), padx=10, pady=5)
            restore_lbl.pack()
            restore_btn.bind("<Button-1>", lambda e: _restore())
            restore_lbl.bind("<Button-1>", lambda e: _restore())
            restore_btn.bind("<Enter>", lambda e: restore_lbl.config(fg=TEXT))
            restore_btn.bind("<Leave>", lambda e: restore_lbl.config(fg=TEXTD))

            reuse_btn = tk.Frame(act_row, bg=ACCENT, cursor="hand2")
            reuse_btn.pack(side="right")
            reuse_lbl = tk.Label(reuse_btn, text="Reuse list", bg=ACCENT, fg="#fff",
                                 font=(F, 11, "bold"), padx=10, pady=5)
            reuse_lbl.pack()
            reuse_btn.bind("<Button-1>", lambda e: _reuse())
            reuse_lbl.bind("<Button-1>", lambda e: _reuse())

        for w in [hdr, status_c, meta, chev] + list(hdr.winfo_children()):
            try:
                w.bind("<Button-1>", toggle_expand)
            except tk.TclError:
                pass
        hdr.bind("<Button-1>", toggle_expand)

    def _clear_history(self, e=None):
        if messagebox.askyesno("Clear History",
                               "Clear all history? This cannot be undone."):
            self._history = []
            _save_hist(self._history)
            self._update_hist_badge()
            self._rebuild_history()

    # ═══ TOAST ════════════════════════════════════════════════════════════════
    def _show_toast(self, msg):
        if hasattr(self, "_toast_widget"):
            try: self._toast_widget.place_forget()
            except: pass
        toast = tk.Label(
            self._body_container, text=msg,
            bg="#323234", fg=TEXT,
            font=(F, 12), padx=14, pady=8,
            relief="flat", bd=0,
        )
        toast.place(relx=0.5, rely=0.93, anchor="center")
        self._toast_widget = toast
        if self._toast_after:
            self.after_cancel(self._toast_after)
        self._toast_after = self.after(3200, lambda: toast.place_forget())


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
