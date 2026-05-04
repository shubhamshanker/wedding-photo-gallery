#!/usr/bin/env python3
"""
Wedding Gallery Pro+ - Premium Production Server
Ultra-optimized, feature-rich wedding photo gallery server.
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
import gzip
import webbrowser
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote
from functools import lru_cache
from datetime import datetime
from collections import defaultdict

# Try to import optional fast libs
try:
    import PIL.Image
    import PIL.ExifTags
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    from concurrent.futures import ThreadPoolExecutor
    HAS_THREADING = True
except ImportError:
    HAS_THREADING = False

# ─── GLOBALS ──────────────────────────────────────────────────────────────────
GALLERY_DIR = None
CACHE = {}
CACHE_LOCK = threading.Lock()
SUPPORTED_IMAGES = {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.heic', '.bmp', '.tiff'}
SUPPORTED_VIDEOS = {'.mov', '.mp4', '.m4v', '.avi', '.mkv', '.webm'}

# Configuration
CONFIG = {
    'max_cache_size': 1024,  # 1GB for Railway's 8GB RAM
    'thumbnail_size': (480, 480),
    'thumbnail_quality': 86,
    'preview_size': (1600, 1600),
    'preview_quality': 88,
    'enable_gzip': True,
    'enable_etag': True,
    'cache_duration': 86400,  # 24 hours
    'auto_open_browser': False,  # Disable by default for production
}


# ─── CACHING ──────────────────────────────────────────────────────────────────
@lru_cache(maxsize=1000)
def get_file_hash(path):
    """Fast hash using file mtime + size."""
    try:
        stat = os.stat(path)
        return f"{stat.st_mtime}-{stat.st_size}"
    except:
        return str(time.time())


class LRUCache:
    """Simple LRU cache with size limit."""
    def __init__(self, max_size_mb=500):
        self.cache = {}
        self.access_times = {}
        self.sizes = {}
        self.max_size = max_size_mb * 1024 * 1024
        self.current_size = 0
        self.lock = threading.Lock()

    def get(self, key):
        with self.lock:
            if key in self.cache:
                self.access_times[key] = time.time()
                return self.cache[key]
        return None

    def set(self, key, value):
        with self.lock:
            size = len(value) if isinstance(value, bytes) else sys.getsizeof(value)

            # Evict if needed
            while self.current_size + size > self.max_size and self.cache:
                oldest_key = min(self.access_times.items(), key=lambda x: x[1])[0]
                self.current_size -= self.sizes.get(oldest_key, 0)
                del self.cache[oldest_key]
                del self.access_times[oldest_key]
                del self.sizes[oldest_key]

            self.cache[key] = value
            self.access_times[key] = time.time()
            self.sizes[key] = size
            self.current_size += size

    def clear(self):
        with self.lock:
            self.cache.clear()
            self.access_times.clear()
            self.sizes.clear()
            self.current_size = 0

    def stats(self):
        with self.lock:
            return {
                'items': len(self.cache),
                'size_mb': round(self.current_size / 1024 / 1024, 2),
                'max_size_mb': round(self.max_size / 1024 / 1024, 2)
            }


THUMB_CACHE = LRUCache(max_size_mb=CONFIG['max_cache_size'])


# ─── MEDIA SCANNING ───────────────────────────────────────────────────────────
def scan_media_files(directory):
    """Recursively scan for all media files with parallel processing."""
    photos = []
    videos = []
    seen = set()

    def scan_dir(root):
        local_photos = []
        local_videos = []
        try:
            for fname in os.listdir(root):
                if fname.startswith('.'):
                    continue

                fpath = os.path.join(root, fname)

                if os.path.isdir(fpath):
                    # Recursively scan subdirectories
                    sub_photos, sub_videos = scan_dir(fpath)
                    local_photos.extend(sub_photos)
                    local_videos.extend(sub_videos)
                    continue

                # Resolve symlinks
                try:
                    real = os.path.realpath(fpath)
                    if real in seen:
                        continue
                    seen.add(real)
                except Exception:
                    continue

                ext = Path(fname).suffix.lower()
                if ext not in SUPPORTED_IMAGES and ext not in SUPPORTED_VIDEOS:
                    continue

                try:
                    stat = os.stat(fpath)
                    rel = os.path.relpath(fpath, directory)
                    entry = {
                        'name': fname,
                        'path': rel,
                        'size': stat.st_size,
                        'mtime': stat.st_mtime,
                        'ext': ext
                    }

                    if ext in SUPPORTED_IMAGES:
                        local_photos.append(entry)
                    elif ext in SUPPORTED_VIDEOS:
                        local_videos.append(entry)
                except Exception:
                    pass

        except Exception as e:
            print(f"Error scanning {root}: {e}")

        return local_photos, local_videos

    return scan_dir(directory)


def get_exif_data(image_path):
    """Extract EXIF data from image."""
    if not HAS_PIL:
        return {}

    try:
        img = PIL.Image.open(image_path)
        exif = img._getexif()
        if not exif:
            return {}

        exif_data = {}
        for tag_id, value in exif.items():
            tag = PIL.ExifTags.TAGS.get(tag_id, tag_id)
            exif_data[tag] = str(value)

        return {
            'camera': exif_data.get('Model', ''),
            'date': exif_data.get('DateTime', ''),
            'iso': exif_data.get('ISOSpeedRatings', ''),
            'exposure': exif_data.get('ExposureTime', ''),
            'aperture': exif_data.get('FNumber', ''),
        }
    except:
        return {}


# ─── REQUEST HANDLER ──────────────────────────────────────────────────────────
class WeddingGalleryProHandler(http.server.BaseHTTPRequestHandler):
    """Ultra-optimized handler for wedding gallery."""

    protocol_version = 'HTTP/1.1'

    def check_auth(self):
        """Verify HTTP Basic Authentication if enabled."""
        auth_user = os.environ.get('AUTH_USER')
        auth_pass = os.environ.get('AUTH_PASS')

        # Skip auth if not configured
        if not auth_user or not auth_pass:
            return True

        auth_header = self.headers.get('Authorization')
        if not auth_header:
            self.send_auth_required()
            return False

        try:
            auth_type, credentials = auth_header.split(' ', 1)
            if auth_type.lower() != 'basic':
                self.send_auth_required()
                return False

            decoded = base64.b64decode(credentials).decode('utf-8')
            username, password = decoded.split(':', 1)

            if username == auth_user and password == auth_pass:
                return True
        except:
            pass

        self.send_auth_required()
        return False

    def send_auth_required(self):
        """Send 401 Unauthorized response."""
        self.send_response(401)
        self.send_header('WWW-Authenticate', 'Basic realm="Wedding Gallery"')
        self.send_header('Content-Type', 'text/html')
        body = b'<h1>401 Unauthorized</h1><p>Please enter credentials.</p>'
        self.send_header('Content-Length', len(body))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        """Custom logging with timestamps."""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"[{timestamp}] {self.address_string()} - {format % args}")

    def log_error(self, format, *args):
        """Silent error logging for broken pipes."""
        if 'Broken pipe' in str(args):
            return
        print(f"ERROR: {format % args}")

    def handle_one_request(self):
        try:
            super().handle_one_request()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        # Skip auth for health checks, check auth for everything else
        if path != '/api/health' and not self.check_auth():
            return

        try:
            # Route handling
            routes = {
                '/': self.serve_gallery_html,
                '/index.html': self.serve_gallery_html,
                '/api/scan': self.api_scan,
                '/api/media': lambda: self.api_media(qs),
                '/api/favorites': self.api_get_favorites,
                '/api/search': lambda: self.api_search(qs),
                '/api/stats': self.api_stats,
                '/api/health': self.api_health,
                '/api/cache/clear': self.api_clear_cache,
                '/api/config': self.api_get_config,
            }

            if path in routes:
                routes[path]()
            elif path.startswith('/thumb/'):
                self.serve_thumbnail(unquote(path[7:]))
            elif path.startswith('/preview/'):
                self.serve_preview(unquote(path[9:]))
            elif path.startswith('/media/'):
                self.serve_media_file(unquote(path[7:]))
            elif path.startswith('/api/exif/'):
                self.api_get_exif(unquote(path[10:]))
            else:
                self.send_404()

        except Exception as e:
            self.send_error_response(500, str(e))

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        # Check authentication first
        if not self.check_auth():
            return

        try:
            routes = {
                '/api/favorites': self.api_save_favorite,
                '/api/upload': self.api_upload,
                '/api/config': self.api_update_config,
            }

            if path in routes:
                routes[path]()
            else:
                self.send_404()
        except Exception as e:
            self.send_error_response(500, str(e))

    # ─── RESPONSE HELPERS ─────────────────────────────────────────────────────
    def send_json(self, data, status=200):
        """Send JSON response with optional gzip compression."""
        body = json.dumps(data, separators=(',', ':')).encode('utf-8')

        # Gzip if requested and enabled
        if CONFIG['enable_gzip'] and 'gzip' in self.headers.get('Accept-Encoding', ''):
            body = gzip.compress(body)
            compressed = True
        else:
            compressed = False

        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', len(body))
        if compressed:
            self.send_header('Content-Encoding', 'gzip')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()

        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def send_404(self):
        self.send_json({'error': 'Not found'}, 404)

    def send_error_response(self, code, msg):
        self.send_json({'error': msg, 'code': code}, code)

    # ─── API ENDPOINTS ────────────────────────────────────────────────────────
    def api_health(self):
        """Health check endpoint."""
        self.send_json({
            'status': 'healthy',
            'timestamp': time.time(),
            'cache': THUMB_CACHE.stats(),
            'pil_available': HAS_PIL,
        })

    def api_scan(self):
        """Scan and cache media list."""
        global CACHE
        start_time = time.time()

        photos, videos = scan_media_files(GALLERY_DIR)

        with CACHE_LOCK:
            CACHE['photos'] = photos
            CACHE['videos'] = videos
            CACHE['scan_time'] = time.time()

        elapsed = time.time() - start_time

        self.send_json({
            'photos': len(photos),
            'videos': len(videos),
            'total': len(photos) + len(videos),
            'scan_duration_ms': round(elapsed * 1000, 2)
        })

    def api_media(self, qs):
        """Return paginated media list."""
        media_type = qs.get('type', ['photos'])[0]
        page = int(qs.get('page', [1])[0])
        per_page = int(qs.get('per_page', [100])[0])
        sort = qs.get('sort', ['date'])[0]
        order = qs.get('order', ['desc'])[0]
        date_from = qs.get('date_from', [''])[0]
        date_to = qs.get('date_to', [''])[0]

        with CACHE_LOCK:
            if media_type == 'videos':
                items = CACHE.get('videos', [])
            else:
                items = CACHE.get('photos', [])

        # Date filter (inclusive). Bad input → ignore, never crash.
        if date_from or date_to:
            from datetime import datetime
            try:
                lo = datetime.strptime(date_from, '%Y-%m-%d').timestamp() if date_from else 0
            except ValueError:
                lo = 0
            try:
                hi_dt = datetime.strptime(date_to, '%Y-%m-%d') if date_to else None
                # End of day (inclusive)
                hi = hi_dt.timestamp() + 86400 - 1 if hi_dt else float('inf')
            except ValueError:
                hi = float('inf')
            items = [it for it in items if lo <= it.get('mtime', 0) <= hi]

        # Sort
        reverse = order == 'desc'
        if sort == 'date':
            items = sorted(items, key=lambda x: x['mtime'], reverse=reverse)
        elif sort == 'name':
            items = sorted(items, key=lambda x: x['name'], reverse=reverse)
        elif sort == 'size':
            items = sorted(items, key=lambda x: x['size'], reverse=reverse)

        # Clamp per_page to a sane range to avoid runaway responses
        per_page = max(1, min(per_page, 1000))

        total = len(items)
        start = (page - 1) * per_page
        end = start + per_page
        page_items = items[start:end]

        self.send_json({
            'items': page_items,
            'total': total,
            'page': page,
            'per_page': per_page,
            'pages': (total + per_page - 1) // per_page if per_page > 0 else 1
        })

    def api_search(self, qs):
        """Search by filename."""
        q = qs.get('q', [''])[0].lower()
        with CACHE_LOCK:
            photos = CACHE.get('photos', [])
            videos = CACHE.get('videos', [])

        results = [p for p in photos + videos if q in p['name'].lower()][:200]
        self.send_json({'results': results, 'total': len(results)})

    def api_stats(self):
        """Return gallery stats."""
        with CACHE_LOCK:
            photos = CACHE.get('photos', [])
            videos = CACHE.get('videos', [])

        total_size = sum(p['size'] for p in photos + videos)

        # Group by extension
        extensions = defaultdict(int)
        for item in photos + videos:
            extensions[item['ext']] += 1

        self.send_json({
            'photos': len(photos),
            'videos': len(videos),
            'total_files': len(photos) + len(videos),
            'total_size_bytes': total_size,
            'total_size_gb': round(total_size / 1e9, 2),
            'scan_time': CACHE.get('scan_time', 0),
            'extensions': dict(extensions),
            'cache': THUMB_CACHE.stats(),
        })

    def api_get_exif(self, rel_path):
        """Get EXIF data for an image."""
        full_path = os.path.join(GALLERY_DIR, rel_path)

        if not os.path.exists(full_path):
            self.send_404()
            return

        exif = get_exif_data(full_path)
        self.send_json({'path': rel_path, 'exif': exif})

    def api_get_favorites(self):
        """Get favorites list."""
        fav_file = os.path.join(GALLERY_DIR, '.favorites.json')
        try:
            with open(fav_file) as f:
                favs = json.load(f)
        except Exception:
            favs = []
        self.send_json({'favorites': favs})

    def api_save_favorite(self):
        """Save/toggle favorite."""
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

    def api_clear_cache(self):
        """Clear thumbnail cache."""
        THUMB_CACHE.clear()
        self.send_json({'status': 'cache cleared', 'cache': THUMB_CACHE.stats()})

    def api_get_config(self):
        """Get current configuration."""
        self.send_json({'config': CONFIG})

    def api_update_config(self):
        """Update configuration."""
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length)
        data = json.loads(body)

        for key, value in data.items():
            if key in CONFIG:
                CONFIG[key] = value

        self.send_json({'config': CONFIG, 'status': 'updated'})

    def api_upload(self):
        """Handle file upload with progress."""
        content_type = self.headers.get('Content-Type', '')
        if 'multipart/form-data' not in content_type:
            self.send_json({'error': 'multipart required'}, 400)
            return

        length = int(self.headers.get('Content-Length', 0))
        if length > 500 * 1024 * 1024:  # 500MB limit
            self.send_json({'error': 'File too large (max 500MB)'}, 400)
            return

        body = self.rfile.read(length)
        boundary = content_type.split('boundary=')[1].encode()

        # Parse multipart
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

    # ─── MEDIA SERVING ────────────────────────────────────────────────────────
    def serve_thumbnail(self, rel_path):
        """Serve optimized thumbnail with caching."""
        full_path = os.path.join(GALLERY_DIR, rel_path)

        if not os.path.exists(full_path):
            self.send_404()
            return

        # Check cache
        cache_key = f"thumb:{rel_path}:{get_file_hash(full_path)}"
        cached = THUMB_CACHE.get(cache_key)

        if cached:
            self._send_image_bytes(cached, 'image/jpeg')
            return

        # Generate thumbnail with PIL
        if HAS_PIL:
            try:
                img = PIL.Image.open(full_path)
                img.thumbnail(CONFIG['thumbnail_size'], PIL.Image.Resampling.LANCZOS)

                if img.mode in ('RGBA', 'P', 'LA'):
                    background = PIL.Image.new('RGB', img.size, (255, 255, 255))
                    if img.mode == 'P':
                        img = img.convert('RGBA')
                    background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
                    img = background
                elif img.mode != 'RGB':
                    img = img.convert('RGB')

                buf = io.BytesIO()
                img.save(buf, 'JPEG', quality=CONFIG['thumbnail_quality'], optimize=True)
                thumb_bytes = buf.getvalue()

                # Cache it
                THUMB_CACHE.set(cache_key, thumb_bytes)

                self._send_image_bytes(thumb_bytes, 'image/jpeg')
                return
            except Exception as e:
                print(f"Thumbnail generation failed for {rel_path}: {e}")

        # Fallback: serve original with range support
        self.serve_media_file(rel_path)

    def serve_preview(self, rel_path):
        """Serve a medium-size preview (~1600px) for the lightbox.

        Base implementation just serves the original; R2 handler overrides
        to generate a downsized JPEG and cache it.
        """
        self.serve_media_file(rel_path)

    def _send_image_bytes(self, data, content_type):
        """Send image bytes with caching headers."""
        etag = hashlib.md5(data[:100]).hexdigest() if CONFIG['enable_etag'] else None

        if etag and self.headers.get('If-None-Match') == etag:
            self.send_response(304)
            self.end_headers()
            return

        self.send_response(200)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', len(data))
        self.send_header('Cache-Control', f'public, max-age={CONFIG["cache_duration"]}')
        if etag:
            self.send_header('ETag', etag)
        self.end_headers()

        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def serve_media_file(self, rel_path):
        """Serve media with range request support."""
        full_path = os.path.join(GALLERY_DIR, rel_path)

        if not os.path.exists(full_path):
            self.send_404()
            return

        # ETag support
        file_hash = get_file_hash(full_path)
        etag = hashlib.md5(file_hash.encode()).hexdigest() if CONFIG['enable_etag'] else None

        if etag and self.headers.get('If-None-Match') == etag:
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
            self.send_header('Cache-Control', f'public, max-age={CONFIG["cache_duration"]}')
            if etag:
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
            self.send_header('Cache-Control', f'public, max-age={CONFIG["cache_duration"]}')
            if etag:
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
        """Serve the gallery HTML (imported from server_claude.py)."""
        from server_claude import get_gallery_html
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


# ─── SERVER ───────────────────────────────────────────────────────────────────
class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


def run_server(directory, port=8000, auto_open=True):
    global GALLERY_DIR
    GALLERY_DIR = os.path.realpath(directory)

    if not os.path.exists(GALLERY_DIR):
        print(f"❌ Error: Directory not found: {GALLERY_DIR}")
        sys.exit(1)

    print(f"""
╔════════════════════════════════════════════════════════════════╗
║                                                                ║
║          🎊 Wedding Gallery Pro+ — Production Ready 🎊        ║
║                                                                ║
╠════════════════════════════════════════════════════════════════╣
║                                                                ║
║  📁 Gallery: {os.path.basename(GALLERY_DIR):<48} ║
║  🌐 URL:     http://localhost:{port:<37} ║
║  🖼️  PIL:     {'✓ Fast thumbnails enabled' if HAS_PIL else '✗ Install Pillow for thumbnails':48} ║
║  🗜️  Gzip:    {'✓ Compression enabled' if CONFIG['enable_gzip'] else '✗ Compression disabled':48} ║
║  💾 Cache:   {CONFIG['max_cache_size']}MB max thumbnail cache{' ' * 28} ║
║                                                                ║
╠════════════════════════════════════════════════════════════════╣
║                                                                ║
║  ⚡ Features:                                                  ║
║     • Lazy loading & pagination                               ║
║     • Optimized thumbnails with LRU cache                     ║
║     • EXIF data support                                       ║
║     • Favorites & upload                                      ║
║     • Health checks & monitoring                              ║
║     • Gzip compression                                        ║
║                                                                ║
╠════════════════════════════════════════════════════════════════╣
║                                                                ║
║  🚀 Ready! Open: http://localhost:{port}/{' ' * 26} ║
║  ⏸️  Stop: Press Ctrl+C{' ' * 39} ║
║                                                                ║
╚════════════════════════════════════════════════════════════════╝
""")

    # Auto-open browser (only in development, not on Railway)
    is_production = os.environ.get('RAILWAY_ENVIRONMENT') is not None
    if auto_open and CONFIG['auto_open_browser'] and not is_production:
        def open_browser():
            time.sleep(1.5)
            try:
                webbrowser.open(f'http://localhost:{port}/')
                print(f"🌐 Opened gallery in browser!")
            except:
                pass

        thread = threading.Thread(target=open_browser, daemon=True)
        thread.start()

    handler = WeddingGalleryProHandler
    with ThreadedTCPServer(("", port), handler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n\n✨ Shutting down gracefully...")
            print(f"📊 Final cache stats: {THUMB_CACHE.stats()}")
            sys.exit(0)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description='Wedding Gallery Pro+ Server',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 server_pro.py                    # Serve current directory on port 8000
  python3 server_pro.py /path/to/photos    # Serve specific directory
  python3 server_pro.py --port 8080        # Use different port
  python3 server_pro.py --no-auto-open     # Don't auto-open browser
        """
    )
    parser.add_argument('directory', nargs='?', default='.',
                       help='Gallery directory (default: current dir)')
    default_port = int(os.environ.get('PORT', 8000))
    parser.add_argument('--port', type=int, default=default_port,
                       help='Port (default: from PORT env or 8000)')
    parser.add_argument('--no-auto-open', action='store_true',
                       help='Don\'t automatically open browser')
    parser.add_argument('--cache-size', type=int, default=500,
                       help='Max thumbnail cache size in MB (default: 500)')

    args = parser.parse_args()

    CONFIG['auto_open_browser'] = not args.no_auto_open
    CONFIG['max_cache_size'] = args.cache_size

    run_server(args.directory, args.port)
