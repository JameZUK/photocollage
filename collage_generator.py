# collage_generator.py
# Contains the logic for creating photo collages.

import os
import random
import math
import logging
import time
from PIL import Image, ImageOps

# Add the import for HEIC support
import pillow_heif

# This registers the HEIC decoder with Pillow, allowing Image.open() to work
pillow_heif.register_heif_opener()


# Set up a logger for this module
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

GOLDEN_RATIO = (1 + math.sqrt(5)) / 2

def find_images(directory):
    """
    Recursively finds all valid image files in a directory.
    """
    start_time = time.time()
    # Added .heic and .heif to the list of supported formats
    valid_extensions = ('.jpg', '.jpeg', '.png', '.heic', '.heif')
    image_paths = []
    logger.info(f"Searching for images in directory: {directory}...")
    for root, _, files in os.walk(directory):
        for file in files:
            if file.lower().endswith(valid_extensions):
                image_paths.append(os.path.join(root, file))
    duration = time.time() - start_time
    logger.info(f"Found {len(image_paths)} total images in {duration:.2f} seconds.")
    return image_paths

def resize_image(img, max_size):
    """
    Resizes a single image to fit within a max_size square, preserving aspect ratio.
    """
    if img.width > max_size or img.height > max_size:
        img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
    return img

def create_collage(image_paths, width, height, layout='auto', padding=10, randomize=True, max_image_size=800, max_images_per_collage=20, same_folder_percentage=25):
    """
    Main function to create a collage.
    """
    total_start_time = time.time()
    if not image_paths:
        logger.warning("No images provided to create_collage.")
        return None

    # --- Thematic folder selection logic ---
    selected_paths = []
    use_same_folder = random.randint(1, 100) <= same_folder_percentage

    if use_same_folder:
        logger.info(f"Attempting to select images from a single folder (chance: {same_folder_percentage}%).")
        folders = {}
        for path in image_paths:
            folder = os.path.dirname(path)
            if folder not in folders:
                folders[folder] = []
            folders[folder].append(path)

        min_images_in_folder = 4 
        valid_folders = [folder for folder, files in folders.items() if len(files) >= min_images_in_folder]

        if valid_folders:
            chosen_folder = random.choice(valid_folders)
            folder_images = folders[chosen_folder]
            logger.info(f"Selected thematic folder: '{os.path.basename(chosen_folder)}' with {len(folder_images)} images.")
            
            if len(folder_images) > max_images_per_collage:
                selected_paths = random.sample(folder_images, max_images_per_collage)
            else:
                selected_paths = list(folder_images)
        else:
            logger.info("No single folder has enough images for a thematic collage. Falling back to random selection.")
            use_same_folder = False

    if not use_same_folder:
        logger.info("Selecting images randomly from all available folders.")
        if len(image_paths) > max_images_per_collage:
            selected_paths = random.sample(image_paths, max_images_per_collage)
        else:
            selected_paths = list(image_paths)

    # --- Load and pre-resize images to determine layout for 'auto' mode ---
    resize_start_time = time.time()
    images = []
    for i, path in enumerate(selected_paths):
        if i < max_images_per_collage:
             logger.info(f"Processing image {i+1}/{len(selected_paths)}: {os.path.basename(path)}")
        try:
            with Image.open(path) as img:
                # *** THIS IS THE FIX ***
                # Apply EXIF orientation data to correct image rotation.
                img = ImageOps.exif_transpose(img)
                
                img.load()
                resized_img = resize_image(img, max_image_size)
                images.append(resized_img)
        except Exception as e:
            logger.error(f"Could not load or resize image {path}: {e}")
    
    resize_duration = time.time() - resize_start_time
    logger.info(f"Finished initial processing of {len(images)} images in {resize_duration:.2f} seconds.")
    
    if not images:
        logger.error("No images could be loaded successfully.")
        return None

    # --- Determine the final layout type ---
    resolved_layout = layout
    if layout == 'auto':
        orientations = {'landscape' if img.width > img.height else 'portrait' if img.height > img.width else 'square' for img in images}
        if len(orientations) > 1:
            resolved_layout = 'golden_ratio'
            logger.info("Auto-layout: Mixed image orientations detected. Using 'golden_ratio'.")
        else:
            resolved_layout = 'grid'
            logger.info("Auto-layout: Uniform image orientation detected. Using 'grid'.")

    # --- Auto-fill grid layouts to prevent empty spaces ---
    if resolved_layout == 'grid':
        images_num = len(selected_paths)
        cols = math.ceil(math.sqrt(images_num * width / height))
        rows = math.ceil(images_num / cols) if cols > 0 else 0
        perfect_grid_size = cols * rows

        if 0 < images_num < perfect_grid_size:
            needed_images = perfect_grid_size - images_num
            logger.info(f"Grid layout has {needed_images} empty slot(s). Trying to add more images.")
            
            available_extras = [p for p in image_paths if p not in selected_paths]
            
            if available_extras:
                num_to_add = min(needed_images, len(available_extras))
                logger.info(f"Adding {num_to_add} extra image(s) to complete the grid.")
                extra_paths = random.sample(available_extras, num_to_add)
                selected_paths.extend(extra_paths)
                
                for path in extra_paths:
                    try:
                        with Image.open(path) as img:
                            # Also apply EXIF transpose to the extra images
                            img = ImageOps.exif_transpose(img)
                            
                            img.load()
                            resized_img = resize_image(img, max_image_size)
                            images.append(resized_img)
                    except Exception as e:
                        logger.error(f"Could not load or resize extra image {path}: {e}")
            else:
                logger.warning("Not enough unique images available to fill the grid completely.")

    logger.info("--- Final images for collage ---")
    for path in selected_paths:
        logger.info(f"  - {os.path.basename(path)}")
    logger.info("---------------------------------")

    collage = Image.new('RGB', (width, height), (255, 255, 255))

    generate_start_time = time.time()
    if resolved_layout == 'grid':
        final_collage = grid_collage(images, collage, padding, randomize)
    elif resolved_layout == 'golden_ratio':
        final_collage = golden_ratio_collage(images, collage, padding, randomize)
    else:
        logger.warning(f"Unknown layout '{layout}', defaulting to golden ratio.")
        final_collage = golden_ratio_collage(images, collage, padding, randomize)

    generate_duration = time.time() - generate_start_time
    total_duration = time.time() - total_start_time
    logger.info(f"Finished generating collage layout in {generate_duration:.2f} seconds.")
    logger.info(f"Total collage creation took {total_duration:.2f} seconds.")
    return final_collage


def golden_ratio_collage(images, collage, padding, randomization):
    logger.info("Using 'golden_ratio' layout algorithm.")
    if randomization:
        random.shuffle(images)
    working_area = {"x": 0, "y": 0, "width": collage.width, "height": collage.height}
    horizontal_order = random.choice(["right-to-left", "left-to-right"]) if randomization else "right-to-left"
    vertical_order = random.choice(["bottom-to-top", "top-to-bottom"]) if randomization else "bottom-to-top"
    x, y = 0, 0
    for i, img in enumerate(images):
        is_last_image = (i == len(images) - 1)
        if working_area["width"] <= padding or working_area["height"] <= padding:
            logger.warning("Working area too small, stopping collage creation early.")
            break
        if working_area["width"] > working_area["height"]:
            split_width = working_area["width"] if is_last_image else int(working_area["width"] / GOLDEN_RATIO)
            img_fit = ImageOps.fit(img, (split_width, working_area["height"]), method=Image.Resampling.LANCZOS)
            if horizontal_order == "right-to-left":
                x = working_area["x"]
                working_area["x"] += img_fit.width + padding
                horizontal_order = "left-to-right"
            else:
                x = working_area["x"] + working_area["width"] - img_fit.width
                horizontal_order = "right-to-left"
            working_area["width"] -= (img_fit.width + padding)
        else:
            split_height = working_area["height"] if is_last_image else int(working_area["height"] / GOLDEN_RATIO)
            img_fit = ImageOps.fit(img, (working_area["width"], split_height), method=Image.Resampling.LANCZOS)
            if vertical_order == "bottom-to-top":
                y = working_area["y"]
                working_area["y"] += img_fit.height + padding
                vertical_order = "top-to-bottom"
            else:
                y = working_area["y"] + working_area["height"] - img_fit.height
                vertical_order = "bottom-to-top"
            working_area["height"] -= (img_fit.height + padding)
        collage.paste(img_fit, (x, y))
        x, y = working_area["x"], working_area["y"]
    return collage

def grid_collage(images, collage, padding, randomization):
    logger.info("Using 'grid' layout algorithm.")
    if randomization: random.shuffle(images)
    images_num = len(images)
    canvas_width, canvas_height = collage.size
    cols = math.ceil(math.sqrt(images_num * canvas_width / canvas_height))
    rows = math.ceil(images_num / cols) if cols > 0 else 0
    if cols == 0 or rows == 0: return collage
    cell_width = (canvas_width - (cols + 1) * padding) // cols
    cell_height = (canvas_height - (rows + 1) * padding) // rows
    for idx, img in enumerate(images):
        img_fit = ImageOps.fit(img, (cell_width, cell_height), method=Image.Resampling.LANCZOS)
        col_idx, row_idx = idx % cols, idx // cols
        x = col_idx * (cell_width + padding) + padding
        y = row_idx * (cell_height + padding) + padding
        if x + cell_width <= canvas_width and y + cell_height <= canvas_height:
            collage.paste(img_fit, (x, y))
    return collage
