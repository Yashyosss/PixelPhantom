# PixelPhantom

**Hunt down every ghost file lurking in your library.**

A precision duplicate finder for images, videos, and audio — built for real collections, not toy demos.

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?style=flat&logo=python)](https://python.org)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey?style=flat)](https://github.com/Yashyosss/PixelPhantom)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat)](LICENSE)
[![Version](https://img.shields.io/badge/Version-1.0.0-purple?style=flat)](https://github.com/Yashyosss/PixelPhantom/releases)

---

## What makes PixelPhantom different

Most duplicate finders make you choose a "mode" and hope for the best. PixelPhantom **analyses your folder first** and automatically picks the right detection method for each file type — no technical knowledge required.

Drop your folder → click Analyse → click Scan → review results → done.

---

## Screenshots

> *Add screenshots here after first run*

---

## Features

### Smart Auto-Detection
| File type | Auto-selected method | Why |
|---|---|---|
| JPG, PNG, WebP, HEIC… | Perceptual hash | Catches resized/re-saved copies |
| RAW (NEF, CR2, ARW…) | MD5 exact | RAW files are never recompressed |
| MP4, MOV, MKV… < 500 MB | Frame sample hash | Finds re-encoded videos |
| MP4, MOV, MKV… > 500 MB | Fast size + header | Optimised for large files |
| MP3, FLAC, WAV, AAC… | MD5 exact | Audio identity by content |

### Integrity Guaranteed
- **Read-only scan phase** — files are never opened for write during scanning
- **SHA-256 integrity snapshot** — keeps a hash of every file marked "keep" before acting
- **Post-action verification** — automatically re-verifies kept files after any move/delete
- **Mismatch alert** — instant notification if any kept file was altered
- **shutil.copy2** used for all copies — preserves timestamps, permissions, EXIF

### User-First Design
- **Guided 5-step workflow** — Analyse → Scan → Review → Act → Report
- **Animated scan overlay** — never feels frozen, even on 50,000 files
- **Dark / Light themes** — 12 accent presets + full custom color picker
- **Scrollable tabs** — comfortable on small screens
- **Side-by-side compare** — see duplicates together before deciding
- **Image preview** — double-click any result to inspect it

### Safe by Default
- **Recycle bin first** — default action sends to `~/.pixelphantom_trash` (restorable)
- **Full restore capability** — bring back any file or all files at once
- **Permanent delete requires extra confirmation** — hard to do by accident
- **Protected folders** — lock specific paths that are never touched

### Performance
- **Multi-threaded** — parallel workers scale to your CPU core count
- **Size pre-filter** — eliminates 80–95% of files before any hashing
- **SQLite hash cache** — rescanning unchanged folders takes seconds
- **Non-blocking UI** — app stays responsive during scans of 100,000+ files

### Export & Reporting
- Export as **CSV**, **JSON**, or **styled HTML report**
- Auto-generate reports saved to `~/PixelPhantom_Reports/`
- Reports include stats, duplicate groups, detection method used, developer credits

---

## Installation

### Requirements
- Python 3.10 or higher
- `tkinter` (bundled with Python on Windows and macOS; see Linux note below)

### Quick start

```bash
# Clone the repo
git clone https://github.com/Yashyosss/PixelPhantom.git
cd PixelPhantom

# Install dependencies
pip install -r requirements.txt

# Run
python pixelphantom.py
```

### Linux — install tkinter if missing

```bash
# Ubuntu / Debian
sudo apt install python3-tk

# Fedora
sudo dnf install python3-tkinter

# Arch
sudo pacman -S tk
```

---

## Dependencies

| Package | Required | Purpose |
|---|---|---|
| `Pillow` | Recommended | Image preview, thumbnail display, perceptual hashing |
| `imagehash` | Optional | Enhanced perceptual hash quality |

All detection modes work without Pillow — the app falls back to MD5 for perceptual hash cases. Install Pillow for the full experience.

---

## How to Use

### Step 1 — Add folders
Click **+ Add folder** or **+ Add multiple** in the Scan tab. Add as many source folders as you need. Cross-folder duplicate detection works automatically.

### Step 2 — Analyse
Click **Analyse Folder**. PixelPhantom reads filenames and sizes (no content reading yet), shows a breakdown of file types, estimated scan time, and which detection method it will use for each type. You can adjust similarity tolerance if needed.

### Step 3 — Scan
Click **▶ Start Scan**. An animated overlay shows live progress. You can cancel at any time — no files are changed during scanning.

### Step 4 — Review results
The **Results** tab shows every duplicate group. Each group has one `KEEP` file and one or more `DUP` files.

- Press **Space** to mark a row `SEL` (selected for action)
- Use **Keep oldest / newest / largest** to auto-select
- **Double-click** any image to preview it
- Click **Compare…** to see two images side-by-side

### Step 5 — Act
Go to the **Move** tab. Choose your action:
- **Recycle bin** — safest, fully reversible (recommended)
- **Move to folder** — moves duplicates to a chosen destination
- **Copy to folder** — copies, originals stay untouched
- **Permanent delete** — irreversible, requires extra confirmation

Click **▶ Execute Action**. PixelPhantom verifies integrity of kept files after completion.

### Restore
Open the **Recycle Bin** tab to restore individual files or everything at once.

---

## File type support

**Images:** `.jpg` `.jpeg` `.png` `.gif` `.bmp` `.webp` `.tiff` `.tif` `.ico` `.heic` `.heif` `.avif` `.svg` `.raw` `.nef` `.cr2` `.arw` `.dng` `.orf` `.rw2` `.pef` `.srw`

**Videos:** `.mp4` `.mov` `.avi` `.mkv` `.wmv` `.flv` `.webm` `.m4v` `.3gp` `.mpeg` `.mpg` `.ts` `.mts` `.vob` `.ogv` `.rm`

**Audio:** `.mp3` `.flac` `.wav` `.aac` `.ogg` `.wma` `.m4a` `.opus` `.aiff` `.aif` `.ape` `.mka` `.mid` `.midi` `.amr`

---

## Data locations

| Location | Purpose |
|---|---|
| `~/.pixelphantom_cache.db` | SQLite hash cache |
| `~/.pixelphantom_trash/` | Recycle bin folder |
| `~/.pixelphantom_trash/manifest.json` | Bin manifest (for restore) |
| `~/PixelPhantom_Reports/` | Generated HTML reports |

---

## Building a standalone executable

### Windows (.exe)

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name PixelPhantom pixelphantom.py
# Output: dist/PixelPhantom.exe
```

### macOS (.app)

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name PixelPhantom pixelphantom.py
# Output: dist/PixelPhantom.app
```

### Linux (binary)

```bash
pip install pyinstaller
pyinstaller --onefile --name PixelPhantom pixelphantom.py
# Output: dist/PixelPhantom
```

A `build.py` helper script is included in the repo for convenience:

```bash
python build.py
```

---

## Architecture overview

```
PixelPhantom v1.0.0
├── Auto-router         — maps each file to the right detection method
├── ScanEngine          — background thread, N parallel hash workers
│   ├── Size pre-filter — eliminates unique-size files (free)
│   ├── Hash workers    — MD5 / phash / frame-sample / fast-video
│   └── Clusterer       — groups by exact match or Hamming distance
├── IntegrityChecker    — SHA-256 snapshot + post-action verify
├── HashCache           — SQLite-backed, skips unchanged files
├── RecycleBin          — JSON manifest, full restore capability
├── ReportGenerator     — styled HTML with stats + credits
└── GUI (tkinter)       — 9 tabs, animated overlay, theme engine
    ├── Scan            — folder picker, analysis, progress
    ├── Results         — treeview, filter, compare
    ├── Preview         — image thumbnail viewer
    ├── Move            — action selector, integrity options
    ├── Recycle Bin     — browse and restore
    ├── Export          — CSV / JSON / HTML
    ├── Settings        — cache, deps, appearance
    ├── Log             — timestamped event log
    └── About           — credits, features, license
```

---

## Performance guide

| Collection | Recommended mode | First scan | Rescan (cache) |
|---|---|---|---|
| < 5,000 images | Auto (phash) | ~30s | < 5s |
| 5,000–50,000 images | Auto (phash) | 3–10 min | ~30s |
| Large video library | Auto (fast) | 5–20 min | ~1 min |
| Mixed 100,000+ files | Auto | 20–60 min | 2–5 min |

---

## Contributing

Pull requests are welcome. For major changes, open an issue first to discuss what you'd like to change.

1. Fork the repo
2. Create your branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## License

MIT License — see [LICENSE](LICENSE) for full text.

---

## Developer

**Yashas K**
- GitHub: [@Yashyosss](https://github.com/Yashyosss)
- Email: yashaskeshav87@gmail.com

---

*PixelPhantom v1.0.0 — © 2025 Yashas K*
