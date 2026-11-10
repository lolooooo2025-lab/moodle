"""check_fonts — bundled font files are real fonts (magic bytes), not HTML 404 pages.

woff2 -> wOF2, woff -> wOFF, ttf -> 00 01 00 00 (and a sane sfnt table count).
Exit 1 if any font file is invalid or too small.
"""
from __future__ import annotations
import sys, pathlib, struct
ROOT = pathlib.Path(__file__).resolve().parent.parent

def valid_font(p: pathlib.Path) -> tuple[bool, str]:
    b = p.read_bytes()
    if len(b) < 1000:
        return False, f"too small ({len(b)} bytes)"
    if p.suffix == ".woff2":
        return (b[:4] == b"wOF2", f"magic={b[:4]!r}")
    if p.suffix == ".woff":
        return (b[:4] == b"wOFF", f"magic={b[:4]!r}")
    if p.suffix == ".ttf":
        if b[:4] != b"\x00\x01\x00\x00":
            return False, f"magic={b[:4]!r}"
        num_tables = struct.unpack(">H", b[4:6])[0]
        return (0 < num_tables < 100, f"sfnt tables={num_tables}")
    return False, "unknown extension"

def main():
    fonts = list((ROOT / "app" / "static" / "fonts").glob("*"))
    fonts = [f for f in fonts if f.suffix in (".woff2", ".woff", ".ttf")]
    if not fonts:
        print("check_fonts: FAIL — no fonts found")
        return 1
    bad = []
    for f in fonts:
        ok, detail = valid_font(f)
        if not ok:
            bad.append(f"{f.name}: {detail}")
    if bad:
        print("check_fonts: FAIL")
        for b in bad:
            print("  " + b)
        return 1
    print(f"check_fonts: PASS — {len(fonts)} real font files (magic bytes verified)")
    return 0

if __name__ == "__main__":
    sys.exit(main())
