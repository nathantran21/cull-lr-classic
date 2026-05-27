#!/usr/bin/env python3
"""
LR Pick Flagger — pywebview edition
-------------------------------------
Wraps the HTML/JS prototype UI with a real Python backend.
Run:   python3 LR_Pick_Flagger_webview.py
Debug: python3 LR_Pick_Flagger_webview.py --debug
Build: bash build_webview.sh
"""

import webview
import sqlite3
import os
import re
import sys
import shutil
import threading
import json
import time
from datetime import datetime
from pathlib import Path

# ── Catalog path ──────────────────────────────────────────────────────────────
CATALOG = (
    "/Users/natha/Pictures/Lightroom Catalog-v13-v13-3/"
    "Old Lightroom Catalogs/"
    "Lightroom Catalog-v13-v13-3_2025-10-29 0911/"
    "Lightroom Catalog-v13-v13-3.lrcat"
)

HISTORY_FILE = Path.home() / ".lr_pick_flagger_history.json"


# ── Python ↔ JS API ───────────────────────────────────────────────────────────

class Api:
    """All public methods are exposed as window.pywebview.api.<name>() in JS."""

    def __init__(self):
        self._lock = threading.Lock()
        self._progress = None
        self.window = None

    def window_close(self):
        # Hide the window; app stays alive in the Dock until the user quits.
        if self.window:
            self.window.hide()

    def window_minimize(self):
        if self.window:
            self.window.minimize()

    def window_toggle_fullscreen(self):
        if self.window:
            self.window.toggle_fullscreen()

    # ── Folder search ─────────────────────────────────────────────────────────

    def search_folders(self, term):
        """Return JSON array of {id, path} whose path contains term (case-insensitive)."""
        try:
            conn = sqlite3.connect(CATALOG)
            cur = conn.cursor()
            cur.execute("""
                SELECT f.id_local, r.absolutePath || f.pathFromRoot
                FROM AgLibraryFolder f
                JOIN AgLibraryRootFolder r ON f.rootFolder = r.id_local
            """)
            rows = cur.fetchall()
            conn.close()
            q = term.strip().lower()
            matches = [{"id": r[0], "path": r[1]}
                       for r in rows if q and q in (r[1] or "").lower()]
            return json.dumps(matches)
        except Exception as e:
            return json.dumps({"error": str(e)})

    # ── Flag picks ────────────────────────────────────────────────────────────

    def start_flag_picks(self, filenames_json, folder_id):
        """
        Start backup + flag in a background thread.
        JS polls get_progress() at ~60ms to track status.
        """
        filenames = json.loads(filenames_json)
        fid = int(folder_id)
        with self._lock:
            self._progress = {
                "phase": "backup", "pct": 0,
                "done": 0, "total": len(filenames),
                "done_final": False, "error": None,
            }
        threading.Thread(target=self._run_worker, args=(filenames, fid), daemon=True).start()
        return "ok"

    def _run_worker(self, filenames, folder_id):
        try:
            # ── Backup ────────────────────────────────────────────────────────
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = CATALOG.replace(".lrcat", f"_backup_{ts}.lrcat")
            shutil.copy2(CATALOG, backup_path)
            with self._lock:
                self._progress.update({"phase": "backup", "pct": 1.0})
            time.sleep(0.12)  # brief pause so the UI can show 100% backup

            # ── Flag picks ────────────────────────────────────────────────────
            conn = sqlite3.connect(CATALOG)
            cur = conn.cursor()
            matched, not_found = [], []
            total = len(filenames)

            for i, basename in enumerate(filenames):
                cur.execute("""
                    SELECT ai.id_local FROM Adobe_images ai
                    JOIN AgLibraryFile alf ON ai.rootFile = alf.id_local
                    WHERE alf.baseName = ? AND alf.folder = ?
                """, (basename, folder_id))
                rows = cur.fetchall()
                if rows:
                    for (img_id,) in rows:
                        cur.execute(
                            "UPDATE Adobe_images SET pick = 1 WHERE id_local = ?",
                            (img_id,))
                    matched.append(basename)
                else:
                    not_found.append(basename)

                with self._lock:
                    self._progress.update({
                        "phase": "flag",
                        "pct": (i + 1) / total,
                        "done": i + 1,
                        "total": total,
                    })

            conn.commit()
            conn.close()

            with self._lock:
                self._progress.update({
                    "done_final": True,
                    "matched": matched,
                    "notFound": not_found,
                    "backupName": os.path.basename(backup_path),
                })

        except Exception as e:
            with self._lock:
                self._progress = {"done_final": True, "error": str(e), "phase": "error"}

    def get_progress(self):
        """Return current progress state as JSON. JS polls this at ~60ms."""
        with self._lock:
            return json.dumps(self._progress or {})

    # ── History persistence ───────────────────────────────────────────────────

    def save_history(self, history_json):
        """
        Persist history to ~/.lr_pick_flagger_history.json.
        Filters out mock seed entries (id: "seed-*") — only real runs persist.
        """
        try:
            data = json.loads(history_json)
            if isinstance(data, list):
                real = [r for r in data
                        if isinstance(r, dict)
                        and not str(r.get("id", "")).startswith("seed-")]
                HISTORY_FILE.write_text(json.dumps(real[:50], indent=2))
        except Exception:
            pass
        return "ok"


# ── HTML + bridge injection ───────────────────────────────────────────────────

# This script is injected right after <body> in the standalone HTML.
# window event listeners survive the bundler's document.documentElement.replaceWith(),
# so the pywebviewready handler fires correctly after the new page is loaded.
_BRIDGE = r"""
<script id="__pywebview_bridge">
(function () {
  // Always seed localStorage with Python's history before React renders.
  // This runs synchronously before DOMContentLoaded (the bundler), so
  // loadHistory() will find our data when React mounts.
  var __hist = /*HISTORY_PLACEHOLDER*/[];
  try {
    localStorage.setItem('lr-pick-flagger:history', JSON.stringify(__hist));
  } catch (e) {}

  // Override mock functions once pywebview injects its API.
  // window listeners survive the bundler's replaceWith, so this fires correctly.
  window.addEventListener('pywebviewready', function () {

    // ── Real folder search ──────────────────────────────────────────────────
    window.mockSearchFolders = async function (term) {
      var raw = await window.pywebview.api.search_folders(term);
      var result = JSON.parse(raw);
      if (result && result.error) throw new Error(result.error);
      return Array.isArray(result) ? result : [];
    };

    // ── Real flag picks (polling pattern) ───────────────────────────────────
    window.mockFlagPicks = async function (filenames, folderId, _scenario, onProgress) {
      await window.pywebview.api.start_flag_picks(
        JSON.stringify(filenames), String(folderId)
      );
      return new Promise(function (resolve, reject) {
        var poll = setInterval(async function () {
          try {
            var raw = await window.pywebview.api.get_progress();
            var s = JSON.parse(raw);
            if (!s || !s.phase) return;
            if (!s.done_final) {
              onProgress && onProgress({
                phase: s.phase, pct: s.pct,
                done: s.done || 0, total: s.total || filenames.length,
              });
            } else {
              clearInterval(poll);
              if (s.error) reject(new Error(s.error));
              else resolve({ matched: s.matched || [], notFound: s.notFound || [] });
            }
          } catch (e) { clearInterval(poll); reject(e); }
        }, 60);
      });
    };

    // ── Fill window — remove outer padding so card fills the frameless window ─
    // React centers the card in a flex container with padding:40, creating dark
    // borders. Use !important to override inline styles so the card fills 100%.
    var __fill = document.createElement('style');
    __fill.textContent =
      '#root > div:first-child { padding: 0 !important; display: block !important; }' +
      '#root > div:first-child > div:first-of-type { width: 100% !important; height: 100vh !important; border-radius: 0 !important; box-shadow: none !important; }';
    document.head && document.head.appendChild(__fill);

    // ── Wire HTML traffic lights to native window actions ───────────────────
    // React renders dot() as div with inline style background: #ff5f57 etc.
    // Poll every 200ms (up to 15s) because React may still be loading when
    // pywebviewready fires. getComputedStyle().backgroundColor is reliable.
    var __dotAttempts = 0;
    var __dotPoll = setInterval(function () {
      __dotAttempts++;
      var wired = 0;
      document.querySelectorAll('[style]').forEach(function (el) {
        if (el.__dotWired) { wired++; return; }
        var bg = window.getComputedStyle(el).backgroundColor;
        if (bg === 'rgb(255, 95, 87)') {
          el.__dotWired = true;
          el.style.cursor = 'pointer';
          el.style.webkitAppRegion = 'no-drag';
          el.addEventListener('click', function (e) {
            e.stopPropagation();
            window.pywebview.api.window_close();
          });
          wired++;
        } else if (bg === 'rgb(254, 188, 46)') {
          el.__dotWired = true;
          el.style.cursor = 'pointer';
          el.style.webkitAppRegion = 'no-drag';
          el.addEventListener('click', function (e) {
            e.stopPropagation();
            window.pywebview.api.window_minimize();
          });
          wired++;
        } else if (bg === 'rgb(40, 200, 64)') {
          el.__dotWired = true;
          el.style.cursor = 'pointer';
          el.style.webkitAppRegion = 'no-drag';
          el.addEventListener('click', function (e) {
            e.stopPropagation();
            window.pywebview.api.window_toggle_fullscreen();
          });
          wired++;
        }
      });
      if (wired >= 3 || __dotAttempts > 75) clearInterval(__dotPoll);
    }, 200);

    // ── Sync history writes to Python ───────────────────────────────────────
    // Intercept localStorage so every history change is mirrored to disk.
    var _origSet = localStorage.setItem.bind(localStorage);
    localStorage.setItem = function (key, value) {
      _origSet(key, value);
      if (key === 'lr-pick-flagger:history') {
        try {
          var arr = JSON.parse(value);
          // Only sync on real runs or when the user clears history.
          var hasReal = arr.some(function (r) {
            return r && r.id && String(r.id).indexOf('run-') === 0;
          });
          if (arr.length === 0 || hasReal)
            window.pywebview.api.save_history(value).catch(function () {});
        } catch (e) {}
      }
    };
  });
}());
</script>
"""


def _resources_dir():
    """Return the directory containing LR Pick Flagger (standalone).html."""
    if getattr(sys, 'frozen', False):
        # py2app bundle: executable is Contents/MacOS/, resources in Contents/Resources/
        return os.path.normpath(
            os.path.join(os.path.dirname(sys.executable), '..', 'Resources'))
    return os.path.dirname(os.path.abspath(__file__))


def _load_history():
    """Read real history from disk; return list (may be empty)."""
    try:
        if HISTORY_FILE.exists():
            data = json.loads(HISTORY_FILE.read_text())
            if isinstance(data, list):
                return [r for r in data
                        if isinstance(r, dict)
                        and not str(r.get('id', '')).startswith('seed-')][:50]
    except Exception:
        pass
    return []


def _build_html():
    """Read the standalone HTML, inject the pywebview bridge, and save to a stable temp path."""
    html_src = os.path.join(_resources_dir(), 'LR Pick Flagger (standalone).html')
    with open(html_src, 'r', encoding='utf-8') as f:
        html = f.read()

    # Build bridge with history seed
    history = _load_history()
    bridge = _BRIDGE.replace(
        '/*HISTORY_PLACEHOLDER*/[]',
        json.dumps(history)
    )

    # Inject right after <body> so it runs before the bundler's DOMContentLoaded handler
    html = html.replace('<body>', '<body>\n' + bridge, 1)

    # Write to a stable path so file:// URL keeps consistent localStorage origin
    dest_dir = Path.home() / '.lr_pick_flagger'
    dest_dir.mkdir(exist_ok=True)
    dest = dest_dir / 'app.html'
    dest.write_text(html, encoding='utf-8')
    return str(dest)


def _setup_dock_reopen(api):
    """Patch the NSApp delegate so clicking the Dock icon re-shows the window."""
    try:
        from AppKit import NSApplication
        app = NSApplication.sharedApplication()
        delegate = app.delegate()
        if delegate is None:
            return

        def applicationShouldHandleReopen_hasVisibleWindows_(self, application, hasVisibleWindows):
            if not hasVisibleWindows and api.window:
                api.window.show()
            return True

        delegate.__class__.applicationShouldHandleReopen_hasVisibleWindows_ = \
            applicationShouldHandleReopen_hasVisibleWindows_
    except Exception:
        pass


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    debug = '--debug' in sys.argv
    html_path = _build_html()
    api = Api()

    window = webview.create_window(
        title='LR Pick Flagger',
        url=f'file://{html_path}',
        js_api=api,
        width=640,
        height=880,
        resizable=True,
        min_size=(580, 760),
        background_color='#0e0e10',
        frameless=True,
        easy_drag=True,
    )
    api.window = window

    # Patch the Dock handler after pywebview has initialised its NSApp delegate.
    def _patch():
        time.sleep(1)
        _setup_dock_reopen(api)
    threading.Thread(target=_patch, daemon=True).start()

    webview.start(debug=debug)


if __name__ == '__main__':
    main()
