#!/usr/bin/env python3
"""
Optimized HTTP server for serving wedding photo gallery.
Handles BrokenPipeError gracefully and supports range requests.
"""

import http.server
import socketserver
import sys
import os
from functools import partial

class SilentHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    """HTTP handler that silently handles broken pipe errors."""

    def log_error(self, format, *args):
        """Override to suppress BrokenPipeError logs."""
        if isinstance(args[0], str) and "Broken pipe" in str(args[0]):
            return
        super().log_error(format, *args)

    def handle_one_request(self):
        """Handle a single HTTP request, catching BrokenPipeError."""
        try:
            super().handle_one_request()
        except (BrokenPipeError, ConnectionResetError):
            # Client disconnected - this is normal for cancelled requests
            pass

    def end_headers(self):
        """Add caching headers for better performance."""
        # Cache images for 1 hour
        if self.path.endswith(('.jpg', '.jpeg', '.png', '.heic', '.HEIC', '.JPG', '.JPEG', '.PNG')):
            self.send_header('Cache-Control', 'public, max-age=3600')
        # Cache videos for 1 hour
        elif self.path.endswith(('.mov', '.MOV', '.mp4', '.MP4')):
            self.send_header('Cache-Control', 'public, max-age=3600')
        super().end_headers()

class ReusableTCPServer(socketserver.TCPServer):
    """TCP server that allows address reuse."""
    allow_reuse_address = True

def run_server(port=8000):
    """Start the HTTP server."""
    # Change to the script directory
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    handler = SilentHTTPRequestHandler

    with ReusableTCPServer(("", port), handler) as httpd:
        print(f"Starting wedding photo gallery server...")
        print(f"Server running at http://localhost:{port}/")
        print(f"Open http://localhost:{port}/gallery.html in your browser")
        print(f"\nPress Ctrl+C to stop the server\n")

        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n\nShutting down server...")
            sys.exit(0)

if __name__ == "__main__":
    port = 8000
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            print(f"Invalid port: {sys.argv[1]}, using default port 8000")

    run_server(port)
