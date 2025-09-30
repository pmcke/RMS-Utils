import sys
import re
from PIL import Image, ImageDraw, ImageFont, ImageStat

def add_top_text(image_path, text, y_fraction=0.10):
    # Open image
    img = Image.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(img)

    # Choose font size relative to image width
    font_size = img.width // 15
    try:
        font = ImageFont.truetype("arial.ttf", font_size)  # Windows/macOS
    except:
        font = ImageFont.load_default()  # fallback

    # --- Determine brightness of top part of image ---
    top_crop_height = img.height // 5  # top 20% of image
    top_crop = img.crop((0, 0, img.width, top_crop_height))
    stat = ImageStat.Stat(top_crop)
    r, g, b = stat.mean
    brightness = (r + g + b) / 3  # average brightness 0–255

    # Pick text color based on brightness
    text_color = "white" if brightness < 128 else "black"
    outline_color = "black" if text_color == "white" else "white"

    # Get text size
    text_width, text_height = draw.textsize(text, font=font)

    # Position text at chosen fraction of height
    x = (img.width - text_width) // 2
    y = int(img.height * y_fraction)

    # Draw outline for visibility
    outline_range = 2
    for dx in range(-outline_range, outline_range+1):
        for dy in range(-outline_range, outline_range+1):
            if dx != 0 or dy != 0:
                draw.text((x+dx, y+dy), text, font=font, fill=outline_color)

    # Draw main text
    draw.text((x, y), text, font=font, fill=text_color)

    # --- Make output filename ---
    safe_text = re.sub(r'[^a-zA-Z0-9_-]', '_', text.strip())  # clean for filename
    base_name = image_path.rsplit('.', 1)[0]
    ext = image_path.rsplit('.', 1)[-1]
    output_path = f"{base_name}_{safe_text}.{ext}"

    # Save output
    img.save(output_path)
    print(f"Saved with text: {output_path}")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python add_text.py <image_path> \"Your Text Here\" [y_fraction]")
    else:
        image_path = sys.argv[1]
        text = sys.argv[2]
        y_fraction = float(sys.argv[3]) if len(sys.argv) > 3 else 0.10
        add_top_text(image_path, text, y_fraction)
