# main.py
# The main entry point for the application.
# Starts the web server to serve the generated collage.

import io
import logging
from flask import Flask, Response, send_file
from config import get_config
from collage_generator import find_images, create_collage

# Initialize the Flask app
app = Flask(__name__)

# Set up logging for the application
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load the application configuration
config = get_config()

@app.route('/')
def index():
    """
    Provides a simple index page with instructions.
    """
    if not config:
        return "<h1>Error: Configuration could not be loaded. Check console.</h1>", 500
        
    port = config.get('server', {}).get('port', 8000)
    return (
        "<h1>Photo Collage Generator</h1>"
        f"<p>Your collage is available at: <a href='/collage.png'>/collage.png</a></p>"
        "<p>Refresh the /collage.png page to generate a new image.</p>"
        "<p>To configure the application, edit the <code>config.yaml</code> file and restart the server.</p>"
        "<p>Check the console output for detailed logs.</p>"
    )

@app.route('/collage.png')
def serve_collage():
    """
    The main endpoint that generates and serves the collage image.
    """
    logger.info("Received request for /collage.png")
    if not config:
        logger.critical("Configuration not loaded. Cannot serve collage.")
        return "Error: Configuration not loaded.", 500

    # Get settings from config
    photo_settings = config.get('photos', {})
    display_settings = config.get('display', {})
    
    source_dir = photo_settings.get('source_directory')
    layout = photo_settings.get('layout', 'auto')
    padding = photo_settings.get('padding', 10)
    randomize = photo_settings.get('randomize_order', True)
    max_size = photo_settings.get('max_image_size', 800)
    max_images = photo_settings.get('max_images_per_collage', 20)
    same_folder_chance = photo_settings.get('same_folder_percentage', 25)
    
    width = display_settings.get('width', 1600)
    height = display_settings.get('height', 1200)

    # 1. Find images
    image_paths = find_images(source_dir)
    if not image_paths:
        return f"No images found in '{source_dir}'. Please add some photos.", 404

    # 2. Create the collage
    collage_image = create_collage(
        image_paths, width, height, layout, padding, randomize, max_size, max_images, same_folder_chance
    )
    if collage_image is None:
        logger.error("Collage generation failed.")
        return "Failed to generate collage.", 500

    # 3. Serve the image
    img_io = io.BytesIO()
    collage_image.save(img_io, 'PNG')
    img_io.seek(0)
    
    logger.info("Successfully served collage image.")
    return send_file(img_io, mimetype='image/png')

if __name__ == '__main__':
    if not config:
        logger.critical("Exiting: Could not load configuration.")
    else:
        server_settings = config.get('server', {})
        host = server_settings.get('host', '0.0.0.0')
        port = server_settings.get('port', 8000)
        
        logger.info(f"Starting server at http://{host}:{port}")
        # --- DEBUGGING STEP ---
        # Reverted to the built-in Flask server to diagnose the startup issue.
        # It provides more verbose output for debugging.
        app.run(host=host, port=port, debug=True)
