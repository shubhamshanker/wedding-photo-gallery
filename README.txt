Wedding Photo Gallery - Quick Start Guide
==========================================

Your 952 wedding media files have been organized for easy viewing!

WHAT WAS CREATED:
-----------------
✓ all_photos/  - 467 photos (HEIC, PNG, JPG) linked here
✓ all_videos/  - 478 videos (MOV) linked here
✓ gallery.html - Interactive web gallery viewer
✓ This used SYMLINKS - no duplicate files, only 19GB total


FIRST TIME SETUP (IMPORTANT):
-----------------------------
Web browsers cannot display HEIC files (iPhone photo format).
You need to convert them to JPEG first:

   1. Open Terminal in this folder
   2. Run: ./convert_heic.sh
   3. Wait 2-3 minutes for conversion to complete
   4. Then proceed to view the gallery

This only needs to be done ONCE. The script converts 440+ HEIC files to JPEG.
Converted images are saved to "all_photos_web/" folder (1.3 GB).


HOW TO VIEW:
-----------

OPTION 1: Web Gallery (Recommended) - NOW OPTIMIZED!
   • Double-click: start_gallery.sh
   • This opens an interactive gallery in your browser
   • NEW Features:
     - Lazy loading: Images load only when you scroll to them
     - Pagination: Choose 20, 50, 100 photos per page or view all
     - Faster initial load and smoother scrolling
     - No more browser lag with hundreds of photos
     - Grid view of all photos
     - Click any photo for full-screen viewer
     - Arrow keys to navigate (← → in full-screen, Esc to close)
     - Separate tab for videos with playback controls
     - Optimized server (no more broken pipe errors)

OPTION 2: macOS Quick Look
   • Open the "all_photos" folder
   • Select all files (Cmd+A)
   • Press Space bar
   • Use arrow keys to browse through all photos

OPTION 3: Finder
   • Open "all_photos" or "all_videos" folder
   • Switch to Icon View (Cmd+1)
   • Adjust icon size with Cmd+J
   • Scroll through all media


IMPORTANT NOTES:
---------------
• Original files are UNCHANGED in their IMG_XXXX folders
• The organized_view uses symlinks (shortcuts) to the originals
• Deleting organized_view won't delete your original photos
• You can safely browse and share from the organized folders


FILE COUNTS:
-----------
Photos: 467 files
  - 445 HEIC (iPhone photos)
  - 20 PNG (screenshots)
  - 2 JPG

Videos: 478 MOV files

Total: 945 media files organized from 516 folders


ENJOY YOUR WEDDING MEMORIES!
