#!/usr/bin/env python3
"""
generate_icon.py — build LR_Pick_Flagger.icns from scratch.

Renders the Aperture Flag icon (Option 06, Claude Design) at every macOS
icon size using Pillow, packages them into an .iconset, then calls
`iconutil` to produce the final .icns file.

Run:  python3 generate_icon.py
"""

import sys, os, math, colorsys, subprocess, shutil
from pathlib import Path

# ── Install Pillow if needed ──────────────────────────────────────────────────
try:
    from PIL import Image, ImageDraw
except ImportError:
    print("Installing Pillow…")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "Pillow", "--quiet"])
    from PIL import Image, ImageDraw

TOOLS_DIR = Path(__file__).parent
ICONSET   = TOOLS_DIR / "AppIcon.iconset"
ICNS_OUT  = TOOLS_DIR / "LR_Pick_Flagger.icns"

# ── Color helpers ─────────────────────────────────────────────────────────────

def hsl_to_rgb(h, s, l):
    """HSL (0-360, 0-100, 0-100) → (r, g, b) each 0-255."""
    r, g, b = colorsys.hls_to_rgb(h / 360, l / 100, s / 100)
    return (int(r * 255), int(g * 255), int(b * 255))

# Six aperture blade colors: hsl((deg+200)%360, 68%, 62%) — color wheel −15% sat
BLADE_COLORS = [hsl_to_rgb((d + 200) % 360, 68, 62) for d in (0, 60, 120, 180, 240, 300)]

# ── Squircle mask builder ─────────────────────────────────────────────────────

def make_squircle_mask(size):
    """
    Return an 'L'-mode PIL image that is white inside the Big-Sur squircle
    and black outside.  Corner radius ≈ 22.4 % of size.
    """
    r_sq = round(size * 0.224)
    mask = Image.new("L", (size, size), 0)
    d    = ImageDraw.Draw(mask)
    # rounded_rectangle available from Pillow 8.2+; fall back to ellipse+rects
    try:
        d.rounded_rectangle([0, 0, size - 1, size - 1], radius=r_sq, fill=255)
    except AttributeError:
        # Pillow < 8.2 fallback: horizontal + vertical bars + corner ellipses
        d.rectangle([r_sq, 0, size - r_sq, size], fill=255)
        d.rectangle([0, r_sq, size, size - r_sq], fill=255)
        for ox, oy in [(0, 0), (size - 2*r_sq, 0),
                       (0, size - 2*r_sq), (size - 2*r_sq, size - 2*r_sq)]:
            d.ellipse([ox, oy, ox + 2*r_sq, oy + 2*r_sq], fill=255)
    return mask

# ── Core drawing routine ──────────────────────────────────────────────────────

def draw_icon(size: int) -> Image.Image:
    """
    Render the Aperture Flag icon at `size` × `size` pixels.
    Returns a Pillow RGBA image ready to save as PNG.
    """
    s   = size
    sc  = s / 1024.0
    cx  = cy = s / 2.0

    # Work on a transparent RGBA canvas; squircle mask applied at the end
    canvas = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d      = ImageDraw.Draw(canvas)

    # ── 1. Radial gradient background ────────────────────────────────────────
    #  SVG: radialGradient cx=0.5 cy=0.4 r=0.8
    #       stop 0% → #2E3F66 (lighter center)
    #       stop 100% → #0E1530 (darker edge)
    edg  = (0x0E, 0x15, 0x30)
    ctr  = (0x2E, 0x3F, 0x66)
    gcy  = 0.4 * s                       # gradient center shifted upward
    max_r = s * 0.8                      # gradient radius = 80% of size

    # Fill base with outer/dark color first
    d.rectangle([0, 0, s, s], fill=edg + (255,))

    steps = 48
    for step in range(steps, -1, -1):    # outermost first, center last
        t   = step / steps               # 1 = outer, 0 = center
        rv  = round(edg[0] + (ctr[0] - edg[0]) * (1 - t))
        gv  = round(edg[1] + (ctr[1] - edg[1]) * (1 - t))
        bv  = round(edg[2] + (ctr[2] - edg[2]) * (1 - t))
        rad = max_r * t
        if rad >= 1:
            d.ellipse([cx - rad, gcy - rad, cx + rad, gcy + rad],
                      fill=(rv, gv, bv, 255))

    # ── 2. Six aperture blades ────────────────────────────────────────────────
    blade_r = 372 * sc
    n_seg   = 64                         # arc segments per blade
    for i, base_deg in enumerate([0, 60, 120, 180, 240, 300]):
        pts = []
        for j in range(n_seg + 1):
            ang = math.radians(base_deg + j * 60 / n_seg - 90)
            pts.append((cx + blade_r * math.cos(ang),
                        cy + blade_r * math.sin(ang)))
        pts.append((cx, cy))
        d.polygon(pts, fill=BLADE_COLORS[i] + (235,))   # opacity ≈ 0.92

    # ── 3. Inner dark well ────────────────────────────────────────────────────
    ir = 252 * sc
    d.ellipse([cx - ir, cy - ir, cx + ir, cy + ir], fill=(14, 21, 48, 255))
    # Subtle inner ring highlight  rgba(255,255,255,.12)
    ring_w = max(1, round(sc * 4))
    d.ellipse([cx - ir, cy - ir, cx + ir, cy + ir],
              fill=None, outline=(255, 255, 255, 30), width=ring_w)

    # ── 4. Flag pole (white) ──────────────────────────────────────────────────
    pcx  = (430 + 12) * sc
    pw   = max(2.0, 24 * sc)
    py1, py2 = 360 * sc, 680 * sc
    d.rectangle([pcx - pw / 2, py1, pcx + pw / 2, py2], fill=(255, 255, 255, 255))

    # ── 5. Flag body (red → pink gradient → two-tone approximation) ──────────
    #  M454 380 L640 400 L580 470 L640 540 L454 520 Z
    flag_pts = [
        (454*sc, 380*sc), (640*sc, 400*sc), (580*sc, 470*sc),
        (640*sc, 540*sc), (454*sc, 520*sc),
    ]
    d.polygon(flag_pts, fill=(230, 52, 101, 255))    # #E63465

    # Shadow fold  M580 470 L640 400 L640 540 Z  fill rgba(0,0,0,.22) over #E63465
    # Pre-composite: (230*0.78, 52*0.78, 101*0.78) = (179, 41, 79) = #B3294F
    fold_pts = [(580*sc, 470*sc), (640*sc, 400*sc), (640*sc, 540*sc)]
    d.polygon(fold_pts, fill=(179, 41, 79, 255))

    # ── 6. Apply squircle clip mask ───────────────────────────────────────────
    mask = make_squircle_mask(s)
    result = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    result.paste(canvas, mask=mask)

    # ── 7. Subtle edge highlights ─────────────────────────────────────────────
    #  Inner white glow: stroke rgba(255,255,255,.18), width 4px
    #  Outer dark shadow: stroke rgba(0,0,0,.08), width 2px, offset (0,2)
    edge_d = ImageDraw.Draw(result)
    try:
        edge_d.rounded_rectangle(
            [2, 2, s - 3, s - 3], radius=round(s * 0.224) - 2,
            outline=(255, 255, 255, 46), width=max(1, round(sc * 4)),
        )
    except (AttributeError, TypeError):
        pass   # old Pillow — skip edge highlight

    return result

# ── Main: generate all sizes and call iconutil ────────────────────────────────

ICON_SIZES = [
    (16,   "icon_16x16.png"),
    (32,   "icon_16x16@2x.png"),
    (32,   "icon_32x32.png"),
    (64,   "icon_32x32@2x.png"),
    (128,  "icon_128x128.png"),
    (256,  "icon_128x128@2x.png"),
    (256,  "icon_256x256.png"),
    (512,  "icon_256x256@2x.png"),
    (512,  "icon_512x512.png"),
    (1024, "icon_512x512@2x.png"),
]

def main():
    # Clean and recreate .iconset directory
    if ICONSET.exists():
        shutil.rmtree(ICONSET)
    ICONSET.mkdir()

    print("Rendering icon sizes…")
    cache: dict[int, Image.Image] = {}
    for px, filename in ICON_SIZES:
        if px not in cache:
            cache[px] = draw_icon(px)
        cache[px].save(ICONSET / filename, "PNG")
        print(f"  ✓  {filename}  ({px}×{px})")

    print("\nRunning iconutil…")
    result = subprocess.run(
        ["iconutil", "-c", "icns", str(ICONSET), "-o", str(ICNS_OUT)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print("iconutil error:", result.stderr)
        sys.exit(1)

    print(f"  ✓  {ICNS_OUT.name}")
    print(f"\nDone!  App icon written to:\n  {ICNS_OUT}")
    print(
        "\nTo use it in the .app bundle, re-run:  bash build_app.sh\n"
        "(build_app.sh now calls this script automatically)"
    )

if __name__ == "__main__":
    main()
