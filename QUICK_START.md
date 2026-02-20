# 🎉 Wedding Photo Gallery - Quick Start Guide

## 🚀 First Time Setup (2 Steps)

### Step 1: Convert HEIC to JPEG (One-time, ~3 minutes)
```bash
cd organized_view
./convert_heic.sh
```

**Why?** Web browsers can't display HEIC files (iPhone's photo format). This converts 440+ photos to JPEG.

**Progress:** You'll see:
```
Found 440 HEIC files to convert
Progress: 50/440 files converted...
Progress: 100/440 files converted...
...
Conversion Complete!
Successfully converted: 440
```

### Step 2: Start the Gallery
```bash
./start_gallery.sh
```

Your browser will open automatically! 🎊

---

## 📸 Using the Gallery

### Photo Viewing
- **Grid View**: Browse thumbnails in a responsive grid
- **Click any photo**: Opens full-screen viewer
- **Pagination**: Choose 20, 50, or 100 photos per page
  - Default: 50 (best performance)
  - Change using dropdown at top

### Keyboard Shortcuts
- `←` Left Arrow: Previous photo (in full-screen)
- `→` Right Arrow: Next photo (in full-screen)
- `Esc`: Close full-screen viewer
- `Space`: Also works to close viewer

### Navigation Tips
- Photos load as you scroll (lazy loading)
- Page buttons at bottom: Previous / Next
- Photo counter shows: "142 / 467"
- Smooth scrolling auto-enabled

---

## 🎬 Video Viewing

Click the **Videos** tab at the top
- 478 videos organized in grid
- Click play on any video
- Built-in browser controls
- Videos load on demand (no lag)

---

## ⚡ Performance Features

✅ **Lazy Loading** - Images load only when visible
✅ **Pagination** - View 50 photos at a time (configurable)
✅ **Smart Caching** - Previously viewed photos load instantly
✅ **Optimized Server** - No errors, smooth performance
✅ **Responsive Design** - Works on any screen size

---

## 📊 What's Included

- **467 Photos** (converted to JPEG for web viewing)
- **478 Videos** (MOV format, browser-compatible)
- **Total:** 945 media files from your wedding
- **Size:** Original 19GB (compressed to 1.3GB for web)

---

## 🛠️ Troubleshooting

### "Failed to load" errors
**Solution:** Run `./convert_heic.sh` to convert HEIC to JPEG

### Gallery won't open
**Solution:**
1. Make sure you're in the `organized_view` folder
2. Run `./start_gallery.sh` (not double-clicking gallery.html)

### Images loading slowly
**Solution:**
1. Reduce photos per page to 20
2. Wait a moment after scrolling for lazy loading
3. Check your internet isn't downloading in background

### Port already in use
**Solution:**
```bash
# Stop any existing server
pkill -f "server.py"
# Start again
./start_gallery.sh
```

### Browser compatibility
**Best experience:**
- ✅ Chrome / Edge (Chromium)
- ✅ Safari (macOS/iOS)
- ✅ Firefox
- ❌ Internet Explorer (not supported)

---

## 📁 File Structure

```
organized_view/
├── gallery.html          # Main gallery viewer
├── server.py            # Optimized web server
├── start_gallery.sh     # Start script
├── convert_heic.sh      # HEIC to JPEG converter
├── all_photos/          # Original photos (symlinks)
├── all_photos_web/      # Converted JPEG photos ✨
├── all_videos/          # Video files (symlinks)
└── README.txt           # Detailed documentation
```

---

## 💡 Pro Tips

1. **First visit?** Start with 50 photos per page
2. **Searching for specific photo?** Switch to "View All" mode
3. **Want fastest loading?** Use 20 photos per page
4. **Keyboard navigation** is faster than mouse clicks
5. **Preloading works** in full-screen - next/prev images load automatically

---

## ✅ Checklist

- [ ] Converted HEIC to JPEG (`./convert_heic.sh`)
- [ ] Started server (`./start_gallery.sh`)
- [ ] Gallery opened in browser
- [ ] Can see photos loading in grid
- [ ] Full-screen viewer works
- [ ] Videos play correctly

---

## 🎯 Quick Commands

```bash
# Convert photos (first time only)
./convert_heic.sh

# Start gallery
./start_gallery.sh

# Stop server
Press Ctrl+C in terminal

# Restart server
pkill -f "server.py" && ./start_gallery.sh
```

---

**Enjoy your wedding memories!** 💒✨

For technical details, see `IMPROVEMENTS.md`
