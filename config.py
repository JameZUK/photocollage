import copy
import os
from collections.abc import Mapping

import yaml

DEFAULT_CONFIG = {
    'server': {
        'host': '0.0.0.0',
        'port': 8000,
    },
    'display': {
        'width': 1600,
        'height': 1200,
    },
    'info_display': {
        'width': 400,
        'height': 300,
        'font_settings': {
            'header': {
                'path': '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
                'size': 12,
            },
            'body': {
                'path': '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
                'size': 10,
            },
            'group_letter': {
                'path': '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
                'size': 24,
            },
        },
    },
    'immich': {
        'base_url': 'http://immich:2283',
        'api_key': '',
        'verify_tls': True,
        'image_size': 'preview',  # 'preview' or 'original'
    },
    'selection': {
        # Weighted random across strategies. Zero disables a strategy.
        'weights': {
            'random': 60,
            'memories': 25,
            'album': 15,
        },
        # Used when strategy == 'album'. Empty means pick any album with enough photos.
        'album_ids': [],
        'min_assets_per_collage': 4,
    },
    'cache': {
        # In-memory TTL for the cached asset-list query; 0 disables.
        'asset_list_ttl_seconds': 300,
        # Image byte cache on disk; empty path disables.
        'image_dir': '',
        'image_max_bytes': 500_000_000,
    },
    'photos': {
        'layout': 'auto',
        'padding': 10,
        'randomize_order': True,
        'max_image_size': 800,
        'max_images_per_collage': 20,
    },
    'generation': {
        # Seconds a generated collage is considered fresh; second display can fetch
        # within this window without forcing a new collage. 0 = always regenerate.
        'ttl_seconds': 30,
    },
    'debugging': {
        'enabled': False,
    },
}

CONFIG_FILE = 'config.yaml'


def _deep_merge(source: Mapping, destination: dict) -> dict:
    for key, value in source.items():
        if isinstance(value, Mapping):
            destination[key] = _deep_merge(value, destination.get(key, {}))
        else:
            destination[key] = value
    return destination


def get_config() -> dict:
    if not os.path.exists(CONFIG_FILE):
        print(f"Configuration file '{CONFIG_FILE}' not found. Creating a default one.")
        try:
            with open(CONFIG_FILE, 'w') as f:
                yaml.dump(DEFAULT_CONFIG, f, default_flow_style=False, sort_keys=False)
            print(f"Default configuration file created at '{os.path.abspath(CONFIG_FILE)}'.")
        except IOError as e:
            print(f"Error creating default configuration file: {e}")
            return copy.deepcopy(DEFAULT_CONFIG)

    final_config = copy.deepcopy(DEFAULT_CONFIG)
    try:
        with open(CONFIG_FILE, 'r') as f:
            user_config = yaml.safe_load(f)
            if user_config:
                _deep_merge(user_config, final_config)
    except (IOError, yaml.YAMLError) as e:
        print(f"Error loading or parsing configuration file: {e}. Using default settings.")
        return copy.deepcopy(DEFAULT_CONFIG)

    return final_config


if __name__ == '__main__':
    config = get_config()
    print(yaml.dump(config, indent=2, default_flow_style=False, sort_keys=False))
