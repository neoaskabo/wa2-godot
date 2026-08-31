#!/usr/bin/env python3
"""Restore the art/audio assets that upstream keeps out of git.

`assets/grp/`, `assets/se/`, `assets/IC/`, `assets/fonts/cn/` and `assets/fonts/jp/`
are excluded by upstream's .gitignore (they are extracted from the game), so a
fresh `git clone` has none of them.  Without them Godot exports a PCK where every
`res://assets/grp/*.png` is missing: the snow particles render as white squares
(null atlas) and the title/menu UI is a black screen.

Upstream still ships the assets *inside* its official Android APK, in Godot's
imported form:

    assets/assets/<relpath>.import          ->  declares the original path
    assets/.godot/imported/<name>-<md5>.ctex ->  "GST2" header + the image bytes

The images are stored losslessly (PNG or lossless WebP), so they can be restored
byte-for-byte.  This script does that, so the game assets never have to live in
git history.

Usage:
    python3 tools/extract_assets.py [--apk PATH] [--out DIR] [--tag 0.2.8]

Defaults to downloading `wa2_<tag>cn.apk` from the upstream releases.
"""

import argparse
import io
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

APK_URL = "https://github.com/dorakyuraduang/wa2-godot/releases/download/{tag}/wa2_{tag}cn.apk"

# Godot 4 .ctex (CompressedTexture2D) layout used here:
#   +0  4  'GST2'
#   +8  4  width
#   +12 4  height
#   +52 4  payload size
#   +56 ..  payload: either a raw WebP ("RIFF") or b'PNG ' + a raw PNG
CTEX_PAYLOAD_OFFSET = 56

# AudioStreamWAV .sample files are Godot binary resources that we cannot cheaply
# decode.  The six SE_*.WAV files are UI click sounds, so we synthesise valid
# short tones instead of leaving the resource missing -- a missing ext_resource
# is what makes scenes like BasePage.tscn fail to load.
SE_FILES = ["SE_8905", "SE_9015", "SE_9211", "SE_9212", "SE_9213", "SE_9214"]

# Imported as a bitmap font (importer="font_data_image"), not as a texture.
# Upstream's APK only carries the baked FontFile, so the source atlas is gone.
# We emit a tiny valid PNG so the resource resolves; glyphs will be blank.
FONT_IMAGE_PLACEHOLDER = "assets/grp/sys_01013.png"


def log(msg):
    print(f"[assets] {msg}", flush=True)


def fetch_apk(tag, dest, local=None):
    if local:
        log(f"using local APK: {local}")
        shutil.copyfile(local, dest)
        return
    url = APK_URL.format(tag=tag)
    # curl, not urllib: reading this 130 MB body through urlopen stalls
    # indefinitely part-way through, while curl streams it in ~30 s.
    last = None
    for attempt in range(1, 4):
        log(f"downloading {url} (attempt {attempt}/3)")
        if shutil.which("curl") is not None:
            r = subprocess.run(
                ["curl", "-sSL", "--fail", "--retry", "3", "--max-time", "600", "-o", dest, url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            if r.returncode == 0:
                size = os.path.getsize(dest) if os.path.exists(dest) else 0
                if size > 10_000_000:
                    log(f"downloaded {size / 1e6:.1f} MB")
                    return
                last = f"suspiciously small: {size} bytes"
            else:
                last = r.stderr.decode("utf-8", "replace").strip()[:200]
        else:
            try:
                req = urllib.request.Request(
                    url, headers={"User-Agent": "wa2-asset-extract/1.0"}
                )
                with urllib.request.urlopen(req, timeout=300) as resp, open(dest, "wb") as f:
                    shutil.copyfileobj(resp, f)
                size = os.path.getsize(dest)
                if size > 10_000_000:
                    log(f"downloaded {size / 1e6:.1f} MB")
                    return
                last = f"suspiciously small: {size} bytes"
            except Exception as exc:  # noqa: BLE001 - surface as a clean CI error
                last = f"{type(exc).__name__}: {exc}"
        log(f"  failed: {last}")
    raise SystemExit(f"could not download the upstream APK: {last}")


def _zip_name(info):
    """Undo zipfile's cp437 fallback for names that are really UTF-8.

    The APK is packed without the UTF-8 flag bit, so zipfile hands back
    mojibake like "14pt\\u00b5\\u00a3\\u00bc\\u03a3\\u2594\\u00f4.png" for the real
    Japanese/Chinese filenames (assets/grp/\\u70df.png, assets/fonts/cn/\\u888b\\u5f71.png...).
    """
    name = info.filename
    if info.flag_bits & 0x800:
        return name
    try:
        return name.encode("cp437").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return name


def unpack(apk, work):
    """Extract the project's assets/ tree and the imported resource cache."""
    with zipfile.ZipFile(apk) as z:
        count = 0
        for info in z.infolist():
            name = _zip_name(info)
            if not (name.startswith("assets/assets/") or name.startswith("assets/.godot/imported/")):
                continue
            if info.is_dir():
                continue
            dst = os.path.join(work, name)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with z.open(info) as src, open(dst, "wb") as out:
                shutil.copyfileobj(src, out)
            count += 1
        if count == 0:
            raise SystemExit("APK does not contain a Godot assets/ tree")
        log(f"unpacked {count} entries")
    return os.path.join(work, "assets")


def ctex_to_bytes(path):
    """Return (image_bytes, ext) for a .ctex file, or None."""
    with open(path, "rb") as f:
        data = f.read()
    if len(data) <= CTEX_PAYLOAD_OFFSET or data[:4] != b"GST2":
        return None
    payload = data[CTEX_PAYLOAD_OFFSET:]
    if payload[:4] == b"RIFF":
        return payload, "webp"
    if payload[:4] == b"PNG ":
        return payload[4:], "png"
    if payload[:2] == b"\x89P":
        return payload, "png"
    return None


def _via_sips(payload, suffix):
    """Convert with the macOS `sips` CLI. Returns PNG bytes or None."""
    if shutil.which("sips") is None:
        return None
    work = tempfile.mkdtemp(prefix="sips")
    try:
        src = os.path.join(work, "in." + suffix)
        dst = os.path.join(work, "out.png")
        with open(src, "wb") as f:
            f.write(payload)
        r = subprocess.run(
            ["sips", "-s", "format", "png", src, "--out", dst],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if r.returncode != 0 or not os.path.exists(dst):
            return None
        with open(dst, "rb") as f:
            return f.read()
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _via_pillow(payload):
    try:
        from PIL import Image
    except ImportError:
        return None
    img = Image.open(io.BytesIO(payload))
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGBA")
    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


def convert(payload, ext, prefer_sips=None):
    """Return PNG bytes.

    Plain PNG is passed through untouched.  WebP needs decoding: Pillow is the
    portable option, but installing it in CI is fragile (PEP 668 marks the
    runner's Python as externally managed), so on macOS we prefer `sips`,
    which ships with the OS and preserves the alpha channel.
    """
    if ext == "png":
        return payload
    if prefer_sips is None:
        prefer_sips = sys.platform == "darwin"
    order = ["sips", "pillow"] if prefer_sips else ["pillow", "sips"]
    for how in order:
        out = _via_pillow(payload) if how == "pillow" else _via_sips(payload, ext)
        if out:
            return out
    # Returning None instead of raising: one undecodable sprite should not
    # abort the whole restore. main() fails the build only if a critical
    # asset is missing.
    return None


def collect_imports(assets_root):
    """Map original project path -> imported cache filename."""
    src_dir = os.path.join(assets_root, "assets")
    mapping = {}
    for dirpath, _dirs, files in os.walk(src_dir):
        for fn in files:
            if not fn.endswith(".import"):
                continue
            full = os.path.join(dirpath, fn)
            # Paths inside the APK are relative to assets/assets/, which is the
            # project's assets/ directory.
            rel = "assets/" + os.path.relpath(full, src_dir)[: -len(".import")]
            text = open(full, encoding="utf-8", errors="replace").read()
            m = re.search(r'path="res://\.godot/imported/([^"]+)"', text)
            if m:
                mapping[rel] = m.group(1)
    return mapping


def synth_wav(path, freq=880.0, seconds=0.06, rate=44100):
    """Write a short low-volume click sound as a 16-bit mono PCM WAV."""
    import math
    frames = int(rate * seconds)
    chunks = bytearray()
    for i in range(frames):
        t = i / rate
        env = math.exp(-t * 55.0)
        v = int(6000 * env * math.sin(2 * math.pi * freq * t))
        chunks += struct.pack("<h", v)
    data = bytes(chunks)
    with open(path, "wb") as f:
        f.write(b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVE")
        f.write(b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16))
        f.write(b"data" + struct.pack("<I", len(data)))
        f.write(data)


def tiny_png(path, w=8, h=8):
    """Write a minimal valid RGBA PNG (fully transparent)."""
    import zlib
    raw = b"".join(b"\x00" + b"\x00" * (w * 4) for _ in range(h))

    def chunk(tag, payload):
        return (
            struct.pack(">I", len(payload))
            + tag
            + payload
            + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)
        )

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw, 9))
    png += chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(png)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apk", help="local APK to use instead of downloading")
    ap.add_argument("--tag", default="0.2.8", help="upstream release tag")
    ap.add_argument("--out", default=".", help="project root to write assets/ into")
    args = ap.parse_args()

    out = os.path.abspath(args.out)
    work = tempfile.mkdtemp(prefix="wa2assets")
    try:
        apk = os.path.join(work, "wa2.apk")
        fetch_apk(args.tag, apk, args.apk)
        assets_root = unpack(apk, work)
        imported = os.path.join(assets_root, ".godot", "imported")

        mapping = collect_imports(assets_root)
        log(f"found {len(mapping)} imported resources")

        written = skipped = failed = 0
        for rel, cache_name in sorted(mapping.items()):
            cache_path = os.path.join(imported, cache_name)
            dst = os.path.join(out, rel)
            if not os.path.exists(cache_path):
                continue
            if cache_name.endswith(".ctex"):
                got = ctex_to_bytes(cache_path)
                if not got:
                    failed += 1
                    log(f"  MISS  {rel} (unsupported ctex)")
                    continue
                payload, ext = got
                png = convert(payload, ext)
                if png is None:
                    failed += 1
                    log(f"  MISS  {rel} (cannot decode {ext})")
                    continue
            elif cache_name.endswith(".sample"):
                # AudioStreamWAV: synthesise a click so the resource resolves.
                png = None
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                synth_wav(dst)
                written += 1
                continue
            else:
                # .fontdata etc. -- not a plain image, cannot restore.
                skipped += 1
                continue
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(dst, "wb") as f:
                f.write(png)
            written += 1

        log(f"wrote {written} files, skipped {skipped} (non-image), failed {failed}")

        # The bitmap-font atlas is only shipped as a baked FontFile.
        dst = os.path.join(out, FONT_IMAGE_PLACEHOLDER)
        if not os.path.exists(dst):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            tiny_png(dst)
            log(f"placeholder written: {FONT_IMAGE_PLACEHOLDER}")

        for name in SE_FILES:
            for ext in ("WAV", "wav"):
                dst = os.path.join(out, "assets", "se", f"{name}.{ext}")
                if not os.path.exists(dst):
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    synth_wav(dst)
    finally:
        shutil.rmtree(work, ignore_errors=True)

    # Sanity check: the snow atlas is the one that turns into white squares.
    critical = ["assets/grp/weather.png", "assets/fonts/cn/本体80.png", "assets/se/SE_9213.WAV"]
    missing = [c for c in critical if not os.path.exists(os.path.join(out, c))]
    if missing:
        # Annotate so the reason lands in the Actions UI, not just the log tail.
        print("::error::missing critical assets: " + ", ".join(missing), flush=True)
        return 1
    log("all critical assets present")
    return 0


if __name__ == "__main__":
    sys.exit(main())
