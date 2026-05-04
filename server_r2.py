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
        if not R2_CLIENT:
            self.send_404()
            return

        # Check cache
        cache_key = f"r2:thumb:{key}"
        cached = THUMB_CACHE.get(cache_key)

        if cached:
            self._send_image_bytes(cached, 'image/jpeg')
            return

        # Download from R2 and generate thumbnail
        if HAS_PIL:
            try:
                import PIL.Image

                # Download image from R2
                response = R2_CLIENT.get_object(Bucket=R2_BUCKET, Key=key)
                img_data = response['Body'].read()

                # Generate thumbnail
                img = PIL.Image.open(io.BytesIO(img_data))
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
                print(f"R2 thumbnail generation failed for {key}: {e}")

        # Fallback: serve full image
        self.serve_r2_media(key)

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
        if not R2_CLIENT:
            self.send_404()
            return

        cache_key = f"r2:preview:{key}"
        cached = THUMB_CACHE.get(cache_key)
        if cached:
            self._send_image_bytes(cached, 'image/jpeg')
            return

        if HAS_PIL:
            try:
                import PIL.Image

                response = R2_CLIENT.get_object(Bucket=R2_BUCKET, Key=key)
                img_data = response['Body'].read()

                img = PIL.Image.open(io.BytesIO(img_data))
                img.thumbnail(CONFIG['preview_size'], PIL.Image.Resampling.LANCZOS)

                if img.mode in ('RGBA', 'P', 'LA'):
                    background = PIL.Image.new('RGB', img.size, (255, 255, 255))
                    if img.mode == 'P':
                        img = img.convert('RGBA')
                    background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
                    img = background
                elif img.mode != 'RGB':
                    img = img.convert('RGB')

                buf = io.BytesIO()
                img.save(buf, 'JPEG', quality=CONFIG['preview_quality'], optimize=True, progressive=True)
                preview_bytes = buf.getvalue()

                THUMB_CACHE.set(cache_key, preview_bytes)

                self._send_image_bytes(preview_bytes, 'image/jpeg')
                return
            except Exception as e:
                print(f"R2 preview generation failed for {key}: {e}")

        # Fallback: serve original
        self.serve_r2_media(key)

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
