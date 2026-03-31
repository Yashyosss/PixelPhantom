"""
PixelPhantom v2.0
Hunt down every ghost file lurking in your library.

Detection method : Pure pixel-level direct comparison (images)
                   Byte-level direct comparison (video / audio)
                   NO hashing — actual content is compared
Image integrity  : Files opened read-only · no re-encoding · no quality loss
                   Original pixel values preserved 100%

Developer : Yashas K
GitHub    : https://github.com/Yashyosss
Email     : yashaskeshav87@gmail.com
License   : Use, Modify, Share
"""

import os, sys, shutil, json, threading, queue, time, csv, platform, math
from pathlib import Path
from collections import defaultdict
from datetime import datetime

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, colorchooser

try:
    from PIL import Image
    PIL_OK = True
except ImportError:
    PIL_OK = False

# ── metadata ──────────────────────────────────────────────────────
APP_NAME    = "PixelPhantom"
APP_VER     = "2.0.0"
APP_TAGLINE = "Hunt down every ghost file lurking in your library."
DEV_NAME    = "Yashas K"
DEV_GITHUB  = "https://github.com/Yashyosss"
DEV_EMAIL   = "yashaskeshav87@gmail.com"
APP_YEAR    = "2026"
APP_LICENSE = "Use, Modify, Share"

# ── supported formats ────────────────────────────────────────────
IMAGE_EXTS = {
    '.jpg','.jpeg','.png','.bmp','.gif','.tiff','.tif',
    '.webp','.ico','.ppm','.pgm','.pbm',
    # RAW formats — compared byte-level since PIL can't always decode them
    '.nef','.cr2','.arw','.dng','.orf','.rw2','.pef','.srw','.raw',
    '.heic','.heif','.avif',
}
VIDEO_EXTS = {
    '.mp4','.mov','.avi','.mkv','.wmv','.flv','.webm',
    '.m4v','.3gp','.mpeg','.mpg','.ts','.mts','.vob','.ogv',
}
AUDIO_EXTS = {
    '.mp3','.flac','.wav','.aac','.ogg','.wma','.m4a','.opus',
    '.aiff','.aif','.ape','.mka','.amr',
}
PIXEL_EXTS   = {'.jpg','.jpeg','.png','.bmp','.tiff','.tif','.webp',
                '.ppm','.pgm','.pbm','.ico'}
ALL_EXTS     = IMAGE_EXTS | VIDEO_EXTS | AUDIO_EXTS

TRASH_DIR    = os.path.join(os.path.expanduser('~'), '.pixelphantom_trash')
REPORTS_DIR  = os.path.join(os.path.expanduser('~'), 'PixelPhantom_Reports')
WORKERS      = max(4, os.cpu_count() or 4)
CHUNK        = 65536   # bytes read per iteration for binary compare

# ═════════════════════════════════════════════════════════════════
#  THEME SYSTEM
# ═════════════════════════════════════════════════════════════════
THEMES = {
    'dark': {
        'bg':'#0d0d0d','bg1':'#141414','bg2':'#1c1c1c',
        'bg3':'#242424','bg4':'#2e2e2e',
        'border':'#2a2a2a','border2':'#3a3a3a',
        'text':'#f0f0f0','text2':'#aaaaaa','text3':'#555555',
        'red':'#ff4d5e','red_dim':'#280008',
        'amber':'#ffb300','amber_dim':'#281e00',
        'green':'#3ddc84','green_dim':'#002814',
        'blue':'#5599ff','blue_dim':'#001630',
    },
    'light': {
        'bg':'#f5f5f3','bg1':'#ebebea','bg2':'#e0e0de',
        'bg3':'#d4d4d2','bg4':'#c8c8c6',
        'border':'#d0d0ce','border2':'#bbbbba',
        'text':'#111111','text2':'#555555','text3':'#999999',
        'red':'#cc1f2d','red_dim':'#ffeaec',
        'amber':'#aa6600','amber_dim':'#fff5e0',
        'green':'#1a7a40','green_dim':'#e8f8ee',
        'blue':'#1155cc','blue_dim':'#e8f0ff',
    },
}

ACCENTS = [
    ('#7c3aed','Phantom'),('#00d68f','Mint'),('#00b4d8','Cyan'),
    ('#ff6b35','Ember'), ('#f72585','Neon'),('#ffd60a','Gold'),
    ('#ff4d5e','Red'),   ('#4361ee','Indigo'),('#06d6a0','Seafoam'),
    ('#fb8500','Tangerine'),
]

C = {}
_theme  = 'dark'
_accent = '#7c3aed'

def _dim(h):
    r,g,b = int(h[1:3],16), int(h[3:5],16), int(h[5:7],16)
    if _theme == 'dark':
        return '#{:02x}{:02x}{:02x}'.format(r//7, g//7, b//7)
    return '#{:02x}{:02x}{:02x}'.format(
        min(255,215+r//20), min(255,215+g//20), min(255,215+b//20))

def apply_theme(name='dark', accent='#7c3aed'):
    global _theme, _accent
    _theme = name; _accent = accent
    C.clear(); C.update(THEMES[name])
    C['accent']     = accent
    C['accent_dim'] = _dim(accent)

apply_theme('dark', '#7c3aed')


# ═════════════════════════════════════════════════════════════════
#  HELPERS
# ═════════════════════════════════════════════════════════════════
def human_size(n):
    for u in ('B','KB','MB','GB','TB'):
        if n < 1024 or u == 'TB': return f'{n:.1f} {u}'
        n /= 1024

def human_time(ts):
    return datetime.fromtimestamp(ts).strftime('%Y-%m-%d  %H:%M')

def human_secs(s):
    s = int(s)
    if s < 60:  return f'{s}s'
    if s < 3600: return f'{s//60}m {s%60}s'
    return f'{s//3600}h {(s%3600)//60}m'


# ═════════════════════════════════════════════════════════════════
#  FILE COLLECTION
# ═════════════════════════════════════════════════════════════════
def collect_files(folders, protected):
    prot = {os.path.abspath(p) for p in protected}
    files = []
    for folder in folders:
        for root, _, names in os.walk(folder):
            if any(os.path.abspath(root).startswith(p) for p in prot):
                continue
            for name in names:
                ext = Path(name).suffix.lower()
                if ext not in ALL_EXTS: continue
                kind = ('image' if ext in IMAGE_EXTS else
                        'video' if ext in VIDEO_EXTS else
                        'audio')
                p = os.path.join(root, name)
                try:
                    st = os.stat(p)
                    files.append({
                        'path': p, 'name': name,
                        'size': st.st_size, 'mtime': st.st_mtime,
                        'kind': kind, 'ext': ext,
                    })
                except OSError: pass
    return files


# ═════════════════════════════════════════════════════════════════
#  COMPARISON FUNCTIONS  (read-only, no modification)
# ═════════════════════════════════════════════════════════════════
def pixels_equal(path_a: str, path_b: str) -> bool:
    """
    Compare two image files pixel by pixel.
    Opens both files read-only. Never writes, never re-encodes.
    Returns True only if every single pixel R,G,B,A value matches.
    """
    if not PIL_OK:
        return bytes_equal(path_a, path_b)
    try:
        with Image.open(path_a) as img_a, Image.open(path_b) as img_b:
            # Different dimensions = definitely not equal
            if img_a.size != img_b.size:
                return False
            # Normalise to same mode so comparison is fair
            mode = 'RGBA' if (img_a.mode == 'RGBA' or img_b.mode == 'RGBA') else 'RGB'
            img_a = img_a.convert(mode)
            img_b = img_b.convert(mode)
            # Direct pixel data comparison — no intermediate hash
            return img_a.tobytes() == img_b.tobytes()
    except Exception:
        # If PIL can't decode, fall back to byte comparison
        return bytes_equal(path_a, path_b)


def bytes_equal(path_a: str, path_b: str) -> bool:
    """
    Compare two files byte by byte.
    Used for video, audio, and RAW images that PIL can't decode.
    Opens files read-only in binary mode. No modification.
    Returns True only if every byte matches.
    """
    try:
        size_a = os.path.getsize(path_a)
        size_b = os.path.getsize(path_b)
        if size_a != size_b: return False
        with open(path_a, 'rb') as fa, open(path_b, 'rb') as fb:
            while True:
                chunk_a = fa.read(CHUNK)
                chunk_b = fb.read(CHUNK)
                if chunk_a != chunk_b: return False
                if not chunk_a: break   # both exhausted
        return True
    except Exception:
        return False


def get_image_dimensions(path: str):
    """
    Read image dimensions without loading pixel data.
    Pure metadata read — very fast.
    Returns (width, height) or None if unreadable.
    """
    if not PIL_OK: return None
    try:
        with Image.open(path) as img:
            return img.size   # (width, height)
    except Exception:
        return None


# ═════════════════════════════════════════════════════════════════
#  SCAN ENGINE
# ═════════════════════════════════════════════════════════════════
class ScanEngine:
    """
    Three-phase duplicate finder using direct comparison.

    Phase 1 — Size gate (free):
        Group files by byte size. Files with unique sizes
        are skipped — impossible to have a duplicate.

    Phase 2 — Dimension gate for images (very fast):
        Within each size group, further group images by
        (width, height). Different dimensions = not equal.

    Phase 3 — Direct comparison (thorough):
        For each candidate group, compare files pairwise.
        Images: pixel-by-pixel via PIL tobytes()
        Video/Audio: byte-by-byte file read
        No hashing at any stage.
    """

    def __init__(self, files, on_progress, on_log, on_done):
        self.files       = files
        self.on_progress = on_progress
        self.on_log      = on_log
        self.on_done     = on_done
        self._stop       = threading.Event()

    def start(self):
        self._stop.clear()
        threading.Thread(target=self._run, daemon=True).start()

    def stop(self):
        self._stop.set()

    def _run(self):
        try:
            self._scan()
        except Exception as e:
            self.on_log(f'Engine error: {e}', 'error')
            self.on_done([], [])

    def _scan(self):
        files  = self.files
        total  = len(files)
        self.on_log(f'Starting pixel scan on {total} files…', 'info')
        self.on_progress(2, 0, total, 0)

        # ── Phase 1: size gate ─────────────────────────────────
        self.on_log('Phase 1 — grouping by file size…', 'info')
        size_groups = defaultdict(list)
        for f in files:
            size_groups[(f['size'], f['kind'])].append(f)

        candidates = [f for grp in size_groups.values()
                      if len(grp) > 1 for f in grp]
        skipped = total - len(candidates)
        self.on_log(
            f'Size gate: {skipped} unique-size files skipped, '
            f'{len(candidates)} candidates remain', 'info')
        self.on_progress(10, skipped, total, 0)

        if not candidates:
            self.on_log('No candidates after size gate — no duplicates.', 'info')
            self.on_done([], files)
            return

        # ── Phase 2: dimension gate for images ─────────────────
        self.on_log('Phase 2 — grouping images by dimensions…', 'info')
        img_size_groups = defaultdict(list)
        other_candidates = []
        dim_cache = {}

        for f in candidates:
            if self._stop.is_set(): break
            if f['ext'] in PIXEL_EXTS:
                dims = dim_cache.get(f['path'])
                if dims is None:
                    dims = get_image_dimensions(f['path'])
                    dim_cache[f['path']] = dims
                if dims:
                    # Key = (file_size, width, height) — must match all three
                    img_size_groups[(f['size'], dims[0], dims[1])].append(f)
                else:
                    other_candidates.append(f)
            else:
                other_candidates.append(f)

        # Images with unique size+dimension combo cannot be duplicates
        img_candidates = [f for grp in img_size_groups.values()
                          if len(grp) > 1 for f in grp]
        dim_skipped = sum(len(grp) for grp in img_size_groups.values()
                          if len(grp) == 1)
        self.on_log(
            f'Dimension gate: {dim_skipped} unique-dimension images skipped, '
            f'{len(img_candidates)} image candidates + '
            f'{len(other_candidates)} video/audio candidates remain', 'info')
        self.on_progress(18, 0, 1, 0)

        # ── Phase 3: direct comparison ─────────────────────────
        self.on_log('Phase 3 — direct pixel/byte comparison…', 'info')
        all_to_compare = img_candidates + other_candidates
        dup_groups = []
        compared   = 0
        t0         = time.time()

        # We process by candidate groups (files already grouped by size+dim)
        # Build final comparison groups
        compare_groups = list(img_size_groups.values())
        # Add back other candidates grouped by size
        other_by_size = defaultdict(list)
        for f in other_candidates:
            other_by_size[(f['size'], f['kind'])].append(f)
        for grp in other_by_size.values():
            if len(grp) > 1:
                compare_groups.append(grp)

        compare_groups = [g for g in compare_groups if len(g) > 1]
        total_pairs = sum(
            len(g)*(len(g)-1)//2 for g in compare_groups
        )
        self.on_log(f'Comparing {total_pairs} pairs across '
                    f'{len(compare_groups)} candidate groups…', 'info')

        pairs_done = 0
        for group in compare_groups:
            if self._stop.is_set(): break

            visited  = [False] * len(group)
            for i in range(len(group)):
                if self._stop.is_set(): break
                if visited[i]: continue

                cluster = [group[i]]
                for j in range(i + 1, len(group)):
                    if self._stop.is_set(): break
                    if visited[j]: continue

                    fa = group[i]['path']
                    fb = group[j]['path']
                    is_dup = (
                        pixels_equal(fa, fb)
                        if group[i]['ext'] in PIXEL_EXTS
                        else bytes_equal(fa, fb)
                    )
                    if is_dup:
                        cluster.append(group[j])
                        visited[j] = True

                    pairs_done += 1
                    if pairs_done % 5 == 0 or total_pairs < 20:
                        elapsed = time.time() - t0
                        speed   = pairs_done / elapsed if elapsed > 0 else 0
                        pct     = 18 + int(pairs_done / max(1,total_pairs) * 80)
                        self.on_progress(min(98, pct), pairs_done, total_pairs, speed)

                visited[i] = True
                if len(cluster) > 1:
                    dup_groups.append(
                        sorted(cluster, key=lambda x: x['mtime'])
                    )

        if self._stop.is_set():
            self.on_log('Scan cancelled.', 'warn')
            self.on_done([], [])
            return

        self.on_progress(100, total_pairs, total_pairs, 0)
        self.on_log(
            f'Scan complete — {len(dup_groups)} duplicate groups found',
            'ok' if dup_groups else 'info')
        self.on_done(dup_groups, files)


# ═════════════════════════════════════════════════════════════════
#  RECYCLE BIN
# ═════════════════════════════════════════════════════════════════
class RecycleBin:
    def __init__(self):
        os.makedirs(TRASH_DIR, exist_ok=True)
        self._log = os.path.join(TRASH_DIR, 'manifest.json')
        self._load()

    def _load(self):
        try:
            with open(self._log) as f: self.records = json.load(f)
        except: self.records = []

    def _save(self):
        with open(self._log, 'w') as f: json.dump(self.records, f, indent=2)

    def send(self, path):
        name = os.path.basename(path)
        ts   = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        dest = os.path.join(TRASH_DIR, f'{ts}_{name}')
        shutil.move(path, dest)
        self.records.append({'original': path, 'trash': dest, 'when': ts})
        self._save()

    def restore_all(self):
        ok = fail = 0
        for rec in list(self.records):
            try:
                os.makedirs(os.path.dirname(rec['original']), exist_ok=True)
                shutil.move(rec['trash'], rec['original'])
                self.records.remove(rec); ok += 1
            except: fail += 1
        self._save(); return ok, fail

    def restore_one(self, tp):
        for rec in self.records:
            if rec['trash'] == tp:
                os.makedirs(os.path.dirname(rec['original']), exist_ok=True)
                shutil.move(rec['trash'], rec['original'])
                self.records.remove(rec); self._save(); return True
        return False

    def empty(self):
        for rec in self.records:
            try: os.remove(rec['trash'])
            except: pass
        self.records.clear(); self._save()

    def count(self): return len(self.records)
    def total_size(self):
        s = 0
        for rec in self.records:
            try: s += os.path.getsize(rec['trash'])
            except: pass
        return s

BIN = RecycleBin()


# ═════════════════════════════════════════════════════════════════
#  REPORT GENERATOR
# ═════════════════════════════════════════════════════════════════
def generate_html_report(dup_groups, all_files, scan_start, scan_end):
    os.makedirs(REPORTS_DIR, exist_ok=True)
    ts   = datetime.now().strftime('%Y%m%d_%H%M%S')
    path = os.path.join(REPORTS_DIR, f'PixelPhantom_Report_{ts}.html')
    dups  = sum(len(g)-1 for g in dup_groups)
    saved = sum(f['size'] for g in dup_groups for f in g[1:])
    rows  = ''
    for gi, group in enumerate(dup_groups):
        for fi, f in enumerate(group):
            role  = 'KEEP' if fi == 0 else 'DUPLICATE'
            color = '#3ddc84' if fi == 0 else '#ff4d5e'
            rows += (
                f'<tr><td>{gi+1}</td>'
                f'<td style="color:{color};font-weight:600">{role}</td>'
                f'<td>{f["name"]}</td><td>{f["kind"].upper()}</td>'
                f'<td>{human_size(f["size"])}</td>'
                f'<td>{human_time(f["mtime"])}</td>'
                f'<td style="font-size:11px;color:#666">{f["path"]}</td></tr>\n'
            )
    html = f'''<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>PixelPhantom Report {ts}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#0d0d0d;color:#f0f0f0;
     font-family:"IBM Plex Mono",Consolas,monospace;padding:32px}}
.hdr{{border-left:4px solid {_accent};padding-left:20px;margin-bottom:28px}}
.title{{font-size:26px;font-weight:700;color:{_accent}}}
.tag{{font-size:12px;color:#555;margin-top:4px}}
.meta{{font-size:12px;color:#aaa;margin-top:10px;line-height:2}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));
        gap:10px;margin:20px 0}}
.card{{background:#1c1c1c;border:0.5px solid #2a2a2a;border-radius:10px;
       padding:14px;text-align:center}}
.cn{{font-size:26px;font-weight:700;color:{_accent}}}
.cl{{font-size:10px;color:#555;margin-top:3px;text-transform:uppercase;
     letter-spacing:0.5px}}
.sec{{font-size:10px;letter-spacing:1.5px;color:#555;text-transform:uppercase;
      margin:24px 0 10px;padding-bottom:6px;border-bottom:0.5px solid #2a2a2a}}
table{{width:100%;border-collapse:collapse;font-size:12px}}
th{{background:#1c1c1c;color:#555;padding:9px 12px;text-align:left;
    border-bottom:0.5px solid #2a2a2a;font-weight:500}}
td{{padding:7px 12px;border-bottom:0.5px solid #141414;vertical-align:middle}}
tr:hover td{{background:#141414}}
.foot{{margin-top:36px;padding-top:16px;border-top:0.5px solid #2a2a2a;
       font-size:11px;color:#404040;line-height:2}}
a{{color:{_accent};text-decoration:none}}
.badge{{display:inline-block;font-size:10px;padding:2px 8px;border-radius:4px;
        background:#1c1c1c;border:0.5px solid #2a2a2a;color:#aaa;margin-top:6px}}
</style></head><body>
<div class="hdr">
  <div class="title">{APP_NAME.upper()}</div>
  <div class="tag">{APP_TAGLINE}</div>
  <div class="badge">Detection: Pure pixel comparison · Zero hashing · Zero quality loss</div>
  <div class="meta">
    Report: {datetime.now().strftime("%A, %d %B %Y at %H:%M:%S")}<br>
    Scan duration: {human_secs(scan_end - scan_start)}<br>
    Files scanned: {len(all_files)}<br>
    Version: {APP_VER}
  </div>
</div>
<div class="cards">
  <div class="card"><div class="cn">{len(all_files)}</div><div class="cl">files scanned</div></div>
  <div class="card"><div class="cn">{len(dup_groups)}</div><div class="cl">dup groups</div></div>
  <div class="card"><div class="cn">{dups}</div><div class="cl">duplicates</div></div>
  <div class="card"><div class="cn" style="font-size:18px">{human_size(saved)}</div><div class="cl">space saveable</div></div>
  <div class="card"><div class="cn">{sum(1 for f in all_files if f["kind"]=="image")}</div><div class="cl">images</div></div>
  <div class="card"><div class="cn">{sum(1 for f in all_files if f["kind"]=="video")}</div><div class="cl">videos</div></div>
  <div class="card"><div class="cn">{sum(1 for f in all_files if f["kind"]=="audio")}</div><div class="cl">audio</div></div>
</div>
<div class="sec">Duplicate groups</div>
<table>
  <thead><tr><th>Group</th><th>Role</th><th>Filename</th><th>Type</th>
  <th>Size</th><th>Modified</th><th>Full Path</th></tr></thead>
  <tbody>{rows}</tbody>
</table>
<div class="foot">
  Generated by <strong>{APP_NAME} v{APP_VER}</strong> &nbsp;·&nbsp;
  Developer: <a href="{DEV_GITHUB}">{DEV_NAME}</a> &nbsp;·&nbsp;
  <a href="mailto:{DEV_EMAIL}">{DEV_EMAIL}</a> &nbsp;·&nbsp;
  {APP_LICENSE} License &nbsp;·&nbsp; {APP_YEAR}
</div>
</body></html>'''
    with open(path, 'w', encoding='utf-8') as f: f.write(html)
    return path


# ═════════════════════════════════════════════════════════════════
#  SCROLLABLE FRAME
# ═════════════════════════════════════════════════════════════════
class ScrollFrame(tk.Frame):
    def __init__(self, parent, **kw):
        bg = kw.pop('bg', C['bg'])
        super().__init__(parent, bg=bg, **kw)
        self._cv  = tk.Canvas(self, bg=bg, highlightthickness=0)
        self._vsb = ttk.Scrollbar(self, orient='vertical', command=self._cv.yview)
        self._cv.configure(yscrollcommand=self._vsb.set)
        self._vsb.pack(side='right', fill='y')
        self._cv.pack(side='left', fill='both', expand=True)
        self.inner = tk.Frame(self._cv, bg=bg)
        self._win  = self._cv.create_window((0, 0), window=self.inner, anchor='nw')
        self.inner.bind('<Configure>',
            lambda e: self._cv.configure(scrollregion=self._cv.bbox('all')))
        self._cv.bind('<Configure>',
            lambda e: self._cv.itemconfig(self._win, width=e.width))
        for seq in ('<MouseWheel>', '<Button-4>', '<Button-5>'):
            self._cv.bind_all(seq, self._on_scroll, add='+')

    def _on_scroll(self, e):
        if e.num == 4 or e.delta > 0: self._cv.yview_scroll(-1, 'units')
        else:                          self._cv.yview_scroll( 1, 'units')

    def recolour(self, bg):
        self._cv.configure(bg=bg)
        self.configure(bg=bg)
        self.inner.configure(bg=bg)


# ═════════════════════════════════════════════════════════════════
#  IN-WINDOW PROGRESS PANEL  (replaces the broken overlay)
# ═════════════════════════════════════════════════════════════════
class ProgressPanel(tk.Frame):
    """
    Animated in-window progress panel.
    Sits inside the main window — no Toplevel, no alpha, nothing to get stuck.
    Shows spinning ring + status + progress bar.
    Call .show() to display, .hide() to remove.
    """
    def __init__(self, parent):
        super().__init__(parent, bg='#000000')
        self._running  = False
        self._frame    = 0
        self._dot_f    = 0
        self._after_ids = []
        self._build()

    def _build(self):
        self._cv = tk.Canvas(self, bg='#0a0a0a', highlightthickness=0)
        self._cv.pack(fill='both', expand=True)

    def show(self):
        self.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.lift()
        self._running = True
        w = self.winfo_width()  or 900
        h = self.winfo_height() or 600
        self._draw(w, h)
        self._spin()
        self._blink()

    def _draw(self, w, h):
        self._cv.delete('all')
        cx, cy = w // 2, h // 2

        # Spinning ring dots
        n, r = 16, 60
        self._dots = []
        for i in range(n):
            a  = 2 * math.pi * i / n
            dx = cx + r * math.cos(a - math.pi / 2)
            dy = cy - 70 + r * math.sin(a - math.pi / 2)
            d  = self._cv.create_oval(dx-4, dy-4, dx+4, dy+4,
                                       fill='#1a1a1a', outline='')
            self._dots.append(d)

        # Title
        self._cv.create_text(cx, cy + 18, text=APP_NAME.upper(),
            fill=C['accent'], font=('IBM Plex Mono', 28, 'bold'), anchor='center')
        self._cv.create_text(cx, cy + 48, text=APP_TAGLINE,
            fill='#444444', font=('IBM Plex Mono', 10), anchor='center')

        # Ellipsis
        self._ell = self._cv.create_text(cx, cy + 70, text='',
            fill='#555555', font=('IBM Plex Mono', 12), anchor='center')

        # Status lines
        self._st1 = self._cv.create_text(cx, cy + 100, text='starting…',
            fill='#666666', font=('IBM Plex Mono', 11), anchor='center')
        self._st2 = self._cv.create_text(cx, cy + 120, text='',
            fill='#444444', font=('IBM Plex Mono', 10), anchor='center')

        # Progress bar
        bw, bh = 360, 4
        bx, by = cx - bw // 2, cy + 150
        self._cv.create_rectangle(bx, by, bx+bw, by+bh,
            fill='#1a1a1a', outline='')
        self._bar     = self._cv.create_rectangle(bx, by, bx, by+bh,
            fill=C['accent'], outline='')
        self._bar_bx  = bx
        self._bar_bw  = bw
        self._pct_lbl = self._cv.create_text(cx, by + 18, text='0%',
            fill='#444444', font=('IBM Plex Mono', 9), anchor='center')

    def _spin(self):
        if not self._running: return
        n = len(self._dots) if hasattr(self, '_dots') else 0
        if n == 0:
            aid = self.after(55, self._spin); self._after_ids.append(aid); return
        ar, ag, ab = (int(C['accent'][1:3], 16),
                      int(C['accent'][3:5], 16),
                      int(C['accent'][5:7], 16))
        for i, dot in enumerate(self._dots):
            phase = (self._frame - i) % n
            t = 1 - phase / n
            r2 = int(0x1a + (ar - 0x1a) * t)
            g2 = int(0x1a + (ag - 0x1a) * t)
            b2 = int(0x1a + (ab - 0x1a) * t)
            try:
                self._cv.itemconfig(dot, fill=f'#{r2:02x}{g2:02x}{b2:02x}')
            except tk.TclError:
                return
        self._frame = (self._frame + 1) % n
        aid = self.after(55, self._spin)
        self._after_ids.append(aid)

    def _blink(self):
        if not self._running: return
        try:
            dots = '·' * (self._dot_f % 4)
            self._cv.itemconfig(self._ell, text=dots)
        except tk.TclError:
            return
        self._dot_f += 1
        aid = self.after(380, self._blink)
        self._after_ids.append(aid)

    def update_progress(self, pct, line1='', line2=''):
        if not self._running: return
        try:
            fill_w = int(self._bar_bw * pct / 100)
            self._cv.coords(self._bar,
                self._bar_bx, 0,
                self._bar_bx + fill_w, 4)
            # recalculate y from stored coords
            bar_coords = self._cv.coords(self._bar)
            if len(bar_coords) == 4:
                by = bar_coords[1]
                self._cv.coords(self._bar,
                    self._bar_bx, by,
                    self._bar_bx + fill_w, by + 4)
            self._cv.itemconfig(self._pct_lbl, text=f'{pct}%')
            if line1: self._cv.itemconfig(self._st1, text=line1)
            if line2: self._cv.itemconfig(self._st2, text=line2)
        except tk.TclError:
            pass

    def hide(self):
        self._running = False
        for aid in self._after_ids:
            try: self.after_cancel(aid)
            except: pass
        self._after_ids.clear()
        self.place_forget()


# ═════════════════════════════════════════════════════════════════
#  APPEARANCE WINDOW
# ═════════════════════════════════════════════════════════════════
class AppearanceWindow(tk.Toplevel):
    def __init__(self, parent, on_apply):
        super().__init__(parent)
        self.title('Appearance')
        self.configure(bg=C['bg'])
        self.geometry('480x520')
        self.resizable(False, False)
        self._on_apply   = on_apply
        self._sel_theme  = tk.StringVar(value=_theme)
        self._sel_accent = _accent
        self._build()

    def _build(self):
        tk.Frame(self, bg=C['accent'], height=4).pack(fill='x')
        tk.Label(self, text='APPEARANCE', bg=C['bg'], fg=C['accent'],
                 font=('IBM Plex Mono', 14, 'bold')).pack(anchor='w', padx=24, pady=(18,4))
        tk.Frame(self, bg=C['border'], height=1).pack(fill='x', padx=24, pady=(0,14))

        # Theme
        tk.Label(self, text='THEME', bg=C['bg'], fg=C['text3'],
                 font=('IBM Plex Mono', 9, 'bold')).pack(anchor='w', padx=24)
        tf = tk.Frame(self, bg=C['bg']); tf.pack(anchor='w', padx=24, pady=(6,12))
        for label, val in [('Dark', 'dark'), ('Light', 'light')]:
            tk.Radiobutton(tf, text=label, variable=self._sel_theme, value=val,
                           bg=C['bg'], fg=C['text'], selectcolor=C['bg2'],
                           activebackground=C['bg'], activeforeground=C['accent'],
                           font=('IBM Plex Mono', 11)).pack(side='left', padx=(0, 20))

        tk.Frame(self, bg=C['border'], height=1).pack(fill='x', padx=24)
        tk.Label(self, text='ACCENT COLOR', bg=C['bg'], fg=C['text3'],
                 font=('IBM Plex Mono', 9, 'bold')).pack(anchor='w', padx=24, pady=(12,6))

        # Swatches
        grid = tk.Frame(self, bg=C['bg']); grid.pack(anchor='w', padx=24, pady=(0,4))
        for i, (hx, name) in enumerate(ACCENTS):
            row, col = divmod(i, 5)
            f = tk.Frame(grid, bg=hx, width=46, height=34, cursor='hand2')
            f.grid(row=row, column=col, padx=3, pady=3)
            f.pack_propagate(False)
            lbl = tk.Label(f, text='', bg=hx, cursor='hand2')
            lbl.pack(fill='both', expand=True)
            lbl.bind('<Button-1>', lambda e, h=hx: self._pick(h))
            f.bind('<Button-1>',   lambda e, h=hx: self._pick(h))

        # Custom
        cr = tk.Frame(self, bg=C['bg']); cr.pack(anchor='w', padx=24, pady=6)
        tk.Button(cr, text='Pick custom…', command=self._custom,
                  bg=C['bg3'], fg=C['text'], relief='flat',
                  font=('IBM Plex Mono', 10), padx=12, pady=5).pack(side='left')
        self._clbl = tk.Label(cr, text=f'  {self._sel_accent}',
                               bg=C['bg'], fg=C['text2'],
                               font=('IBM Plex Mono', 10))
        self._clbl.pack(side='left', padx=8)

        tk.Frame(self, bg=C['border'], height=1).pack(fill='x', padx=24, pady=10)
        self._strip = tk.Frame(self, bg=self._sel_accent, height=6)
        self._strip.pack(fill='x', padx=24, pady=(0,14))

        br = tk.Frame(self, bg=C['bg']); br.pack(pady=10)
        tk.Button(br, text='Apply', command=self._apply,
                  bg=C['accent'], fg='#0d0d0d', relief='flat',
                  font=('IBM Plex Mono', 11, 'bold'),
                  padx=22, pady=8).pack(side='left', padx=6)
        tk.Button(br, text='Cancel', command=self.destroy,
                  bg=C['bg3'], fg=C['text'], relief='flat',
                  font=('IBM Plex Mono', 10),
                  padx=16, pady=8).pack(side='left', padx=6)

    def _pick(self, h):
        self._sel_accent = h
        self._clbl.config(text=f'  {h}')
        self._strip.config(bg=h)

    def _custom(self):
        r = colorchooser.askcolor(color=self._sel_accent, title='Pick accent')
        if r and r[1]: self._pick(r[1])

    def _apply(self):
        self._on_apply(self._sel_theme.get(), self._sel_accent)
        self.destroy()


# ═════════════════════════════════════════════════════════════════
#  COMPARE WINDOW
# ═════════════════════════════════════════════════════════════════
class CompareWindow(tk.Toplevel):
    def __init__(self, parent, groups):
        super().__init__(parent)
        self.title('Compare — side by side')
        self.configure(bg=C['bg'])
        self.geometry('1060x680')
        self.groups = groups; self.idx = 0; self._imgs = []
        self._build(); self._load()

    def _build(self):
        top = tk.Frame(self, bg=C['bg1'], height=46)
        top.pack(fill='x'); top.pack_propagate(False)
        self._nav = tk.Label(top, text='', bg=C['bg1'], fg=C['text2'],
                              font=('IBM Plex Mono', 10))
        self._nav.pack(side='left', padx=16, pady=13)
        for txt, cmd in [('next →', self._next), ('← prev', self._prev)]:
            tk.Button(top, text=txt, command=cmd,
                      bg=C['bg3'], fg=C['text'],
                      activebackground=C['bg4'], activeforeground=C['accent'],
                      relief='flat', font=('IBM Plex Mono', 9),
                      padx=12, pady=5, bd=0).pack(side='right', padx=4, pady=8)

        pf = tk.Frame(self, bg=C['bg'])
        pf.pack(fill='both', expand=True, padx=10, pady=10)
        pf.grid_columnconfigure(0, weight=1)
        pf.grid_columnconfigure(1, weight=1)
        pf.grid_rowconfigure(0, weight=1)

        self._cvs = []; self._infos = []
        for col in range(2):
            f = tk.Frame(pf, bg=C['bg2'],
                          highlightbackground=C['border2'],
                          highlightthickness=1)
            f.grid(row=0, column=col, sticky='nsew', padx=4)
            lbl = tk.Label(f, text='', bg=C['bg2'], fg=C['text2'],
                            font=('IBM Plex Mono', 9), anchor='w', justify='left')
            lbl.pack(fill='x', padx=10, pady=(10,4))
            self._infos.append(lbl)
            c = tk.Canvas(f, bg=C['bg3'], highlightthickness=0)
            c.pack(fill='both', expand=True, padx=6, pady=(0,6))
            self._cvs.append(c)

    def _load(self):
        g = self.groups[self.idx]; self._imgs = []
        self._nav.config(
            text=f'Group {self.idx+1} of {len(self.groups)}  ·  {len(g)} copies')
        for i, f in enumerate(g[:2]):
            role = 'KEEP' if i == 0 else 'DUPLICATE'
            self._infos[i].config(
                text=f'{role}: {f["name"]}\n'
                     f'{human_size(f["size"])}  ·  {human_time(f["mtime"])}\n'
                     f'{f["path"]}',
                fg=C['green'] if i == 0 else C['red'])
            self._show_img(self._cvs[i], f['path'])

    def _show_img(self, cv, path):
        cv.delete('all')
        ext = Path(path).suffix.lower()
        if not PIL_OK or ext not in PIXEL_EXTS:
            cv.create_text(200, 120, text='Preview not available',
                           fill=C['text3'], font=('IBM Plex Mono', 11))
            return
        try:
            from PIL import ImageTk
            self.update_idletasks()
            w = max(cv.winfo_width(), 440)
            h = max(cv.winfo_height(), 440)
            with Image.open(path) as img:
                img.thumbnail((w-16, h-16), Image.LANCZOS)
                tk_img = ImageTk.PhotoImage(img)
                self._imgs.append(tk_img)
                cv.create_image(w//2, h//2, anchor='center', image=tk_img)
        except Exception as e:
            cv.create_text(20, 20, text=f'Error: {e}',
                           fill=C['red'], font=('IBM Plex Mono', 10), anchor='nw')

    def _prev(self):
        if self.idx > 0: self.idx -= 1; self._load()

    def _next(self):
        if self.idx < len(self.groups) - 1: self.idx += 1; self._load()


# ═════════════════════════════════════════════════════════════════
#  MAIN APPLICATION
# ═════════════════════════════════════════════════════════════════
class PixelPhantom(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry('1240x860')
        self.minsize(1020, 680)
        self.configure(bg=C['bg'])

        self._folders    = []
        self._protected  = []
        self._dup_groups = []
        self._all_files  = []
        self._engine     = None
        self._scan_start = 0
        self._scan_end   = 0
        self._prev_img   = None
        self._sframes    = []

        self._setup_style()
        self._build_ui()

        self._log(f'{APP_NAME} v{APP_VER} — {APP_TAGLINE}', 'ok')
        self._log(f'Developer: {DEV_NAME}  ·  {DEV_GITHUB}', 'info')
        self._log(f'Pillow: {"✓ installed — pixel comparison active" if PIL_OK else "✗ not found → pip install Pillow  (byte comparison fallback active)"}',
                  'ok' if PIL_OK else 'warn')
        self._log(f'Detection: {"Direct pixel comparison (PIL tobytes)" if PIL_OK else "Byte-level file comparison"}', 'info')
        self._log(f'Workers: {WORKERS} threads', 'info')

    # ── style ─────────────────────────────────────────────────────
    def _setup_style(self):
        s = ttk.Style(self); s.theme_use('clam')
        s.configure('.', background=C['bg'], foreground=C['text'],
                    fieldbackground=C['bg2'],
                    font=('IBM Plex Mono', 10), borderwidth=0, relief='flat')
        s.configure('TNotebook', background=C['bg'], borderwidth=0)
        s.configure('TNotebook.Tab', background=C['bg1'],
                    foreground=C['text3'], padding=[22, 10],
                    font=('IBM Plex Mono', 10, 'bold'), borderwidth=0)
        s.map('TNotebook.Tab',
              background=[('selected', C['bg2'])],
              foreground=[('selected', C['accent'])])
        s.configure('Treeview', background=C['bg1'], foreground=C['text'],
                    fieldbackground=C['bg1'], rowheight=28,
                    font=('IBM Plex Mono', 10), borderwidth=0)
        s.configure('Treeview.Heading', background=C['bg2'],
                    foreground=C['text3'],
                    font=('IBM Plex Mono', 9, 'bold'),
                    borderwidth=0, relief='flat')
        s.map('Treeview',
              background=[('selected', C['bg3'])],
              foreground=[('selected', C['accent'])])
        s.configure('Horizontal.TProgressbar',
                    background=C['accent'], troughcolor=C['bg3'],
                    borderwidth=0, thickness=4)
        s.configure('TScrollbar', background=C['bg2'],
                    troughcolor=C['bg1'],
                    arrowcolor=C['border2'], borderwidth=0)
        s.configure('TCheckbutton', background=C['bg'],
                    foreground=C['text'], font=('IBM Plex Mono', 10))
        s.map('TCheckbutton',
              background=[('active', C['bg'])],
              foreground=[('active', C['accent'])])

    def _reapply_style(self):
        self._setup_style()
        self.configure(bg=C['bg'])
        for sf in self._sframes: sf.recolour(C['bg'])
        self._retheme_widget(self)

    def _retheme_widget(self, w):
        cls = w.winfo_class()
        try:
            if cls in ('Frame','Label','Checkbutton','Radiobutton',
                       'Listbox','Text','Canvas','Entry'):
                w.configure(bg=C['bg'])
            if cls == 'Label': w.configure(fg=C['text'])
        except: pass
        for child in w.winfo_children():
            self._retheme_widget(child)

    # ── skeleton ──────────────────────────────────────────────────
    def _build_ui(self):
        # Header
        hdr = tk.Frame(self, bg=C['bg1'], height=54)
        hdr.pack(fill='x'); hdr.pack_propagate(False)
        tk.Frame(hdr, bg=C['accent'], width=4).pack(side='left', fill='y')
        tk.Label(hdr, text=APP_NAME.upper(), bg=C['bg1'], fg=C['accent'],
                 font=('IBM Plex Mono', 20, 'bold')).pack(side='left', padx=18)
        tk.Label(hdr, text=APP_TAGLINE, bg=C['bg1'], fg=C['text3'],
                 font=('IBM Plex Mono', 10)).pack(side='left')
        tk.Label(hdr, text=f'v{APP_VER}', bg=C['bg1'], fg=C['text3'],
                 font=('IBM Plex Mono', 9)).pack(side='right', padx=16)
        tk.Frame(hdr, bg=C['border'], width=1).pack(side='right', fill='y')
        self._acbtn(hdr, 'appearance', self._open_appearance
                    ).pack(side='right', padx=10, pady=10)
        tk.Frame(self, bg=C['border'], height=1).pack(fill='x')

        # Notebook
        self._nb = ttk.Notebook(self)
        self._nb.pack(fill='both', expand=True)
        self._tabs = {}
        for name in ['  SCAN  ','  RESULTS  ','  PREVIEW  ',
                     '  MOVE  ','  RECYCLE BIN  ',
                     '  EXPORT  ','  SETTINGS  ','  LOG  ','  ABOUT  ']:
            f = tk.Frame(self._nb, bg=C['bg'])
            self._nb.add(f, text=name)
            self._tabs[name.strip()] = f

        self._build_scan(self._tabs['SCAN'])
        self._build_results(self._tabs['RESULTS'])
        self._build_preview(self._tabs['PREVIEW'])
        self._build_move(self._tabs['MOVE'])
        self._build_bin(self._tabs['RECYCLE BIN'])
        self._build_export(self._tabs['EXPORT'])
        self._build_settings(self._tabs['SETTINGS'])
        self._build_log(self._tabs['LOG'])
        self._build_about(self._tabs['ABOUT'])

        # Status bar
        sb = tk.Frame(self, bg=C['bg2'], height=26)
        sb.pack(fill='x', side='bottom'); sb.pack_propagate(False)
        tk.Frame(sb, bg=C['accent'], width=3).pack(side='left', fill='y')
        self._status = tk.StringVar(value='Ready — add a folder to begin')
        tk.Label(sb, textvariable=self._status, bg=C['bg2'], fg=C['text3'],
                 font=('IBM Plex Mono', 9), anchor='w').pack(side='left', padx=10)
        self._bin_lbl = tk.Label(sb, text='', bg=C['bg2'], fg=C['amber'],
                                  font=('IBM Plex Mono', 9))
        self._bin_lbl.pack(side='right', padx=12)
        self._refresh_bin_label()

    # ── widget factories ──────────────────────────────────────────
    def _btn(self, p, text, cmd, danger=False):
        bg = C['red_dim'] if danger else C['bg3']
        fg = C['red']     if danger else C['text2']
        return tk.Button(p, text=text, command=cmd, bg=bg, fg=fg,
                         activebackground=C['bg4'],
                         activeforeground=C['accent'],
                         relief='flat', font=('IBM Plex Mono', 9),
                         padx=12, pady=5, cursor='hand2', bd=0)

    def _acbtn(self, p, text, cmd):
        return tk.Button(p, text=text, command=cmd,
                         bg=C['accent_dim'], fg=C['accent'],
                         activebackground=C['bg4'],
                         activeforeground=C['accent'],
                         relief='flat', font=('IBM Plex Mono', 9, 'bold'),
                         padx=12, pady=5, cursor='hand2', bd=0)

    def _sec(self, p, title):
        f = tk.Frame(p, bg=C['bg']); f.pack(fill='x', padx=16, pady=(16,2))
        tk.Label(f, text=title, bg=C['bg'], fg=C['text3'],
                 font=('IBM Plex Mono', 9, 'bold')).pack(side='left')
        tk.Frame(f, bg=C['border'], height=1).pack(
            side='left', fill='x', expand=True, padx=(8,0))

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  SCAN TAB
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    def _build_scan(self, p):
        outer = tk.Frame(p, bg=C['bg'])
        outer.pack(fill='both', expand=True)
        outer.grid_columnconfigure(0, weight=1)
        outer.grid_columnconfigure(1, minsize=260)
        outer.grid_rowconfigure(0, weight=1)

        sf = ScrollFrame(outer, bg=C['bg'])
        sf.grid(row=0, column=0, sticky='nsew')
        self._sframes.append(sf); left = sf.inner

        right = tk.Frame(outer, bg=C['bg'], width=260)
        right.grid(row=0, column=1, sticky='ns')
        right.pack_propagate(False)

        # Source folders
        self._sec(left, 'SOURCE FOLDERS')
        fr = tk.Frame(left, bg=C['bg']); fr.pack(fill='x', padx=16, pady=(6,0))
        self._acbtn(fr, '+ Add folder',    self._add_folder).pack(side='left', padx=(0,6))
        self._acbtn(fr, '+ Add multiple',  self._add_multi ).pack(side='left', padx=(0,6))
        self._btn(  fr, 'Clear all',        self._clear_folders).pack(side='left')
        self._flist = tk.Listbox(left, bg=C['bg2'], fg=C['text'],
                                  font=('IBM Plex Mono', 10), height=5,
                                  selectbackground=C['bg3'],
                                  selectforeground=C['accent'],
                                  relief='flat', highlightthickness=1,
                                  highlightbackground=C['border'])
        self._flist.pack(fill='x', padx=16, pady=(6,0))
        rr = tk.Frame(left, bg=C['bg']); rr.pack(fill='x', padx=16, pady=2)
        self._btn(rr, '✕ Remove selected', self._remove_folder).pack(side='left')

        # How it works info box
        self._sec(left, 'HOW DETECTION WORKS')
        info = tk.Frame(left, bg=C['bg2'],
                         highlightbackground=C['border'],
                         highlightthickness=1)
        info.pack(fill='x', padx=16, pady=(4,0))
        lines = [
            '1. Group by file size  (free — no reading)',
            '2. Group images by dimensions  (very fast)',
            '3. Compare pixel R,G,B values directly  (exact)',
            '   Videos / Audio compared byte-by-byte',
            '',
            'Files are opened READ-ONLY.',
            'No re-encoding. No quality loss. Ever.',
        ]
        for line in lines:
            tk.Label(info, text=line, bg=C['bg2'],
                     fg=C['accent'] if line.startswith('  ') or 'READ' in line
                        else C['text2'],
                     font=('IBM Plex Mono', 9),
                     anchor='w').pack(anchor='w', padx=12, pady=1)
        tk.Frame(info, bg=C['bg2'], height=6).pack()

        # Tolerance (for images only — allows 0 diff pixels)
        self._sec(left, 'SENSITIVITY')
        tr = tk.Frame(left, bg=C['bg']); tr.pack(fill='x', padx=16, pady=(4,0))
        tk.Label(tr, text='Pixel tolerance:', bg=C['bg'],
                 fg=C['text3'], font=('IBM Plex Mono', 10)).pack(side='left', padx=(0,8))
        self._tol_var = tk.IntVar(value=0)
        self._tol_lbl = tk.Label(tr, text='0', bg=C['bg'], fg=C['accent'],
                                  font=('IBM Plex Mono', 10, 'bold'), width=3)
        self._tol_lbl.pack(side='left')
        tk.Scale(tr, from_=0, to=10, orient='horizontal',
                 variable=self._tol_var,
                 bg=C['bg'], fg=C['text'], troughcolor=C['bg3'],
                 highlightthickness=0, sliderrelief='flat',
                 width=8, length=160,
                 command=lambda v: self._tol_lbl.config(
                     text=str(int(float(v))))).pack(side='left', padx=4)
        tk.Label(tr, text='(0 = exact match)', bg=C['bg'],
                 fg=C['text3'], font=('IBM Plex Mono', 9)).pack(side='left', padx=8)

        # Progress
        self._sec(left, 'PROGRESS')
        self._prog = ttk.Progressbar(left, mode='determinate',
                                      style='Horizontal.TProgressbar')
        self._prog.pack(fill='x', padx=16, pady=(6,2))
        pr = tk.Frame(left, bg=C['bg']); pr.pack(fill='x', padx=16)
        self._prog_lbl = tk.Label(pr, text='idle', bg=C['bg'],
                                   fg=C['text3'], font=('IBM Plex Mono', 10))
        self._prog_lbl.pack(side='left')
        self._spd_lbl = tk.Label(pr, text='', bg=C['bg'],
                                  fg=C['accent'], font=('IBM Plex Mono', 10))
        self._spd_lbl.pack(side='right')

        # Stat cards
        sc = tk.Frame(left, bg=C['bg'])
        sc.pack(fill='x', padx=16, pady=(12,0))
        self._svars = {}
        for i, (key, label) in enumerate([
            ('files','scanned'), ('images','images'),
            ('videos','videos'), ('audio','audio'),
            ('groups','dup groups'), ('dups','duplicates'),
            ('saved','space saved')
        ]):
            v = tk.StringVar(value='—'); self._svars[key] = v
            card = tk.Frame(sc, bg=C['bg2'],
                             highlightbackground=C['border'],
                             highlightthickness=1)
            card.grid(row=i//4, column=i%4, padx=3, pady=3, sticky='ew')
            sc.grid_columnconfigure(i%4, weight=1)
            tk.Label(card, textvariable=v, bg=C['bg2'], fg=C['accent'],
                     font=('IBM Plex Mono', 15, 'bold')).pack(pady=(8,1))
            tk.Label(card, text=label, bg=C['bg2'], fg=C['text3'],
                     font=('IBM Plex Mono', 8)).pack(pady=(0,8))

        # Action buttons
        br = tk.Frame(left, bg=C['bg'])
        br.pack(fill='x', padx=16, pady=(14,20))
        self._scan_btn = self._acbtn(br, '▶  Start Scan', self._start_scan)
        self._stop_btn = self._btn(  br, '■  Stop',        self._stop_scan)
        self._scan_btn.pack(side='left', padx=(0,8))
        self._stop_btn.pack(side='left', padx=(0,8))
        self._stop_btn.config(state='disabled')

        # Right panel — protected folders
        self._sec(right, 'PROTECTED FOLDERS')
        tk.Label(right, text='Files here are never\ntouched or compared.',
                 bg=C['bg'], fg=C['text3'],
                 font=('IBM Plex Mono', 9), justify='left'
                 ).pack(anchor='w', padx=16, pady=(4,6))
        self._acbtn(right, '+ Protect folder',
                    self._add_protected).pack(anchor='w', padx=16, pady=(0,4))
        self._plist = tk.Listbox(right, bg=C['bg2'], fg=C['amber'],
                                  font=('IBM Plex Mono', 9), height=8,
                                  selectbackground=C['bg3'],
                                  relief='flat', highlightthickness=1,
                                  highlightbackground=C['border'])
        self._plist.pack(fill='x', padx=16, pady=(0,4))
        self._btn(right, '✕ Remove',
                  self._remove_protected).pack(anchor='w', padx=16)

        # Progress panel (sits inside scan tab, hidden until scan starts)
        self._prog_panel = ProgressPanel(p)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  RESULTS TAB
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    def _build_results(self, p):
        tb = tk.Frame(p, bg=C['bg'])
        tb.pack(fill='x', padx=12, pady=(10,4))
        self._acbtn(tb, 'Select all dups',  self._sel_all ).pack(side='left', padx=(0,4))
        self._btn(  tb, 'Deselect all',      self._desel_all).pack(side='left', padx=(0,4))
        self._btn(  tb, 'Keep oldest',
                    lambda: self._keep_by(lambda f: f['mtime'])
                    ).pack(side='left', padx=(0,4))
        self._btn(  tb, 'Keep newest',
                    lambda: self._keep_by(lambda f: f['mtime'], True)
                    ).pack(side='left', padx=(0,4))
        self._btn(  tb, 'Keep largest',
                    lambda: self._keep_by(lambda f: f['size'], True)
                    ).pack(side='left', padx=(0,12))
        self._btn(  tb, 'Compare…', self._open_compare).pack(side='left', padx=(0,16))

        tk.Label(tb, text='filter:', bg=C['bg'], fg=C['text3'],
                 font=('IBM Plex Mono', 10)).pack(side='left', padx=(0,4))
        self._filter_var = tk.StringVar()
        tk.Entry(tb, textvariable=self._filter_var, bg=C['bg2'], fg=C['text'],
                 insertbackground=C['accent'], relief='flat',
                 font=('IBM Plex Mono', 10), width=26
                 ).pack(side='left', ipady=4)
        self._filter_var.trace_add('write', lambda *_: self._populate_tree())

        frame = tk.Frame(p, bg=C['bg'])
        frame.pack(fill='both', expand=True, padx=12, pady=(0,10))
        cols = ('mark','grp','name','kind','size','date','path')
        self._tree = ttk.Treeview(frame, columns=cols,
                                   show='headings', selectmode='extended')
        hdrs = {'mark':'mark','grp':'grp','name':'filename',
                'kind':'type','size':'size','date':'modified','path':'path'}
        ws   = {'mark':52,'grp':52,'name':220,'kind':70,
                'size':90,'date':140,'path':400}
        for c in cols:
            self._tree.heading(c, text=hdrs[c],
                               command=lambda col=c: self._sort_tree(col))
            self._tree.column(c, width=ws[c], minwidth=40)
        vsb = ttk.Scrollbar(frame, orient='vertical',   command=self._tree.yview)
        hsb = ttk.Scrollbar(frame, orient='horizontal',  command=self._tree.xview)
        self._tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self._tree.grid(row=0, column=0, sticky='nsew')
        vsb.grid(row=0, column=1, sticky='ns')
        hsb.grid(row=1, column=0, sticky='ew')
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)
        self._tree.tag_configure('keep', foreground=C['text3'])
        self._tree.tag_configure('dup',  foreground=C['text2'])
        self._tree.tag_configure('sel',  foreground=C['accent'],
                                         background='#0d0a1a')
        self._tree.bind('<space>',    self._toggle_sel)
        self._tree.bind('<Double-1>', self._dbl_click)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  PREVIEW TAB
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    def _build_preview(self, p):
        bar = tk.Frame(p, bg=C['bg1'], height=42)
        bar.pack(fill='x'); bar.pack_propagate(False)
        self._prev_info = tk.Label(bar,
            text='Double-click any file in Results to preview',
            bg=C['bg1'], fg=C['text3'],
            font=('IBM Plex Mono', 10), anchor='w')
        self._prev_info.pack(side='left', padx=16, pady=11)
        self._prev_canvas = tk.Canvas(p, bg=C['bg2'], highlightthickness=0)
        self._prev_canvas.pack(fill='both', expand=True, padx=12, pady=12)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  MOVE TAB
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    def _build_move(self, p):
        sf = ScrollFrame(p, bg=C['bg'])
        sf.pack(fill='both', expand=True)
        self._sframes.append(sf); left = sf.inner

        self._sec(left, 'DESTINATION FOLDER')
        dr = tk.Frame(left, bg=C['bg']); dr.pack(fill='x', padx=16, pady=(6,0))
        self._dest_var = tk.StringVar()
        tk.Entry(dr, textvariable=self._dest_var, bg=C['bg2'], fg=C['text'],
                 insertbackground=C['accent'], relief='flat',
                 font=('IBM Plex Mono', 11)
                 ).pack(side='left', fill='x', expand=True, ipady=6, padx=(0,8))
        self._btn(dr, 'Browse…', self._browse_dest).pack(side='left')

        self._sec(left, 'ACTION')
        self._action_var = tk.StringVar(value='recycle')
        for label, val in [
            ('Send to recycle bin  (recommended — fully restorable)', 'recycle'),
            ('Move duplicates to destination folder',                  'move'),
            ('Copy duplicates to destination folder',                  'copy'),
            ('Permanent delete  (cannot be undone)',                   'delete'),
        ]:
            tk.Radiobutton(left, text=label, variable=self._action_var, value=val,
                           bg=C['bg'], fg=C['text2'], selectcolor=C['bg2'],
                           activebackground=C['bg'], activeforeground=C['accent'],
                           font=('IBM Plex Mono', 10)
                           ).pack(anchor='w', padx=16, pady=3)

        self._sec(left, 'SUMMARY')
        self._mv_summary = tk.Text(left, bg=C['bg1'], fg=C['text2'],
                                    font=('IBM Plex Mono', 10), height=10,
                                    relief='flat', state='disabled', wrap='word')
        self._mv_summary.pack(fill='x', padx=16, pady=(4,0))

        br = tk.Frame(left, bg=C['bg']); br.pack(fill='x', padx=16, pady=10)
        self._acbtn(br, '▶  Execute Action',    self._execute_action).pack(side='left', padx=(0,8))
        self._btn(  br, 'Refresh summary',       self._refresh_summary).pack(side='left')

        self._mv_prog = ttk.Progressbar(left, mode='determinate',
                                         style='Horizontal.TProgressbar')
        self._mv_prog.pack(fill='x', padx=16, pady=(0,4))
        self._mv_lbl = tk.Label(left, text='', bg=C['bg'],
                                 fg=C['text3'], font=('IBM Plex Mono', 9))
        self._mv_lbl.pack(anchor='w', padx=16, pady=(0,20))

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  RECYCLE BIN TAB
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    def _build_bin(self, p):
        tb = tk.Frame(p, bg=C['bg']); tb.pack(fill='x', padx=12, pady=(10,4))
        self._acbtn(tb, 'Restore all',      self._restore_all).pack(side='left', padx=(0,6))
        self._btn(  tb, 'Restore selected', self._restore_sel).pack(side='left', padx=(0,6))
        self._btn(  tb, 'Empty bin',        self._empty_bin, danger=True).pack(side='left')

        frame = tk.Frame(p, bg=C['bg'])
        frame.pack(fill='both', expand=True, padx=12, pady=(0,10))
        cols = ('name','orig','when','tp')
        self._bin_tree = ttk.Treeview(frame, columns=cols,
                                       show='headings', selectmode='extended')
        for c, w, lbl in [('name',180,'Filename'),('orig',340,'Original path'),
                            ('when',150,'Deleted'),('tp',0,'trash_path')]:
            self._bin_tree.heading(c, text=lbl)
            self._bin_tree.column(c, width=w, minwidth=40)
        self._bin_tree.column('tp', width=0, minwidth=0, stretch=False)
        vsb = ttk.Scrollbar(frame, orient='vertical', command=self._bin_tree.yview)
        self._bin_tree.configure(yscrollcommand=vsb.set)
        self._bin_tree.grid(row=0, column=0, sticky='nsew')
        vsb.grid(row=0, column=1, sticky='ns')
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)
        self._refresh_bin_tree()

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  EXPORT TAB
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    def _build_export(self, p):
        sf = ScrollFrame(p, bg=C['bg'])
        sf.pack(fill='both', expand=True)
        self._sframes.append(sf); left = sf.inner

        self._sec(left, 'EXPORT RESULTS')
        for lbl, cmd in [('Export as CSV',          self._export_csv),
                           ('Export as JSON',         self._export_json),
                           ('Export as HTML report',  self._export_html)]:
            self._btn(left, lbl, cmd).pack(anchor='w', padx=16, pady=4)

        self._sec(left, 'GENERATE REPORT')
        tk.Label(left,
                 text=f'Saves to: {REPORTS_DIR}',
                 bg=C['bg'], fg=C['text3'],
                 font=('IBM Plex Mono', 10)
                 ).pack(anchor='w', padx=16, pady=(4,6))
        self._acbtn(left, 'Generate Full Report',
                    self._gen_report).pack(anchor='w', padx=16, pady=(0,12))

        self._sec(left, 'PREVIEW')
        self._exp_prev = tk.Text(left, bg=C['bg1'], fg=C['text2'],
                                  font=('IBM Plex Mono', 9), height=18,
                                  relief='flat', state='disabled', wrap='none')
        self._exp_prev.pack(fill='x', padx=16, pady=(4,20))

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  SETTINGS TAB
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    def _build_settings(self, p):
        sf = ScrollFrame(p, bg=C['bg'])
        sf.pack(fill='both', expand=True)
        self._sframes.append(sf); left = sf.inner

        self._sec(left, 'APPEARANCE')
        self._acbtn(left, 'Open Appearance Settings…',
                    self._open_appearance).pack(anchor='w', padx=16, pady=(6,12))

        self._sec(left, 'DETECTION METHOD')
        tk.Label(left,
                 text='Images  →  pixel-by-pixel comparison (PIL Image.tobytes)\n'
                      'Videos  →  byte-by-byte file comparison\n'
                      'Audio   →  byte-by-byte file comparison\n'
                      'RAW     →  byte-by-byte file comparison\n\n'
                      'All files are opened READ-ONLY.\n'
                      'No hashing. No encoding. Zero quality loss.',
                 bg=C['bg'], fg=C['text2'],
                 font=('IBM Plex Mono', 10), justify='left'
                 ).pack(anchor='w', padx=16, pady=(4,12))

        self._sec(left, 'DEPENDENCIES')
        for name, ok, cmd in [
            ('Pillow (pixel comparison)', PIL_OK, 'pip install Pillow'),
        ]:
            row = tk.Frame(left, bg=C['bg']); row.pack(anchor='w', padx=16, pady=2)
            tk.Label(row, text=f'{"✓" if ok else "✗"}  {name}',
                     bg=C['bg'], fg=C['green'] if ok else C['red'],
                     font=('IBM Plex Mono', 10)).pack(side='left')
            if not ok:
                tk.Label(row, text=f'  →  {cmd}', bg=C['bg'],
                         fg=C['text3'], font=('IBM Plex Mono', 10)
                         ).pack(side='left')

        self._sec(left, 'SYSTEM')
        for line in [
            f'OS       : {platform.system()} {platform.release()}',
            f'Python   : {sys.version.split()[0]}',
            f'Workers  : {WORKERS} threads',
            f'Trash    : {TRASH_DIR}',
            f'Reports  : {REPORTS_DIR}',
            f'Images   : {len(IMAGE_EXTS)} extensions',
            f'Videos   : {len(VIDEO_EXTS)} extensions',
            f'Audio    : {len(AUDIO_EXTS)} extensions',
        ]:
            tk.Label(left, text=line, bg=C['bg'], fg=C['text3'],
                     font=('IBM Plex Mono', 10)
                     ).pack(anchor='w', padx=16, pady=1)
        tk.Frame(left, bg=C['bg'], height=20).pack()

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  LOG TAB
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    def _build_log(self, p):
        tb = tk.Frame(p, bg=C['bg']); tb.pack(fill='x', padx=12, pady=(10,4))
        self._btn(tb, 'Clear',     self._clear_log).pack(side='left', padx=(0,6))
        self._btn(tb, 'Save log…', self._save_log ).pack(side='left')
        self._log_txt = tk.Text(p, bg=C['bg1'], fg=C['text'],
                                 font=('IBM Plex Mono', 10),
                                 relief='flat', wrap='none', state='disabled')
        vsb = ttk.Scrollbar(p, orient='vertical', command=self._log_txt.yview)
        self._log_txt.configure(yscrollcommand=vsb.set)
        vsb.pack(side='right', fill='y', padx=(0,4), pady=4)
        self._log_txt.pack(fill='both', expand=True, padx=(12,0), pady=(0,10))
        self._log_txt.tag_configure('ok',    foreground=C['green'])
        self._log_txt.tag_configure('warn',  foreground=C['amber'])
        self._log_txt.tag_configure('error', foreground=C['red'])
        self._log_txt.tag_configure('info',  foreground=C['blue'])

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  ABOUT TAB
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    def _build_about(self, p):
        sf = ScrollFrame(p, bg=C['bg'])
        sf.pack(fill='both', expand=True)
        self._sframes.append(sf); inner = sf.inner

        logo = tk.Frame(inner, bg=C['bg']); logo.pack(pady=(32,0))
        tk.Frame(logo, bg=C['accent'], width=6, height=60
                 ).pack(side='left', padx=(0,16))
        nc = tk.Frame(logo, bg=C['bg']); nc.pack(side='left')
        tk.Label(nc, text=APP_NAME.upper(), bg=C['bg'], fg=C['accent'],
                 font=('IBM Plex Mono', 28, 'bold')).pack(anchor='w')
        tk.Label(nc, text=f'v{APP_VER}  ·  {APP_TAGLINE}',
                 bg=C['bg'], fg=C['text3'],
                 font=('IBM Plex Mono', 11)).pack(anchor='w', pady=(2,0))
        tk.Label(nc, text='Detection: Pure pixel comparison · Zero hashing · Zero quality loss',
                 bg=C['bg'], fg=C['text3'],
                 font=('IBM Plex Mono', 9)).pack(anchor='w', pady=(2,0))

        tk.Frame(inner, bg=C['border'], height=1).pack(fill='x', padx=32, pady=20)

        dc = tk.Frame(inner, bg=C['bg2'],
                       highlightbackground=C['border'], highlightthickness=1)
        dc.pack(padx=32, pady=(0,20), fill='x')
        tk.Label(dc, text='DEVELOPER', bg=C['bg2'], fg=C['text3'],
                 font=('IBM Plex Mono', 9, 'bold')
                 ).pack(anchor='w', padx=20, pady=(14,6))
        for label, val in [('Name',    DEV_NAME),
                             ('GitHub',  DEV_GITHUB),
                             ('Email',   DEV_EMAIL),
                             ('License', APP_LICENSE),
                             ('Year',    APP_YEAR)]:
            row = tk.Frame(dc, bg=C['bg2']); row.pack(fill='x', padx=20, pady=2)
            tk.Label(row, text=f'{label}:', bg=C['bg2'], fg=C['text3'],
                     font=('IBM Plex Mono', 10), width=10,
                     anchor='w').pack(side='left')
            tk.Label(row, text=val, bg=C['bg2'], fg=C['text'],
                     font=('IBM Plex Mono', 10)).pack(side='left', padx=8)
        tk.Frame(dc, bg=C['bg2'], height=12).pack()

        tk.Frame(inner, bg=C['border'], height=1).pack(fill='x', padx=32)
        tk.Label(inner, text='HOW IT WORKS', bg=C['bg'], fg=C['text3'],
                 font=('IBM Plex Mono', 9, 'bold')
                 ).pack(anchor='w', padx=32, pady=(14,8))
        for title, desc in [
            ('Phase 1 — size gate',
             'Files with unique byte sizes are skipped instantly. Free.'),
            ('Phase 2 — dimension gate',
             'Images with different pixel dimensions cannot be equal. Skipped fast.'),
            ('Phase 3 — pixel comparison',
             'Image pairs: PIL reads R,G,B per pixel and compares directly. No hash.'),
            ('Phase 3 — byte comparison',
             'Video/audio pairs: raw bytes are read and compared chunk by chunk.'),
            ('Zero modification',
             'Every file is opened read-only. No writes. No re-encoding. Ever.'),
            ('Move / Recycle',
             'Only duplicates are moved. Original files stay exactly as they were.'),
        ]:
            row = tk.Frame(inner, bg=C['bg']); row.pack(fill='x', padx=32, pady=2)
            tk.Label(row, text=f'◆  {title}', bg=C['bg'], fg=C['accent'],
                     font=('IBM Plex Mono', 10, 'bold'),
                     width=26, anchor='w').pack(side='left')
            tk.Label(row, text=desc, bg=C['bg'], fg=C['text2'],
                     font=('IBM Plex Mono', 10)).pack(side='left')

        tk.Frame(inner, bg=C['border'], height=1).pack(fill='x', padx=32, pady=20)
        tk.Label(inner,
                 text=f'© {APP_YEAR} {DEV_NAME}. {APP_LICENSE} License.',
                 bg=C['bg'], fg=C['text3'],
                 font=('IBM Plex Mono', 10)).pack(pady=(0,32))

    # ══════════════════════════════════════════════════════════════
    #  FOLDER MANAGEMENT
    # ══════════════════════════════════════════════════════════════
    def _add_folder(self):
        d = filedialog.askdirectory(title='Add source folder')
        if d and d not in self._folders:
            self._folders.append(d); self._flist.insert('end', d)

    def _add_multi(self):
        while True:
            d = filedialog.askdirectory(title='Add folder (cancel to stop)')
            if not d: break
            if d not in self._folders:
                self._folders.append(d); self._flist.insert('end', d)

    def _clear_folders(self):
        self._folders.clear(); self._flist.delete(0, 'end')

    def _remove_folder(self):
        for i in reversed(self._flist.curselection()):
            self._folders.pop(i); self._flist.delete(i)

    def _add_protected(self):
        d = filedialog.askdirectory(title='Add protected folder')
        if d and d not in self._protected:
            self._protected.append(d); self._plist.insert('end', d)

    def _remove_protected(self):
        for i in reversed(self._plist.curselection()):
            self._protected.pop(i); self._plist.delete(i)

    # ══════════════════════════════════════════════════════════════
    #  SCAN
    # ══════════════════════════════════════════════════════════════
    def _start_scan(self):
        if not self._folders:
            messagebox.showerror('No folder',
                                 'Add at least one source folder first.')
            return

        self._log('Collecting files…', 'info')
        files = collect_files(self._folders, self._protected)
        if not files:
            messagebox.showinfo('No files',
                'No supported files found in the selected folder(s).')
            return

        self._log(f'Found {len(files)} files — starting scan', 'ok')
        self._scan_btn.config(state='disabled')
        self._stop_btn.config(state='normal')
        self._dup_groups = []; self._all_files = []
        for v in self._svars.values(): v.set('…')
        self._prog['value'] = 0
        self._scan_start = time.time()

        # Show in-window progress panel
        self._prog_panel.show()

        self._engine = ScanEngine(
            files=files,
            on_progress=lambda *a: self.after(0, lambda a=a: self._upd_prog(*a)),
            on_log=lambda m, k='': self.after(0, lambda m=m, k=k: self._log(m, k)),
            on_done=lambda g, f: self.after(0, lambda g=g, f=f: self._finish(g, f)),
        )
        self._engine.start()

    def _stop_scan(self):
        if self._engine: self._engine.stop()
        self._scan_btn.config(state='normal')
        self._stop_btn.config(state='disabled')
        self._prog_panel.hide()

    def _upd_prog(self, pct, done, total, speed):
        self._prog['value'] = pct
        spd = f'{speed:.1f} pairs/s' if speed else ''
        self._prog_lbl.config(text=f'{done} / {total}')
        self._spd_lbl.config(text=spd)
        self._status.set(f'Scanning… {pct}%  {spd}')
        self._prog_panel.update_progress(
            pct,
            f'comparing {done} of {total}…',
            spd)

    def _finish(self, dup_groups, all_files):
        self._scan_end   = time.time()
        self._dup_groups = dup_groups
        self._all_files  = all_files

        self._prog_panel.hide()
        self._scan_btn.config(state='normal')
        self._stop_btn.config(state='disabled')
        self._prog['value'] = 100
        self._prog_lbl.config(text='complete')

        imgs  = sum(1 for f in all_files if f['kind'] == 'image')
        vids  = sum(1 for f in all_files if f['kind'] == 'video')
        auds  = sum(1 for f in all_files if f['kind'] == 'audio')
        dups  = sum(len(g) - 1 for g in dup_groups)
        saved = sum(f['size'] for g in dup_groups for f in g[1:])

        self._svars['files'].set(str(len(all_files)))
        self._svars['images'].set(str(imgs))
        self._svars['videos'].set(str(vids))
        self._svars['audio'].set(str(auds))
        self._svars['groups'].set(str(len(dup_groups)))
        self._svars['dups'].set(str(dups))
        self._svars['saved'].set(human_size(saved))
        self._status.set(
            f'Done  ·  {dups} duplicates in {len(dup_groups)} groups'
            f'  ·  {human_size(saved)} saveable'
            f'  ·  {human_secs(self._scan_end - self._scan_start)}')

        self._populate_tree()
        self._refresh_summary()
        if dup_groups:
            self._nb.select(1)   # jump to Results tab
        self._log(
            f'Scan finished in {human_secs(self._scan_end - self._scan_start)}'
            f' — {dups} duplicates found', 'ok')

    # ══════════════════════════════════════════════════════════════
    #  TREE
    # ══════════════════════════════════════════════════════════════
    def _populate_tree(self):
        for item in self._tree.get_children():
            self._tree.delete(item)
        ft = self._filter_var.get().lower()
        for gi, group in enumerate(self._dup_groups):
            for fi, f in enumerate(group):
                if ft and ft not in f['name'].lower() \
                       and ft not in f['path'].lower():
                    continue
                mark = 'KEEP' if fi == 0 else 'DUP'
                tag  = 'keep' if fi == 0 else 'dup'
                self._tree.insert('', 'end', iid=f['path'],
                    values=(mark, f'#{gi+1}', f['name'],
                            f['kind'].upper(),
                            human_size(f['size']),
                            human_time(f['mtime']),
                            f['path']),
                    tags=(tag,))

    def _sort_tree(self, col):
        items = [(self._tree.set(k, col), k)
                 for k in self._tree.get_children()]
        items.sort()
        for i, (_, k) in enumerate(items): self._tree.move(k, '', i)

    def _toggle_sel(self, e=None):
        for iid in self._tree.selection():
            vals = list(self._tree.item(iid, 'values'))
            if vals[0] == 'DUP':
                vals[0] = 'SEL'
                self._tree.item(iid, values=vals, tags=('sel',))
            elif vals[0] == 'SEL':
                vals[0] = 'DUP'
                self._tree.item(iid, values=vals, tags=('dup',))

    def _sel_all(self):
        for iid in self._tree.get_children():
            vals = list(self._tree.item(iid, 'values'))
            if vals[0] == 'DUP':
                vals[0] = 'SEL'
                self._tree.item(iid, values=vals, tags=('sel',))

    def _desel_all(self):
        for iid in self._tree.get_children():
            vals = list(self._tree.item(iid, 'values'))
            if vals[0] == 'SEL':
                vals[0] = 'DUP'
                self._tree.item(iid, values=vals, tags=('dup',))

    def _keep_by(self, key_fn, reverse=False):
        self._desel_all()
        for g in self._dup_groups:
            if len(g) < 2: continue
            for f in sorted(g, key=key_fn, reverse=reverse)[1:]:
                if self._tree.exists(f['path']):
                    vals = list(self._tree.item(f['path'], 'values'))
                    vals[0] = 'SEL'
                    self._tree.item(f['path'], values=vals, tags=('sel',))

    def _get_sel(self):
        return [self._tree.item(iid, 'values')[6]
                for iid in self._tree.get_children()
                if self._tree.item(iid, 'values')[0] == 'SEL']

    def _dbl_click(self, e=None):
        sel = self._tree.selection()
        if not sel: return
        path = self._tree.item(sel[0], 'values')[6]
        self._load_preview(path)
        self._nb.select(2)

    # ══════════════════════════════════════════════════════════════
    #  PREVIEW
    # ══════════════════════════════════════════════════════════════
    def _load_preview(self, path):
        self._prev_canvas.delete('all')
        try: sz = human_size(os.path.getsize(path))
        except: sz = '?'
        self._prev_info.config(text=f'{path}  ·  {sz}')
        ext = Path(path).suffix.lower()
        if not PIL_OK or ext not in PIXEL_EXTS:
            self._prev_canvas.create_text(
                300, 200,
                text=('Install Pillow for image preview\n(pip install Pillow)'
                      if not PIL_OK else f'No preview for {ext} files'),
                fill=C['text3'], font=('IBM Plex Mono', 12))
            return
        try:
            from PIL import ImageTk
            self.update_idletasks()
            cw = max(self._prev_canvas.winfo_width(),  600)
            ch = max(self._prev_canvas.winfo_height(), 400)
            with Image.open(path) as img:
                img.thumbnail((cw-20, ch-20), Image.LANCZOS)
                tk_img = ImageTk.PhotoImage(img)
                self._prev_img = tk_img
                self._prev_canvas.create_image(
                    cw//2, ch//2, anchor='center', image=tk_img)
        except Exception as e:
            self._prev_canvas.create_text(
                300, 200, text=f'Error: {e}',
                fill=C['red'], font=('IBM Plex Mono', 11))

    # ══════════════════════════════════════════════════════════════
    #  COMPARE
    # ══════════════════════════════════════════════════════════════
    def _open_compare(self):
        img_groups = [g for g in self._dup_groups
                      if any(f['kind'] == 'image' for f in g)]
        if not img_groups:
            messagebox.showinfo('No image groups',
                'No image duplicate groups to compare.'); return
        CompareWindow(self, img_groups)

    # ══════════════════════════════════════════════════════════════
    #  MOVE / ACTION
    # ══════════════════════════════════════════════════════════════
    def _browse_dest(self):
        d = filedialog.askdirectory(title='Destination folder')
        if d: self._dest_var.set(d)

    def _refresh_summary(self):
        paths = self._get_sel()
        total = sum(os.path.getsize(p) for p in paths if os.path.exists(p))
        lines = [
            f'Selected files    : {len(paths)}',
            f'Space to recover  : {human_size(total)}',
            f'Action            : {self._action_var.get().upper()}',
            f'Destination       : {self._dest_var.get() or "(not set)"}',
            '', 'Files to process:',
        ] + [f'  {p}' for p in paths[:50]]
        if len(paths) > 50:
            lines.append(f'  … and {len(paths)-50} more')
        self._mv_summary.config(state='normal')
        self._mv_summary.delete('1.0', 'end')
        self._mv_summary.insert('end', '\n'.join(lines))
        self._mv_summary.config(state='disabled')

    def _execute_action(self):
        paths  = self._get_sel()
        if not paths:
            messagebox.showinfo('Nothing selected',
                'Mark files as SEL in the Results tab first (Space key).')
            return
        action = self._action_var.get()
        dest   = self._dest_var.get().strip()
        if action in ('move', 'copy') and not dest:
            messagebox.showerror('No destination',
                'Set a destination folder in the box above.')
            return
        if action == 'delete':
            if not messagebox.askyesno(
                'Confirm delete',
                f'Permanently delete {len(paths)} files?\nThis cannot be undone.'):
                return
        if action in ('move', 'copy'):
            os.makedirs(dest, exist_ok=True)

        self._mv_prog['maximum'] = len(paths)
        self._mv_prog['value']   = 0

        def run():
            ok = fail = 0
            for i, p in enumerate(paths):
                try:
                    if   action == 'recycle': BIN.send(p)
                    elif action == 'move':    shutil.move(p,     self._sdest(dest,p,i))
                    elif action == 'copy':    shutil.copy2(p,    self._sdest(dest,p,i))
                    elif action == 'delete':  os.remove(p)
                    ok += 1
                except Exception as e:
                    self._log(f'FAIL {p}: {e}', 'error')
                    fail += 1
                self.after(0, lambda v=i+1: self._mv_prog.config(value=v))
                self.after(0, lambda t=f'{action.title()}d {i+1}/{len(paths)}':
                           self._mv_lbl.config(text=t))
            self.after(0, lambda: self._log(
                f'{action.title()} complete: {ok} ok, {fail} failed',
                'ok' if fail == 0 else 'warn'))
            self.after(0, self._refresh_bin_label)
            self.after(0, self._refresh_bin_tree)
            self.after(0, lambda: messagebox.showinfo(
                'Done', f'{ok} files processed. {fail} failed.'))

        threading.Thread(target=run, daemon=True).start()

    def _sdest(self, dest, src, idx):
        name = os.path.basename(src)
        d    = os.path.join(dest, name)
        if os.path.exists(d):
            base, ext = os.path.splitext(name)
            d = os.path.join(dest, f'{base}_{idx}{ext}')
        return d

    # ══════════════════════════════════════════════════════════════
    #  RECYCLE BIN
    # ══════════════════════════════════════════════════════════════
    def _refresh_bin_tree(self):
        for item in self._bin_tree.get_children():
            self._bin_tree.delete(item)
        for rec in BIN.records:
            self._bin_tree.insert('', 'end', values=(
                os.path.basename(rec['original']),
                rec['original'], rec['when'], rec['trash']))

    def _restore_all(self):
        ok, fail = BIN.restore_all()
        self._refresh_bin_tree(); self._refresh_bin_label()
        messagebox.showinfo('Restored', f'{ok} restored. {fail} failed.')

    def _restore_sel(self):
        ok = fail = 0
        for iid in self._bin_tree.selection():
            tp = self._bin_tree.item(iid, 'values')[3]
            (ok := ok+1) if BIN.restore_one(tp) else (fail := fail+1)
        self._refresh_bin_tree(); self._refresh_bin_label()
        messagebox.showinfo('Restored', f'{ok} restored. {fail} failed.')

    def _empty_bin(self):
        if not messagebox.askyesno(
            'Empty bin',
            f'Permanently delete {BIN.count()} files?\nCannot be undone.'): return
        BIN.empty(); self._refresh_bin_tree(); self._refresh_bin_label()

    def _refresh_bin_label(self):
        n = BIN.count()
        self._bin_lbl.config(
            text=f'bin: {n} ({human_size(BIN.total_size())})' if n else '')

    # ══════════════════════════════════════════════════════════════
    #  EXPORT
    # ══════════════════════════════════════════════════════════════
    def _export_csv(self):
        p = filedialog.asksaveasfilename(
            defaultextension='.csv',
            filetypes=[('CSV', '*.csv'), ('All', '*.*')])
        if not p: return
        with open(p, 'w', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            w.writerow(['group','role','name','kind','size','modified','path'])
            for gi, g in enumerate(self._dup_groups):
                for fi, file in enumerate(g):
                    w.writerow([gi+1, 'KEEP' if fi==0 else 'DUP',
                                file['name'], file['kind'],
                                file['size'],
                                human_time(file['mtime']),
                                file['path']])
        self._log(f'CSV exported: {p}', 'ok')
        self._show_exp(open(p, encoding='utf-8').read()[:4000])

    def _export_json(self):
        p = filedialog.asksaveasfilename(
            defaultextension='.json',
            filetypes=[('JSON', '*.json'), ('All', '*.*')])
        if not p: return
        import json as _json
        data = [{'group': gi+1, 'files': [
            {'role': 'keep' if fi==0 else 'dup',
             'name': f['name'], 'kind': f['kind'],
             'size': f['size'], 'path': f['path'],
             'mtime': f['mtime']}
            for fi, f in enumerate(g)]}
            for gi, g in enumerate(self._dup_groups)]
        with open(p, 'w', encoding='utf-8') as f:
            _json.dump(data, f, indent=2)
        self._log(f'JSON exported: {p}', 'ok')
        self._show_exp(open(p, encoding='utf-8').read()[:4000])

    def _export_html(self):
        path = generate_html_report(
            self._dup_groups, self._all_files,
            self._scan_start, self._scan_end)
        self._log(f'HTML report: {path}', 'ok')
        self._show_exp(open(path, encoding='utf-8').read()[:4000])

    def _gen_report(self):
        if not self._dup_groups:
            messagebox.showinfo('No data', 'Run a scan first.'); return
        path = generate_html_report(
            self._dup_groups, self._all_files,
            self._scan_start, self._scan_end)
        self._log(f'Report saved: {path}', 'ok')
        self._show_exp(open(path, encoding='utf-8').read()[:4000])
        messagebox.showinfo('Report saved', f'Saved to:\n{path}')

    def _show_exp(self, text):
        self._exp_prev.config(state='normal')
        self._exp_prev.delete('1.0', 'end')
        self._exp_prev.insert('end', text)
        self._exp_prev.config(state='disabled')

    # ══════════════════════════════════════════════════════════════
    #  LOG
    # ══════════════════════════════════════════════════════════════
    def _log(self, msg, kind=''):
        ts = time.strftime('%H:%M:%S')
        self._log_txt.config(state='normal')
        self._log_txt.insert('end', f'[{ts}]  {msg}\n', kind)
        self._log_txt.see('end')
        self._log_txt.config(state='disabled')

    def _clear_log(self):
        self._log_txt.config(state='normal')
        self._log_txt.delete('1.0', 'end')
        self._log_txt.config(state='disabled')

    def _save_log(self):
        p = filedialog.asksaveasfilename(
            defaultextension='.txt',
            filetypes=[('Text', '*.txt'), ('All', '*.*')])
        if p:
            self._log_txt.config(state='normal')
            content = self._log_txt.get('1.0', 'end')
            self._log_txt.config(state='disabled')
            with open(p, 'w', encoding='utf-8') as f: f.write(content)

    # ══════════════════════════════════════════════════════════════
    #  APPEARANCE
    # ══════════════════════════════════════════════════════════════
    def _open_appearance(self):
        AppearanceWindow(self, self._apply_theme)

    def _apply_theme(self, theme, accent):
        apply_theme(theme, accent)
        self._reapply_style()
        self._status.set(f'Theme: {theme}  ·  accent: {accent}')


# ═════════════════════════════════════════════════════════════════
if __name__ == '__main__':
    app = PixelPhantom()
    app.mainloop()