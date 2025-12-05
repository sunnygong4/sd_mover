#!/usr/bin/env python3
import argparse, os, sys, shutil, hashlib, datetime as dt
from pathlib import Path

# ---- File types ----
IMAGE_EXTS = {
    ".jpg",".jpeg",".png",".heic",".heif",".tif",".tiff",".gif",".neg"
}
RAW_EXTS = {
    ".cr2",".cr3",".arw",".nef",".dng",".orf",".rw2",".raf",".srw",".pef"
}
DEFAULT_EXTS = IMAGE_EXTS | RAW_EXTS

# ---- Optional EXIF (Pillow) ----
try:
    from PIL import Image
    from PIL.ExifTags import TAGS
    PIL_OK = True
except Exception:
    PIL_OK = False

def parse_args():
    p = argparse.ArgumentParser(
        description="Move photos from F:\\DCIM\\100CANON to P:\\Photos\\YYYY.MM.x\\YYYY.MM.DD based on shot date."
    )
    p.add_argument("--source", "-s", default=r"F:\DCIM\100CANON",
                   help="Source folder (default F:\\DCIM\\100CANON)")
    p.add_argument("--dest", "-d", default=r"P:\Photos",
                   help="Destination root (default P:\\Photos)")
    p.add_argument("--date", required=True,
                   help="Only move files shot on this date (YYYY-MM-DD), using EXIF DateTimeOriginal when available.")
    p.add_argument("--extensions", nargs="*", help="Override extensions (e.g. .jpg .cr2). Default: JPEG + common RAW + .neg")
    p.add_argument("--use-exif", action="store_true", help="Prefer EXIF DateTimeOriginal for photos (recommended).")
    p.add_argument("--dry-run", action="store_true", help="Show actions without moving files.")
    p.add_argument("--min-size-kb", type=int, default=5, help="Skip tiny files (default 5KB).")
    return p.parse_args()

def file_hash(path, first_mb_only=True):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        if first_mb_only:
            h.update(f.read(1024 * 1024))
        else:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
    return h.hexdigest()

def exif_date(path: Path):
    if not PIL_OK:
        return None
    try:
        with Image.open(path) as im:
            exif = im._getexif()
            if not exif:
                return None
            exif_map = {TAGS.get(k, k): v for k, v in exif.items()}
            for k in ("DateTimeOriginal", "DateTime", "CreateDate"):
                v = exif_map.get(k)
                if isinstance(v, str):
                    raw = v.strip().replace("-", ":").replace(".", ":")
                    # Expect "YYYY:MM:DD HH:MM:SS"
                    parts = raw.split(" ")[0].split(":")
                    if len(parts) >= 3 and all(p.isdigit() for p in parts[:3]):
                        y,m,d = map(int, parts[:3])
                        return dt.date(y,m,d)
    except Exception:
        return None
    return None

def file_date(path: Path, use_exif: bool):
    if use_exif and path.suffix.lower() in (IMAGE_EXTS | RAW_EXTS):
        d = exif_date(path)
        if d:
            return d
    # Fallback to filesystem mtime
    return dt.date.fromtimestamp(path.stat().st_mtime)

def ensure_dir(p: Path, dry=False):
    if not dry:
        p.mkdir(parents=True, exist_ok=True)

def main():
    args = parse_args()
    src = Path(args.source)
    dst_root = Path(args.dest)
    wanted_date = dt.datetime.strptime(args.date, "%Y-%m-%d").date()
    exts = set(e.lower() if e.startswith(".") else "."+e.lower()
               for e in (args.extensions or DEFAULT_EXTS))

    if not src.exists():
        print(f"[ERROR] Source not found: {src}", file=sys.stderr)
        sys.exit(1)
    if not dst_root.exists() and not args.dry_run:
        dst_root.mkdir(parents=True, exist_ok=True)

    planned = []
    for root, _, files in os.walk(src):
        for name in files:
            p = Path(root) / name
            if p.suffix.lower() not in exts:
                continue
            try:
                if p.stat().st_size < args.min_size_kb * 1024:
                    continue
            except FileNotFoundError:
                continue

            d = file_date(p, args.use_exif)
            if d != wanted_date:
                continue

            # Destination path P:\Photos\YYYY.MM.x\YYYY.MM.DD\
            month_folder = f"{d.year:04d}.{d.month:02d}.x"
            day_folder = f"{d.year:04d}.{d.month:02d}.{d.day:02d}"
            out_dir = dst_root / month_folder / day_folder
            out_path = out_dir / p.name

            # De-dupe by quick hash if name collision
            if out_path.exists():
                try:
                    if file_hash(p) == file_hash(out_path):
                        print(f"[SKIP] Duplicate content: {p} == {out_path}")
                        continue
                except Exception:
                    pass
                base, suf = out_path.stem, out_path.suffix
                i = 1
                while out_path.exists():
                    out_path = out_dir / f"{base} ({i}){suf}"
                    i += 1

            planned.append((p, out_dir, out_path))

    moved, bytes_total = 0, 0
    for src_path, out_dir, out_path in planned:
        print(f"[MOVE] {src_path}  ->  {out_path}")
        if not args.dry_run:
            ensure_dir(out_dir)
            shutil.move(str(src_path), str(out_path))
            try:
                bytes_total += out_path.stat().st_size
            except Exception:
                pass
        moved += 1

    print(f"\nDone. {moved} file(s) {'would be ' if args.dry_run else ''}moved. ~{bytes_total/1_000_000:.2f} MB.")
    if args.use_exif and not PIL_OK:
        print("Note: --use-exif requested but Pillow is not installed; used file modified times instead.", file=sys.stderr)

if __name__ == "__main__":
    main()
