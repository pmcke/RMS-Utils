import sys
import os
from PIL import Image, ImageDraw, ImageFont, ImageStat

VALID_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".gif"}

def pick_text_color(img, padding=10):
    """Examine brightness of bottom-left area and choose contrasting text color."""
    w, h = img.size
    sample = img.crop((0, h - 100, 100, h))  # bottom-left sample
    stat = ImageStat.Stat(sample)
    r, g, b = stat.mean
    brightness = (r + g + b) / 3
    return "white" if brightness < 128 else "black"


def add_filename_label(image_path, output_dir):
    filename = os.path.basename(image_path)
    name_only = filename  # keep extension in text, since you asked for filename only

    img = Image.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(img)

    # Small text relative to image size
    font_size = max(20, img.width // 40)
    try:
        font = ImageFont.truetype("arial.ttf", font_size)
    except:
        font = ImageFont.load_default()

    text_color = pick_text_color(img)

    text_width, text_height = draw.textsize(name_only, font=font)

    # Bottom-left placement with padding
    padding = 10
    x = padding
    y = img.height - text_height - padding

    # Optional outline for visibility
    outline_color = "black" if text_color == "white" else "white"
    for dx in (-1, 1):
        for dy in (-1, 1):
            draw.text((x + dx, y + dy), name_only, font=font, fill=outline_color)

    draw.text((x, y), name_only, font=font, fill=text_color)

    # Save output in current directory with new name
    name, ext = os.path.splitext(filename)
    out_path = os.path.join(output_dir, f"{name}_labelled{ext}")

    img.save(out_path)
    print(f"Saved: {out_path}")


def process_folder(root_path):
    output_dir = os.getcwd()

    for base, dirs, files in os.walk(root_path):
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in VALID_EXT:
                full_path = os.path.join(base, f)
                add_filename_label(full_path, output_dir)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python label_images.py <path_to_folder>")
        sys.exit(1)

    target_path = sys.argv[1]
    process_folder(target_path)
