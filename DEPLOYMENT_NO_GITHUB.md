# Railway Deployment - Without GitHub Photos

## Strategy: Railway CLI + Volume Storage

Since photos aren't in GitHub, we'll use Railway CLI to deploy and Railway Volumes to store photos.

## Quick Setup

### 1. Install Railway CLI
```bash
npm install -g @railway/cli
# or
brew install railway
```

### 2. Login to Railway
```bash
railway login
```

### 3. Initialize Project
```bash
railway init
# Select "Create new project"
# Name it: wedding-gallery
```

### 4. Add Railway Volume for Photos
```bash
railway volume create wedding-photos 5GB
railway volume attach wedding-photos /app/all_photos_web
```

### 5. Set Environment Variables
```bash
railway variables set AUTH_USER=wedding2024
railway variables set AUTH_PASS=$(openssl rand -base64 20)
```

### 6. Deploy Code
```bash
git push origin main  # Push code only (no photos)
railway up
```

### 7. Upload Photos to Volume
```bash
# SSH into Railway container
railway ssh

# From local machine, use rsync or scp
# (Railway provides SSH access to upload files)
```

## Alternative: Use Cloud Storage

Better approach - use S3/CloudFlare R2 for photos:
- Upload photos to S3 bucket
- Modify server to read from S3
- Much cheaper and more scalable

Would you like me to:
1. Set up Railway CLI deployment with volumes?
2. Modify server to use S3/R2 storage?
3. Use a different platform (Render, Fly.io, etc.)?
