# config.py
# Handles loading and creating the application's configuration file.

import yaml
import os

# Define the default configuration structure.
# This will be used if config.yaml does not exist.
DEFAULT_CONFIG = {
    'server': {
        'host': '0.0.0.0',
        'port': 8000
    },
    'display': {
        'width': 1600,
        'height': 1200
    },
    'photos': {
        'source_directory': './photos',
        'layout': 'auto',
        'padding': 10,
        'randomize_order': True,
        'max_image_size': 800,
        'max_images_per_collage': 20,
        # New setting: Percentage chance to pull all images from a single sub-folder.
        'same_folder_percentage': 25
    }
}

CONFIG_FILE = 'config.yaml'

def get_config():
    """
    Loads the configuration from config.yaml.
    If the file doesn't exist, it creates it with default settings.
    """
    if not os.path.exists(CONFIG_FILE):
        print(f"Configuration file '{CONFIG_FILE}' not found. Creating a default one.")
        try:
            with open(CONFIG_FILE, 'w') as f:
                yaml.dump(DEFAULT_CONFIG, f, default_flow_style=False, sort_keys=False)
            print(f"Default configuration file created at '{os.path.abspath(CONFIG_FILE)}'.")
            # Create a placeholder photos directory as well
            photos_dir = DEFAULT_CONFIG['photos']['source_directory']
            if not os.path.exists(photos_dir):
                os.makedirs(photos_dir)
                print(f"Created a sample '{photos_dir}' directory. Please add your photos there.")

        except IOError as e:
            print(f"Error creating default configuration file: {e}")
            return None

    # Now, load the configuration from the file.
    try:
        with open(CONFIG_FILE, 'r') as f:
            config = yaml.safe_load(f)
            return config
    except (IOError, yaml.YAMLError) as e:
        print(f"Error loading configuration file: {e}")
        return None

if __name__ == '__main__':
    # This allows running the script directly to test config loading/creation.
    config = get_config()
    if config:
        print("\nConfiguration loaded successfully:")
        print(yaml.dump(config, indent=2))
