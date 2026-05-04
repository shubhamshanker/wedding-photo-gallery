#!/usr/bin/env python3
"""
Wedding Gallery with Cloudflare R2 Storage
Serves photos from R2, supports uploads to R2
"""

import os
import sys
import json
import time
import io
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# Import server_pro as base
from server_pro import (
    WeddingGalleryProHandler,
    ThreadedTCPServer,
    CACHE, CACHE_LOCK,
    SUPPORTED_IMAGES, SUPPORTED_VIDEOS,
    CONFIG, THUMB_CACHE,
    HAS_PIL
)

# R2 imports
try:
    import boto3
    from botocore.client import Config
    from botocore.exceptions import ClientError
    HAS_BOTO3 = True
except ImportError:
    HAS_BOTO3 = False
    class ClientError(Exception):  # noqa: N818 — fallback so refs don't NameError
        pass

# ─── R2 CLIENT ────────────────────────────────────────────────────────────────
R2_CLIENT = None
R2_BUCKET = None

def init_r2():
    """Initialize R2 client from environment variables."""
    global R2_CLIENT, R2_BUCKET

    if not HAS_BOTO3:
        print("⚠️  Warning: boto3 not installed. R2 features disabled.")
        print("   Install: pip install boto3")
        return False

    access_key = os.environ.get('R2_ACCESS_KEY')
    secret_key = os.environ.get('R2_SECRET_KEY')
    endpoint = os.environ.get('R2_ENDPOINT')
    bucket = os.environ.get('R2_BUCKET', 'wedding-gallery-photos')

    if not all([access_key, secret_key, endpoint]):
        print("⚠️  Warning: R2 credentials not set. Using local storage.")
        print("   Set: R2_ACCESS_KEY, R2_SECRET_KEY, R2_ENDPOINT")
        return False

    try:
        R2_CLIENT = boto3.client(
            's3',
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=Config(signature_version='s3v4'),
            region_name='auto'
        )
        R2_BUCKET = bucket

        # Test connection
        R2_CLIENT.head_bucket(Bucket=bucket)
        print(f"✅ R2 connected: {bucket}")
        return True
    except Exception as e:
        print(f"❌ R2 connection failed: {e}")
        R2_CLIENT = None
        return False


# ─── DERIVATIVE GENERATION (thumb + preview) ──────────────────────────────────
DERIV_PREFIX = '_cache'  # all generated thumbs/previews live here in R2

def _deriv_key(kind, src_key):
    """R2 key for a derivative: _cache/thumb/<src> or _cache/preview/<src>."""
    return f"{DERIV_PREFIX}/{kind}/{src_key}"


def get_or_make_r2_derivative(src_key, kind):
    """Return JPEG bytes for thumb/preview of src_key. Cached in memory + R2.

    Lookup order: memory cache → R2 _cache/<kind>/<src> → generate from original.
    Once generated, persists to R2 so dyno restarts don't lose work.
    Returns None on failure (caller should fall back).
    """
    if not R2_CLIENT:
        return None

    mem_key = f"r2:{kind}:{src_key}"
    cached = THUMB_CACHE.get(mem_key)
    if cached:
        return cached

    deriv_key = _deriv_key(kind, src_key)

    # Try persisted derivative on R2
    try:
        resp = R2_CLIENT.get_object(Bucket=R2_BUCKET, Key=deriv_key)
        data = resp['Body'].read()
        THUMB_CACHE.set(mem_key, data)
        return data
    except ClientError as e:
        code = e.response.get('Error', {}).get('Code', '')
        if code not in ('NoSuchKey', '404'):
            print(f"R2 derivative fetch error ({deriv_key}): {e}")

    # Generate from original
    if not HAS_PIL:
        return None

    try:
        import PIL.Image

        resp = R2_CLIENT.get_object(Bucket=R2_BUCKET, Key=src_key)
        img_data = resp['Body'].read()

        img = PIL.Image.open(io.BytesIO(img_data))

        # Honor EXIF orientation so generated thumbs aren't sideways
        try:
            from PIL import ImageOps
            img = ImageOps.exif_transpose(img)
        except Exception:
            pass

        if kind == 'preview':
            size = CONFIG['preview_size']
            quality = CONFIG['preview_quality']
            progressive = True
        else:
            size = CONFIG['thumbnail_size']
            quality = CONFIG['thumbnail_quality']
            progressive = False

        img.thumbnail(size, PIL.Image.Resampling.LANCZOS)

        if img.mode in ('RGBA', 'P', 'LA'):
            background = PIL.Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
            img = background
        elif img.mode != 'RGB':
            img = img.convert('RGB')

        buf = io.BytesIO()
        img.save(buf, 'JPEG', quality=quality, optimize=True, progressive=progressive)
        out = buf.getvalue()

        THUMB_CACHE.set(mem_key, out)

        # Persist to R2 (best-effort, don't block response on failure)
        try:
            R2_CLIENT.put_object(
                Bucket=R2_BUCKET,
                Key=deriv_key,
                Body=out,
                ContentType='image/jpeg',
                CacheControl=f"public, max-age={CONFIG['cache_duration']}",
            )
        except Exception as e:
            print(f"R2 derivative persist failed ({deriv_key}): {e}")

        return out
    except Exception as e:
        print(f"R2 derivative generation failed ({src_key}, {kind}): {e}")
        return None


# ─── BACKGROUND PRE-WARM ──────────────────────────────────────────────────────
_PREWARM_LOCK = threading.Lock()
_PREWARMED = set()  # src keys we've already kicked a job for this process

def prewarm_r2_thumbs(photos, kind='thumb', concurrency=8):
    """Spawn a daemon thread that generates+persists thumbs for given photos.

    Idempotent: each src key is only ever pre-warmed once per process.
    Skips photos whose derivative already exists on R2.
    """
    if not R2_CLIENT or not photos:
        return

    keys = []
    with _PREWARM_LOCK:
        for p in photos:
            k = p['path'] if isinstance(p, dict) else p
            mark = f"{kind}:{k}"
            if mark in _PREWARMED:
                continue
            _PREWARMED.add(mark)
            keys.append(k)

    if not keys:
        return

    def _run():
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            for k in keys:
                pool.submit(_prewarm_one, k, kind)

    t = threading.Thread(target=_run, daemon=True, name=f"prewarm-{kind}")
    t.start()


def _prewarm_one(src_key, kind):
    """Generate one derivative if not already on R2."""
    try:
        # Cheap existence check first — saves a full download if already cached.
        deriv_key = _deriv_key(kind, src_key)
        try:
            R2_CLIENT.head_object(Bucket=R2_BUCKET, Key=deriv_key)
            return  # already exists
        except ClientError:
            pass
        get_or_make_r2_derivative(src_key, kind)
    except Exception as e:
        print(f"prewarm failed for {src_key}: {e}")


# ─── R2-ENHANCED HANDLER ──────────────────────────────────────────────────────
class R2GalleryHandler(WeddingGalleryProHandler):
    """Extended handler with R2 storage support."""

    def scan_r2_photos(self):
        """Scan photos from R2 bucket."""
        if not R2_CLIENT:
            return [], []

        try:
            photos = []
            videos = []

            paginator = R2_CLIENT.get_paginator('list_objects_v2')
            for page in paginator.paginate(Bucket=R2_BUCKET):
                for obj in page.get('Contents', []):
                    key = obj['Key']
                    # Skip our own generated thumbs/previews
                    if key.startswith(DERIV_PREFIX + '/'):
                        continue
                    ext = Path(key).suffix.lower()

                    entry = {
                        'name': key,
                        'path': key,
                        'size': obj['Size'],
                        'mtime': obj['LastModified'].timestamp(),
                        'ext': ext,
                        'source': 'r2'
                    }

                    if ext in SUPPORTED_IMAGES:
                        photos.append(entry)
                    elif ext in SUPPORTED_VIDEOS:
                        videos.append(entry)

            return photos, videos
        except Exception as e:
            print(f"Error scanning R2: {e}")
            return [], []

    def api_scan(self):
        """Scan both local and R2 photos."""
        from server_pro import scan_media_files, GALLERY_DIR

        start_time = time.time()

        # Scan local files
        local_photos, local_videos = scan_media_files(GALLERY_DIR)

        # Scan R2 files
        r2_photos, r2_videos = self.scan_r2_photos()

        # Combine
        all_photos = local_photos + r2_photos
        all_videos = local_videos + r2_videos

        with CACHE_LOCK:
            CACHE['photos'] = all_photos
            CACHE['videos'] = all_videos
            CACHE['scan_time'] = time.time()

        elapsed = time.time() - start_time

        # Kick off background pre-warm for the first page of R2 thumbs.
        # Persisted to R2, so subsequent dyno restarts skip generation entirely.
        if r2_photos:
            prewarm_r2_thumbs(r2_photos[:120])

        self.send_json({
            'photos': len(all_photos),
            'videos': len(all_videos),
            'local_photos': len(local_photos),
            'r2_photos': len(r2_photos),
            'total': len(all_photos) + len(all_videos),
            'scan_duration_ms': round(elapsed * 1000, 2)
        })

    def serve_thumbnail(self, rel_path):
        """Serve thumbnail from R2 or local."""
        # Check if photo is in R2
        with CACHE_LOCK:
            photos = CACHE.get('photos', [])
            photo = next((p for p in photos if p['path'] == rel_path), None)

        if photo and photo.get('source') == 'r2':
            self.serve_r2_thumbnail(rel_path)
        else:
            # Use parent's local thumbnail method
            super().serve_thumbnail(rel_path)

    def serve_r2_thumbnail(self, key):
        """Generate and serve thumbnail from R2 photo."""
        bytes_ = get_or_make_r2_derivative(key, 'thumb')
        if bytes_ is None:
            self.serve_r2_media(key)
            return
        self._send_image_bytes(bytes_, 'image/jpeg')

    def serve_media_file(self, rel_path):
        """Serve media from R2 or local."""
        # Check if photo is in R2
        with CACHE_LOCK:
            photos = CACHE.get('photos', [])
            videos = CACHE.get('videos', [])
            item = next((p for p in photos + videos if p['path'] == rel_path), None)

        if item and item.get('source') == 'r2':
            self.serve_r2_media(rel_path)
        else:
            # Use parent's local media method
            super().serve_media_file(rel_path)

    def serve_preview(self, rel_path):
        """Serve a medium-size, high-quality preview for the lightbox."""
        with CACHE_LOCK:
            photos = CACHE.get('photos', [])
            photo = next((p for p in photos if p['path'] == rel_path), None)

        if photo and photo.get('source') == 'r2':
            self.serve_r2_preview(rel_path)
        else:
            super().serve_preview(rel_path)

    def serve_r2_preview(self, key):
        """Generate and serve ~1600px JPEG preview from R2 original."""
        bytes_ = get_or_make_r2_derivative(key, 'preview')
        if bytes_ is None:
            self.serve_r2_media(key)
            return
        self._send_image_bytes(bytes_, 'image/jpeg')

    def serve_r2_media(self, key):
        """Serve full media file from R2."""
        if not R2_CLIENT:
            self.send_404()
            return

        try:
            response = R2_CLIENT.get_object(Bucket=R2_BUCKET, Key=key)
            data = response['Body'].read()

            # Determine content type
            ext = Path(key).suffix.lower()
            if ext in ['.jpg', '.jpeg']:
                content_type = 'image/jpeg'
            elif ext == '.png':
                content_type = 'image/png'
            elif ext in ['.mp4', '.mov', '.m4v']:
                content_type = 'video/mp4'
            else:
                content_type = 'application/octet-stream'

            self._send_image_bytes(data, content_type)
        except Exception as e:
            print(f"Error serving R2 media {key}: {e}")
            self.send_404()

    def api_upload(self):
        """Handle file upload - saves to R2 if configured, else local."""
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

            # Upload to R2 if configured, else save locally
            if R2_CLIENT:
                try:
                    # Generate unique key
                    key = f"uploads/{int(time.time())}_{fname}"

                    # Upload to R2
                    R2_CLIENT.put_object(
                        Bucket=R2_BUCKET,
                        Key=key,
                        Body=content,
                        ContentType='image/jpeg' if ext in ['.jpg', '.jpeg'] else 'image/png'
                    )
                    saved.append(key)
                    print(f"✅ Uploaded to R2: {key}")
                except Exception as e:
                    print(f"❌ R2 upload failed for {fname}: {e}")
            else:
                # Save locally (fallback)
                from server_pro import GALLERY_DIR
                upload_dir = os.path.join(GALLERY_DIR, 'uploads')
                os.makedirs(upload_dir, exist_ok=True)
                dest = os.path.join(upload_dir, f"{int(time.time())}_{fname}")

                with open(dest, 'wb') as f:
                    f.write(content)
                saved.append(os.path.basename(dest))

        # Rescan
        self.api_scan()

        self.send_json({'saved': saved, 'count': len(saved)})


# ─── SERVER ───────────────────────────────────────────────────────────────────
def run_server(directory, port=8000, auto_open=True):
    """Run server with R2 support."""
    from server_pro import GALLERY_DIR
    import server_pro

    server_pro.GALLERY_DIR = os.path.realpath(directory)

    # Initialize R2
    r2_enabled = init_r2()

    print(f"""
╔════════════════════════════════════════════════════════════════╗
║                                                                ║
║       🎊 Wedding Gallery Pro+ with Cloudflare R2 🎊          ║
║                                                                ║
╠════════════════════════════════════════════════════════════════╣
║                                                                ║
║  📁 Local:   {os.path.basename(server_pro.GALLERY_DIR):<48} ║
║  ☁️  R2:      {'✓ Connected to ' + R2_BUCKET if r2_enabled else '✗ Not configured':48} ║
║  🌐 URL:     http://localhost:{port:<37} ║
║  🖼️  PIL:     {'✓ Thumbnails enabled' if HAS_PIL else '✗ Install Pillow':48} ║
║  📦 boto3:   {'✓ R2 support enabled' if HAS_BOTO3 else '✗ Install boto3':48} ║
║                                                                ║
╠════════════════════════════════════════════════════════════════╣
║                                                                ║
║  ⚡ Features:                                                  ║
║     • Photos served from Cloudflare R2                        ║
║     • Direct upload to R2 storage                             ║
║     • Optimized thumbnails with caching                       ║
║     • HTTP Basic Authentication                               ║
║     • Mobile-responsive UI                                    ║
║                                                                ║
╠════════════════════════════════════════════════════════════════╣
║                                                                ║
║  🚀 Ready! Open: http://localhost:{port}/{' ' * 26} ║
║  ⏸️  Stop: Press Ctrl+C{' ' * 39} ║
║                                                                ║
╚════════════════════════════════════════════════════════════════╝
""")

    # Auto-open browser (only in development)
    is_production = os.environ.get('RAILWAY_ENVIRONMENT') is not None
    if auto_open and CONFIG['auto_open_browser'] and not is_production:
        import webbrowser
        import threading

        def open_browser():
            time.sleep(1.5)
            try:
                webbrowser.open(f'http://localhost:{port}/')
                print(f"🌐 Opened gallery in browser!")
            except:
                pass

        thread = threading.Thread(target=open_browser, daemon=True)
        thread.start()

    handler = R2GalleryHandler
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
        description='Wedding Gallery Pro+ with Cloudflare R2',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('directory', nargs='?', default='.',
                       help='Gallery directory (default: current dir)')
    default_port = int(os.environ.get('PORT', 8000))
    parser.add_argument('--port', type=int, default=default_port,
                       help='Port (default: from PORT env or 8000)')
    parser.add_argument('--no-auto-open', action='store_true',
                       help='Don\'t automatically open browser')

    args = parser.parse_args()

    CONFIG['auto_open_browser'] = not args.no_auto_open

    run_server(args.directory, args.port, not args.no_auto_open)
