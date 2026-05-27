#!/usr/bin/env python3
"""
flag_picks.py
-------------
Flags photos as Picks in a Lightroom Classic catalog based on a
filename list exported from Pixieset's Favorite Activity (Lightroom Copy List).

Scopes matches to a specific shoot folder to avoid duplicate filename conflicts.
Strips Pixieset-appended suffixes (e.g. _Tran_Nate) before matching against LR.

IMPORTANT: Close Lightroom Classic before running this script.
"""

import sqlite3
import os
import sys
import shutil
import re
from datetime import datetime


def get_input(prompt, must_exist=False):
    while True:
        value = input(prompt).strip().strip('"').strip("'")
        if must_exist and not os.path.exists(value):
            print(f"  ✗ File not found: {value}. Try again.\n")
        else:
            return value


def strip_suffix(basename):
    """
    Strips the photographer suffix Pixieset appends to exported filenames.
    e.g. IMG_7846_Tran_Nate -> IMG_7846
    Removes the last two _Word_Word segments if they look like a name.
    """
    # Match pattern: IMG_XXXX_Word_Word (two trailing _Capitalized segments)
    result = re.sub(r'(_[A-Za-z]+){2}$', '', basename)
    return result


def load_filenames(filepath):
    """Load filenames from a .csv or .txt file. Handles Pixieset CSV export format."""
    filenames = set()
    with open(filepath, "r", encoding="utf-8-sig") as f:
        for line in f:
            name = line.strip().strip('"').strip(",").strip()
            if not name or name.lower() in ("filename", "file name", "name"):
                continue
            # Strip extension
            root, _ = os.path.splitext(name)
            if not root:
                root = name
            # Strip photographer suffix
            cleaned = strip_suffix(root)
            filenames.add(cleaned)
    return filenames


def backup_catalog(catalog_path):
    """Create a timestamped backup of the .lrcat file before modifying."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = catalog_path.replace(".lrcat", f"_backup_{timestamp}.lrcat")
    shutil.copy2(catalog_path, backup_path)
    return backup_path


def get_folder_id(catalog_path, search_term):
    """
    Find folders matching the search term and let user pick if multiple found.
    Returns the selected folder's id_local and full path.
    """
    conn = sqlite3.connect(catalog_path)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT f.id_local,
               r.absolutePath || f.pathFromRoot AS fullPath
        FROM AgLibraryFolder f
        JOIN AgLibraryRootFolder r ON f.rootFolder = r.id_local
    """)
    all_folders = cursor.fetchall()
    conn.close()

    matches = [
        (fid, fpath) for fid, fpath in all_folders
        if search_term.lower() in (fpath or "").lower()
    ]

    if not matches:
        return None, None

    if len(matches) == 1:
        return matches[0]

    print(f"\n  Found {len(matches)} folders matching '{search_term}':")
    for i, (fid, fpath) in enumerate(matches, 1):
        print(f"  [{i}] {fpath}")

    while True:
        choice = input("\n  Enter the number of the correct folder: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(matches):
            return matches[int(choice) - 1]
        print("  Invalid choice, try again.")


def flag_picks(catalog_path, filenames, folder_id):
    """
    Flags picks scoped to a specific folder_id.
    Matches on baseName (no extension) within that folder only.
    """
    conn = sqlite3.connect(catalog_path)
    cursor = conn.cursor()

    matched = []
    not_found = []

    for basename in filenames:
        cursor.execute("""
            SELECT ai.id_local
            FROM Adobe_images ai
            JOIN AgLibraryFile alf ON ai.rootFile = alf.id_local
            WHERE alf.baseName = ?
              AND alf.folder = ?
        """, (basename, folder_id))
        rows = cursor.fetchall()

        if rows:
            for (image_id,) in rows:
                cursor.execute("""
                    UPDATE Adobe_images
                    SET pick = 1
                    WHERE id_local = ?
                """, (image_id,))
            matched.append(basename)
        else:
            not_found.append(basename)

    conn.commit()
    conn.close()
    return matched, not_found


def main():
    print("\n========================================")
    print("  Lightroom Pick Flagger — Pixieset")
    print("========================================\n")
    print("⚠️  Make sure Lightroom Classic is CLOSED before continuing.\n")

    input("Press Enter to continue once Lightroom is closed...")

    # Step 1 — Catalog path
    print()
    catalog_path = get_input(
        "1. Drag your Lightroom catalog (.lrcat) into this window, or paste the path:\n> ",
        must_exist=True
    )
    if not catalog_path.endswith(".lrcat"):
        print("  ⚠️  Warning: That doesn't look like a .lrcat file. Continuing anyway...\n")

    # Step 2 — Shoot folder
    print()
    print("2. Enter part of your shoot folder name to scope the picks.")
    print("   (e.g. 'VyJeff' or '2024-05-18')")
    while True:
        search_term = input("> ").strip()
        if not search_term:
            print("  Please enter a folder search term.")
            continue

        folder_id, folder_path = get_folder_id(catalog_path, search_term)

        if folder_id is None:
            print(f"  ✗ No folders found matching '{search_term}'. Try a different term.\n")
            continue

        print(f"\n  ✓ Using folder: {folder_path}")
        confirm = input("  Is this correct? (y/n): ").strip().lower()
        if confirm == "y":
            break
        print("  Let's try again.\n")

    # Step 3 — Filename list
    print()
    filenames_path = get_input(
        "3. Drag your Pixieset filename list (.txt) into this window, or paste the path:\n> ",
        must_exist=True
    )

    print("\nLoading filename list...")
    try:
        filenames = load_filenames(filenames_path)
    except Exception as e:
        print(f"  ✗ Could not read filename list: {e}")
        sys.exit(1)

    print(f"  ✓ Found {len(filenames)} unique filenames")
    print(f"  Sample after suffix strip: {list(filenames)[:3]}\n")

    # Step 4 — Backup
    print("Backing up catalog...")
    try:
        backup_path = backup_catalog(catalog_path)
        print(f"  ✓ Backup saved to:\n    {backup_path}\n")
    except Exception as e:
        print(f"  ✗ Could not back up catalog: {e}")
        print("  Aborting for safety. Check file permissions and try again.")
        sys.exit(1)

    # Step 5 — Flag picks
    print("Flagging picks in catalog...")
    try:
        matched, not_found = flag_picks(catalog_path, filenames, folder_id)
    except Exception as e:
        print(f"  ✗ Error accessing catalog: {e}")
        print("  Make sure Lightroom is fully closed and try again.")
        sys.exit(1)

    # Results
    print(f"\n========================================")
    print(f"  Done!")
    print(f"========================================")
    print(f"  ✓ Flagged as Pick : {len(matched)} photos")
    print(f"  ✗ Not found in LR : {len(not_found)} filenames")

    if not_found:
        print(f"\n  Filenames not matched in folder:")
        for name in sorted(not_found)[:20]:
            print(f"    - {name}")
        if len(not_found) > 20:
            print(f"    ... and {len(not_found) - 20} more")

    print(f"\nOpen Lightroom and verify your picks.")
    print(f"Backup is at:\n  {backup_path}\n")


if __name__ == "__main__":
    main()
