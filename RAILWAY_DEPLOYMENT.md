# Railway Deployment Guide - Wedding Photo Gallery

## Quick Start

Your wedding photo gallery is now ready for Railway deployment!

### What's Been Configured

✅ **Configuration Files Created:**
- `requirements.txt` - Pillow dependency for fast thumbnails
- `Procfile` - Railway start command
- `.railwayignore` - Deployment optimization

✅ **Server Modifications (server_pro.py):**
- Dynamic port support (reads $PORT from Railway)
- HTTP Basic Authentication (secure, browser-native)
- Production optimizations (1GB cache, disabled auto-browser)
- Health check endpoint (unauthenticated `/api/health`)

✅ **Git Configuration:**
- Updated `.gitignore` to allow `all_photos_web/` (1.3GB, 441 photos)
- Ready to commit and push

---

## Step-by-Step Deployment

### Step 1: Commit and Push to GitHub

```bash
# Add configuration files
git add requirements.txt Procfile .railwayignore .gitignore server_pro.py RAILWAY_DEPLOYMENT.md
git commit -m "Add Railway deployment configuration"

# Add optimized photos (this will take a few minutes - 1.3GB)
git add all_photos_web/
git commit -m "Add wedding photos for deployment"

# Push to GitHub
git push origin main
```

### Step 2: Deploy to Railway

1. **Create Railway Account**
   - Visit: https://railway.app
   - Sign up with GitHub (recommended)
   - No credit card required initially

2. **Create New Project**
   - Click "New Project"
   - Select "Deploy from GitHub repo"
   - Authorize Railway to access your GitHub
   - Select this repository: `organized_view`
   - Click "Deploy Now"

3. **Configure Environment Variables**

   In Railway Dashboard → Your Project → Variables, add:

   ```
   AUTH_USER=wedding2024
   AUTH_PASS=<generate-strong-password>
   ```

   **Generate a strong password:**
   ```bash
   openssl rand -base64 20
   ```
   Example: `7xK9mP2vN8qR4wL6tY3hZ5b`

4. **Configure Settings**
   - **Region:** Choose closest to your family (e.g., us-west1)
   - **Health Check Path:** `/api/health`
   - **Health Check Timeout:** 30 seconds

5. **Generate Domain**
   - Settings → Networking → "Generate Domain"
   - Railway provides: `your-app-name.up.railway.app`
   - Optional: Add custom domain

**Deployment time:** 5-10 minutes for first deploy (1.3GB upload)

---

## Step 3: Test Your Deployment

### Health Check
```bash
curl https://your-app-name.up.railway.app/api/health
```

Expected response:
```json
{
  "status": "healthy",
  "timestamp": 1234567890,
  "cache": {"items": 0, "size_mb": 0, "max_size_mb": 1024},
  "pil_available": true
}
```

### Browser Testing

**Desktop:**
- ✓ Auth prompt appears and accepts credentials
- ✓ Gallery loads with all photos
- ✓ Thumbnails generate quickly
- ✓ Lightbox opens with arrow key navigation
- ✓ Search, favorites, and download work
- ✓ Responsive grid view

**Mobile:**
- ✓ Auth works on mobile browsers
- ✓ Touch gestures (swipe, pinch-to-zoom)
- ✓ Download saves to device
- ✓ Responsive layout

---

## Step 4: Share with Family

### Option A: Pre-authenticated URL (easiest)
```
https://wedding2024:PASSWORD@your-app-name.up.railway.app
```
**Pros:** One-click access
**Cons:** Password visible in address bar

### Option B: Separate credentials (more secure)
```
Wedding Photo Gallery 📸

View photos: https://your-app-name.up.railway.app

Username: wedding2024
Password: [your-password]

Works on all devices!
```

---

## Monitoring & Costs

### Railway Dashboard
Monitor:
- **CPU:** Should be <20%
- **Memory:** Will grow to ~1GB (thumbnail cache) - normal
- **Bandwidth:** Track usage (100GB/month included)
- **Health Checks:** Should be green

### Cost Estimate
**Railway Hobby Plan:** $5/month
- 8GB RAM
- 100GB bandwidth/month
- Unlimited deployments
- Auto-HTTPS
- Custom domains

**Expected usage for 20 family members:**
- ~78GB/month (well within limits)

---

## Troubleshooting

### Issue: Pillow build fails
**Fix:** Add `nixpacks.toml`:
```toml
[phases.setup]
aptPkgs = ['libjpeg-dev', 'zlib1g-dev']
```

### Issue: Photos don't load (404)
**Fix:** Verify photos are committed:
```bash
git ls-files all_photos_web/ | wc -l
# Should show 441+ files
```

### Issue: Auth loop (constantly prompts)
**Fix:** Check Railway Variables match exactly:
- Variable names: `AUTH_USER` and `AUTH_PASS` (case-sensitive)
- No extra spaces in values

### Issue: Slow first load
**Fix:** Railway free tier sleeps after 30 minutes of inactivity. Upgrade to Hobby plan ($5/month) for always-on service.

### Issue: 500 Error on deployment
**Check logs in Railway dashboard:**
```bash
# Common issues:
# - Missing server_claude.py dependency
# - File permissions
# - Port binding
```

---

## Security Notes

- ✅ HTTPS enabled automatically by Railway
- ✅ HTTP Basic Auth protects gallery
- ✅ Health check endpoint is public (required for Railway monitoring)
- ✅ All other endpoints require authentication
- ✅ No hardcoded passwords (environment variables only)

---

## Local Testing Before Deploy

Test the production configuration locally:

```bash
# Set environment variables
export AUTH_USER=wedding2024
export AUTH_PASS=testpassword123
export PORT=8000

# Run server
python3 server_pro.py .

# Test in browser
open http://localhost:8000
# Should prompt for username/password
```

---

## What's Deployed

- ✅ **462 optimized photos** (~1.3GB)
- ✅ **Production-ready server** (caching, compression, auth)
- ✅ **Beautiful UI** (grid view, lightbox, favorites, search)
- ✅ **Mobile-responsive** (works on all devices)
- ✅ **Fast thumbnails** (Pillow-powered, 1GB cache)
- ❌ **Videos excluded** (symlinks don't work on Railway)

---

## Next Steps

1. Run the git commands above to commit and push
2. Follow Railway deployment steps
3. Test the deployment
4. Share URL with family
5. Enjoy! 🎉

**Questions or issues?** Check Railway logs in the dashboard or Railway's documentation at https://docs.railway.app
