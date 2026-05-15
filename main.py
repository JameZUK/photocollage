import io
import logging
import math
import os
import threading
import time
from datetime import date as _date_cls, datetime as _datetime_cls
from typing import Optional

from flask import Flask, send_file
from PIL import Image, ImageDraw, ImageFont

from asset_source import AssetSource, ImageFetcher
from collage_generator import create_collage
from config import get_config
from immich_client import ImmichClient


def _relative_date(date_str: str) -> str:
    """Convert 'YYYY-MM-DD' to a compact relative form like '8y ago'."""
    try:
        d = _datetime_cls.strptime(date_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return ''
    today = _date_cls.today()
    delta_days = (today - d).days
    if delta_days < 0:
        return ''
    if delta_days == 0:
        return 'today'
    if delta_days == 1:
        return 'yesterday'
    if delta_days < 14:
        return f'{delta_days}d ago'
    if delta_days < 60:
        return f'{delta_days // 7}w ago'
    years = today.year - d.year - ((today.month, today.day) < (d.month, d.day))
    if years >= 1:
        return f'{years}y ago'
    months = (today.year - d.year) * 12 + (today.month - d.month) - (1 if today.day < d.day else 0)
    return f'{months}mo ago' if months > 0 else ''


def _format_people(names: list, *, max_show: int = 3, first_names_only: bool = True) -> str:
    """Compact people summary: 'Tom, Sarah & Mum' or 'Tom, Sarah, Mum +2'."""
    if not names:
        return ''
    seen = {}
    for n in names:
        if not n:
            continue
        display = n.split(' ', 1)[0] if first_names_only else n
        seen[display] = seen.get(display, 0) + 1
    if not seen:
        return ''
    unique = sorted(seen.keys(), key=lambda k: (-seen[k], k))
    if len(unique) <= max_show:
        if len(unique) == 1:
            return unique[0]
        return ', '.join(unique[:-1]) + ' & ' + unique[-1]
    rest = len(unique) - max_show
    return ', '.join(unique[:max_show]) + f' +{rest}'

app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

config = get_config()

immich_cfg = config['immich']
immich_client = ImmichClient(
    base_url=immich_cfg['base_url'],
    api_key=immich_cfg['api_key'],
    verify_tls=immich_cfg.get('verify_tls', True),
)
asset_source = AssetSource(immich_client, config['selection'], config['cache'])
image_fetcher = ImageFetcher(immich_client, immich_cfg.get('image_size', 'preview'), config['cache'])


# --- Data Grouping Logic ---

def group_collage_info(photo_details):
    """Groups photos by date and location, assigning styles and letters."""
    groups = {}
    photo_to_group_key = {}

    core_colors = [
        ((255, 0, 0), 'Red'),
        ((255, 255, 0), 'Yellow'),
        ((0, 0, 0), 'Black'),
    ]
    red, yellow, black = core_colors[0], core_colors[1], core_colors[2]
    stripe_combinations = [
        (red, yellow),
        (black, red),
        (yellow, black),
    ]
    styles = core_colors + stripe_combinations

    for i, item in enumerate(photo_details):
        meta = item.get('metadata', {})
        date_part = meta.get('datetime', 'Unknown Date').split(' ')[0]
        location = meta.get('location', 'Unknown Location')
        group_key = (date_part, location)

        photo_to_group_key[i] = group_key

        if group_key not in groups:
            group_index = len(groups)
            style = styles[group_index % len(styles)]
            group_letter = chr(ord('A') + group_index)
            groups[group_key] = {
                'style': style,
                'letter': group_letter,
                'members': [],
            }
        groups[group_key]['members'].append(i)

    for i, (group_key, group_data) in enumerate(groups.items()):
        group_data['id'] = i
        group_data['key'] = group_key

    return {'photos': photo_details, 'groups': list(groups.values()), 'photo_map': photo_to_group_key}


# --- Pillow-based InfoGraphic Renderer ---
class InfoGraphicRenderer:
    def __init__(self, collage_info, config):
        self.collage_info = collage_info
        self.settings = config.get('info_display', {})
        self.width = self.settings.get('width', 400)
        self.height = self.settings.get('height', 300)
        self.image = Image.new('RGB', (self.width, self.height), (255, 255, 255))
        self.draw = ImageDraw.Draw(self.image)
        self._load_fonts()
        self.debug_enabled = config.get('debugging', {}).get('enabled', False)
        self.group_text_cfg = self.settings.get('group_text', {})
        self.fit_groups = set()
        self.callout_groups = {}
        self.scale_x = 1
        self.scale_y = 1

    def _build_group_text_lines(self, group):
        """Return ordered text lines for a group based on info_display.group_text.lines."""
        photos = self.collage_info['photos']
        members = group['members']
        date_str, location = group['key']
        fields = self.group_text_cfg.get('lines', ['date', 'location', 'filenames'])
        people_max = self.group_text_cfg.get('people_max', 3)
        first_names = self.group_text_cfg.get('use_first_names_only', True)

        def metas():
            return [photos[m]['metadata'] for m in members]

        lines = []
        for field in fields:
            if field == 'date':
                if date_str not in ('Unknown Date', 'N/A'):
                    lines.append(date_str)
            elif field == 'date_relative':
                rel = _relative_date(date_str)
                if rel:
                    lines.append(rel)
            elif field == 'location':
                if location not in ('Unknown Location', 'N/A'):
                    lines.append(location)
            elif field == 'city':
                cities = sorted({m.get('city') for m in metas() if m.get('city')})
                if cities:
                    lines.append(', '.join(cities))
            elif field == 'country':
                countries = sorted({m.get('country') for m in metas() if m.get('country')})
                if countries:
                    lines.append(', '.join(countries))
            elif field == 'people':
                names = []
                for m in metas():
                    names.extend(m.get('people') or [])
                formatted = _format_people(names, max_show=people_max, first_names_only=first_names)
                if formatted:
                    lines.append(formatted)
            elif field == 'description':
                for m in metas():
                    desc = (m.get('description') or '').strip()
                    if desc:
                        lines.append(desc)
                        break
            elif field == 'filenames':
                if len(members) > 1:
                    lines.extend(
                        f"{i+1}. {os.path.basename(photos[m]['metadata']['filename'])}"
                        for i, m in enumerate(members)
                    )
                elif members:
                    lines.append(os.path.basename(photos[members[0]]['metadata']['filename']))
            elif field == 'filenames_plain':
                for m in members:
                    lines.append(os.path.basename(photos[m]['metadata']['filename']))
        return lines

    def _load_fonts(self):
        font_config = self.settings.get('font_settings', {})
        self.fonts = {}
        defaults = {
            'header': {'path': None, 'size': 12},
            'body': {'path': None, 'size': 10},
            'group_letter': {'path': None, 'size': 24},
        }
        for name, default in defaults.items():
            info = font_config.get(name, default)
            try:
                self.fonts[name] = ImageFont.truetype(info.get('path', 'sans-serif.ttf'), info.get('size'))
            except IOError:
                logger.warning(f"Font '{info.get('path')}' not found. Using default font for '{name}'.")
                self.fonts[name] = ImageFont.load_default()

    def render(self):
        if not self.collage_info or not self.collage_info.get('photos'):
            return Image.new('RGB', (self.width, self.height), (250, 250, 250))
        self._determine_final_layout()
        self._drawing_pass()
        return self._finalize_and_get_image()

    def _get_wrapped_text_and_height(self, text, font, available_w):
        if available_w <= 0:
            return "", 0
        original_lines = text.split('\n')
        wrapped_lines = []
        for line in original_lines:
            words = line.split(' ')
            current_line = ""
            for word in words:
                if not word:
                    continue
                word_width = self.draw.textbbox((0, 0), word, font=font)[2]
                test_line = current_line + (" " if current_line else "") + word
                test_width = self.draw.textbbox((0, 0), test_line, font=font)[2]
                if test_width <= available_w:
                    current_line = test_line
                else:
                    if current_line:
                        wrapped_lines.append(current_line)
                    if word_width > available_w:
                        remaining_word = word
                        while remaining_word:
                            cut_pos = 0
                            for i in range(1, len(remaining_word) + 1):
                                chunk = remaining_word[:i]
                                if self.draw.textbbox((0, 0), chunk, font=font)[2] <= available_w:
                                    cut_pos = i
                                else:
                                    break
                            if cut_pos == 0 and len(remaining_word) > 0:
                                cut_pos = 1
                            wrapped_lines.append(remaining_word[:cut_pos])
                            remaining_word = remaining_word[cut_pos:]
                        current_line = ""
                    else:
                        current_line = word
            if current_line:
                wrapped_lines.append(current_line)
        wrapped_text = "\n".join(wrapped_lines)
        final_bbox = self.draw.textbbox((0, 0), wrapped_text, font=font)
        return wrapped_text, final_bbox[3] - final_bbox[1]

    def _determine_final_layout(self):
        photos = self.collage_info['photos']
        self.min_x_coll = min(p['box'][0] for p in photos)
        self.max_x_coll = max(p['box'][2] for p in photos)
        self.min_y_coll = min(p['box'][1] for p in photos)
        self.max_y_coll = max(p['box'][3] for p in photos)
        coll_w = self.max_x_coll - self.min_x_coll
        coll_h = self.max_y_coll - self.min_y_coll

        while True:
            current_callout_keys = set(self.callout_groups.keys())
            has_left = 'left' in self.callout_groups.values()
            has_right = 'right' in self.callout_groups.values()
            callout_panel_width = self.width * 0.35
            grid_x_start, grid_width = 0, self.width
            if has_left:
                grid_x_start = callout_panel_width
                grid_width -= callout_panel_width
            if has_right:
                grid_width -= callout_panel_width

            scale_x_current = grid_width / coll_w if coll_w > 0 else 0
            scale_y_current = self.height / coll_h if coll_h > 0 else 0

            new_fit_groups, new_callout_groups = set(), {}
            collage_center_x = (self.min_x_coll + self.max_x_coll) / 2

            for group_data in self.collage_info['groups']:
                member_boxes = [(photos[i]['box'], i) for i in group_data['members']]
                largest_box_coll, _ = max(member_boxes, key=lambda item: (item[0][2] - item[0][0]) * (item[0][3] - item[0][1]))
                body_lines = self._build_group_text_lines(group_data)
                full_group_text = "\n".join([group_data['letter']] + body_lines)

                available_w = (largest_box_coll[2] - largest_box_coll[0]) * scale_x_current - 20
                available_h = (largest_box_coll[3] - largest_box_coll[1]) * scale_y_current - 20
                _, measured_height = self._get_wrapped_text_and_height(full_group_text, self.fonts['body'], available_w)

                text_fits_height = (measured_height + 15) < available_h
                box_is_large_enough = available_w > 60 and available_h > 40
                group_fits = text_fits_height and box_is_large_enough

                if group_fits:
                    new_fit_groups.add(group_data['id'])
                else:
                    group_center_x = (min(b[0][0] for b in member_boxes) + max(b[0][2] for b in member_boxes)) / 2
                    new_callout_groups[group_data['id']] = 'left' if group_center_x < collage_center_x else 'right'

            if set(new_callout_groups.keys()) == current_callout_keys:
                self.fit_groups, self.callout_groups = new_fit_groups, new_callout_groups
                break
            self.callout_groups = new_callout_groups

        has_left = 'left' in self.callout_groups.values()
        has_right = 'right' in self.callout_groups.values()
        callout_panel_width = self.width * 0.35
        grid_x_start, grid_width = 0, self.width
        if has_left:
            grid_x_start = callout_panel_width
            grid_width -= callout_panel_width
        if has_right:
            grid_width -= callout_panel_width
        self.scale_x = grid_width / coll_w if coll_w > 0 else 0
        self.scale_y = self.height / coll_h if coll_h > 0 else 0
        self.grid_area_x, self.grid_area_y = grid_x_start, 0

    def _get_scaled_box(self, box_coll):
        x = self.grid_area_x + (box_coll[0] - self.min_x_coll) * self.scale_x
        y = self.grid_area_y + (box_coll[1] - self.min_y_coll) * self.scale_y
        w = (box_coll[2] - box_coll[0]) * self.scale_x
        h = (box_coll[3] - box_coll[1]) * self.scale_y
        return x, y, w, h

    def _drawing_pass(self):
        self._draw_grid_boxes_and_labels()
        self._draw_callout_panels()

    def _get_rounded_rect_path(self, xy, radius):
        x0, y0, x1, y1 = xy
        path = []
        for i in range(16):
            path.append((x1 - radius + radius * math.cos(math.radians(-90 + i * (90 / 15))), y0 + radius + radius * math.sin(math.radians(-90 + i * (90 / 15)))))
        for i in range(16):
            path.append((x1 - radius + radius * math.cos(math.radians(0 + i * (90 / 15))), y1 - radius + radius * math.sin(math.radians(0 + i * (90 / 15)))))
        for i in range(16):
            path.append((x0 + radius + radius * math.cos(math.radians(90 + i * (90 / 15))), y1 - radius + radius * math.sin(math.radians(90 + i * (90 / 15)))))
        for i in range(16):
            path.append((x0 + radius + radius * math.cos(math.radians(180 + i * (90 / 15))), y0 + radius + radius * math.sin(math.radians(180 + i * (90 / 15)))))
        path.append(path[0])
        return path

    def _draw_striped_path(self, path, color1, color2, width, dash_length=5):
        path_distance = 0
        for i in range(len(path) - 1):
            p1, p2 = path[i], path[i + 1]
            dx, dy = p2[0] - p1[0], p2[1] - p1[1]
            segment_length = math.hypot(dx, dy)
            if segment_length == 0:
                continue
            unit_dx, unit_dy = dx / segment_length, dy / segment_length
            segment_distance = 0
            while segment_distance < segment_length:
                current_color = color1 if int(path_distance // dash_length) % 2 == 0 else color2
                len_to_draw = min(dash_length - (path_distance % dash_length), segment_length - segment_distance)
                start_x, start_y = p1[0] + segment_distance * unit_dx, p1[1] + segment_distance * unit_dy
                end_x, end_y = start_x + len_to_draw * unit_dx, start_y + len_to_draw * unit_dy
                self.draw.line([(start_x, start_y), (end_x, end_y)], fill=current_color, width=width)
                segment_distance += len_to_draw
                path_distance += len_to_draw

    def _draw_grid_boxes_and_labels(self):
        photos = self.collage_info['photos']
        for group_data in self.collage_info['groups']:
            group_id = group_data['id']
            style = group_data['style']
            is_stripe = isinstance(style[0], tuple) and isinstance(style[0][0], tuple)
            member_boxes = [(photos[i]['box'], i) for i in group_data['members']]
            largest_box_coll, largest_photo_idx = max(member_boxes, key=lambda item: (item[0][2] - item[0][0]) * (item[0][3] - item[0][1]))

            for _, (photo_box_coll, photo_idx) in enumerate(member_boxes):
                x, y, w, h = self._get_scaled_box(photo_box_coll)
                gap = 2
                if is_stripe:
                    color1, _ = style[0]
                    color2, _ = style[1]
                    linewidth = 6
                    offset = linewidth / 2
                    path = [
                        (x + gap + offset, y + gap + offset),
                        (x + w - gap - offset, y + gap + offset),
                        (x + w - gap - offset, y + h - gap - offset),
                        (x + gap + offset, y + h - gap - offset),
                        (x + gap + offset, y + gap + offset),
                    ]
                    self._draw_striped_path(path, color1, color2, width=linewidth)
                else:
                    color_tuple, _ = style
                    self.draw.rectangle([x + gap, y + gap, x + w - gap, y + h - gap], outline=color_tuple, width=6)

                if group_id in self.fit_groups and photo_idx == largest_photo_idx:
                    body_lines = self._build_group_text_lines(group_data)
                    text_to_draw = "\n".join([group_data['letter']] + body_lines)
                    wrapped_text, _ = self._get_wrapped_text_and_height(text_to_draw, self.fonts['body'], w - 20)
                    self._draw_text_in_box(wrapped_text, self.fonts['body'], (x, y, w, h), (0, 0, 0), stroke_color=(255, 255, 255))
                else:
                    text_color = style[0][0] if is_stripe else style[0]
                    self._draw_text_in_box(group_data['letter'], self.fonts['group_letter'], (x, y, w, h), text_color, stroke_color=(255, 255, 255))

    def _draw_callout_panels(self):
        groups_by_id = {g['id']: g for g in self.collage_info['groups']}
        left_groups = [groups_by_id[gid] for gid, side in self.callout_groups.items() if side == 'left']
        right_groups = [groups_by_id[gid] for gid, side in self.callout_groups.items() if side == 'right']
        self._draw_single_panel(left_groups, is_left_panel=True)
        self._draw_single_panel(right_groups, is_left_panel=False)

    def _draw_single_panel(self, groups, is_left_panel):
        if not groups:
            return
        photos = self.collage_info['photos']
        for group in groups:
            member_boxes = [photos[i]['box'] for i in group['members']]
            if is_left_panel:
                nearest_box_coll = min(member_boxes, key=lambda b: b[0])
                anchor_x_coll = nearest_box_coll[0]
            else:
                nearest_box_coll = max(member_boxes, key=lambda b: b[2])
                anchor_x_coll = nearest_box_coll[2]
            anchor_y_coll = (nearest_box_coll[1] + nearest_box_coll[3]) / 2
            sx, sy, _, _ = self._get_scaled_box((anchor_x_coll, anchor_y_coll, anchor_x_coll, anchor_y_coll))
            group['anchor_x'], group['anchor_y'] = sx, sy

        groups.sort(key=lambda g: g['anchor_y'])
        panel_width = self.width * 0.35
        grid_padding = (0.05 * self.width + 20) / 2
        side_padding = 4
        callout_max_width = panel_width - grid_padding - side_padding

        placed_boxes = []
        for group in groups:
            header_line = f"Group {group['letter']}"
            body_lines = self._build_group_text_lines(group)
            wrapped_text, box_h = self._get_wrapped_text_and_height('\n'.join([header_line] + body_lines), self.fonts['header'], callout_max_width)
            box_h += 20
            placed_boxes.append({'y': group['anchor_y'] - box_h / 2, 'h': box_h, 'group': group, 'text': wrapped_text})

        for i in range(1, len(placed_boxes)):
            prev_box, curr_box = placed_boxes[i - 1], placed_boxes[i]
            if curr_box['y'] < prev_box['y'] + prev_box['h'] + 10:
                curr_box['y'] = prev_box['y'] + prev_box['h'] + 10

        if placed_boxes:
            total_h = (placed_boxes[-1]['y'] + placed_boxes[-1]['h']) - placed_boxes[0]['y']
            current_center = placed_boxes[0]['y'] + total_h / 2
            ideal_center = sum(b['group']['anchor_y'] for b in placed_boxes) / len(placed_boxes)
            shift = ideal_center - current_center
            for box in placed_boxes:
                box['y'] += shift
            min_y, max_y = placed_boxes[0]['y'], placed_boxes[-1]['y'] + placed_boxes[-1]['h']
            if min_y < 10:
                for box in placed_boxes:
                    box['y'] += (10 - min_y)
            if max_y > self.height - 10:
                for box in placed_boxes:
                    box['y'] -= (max_y - (self.height - 10))

        for box_data in placed_boxes:
            y, h, group = box_data['y'], box_data['h'], box_data['group']
            style = group['style']
            box_x = side_padding if is_left_panel else (self.width - panel_width) + grid_padding
            is_stripe = isinstance(style[0], tuple) and isinstance(style[0][0], tuple)

            self.draw.rounded_rectangle([box_x, y, box_x + callout_max_width, y + h], radius=15, fill=(255, 255, 255))
            if is_stripe:
                color1, _ = style[0]
                color2, _ = style[1]
                linewidth = 6
                offset = linewidth / 2
                xy_inset = (box_x + offset, y + offset, box_x + callout_max_width - offset, y + h - offset)
                inset_radius = max(0, 15 - offset)
                path = self._get_rounded_rect_path(xy_inset, inset_radius)
                self._draw_striped_path(path, color1, color2, width=linewidth)
                line_color_tuple = (color1, color2)
            else:
                color_tuple, _ = style
                self.draw.rounded_rectangle([box_x, y, box_x + callout_max_width, y + h], radius=15, outline=color_tuple, width=6)
                line_color_tuple = (color_tuple, color_tuple)

            self._draw_text_in_box(box_data['text'], self.fonts['header'], (box_x, y, callout_max_width, h), (0, 0, 0))

            gap = 2
            line_end_y = group['anchor_y']
            if is_left_panel:
                line_start_x, line_end_x = box_x + callout_max_width, group['anchor_x'] + gap
            else:
                line_start_x, line_end_x = box_x, group['anchor_x'] - gap
            self._draw_striped_path([(line_start_x, y + h / 2), (line_end_x, line_end_y)], line_color_tuple[0], line_color_tuple[1], width=6)
            self.draw.ellipse([line_end_x - 4, line_end_y - 4, line_end_x + 4, line_end_y + 4], fill=line_color_tuple[0], outline=(255, 255, 255), width=1)

    def _draw_text_in_box(self, text, font, box, color, stroke_color=None):
        x, y, w, h = box
        bbox = self.draw.textbbox((0, 0), text, font=font, align="center")
        text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        text_x = x + (w - text_w) / 2
        text_y = y + (h - text_h) / 2
        self.draw.text((text_x, text_y), text, font=font, fill=color, align="center",
                       stroke_width=2 if stroke_color else 0, stroke_fill=stroke_color)

    def _finalize_and_get_image(self):
        # Quantize to the Inky wHAT 4-colour palette so text and borders are crisp.
        palette_data = [
            0, 0, 0,
            255, 255, 255,
            255, 255, 0,
            255, 0, 0,
        ] + [0] * (252 * 3)
        palette_image = Image.new('P', (1, 1))
        palette_image.putpalette(palette_data)
        return self.image.convert('RGB').quantize(palette=palette_image, dither=Image.Dither.NONE)


# --- Generation manager: shared collage state for /collage.png and /info.png ---

class GenerationManager:
    def __init__(self, ttl_seconds: int):
        self.ttl = max(0, int(ttl_seconds))
        self._lock = threading.Lock()
        self._current: Optional[dict] = None

    def ensure_current(self) -> Optional[dict]:
        with self._lock:
            now = time.monotonic()
            if self._current and self.ttl > 0 and (now - self._current['created_at']) < self.ttl:
                return self._current
            new = self._generate()
            if new is None:
                return self._current  # keep the stale generation rather than nothing
            new['created_at'] = now
            self._current = new
            return new

    def _generate(self) -> Optional[dict]:
        photo_cfg = config['photos']
        display_cfg = config['display']
        max_n = photo_cfg.get('max_images_per_collage', 20)

        assets, strategy = asset_source.pick_assets(max_n)
        if not assets:
            logger.error("No assets returned from any selection strategy.")
            return None

        collage_image, details = create_collage(
            assets,
            image_fetcher,
            width=display_cfg['width'],
            height=display_cfg['height'],
            layout=photo_cfg.get('layout', 'auto'),
            padding=photo_cfg.get('padding', 10),
            randomize_order=photo_cfg.get('randomize_order', True),
            max_image_size=photo_cfg.get('max_image_size', 800),
            max_images_per_collage=max_n,
        )
        if collage_image is None or not details:
            return None

        return {
            'collage_image': collage_image,
            'info': group_collage_info(details),
            'strategy': strategy,
        }


generation = GenerationManager(config['generation']['ttl_seconds'])


# --- Flask Routes ---

@app.route('/')
def index():
    legend_html = "<h2>Last Collage Legend</h2>"
    current = generation._current
    if current and current['info'].get('groups'):
        sorted_groups = sorted(current['info']['groups'], key=lambda g: g['letter'])
        for group_info in sorted_groups:
            style = group_info['style']
            is_stripe = isinstance(style[0], tuple) and isinstance(style[0][0], tuple)
            if is_stripe:
                hex_color1 = '#%02x%02x%02x' % style[0][0]
                hex_color2 = '#%02x%02x%02x' % style[1][0]
                legend_marker = f"<span style='color:{hex_color1};'>●</span><span style='color:{hex_color2};'>●</span>"
            else:
                hex_color = '#%02x%02x%02x' % style[0]
                legend_marker = f"<strong style='color:{hex_color};'>●</strong>"
            date, location = group_info['key']
            legend_html += f"<p>{legend_marker} Group {group_info['letter']}: {date}, {location}</p>"
        legend_html += f"<p><em>Strategy: {current['strategy']}</em></p>"
    else:
        legend_html += "<p>No collage generated yet.</p>"

    return ("<h1>Photo Collage Server</h1>"
            f"<p>View the collage: <a href='/collage.png'>/collage.png</a></p>"
            f"<p>View the info graphic: <a href='/info.png'>/info.png</a></p><hr>" + legend_html)


@app.route('/collage.png')
def serve_collage():
    current = generation.ensure_current()
    if current is None:
        return "Failed to generate collage. Check logs.", 500
    img_io = io.BytesIO()
    current['collage_image'].save(img_io, 'PNG')
    img_io.seek(0)
    return send_file(img_io, mimetype='image/png')


@app.route('/info.png')
def serve_info_image():
    current = generation.ensure_current()
    if current is None:
        return "Failed to generate collage. Check logs.", 500
    renderer = InfoGraphicRenderer(current['info'], config)
    info_image = renderer.render()
    img_io = io.BytesIO()
    info_image.save(img_io, 'PNG')
    img_io.seek(0)
    return send_file(img_io, mimetype='image/png')


if __name__ == '__main__':
    from waitress import serve
    server_cfg = config['server']
    host, port = server_cfg.get('host', '0.0.0.0'), server_cfg.get('port', 8000)
    logger.info(f"Starting production server at http://{host}:{port}")
    serve(app, host=host, port=port)
