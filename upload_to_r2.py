#!/usr/bin/env python3
"""
Upload wedding photos to Cloudflare R2
Requires: pip install boto3
"""

import os
import sys
from pathlib import Path
try:
    import boto3
    from botocore.client import Config
except ImportError:
    print("❌ Error: boto3 not installed")
    print("Run: pip install boto3")
    sys.exit(1)

# ─── CONFIGURATION ────────────────────────────────────────────────────────────
# Set these from your Cloudflare R2 credentials
R2_ACCESS_KEY = os.environ.get('R2_ACCESS_KEY', '')
R2_SECRET_KEY = os.environ.get('R2_SECRET_KEY', '')
R2_ENDPOINT = os.environ.get('R2_ENDPOINT', '')
R2_BUCKET = os.environ.get('R2_BUCKET', 'wedding-gallery-photos')

PHOTOS_DIR = 'all_photos_web'

def upload_photos():
    """Upload all photos to R2 bucket."""

    # Validate credentials
    if not all([R2_ACCESS_KEY, R2_SECRET_KEY, R2_ENDPOINT]):
        print("❌ Missing R2 credentials!")
        print("\nSet environment variables:")
        print("  export R2_ACCESS_KEY='your-access-key'")
        print("  export R2_SECRET_KEY='your-secret-key'")
        print("  export R2_ENDPOINT='https://xxxxx.r2.cloudflarestorage.com'")
        print("  export R2_BUCKET='wedding-gallery-photos'")
        sys.exit(1)

    # Initialize R2 client (S3-compatible)
    s3 = boto3.client(
        's3',
        endpoint_url=R2_ENDPOINT,
        aws_access_key_id=R2_ACCESS_KEY,
        aws_secret_access_key=R2_SECRET_KEY,
        config=Config(signature_version='s3v4'),
        region_name='auto'
    )

    print(f"\n🚀 Starting photo upload to R2 bucket: {R2_BUCKET}")
    print(f"📁 Source directory: {PHOTOS_DIR}\n")

    # Get all photo files
    photos = []
    for ext in ['*.jpg', '*.jpeg', '*.png', '*.JPG', '*.JPEG', '*.PNG']:
        photos.extend(Path(PHOTOS_DIR).glob(ext))

    total = len(photos)
    if total == 0:
        print(f"❌ No photos found in {PHOTOS_DIR}/")
        sys.exit(1)

    print(f"📸 Found {total} photos to upload\n")

    # Upload with progress
    uploaded = 0
    skipped = 0
    errors = 0

    for i, photo_path in enumerate(photos, 1):
        key = photo_path.name

        try:
            # Check if already exists
            try:
                s3.head_object(Bucket=R2_BUCKET, Key=key)
                print(f"⏭️  [{i}/{total}] Skipped (exists): {key}")
                skipped += 1
                continue
            except:
                pass

            # Upload
            with open(photo_path, 'rb') as f:
                s3.put_object(
                    Bucket=R2_BUCKET,
                    Key=key,
                    Body=f,
                    ContentType='image/jpeg' if key.lower().endswith(('.jpg', '.jpeg')) else 'image/png'
                )

            uploaded += 1
            size_mb = photo_path.stat().st_size / 1024 / 1024
            print(f"✅ [{i}/{total}] Uploaded: {key} ({size_mb:.2f} MB)")

        except Exception as e:
            errors += 1
            print(f"❌ [{i}/{total}] Failed: {key} - {e}")

    # Summary
    print(f"\n{'='*60}")
    print(f"📊 Upload Summary:")
    print(f"   Total files:  {total}")
    print(f"   ✅ Uploaded:  {uploaded}")
    print(f"   ⏭️  Skipped:   {skipped}")
    print(f"   ❌ Errors:    {errors}")
    print(f"{'='*60}\n")

    if errors == 0:
        print("🎉 All photos uploaded successfully!")
        print(f"\n📍 Photos are now available at:")
        print(f"   Bucket: {R2_BUCKET}")
        print(f"   Endpoint: {R2_ENDPOINT}")
    else:
        print(f"⚠️  Completed with {errors} errors")

    # Test access
    print("\n🔍 Testing bucket access...")
    try:
        response = s3.list_objects_v2(Bucket=R2_BUCKET, MaxKeys=5)
        count = response.get('KeyCount', 0)
        print(f"✅ Bucket accessible - {count} files listed")
    except Exception as e:
        print(f"❌ Bucket access test failed: {e}")


if __name__ == '__main__':
    print("""
╔════════════════════════════════════════════════════════════════╗
║                                                                ║
║          📤 Wedding Gallery - R2 Photo Uploader 📤            ║
║                                                                ║
╚════════════════════════════════════════════════════════════════╝
    """)

    try:
        upload_photos()
    except KeyboardInterrupt:
        print("\n\n⏸️  Upload cancelled by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        sys.exit(1)
