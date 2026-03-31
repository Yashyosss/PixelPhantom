PixelPhantom — Synopsis

**PixelPhantom** is a desktop application that finds and removes duplicate images, videos, and audio files from your computer. It is built in Python and runs on Windows, macOS, and Linux.

What problem it solves

Over time, photo libraries, download folders, and media collections accumulate duplicate files — the same image saved twice under different names, the same video copied to multiple folders, photos re-saved by different applications. These duplicates waste storage space and make collections hard to manage. PixelPhantom finds them and lets you safely remove them.

 How it detects duplicates

Most duplicate finders work by computing a hash — a short fingerprint — of each file and comparing fingerprints. PixelPhantom takes a different approach. It compares the actual content directly.

For images, it reads every pixel's red, green, and blue values and compares them side by side. Two images are only considered duplicates if every single pixel matches exactly. This means it correctly identifies duplicates even when the same image was saved by different software, given a different filename, or stored in a different folder — something hash-based tools often miss.

For videos and audio, it compares the raw file bytes directly, chunk by chunk.

No hashing is used at any stage. No image is ever re-encoded or modified. Every file is opened in read-only mode during scanning, so there is zero risk of accidental changes to your originals.

 How it works — the three steps

To handle large collections efficiently without reading every file against every other file, PixelPhantom uses a three-phase approach:

**Step 1 — Size filter.** Files with a unique byte size cannot possibly be duplicates, so they are skipped immediately without reading any content. This typically eliminates 85–95% of files for free.

**Step 2 — Dimension filter (images only).** Images with different pixel dimensions cannot be identical, so they are skipped after a fast header read.

**Step 3 — Direct comparison.** Only the small remaining group of files that survived both filters are compared pixel-by-pixel or byte-by-byte. This is where the actual duplicate detection happens.

What happens after duplicates are found

Results appear in a list grouped by duplicate set. For each group, PixelPhantom marks one file as "keep" and the others as duplicates. You can preview images, compare them side by side, and choose which copies to remove using auto-select options like keep oldest, keep newest, or keep largest.

The default action is to send duplicates to a recycle bin — a special folder that keeps a record of where each file came from. Files can be fully restored at any time. Permanent deletion requires an extra confirmation step.

Features at a glance

- Supports images (JPG, PNG, BMP, WebP, HEIC, RAW and more), videos (MP4, MOV, MKV and more), and audio (MP3, FLAC, WAV and more)
- Pure pixel comparison — no hashing, no quality loss, no file modification
- Three-phase pipeline keeps scanning fast even on large collections
- Recycle bin with full restore capability
- Side-by-side image comparison
- Dark and light themes with customisable accent colour
- Export results as CSV, JSON, or styled HTML report
- Multi-folder scanning — find duplicates across different locations
- Protected folders — lock specific paths so they are never touched
- 90 automated tests verifying every core function

 Who it is for

Anyone who manages a large photo library, video collection, or audio archive and wants to reclaim storage space and eliminate clutter — without risking accidental loss of original files.

**Developer:** Yashas K
**GitHub:** https://github.com/Yashyosss
**License:** use, modify, and share
