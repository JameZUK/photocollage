import io
import logging
import math
import random
import time

from PIL import Image, ImageOps

# pillow_heif is only needed if image_size='original' returns HEIC bytes.
try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except ImportError:
    pass

logger = logging.getLogger(__name__)

GOLDEN_RATIO = (1 + math.sqrt(5)) / 2


def asset_metadata(asset: dict) -> dict:
    """Extract display metadata from an Immich AssetResponseDto."""
    exif = asset.get('exifInfo') or {}

    dt_str = asset.get('localDateTime') or exif.get('dateTimeOriginal') or asset.get('fileCreatedAt')
    date_part = dt_str[:10] if isinstance(dt_str, str) and len(dt_str) >= 10 else 'N/A'

    city = exif.get('city')
    country = exif.get('country')
    if country == 'United Kingdom':
        country = 'UK'
    if city and country:
        location = f"{city}, {country}"
    elif city:
        location = city
    elif country:
        location = country
    else:
        location = 'N/A'

    return {
        'filename': asset.get('originalFileName', asset.get('id', 'unknown')),
        'datetime': date_part,
        'location': location,
    }


def _resize_image(img: Image.Image, max_size: int) -> Image.Image:
    if img.width > max_size or img.height > max_size:
        img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
    return img


def _load_assets(assets, fetcher, max_image_size, max_count):
    loaded = []
    for asset in assets[:max_count]:
        asset_id = asset['id']
        data = fetcher.fetch(asset_id)
        if not data:
            continue
        try:
            with Image.open(io.BytesIO(data)) as img:
                img = ImageOps.exif_transpose(img)
                img.load()
                resized = _resize_image(img.copy(), max_image_size)
        except Exception as e:
            logger.error(f"Failed to decode asset {asset_id}: {e}")
            continue
        loaded.append({
            'id': asset_id,
            'image': resized.convert('RGB'),
            'metadata': asset_metadata(asset),
        })
    return loaded


def create_collage(
    assets: list[dict],
    fetcher,
    *,
    width: int,
    height: int,
    layout: str = 'auto',
    padding: int = 10,
    randomize_order: bool = True,
    max_image_size: int = 800,
    max_images_per_collage: int = 20,
):
    """Build a collage from Immich asset dicts.

    Returns (PIL.Image, [{'box': (x1,y1,x2,y2), 'metadata': {...}}, ...]).
    """
    start = time.time()
    if not assets:
        logger.warning("No assets provided to create_collage.")
        return None, None

    image_details = _load_assets(assets, fetcher, max_image_size, max_images_per_collage)
    if not image_details:
        logger.error("No assets could be loaded.")
        return None, None

    resolved_layout = layout
    if layout == 'auto':
        orientations = {
            ('landscape' if i['image'].width > i['image'].height else 'portrait')
            for i in image_details
        }
        resolved_layout = 'golden_ratio' if len(orientations) > 1 else 'grid'
        logger.info(f"Auto-layout chose '{resolved_layout}'.")

    canvas = Image.new('RGB', (width, height), (255, 255, 255))
    layout_fn = _grid_layout if resolved_layout == 'grid' else _golden_ratio_layout
    canvas, placements = layout_fn(image_details, canvas, padding, randomize_order)

    details = [{'box': p['box'], 'metadata': p['metadata']} for p in placements]
    logger.info(f"Collage built in {time.time() - start:.2f}s ({len(details)} photos).")
    return canvas, details


def _golden_ratio_layout(image_details, canvas, padding, randomize_order):
    if randomize_order:
        random.shuffle(image_details)
    placements = []
    area = {
        'x': padding,
        'y': padding,
        'width': canvas.width - 2 * padding,
        'height': canvas.height - 2 * padding,
    }
    for i, item in enumerate(image_details):
        if area['width'] <= 0 or area['height'] <= 0:
            break
        is_last = (i == len(image_details) - 1)
        x, y = area['x'], area['y']

        if area['width'] > area['height']:
            split_w = area['width'] if is_last else int(area['width'] / GOLDEN_RATIO)
            img_fit = ImageOps.fit(item['image'], (split_w, area['height']), method=Image.Resampling.LANCZOS)
            area['x'] += img_fit.width + padding
            area['width'] -= (img_fit.width + padding)
        else:
            split_h = area['height'] if is_last else int(area['height'] / GOLDEN_RATIO)
            img_fit = ImageOps.fit(item['image'], (area['width'], split_h), method=Image.Resampling.LANCZOS)
            area['y'] += img_fit.height + padding
            area['height'] -= (img_fit.height + padding)

        canvas.paste(img_fit, (x, y))
        placements.append({
            'metadata': item['metadata'],
            'box': (x, y, x + img_fit.width, y + img_fit.height),
        })
    return canvas, placements


def _grid_layout(image_details, canvas, padding, randomize_order):
    if randomize_order:
        random.shuffle(image_details)
    placements = []
    n = len(image_details)
    w, h = canvas.size
    cols = max(1, math.ceil(math.sqrt(n * w / h)))
    rows = max(1, math.ceil(n / cols))

    cell_w = (w - (cols + 1) * padding) // cols
    cell_h = (h - (rows + 1) * padding) // rows

    for idx, item in enumerate(image_details):
        img_fit = ImageOps.fit(item['image'], (cell_w, cell_h), method=Image.Resampling.LANCZOS)
        col, row = idx % cols, idx // cols
        x = col * (cell_w + padding) + padding
        y = row * (cell_h + padding) + padding
        if x + cell_w > w or y + cell_h > h:
            continue
        canvas.paste(img_fit, (x, y))
        placements.append({
            'metadata': item['metadata'],
            'box': (x, y, x + cell_w, y + cell_h),
        })
    return canvas, placements
