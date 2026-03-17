# Cloudflare R2 Setup Guide - Wedding Gallery

## Step 1: Create Cloudflare Account & R2 Bucket

### 1.1 Sign Up
- Go to: https://dash.cloudflare.com/sign-up
- Enter email and create password
- Verify email
- **No credit card required for R2 free tier!**

### 1.2 Enable R2
- Login to Cloudflare dashboard
- Left sidebar → **R2**
- Click **"Purchase R2"** (it's free, just enables it)
- Confirm (no payment needed)

### 1.3 Create Bucket
- Click **"Create bucket"**
- Bucket name: `wedding-gallery-photos` (must be unique)
- Location: **Automatic** (or choose closest region)
- Click **"Create bucket"**

### 1.4 Get API Credentials
- Go to **R2** → **Manage R2 API Tokens**
- Click **"Create API token"**
- Token name: `wedding-gallery-access`
- Permissions: **Object Read & Write**
- TTL: **Forever** (or 1 year)
- Click **"Create API Token"**

**SAVE THESE VALUES** (you'll only see them once):
```
Access Key ID: <copy this>
Secret Access Key: <copy this>
Endpoint URL: https://<account-id>.r2.cloudflarestorage.com
```

### 1.5 Enable Public Access (Optional - for direct photo URLs)
- Go to your bucket → **Settings**
- Under **Public Access** → Click **"Allow Access"**
- Domain: `photos.yourdomain.com` or use default R2.dev subdomain
- This allows photos to be accessed via public URLs

---

## Step 2: Upload Photos to R2

I'll create a Python script to upload your 462 photos automatically.

### 2.1 Install AWS CLI or use Python script
```bash
pip install boto3
```

### 2.2 Run Upload Script
```bash
python upload_to_r2.py
```

This will:
- Connect to your R2 bucket
- Upload all 462 photos from `all_photos_web/`
- Show progress bar
- Takes ~5-10 minutes depending on internet speed

---

## Step 3: Configure Server for R2

Add these environment variables to Railway:

```bash
# Cloudflare R2 Credentials
R2_ACCESS_KEY=<your-access-key-id>
R2_SECRET_KEY=<your-secret-access-key>
R2_ENDPOINT=https://<account-id>.r2.cloudflarestorage.com
R2_BUCKET=wedding-gallery-photos

# Optional: Public URL (if enabled)
R2_PUBLIC_URL=https://pub-xxxxx.r2.dev
```

---

## Step 4: Deploy to Railway

```bash
# Push updated code to GitHub
git add .
git commit -m "Add Cloudflare R2 photo storage support"
git push origin main

# Deploy to Railway (photos will load from R2)
railway up
```

---

## Architecture

**Before (GitHub):**
- ❌ 1.3GB photos in git repo
- ❌ Slow deployments
- ❌ Storage limits

**After (R2):**
- ✅ Code in GitHub (~2MB)
- ✅ Photos in R2 (1.3GB, free tier)
- ✅ Fast deployments
- ✅ Unlimited bandwidth (R2 has no egress fees!)
- ✅ Photo uploads go directly to R2

---

## Costs

**Free Tier (Lifetime):**
- Storage: 10 GB/month (you use 1.3GB)
- Class A operations: 1M/month (uploads, lists)
- Class B operations: 10M/month (downloads)
- **NO egress fees** (unlike AWS S3)

You're well within free limits!

---

## Next Steps

1. Create R2 account and bucket (5 min)
2. Get API credentials
3. Share credentials with me (I'll create upload script)
4. Upload photos to R2
5. Deploy to Railway

Ready? Let me know when you have the R2 credentials!
