#!/bin/bash
# Run this once to package LR_Pick_Flagger.py as a double-clickable Mac app
# Usage: bash build_app.sh

set -e
cd ~/Documents/LR\ Tools

echo "Step 1 — Generating app icon (.icns)…"
python3 generate_icon.py

echo ""
echo "Step 2 — Installing py2app…"
pip3 install py2app --quiet

echo ""
echo "Step 3 — Building app bundle…"
cat > setup.py << 'SETUP'
from setuptools import setup
APP = ['LR_Pick_Flagger.py']
OPTIONS = {
    'argv_emulation': False,
    'iconfile': 'LR_Pick_Flagger.icns',
    'plist': {
        'CFBundleName': 'LR Pick Flagger',
        'CFBundleDisplayName': 'LR Pick Flagger',
        'CFBundleVersion': '1.0',
        'CFBundleIconFile': 'LR_Pick_Flagger',
    },
}
setup(app=APP, options={'py2app': OPTIONS}, setup_requires=['py2app'])
SETUP

python3 setup.py py2app --quiet

echo ""
echo "✓ Done! Your app is at:"
echo "  ~/Documents/LR Tools/dist/LR Pick Flagger.app"
echo ""
echo "Drag it to your Applications folder or Dock to use it anytime."
