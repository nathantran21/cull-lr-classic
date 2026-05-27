#!/bin/bash
# Build LR Pick Flagger (pywebview edition) as a double-clickable .app
# Usage: bash build_webview.sh

set -e
cd ~/Documents/LR\ Tools

echo "Checking dependencies..."
pip3 install pywebview py2app --quiet

echo "Cleaning previous build..."
rm -rf build/bdist.*/LR\ Pick\ Flagger\ *.app dist/LR\ Pick\ Flagger.app 2>/dev/null || true

echo "Building .app..."
python3 setup_webview.py py2app 2>&1

echo ""
if [ -d "dist/LR Pick Flagger.app" ]; then
  echo "Ad-hoc signing app (required on macOS 12+)..."
  codesign --deep --force --sign - "dist/LR Pick Flagger.app" 2>&1
  echo "Removing quarantine flag..."
  xattr -cr "dist/LR Pick Flagger.app" 2>/dev/null || true

  echo "✓ Done! App is at:"
  echo "  ~/Documents/LR Tools/dist/LR Pick Flagger.app"
  echo ""
  echo "To install:"
  echo "  cp -r dist/LR\\ Pick\\ Flagger.app /Applications/"
else
  echo "✗ Build failed — check output above."
  exit 1
fi
