# 🚀 Quick Start - Wedding Gallery Deployment

## ✅ Code Pushed to GitHub!

**Next:** Cloudflare R2 (photos) → Railway (server) → Share!

---

## Step 1: Cloudflare R2 Setup (5 min)

1. **Sign up:** https://dash.cloudflare.com/sign-up
2. **Enable R2:** Dashboard → R2 → "Purchase R2" (FREE)
3. **Create bucket:** "wedding-gallery-photos"
4. **Get API token:** R2 → Manage API Tokens → Create
   - Save: Access Key ID, Secret Key, Endpoint URL

---

## Step 2: Upload Photos (10 min)

```bash
# Install boto3
pip install boto3

# Set credentials
export R2_ACCESS_KEY='your-key'
export R2_SECRET_KEY='your-secret'
export R2_ENDPOINT='https://xxxxx.r2.cloudflarestorage.com'

# Upload 462 photos
python upload_to_r2.py
```

---

## Step 3: Deploy to Railway (5 min)

1. **Sign up:** https://railway.app (GitHub login)
2. **Deploy:** New Project → Deploy from GitHub → Select repo
3. **Set variables:**
   - `AUTH_USER=wedding2024`
   - `AUTH_PASS=$(openssl rand -base64 20)`
   - `R2_ACCESS_KEY`, `R2_SECRET_KEY`, `R2_ENDPOINT`, `R2_BUCKET`
4. **Generate domain:** Settings → Networking → Generate

---

## Step 4: Share! 🎉

```
Wedding Photos: https://your-app.up.railway.app
Username: wedding2024
Password: [your-password]
```

**Total cost:** $5/month (Railway) + $0 (R2 free tier)

See CLOUDFLARE_R2_SETUP.md for detailed guide.
