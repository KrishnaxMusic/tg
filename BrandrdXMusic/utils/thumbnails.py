import random
import logging
import os
import re
import aiofiles
import aiohttp
import traceback
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont
from youtubesearchpython.__future__ import VideosSearch

logging.basicConfig(level=logging.INFO)

def changeImageSize(maxWidth, maxHeight, image):
    widthRatio = maxWidth / image.size[0]
    heightRatio = maxHeight / image.size[1]
    newWidth = int(widthRatio * image.size[0])
    newHeight = int(heightRatio * image.size[1])
    return image.resize((newWidth, newHeight))

def truncate(text):
    words = text.split(" ")
    text1 = ""
    text2 = ""    
    for word in words:
        if len(text1) + len(word) < 30:
            text1 += " " + word
        elif len(text2) + len(word) < 30:
            text2 += " " + word

    return [text1.strip(), text2.strip()]

def random_color():
    return (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))

def generate_gradient(width, height, start_color, end_color):
    base = Image.new('RGBA', (width, height), start_color)
    top = Image.new('RGBA', (width, height), end_color)
    mask = Image.new('L', (width, height))
    mask_data = []
    for y in range(height):
        mask_data.extend([int(60 * (y / height))] * width)
    mask.putdata(mask_data)
    base.paste(top, (0, 0), mask)
    return base

def crop_center_circle(img, output_size, border, border_color, crop_scale=1.5):
    half_w, half_h = img.size[0] / 2, img.size[1] / 2
    crop_size = int(output_size * crop_scale)
    img = img.crop((
        half_w - crop_size / 2,
        half_h - crop_size / 2,
        half_w + crop_size / 2,
        half_h + crop_size / 2
    ))
    img = img.resize((output_size - 2 * border, output_size - 2 * border))

    final_img = Image.new("RGBA", (output_size, output_size), border_color)

    mask_main = Image.new("L", (output_size - 2 * border, output_size - 2 * border), 0)
    draw_main = ImageDraw.Draw(mask_main)
    draw_main.ellipse((0, 0, output_size - 2 * border, output_size - 2 * border), fill=255)

    final_img.paste(img, (border, border), mask_main)

    mask_border = Image.new("L", (output_size, output_size), 0)
    draw_border = ImageDraw.Draw(mask_border)
    draw_border.ellipse((0, 0, output_size, output_size), fill=255)

    result = Image.composite(final_img, Image.new("RGBA", final_img.size, (0, 0, 0, 0)), mask_border)
    return result

def draw_text_with_shadow(background, draw, position, text, font, fill, shadow_offset=(3, 3), shadow_blur=5):
    shadow = Image.new('RGBA', background.size, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    shadow_draw.text(position, text, font=font, fill="black")
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=shadow_blur))
    background.paste(shadow, shadow_offset, shadow)
    draw.text(position, text, font=font, fill=fill)

async def gen_thumb(videoid: str):
    try:
        cache_path = f"cache/{videoid}_v4.png"
        if os.path.isfile(cache_path):
            return cache_path

        results = VideosSearch(videoid, limit=1)
        search_result = (await results.next())["result"][0]

        title = search_result.get("title", "Unsupported Title")
        title = re.sub(r"\W+", " ", title).title()
        duration = search_result.get("duration", "Live")

        thumbnail_data = search_result.get("thumbnails")
        thumbnail_url = thumbnail_data[0]["url"].split("?")[0] if thumbnail_data else None

        views = search_result.get("viewCount", {}).get("short", "Unknown Views")
        channel = search_result.get("channel", {}).get("name", "Unknown Channel")

        if not thumbnail_url:
            logging.error("No thumbnail URL found.")
            return None

        image_path = f"cache/thumb_{videoid}.png"
        async with aiohttp.ClientSession() as session:
            async with session.get(thumbnail_url) as resp:
                if resp.status == 200:
                    content = await resp.read()
                    content_type = resp.headers.get("Content-Type", "")
                    if "jpeg" in content_type or "jpg" in content_type:
                        ext = "jpg"
                    elif "png" in content_type:
                        ext = "png"
                    else:
                        logging.error(f"Unsupported content type: {content_type}")
                        return None
                    async with aiofiles.open(image_path, mode="wb") as f:
                        await f.write(content)
                else:
                    logging.error(f"Failed to fetch thumbnail: HTTP {resp.status}")
                    return None

        youtube = Image.open(image_path)
        image1 = changeImageSize(1280, 720, youtube)
        image2 = image1.convert("RGBA")
        background = ImageEnhance.Brightness(image2.filter(ImageFilter.BoxBlur(20))).enhance(0.6)

        # Gradient overlay
        start_color, end_color = random_color(), random_color()
        gradient = generate_gradient(1280, 720, start_color, end_color)
        background = Image.blend(background, gradient, alpha=0.2)

        draw = ImageDraw.Draw(background)

        # ✅ Make sure these font files exist
        arial = ImageFont.truetype("tg/assets/font2.ttf", 30)
        font = ImageFont.truetype("tg/assets/font.ttf", 30)
        title_font = ImageFont.truetype("tg/assets/font3.ttf", 45)

        # Circular thumbnail
        circle_thumb = crop_center_circle(youtube, 400, 20, start_color)
        background.paste(circle_thumb, (120, 160), circle_thumb)

        text_x = 565
        title_lines = truncate(title)
        draw_text_with_shadow(background, draw, (text_x, 180), title_lines[0], title_font, (255, 255, 255))
        draw_text_with_shadow(background, draw, (text_x, 230), title_lines[1], title_font, (255, 255, 255))
        draw_text_with_shadow(background, draw, (text_x, 320), f"{channel}  |  {views}", arial, (255, 255, 255))

        # Progress bar
        line_length = 580
        if duration.lower() != "live":
            color_line_len = int(line_length * random.uniform(0.15, 0.85))
            white_line_len = line_length - color_line_len
            draw.line([(text_x, 380), (text_x + color_line_len, 380)], fill=start_color, width=9)
            draw.line([(text_x + color_line_len, 380), (text_x + line_length, 380)], fill="white", width=8)
            circle_pos = (text_x + color_line_len, 380)
        else:
            draw.line([(text_x, 380), (text_x + line_length, 380)], fill="red", width=9)
            circle_pos = (text_x + line_length, 380)

        draw.ellipse([
            circle_pos[0] - 10, circle_pos[1] - 10,
            circle_pos[0] + 10, circle_pos[1] + 10
        ], fill=start_color)

        # Duration text
        draw_text_with_shadow(background, draw, (text_x, 400), "00:00", arial, (255, 255, 255))
        draw_text_with_shadow(background, draw, (1080, 400), duration, arial, (255, 255, 255))

        # Play icons (ensure file exists)
        play_icon = Image.open("tg/assets/play_icons.png").resize((580, 62))
        background.paste(play_icon,
