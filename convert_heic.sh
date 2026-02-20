#!/bin/bash
# Convert HEIC images to JPEG for web browser compatibility

echo "=================================="
echo "HEIC to JPEG Converter for Gallery"
echo "=================================="
echo ""

# Change to the organized_view directory
cd "$(dirname "$0")"

# Check if we have conversion tools available
if command -v sips &> /dev/null; then
    echo "✓ Using macOS 'sips' tool for conversion"
    CONVERTER="sips"
elif command -v heif-convert &> /dev/null; then
    echo "✓ Using 'heif-convert' for conversion"
    CONVERTER="heif-convert"
elif command -v magick &> /dev/null; then
    echo "✓ Using ImageMagick for conversion"
    CONVERTER="magick"
else
    echo "❌ No HEIC converter found!"
    echo ""
    echo "Please install one of the following:"
    echo "  1. macOS sips (built-in on macOS)"
    echo "  2. libheif: brew install libheif"
    echo "  3. ImageMagick: brew install imagemagick"
    exit 1
fi

# Create a directory for converted images
mkdir -p all_photos_web

echo ""
echo "Converting HEIC files to JPEG..."
echo "This may take a few minutes for 445 files..."
echo ""

# Counter
total=0
converted=0
failed=0

# Count total HEIC files
total=$(ls all_photos/*.HEIC 2>/dev/null | wc -l | tr -d ' ')

if [ "$total" -eq 0 ]; then
    echo "No HEIC files found in all_photos/"
    exit 0
fi

echo "Found $total HEIC files to convert"
echo ""

# Convert each HEIC file
for heic_file in all_photos/*.HEIC; do
    if [ -f "$heic_file" ]; then
        # Get base name without extension
        basename=$(basename "$heic_file" .HEIC)
        output_file="all_photos_web/${basename}.jpg"

        # Skip if already converted
        if [ -f "$output_file" ]; then
            ((converted++))
            continue
        fi

        # Convert based on available tool
        if [ "$CONVERTER" = "sips" ]; then
            # Follow the symlink to get the real file
            real_file=$(readlink "$heic_file" || echo "$heic_file")
            if sips -s format jpeg "$real_file" --out "$output_file" > /dev/null 2>&1; then
                ((converted++))
            else
                echo "Failed: $basename"
                ((failed++))
            fi
        elif [ "$CONVERTER" = "heif-convert" ]; then
            real_file=$(readlink "$heic_file" || echo "$heic_file")
            if heif-convert "$real_file" "$output_file" > /dev/null 2>&1; then
                ((converted++))
            else
                echo "Failed: $basename"
                ((failed++))
            fi
        elif [ "$CONVERTER" = "magick" ]; then
            real_file=$(readlink "$heic_file" || echo "$heic_file")
            if magick "$real_file" "$output_file" > /dev/null 2>&1; then
                ((converted++))
            else
                echo "Failed: $basename"
                ((failed++))
            fi
        fi

        # Show progress every 50 files
        if [ $((converted % 50)) -eq 0 ]; then
            echo "Progress: $converted/$total files converted..."
        fi
    fi
done

# Also copy PNG and JPG files
echo ""
echo "Copying PNG and JPG files..."
for img in all_photos/*.PNG all_photos/*.png all_photos/*.JPG all_photos/*.jpg all_photos/*.JPEG all_photos/*.jpeg; do
    if [ -f "$img" ]; then
        real_file=$(readlink "$img" || echo "$img")
        cp "$real_file" "all_photos_web/$(basename "$img")" 2>/dev/null
    fi
done

echo ""
echo "=================================="
echo "Conversion Complete!"
echo "=================================="
echo "Total HEIC files: $total"
echo "Successfully converted: $converted"
echo "Failed: $failed"
echo ""
echo "Converted images saved to: all_photos_web/"
echo ""
echo "Next step: Run ./start_gallery.sh to view the gallery"
echo ""
