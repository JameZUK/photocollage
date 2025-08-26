## **Photo Collage Generator for Inky Impression Display**

### **1\. Application Overview**

The project is a Python-based web application designed to create and serve photo collages specifically formatted for an Inky Impression e-ink display. The application will run as a local web server, which, when accessed, will dynamically generate a collage from a user-defined directory of photos. It will be configurable via a simple text file, allowing users to easily set parameters like display resolution and the source of their images. If the configuration file is missing on first run, the application will automatically create a default version with example settings to ensure a smooth initial setup.

### **2\. Core Functionality**

* **Configuration Management:**  
  * On startup, the application will look for a configuration file (e.g., config.yaml) in its root directory.  
  * If the file exists, it will load the settings.  
  * If the file does not exist, it will generate a new one with predefined default values and clear comments explaining each setting.  
* **Image Source:**  
  * The application will read image files from a directory structure specified in the configuration.  
  * It will recursively scan the source directory to find all valid image files (e.g., .jpg, .jpeg, .png).  
* **Collage Generation:**  
  * The core feature is the dynamic creation of a single collage image.  
  * The application will intelligently select a number of photos from the source directory. If randomize\_order is true, the selection will be shuffled.  
  * It will arrange these photos into a visually appealing layout based on the layout setting. Options will include:  
    * **grid**: A standard layout that arranges images in a uniform grid. Best for images of similar aspect ratios.  
    * **golden\_ratio**: A more dynamic layout that recursively divides the canvas according to the golden ratio, creating a pleasing, organic look. Works well with mixed-orientation photos.  
    * **auto**: The application will analyze the aspect ratios of the selected images and attempt to choose the most suitable layout automatically.  
  * The final generated image will be resized to the exact resolution specified in the configuration file (e.g., 1600x1200 pixels) with optional padding between images.  
* **Web Server:**  
  * A lightweight web server will be responsible for serving the generated collage.  
  * A single endpoint (e.g., /collage.png) will trigger the collage generation process and return the resulting image.  
  * This allows the Inky Impression frame to easily fetch a new image over the network on a schedule.

### **3\. Technical Design**

* **Language:** Python 3.x  
* **Web Framework:** A lightweight framework such as **Flask** or **FastAPI** is recommended for its simplicity in creating a single-endpoint API.  
* **Image Processing:** The **Pillow** (PIL Fork) library will be used for all image manipulation tasks, including opening, resizing, cropping, and compositing images onto the final collage canvas.  
* **Configuration:** The configuration file will be in **YAML** format for human readability. The **PyYAML** library will be used to parse it.  
* **Application Structure:**  
  * main.py: The main entry point for the application. It will handle starting the web server and initializing the configuration.  
  * collage\_generator.py: A module containing the logic for finding photos and creating the collage.  
  * config.py: A module to handle loading, validating, and creating the default configuration file.  
  * photos/: An example directory containing a few placeholder images for initial testing.  
  * config.yaml: The user-editable configuration file.

### **4\. Configuration File Specification (config.yaml)**

\# \--- Photo Collage Generator Settings \---

\# Web server configuration  
server:  
  host: "0.0.0.0"  \# Host to bind the server to. 0.0.0.0 makes it accessible on the network.  
  port: 8000        \# Port for the web server.

\# Inky Impression display settings  
display:  
  width: 1600        \# The width of the display in pixels.  
  height: 1200       \# The height of the display in pixels.

\# Photo source and collage settings  
photos:  
  \# The path to the directory containing your photos.  
  \# Can be an absolute path (e.g., "C:/Users/YourUser/Pictures")  
  \# or a relative path (e.g., "./photos").  
  source\_directory: "./photos"

  \# The layout style for the collage.  
  \# Options: "grid", "golden\_ratio", "auto"  
  layout: "auto"

  \# The space in pixels between images in the collage.  
  padding: 10

  \# Whether to randomize the order of photos for each collage.  
  \# Options: true, false  
  randomize\_order: true

### **5\. API Endpoint**

* **URL:** http://\<server\_ip\>:\<port\>/collage.png  
* **Method:** GET  
* **Response:**  
  * **Success (200 OK):** The response body will contain the raw image data for the generated collage with a Content-Type of image/png.  
  * **Error (500 Internal Server Error):** If the photo directory is not found or no images are available, a server error will be returned with a descriptive message in the response body.
