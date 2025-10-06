import os
import re
import random
import logging
import aiofiles
import aiohttp
import traceback
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont
from youtubesearchpython.__future__ import VideosSearch

logging.basicConfig(level=logging.INFO)

# -----------------------------
# Helper functions
# -----------------------------
def changeImageSize(maxWidth, maxHeight, image):
    widthRatio = maxWidth / image.size[0]
    heightRatio = maxHeight / image.size[1]
    newWidth = int(widthRatio * image.size[0])
    newHeight = int(heightRatio * image.size[1])
    return image.resize((newWidth, newHeight))


def truncate(text):
    words = text.split(" ")
    text1, text2 = "", ""
    for i in words:
        if len(text1) + len(i) < 30:
            text1 += " " + i
        elif len(text2) + len(i) < 30:
            text2 += " " + i
    return [text1.strip(), text2.strip()]


def random_color():
    return tuple(random.randint(0, 255) for _ in range(3))


def generate_gradient(width, height, start_color, end_color):
    base = Image.new('RGBA', (width, height), start_color)
    top = Image.new('RGBA', (width, height), end_color)
    mask = Image.new('L', (width, height))
    mask_data = [int(255 * (y / height)) for y in range(height) for _ in range(width)]
    mask.putdata(mask_data)
    base.paste(top, (0, 0), mask)
    return base


def crop_center_circle(img, output_size, border, border_color, crop_scale=1.5):
    half_w, half_h = img.size[0] / 2, img.size[1] / 2
    larger_size = int(output_size * crop_scale)
    img = img.crop((
        half_w - larger_size / 2,
        half_h - larger_size / 2,
        half_w + larger_size / 2,
        half_h + larger_size / 2
    ))
    img = img.resize((output_size - 2 * border, output_size - 2 * border))
    final_img = Image.new("RGBA", (output_size, output_size), border_color)
    mask_main = Image.new("L", (output_size - 2 * border, output_size - 2 * border), 0)
    draw_main = ImageDraw.Draw(mask_main)
    draw_main.ellipse((0, 0, output_size - 2 * border, output_size - 2 * border), fill=255)
    final_img.paste(img, (border, border), mask_main)
    return final_img


def draw_text_with_shadow(background, draw, position, text, font, fill, shadow_offset=(3, 3), shadow_blur=5):
    shadow = Image.new('RGBA', background.size, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    shadow_draw.text(position, text, font=font, fill="black")
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=shadow_blur))
    background.paste(shadow, shadow_offset, shadow)
    draw.text(position, text, font=font, fill=fill)


# -----------------------------
# Main function
# -----------------------------
async def gen_thumb(videoid: str):
    try:
        os.makedirs("cache", exist_ok=True)
        cached_path = f"cache/{videoid}_v4.png"
        if os.path.isfile(cached_path):
            return cached_path

        url = f"https://www.youtube.com/watch?v={videoid}"
        results = VideosSearch(url, limit=1)
        data = await results.next()
        if not data["result"]:
            raise ValueError("No video results found")

        result = data["result"][0]
        title = re.sub(r"\W+", " ", result.get("title", "Unknown Title")).title()
        duration = result.get("duration", "Live")
        thumbnail = result.get("thumbnails", [{}])[0].get("url", "").split("?")[0]
        views = result.get("viewCount", {}).get("short", "Unknown Views")
        channel = result.get("channel", {}).get("name", "Unknown Channel")

        if not thumbnail:
            raise ValueError("Thumbnail not found")

        filepath = f"cache/thumb_{videoid}.png"
        async with aiohttp.ClientSession() as session:
            async with session.get(thumbnail) as resp:
                if resp.status != 200:
                    raise Exception(f"Failed to download thumbnail: {resp.status}")
                async with aiofiles.open(filepath, mode="wb") as f:
                    await f.write(await resp.read())

        # Open thumbnail
        youtube = Image.open(filepath).convert("RGBA")
        image1 = changeImageSize(1280, 720, youtube)

        # Blur and gradient background
        background = image1.filter(ImageFilter.BoxBlur(20))
        background = ImageEnhance.Brightness(background).enhance(0.6)
        start_color, end_color = random_color(), random_color()
        gradient = generate_gradient(1280, 720, start_color, end_color)
        background = Image.blend(background, gradient, alpha=0.25)

        draw = ImageDraw.Draw(background)

        # Fonts (make sure these paths exist)
        arial = ImageFont.truetype("tg/assets/font2.ttf", 30)
        title_font = ImageFont.truetype("tg/assets/font3.ttf", 45)

        # Circle Thumbnail
        circle_thumbnail = crop_center_circle(youtube, 400, 20, start_color)
        background.paste(circle_thumbnail, (120, 160), circle_thumbnail)

        # Text
        text_x = 565
        title_lines = truncate(title)
        draw_text_with_shadow(background, draw, (text_x, 180), title_lines[0], title_font, (255, 255, 255))
        draw_text_with_shadow(background, draw, (text_x, 230), title_lines[1], title_font, (255, 255, 255))
        draw_text_with_shadow(background, draw, (text_x, 320), f"{channel}  |  {views}", arial, (255, 255, 255))

        # Progress Line
        line_length = 580
        line_color = random_color()

        if duration != "Live":
            color_len = int(line_length * random.uniform(0.15, 0.85))
            draw.line([(text_x, 380), (text_x + color_len, 380)], fill=line_color, width=9)
            draw.line([(text_x + color_len, 380), (text_x + line_length, 380)], fill="white", width=8)
        else:
            draw.line([(text_x, 380), (text_x + line_length, 380)], fill=(255, 0, 0), width=9)

        draw_text_with_shadow(background, draw, (text_x, 400), "00:00", arial, (255, 255, 255))
        draw_text_with_shadow(background, draw, (1080, 400), duration, arial, (255, 255, 255))

        # Play Icons
        play_icons = Image.open("tg/assets/play_icons.png").resize((580, 62))
        background.paste(play_icons, (text_x, 450), play_icons)

        os.remove(filepath)
        background.save(cached_path)
        return cached_path

    except Exception as e:
        logging.error(f"Error generating thumbnail for {videoid}: {e}")
        traceback.print_exc()
        return None
