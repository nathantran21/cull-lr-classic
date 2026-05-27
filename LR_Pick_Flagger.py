#!/usr/bin/env python3
"""
LR Pick Flagger
---------------
A Mac app for flagging Lightroom picks from a Pixieset favorites list.
Run via: python3 LR_Pick_Flagger.py
"""

import tkinter as tk
import tkinter.font as tkfont
from tkinter import messagebox
import sqlite3
import os
import re
import shutil
import threading
import math
import colorsys
import json
import time
from datetime import datetime
from pathlib import Path

# ─── YOUR CATALOG PATH ───────────────────────────────────────────────────────
CATALOG_PATH = "/Users/natha/Pictures/Lightroom Catalog-v13-v13-3/Old Lightroom Catalogs/Lightroom Catalog-v13-v13-3_2025-10-29 0911/Lightroom Catalog-v13-v13-3.lrcat"
# ─────────────────────────────────────────────────────────────────────────────

# ─── Design tokens ───────────────────────────────────────────────────────────
BG          = "#1C1C1E"
SURFACE     = "#2A2A2C"
SURFACE_DIM = "#232325"
SURFACE_HI  = "#323234"
BORDER      = "#2E2E30"
BORDER_STR  = "#3A3A3C"
TEXT        = "#F5F5F7"
TEXT_DIM    = "#8E8E93"
TEXT_FAINT  = "#636366"
ACCENT      = "#0A84FF"
ACCENT_HOV  = "#3395FF"
ACCENT_DIM  = "#1A2A3F"
SUCCESS     = "#30D158"
SUCCESS_DIM = "#0D3321"
SUCCESS_HOV = "#3AE060"
WARNING     = "#FFD60A"
ERROR       = "#FF453A"
ERROR_DIM   = "#3A1212"
GRAY        = "#48484A"
GRAY_HOV    = "#636366"
WARNING_DIM = "#3A2E00"
FONT        = "Helvetica Neue"
FONT_MONO   = "Menlo"
RADIUS      = 15
# ─────────────────────────────────────────────────────────────────────────────

# ─── History helpers ─────────────────────────────────────────────────────────

HISTORY_FILE = Path.home() / ".lr_pick_flagger_history.json"


def load_history():
    """Load past runs from disk; returns list of dicts (newest first)."""
    try:
        data = json.loads(HISTORY_FILE.read_text())
        if isinstance(data, list):
            return data[:50]
    except Exception:
        pass
    return []


def save_history(entries):
    """Persist up to 50 entries to disk."""
    try:
        HISTORY_FILE.write_text(json.dumps(entries[:50], indent=2))
    except Exception:
        pass


def fmt_relative(ts):
    """Human-readable relative time from a Unix timestamp."""
    d = time.time() - ts
    if d < 60:       return "just now"
    if d < 3600:     return f"{int(d / 60)}m ago"
    if d < 86400:    return f"{int(d / 3600)}h ago"
    if d < 86400 * 6: return f"{int(d / 86400)}d ago"
    return datetime.fromtimestamp(ts).strftime("%b %-d")


def backup_name_from_ts(ts):
    d = datetime.fromtimestamp(ts)
    return (f"Lightroom Catalog-v13-v13-3_backup_{d.strftime('%Y%m%d_%H%M%S')}.lrcat")

# ─────────────────────────────────────────────────────────────────────────────


# ─── Business logic ──────────────────────────────────────────────────────────

def strip_suffix(basename):
    return re.sub(r'(_[A-Za-z]+){2}$', '', basename)


def parse_filenames(raw_text):
    filenames = set()
    tokens = re.split(r'[\s,\n\r]+', raw_text.strip())
    for token in tokens:
        token = token.strip().strip('"').strip("'")
        if not token:
            continue
        root, _ = os.path.splitext(token)
        cleaned = strip_suffix(root if root else token)
        if cleaned:
            filenames.add(cleaned)
    return filenames


def backup_catalog():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = CATALOG_PATH.replace(".lrcat", f"_backup_{timestamp}.lrcat")
    shutil.copy2(CATALOG_PATH, backup_path)
    return backup_path


def get_matching_folders(search_term):
    conn = sqlite3.connect(CATALOG_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT f.id_local,
               r.absolutePath || f.pathFromRoot AS fullPath
        FROM AgLibraryFolder f
        JOIN AgLibraryRootFolder r ON f.rootFolder = r.id_local
    """)
    all_folders = cursor.fetchall()
    conn.close()
    return [
        (fid, fpath) for fid, fpath in all_folders
        if search_term.lower() in (fpath or "").lower()
    ]


# ─── Rounded-corner drawing ───────────────────────────────────────────────────

def _rr(canvas, x1, y1, x2, y2, r, fill):
    """Smooth rounded rectangle via polygon."""
    pts = [
        x1+r, y1,   x2-r, y1,
        x2,   y1,   x2,   y1+r,
        x2,   y2-r, x2,   y2,
        x2-r, y2,   x1+r, y2,
        x1,   y2,   x1,   y2-r,
        x1,   y1+r, x1,   y1,
    ]
    canvas.create_polygon(pts, smooth=True, fill=fill, outline="")


# ─── Aperture Flag icon (Option 06, Claude Design) ───────────────────────────

def _hsl_hex(h, s, l):
    """HSL (0-360, 0-100, 0-100) → tkinter hex color."""
    r, g, b = colorsys.hls_to_rgb(h / 360, l / 100, s / 100)
    return "#{:02x}{:02x}{:02x}".format(int(r * 255), int(g * 255), int(b * 255))

# Six aperture blade colors: hsl((deg+200)%360, 68%, 62%) — color wheel −15% sat
_BLADE_COLORS = [_hsl_hex((d + 200) % 360, 68, 62) for d in (0, 60, 120, 180, 240, 300)]


def draw_aperture_flag_icon(canvas, size):
    """
    Draw the Aperture Flag app icon (Option 06 from Claude Design) into a
    tkinter Canvas of the given size.  Dark navy radial-gradient background,
    six-blade color wheel at −15% saturation, white pole, red flag at center.
    Scales cleanly from 16 px to 1024 px.
    """
    canvas.delete("all")
    s    = size
    sc   = s / 1024.0          # scale factor relative to 1024-px master
    cx   = cy = s / 2.0        # icon center
    r_sq = round(s * 0.224)    # Big-Sur squircle corner radius ≈ 22.4 %

    # Outer / inner gradient stops (radialGradient cx=0.5 cy=0.4 r=0.8)
    edg = (0x0E, 0x15, 0x30)   # #0E1530  — outer dark
    ctr = (0x2E, 0x3F, 0x66)   # #2E3F66  — center lighter

    # ── 1. Squircle base fill (handles corners beyond the inscribed circle) ──
    _rr(canvas, 0, 0, s, s, r_sq, "#{:02x}{:02x}{:02x}".format(*edg))

    # ── 2. Radial gradient — concentric ovals, outermost first ──────────────
    #  gradient center shifted upward to cy=0.4 (matching SVG radialGradient)
    gcy   = 0.4 * s
    steps = 18
    for step in range(steps, -1, -1):   # largest/darkest first → smallest/lighter on top
        t   = step / steps              # 1 = outermost, 0 = center
        rv  = round(edg[0] + (ctr[0] - edg[0]) * (1 - t))
        gv  = round(edg[1] + (ctr[1] - edg[1]) * (1 - t))
        bv  = round(edg[2] + (ctr[2] - edg[2]) * (1 - t))
        rad = round(cx * t)
        if rad > 0:
            canvas.create_oval(cx - rad, gcy - rad, cx + rad, gcy + rad,
                               fill=f"#{rv:02x}{gv:02x}{bv:02x}", outline="")

    # ── 3. Six aperture blades (arc + center point → filled polygon) ─────────
    blade_r = 372 * sc
    n_seg   = 20               # arc subdivisions per blade
    for i, base_deg in enumerate([0, 60, 120, 180, 240, 300]):
        pts = []
        for j in range(n_seg + 1):
            # Convert CW-from-top angle to standard screen-coordinate angle
            ang = math.radians(base_deg + j * 60 / n_seg - 90)
            pts += [cx + blade_r * math.cos(ang),
                    cy + blade_r * math.sin(ang)]
        pts += [cx, cy]
        canvas.create_polygon(pts, fill=_BLADE_COLORS[i], outline="", smooth=False)

    # ── 4. Inner dark well ────────────────────────────────────────────────────
    ir = 252 * sc
    canvas.create_oval(cx - ir, cy - ir, cx + ir, cy + ir,
                       fill="#0E1530", outline="#2A3A5E",
                       width=max(1, round(sc * 4)))

    # ── 5. Flag pole (white rectangle, rounded ends) ──────────────────────────
    pcx = (430 + 12) * sc      # horizontal center of the 24-px wide pole
    pw  = max(1.5, 24 * sc)    # pole width
    py1, py2 = 360 * sc, 680 * sc
    canvas.create_rectangle(pcx - pw / 2, py1, pcx + pw / 2, py2,
                            fill="white", outline="")

    # ── 6. Flag body — gradient approximated as two tones ────────────────────
    #  SVG: M454 380 L640 400 L580 470 L640 540 L454 520 Z
    flag_pts = [454*sc, 380*sc,  640*sc, 400*sc,
                580*sc, 470*sc,  640*sc, 540*sc,  454*sc, 520*sc]
    canvas.create_polygon(flag_pts, fill="#E63465", outline="")
    #  Shadow fold (path "M580 470 L640 400 L640 540 Z", fill rgba(0,0,0,.22))
    canvas.create_polygon([580*sc, 470*sc,  640*sc, 400*sc,  640*sc, 540*sc],
                          fill="#B02050", outline="")


def draw_flag_icon_hero(canvas, size):
    """
    Draw the hero app icon: accent-coloured rounded square with white flag glyph.
    Matches the design's 44×44 icon — linear-gradient(135°, accent, accent·80%)
    with a 22×22 flag SVG path centered inside.
    """
    canvas.delete("all")
    s  = size
    r  = round(s * 0.227)          # ≈10 px at 44 px, matches borderRadius:10
    # Background — solid accent (gradient approximated by a lighter inner fill)
    _rr(canvas, 0, 0, s, s, r, ACCENT)
    # Inner highlight: top strip rgba(255,255,255,0.25) → slightly lighter blue
    _rr(canvas, 0, 0, s, s // 2, r, "#1D8FFF")

    # Flag glyph from the design's <Glyph kind="flag" size={22} color="#fff" />
    # SVG path (14×14 viewBox): M3 2V12  M3 2H10L9 4.5L10 7H3
    sc = (s * 0.5) / 14.0          # scale 14-unit glyph to half the canvas
    ox = s / 2.0 - 6.5 * sc        # center horizontally (glyph mid-x = 6.5)
    oy = s / 2.0 - 7.0 * sc        # center vertically   (glyph mid-y = 7)

    # Pole: x=3, y=2 → y=12
    px = ox + 3 * sc
    pw = max(1.5, sc * 1.5)
    canvas.create_rectangle(
        px - pw / 2, oy + 2 * sc,
        px + pw / 2, oy + 12 * sc,
        fill="white", outline="",
    )
    # Flag body: M3 2 H10 L9 4.5 L10 7 H3 Z
    canvas.create_polygon(
        [ox + 3*sc,  oy + 2*sc,
         ox + 10*sc, oy + 2*sc,
         ox + 9*sc,  oy + 4.5*sc,
         ox + 10*sc, oy + 7*sc,
         ox + 3*sc,  oy + 7*sc],
        fill="white", outline="",
    )


class RoundedBorder(tk.Canvas):
    """Canvas that draws a rounded-rect border and embeds one child widget."""

    def __init__(self, parent, height, **kwargs):
        super().__init__(parent, bg=BG, highlightthickness=0, height=height, **kwargs)
        self._child   = None
        self._focused = False
        self.bind("<Configure>", self._draw)

    def attach(self, child):
        self._child = child
        child.bind("<FocusIn>",  lambda e: self._set_focus(True),  add="+")
        child.bind("<FocusOut>", lambda e: self._set_focus(False), add="+")

    def _draw(self, event=None):
        w = self.winfo_width()
        h = self.winfo_height()
        if w < 4:
            return
        self.delete("all")
        bc = ACCENT if self._focused else BORDER_STR
        _rr(self, 0,   0,   w,   h,   RADIUS,   bc)
        _rr(self, 1.5, 1.5, w-1.5, h-1.5, RADIUS-1, SURFACE)
        if self._child:
            self.create_window(2, 2, window=self._child,
                               anchor="nw", width=w-4, height=h-4)

    def _set_focus(self, focused):
        self._focused = focused
        self._draw()


class RoundedButton(tk.Canvas):
    """Canvas-based button with rounded corners, hover, and enable/disable."""

    def __init__(self, parent, text, command, height=44,
                 fill=GRAY, hover=GRAY_HOV, fg=TEXT,
                 font_spec=None, **kwargs):
        super().__init__(parent, bg=BG, highlightthickness=0,
                         height=height, cursor="hand2", **kwargs)
        self._text    = text
        self._cmd     = command
        self._fill    = fill
        self._hover   = hover
        self._fg      = fg
        self._font    = font_spec or (FONT, 11)
        self._enabled = True
        self._cur     = fill

        self.bind("<Configure>", lambda e: self._draw(self._cur))
        self.bind("<Enter>",     self._on_enter)
        self.bind("<Leave>",     self._on_leave)
        self.bind("<Button-1>",  self._on_click)

    def _draw(self, fill):
        self._cur = fill
        w = self.winfo_width()
        h = self.winfo_height()
        if w < 4:
            return
        self.delete("all")
        _rr(self, 0, 0, w, h, RADIUS, fill)
        self.create_text(w // 2, h // 2, text=self._text,
                         fill=self._fg, font=self._font)

    def _on_enter(self, e):
        if self._enabled: self._draw(self._hover)

    def _on_leave(self, e):
        if self._enabled: self._draw(self._fill)

    def _on_click(self, e):
        if self._enabled: self._cmd()

    def enable(self, fill, hover, fg):
        self._fill, self._hover, self._fg = fill, hover, fg
        self._enabled = True
        self.config(cursor="hand2")
        self._draw(fill)

    def disable(self, fill, fg):
        self._fill = fill
        self._fg   = fg
        self._enabled = False
        self.config(cursor="")
        self._draw(fill)

    def set_text(self, text):
        self._text = text
        self._draw(self._cur)


# ─── App ─────────────────────────────────────────────────────────────────────

_PASTE_PH  = "Paste your Pixieset Lightroom Copy List,\nor drop a .txt / .csv file\n\nDSC_4823_LR_Edit.jpg\n..."
_FOLDER_PH = "e.g. Tea Garden, Sarah, Wedding"


class App(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("LR Pick Flagger")
        self.resizable(False, False)
        self.configure(bg=BG)
        self.geometry("560x820")

        self.update_idletasks()
        x = (self.winfo_screenwidth()  // 2) - 280
        y = (self.winfo_screenheight() // 2) - 410
        self.geometry(f"+{x}+{y}")

        # ── State
        self._selected_folder_id   = None
        self._selected_folder_path = None
        self._folder_matches       = []
        self._current_filenames    = []
        self._toast_after_id       = None

        # ── History
        self._history         = load_history()
        self._hist_expanded   = set()   # set of run IDs currently expanded
        self._hist_chip_tabs  = {}      # {run_id: "matched"|"notfound"}
        self._hist_open       = False

        self._build_ui()

    # ── Top-level layout ──────────────────────────────────────────────────────

    def _build_ui(self):
        self._build_hero()
        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")
        self._build_footer()          # pack bottom FIRST so scroll area fills middle
        self._build_history_panel()   # pre-built, packed/forgotten on toggle
        self._build_scroll_area()

    # ── Hero ─────────────────────────────────────────────────────────────────

    def _build_hero(self):
        hero = tk.Frame(self, bg=BG)
        hero.pack(fill="x", padx=28, pady=(22, 18))

        # Right-side icon buttons (packed before title so they stay right)
        btns = tk.Frame(hero, bg=BG)
        btns.pack(side="right", anchor="center")

        # History button (clock icon + optional count badge)
        self._hist_btn = RoundedButton(
            btns, "⏱", self._toggle_history,
            height=26, width=34, fill=BG, hover=SURFACE_HI, fg=TEXT_DIM,
            font_spec=(FONT, 12),
        )
        self._hist_btn.pack(side="left")

        # Reset button
        RoundedButton(
            btns, "↺", self._reset,
            height=26, width=30, fill=BG, hover=SURFACE_HI, fg=TEXT_DIM,
            font_spec=(FONT, 13),
        ).pack(side="left", padx=(4, 0))

        # App icon — accent square with flag glyph (matches design hero)
        ic = tk.Canvas(hero, width=44, height=44, bg=BG, highlightthickness=0)
        ic.pack(side="left")
        ic.bind("<Configure>", lambda e: draw_flag_icon_hero(ic, 44))

        # Title + subtitle
        tf = tk.Frame(hero, bg=BG)
        tf.pack(side="left", padx=(12, 0))
        tk.Label(tf, text="LR Pick Flagger",
                 bg=BG, fg=TEXT, font=(FONT, 20, "bold"), anchor="w"
                 ).pack(anchor="w")
        tk.Label(tf, text="Flag Pixieset favorites as picks in Lightroom Classic",
                 bg=BG, fg=TEXT_DIM, font=(FONT, 11), anchor="w"
                 ).pack(anchor="w", pady=(2, 0))

        self._update_hist_badge()

    # ── Scrollable content area ───────────────────────────────────────────────

    def _build_scroll_area(self):
        self._scroll_outer = tk.Frame(self, bg=BG)
        outer = self._scroll_outer
        outer.pack(fill="both", expand=True)

        self._sc = tk.Canvas(outer, bg=BG, highlightthickness=0, bd=0)
        self._sc.pack(fill="both", expand=True)

        self._cf = tk.Frame(self._sc, bg=BG)
        self._cw = self._sc.create_window(0, 0, window=self._cf, anchor="nw")

        self._cf.bind("<Configure>", lambda e: (
            self._sc.configure(scrollregion=self._sc.bbox("all"))
        ))
        self._sc.bind("<Configure>", lambda e:
            self._sc.itemconfig(self._cw, width=e.width))
        self.bind_all("<MouseWheel>",
            lambda e: self._sc.yview_scroll(int(-1 * e.delta / 120), "units"))

        self._build_content(self._cf)

    # ── Main content ─────────────────────────────────────────────────────────

    def _build_content(self, p):
        f11 = tkfont.Font(family=FONT, size=11)
        f12 = tkfont.Font(family=FONT, size=12)
        paste_h = 7 * f11.metrics("linespace") + 20 + 4
        entry_h = f12.metrics("linespace") + 20 + 4

        # ── Step 1 header
        r1 = tk.Frame(p, bg=BG)
        r1.pack(fill="x", padx=28, pady=(22, 8))
        self._b1 = self._make_badge(r1, "1")
        self._b1.pack(side="left")
        tk.Label(r1, text="  Paste Pixieset list",
                 bg=BG, fg=TEXT, font=(FONT, 13, "bold")).pack(side="left")
        self._count_chip = tk.Label(r1, text="empty",
                                    bg=SURFACE_DIM, fg=TEXT_FAINT,
                                    font=(FONT, 11, "bold"), padx=8, pady=2)
        self._count_chip.pack(side="right")

        # Paste box
        pc = RoundedBorder(p, height=paste_h)
        pc.pack(fill="x", padx=28)
        self.paste_box = tk.Text(
            pc, height=7, wrap="word",
            bg=SURFACE, fg=TEXT_FAINT,
            insertbackground=TEXT,
            relief="flat", bd=0,
            font=(FONT, 11), padx=12, pady=10,
        )
        pc.attach(self.paste_box)
        self.paste_box.insert("1.0", _PASTE_PH)
        self.paste_box.edit_modified(False)
        self.paste_box.bind("<FocusIn>",   self._clear_paste_ph)
        self.paste_box.bind("<<Modified>>", self._on_paste_modified)

        # ── Step 2 header
        r2 = tk.Frame(p, bg=BG)
        r2.pack(fill="x", padx=28, pady=(20, 8))
        self._b2 = self._make_badge(r2, "2")
        self._b2.pack(side="left")
        tk.Label(r2, text="  Shoot folder keyword",
                 bg=BG, fg=TEXT, font=(FONT, 13, "bold")).pack(side="left")

        # Folder row
        fr = tk.Frame(p, bg=BG)
        fr.pack(fill="x", padx=28)
        fr.columnconfigure(0, weight=1)

        fc = RoundedBorder(fr, height=entry_h)
        fc.grid(row=0, column=0, sticky="ew")

        fi = tk.Frame(fc, bg=SURFACE)
        fc.attach(fi)

        # Magnifying glass icon
        mg = tk.Canvas(fi, width=20, height=entry_h - 4,
                        bg=SURFACE, highlightthickness=0)
        mg.pack(side="left", padx=(10, 0))
        mg.bind("<Configure>", lambda e, c=mg: (
            c.delete("all"),
            c.create_oval(3, c.winfo_height()//2-5, 13, c.winfo_height()//2+5,
                          outline=TEXT_DIM, width=1.4),
            c.create_line(11, c.winfo_height()//2+4, 17, c.winfo_height()//2+10,
                          fill=TEXT_DIM, width=1.4, capstyle="round"),
        ))

        self.folder_entry = tk.Entry(
            fi, bg=SURFACE, fg=TEXT_FAINT,
            insertbackground=TEXT,
            relief="flat", bd=0, font=(FONT, 12),
        )
        self.folder_entry.pack(side="left", fill="x", expand=True, ipady=9)
        self.folder_entry.insert(0, _FOLDER_PH)
        self.folder_entry.bind("<FocusIn>",  self._clear_folder_ph)
        self.folder_entry.bind("<Return>",   lambda e: self._search_folder())

        self.search_btn = RoundedButton(
            fr, "Search", self._search_folder,
            height=entry_h, width=90,
            fill=GRAY, hover=GRAY_HOV, fg=TEXT,
            font_spec=(FONT, 11),
        )
        self.search_btn.grid(row=0, column=1, padx=(8, 0), sticky="ns")

        # Folder result — text label for searching / error / multi-match states
        self._folder_result_lbl = tk.Label(
            p, text="", bg=BG, fg=SUCCESS,
            font=(FONT, 11), anchor="w", wraplength=500,
        )
        self._folder_result_lbl.pack(fill="x", padx=28, pady=(6, 0))

        # Green card for single-match result (hidden until a single match is found)
        self._folder_match_card = tk.Frame(
            p, bg=SUCCESS_DIM,
            highlightthickness=1, highlightbackground="#1B5C32",
        )
        # Populated + packed on single match; pack_forgot on other states

        # Folder picker (multi-match) — card-style items built dynamically
        self._picker_frame = tk.Frame(p, bg=BG)
        self._picker_inner = tk.Frame(
            self._picker_frame,
            bg=SURFACE,
            highlightthickness=1,
            highlightbackground=BORDER_STR,
        )
        self._picker_inner.pack(fill="x", padx=28)

        # ── Dynamic run section
        self._run_sec = tk.Frame(p, bg=BG)
        self._run_sec.pack(fill="x", padx=28, pady=(20, 0))

        self._build_run_btn_panel()
        self._build_run_card_panel()
        self._build_result_panel()
        self._build_error_panel()

        # Helper text
        self._helper = tk.Label(
            p, text="A timestamped backup of your catalog is written before any change. Close Lightroom before running.",
            bg=BG, fg=TEXT_FAINT, font=(FONT, 10),
            wraplength=504, justify="left", anchor="w",
        )
        self._helper.pack(fill="x", padx=28, pady=(14, 24))

        self._show_panel("btn")

    # ── Step badges ──────────────────────────────────────────────────────────

    def _make_badge(self, parent, number, complete=False):
        s = 22
        c = tk.Canvas(parent, width=s, height=s, bg=BG, highlightthickness=0)
        self._draw_badge(c, number, complete)
        return c

    def _draw_badge(self, c, number, complete):
        s = 22
        c.delete("all")
        if complete:
            c.create_oval(0, 0, s, s, fill=ACCENT, outline="")
            c.create_line(5, 11, 9, 15,  fill="white", width=1.8, capstyle="round")
            c.create_line(9, 15, 17, 7,  fill="white", width=1.8, capstyle="round")
        else:
            c.create_oval(0, 0, s, s, fill=SURFACE_DIM, outline="")
            c.create_text(s//2, s//2+1, text=str(number),
                          fill=TEXT_DIM, font=(FONT, 10, "bold"))

    def _set_badge(self, badge_canvas, number, complete):
        self._draw_badge(badge_canvas, number, complete)

    # ── Run panels ────────────────────────────────────────────────────────────

    def _build_run_btn_panel(self):
        self._btn_panel = tk.Frame(self._run_sec, bg=BG)
        self.run_btn = RoundedButton(
            self._btn_panel, "Flag Picks in Lightroom", self._run,
            height=44, fill=SURFACE_HI, hover=SURFACE_HI, fg=TEXT_FAINT,
            font_spec=(FONT, 13, "bold"),
        )
        self.run_btn._enabled = False
        self.run_btn.config(cursor="")
        self.run_btn.pack(fill="x")

    def _build_run_card_panel(self):
        """Progress card shown during backup + flagging."""
        self._card_panel = tk.Canvas(self._run_sec, bg=BG,
                                      highlightthickness=0, height=108)
        self._card_inner = tk.Frame(self._card_panel, bg=SURFACE)
        self._card_panel.bind("<Configure>", self._draw_card_bg)

        ci = tk.Frame(self._card_inner, bg=SURFACE)
        ci.pack(fill="x", padx=18, pady=(16, 14))

        top_row = tk.Frame(ci, bg=SURFACE)
        top_row.pack(fill="x")
        self._phase_lbl = tk.Label(top_row, text="Backing up catalog…",
                                    bg=SURFACE, fg=TEXT,
                                    font=(FONT, 13, "bold"), anchor="w")
        self._phase_lbl.pack(side="left")
        self._pct_lbl = tk.Label(top_row, text="0%",
                                  bg=SURFACE, fg=TEXT_DIM,
                                  font=(FONT_MONO, 11), anchor="e")
        self._pct_lbl.pack(side="right")

        self._prog_c = tk.Canvas(ci, bg=SURFACE, highlightthickness=0, height=4)
        self._prog_c.pack(fill="x", pady=(10, 0))
        self._prog_c.bind("<Configure>", lambda e: self._draw_prog(0))

        self._phase_sub = tk.Label(
            ci, text="Writing a timestamped .lrcat backup before any changes.",
            bg=SURFACE, fg=TEXT_FAINT, font=(FONT, 10),
            wraplength=480, justify="left", anchor="w",
        )
        self._phase_sub.pack(fill="x", pady=(8, 0))

    def _draw_card_bg(self, event=None):
        c = self._card_panel
        w = c.winfo_width()
        h = c.winfo_height()
        if w < 4:
            return
        c.delete("bg")
        _rr(c, 0, 0, w, h, RADIUS, BORDER_STR)
        _rr(c, 1, 1, w-1, h-1, RADIUS-1, SURFACE)
        c.create_window(1, 1, window=self._card_inner,
                        anchor="nw", width=w-2, height=h-2, tags="bg")
        c.tag_lower("bg")

    def _draw_prog(self, pct, color=ACCENT):
        c = self._prog_c
        w = c.winfo_width()
        if w < 2:
            return
        c.delete("all")
        _rr(c, 0, 0, w, 4, 2, SURFACE_DIM)
        if pct > 0:
            _rr(c, 0, 0, max(4, int(pct * w)), 4, 2, color)

    def _build_result_panel(self):
        """Matched / not-found result card."""
        self._res_panel = tk.Canvas(self._run_sec, bg=BG,
                                     highlightthickness=0, height=1)
        self._res_inner = tk.Frame(self._res_panel, bg=SURFACE)
        self._res_panel.bind("<Configure>", self._draw_res_bg)

        ri = self._res_inner

        # Summary row
        summ = tk.Frame(ri, bg=SURFACE)
        summ.pack(fill="x", padx=18, pady=(14, 0))
        self._res_icon = tk.Canvas(summ, width=24, height=24,
                                    bg=SURFACE, highlightthickness=0)
        self._res_icon.pack(side="left")
        st = tk.Frame(summ, bg=SURFACE)
        st.pack(side="left", padx=(10, 0))
        self._res_title = tk.Label(st, text="", bg=SURFACE, fg=TEXT,
                                    font=(FONT, 15, "bold"), anchor="w")
        self._res_title.pack(anchor="w")
        self._res_sub = tk.Label(st, text="", bg=SURFACE, fg=TEXT_DIM,
                                  font=(FONT, 11), anchor="w", wraplength=420)
        self._res_sub.pack(anchor="w", pady=(2, 0))

        # Divider
        tk.Frame(ri, bg=BORDER, height=1).pack(fill="x", pady=(12, 0))

        # Tab row — tabs on left, Restore backup on right
        tr = tk.Frame(ri, bg=SURFACE)
        tr.pack(fill="x", padx=14, pady=(8, 4))

        self._tab_m = tk.Label(tr, text="● Matched  0",
                                bg=SURFACE_DIM, fg=TEXT,
                                font=(FONT, 11), padx=10, pady=5, cursor="hand2")
        self._tab_m.pack(side="left")
        self._tab_m.bind("<Button-1>", lambda e: self._set_tab("matched"))

        self._tab_n = tk.Label(tr, text="● Not found  0",
                                bg=SURFACE, fg=TEXT_DIM,
                                font=(FONT, 11), padx=10, pady=5, cursor="hand2")
        self._tab_n.pack(side="left", padx=(4, 0))
        self._tab_n.bind("<Button-1>", lambda e: self._set_tab("notfound"))

        # Restore backup — right side of tab row
        rb_tab = tk.Label(tr, text="Restore backup",
                          bg=SURFACE, fg=TEXT_DIM,
                          font=(FONT, 11), padx=8, pady=5, cursor="hand2")
        rb_tab.pack(side="right")
        rb_tab.bind("<Button-1>", lambda e: messagebox.showinfo(
            "Restore Backup",
            "Find the timestamped .lrcat backup in the same folder as your catalog."))
        rb_tab.bind("<Enter>", lambda e: rb_tab.config(bg=SURFACE_DIM))
        rb_tab.bind("<Leave>", lambda e: rb_tab.config(bg=SURFACE))

        # Chip display (Text widget with colored tags)
        self._chip_txt = tk.Text(
            ri, height=6, wrap="word",
            bg=SURFACE, fg=TEXT_DIM,
            relief="flat", bd=0,
            font=(FONT_MONO, 10),
            padx=14, pady=8,
            state="disabled",
            cursor="arrow",
            highlightthickness=0,
        )
        self._chip_txt.pack(fill="x")
        self._chip_txt.tag_config("m", background="#0D3321",  foreground=SUCCESS)
        self._chip_txt.tag_config("n", background="#3A1212",  foreground=ERROR)
        self._chip_txt.tag_config("sp", background=SURFACE,   foreground=SURFACE)

        # Footer — "Run another" primary button
        rf = tk.Frame(ri, bg=SURFACE)
        rf.pack(fill="x", padx=14, pady=(4, 14))
        run_again_btn = RoundedButton(
            rf, "Run another", self._reset,
            height=36, fill=ACCENT, hover=ACCENT_HOV, fg="#ffffff",
            font_spec=(FONT, 12, "bold"),
        )
        run_again_btn.pack(side="right")

        self._cur_tab       = "matched"
        self._res_matched   = []
        self._res_not_found = []

    def _draw_res_bg(self, event=None):
        c = self._res_panel
        w = c.winfo_width()
        h = c.winfo_height()
        if w < 4:
            return
        c.delete("bg")
        _rr(c, 0, 0, w, h, RADIUS, BORDER_STR)
        _rr(c, 1, 1, w-1, h-1, RADIUS-1, SURFACE)
        c.create_window(1, 1, window=self._res_inner,
                        anchor="nw", width=w-2, height=h-2, tags="bg")
        c.tag_lower("bg")
        # Sync canvas height to inner frame
        self.update_idletasks()
        ih = self._res_inner.winfo_reqheight()
        if ih > 1:
            c.config(height=ih + 2)

    def _build_error_panel(self):
        """Error banner with dismiss."""
        self._err_panel = tk.Canvas(self._run_sec, bg=BG,
                                     highlightthickness=0, height=80)
        self._err_inner = tk.Frame(self._err_panel, bg=ERROR_DIM)
        self._err_panel.bind("<Configure>", self._draw_err_bg)

        ei = tk.Frame(self._err_inner, bg=ERROR_DIM)
        ei.pack(fill="x", padx=14, pady=12)

        # X icon
        xi = tk.Canvas(ei, width=16, height=16, bg=ERROR_DIM, highlightthickness=0)
        xi.pack(side="left", anchor="n", pady=1)
        xi.create_line(3, 3, 13, 13, fill=ERROR, width=1.8, capstyle="round")
        xi.create_line(13, 3, 3, 13, fill=ERROR, width=1.8, capstyle="round")

        et = tk.Frame(ei, bg=ERROR_DIM)
        et.pack(side="left", fill="x", expand=True, padx=(10, 0))
        tk.Label(et, text="Couldn't write to catalog",
                 bg=ERROR_DIM, fg=ERROR, font=(FONT, 12, "bold"), anchor="w"
                 ).pack(fill="x")
        self._err_msg = tk.Label(et, text="", bg=ERROR_DIM, fg=TEXT,
                                  font=(FONT_MONO, 10),
                                  anchor="w", wraplength=380, justify="left")
        self._err_msg.pack(fill="x", pady=(2, 0))

        dm = tk.Label(ei, text="✕", bg=ERROR_DIM, fg=TEXT_DIM,
                       font=(FONT, 13), cursor="hand2")
        dm.pack(side="right", anchor="n")
        dm.bind("<Button-1>", lambda e: self._show_panel("btn"))

    def _draw_err_bg(self, event=None):
        c = self._err_panel
        w = c.winfo_width()
        h = c.winfo_height()
        if w < 4:
            return
        c.delete("bg")
        _rr(c, 0, 0, w, h, RADIUS, ERROR_DIM)
        c.create_window(0, 0, window=self._err_inner,
                        anchor="nw", width=w, height=h, tags="bg")
        c.tag_lower("bg")
        self.update_idletasks()
        ih = self._err_inner.winfo_reqheight()
        if ih > 1:
            c.config(height=ih)

    # ── Panel switching ───────────────────────────────────────────────────────

    def _show_panel(self, which):
        for panel in [self._btn_panel, self._card_panel,
                       self._res_panel, self._err_panel]:
            panel.pack_forget()
        if which == "btn":
            self._btn_panel.pack(fill="x")
            self._helper.config(
                text="A timestamped backup of your catalog is written before any change. "
                     "Close Lightroom before running.")
        elif which == "card":
            self._card_panel.pack(fill="x")
            self._helper.config(text="")
        elif which == "result":
            self._res_panel.pack(fill="x")
            self.after(50, lambda: self._draw_res_bg())
            self._helper.config(text="Open Lightroom and filter by Pick to verify.")
        elif which == "error":
            self._err_panel.pack(fill="x")
            self.after(50, lambda: self._draw_err_bg())
            self._btn_panel.pack(fill="x", pady=(12, 0))
            self._helper.config(text="Make sure Lightroom is closed, then try again.")

    # ── Footer ────────────────────────────────────────────────────────────────

    def _build_footer(self):
        foot = tk.Frame(self, bg=BG)
        foot.pack(fill="x", side="bottom")
        tk.Frame(foot, bg=BORDER, height=1).pack(fill="x")

        row = tk.Frame(foot, bg=BG)
        row.pack(fill="x", padx=20, pady=9)

        # Folder icon
        fi = tk.Canvas(row, width=14, height=14, bg=BG, highlightthickness=0)
        fi.pack(side="left")
        fi.create_arc(1, 3, 7, 9, start=45, extent=90,
                      fill=TEXT_DIM, outline="")
        fi.create_rectangle(1, 6, 13, 13, outline=TEXT_DIM, fill="", width=1)

        name = Path(CATALOG_PATH).name
        tk.Label(row, text=name, bg=BG, fg=TEXT_DIM,
                 font=(FONT_MONO, 10), anchor="w"
                 ).pack(side="left", padx=(6, 0))

        # Ready dot
        rr = tk.Frame(row, bg=BG)
        rr.pack(side="right")
        dot = tk.Canvas(rr, width=8, height=8, bg=BG, highlightthickness=0)
        dot.pack(side="left")
        dot.create_oval(1, 1, 7, 7, fill=SUCCESS, outline="")
        tk.Label(rr, text="Ready", bg=BG, fg=SUCCESS,
                 font=(FONT, 10, "bold")).pack(side="left", padx=(4, 0))

    # ── Placeholders ─────────────────────────────────────────────────────────

    def _clear_paste_ph(self, event):
        if self.paste_box.get("1.0", "end-1c") == _PASTE_PH:
            self.paste_box.delete("1.0", "end")
            self.paste_box.configure(fg=TEXT)

    def _clear_folder_ph(self, event):
        if self.folder_entry.get() == _FOLDER_PH:
            self.folder_entry.delete(0, "end")
            self.folder_entry.configure(fg=TEXT)

    # ── Live count & button state ─────────────────────────────────────────────

    def _on_paste_modified(self, event=None):
        self.paste_box.edit_modified(False)
        raw = self.paste_box.get("1.0", "end-1c").strip()
        if raw and raw != _PASTE_PH:
            names = list(parse_filenames(raw))
            self._current_filenames = names
            if names:
                n = len(names)
                self._count_chip.config(
                    text=f"{n} {'file' if n == 1 else 'files'}",
                    bg=ACCENT_DIM, fg=ACCENT)
                self._set_badge(self._b1, "1", complete=True)
            else:
                self._current_filenames = []
                self._count_chip.config(text="empty", bg=SURFACE_DIM, fg=TEXT_FAINT)
                self._set_badge(self._b1, "1", complete=False)
        else:
            self._current_filenames = []
            self._count_chip.config(text="empty", bg=SURFACE_DIM, fg=TEXT_FAINT)
            self._set_badge(self._b1, "1", complete=False)
        self._update_run_btn()

    def _update_run_btn(self):
        if self._current_filenames and self._selected_folder_id:
            self.run_btn.enable(ACCENT, ACCENT_HOV, "#FFFFFF")
        else:
            self.run_btn.disable(SURFACE_HI, TEXT_FAINT)

    # ── Folder search ────────────────────────────────────────────────────────

    def _search_folder(self):
        term = self.folder_entry.get().strip()
        if not term or term == _FOLDER_PH:
            self._show_toast("Enter a folder keyword first.")
            return

        # Hide card/picker while searching
        self._folder_match_card.pack_forget()
        self._picker_frame.pack_forget()
        self._folder_result_lbl.config(text="Searching catalog…", fg=TEXT_DIM)
        self.update()

        try:
            matches = get_matching_folders(term)
        except Exception as e:
            self._folder_result_lbl.config(text=f"✗ Catalog error: {e}", fg=ERROR)
            self._selected_folder_id = None
            self._set_badge(self._b2, "2", complete=False)
            self._update_run_btn()
            return

        if not matches:
            self._folder_result_lbl.config(
                text="✗ No folders match this keyword.", fg=ERROR)
            self._selected_folder_id = None
            self._set_badge(self._b2, "2", complete=False)
            self._update_run_btn()
            return

        if len(matches) == 1:
            fid, fpath = matches[0]
            self._selected_folder_id   = fid
            self._selected_folder_path = fpath
            short = fpath.rstrip("/").split("/")[-1]
            # Show green match card
            self._folder_result_lbl.config(text="")
            self._show_folder_match_card(fid, fpath, short)
            self._picker_frame.pack_forget()
            self._set_badge(self._b2, "2", complete=True)
        else:
            self._folder_matches = matches
            self._folder_result_lbl.config(
                text=f"{len(matches)} folders match — pick one:", fg=WARNING)
            self._folder_match_card.pack_forget()
            self._build_picker_cards(matches)
            self._picker_frame.pack(fill="x", pady=(6, 0), before=self._run_sec)

        self._update_run_btn()

    def _show_folder_match_card(self, fid, fpath, short):
        """Populate and show the green single-match result card."""
        for w in self._folder_match_card.winfo_children():
            w.destroy()
        row = tk.Frame(self._folder_match_card, bg=SUCCESS_DIM)
        row.pack(fill="x", padx=10, pady=8)
        # Check-mark icon
        ck = tk.Canvas(row, width=14, height=14,
                       bg=SUCCESS_DIM, highlightthickness=0)
        ck.pack(side="left")
        ck.create_line(2, 7, 6, 11, fill=SUCCESS, width=1.6, capstyle="round")
        ck.create_line(6, 11, 12, 4,  fill=SUCCESS, width=1.6, capstyle="round")
        tk.Label(row, text=short,
                 bg=SUCCESS_DIM, fg=TEXT, font=(FONT, 12, "bold"),
                 ).pack(side="left", padx=(8, 0))
        tk.Label(row, text=f"id {fid}",
                 bg=SUCCESS_DIM, fg=TEXT_DIM, font=(FONT_MONO, 10),
                 ).pack(side="right")
        self._folder_match_card.pack(fill="x", padx=28, pady=(6, 0), before=self._run_sec)

    def _build_picker_cards(self, matches):
        """Replace picker inner content with card-style folder items."""
        for w in self._picker_inner.winfo_children():
            w.destroy()
        for idx, (fid, fpath) in enumerate(matches):
            short = fpath.rstrip("/").split("/")[-1]
            if idx > 0:
                tk.Frame(self._picker_inner, bg=BORDER_STR, height=1).pack(fill="x")
            card  = tk.Frame(self._picker_inner, bg=SURFACE, cursor="hand2")
            card.pack(fill="x")
            inner = tk.Frame(card, bg=SURFACE)
            inner.pack(fill="x", padx=12, pady=(8, 8))
            name_l = tk.Label(inner, text=short, bg=SURFACE, fg=TEXT,
                               font=(FONT, 12, "bold"), anchor="w")
            name_l.pack(fill="x")
            path_l = tk.Label(inner, text=fpath, bg=SURFACE, fg=TEXT_FAINT,
                               font=(FONT_MONO, 10), anchor="w", wraplength=480)
            path_l.pack(fill="x", pady=(2, 0))

            def _select(e=None, fid=fid, fpath=fpath, short=short):
                self._selected_folder_id   = fid
                self._selected_folder_path = fpath
                self._folder_result_lbl.config(text="")
                self._picker_frame.pack_forget()
                self._show_folder_match_card(fid, fpath, short)
                self._set_badge(self._b2, "2", complete=True)
                self._update_run_btn()

            all_widgets = [card, inner, name_l, path_l]

            def _enter(e, ws=all_widgets):
                for w in ws:
                    w.config(bg=SURFACE_DIM)
            def _leave(e, ws=all_widgets):
                for w in ws:
                    w.config(bg=SURFACE)

            for w in all_widgets:
                w.bind("<Button-1>", _select)
                w.bind("<Enter>",    _enter)
                w.bind("<Leave>",    _leave)

    # ── Run (threaded) ────────────────────────────────────────────────────────

    def _run(self):
        if not self._current_filenames or not self._selected_folder_id:
            return

        self._show_panel("card")
        self._phase_lbl.config(text="Backing up catalog…")
        self._phase_sub.config(
            text="Writing a timestamped .lrcat backup before any changes.")
        self._pct_lbl.config(text="0%")
        self._draw_prog(0)

        filenames = list(self._current_filenames)
        folder_id = self._selected_folder_id

        def worker():
            try:
                # Backup
                self.after(0, lambda: self._set_phase("backup", 0))
                backup_catalog()
                self.after(0, lambda: self._set_phase("backup", 1.0))

                # Flag
                conn    = sqlite3.connect(CATALOG_PATH)
                cursor  = conn.cursor()
                matched, not_found = [], []
                total = len(filenames)

                for i, basename in enumerate(filenames):
                    cursor.execute("""
                        SELECT ai.id_local
                        FROM Adobe_images ai
                        JOIN AgLibraryFile alf ON ai.rootFile = alf.id_local
                        WHERE alf.baseName = ? AND alf.folder = ?
                    """, (basename, folder_id))
                    rows = cursor.fetchall()
                    if rows:
                        for (img_id,) in rows:
                            cursor.execute(
                                "UPDATE Adobe_images SET pick = 1 WHERE id_local = ?",
                                (img_id,))
                        matched.append(basename)
                    else:
                        not_found.append(basename)

                    pct  = (i + 1) / total
                    done = i + 1
                    self.after(0, lambda p=pct, d=done, t=total:
                               self._set_phase("flag", p, d, t))

                conn.commit()
                conn.close()
                self.after(0, lambda: self._finish_run(matched, not_found))

            except Exception as e:
                self.after(0, lambda: self._handle_error(str(e)))

        threading.Thread(target=worker, daemon=True).start()

    def _set_phase(self, phase, pct, done=0, total=0):
        pct_str = f"{int(pct * 100)}%"
        if phase == "backup":
            self._phase_lbl.config(text="Backing up catalog…")
            self._phase_sub.config(
                text="Writing a timestamped .lrcat backup before any changes.")
        elif phase == "flag":
            self._phase_lbl.config(text=f"Flagging picks · {done} of {total}")
            self._phase_sub.config(
                text="Setting pick=1 in Adobe_images for each match.")
        self._pct_lbl.config(text=pct_str)
        color = ACCENT if phase == "backup" else SUCCESS
        self._draw_prog(pct, color)

    def _finish_run(self, matched, not_found):
        # ── Persist to history ────────────────────────────────────────────────
        ts = time.time()
        entry = {
            "id":         f"run-{int(ts * 1000)}",
            "timestamp":  ts,
            "folder": {
                "id":   self._selected_folder_id,
                "path": self._selected_folder_path or "",
            },
            "matched":    matched,
            "notFound":   not_found,
            "backupName": backup_name_from_ts(ts),
        }
        self._history.insert(0, entry)
        self._history = self._history[:50]
        save_history(self._history)
        self._update_hist_badge()

        self._res_matched   = matched
        self._res_not_found = not_found

        total       = len(matched) + len(not_found)
        none_match  = len(matched) == 0
        all_match   = len(not_found) == 0

        # Icon
        ic = self._res_icon
        ic.delete("all")
        if none_match:
            ic.create_oval(0, 0, 24, 24, fill=ERROR_DIM, outline="")
            ic.create_line(7, 7, 17, 17, fill=ERROR, width=1.8, capstyle="round")
            ic.create_line(17, 7, 7, 17, fill=ERROR, width=1.8, capstyle="round")
        else:
            ic.create_oval(0, 0, 24, 24, fill=SUCCESS_DIM, outline="")
            ic.create_line(6, 13, 10, 17, fill=SUCCESS, width=1.8, capstyle="round")
            ic.create_line(10, 17, 18, 8, fill=SUCCESS, width=1.8, capstyle="round")

        # Title
        if none_match:
            title = "No photos flagged"
        elif all_match:
            n = len(matched)
            title = f"{n} {'photo' if n == 1 else 'photos'} flagged"
        else:
            title = f"{len(matched)} of {total} flagged"

        self._res_title.config(text=title)
        self._res_sub.config(
            text=("None of the pasted filenames matched files in this folder."
                  if none_match
                  else "Open Lightroom and filter by Pick to verify."))

        self._tab_m.config(text=f"● Matched  {len(matched)}")
        self._tab_n.config(text=f"● Not found  {len(not_found)}")

        self._cur_tab = "matched"
        self._tab_m.config(bg=SURFACE_DIM, fg=TEXT)
        self._tab_n.config(bg=SURFACE, fg=TEXT_DIM)
        self._fill_chips(matched, "m")

        self._show_panel("result")

    def _handle_error(self, msg):
        self._err_msg.config(text=msg)
        self._show_panel("error")

    # ── Result tabs & chips ───────────────────────────────────────────────────

    def _set_tab(self, tab):
        self._cur_tab = tab
        if tab == "matched":
            self._tab_m.config(bg=SURFACE_DIM, fg=TEXT)
            self._tab_n.config(bg=SURFACE,     fg=TEXT_DIM)
            self._fill_chips(self._res_matched, "m")
        else:
            self._tab_m.config(bg=SURFACE,     fg=TEXT_DIM)
            self._tab_n.config(bg=SURFACE_DIM, fg=TEXT)
            self._fill_chips(self._res_not_found, "n")
        self.after(60, self._draw_res_bg)

    def _fill_chips(self, names, tag):
        t = self._chip_txt
        t.config(state="normal")
        t.delete("1.0", "end")
        if not names:
            msg = ("Clean run — every filename was found."
                   if tag == "n"
                   else "No matches in this run.")
            t.insert("end", msg)
            t.config(fg=TEXT_FAINT)
        else:
            t.config(fg=TEXT)
            for name in names:
                t.insert("end", f" {name} ", tag)
                t.insert("end", " ", "sp")
        t.config(state="disabled")

    # ── Reset ─────────────────────────────────────────────────────────────────

    def _reset(self):
        self.paste_box.config(state="normal")
        self.paste_box.delete("1.0", "end")
        self.paste_box.insert("1.0", _PASTE_PH)
        self.paste_box.config(fg=TEXT_FAINT)
        self.paste_box.edit_modified(False)

        self.folder_entry.delete(0, "end")
        self.folder_entry.insert(0, _FOLDER_PH)
        self.folder_entry.config(fg=TEXT_FAINT)

        self._selected_folder_id   = None
        self._selected_folder_path = None
        self._current_filenames    = []
        self._folder_result_lbl.config(text="")
        self._folder_match_card.pack_forget()
        for w in self._picker_inner.winfo_children():
            w.destroy()
        self._picker_frame.pack_forget()

        self._set_badge(self._b1, "1", complete=False)
        self._set_badge(self._b2, "2", complete=False)
        self._count_chip.config(text="empty", bg=SURFACE_DIM, fg=TEXT_FAINT)
        self._show_panel("btn")
        self._update_run_btn()

    # ── Toast ─────────────────────────────────────────────────────────────────

    def _show_toast(self, msg, duration=2800):
        if self._toast_after_id:
            self.after_cancel(self._toast_after_id)
        if hasattr(self, "_toast_w") and self._toast_w:
            try:
                self._toast_w.destroy()
            except Exception:
                pass

        self._toast_w = tk.Label(
            self, text=msg,
            bg="#323234", fg=TEXT,
            font=(FONT, 11, "bold"),
            padx=14, pady=9,
        )
        self.update_idletasks()
        tw = self._toast_w.winfo_reqwidth()
        ww = self.winfo_width()
        self._toast_w.place(x=(ww - tw) // 2, y=self.winfo_height() - 70)

        def _dismiss():
            try:
                self._toast_w.destroy()
                self._toast_w = None
            except Exception:
                pass

        self._toast_after_id = self.after(duration, _dismiss)


    # ── History badge ─────────────────────────────────────────────────────────

    def _update_hist_badge(self):
        n = len(self._history)
        self._hist_btn.set_text("⏱" if n == 0 else f"⏱ {n}")

    # ── History panel ─────────────────────────────────────────────────────────

    def _build_history_panel(self):
        """Build the history drawer (not packed until _toggle_history)."""
        self._hist_panel = tk.Frame(self, bg=BG)

        # Sub-header
        hdr = tk.Frame(self._hist_panel, bg=BG)
        hdr.pack(fill="x", padx=28, pady=(14, 12))

        RoundedButton(
            hdr, "‹ Back", self._hide_history_panel,
            height=24, width=60, fill=BG, hover=SURFACE_HI, fg=TEXT_DIM,
            font_spec=(FONT, 12),
        ).pack(side="left")

        tk.Label(hdr, text="History",
                 bg=BG, fg=TEXT, font=(FONT, 17, "bold"),
                 ).pack(side="left", padx=(10, 0))

        self._hist_count_lbl = tk.Label(hdr, bg=BG, fg=TEXT_FAINT,
                                         font=(FONT_MONO, 11))
        self._hist_count_lbl.pack(side="left", padx=(8, 0))

        self._hist_clear_lbl = tk.Label(hdr, text="Clear all",
                                         bg=BG, fg=TEXT_DIM,
                                         font=(FONT, 11), cursor="hand2")
        self._hist_clear_lbl.pack(side="right")
        self._hist_clear_lbl.bind("<Button-1>",  lambda e: self._clear_history())
        self._hist_clear_lbl.bind("<Enter>",     lambda e: self._hist_clear_lbl.config(fg=ERROR))
        self._hist_clear_lbl.bind("<Leave>",     lambda e: self._hist_clear_lbl.config(fg=TEXT_DIM))

        tk.Frame(self._hist_panel, bg=BORDER, height=1).pack(fill="x")

        # Scrollable list
        outer = tk.Frame(self._hist_panel, bg=BG)
        outer.pack(fill="both", expand=True)

        self._hist_sc = tk.Canvas(outer, bg=BG, highlightthickness=0, bd=0)
        self._hist_sc.pack(fill="both", expand=True)

        self._hist_cf = tk.Frame(self._hist_sc, bg=BG)
        self._hist_cw = self._hist_sc.create_window(0, 0, window=self._hist_cf, anchor="nw")

        self._hist_cf.bind(
            "<Configure>",
            lambda e: self._hist_sc.configure(scrollregion=self._hist_sc.bbox("all")),
        )
        self._hist_sc.bind(
            "<Configure>",
            lambda e: self._hist_sc.itemconfig(self._hist_cw, width=e.width),
        )

    def _toggle_history(self):
        if self._hist_open:
            self._hide_history_panel()
        else:
            self._show_history_panel()

    def _show_history_panel(self):
        self._hist_open = True
        self._scroll_outer.pack_forget()
        self._hist_panel.pack(fill="both", expand=True)
        # Route mousewheel to history canvas
        self.bind_all("<MouseWheel>",
                      lambda e: self._hist_sc.yview_scroll(int(-1 * e.delta / 120), "units"))
        self._rebuild_history_list()

    def _hide_history_panel(self):
        self._hist_open = False
        self._hist_panel.pack_forget()
        self._scroll_outer.pack(fill="both", expand=True)
        # Restore mousewheel to main canvas
        self.bind_all("<MouseWheel>",
                      lambda e: self._sc.yview_scroll(int(-1 * e.delta / 120), "units"))

    def _rebuild_history_list(self):
        """Destroy and rebuild every row widget from self._history."""
        # Remember scroll position
        yview = self._hist_sc.yview()

        for w in self._hist_cf.winfo_children():
            w.destroy()

        n = len(self._history)
        self._hist_count_lbl.config(text=f"{n} {'run' if n == 1 else 'runs'}")

        if n == 0:
            self._hist_clear_lbl.pack_forget()
            self._build_empty_history()
        else:
            self._hist_clear_lbl.pack(side="right")
            for entry in self._history:
                self._build_history_row(entry)

        # Restore scroll position after layout
        self.after(40, lambda: self._hist_sc.yview_moveto(yview[0]))

    def _build_empty_history(self):
        f = tk.Frame(self._hist_cf, bg=BG)
        f.pack(fill="x", padx=28, pady=60)

        # Clock icon
        ic = tk.Canvas(f, width=44, height=44, bg=BG, highlightthickness=0)
        ic.pack()
        _rr(ic, 0, 0, 44, 44, 12, SURFACE_DIM)
        ic.create_oval(11, 11, 33, 33, outline=TEXT_FAINT, width=1.4, fill="")
        ic.create_line(22, 22, 22, 14, fill=TEXT_FAINT, width=1.4, capstyle="round")
        ic.create_line(22, 22, 28, 26, fill=TEXT_FAINT, width=1.4, capstyle="round")

        tk.Label(f, text="No runs yet",
                 bg=BG, fg=TEXT, font=(FONT, 13, "bold")).pack(pady=(12, 4))
        tk.Label(f,
                 text="Once you flag picks, each run is logged here\n"
                      "with the folder, filenames, and a backup link.",
                 bg=BG, fg=TEXT_DIM, font=(FONT, 11),
                 justify="center", wraplength=280).pack()

    def _build_history_row(self, entry):
        """Build one history row card (collapsed or expanded)."""
        run_id    = entry["id"]
        matched   = entry.get("matched",   [])
        not_found = entry.get("notFound",  [])
        folder    = entry.get("folder",    {})
        ts        = entry.get("timestamp", 0)
        backup_nm = entry.get("backupName", "")

        total      = len(matched) + len(not_found)
        none_match = len(matched) == 0
        all_match  = len(not_found) == 0
        ratio      = len(matched) / max(total, 1)
        ring_col   = ERROR if none_match else (SUCCESS if all_match else WARNING)
        dot_bg     = ERROR_DIM if none_match else SUCCESS_DIM

        folder_path = folder.get("path", "")
        folder_name = folder_path.rstrip("/").split("/")[-1] if folder_path else ""
        expanded    = run_id in self._hist_expanded
        chip_tab    = self._hist_chip_tabs.get(run_id, "matched")

        # ── Card shell ────────────────────────────────────────────────────────
        card = tk.Frame(self._hist_cf, bg=SURFACE,
                        highlightthickness=1, highlightbackground=BORDER_STR)
        card.pack(fill="x", padx=28, pady=(0, 8))

        # ── Collapsed header ──────────────────────────────────────────────────
        hdr = tk.Frame(card, bg=SURFACE, cursor="hand2")
        hdr.pack(fill="x", padx=14, pady=(10, 10))
        for w in (hdr,):
            w.bind("<Button-1>", lambda e, rid=run_id: self._toggle_row(rid))

        # Status dot
        dot = tk.Canvas(hdr, width=28, height=28, bg=SURFACE, highlightthickness=0)
        dot.pack(side="left", padx=(0, 10))
        dot.create_oval(1, 1, 27, 27, fill=dot_bg, outline="")
        if none_match:
            dot.create_line(9,  9, 19, 19, fill=ring_col, width=1.8, capstyle="round")
            dot.create_line(19, 9,  9, 19, fill=ring_col, width=1.8, capstyle="round")
        else:
            dot.create_line( 7, 14, 11, 18, fill=ring_col, width=1.8, capstyle="round")
            dot.create_line(11, 18, 21,  8, fill=ring_col, width=1.8, capstyle="round")
        dot.bind("<Button-1>", lambda e, rid=run_id: self._toggle_row(rid))

        # Meta column
        meta = tk.Frame(hdr, bg=SURFACE)
        meta.pack(side="left", fill="x", expand=True)

        fl = tk.Label(meta, text=folder_name, bg=SURFACE, fg=TEXT,
                      font=(FONT, 12, "bold"), anchor="w")
        fl.pack(fill="x")
        fl.bind("<Button-1>", lambda e, rid=run_id: self._toggle_row(rid))

        sub_text = f"{fmt_relative(ts)}  ·  {len(matched)} of {total} flagged"
        sub_col  = ERROR if none_match else TEXT_DIM
        sl = tk.Label(meta, text=sub_text, bg=SURFACE, fg=sub_col,
                      font=(FONT, 10), anchor="w")
        sl.pack(fill="x", pady=(2, 0))
        sl.bind("<Button-1>", lambda e, rid=run_id: self._toggle_row(rid))

        # Mini progress bar (3 px via Canvas)
        pb = tk.Canvas(meta, height=3, bg=SURFACE_DIM, highlightthickness=0)
        pb.pack(fill="x", pady=(6, 0))
        pb.bind("<Button-1>", lambda e, rid=run_id: self._toggle_row(rid))

        def _draw_pb(e=None, _pb=pb, _ratio=ratio, _col=ring_col):
            w = _pb.winfo_width()
            if w < 2:
                return
            _pb.delete("all")
            if _ratio > 0:
                _pb.create_rectangle(0, 0, int(w * _ratio), 3, fill=_col, outline="")
        pb.bind("<Configure>", _draw_pb)

        # Chevron
        chev_txt = "›" if not expanded else "⌄"
        chev = tk.Label(hdr, text=chev_txt, bg=SURFACE, fg=TEXT_FAINT,
                        font=(FONT, 16))
        chev.pack(side="right", anchor="center")
        chev.bind("<Button-1>", lambda e, rid=run_id: self._toggle_row(rid))

        if not expanded:
            return

        # ── Expanded body ─────────────────────────────────────────────────────
        tk.Frame(card, bg=BORDER, height=1).pack(fill="x")

        body = tk.Frame(card, bg=SURFACE)
        body.pack(fill="x", padx=14, pady=(10, 12))

        # Full path
        tk.Label(body, text=folder_path, bg=SURFACE, fg=TEXT_FAINT,
                 font=(FONT_MONO, 10), anchor="w",
                 wraplength=460, justify="left").pack(fill="x", pady=(0, 8))

        # Chip tabs
        tabs_row = tk.Frame(body, bg=SURFACE)
        tabs_row.pack(fill="x", pady=(0, 6))

        def _make_tab(label, key, count, color):
            is_active = (chip_tab == key)
            bg = SURFACE_DIM if is_active else SURFACE
            fg = TEXT if is_active else TEXT_DIM
            t = tk.Label(tabs_row,
                         text=f"● {label}  {count}",
                         bg=bg, fg=fg, font=(FONT, 11),
                         padx=8, pady=4, cursor="hand2")
            t.pack(side="left", padx=(0, 4))
            t.bind("<Button-1>",
                   lambda e, k=key, rid=run_id: self._set_hist_tab(rid, k))

        _make_tab("Matched",   "matched",  len(matched),   SUCCESS)
        _make_tab("Not found", "notfound", len(not_found), ERROR)

        # Chips
        chip_names = matched if chip_tab == "matched" else not_found
        chip_tag   = "m"    if chip_tab == "matched" else "n"

        ct = tk.Text(body, bg=SURFACE, bd=0, relief="flat",
                     font=(FONT_MONO, 10), padx=0, pady=6,
                     state="disabled", cursor="arrow",
                     highlightthickness=0, height=4, wrap="word")
        ct.pack(fill="x")
        ct.tag_config("m",  background=SUCCESS_DIM, foreground=SUCCESS)
        ct.tag_config("n",  background=ERROR_DIM,   foreground=ERROR)
        ct.tag_config("sp", background=SURFACE,     foreground=SURFACE)
        ct.config(state="normal")
        ct.delete("1.0", "end")
        if not chip_names:
            msg = ("No misses — clean run."
                   if chip_tab == "matched" else "No matches.")
            ct.insert("end", msg)
            ct.config(fg=TEXT_FAINT)
        else:
            ct.config(fg=TEXT)
            for name in chip_names:
                ct.insert("end", f" {name} ", chip_tag)
                ct.insert("end", " ", "sp")
        ct.config(state="disabled")

        # Backup + actions
        tk.Frame(body, bg=BORDER, height=1).pack(fill="x", pady=(10, 8))

        act = tk.Frame(body, bg=SURFACE)
        act.pack(fill="x")

        bk = tk.Frame(act, bg=SURFACE)
        bk.pack(side="left", fill="x", expand=True)
        tk.Label(bk, text="CATALOG BACKUP", bg=SURFACE, fg=TEXT_FAINT,
                 font=(FONT, 9), anchor="w").pack(anchor="w")
        tk.Label(bk, text=backup_nm, bg=SURFACE, fg=TEXT_DIM,
                 font=(FONT_MONO, 9), anchor="w").pack(anchor="w", pady=(2, 0))

        RoundedButton(act, "Restore",
                      lambda _e=entry: self._restore_run(_e),
                      height=28, fill=SURFACE, hover=SURFACE_HI, fg=TEXT_DIM,
                      font_spec=(FONT, 11),
                      ).pack(side="right", padx=(4, 0))
        RoundedButton(act, "Reuse list",
                      lambda _e=entry: self._reuse_run(_e),
                      height=28, fill=ACCENT, hover=ACCENT, fg="#fff",
                      font_spec=(FONT, 11),
                      ).pack(side="right")

    # ── History row interactions ───────────────────────────────────────────────

    def _toggle_row(self, run_id):
        if run_id in self._hist_expanded:
            self._hist_expanded.discard(run_id)
        else:
            self._hist_expanded.add(run_id)
        self._rebuild_history_list()

    def _set_hist_tab(self, run_id, tab):
        self._hist_chip_tabs[run_id] = tab
        self._rebuild_history_list()

    def _clear_history(self):
        from tkinter import messagebox as _mb
        if _mb.askyesno("Clear History",
                        "Clear all run history? This cannot be undone."):
            self._history.clear()
            self._hist_expanded.clear()
            self._hist_chip_tabs.clear()
            save_history(self._history)
            self._update_hist_badge()
            self._rebuild_history_list()

    def _reuse_run(self, entry):
        """Load a past run's filenames + folder into the main UI."""
        folder    = entry.get("folder", {})
        matched   = entry.get("matched",  [])
        not_found = entry.get("notFound", [])
        all_names = matched + not_found

        folder_path = folder.get("path", "")
        folder_name = folder_path.rstrip("/").split("/")[-1] if folder_path else ""
        folder_id   = folder.get("id")

        # Populate paste box
        paste_text = "\n".join(n + ".jpg" for n in all_names)
        self.paste_box.config(state="normal", fg=TEXT)
        self.paste_box.delete("1.0", "end")
        self.paste_box.insert("1.0", paste_text)
        self.paste_box.edit_modified(False)
        self._on_paste_modified()

        # Restore folder selection
        if folder_id and folder_path:
            self.folder_entry.config(fg=TEXT)
            self.folder_entry.delete(0, "end")
            self.folder_entry.insert(0, folder_name)
            self._selected_folder_id   = folder_id
            self._selected_folder_path = folder_path
            self._folder_result_lbl.config(text="")
            self._folder_match_card.pack_forget()
            self._show_folder_match_card(folder_id, folder_path, folder_name)
            self._set_badge(self._b2, "2", complete=True)

        self._update_run_btn()
        self._hide_history_panel()
        self._show_toast(
            f"Loaded {len(all_names)} filenames from {folder_name}")

    def _restore_run(self, entry):
        backup = entry.get("backupName", "backup file")
        self._show_toast(f"Backup: {backup}")


if __name__ == "__main__":
    app = App()
    app.mainloop()
