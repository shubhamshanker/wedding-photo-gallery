#!/usr/bin/env python3
"""
Wedding Gallery Pro - Production Server
Ultra-fast, feature-rich wedding photo gallery server.
"""

import http.server
import socketserver
import sys
import os
import json
import hashlib
import mimetypes
import threading
import time
import io
import base64
import struct
import zlib
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote
from functools import lru_cache

# Try to import optional fast libs
try:
    import PIL.Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

GALLERY_DIR = None  # Set at runtime
CACHE = {}  # In-memory cache for thumbnails and metadata
CACHE_LOCK = threading.Lock()
SUPPORTED_IMAGES = {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.heic'}
SUPPORTED_VIDEOS = {'.mov', '.mp4', '.m4v', '.avi', '.mkv'}


def get_file_hash(path):
    """Fast hash using file mtime + size."""
    stat = os.stat(path)
    return f"{stat.st_mtime}-{stat.st_size}"


def scan_media_files(directory):
    """Recursively scan for all media files."""
    photos = []
    videos = []
    seen = set()

    for root, dirs, files in os.walk(directory):
        # Skip hidden dirs
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for fname in sorted(files):
            if fname.startswith('.'):
                continue
            fpath = os.path.join(root, fname)
            # Resolve symlinks to avoid duplicates
            try:
                real = os.path.realpath(fpath)
                if real in seen:
                    continue
                seen.add(real)
            except Exception:
                pass

            ext = Path(fname).suffix.lower()
            rel = os.path.relpath(fpath, directory)
            stat = os.stat(fpath)
            entry = {
                'name': fname,
                'path': rel,
                'size': stat.st_size,
                'mtime': stat.st_mtime,
                'ext': ext
            }
            if ext in SUPPORTED_IMAGES:
                photos.append(entry)
            elif ext in SUPPORTED_VIDEOS:
                videos.append(entry)

    return photos, videos


def make_tiny_thumbnail_png(width=4, height=4):
    """Generate a minimal placeholder PNG."""
    # 1x1 gray PNG
    raw = b'\x89PNG\r\n\x1a\n'
    ihdr = struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0)
    raw += _png_chunk(b'IHDR', ihdr)
    idat = zlib.compress(b'\x00\x80\x80\x80')
    raw += _png_chunk(b'IDAT', idat)
    raw += _png_chunk(b'IEND', b'')
    return raw


def _png_chunk(chunk_type, data):
    c = struct.pack('>I', len(data)) + chunk_type + data
    crc = zlib.crc32(chunk_type + data) & 0xffffffff
    return c + struct.pack('>I', crc)


class WeddingGalleryHandler(http.server.BaseHTTPRequestHandler):
    """Ultra-optimized handler for wedding gallery."""

    def log_message(self, format, *args):
        pass  # Silent logging

    def log_error(self, format, *args):
        pass

    def handle_one_request(self):
        try:
            super().handle_one_request()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        try:
            if path == '/' or path == '/index.html':
                self.serve_gallery_html()
            elif path == '/api/scan':
                self.api_scan()
            elif path == '/api/media':
                self.api_media(qs)
            elif path == '/api/favorites':
                self.api_get_favorites()
            elif path == '/api/search':
                self.api_search(qs)
            elif path == '/api/stats':
                self.api_stats()
            elif path.startswith('/thumb/'):
                self.serve_thumbnail(path[7:])
            elif path.startswith('/media/'):
                self.serve_media_file(unquote(path[7:]))
            elif path.startswith('/upload'):
                self.serve_upload_page()
            else:
                self.send_404()
        except Exception as e:
            self.send_error_response(500, str(e))

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            if path == '/api/favorites':
                self.api_save_favorite()
            elif path == '/api/upload':
                self.api_upload()
            else:
                self.send_404()
        except Exception as e:
            self.send_error_response(500, str(e))

    def send_json(self, data, status=200):
        body = json.dumps(data).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', len(body))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def send_404(self):
        self.send_response(404)
        self.send_header('Content-Type', 'text/plain')
        self.end_headers()
        try:
            self.wfile.write(b'Not found')
        except Exception:
            pass

    def send_error_response(self, code, msg):
        self.send_json({'error': msg}, code)

    def api_scan(self):
        """Scan and cache media list."""
        global CACHE
        photos, videos = scan_media_files(GALLERY_DIR)
        with CACHE_LOCK:
            CACHE['photos'] = photos
            CACHE['videos'] = videos
            CACHE['scan_time'] = time.time()
        self.send_json({
            'photos': len(photos),
            'videos': len(videos),
            'total': len(photos) + len(videos)
        })

    def api_media(self, qs):
        """Return paginated media list."""
        media_type = qs.get('type', ['photos'])[0]
        page = int(qs.get('page', [1])[0])
        per_page = int(qs.get('per_page', [50])[0])
        sort = qs.get('sort', ['date'])[0]
        order = qs.get('order', ['desc'])[0]

        with CACHE_LOCK:
            if media_type == 'videos':
                items = CACHE.get('videos', [])
            else:
                items = CACHE.get('photos', [])

        # Sort
        reverse = order == 'desc'
        if sort == 'date':
            items = sorted(items, key=lambda x: x['mtime'], reverse=reverse)
        elif sort == 'name':
            items = sorted(items, key=lambda x: x['name'], reverse=reverse)
        elif sort == 'size':
            items = sorted(items, key=lambda x: x['size'], reverse=reverse)

        total = len(items)
        start = (page - 1) * per_page
        end = start + per_page
        page_items = items[start:end]

        self.send_json({
            'items': page_items,
            'total': total,
            'page': page,
            'per_page': per_page,
            'pages': (total + per_page - 1) // per_page
        })

    def api_search(self, qs):
        """Search by filename."""
        q = qs.get('q', [''])[0].lower()
        with CACHE_LOCK:
            photos = CACHE.get('photos', [])
            videos = CACHE.get('videos', [])

        results = [p for p in photos + videos if q in p['name'].lower()][:100]
        self.send_json({'results': results, 'total': len(results)})

    def api_stats(self):
        """Return gallery stats."""
        with CACHE_LOCK:
            photos = CACHE.get('photos', [])
            videos = CACHE.get('videos', [])

        total_size = sum(p['size'] for p in photos + videos)
        self.send_json({
            'photos': len(photos),
            'videos': len(videos),
            'total_size_gb': round(total_size / 1e9, 2),
            'scan_time': CACHE.get('scan_time', 0)
        })

    def api_get_favorites(self):
        fav_file = os.path.join(GALLERY_DIR, '.favorites.json')
        try:
            with open(fav_file) as f:
                favs = json.load(f)
        except Exception:
            favs = []
        self.send_json({'favorites': favs})

    def api_save_favorite(self):
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length)
        data = json.loads(body)
        fav_file = os.path.join(GALLERY_DIR, '.favorites.json')
        try:
            with open(fav_file) as f:
                favs = json.load(f)
        except Exception:
            favs = []

        path = data.get('path')
        action = data.get('action', 'toggle')
        if action == 'toggle':
            if path in favs:
                favs.remove(path)
                added = False
            else:
                favs.append(path)
                added = True
        elif action == 'add':
            if path not in favs:
                favs.append(path)
            added = True
        else:
            if path in favs:
                favs.remove(path)
            added = False

        with open(fav_file, 'w') as f:
            json.dump(favs, f)
        self.send_json({'favorites': favs, 'added': added})

    def api_upload(self):
        """Handle file upload."""
        content_type = self.headers.get('Content-Type', '')
        if 'multipart/form-data' not in content_type:
            self.send_json({'error': 'multipart required'}, 400)
            return

        # Simple multipart parsing
        length = int(self.headers.get('Content-Length', 0))
        if length > 500 * 1024 * 1024:  # 500MB limit
            self.send_json({'error': 'File too large (max 500MB)'}, 400)
            return

        body = self.rfile.read(length)
        boundary = content_type.split('boundary=')[1].encode()

        # Parse parts
        parts = body.split(b'--' + boundary)
        saved = []
        for part in parts[1:-1]:
            if b'\r\n\r\n' not in part:
                continue
            header, content = part.split(b'\r\n\r\n', 1)
            content = content.rstrip(b'\r\n')
            header_str = header.decode('utf-8', errors='ignore')
            if 'filename=' not in header_str:
                continue
            fname = header_str.split('filename="')[1].split('"')[0]
            if not fname:
                continue

            ext = Path(fname).suffix.lower()
            if ext not in SUPPORTED_IMAGES | SUPPORTED_VIDEOS:
                continue

            upload_dir = os.path.join(GALLERY_DIR, 'uploads')
            os.makedirs(upload_dir, exist_ok=True)
            dest = os.path.join(upload_dir, fname)
            # Avoid overwrite
            if os.path.exists(dest):
                base = Path(fname).stem
                dest = os.path.join(upload_dir, f"{base}_{int(time.time())}{ext}")

            with open(dest, 'wb') as f:
                f.write(content)
            saved.append(os.path.basename(dest))

        # Rescan
        photos, videos = scan_media_files(GALLERY_DIR)
        with CACHE_LOCK:
            CACHE['photos'] = photos
            CACHE['videos'] = videos

        self.send_json({'saved': saved, 'count': len(saved)})

    def serve_thumbnail(self, rel_path):
        """Serve fast thumbnail - use PIL if available, else serve original with cache."""
        rel_path = unquote(rel_path)
        full_path = os.path.join(GALLERY_DIR, rel_path)

        if not os.path.exists(full_path):
            self.send_404()
            return

        cache_key = f"thumb:{rel_path}:{get_file_hash(full_path)}"
        with CACHE_LOCK:
            cached = CACHE.get(cache_key)

        if cached:
            self._send_image_bytes(cached, 'image/jpeg')
            return

        if HAS_PIL:
            try:
                img = PIL.Image.open(full_path)
                img.thumbnail((400, 400), PIL.Image.LANCZOS)
                if img.mode in ('RGBA', 'P'):
                    img = img.convert('RGB')
                buf = io.BytesIO()
                img.save(buf, 'JPEG', quality=75, optimize=True)
                thumb_bytes = buf.getvalue()
                with CACHE_LOCK:
                    CACHE[cache_key] = thumb_bytes
                self._send_image_bytes(thumb_bytes, 'image/jpeg')
                return
            except Exception:
                pass

        # Fallback: serve original with range support
        self.serve_media_file(rel_path)

    def _send_image_bytes(self, data, content_type):
        self.send_response(200)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', len(data))
        self.send_header('Cache-Control', 'public, max-age=86400')
        self.send_header('ETag', hashlib.md5(data[:100]).hexdigest())
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def serve_media_file(self, rel_path):
        """Serve media with range request support for video streaming."""
        full_path = os.path.join(GALLERY_DIR, rel_path)

        if not os.path.exists(full_path):
            self.send_404()
            return

        # ETag support
        file_hash = get_file_hash(full_path)
        etag = hashlib.md5(file_hash.encode()).hexdigest()
        if self.headers.get('If-None-Match') == etag:
            self.send_response(304)
            self.end_headers()
            return

        ext = Path(full_path).suffix.lower()
        mime = mimetypes.guess_type(full_path)[0] or 'application/octet-stream'

        file_size = os.path.getsize(full_path)
        range_header = self.headers.get('Range')

        if range_header:
            # Parse range
            range_val = range_header.strip().replace('bytes=', '')
            parts = range_val.split('-')
            start = int(parts[0]) if parts[0] else 0
            end = int(parts[1]) if parts[1] else file_size - 1
            end = min(end, file_size - 1)
            length = end - start + 1

            self.send_response(206)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', length)
            self.send_header('Content-Range', f'bytes {start}-{end}/{file_size}')
            self.send_header('Accept-Ranges', 'bytes')
            self.send_header('Cache-Control', 'public, max-age=3600')
            self.send_header('ETag', etag)
            self.end_headers()

            try:
                with open(full_path, 'rb') as f:
                    f.seek(start)
                    remaining = length
                    while remaining > 0:
                        chunk = f.read(min(65536, remaining))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        remaining -= len(chunk)
            except (BrokenPipeError, ConnectionResetError):
                pass
        else:
            self.send_response(200)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', file_size)
            self.send_header('Accept-Ranges', 'bytes')
            self.send_header('Cache-Control', 'public, max-age=3600')
            self.send_header('ETag', etag)
            self.end_headers()

            try:
                with open(full_path, 'rb') as f:
                    while True:
                        chunk = f.read(65536)
                        if not chunk:
                            break
                        self.wfile.write(chunk)
            except (BrokenPipeError, ConnectionResetError):
                pass

    def serve_gallery_html(self):
        html = get_gallery_html()
        body = html.encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', len(body))
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def serve_upload_page(self):
        self.serve_gallery_html()


def get_gallery_html():
    return '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Wedding Gallery ✦</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,300;0,400;0,600;1,300;1,400&family=DM+Sans:wght@300;400;500&display=swap" rel="stylesheet">
<style>
  :root {
    --cream: #faf7f2;
    --warm-white: #fefcf9;
    --gold: #c9a96e;
    --gold-light: #e8d5b0;
    --gold-dark: #a07840;
    --charcoal: #2a2420;
    --warm-gray: #6b5e54;
    --rose: #c4877b;
    --rose-light: #f0d8d4;
    --border: rgba(201,169,110,0.2);
    --shadow: 0 4px 40px rgba(42,36,32,0.08);
    --shadow-hover: 0 12px 60px rgba(42,36,32,0.16);
    --radius: 4px;
    --font-serif: 'Cormorant Garamond', Georgia, serif;
    --font-sans: 'DM Sans', system-ui, sans-serif;
  }

  * { box-sizing: border-box; margin: 0; padding: 0; }

  html { scroll-behavior: smooth; }

  body {
    font-family: var(--font-sans);
    background: var(--cream);
    color: var(--charcoal);
    min-height: 100vh;
    -webkit-font-smoothing: antialiased;
  }

  /* ─── HEADER ─── */
  .header {
    background: var(--warm-white);
    border-bottom: 1px solid var(--border);
    padding: 0 32px;
    position: sticky;
    top: 0;
    z-index: 100;
    backdrop-filter: blur(20px);
    -webkit-backdrop-filter: blur(20px);
  }

  .header-inner {
    max-width: 1600px;
    margin: 0 auto;
    display: flex;
    align-items: center;
    gap: 24px;
    height: 64px;
  }

  .logo {
    font-family: var(--font-serif);
    font-size: 22px;
    font-weight: 300;
    color: var(--charcoal);
    letter-spacing: 0.02em;
    white-space: nowrap;
    flex-shrink: 0;
  }

  .logo span {
    color: var(--gold);
    font-style: italic;
  }

  .search-wrap {
    flex: 1;
    max-width: 400px;
    position: relative;
  }

  .search-input {
    width: 100%;
    padding: 9px 16px 9px 40px;
    background: var(--cream);
    border: 1px solid var(--border);
    border-radius: 24px;
    font-family: var(--font-sans);
    font-size: 13px;
    color: var(--charcoal);
    outline: none;
    transition: border-color 0.2s, box-shadow 0.2s;
  }

  .search-input:focus {
    border-color: var(--gold);
    box-shadow: 0 0 0 3px rgba(201,169,110,0.12);
  }

  .search-icon {
    position: absolute;
    left: 14px;
    top: 50%;
    transform: translateY(-50%);
    color: var(--warm-gray);
    pointer-events: none;
  }

  .header-actions {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-left: auto;
  }

  .btn {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 8px 16px;
    border-radius: 24px;
    font-family: var(--font-sans);
    font-size: 12px;
    font-weight: 500;
    letter-spacing: 0.04em;
    cursor: pointer;
    border: none;
    transition: all 0.2s;
    text-transform: uppercase;
  }

  .btn-outline {
    background: transparent;
    border: 1px solid var(--border);
    color: var(--warm-gray);
  }
  .btn-outline:hover { border-color: var(--gold); color: var(--gold-dark); }

  .btn-gold {
    background: var(--gold);
    color: #fff;
  }
  .btn-gold:hover { background: var(--gold-dark); }

  .btn-ghost {
    background: transparent;
    border: 1px solid transparent;
    color: var(--warm-gray);
    padding: 8px 10px;
  }
  .btn-ghost:hover { background: var(--rose-light); color: var(--rose); }
  .btn-ghost.active { background: var(--rose-light); color: var(--rose); }

  /* ─── TABS ─── */
  .tabs-bar {
    background: var(--warm-white);
    border-bottom: 1px solid var(--border);
    padding: 0 32px;
  }

  .tabs-inner {
    max-width: 1600px;
    margin: 0 auto;
    display: flex;
    align-items: center;
    gap: 0;
  }

  .tab {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 12px 20px;
    font-size: 12px;
    font-weight: 500;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--warm-gray);
    cursor: pointer;
    border-bottom: 2px solid transparent;
    transition: color 0.2s, border-color 0.2s;
    white-space: nowrap;
  }
  .tab:hover { color: var(--charcoal); }
  .tab.active { color: var(--gold-dark); border-bottom-color: var(--gold); }

  .tab-count {
    background: var(--cream);
    color: var(--warm-gray);
    font-size: 10px;
    padding: 1px 6px;
    border-radius: 10px;
    font-weight: 400;
  }
  .tab.active .tab-count { background: var(--gold-light); color: var(--gold-dark); }

  /* ─── TOOLBAR ─── */
  .toolbar {
    max-width: 1600px;
    margin: 0 auto;
    padding: 16px 32px;
    display: flex;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
  }

  .toolbar-left { display: flex; align-items: center; gap: 8px; }
  .toolbar-right { display: flex; align-items: center; gap: 8px; margin-left: auto; }

  select {
    padding: 7px 12px;
    border: 1px solid var(--border);
    border-radius: 6px;
    background: var(--warm-white);
    font-family: var(--font-sans);
    font-size: 12px;
    color: var(--charcoal);
    cursor: pointer;
    outline: none;
  }
  select:focus { border-color: var(--gold); }

  .view-toggle { display: flex; border: 1px solid var(--border); border-radius: 6px; overflow: hidden; }
  .view-btn {
    padding: 7px 10px;
    background: transparent;
    border: none;
    color: var(--warm-gray);
    cursor: pointer;
    transition: background 0.15s;
    display: flex;
    align-items: center;
  }
  .view-btn:hover { background: var(--cream); }
  .view-btn.active { background: var(--gold-light); color: var(--gold-dark); }

  /* ─── GALLERY GRID ─── */
  .gallery-wrap {
    max-width: 1600px;
    margin: 0 auto;
    padding: 0 32px 48px;
  }

  .gallery-grid {
    display: grid;
    gap: 4px;
    grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  }

  .gallery-grid.cols-2 { grid-template-columns: repeat(2, 1fr); }
  .gallery-grid.cols-3 { grid-template-columns: repeat(3, 1fr); }
  .gallery-grid.cols-4 { grid-template-columns: repeat(4, 1fr); }
  .gallery-grid.cols-5 { grid-template-columns: repeat(5, 1fr); }
  .gallery-grid.cols-6 { grid-template-columns: repeat(6, 1fr); }

  .gallery-grid.masonry {
    columns: 5;
    column-gap: 4px;
    display: block;
  }

  .gallery-grid.list {
    display: flex;
    flex-direction: column;
    gap: 1px;
  }

  /* Photo Card */
  .photo-card {
    position: relative;
    overflow: hidden;
    cursor: pointer;
    background: var(--gold-light);
  }

  .gallery-grid.masonry .photo-card {
    display: inline-block;
    width: 100%;
    margin-bottom: 4px;
    break-inside: avoid;
  }

  .gallery-grid.list .photo-card {
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 8px 12px;
    background: var(--warm-white);
    border-radius: 4px;
    height: 56px;
  }

  .photo-card:hover .photo-overlay { opacity: 1; }
  .photo-card:hover .photo-img { transform: scale(1.03); }

  .photo-img-wrap {
    aspect-ratio: 1;
    overflow: hidden;
    background: var(--gold-light);
  }

  .gallery-grid.masonry .photo-img-wrap {
    aspect-ratio: unset;
  }

  .gallery-grid.list .photo-img-wrap {
    width: 40px;
    height: 40px;
    flex-shrink: 0;
    aspect-ratio: 1;
    border-radius: 3px;
    overflow: hidden;
  }

  .photo-img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    transition: transform 0.4s cubic-bezier(0.25, 0.46, 0.45, 0.94);
    display: block;
  }

  .photo-overlay {
    position: absolute;
    inset: 0;
    background: linear-gradient(to top, rgba(42,36,32,0.6) 0%, transparent 50%);
    opacity: 0;
    transition: opacity 0.3s;
    display: flex;
    flex-direction: column;
    justify-content: flex-end;
    padding: 12px;
  }

  .gallery-grid.list .photo-overlay { display: none; }

  .photo-name {
    color: #fff;
    font-size: 11px;
    font-weight: 400;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    opacity: 0.9;
  }

  .photo-actions {
    display: flex;
    gap: 6px;
    margin-bottom: 4px;
  }

  .action-btn {
    width: 28px;
    height: 28px;
    border-radius: 50%;
    border: none;
    background: rgba(255,255,255,0.2);
    backdrop-filter: blur(8px);
    color: #fff;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: background 0.2s;
    font-size: 13px;
  }
  .action-btn:hover { background: rgba(255,255,255,0.35); }
  .action-btn.fav { color: var(--rose); }
  .action-btn.fav.active { background: var(--rose); color: #fff; }

  .list-info {
    flex: 1;
    min-width: 0;
  }
  .list-name {
    font-size: 13px;
    font-weight: 400;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .list-meta {
    font-size: 11px;
    color: var(--warm-gray);
    margin-top: 1px;
  }

  /* Video card badge */
  .video-badge {
    position: absolute;
    top: 8px;
    left: 8px;
    background: rgba(42,36,32,0.7);
    backdrop-filter: blur(8px);
    color: #fff;
    font-size: 10px;
    padding: 2px 8px;
    border-radius: 10px;
    font-weight: 500;
    letter-spacing: 0.06em;
  }

  /* ─── LIGHTBOX ─── */
  .lightbox {
    position: fixed;
    inset: 0;
    background: rgba(15, 12, 10, 0.97);
    z-index: 1000;
    display: none;
    flex-direction: column;
  }
  .lightbox.open { display: flex; }

  .lb-header {
    display: flex;
    align-items: center;
    padding: 16px 24px;
    gap: 16px;
    flex-shrink: 0;
  }

  .lb-title {
    font-family: var(--font-serif);
    font-size: 16px;
    font-weight: 300;
    color: rgba(255,255,255,0.7);
    flex: 1;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .lb-counter {
    font-size: 12px;
    color: rgba(255,255,255,0.4);
    letter-spacing: 0.06em;
  }

  .lb-close {
    width: 36px;
    height: 36px;
    border-radius: 50%;
    border: 1px solid rgba(255,255,255,0.15);
    background: transparent;
    color: rgba(255,255,255,0.7);
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 16px;
    transition: all 0.2s;
  }
  .lb-close:hover { background: rgba(255,255,255,0.1); color: #fff; }

  .lb-body {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    position: relative;
    min-height: 0;
    padding: 0 80px;
  }

  .lb-img {
    max-width: 100%;
    max-height: 100%;
    object-fit: contain;
    display: block;
    border-radius: 2px;
    animation: lb-in 0.25s ease;
  }

  .lb-video {
    max-width: 100%;
    max-height: 100%;
    border-radius: 2px;
    outline: none;
  }

  @keyframes lb-in {
    from { opacity: 0; transform: scale(0.97); }
    to { opacity: 1; transform: scale(1); }
  }

  .lb-nav {
    position: absolute;
    top: 50%;
    transform: translateY(-50%);
    width: 48px;
    height: 48px;
    border-radius: 50%;
    border: 1px solid rgba(255,255,255,0.2);
    background: rgba(255,255,255,0.05);
    color: rgba(255,255,255,0.8);
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 18px;
    transition: all 0.2s;
    backdrop-filter: blur(8px);
  }
  .lb-nav:hover { background: rgba(255,255,255,0.15); color: #fff; }
  .lb-prev { left: 16px; }
  .lb-next { right: 16px; }

  .lb-footer {
    display: flex;
    align-items: center;
    padding: 12px 24px;
    gap: 12px;
    flex-shrink: 0;
    border-top: 1px solid rgba(255,255,255,0.06);
  }

  .lb-thumb-strip {
    display: flex;
    gap: 4px;
    overflow-x: auto;
    flex: 1;
    padding: 4px 0;
    scrollbar-width: thin;
  }
  .lb-thumb-strip::-webkit-scrollbar { height: 3px; }
  .lb-thumb-strip::-webkit-scrollbar-track { background: transparent; }
  .lb-thumb-strip::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.2); border-radius: 2px; }

  .lb-thumb {
    width: 52px;
    height: 40px;
    flex-shrink: 0;
    object-fit: cover;
    border-radius: 2px;
    cursor: pointer;
    opacity: 0.4;
    transition: opacity 0.2s, outline 0.2s;
    border: 2px solid transparent;
  }
  .lb-thumb.active {
    opacity: 1;
    border-color: var(--gold);
  }

  .lb-actions {
    display: flex;
    gap: 8px;
    flex-shrink: 0;
  }

  .lb-btn {
    padding: 8px 14px;
    border-radius: 20px;
    border: 1px solid rgba(255,255,255,0.2);
    background: transparent;
    color: rgba(255,255,255,0.7);
    font-size: 11px;
    font-weight: 500;
    letter-spacing: 0.06em;
    cursor: pointer;
    transition: all 0.2s;
    text-transform: uppercase;
    display: flex;
    align-items: center;
    gap: 6px;
    font-family: var(--font-sans);
  }
  .lb-btn:hover { background: rgba(255,255,255,0.1); color: #fff; border-color: rgba(255,255,255,0.4); }
  .lb-btn.fav-btn.active { background: var(--rose); border-color: var(--rose); color: #fff; }

  /* ─── UPLOAD MODAL ─── */
  .modal-bg {
    position: fixed;
    inset: 0;
    background: rgba(42,36,32,0.6);
    z-index: 500;
    display: none;
    align-items: center;
    justify-content: center;
    padding: 24px;
    backdrop-filter: blur(8px);
  }
  .modal-bg.open { display: flex; }

  .modal {
    background: var(--warm-white);
    border-radius: 12px;
    padding: 32px;
    max-width: 520px;
    width: 100%;
    box-shadow: 0 24px 80px rgba(42,36,32,0.2);
  }

  .modal-title {
    font-family: var(--font-serif);
    font-size: 24px;
    font-weight: 300;
    margin-bottom: 6px;
  }
  .modal-sub { font-size: 13px; color: var(--warm-gray); margin-bottom: 24px; }

  .dropzone {
    border: 2px dashed var(--gold-light);
    border-radius: 8px;
    padding: 40px;
    text-align: center;
    cursor: pointer;
    transition: all 0.2s;
    background: var(--cream);
  }
  .dropzone:hover, .dropzone.drag-over {
    border-color: var(--gold);
    background: rgba(201,169,110,0.05);
  }
  .dropzone-icon { font-size: 32px; margin-bottom: 12px; color: var(--gold); }
  .dropzone-text { font-size: 14px; color: var(--warm-gray); }
  .dropzone-text strong { color: var(--charcoal); }

  #upload-input { display: none; }

  .upload-list { margin-top: 16px; display: flex; flex-direction: column; gap: 6px; max-height: 200px; overflow-y: auto; }
  .upload-item { display: flex; align-items: center; gap: 10px; padding: 8px 12px; background: var(--cream); border-radius: 6px; font-size: 12px; }
  .upload-item-name { flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .upload-progress { height: 3px; background: var(--gold-light); border-radius: 2px; margin-top: 4px; overflow: hidden; }
  .upload-progress-bar { height: 100%; background: var(--gold); transition: width 0.3s; border-radius: 2px; }

  .modal-footer { display: flex; gap: 10px; margin-top: 20px; justify-content: flex-end; }

  /* ─── PAGINATION ─── */
  .pagination {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 4px;
    padding: 32px 0 0;
  }

  .page-btn {
    width: 36px;
    height: 36px;
    border-radius: 50%;
    border: 1px solid var(--border);
    background: var(--warm-white);
    color: var(--charcoal);
    font-size: 13px;
    font-family: var(--font-sans);
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.2s;
  }
  .page-btn:hover { border-color: var(--gold); color: var(--gold-dark); }
  .page-btn.active { background: var(--gold); border-color: var(--gold); color: #fff; }
  .page-btn:disabled { opacity: 0.3; cursor: default; }

  .page-info { font-size: 12px; color: var(--warm-gray); padding: 0 8px; }

  /* ─── EMPTY / LOADING ─── */
  .empty-state {
    text-align: center;
    padding: 80px 24px;
    color: var(--warm-gray);
  }
  .empty-icon { font-size: 48px; margin-bottom: 16px; }
  .empty-title { font-family: var(--font-serif); font-size: 24px; font-weight: 300; margin-bottom: 8px; color: var(--charcoal); }
  .empty-text { font-size: 14px; }

  .loading-spinner {
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 80px;
    gap: 12px;
    color: var(--warm-gray);
    font-size: 14px;
  }

  @keyframes spin { to { transform: rotate(360deg); } }
  .spinner {
    width: 24px;
    height: 24px;
    border: 2px solid var(--border);
    border-top-color: var(--gold);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }

  /* ─── TOAST ─── */
  .toast-container {
    position: fixed;
    bottom: 24px;
    right: 24px;
    z-index: 2000;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .toast {
    background: var(--charcoal);
    color: #fff;
    padding: 12px 20px;
    border-radius: 8px;
    font-size: 13px;
    display: flex;
    align-items: center;
    gap: 10px;
    box-shadow: var(--shadow-hover);
    animation: toast-in 0.3s ease;
    max-width: 300px;
  }
  .toast.success { border-left: 3px solid #7db87d; }
  .toast.error { border-left: 3px solid var(--rose); }
  @keyframes toast-in {
    from { opacity: 0; transform: translateX(20px); }
    to { opacity: 1; transform: translateX(0); }
  }

  /* ─── STATS BAR ─── */
  .stats-bar {
    background: var(--warm-white);
    border-top: 1px solid var(--border);
    padding: 0 32px;
  }
  .stats-inner {
    max-width: 1600px;
    margin: 0 auto;
    padding: 10px 0;
    display: flex;
    gap: 24px;
    align-items: center;
    font-size: 12px;
    color: var(--warm-gray);
  }
  .stat { display: flex; align-items: center; gap: 6px; }
  .stat strong { color: var(--charcoal); font-weight: 500; }

  /* ─── SELECTION MODE ─── */
  .selection-bar {
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    background: var(--charcoal);
    padding: 14px 32px;
    display: none;
    align-items: center;
    gap: 16px;
    z-index: 200;
    border-top: 1px solid rgba(255,255,255,0.1);
  }
  .selection-bar.visible { display: flex; }
  .sel-count { color: rgba(255,255,255,0.7); font-size: 14px; }
  .sel-count strong { color: #fff; }

  /* Photo card selected state */
  .photo-card.selected::after {
    content: '';
    position: absolute;
    inset: 0;
    border: 3px solid var(--gold);
    pointer-events: none;
    z-index: 2;
  }
  .photo-card.selected .photo-img-wrap::after {
    content: '✓';
    position: absolute;
    top: 8px;
    right: 8px;
    width: 24px;
    height: 24px;
    border-radius: 50%;
    background: var(--gold);
    color: #fff;
    font-size: 12px;
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 3;
  }

  /* ─── RESPONSIVE ─── */
  @media (max-width: 768px) {
    .header-inner { padding: 0; }
    .gallery-grid { grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); }
    .gallery-grid.masonry { columns: 2; }
    .lb-body { padding: 0 48px; }
    .lb-thumb-strip { display: none; }
    .toolbar { padding: 12px 16px; }
    .gallery-wrap { padding: 0 16px 48px; }
    .tabs-bar, .stats-bar { padding: 0 16px; }
  }

  /* ─── SHIMMER ─── */
  .shimmer {
    background: linear-gradient(90deg, var(--gold-light) 25%, rgba(255,255,255,0.5) 50%, var(--gold-light) 75%);
    background-size: 200% 100%;
    animation: shimmer 1.5s infinite;
  }
  @keyframes shimmer { from { background-position: 200% 0; } to { background-position: -200% 0; } }
</style>
</head>
<body>

<!-- HEADER -->
<header class="header">
  <div class="header-inner">
    <div class="logo">Wedding <span>Gallery</span></div>
    <div class="search-wrap">
      <svg class="search-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>
      </svg>
      <input class="search-input" type="text" id="searchInput" placeholder="Search photos & videos...">
    </div>
    <div class="header-actions">
      <button class="btn btn-ghost" id="favBtn" title="Favorites">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/>
        </svg>
        Favorites
      </button>
      <button class="btn btn-outline" id="selectBtn">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <rect x="3" y="3" width="18" height="18" rx="2"/><path d="M9 12l2 2 4-4"/>
        </svg>
        Select
      </button>
      <button class="btn btn-outline" id="scanBtn">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="1 4 1 10 7 10"/><polyline points="23 20 23 14 17 14"/>
          <path d="M20.49 9A9 9 0 0 0 5.64 5.64L1 10m22 4-4.64 4.36A9 9 0 0 1 3.51 15"/>
        </svg>
        Refresh
      </button>
      <button class="btn btn-gold" id="uploadBtn">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="16 16 12 12 8 16"/><line x1="12" y1="12" x2="12" y2="21"/>
          <path d="M20.39 18.39A5 5 0 0 0 18 9h-1.26A8 8 0 1 0 3 16.3"/>
        </svg>
        Upload
      </button>
    </div>
  </div>
</header>

<!-- TABS -->
<div class="tabs-bar">
  <div class="tabs-inner">
    <div class="tab active" data-tab="photos">
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="9" cy="9" r="2"/>
        <polyline points="21 15 16 10 5 21"/>
      </svg>
      Photos <span class="tab-count" id="photoCount">—</span>
    </div>
    <div class="tab" data-tab="videos">
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <polygon points="23 7 16 12 23 17 23 7"/><rect x="1" y="5" width="15" height="14" rx="2" ry="2"/>
      </svg>
      Videos <span class="tab-count" id="videoCount">—</span>
    </div>
  </div>
</div>

<!-- TOOLBAR -->
<div class="toolbar">
  <div class="toolbar-left">
    <select id="perPageSel">
      <option value="50">50 per page</option>
      <option value="100" selected>100 per page</option>
      <option value="200">200 per page</option>
      <option value="500">500 per page</option>
    </select>
    <select id="sortSel">
      <option value="date-desc">Newest first</option>
      <option value="date-asc">Oldest first</option>
      <option value="name-asc">Name A-Z</option>
      <option value="name-desc">Name Z-A</option>
      <option value="size-desc">Largest first</option>
    </select>
    <select id="colsSel">
      <option value="3">3 cols</option>
      <option value="4" selected>4 cols</option>
      <option value="5">5 cols</option>
      <option value="6">6 cols</option>
      <option value="masonry">Masonry</option>
    </select>
  </div>
  <div class="toolbar-right">
    <div class="view-toggle">
      <button class="view-btn active" data-view="grid" title="Grid">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/>
          <rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/>
        </svg>
      </button>
      <button class="view-btn" data-view="list" title="List">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/>
          <line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3" y2="6"/>
          <line x1="3" y1="12" x2="3" y2="12"/><line x1="3" y1="18" x2="3" y2="18"/>
        </svg>
      </button>
    </div>
  </div>
</div>

<!-- GALLERY -->
<div class="gallery-wrap">
  <div class="gallery-grid cols-4" id="galleryGrid">
    <div class="loading-spinner">
      <div class="spinner"></div>
      <span>Loading your memories...</span>
    </div>
  </div>
  <div class="pagination" id="pagination"></div>
</div>

<!-- STATS BAR -->
<div class="stats-bar">
  <div class="stats-inner" id="statsBar">
    <div class="stat">Scanning...</div>
  </div>
</div>

<!-- LIGHTBOX -->
<div class="lightbox" id="lightbox">
  <div class="lb-header">
    <span class="lb-title" id="lbTitle"></span>
    <span class="lb-counter" id="lbCounter"></span>
    <button class="lb-close" id="lbClose">✕</button>
  </div>
  <div class="lb-body">
    <button class="lb-nav lb-prev" id="lbPrev">‹</button>
    <img class="lb-img" id="lbImg" src="" alt="" style="display:none">
    <video class="lb-video" id="lbVideo" controls style="display:none"></video>
    <button class="lb-nav lb-next" id="lbNext">›</button>
  </div>
  <div class="lb-footer">
    <div class="lb-thumb-strip" id="lbThumbs"></div>
    <div class="lb-actions">
      <button class="lb-btn fav-btn" id="lbFav">♡ Favorite</button>
      <a class="lb-btn" id="lbDownload" download>↓ Download</a>
      <button class="lb-btn" id="lbInfo">i Info</button>
    </div>
  </div>
</div>

<!-- UPLOAD MODAL -->
<div class="modal-bg" id="uploadModal">
  <div class="modal">
    <div class="modal-title">Upload Photos & Videos</div>
    <div class="modal-sub">Add new memories to your gallery. Supports JPG, PNG, HEIC, MOV, MP4 and more.</div>
    <div class="dropzone" id="dropzone">
      <div class="dropzone-icon">🌸</div>
      <div class="dropzone-text"><strong>Drag & drop files here</strong><br>or click to browse</div>
      <input type="file" id="upload-input" multiple accept="image/*,video/*">
    </div>
    <div class="upload-list" id="uploadList"></div>
    <div class="modal-footer">
      <button class="btn btn-outline" id="uploadCancel">Cancel</button>
      <button class="btn btn-gold" id="uploadSubmit">Upload Files</button>
    </div>
  </div>
</div>

<!-- SELECTION BAR -->
<div class="selection-bar" id="selectionBar">
  <span class="sel-count"><strong id="selCount">0</strong> selected</span>
  <button class="btn btn-outline" style="border-color:rgba(255,255,255,0.2);color:rgba(255,255,255,0.7)" id="selFav">♡ Favorite All</button>
  <button class="btn btn-outline" style="border-color:rgba(255,255,255,0.2);color:rgba(255,255,255,0.7)" id="selDownload">↓ Download All</button>
  <button class="btn btn-outline" style="border-color:rgba(255,255,255,0.2);color:rgba(255,255,255,0.7);margin-left:auto" id="selClear">Cancel</button>
</div>

<!-- TOASTS -->
<div class="toast-container" id="toasts"></div>

<script>
// ─── STATE ───────────────────────────────────────────────────────────────────
const state = {
  tab: 'photos',
  page: 1,
  perPage: 100,
  sort: 'date',
  order: 'desc',
  cols: '4',
  view: 'grid',
  items: [],
  total: 0,
  pages: 0,
  favorites: new Set(),
  selected: new Set(),
  selMode: false,
  searchQ: '',
  showFavOnly: false,
  lbIndex: 0,
  lbItems: [],
};

// ─── LAZY IMG LOADING ─────────────────────────────────────────────────────────
const imgObserver = new IntersectionObserver((entries) => {
  entries.forEach(e => {
    if (e.isIntersecting) {
      const img = e.target;
      if (img.dataset.src) {
        img.src = img.dataset.src;
        img.removeAttribute('data-src');
        imgObserver.unobserve(img);
      }
    }
  });
}, { rootMargin: '200px' });

// ─── API ──────────────────────────────────────────────────────────────────────
async function api(url, opts) {
  const r = await fetch(url, opts);
  return r.json();
}

async function loadFavorites() {
  try {
    const d = await api('/api/favorites');
    state.favorites = new Set(d.favorites || []);
  } catch(e) {}
}

async function scan() {
  showToast('Scanning media files...', 'info');
  const d = await api('/api/scan');
  document.getElementById('photoCount').textContent = d.photos;
  document.getElementById('videoCount').textContent = d.videos;
  updateStats(d);
  await loadPage();
}

async function loadPage() {
  const grid = document.getElementById('galleryGrid');
  grid.innerHTML = '<div class="loading-spinner"><div class="spinner"></div><span>Loading...</span></div>';

  let url, data;
  if (state.searchQ) {
    data = await api(`/api/search?q=${encodeURIComponent(state.searchQ)}`);
    const allItems = data.results || [];
    const filtered = state.tab === 'videos'
      ? allItems.filter(i => ['.mov','.mp4','.m4v','.avi','.mkv'].includes(i.ext))
      : allItems.filter(i => ['.jpg','.jpeg','.png','.webp','.gif','.heic'].includes(i.ext));
    state.items = filtered;
    state.total = filtered.length;
    state.pages = Math.ceil(filtered.length / state.perPage);
    renderGrid(filtered.slice((state.page-1)*state.perPage, state.page*state.perPage));
  } else {
    url = `/api/media?type=${state.tab}&page=${state.page}&per_page=${state.perPage}&sort=${state.sort}&order=${state.order}`;
    data = await api(url);
    state.items = data.items || [];
    state.total = data.total;
    state.pages = data.pages;

    let items = state.items;
    if (state.showFavOnly) {
      items = items.filter(i => state.favorites.has(i.path));
    }
    renderGrid(items);
  }

  renderPagination();
  updatePageInfo();
}

function updateStats(d) {
  const bar = document.getElementById('statsBar');
  bar.innerHTML = `
    <div class="stat">📷 <strong>${d.photos || 0}</strong> Photos</div>
    <div class="stat">🎬 <strong>${d.videos || 0}</strong> Videos</div>
    <div class="stat">✦ <strong>${(d.photos||0)+(d.videos||0)}</strong> Total</div>
  `;
}

function updatePageInfo() {
  const tab = document.querySelector('.tab.active');
  if (tab) tab.querySelector('.tab-count').textContent = state.total;
}

// ─── RENDER ───────────────────────────────────────────────────────────────────
function renderGrid(items) {
  const grid = document.getElementById('galleryGrid');
  grid.className = 'gallery-grid';

  if (state.view === 'list') {
    grid.classList.add('list');
  } else if (state.cols === 'masonry') {
    grid.classList.add('masonry');
  } else {
    grid.classList.add(`cols-${state.cols}`);
  }

  if (!items || items.length === 0) {
    grid.innerHTML = `
      <div class="empty-state" style="grid-column:1/-1">
        <div class="empty-icon">${state.showFavOnly ? '♡' : '🌸'}</div>
        <div class="empty-title">${state.showFavOnly ? 'No favorites yet' : 'No media found'}</div>
        <div class="empty-text">${state.showFavOnly ? 'Heart your favorite photos to find them here' : 'Try scanning your gallery folder or upload new photos'}</div>
      </div>`;
    return;
  }

  const frag = document.createDocumentFragment();
  items.forEach((item, idx) => {
    const card = createCard(item, idx);
    frag.appendChild(card);
  });
  grid.innerHTML = '';
  grid.appendChild(frag);

  // Observe lazy imgs
  grid.querySelectorAll('img[data-src]').forEach(img => imgObserver.observe(img));

  // Set lightbox items
  state.lbItems = items;
}

function createCard(item, idx) {
  const isVideo = ['.mov','.mp4','.m4v','.avi','.mkv'].includes(item.ext);
  const isFav = state.favorites.has(item.path);
  const isSelected = state.selected.has(item.path);

  const card = document.createElement('div');
  card.className = 'photo-card' + (isSelected ? ' selected' : '');
  card.dataset.path = item.path;
  card.dataset.idx = idx;

  if (state.view === 'list') {
    const thumbSrc = isVideo ? '' : `/thumb/${encodeURIComponent(item.path)}`;
    card.innerHTML = `
      <div class="photo-img-wrap" style="position:relative">
        ${isVideo
          ? '<div style="width:40px;height:40px;background:var(--charcoal);border-radius:3px;display:flex;align-items:center;justify-content:center;color:var(--gold);font-size:16px">▶</div>'
          : `<img src="${thumbSrc}" class="photo-img" alt="${item.name}" loading="lazy" style="width:40px;height:40px;object-fit:cover">`
        }
      </div>
      <div class="list-info">
        <div class="list-name">${item.name}</div>
        <div class="list-meta">${formatSize(item.size)} · ${formatDate(item.mtime)}</div>
      </div>
      <button class="action-btn fav ${isFav?'active':''}" data-path="${item.path}" onclick="event.stopPropagation();toggleFav('${item.path}',this)">♡</button>
    `;
  } else {
    const thumbSrc = isVideo ? '' : `/thumb/${encodeURIComponent(item.path)}`;
    card.innerHTML = `
      ${isVideo ? '<div class="video-badge">VIDEO</div>' : ''}
      <div class="photo-img-wrap" style="position:relative">
        ${isVideo
          ? `<div style="aspect-ratio:1;background:var(--charcoal);display:flex;align-items:center;justify-content:center;color:var(--gold);font-size:32px">▶</div>`
          : `<img data-src="${thumbSrc}" class="photo-img shimmer" alt="${item.name}" onload="this.classList.remove('shimmer')">`
        }
      </div>
      <div class="photo-overlay">
        <div class="photo-actions">
          <button class="action-btn fav ${isFav?'active':''}" onclick="event.stopPropagation();toggleFav('${item.path}',this)" title="Favorite">♡</button>
          <a class="action-btn" href="/media/${encodeURIComponent(item.path)}" download="${item.name}" onclick="event.stopPropagation()" title="Download">↓</a>
        </div>
        <div class="photo-name">${item.name}</div>
      </div>
    `;
  }

  card.addEventListener('click', () => {
    if (state.selMode) {
      toggleSelect(item.path, card);
    } else {
      openLightbox(idx);
    }
  });

  return card;
}

// ─── LIGHTBOX ─────────────────────────────────────────────────────────────────
function openLightbox(idx) {
  state.lbIndex = idx;
  const lb = document.getElementById('lightbox');
  lb.classList.add('open');
  document.body.style.overflow = 'hidden';
  renderLightboxItem();
  renderThumbs();
}

function closeLightbox() {
  document.getElementById('lightbox').classList.remove('open');
  document.body.style.overflow = '';
  const vid = document.getElementById('lbVideo');
  vid.pause();
  vid.src = '';
}

function renderLightboxItem() {
  const item = state.lbItems[state.lbIndex];
  if (!item) return;

  const img = document.getElementById('lbImg');
  const vid = document.getElementById('lbVideo');
  const isVideo = ['.mov','.mp4','.m4v','.avi','.mkv'].includes(item.ext);

  document.getElementById('lbTitle').textContent = item.name;
  document.getElementById('lbCounter').textContent = `${state.lbIndex + 1} / ${state.lbItems.length}`;

  const dl = document.getElementById('lbDownload');
  dl.href = `/media/${encodeURIComponent(item.path)}`;
  dl.download = item.name;

  const favBtn = document.getElementById('lbFav');
  const isFav = state.favorites.has(item.path);
  favBtn.textContent = isFav ? '♥ Favorited' : '♡ Favorite';
  favBtn.className = `lb-btn fav-btn${isFav ? ' active' : ''}`;
  favBtn.dataset.path = item.path;

  if (isVideo) {
    img.style.display = 'none';
    vid.style.display = 'block';
    vid.src = `/media/${encodeURIComponent(item.path)}`;
    vid.play().catch(()=>{});
  } else {
    vid.pause(); vid.src = '';
    vid.style.display = 'none';
    img.style.display = 'block';
    img.src = `/media/${encodeURIComponent(item.path)}`;
    img.style.animation = 'none';
    requestAnimationFrame(() => { img.style.animation = ''; });
  }

  // Update active thumb
  document.querySelectorAll('.lb-thumb').forEach((t, i) => {
    t.classList.toggle('active', i === state.lbIndex);
    if (i === state.lbIndex) t.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });
  });
}

function renderThumbs() {
  const strip = document.getElementById('lbThumbs');
  const items = state.lbItems.slice(0, 100); // Max 100 thumbs
  strip.innerHTML = items.map((item, i) => {
    const isVideo = ['.mov','.mp4','.m4v'].includes(item.ext);
    if (isVideo) {
      return `<div class="lb-thumb" style="background:var(--charcoal);display:flex;align-items:center;justify-content:center;color:var(--gold);font-size:12px;cursor:pointer" data-idx="${i}" onclick="jumpLb(${i})">▶</div>`;
    }
    return `<img class="lb-thumb ${i===state.lbIndex?'active':''}" src="/thumb/${encodeURIComponent(item.path)}" loading="lazy" data-idx="${i}" onclick="jumpLb(${i})" alt="${item.name}">`;
  }).join('');
}

function jumpLb(idx) {
  state.lbIndex = idx;
  renderLightboxItem();
  document.querySelectorAll('.lb-thumb').forEach((t, i) => t.classList.toggle('active', i === idx));
}

function navLb(dir) {
  const newIdx = state.lbIndex + dir;
  if (newIdx < 0 || newIdx >= state.lbItems.length) return;
  jumpLb(newIdx);
}

// ─── FAVORITES ────────────────────────────────────────────────────────────────
async function toggleFav(path, btn) {
  try {
    const d = await api('/api/favorites', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path, action: 'toggle' })
    });
    state.favorites = new Set(d.favorites);
    const added = state.favorites.has(path);
    if (btn) {
      btn.classList.toggle('active', added);
    }
    // Update lb fav btn
    const lbFav = document.getElementById('lbFav');
    if (lbFav.dataset.path === path) {
      lbFav.textContent = added ? '♥ Favorited' : '♡ Favorite';
      lbFav.className = `lb-btn fav-btn${added ? ' active' : ''}`;
    }
    showToast(added ? '♥ Added to favorites' : 'Removed from favorites', 'success');
  } catch(e) {
    showToast('Could not update favorites', 'error');
  }
}

// ─── SELECTION ────────────────────────────────────────────────────────────────
function toggleSelect(path, card) {
  if (state.selected.has(path)) {
    state.selected.delete(path);
    card.classList.remove('selected');
  } else {
    state.selected.add(path);
    card.classList.add('selected');
  }
  updateSelBar();
}

function updateSelBar() {
  const bar = document.getElementById('selectionBar');
  const count = state.selected.size;
  document.getElementById('selCount').textContent = count;
  bar.classList.toggle('visible', count > 0 && state.selMode);
}

// ─── UPLOAD ───────────────────────────────────────────────────────────────────
let pendingFiles = [];

function setupUpload() {
  const dropzone = document.getElementById('dropzone');
  const input = document.getElementById('upload-input');

  dropzone.addEventListener('click', () => input.click());
  input.addEventListener('change', () => {
    pendingFiles = [...input.files];
    renderUploadList();
  });

  dropzone.addEventListener('dragover', e => { e.preventDefault(); dropzone.classList.add('drag-over'); });
  dropzone.addEventListener('dragleave', () => dropzone.classList.remove('drag-over'));
  dropzone.addEventListener('drop', e => {
    e.preventDefault();
    dropzone.classList.remove('drag-over');
    pendingFiles = [...e.dataTransfer.files];
    renderUploadList();
  });

  document.getElementById('uploadSubmit').addEventListener('click', submitUpload);
  document.getElementById('uploadCancel').addEventListener('click', closeUploadModal);
}

function renderUploadList() {
  const list = document.getElementById('uploadList');
  list.innerHTML = pendingFiles.map((f, i) => `
    <div class="upload-item" id="upload-item-${i}">
      <span style="font-size:16px">${f.type.startsWith('video') ? '🎬' : '🖼️'}</span>
      <span class="upload-item-name">${f.name}</span>
      <span style="color:var(--warm-gray);font-size:11px">${formatSize(f.size)}</span>
    </div>
  `).join('');
}

async function submitUpload() {
  if (!pendingFiles.length) return;
  const btn = document.getElementById('uploadSubmit');
  btn.textContent = 'Uploading...';
  btn.disabled = true;

  const form = new FormData();
  pendingFiles.forEach(f => form.append('file', f));

  try {
    const resp = await fetch('/api/upload', { method: 'POST', body: form });
    const d = await resp.json();
    showToast(`✓ Uploaded ${d.count || 0} files`, 'success');
    closeUploadModal();
    await scan();
  } catch(e) {
    showToast('Upload failed. Is the server running?', 'error');
  } finally {
    btn.textContent = 'Upload Files';
    btn.disabled = false;
  }
}

function closeUploadModal() {
  document.getElementById('uploadModal').classList.remove('open');
  pendingFiles = [];
  document.getElementById('uploadList').innerHTML = '';
}

// ─── PAGINATION ───────────────────────────────────────────────────────────────
function renderPagination() {
  const el = document.getElementById('pagination');
  if (state.pages <= 1) { el.innerHTML = ''; return; }

  let html = `<button class="page-btn" onclick="goPage(${state.page-1})" ${state.page<=1?'disabled':''}>‹</button>`;
  const maxBtns = 7;
  let start = Math.max(1, state.page - 3);
  let end = Math.min(state.pages, start + maxBtns - 1);
  if (end - start < maxBtns - 1) start = Math.max(1, end - maxBtns + 1);

  if (start > 1) html += `<button class="page-btn" onclick="goPage(1)">1</button>${start>2?'<span class="page-info">…</span>':''}`;
  for (let i = start; i <= end; i++) {
    html += `<button class="page-btn ${i===state.page?'active':''}" onclick="goPage(${i})">${i}</button>`;
  }
  if (end < state.pages) html += `${end<state.pages-1?'<span class="page-info">…</span>':''}<button class="page-btn" onclick="goPage(${state.pages})">${state.pages}</button>`;
  html += `<button class="page-btn" onclick="goPage(${state.page+1})" ${state.page>=state.pages?'disabled':''}>›</button>`;
  html += `<span class="page-info">Page ${state.page} of ${state.pages}</span>`;

  el.innerHTML = html;
}

function goPage(p) {
  if (p < 1 || p > state.pages || p === state.page) return;
  state.page = p;
  loadPage();
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

// ─── TOAST ────────────────────────────────────────────────────────────────────
function showToast(msg, type='success') {
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = msg;
  document.getElementById('toasts').appendChild(el);
  setTimeout(() => el.remove(), 3000);
}

// ─── UTILS ───────────────────────────────────────────────────────────────────
function formatSize(bytes) {
  if (bytes > 1e9) return (bytes/1e9).toFixed(1) + ' GB';
  if (bytes > 1e6) return (bytes/1e6).toFixed(1) + ' MB';
  return (bytes/1e3).toFixed(0) + ' KB';
}

function formatDate(ts) {
  return new Date(ts * 1000).toLocaleDateString('en-US', { year:'numeric', month:'short', day:'numeric' });
}

// ─── EVENT LISTENERS ─────────────────────────────────────────────────────────
document.querySelectorAll('.tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    tab.classList.add('active');
    state.tab = tab.dataset.tab;
    state.page = 1;
    loadPage();
  });
});

document.getElementById('perPageSel').addEventListener('change', e => {
  state.perPage = parseInt(e.target.value);
  state.page = 1;
  loadPage();
});

document.getElementById('sortSel').addEventListener('change', e => {
  const [sort, order] = e.target.value.split('-');
  state.sort = sort;
  state.order = order;
  state.page = 1;
  loadPage();
});

document.getElementById('colsSel').addEventListener('change', e => {
  state.cols = e.target.value;
  loadPage();
});

document.querySelectorAll('.view-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.view-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    state.view = btn.dataset.view;
    loadPage();
  });
});

document.getElementById('scanBtn').addEventListener('click', scan);
document.getElementById('uploadBtn').addEventListener('click', () => document.getElementById('uploadModal').classList.add('open'));

let searchTimeout;
document.getElementById('searchInput').addEventListener('input', e => {
  clearTimeout(searchTimeout);
  state.searchQ = e.target.value.trim();
  state.page = 1;
  searchTimeout = setTimeout(loadPage, 300);
});

document.getElementById('favBtn').addEventListener('click', () => {
  state.showFavOnly = !state.showFavOnly;
  document.getElementById('favBtn').classList.toggle('active', state.showFavOnly);
  loadPage();
});

document.getElementById('selectBtn').addEventListener('click', () => {
  state.selMode = !state.selMode;
  state.selected.clear();
  document.getElementById('selectBtn').textContent = state.selMode ? 'Done' : 'Select';
  document.getElementById('selectionBar').classList.remove('visible');
  document.querySelectorAll('.photo-card').forEach(c => c.classList.remove('selected'));
});

document.getElementById('selClear').addEventListener('click', () => {
  state.selMode = false;
  state.selected.clear();
  document.getElementById('selectBtn').textContent = 'Select';
  document.getElementById('selectionBar').classList.remove('visible');
  document.querySelectorAll('.photo-card').forEach(c => c.classList.remove('selected'));
});

// Lightbox controls
document.getElementById('lbClose').addEventListener('click', closeLightbox);
document.getElementById('lbPrev').addEventListener('click', () => navLb(-1));
document.getElementById('lbNext').addEventListener('click', () => navLb(1));
document.getElementById('lbFav').addEventListener('click', e => {
  const path = e.currentTarget.dataset.path;
  if (path) toggleFav(path, null);
});

document.getElementById('lbInfo').addEventListener('click', () => {
  const item = state.lbItems[state.lbIndex];
  if (item) showToast(`${item.name} · ${formatSize(item.size)} · ${formatDate(item.mtime)}`, 'success');
});

document.getElementById('lightbox').addEventListener('click', e => {
  if (e.target === e.currentTarget) closeLightbox();
});

document.getElementById('uploadModal').addEventListener('click', e => {
  if (e.target === e.currentTarget) closeUploadModal();
});

// Keyboard
document.addEventListener('keydown', e => {
  const lb = document.getElementById('lightbox');
  if (lb.classList.contains('open')) {
    if (e.key === 'ArrowLeft') navLb(-1);
    else if (e.key === 'ArrowRight') navLb(1);
    else if (e.key === 'Escape') closeLightbox();
    else if (e.key === 'f' || e.key === 'F') {
      const item = state.lbItems[state.lbIndex];
      if (item) toggleFav(item.path, null);
    }
  } else {
    if (e.key === 'Escape' && state.selMode) {
      state.selMode = false;
      state.selected.clear();
      document.getElementById('selectBtn').textContent = 'Select';
      document.getElementById('selectionBar').classList.remove('visible');
    }
  }
});

// Touch swipe
let touchStartX = 0;
document.getElementById('lightbox').addEventListener('touchstart', e => { touchStartX = e.touches[0].clientX; });
document.getElementById('lightbox').addEventListener('touchend', e => {
  const dx = e.changedTouches[0].clientX - touchStartX;
  if (Math.abs(dx) > 50) navLb(dx < 0 ? 1 : -1);
});

// ─── INIT ────────────────────────────────────────────────────────────────────
setupUpload();
loadFavorites().then(scan);
</script>
</body>
</html>
'''


class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


def run_server(directory, port=8000):
    global GALLERY_DIR
    GALLERY_DIR = os.path.realpath(directory)

    if not os.path.exists(GALLERY_DIR):
        print(f"Error: Directory not found: {GALLERY_DIR}")
        sys.exit(1)

    print(f"""
╔══════════════════════════════════════════════════════╗
║          Wedding Gallery Pro — Production            ║
╠══════════════════════════════════════════════════════╣
║  Gallery: {GALLERY_DIR[:44]:<44} ║
║  URL:     http://localhost:{port:<25} ║
║  PIL:     {'✓ Fast thumbnails enabled' if HAS_PIL else '✗ Install Pillow for fast thumbs':36} ║
╚══════════════════════════════════════════════════════╝
  Open your browser and go to: http://localhost:{port}/
  Press Ctrl+C to stop.
""")

    handler = WeddingGalleryHandler
    with ThreadedTCPServer(("", port), handler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down gracefully...")
            sys.exit(0)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='Wedding Gallery Pro Server')
    parser.add_argument('directory', nargs='?', default='.', help='Gallery directory (default: current dir)')
    parser.add_argument('--port', type=int, default=8000, help='Port (default: 8000)')
    args = parser.parse_args()
    run_server(args.directory, args.port)
