#!/bin/bash
# Start an optimized local web server to view the gallery

# Change to the organized_view directory
cd "$(dirname "$0")"

# Open in default browser after a delay
(sleep 2 && open http://localhost:8000/gallery.html) &

# Start the optimized Python server
python3 server.py 8000
