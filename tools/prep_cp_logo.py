"""Generate NeoFace logo assets from a source image.

Produces (matching the shipped asset dimensions):
  cp/icon.bmp       256x256 24-bit  tile logo loaded by GetBitmapValue
  cp/tile.bmp       512x512 24-bit  full-size spare tile art
  static/logo.png   128x128 RGBA    dashboard header logo (with --dashboard)

Usage:
  python tools\\prep_cp_logo.py path\\to\\logo.png
  python tools\\prep_cp_logo.py logo.png --dashboard
  python tools\\prep_cp_logo.py logo.png --out-dir cp --bg 255,255,255
"""
import argparse
import os
import sys

from PIL import Image

ICON = (256, 256)
TILE = (512, 512)
DASH = (128, 128)


def square_crop(img, size):
    """Center-crop to a square, then resize to size (RGBA)."""
    img = img.convert("RGBA")
    w, h = img.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    img = img.crop((left, top, left + side, top + side))
    return img.resize(size, Image.LANCZOS)


def save_bmp(img, path, bg):
    background = Image.new("RGB", img.size, bg)
    background.paste(img, mask=img.split()[3])
    background.save(path, "BMP")
    print("wrote %s (%dx%d)" % (path, img.size[0], img.size[1]))


def main():
    ap = argparse.ArgumentParser(description="Generate NeoFace logo assets from one source image")
    ap.add_argument("source", help="source image (PNG/JPG; transparency respected for BMPs)")
    ap.add_argument("--out-dir", default="cp", help="directory for icon.bmp/tile.bmp (default: cp)")
    ap.add_argument("--dashboard", action="store_true", help="also write static/logo.png")
    ap.add_argument("--bg", default="0,0,0", help="RGB fill behind transparency for BMPs (default 0,0,0)")
    args = ap.parse_args()

    try:
        bg = tuple(int(x.strip()) for x in args.bg.split(","))
    except ValueError:
        ap.error("--bg must be R,G,B integers")
    if len(bg) != 3 or any(c < 0 or c > 255 for c in bg):
        ap.error("--bg must be three values 0-255")

    src = Image.open(args.source)
    os.makedirs(args.out_dir, exist_ok=True)

    save_bmp(square_crop(src, ICON), os.path.join(args.out_dir, "icon.bmp"), bg)
    save_bmp(square_crop(src, TILE), os.path.join(args.out_dir, "tile.bmp"), bg)

    if args.dashboard:
        os.makedirs("static", exist_ok=True)
        square_crop(src, DASH).save(os.path.join("static", "logo.png"), "PNG")
        print("wrote static/logo.png (128x128)")

    print("done. redeploy assets: cp\\deploy_all.ps1 (or cp\\register_cp.ps1)")


if __name__ == "__main__":
    sys.exit(main())
