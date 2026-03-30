# 🚀 Netlify Deployment Guide

## Step-by-Step Instructions

### 1. Create Netlify Account (1 minute)
1. Go to https://app.netlify.com/signup
2. Click "Sign up with GitHub"
3. Authorize Netlify to access your GitHub account

### 2. Deploy Your Site (2 minutes)
1. Once logged in, click **"Add new site"** → **"Import an existing project"**
2. Click **"Deploy with GitHub"**
3. Search for and select: **"wedding-photo-gallery"**
4. Configure build settings:
   - **Build command:** Leave empty (it's a static site)
   - **Publish directory:** `.` (current directory)
5. Click **"Deploy site"**

### 3. Wait for Deployment (2-3 minutes)
- Netlify will automatically build and deploy your site
- You'll see a progress bar
- Once complete, you'll get a random URL like: `https://random-name-123.netlify.app`

### 4. Customize Your URL (Optional)
1. Go to **Site settings** → **Domain management**
2. Click **"Options"** → **"Edit site name"**
3. Change to something memorable like: `shubham-wedding-gallery`
4. Your new URL: `https://shubham-wedding-gallery.netlify.app`

### 5. Test Your Gallery
1. Visit your Netlify URL
2. You should see the login page
3. Enter password: `wedding2024`
4. Browse the 462 wedding photos!

## 🔐 Change Password

To change the default password:
1. Go to your GitHub repo
2. Edit `login.html`
3. Find line ~32: `const CORRECT_PASSWORD_HASH = "wedding2024";`
4. Change to your desired password
5. Commit and push - Netlify will auto-redeploy!

## 🎯 Share With Guests

Share these details:
```
🎊 Wedding Photo Gallery
URL: https://your-site.netlify.app
Password: wedding2024
```

## 📊 What's Included

- ✅ 462 wedding photos (1.3GB)
- ✅ Password protection
- ✅ Mobile responsive
- ✅ Fast loading with lazy loading
- ✅ Lightbox viewer
- ✅ Keyboard navigation

## 🆓 Costs

**FREE!**
- Netlify free tier includes:
  - 100GB bandwidth/month
  - Automatic HTTPS
  - Continuous deployment from GitHub
  - Custom domain support

## 🔄 Auto-Deployment

Every time you push to GitHub, Netlify automatically redeploys!

To add more photos:
1. Add photos to `all_photos_web/` folder
2. Commit and push to GitHub
3. Netlify auto-deploys in 1-2 minutes

## 🛠️ Troubleshooting

**Login page doesn't load:**
- Clear browser cache
- Try incognito/private mode

**Photos not loading:**
- Check browser console for errors
- Verify files uploaded to GitHub

**Deployment failed:**
- Check Netlify build logs
- Ensure all files committed to GitHub

## 📞 Support

If you need help:
1. Check Netlify build logs
2. Verify GitHub repo has all files
3. Test locally first: open `index.html` in browser

---

**Enjoy sharing your wedding memories!** 💍✨
