# 🚀 Quick Deploy: R2 + Railway (15 minutes total)

## Why This Approach?
✅ Much faster than uploading 1.3GB to GitHub
✅ Photos stored separately in Cloudflare R2 (free, fast CDN)
✅ Code in GitHub (small, fast deploys)
✅ Total cost: $5/month Railway (R2 is free)

---

## Step 1: Cloudflare R2 Setup (5 minutes)

### 1.1 Create Account & Bucket
1. Go to: https://dash.cloudflare.com/sign-up
2. Sign up (no credit card needed for R2 free tier)
3. Go to **R2** in left sidebar
4. Click **"Purchase R2"** (it's free, just enables it)
5. Click **"Create bucket"**
   - Name: `wedding-gallery-photos`
   - Location: Automatic
   - Click **Create**

### 1.2 Get API Credentials
1. Go to **R2** → **Manage R2 API Tokens**
2. Click **"Create API token"**
   - Name: `wedding-gallery`
   - Permissions: **Object Read & Write**
   - TTL: Forever
3. **SAVE THESE** (shown only once):
   ```
   Access Key ID: __________________
   Secret Access Key: __________________
   Endpoint URL: https://______.r2.cloudflarestorage.com
   ```

---

## Step 2: Upload Photos to R2 (10 minutes)

Run these commands in your terminal:

```bash
# Install boto3 (if not already installed)
pip3 install boto3

# Set your R2 credentials (paste your actual values)
export R2_ACCESS_KEY='your-access-key-here'
export R2_SECRET_KEY='your-secret-key-here'
export R2_ENDPOINT='https://xxxxx.r2.cloudflarestorage.com'
export R2_BUCKET='wedding-gallery-photos'

# Upload all 462 photos (takes ~5-10 minutes)
python3 upload_to_r2.py
```

You'll see progress like:
```
🚀 Starting photo upload to R2...
[1/462] Uploading IMG_6797.PNG...
[2/462] Uploading IMG_6798.jpg...
...
✅ Upload complete! 462 photos uploaded
```

---

## Step 3: Push Code to GitHub (30 seconds)

```bash
# Commit only the code (no photos)
git add .
git commit -m "Add R2-powered wedding gallery"
git push origin main
```

This is fast because we're not uploading 1.3GB of photos!

---

## Step 4: Deploy to Railway (5 minutes)

### 4.1 Sign Up
1. Go to: https://railway.app
2. Click **"Login with GitHub"**
3. Authorize Railway

### 4.2 Deploy
1. Click **"New Project"**
2. Click **"Deploy from GitHub repo"**
3. Select: **"wedding-photo-gallery"**
4. Railway auto-detects settings

### 4.3 Add Environment Variables
Click **Variables** tab and add:

```
R2_ACCESS_KEY=your-access-key
R2_SECRET_KEY=your-secret-key
R2_ENDPOINT=https://xxxxx.r2.cloudflarestorage.com
R2_BUCKET=wedding-gallery-photos
AUTH_USER=wedding2024
AUTH_PASS=securepassword123
```

### 4.4 Generate Domain
1. Go to **Settings** → **Networking**
2. Click **"Generate Domain"**
3. You get: `https://wedding-gallery-production.up.railway.app`

---

## Step 5: Test & Share! 🎉

1. Visit your Railway URL
2. Login with:
   - Username: `wedding2024`
   - Password: `securepassword123`
3. View your 462 photos!

**Share with guests:**
```
🎊 Wedding Photo Gallery
URL: https://your-app.up.railway.app
Username: wedding2024
Password: securepassword123
```

---

## 💰 Costs

- **Cloudflare R2:** FREE (10GB free tier, you use 1.3GB)
- **Railway:** $5/month (hobby plan)
- **Total:** $5/month

---

## ⚡ Performance

- Photos load from R2 CDN (super fast worldwide)
- Automatic thumbnails generated
- Lazy loading
- Mobile optimized

---

## 🔄 Add More Photos Later

1. Add photos to `all_photos_web/` folder
2. Run: `python3 upload_to_r2.py` (uploads only new photos)
3. Photos appear instantly!

---

**Ready? Let's start with Step 1: Get your R2 credentials!**
