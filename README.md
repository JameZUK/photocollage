# **Photo Collage Generator for E-Ink Displays**

A Python-based web server that dynamically generates beautiful photo collages, perfectly sized for e-ink displays like the Inky Impression. The application scans a directory of your photos, intelligently arranges them into a visually appealing layout, and serves the final image via a simple web endpoint.  
It's designed to run continuously in a Docker container, making it easy to set up a personal digital photo frame that always shows fresh content.

## **Features**

* **Dynamic Collage Generation**: Automatically creates new collages on each request.  
* **Multiple Layouts**: Supports grid and golden\_ratio layouts, with an auto mode that intelligently selects the best one based on your photos.  
* **Thematic Collages**: Has a configurable chance to pull all photos from a single sub-folder, creating collages from the same day or event.  
* **Smart & Efficient**: Pre-resizes images for fast layout calculations but uses original files for final high-quality output. Automatically corrects image orientation based on EXIF data.  
* **Highly Configurable**: All settings are managed in a simple config.yaml file, which is auto-created on first run.  
* **Dockerized**: Comes with docker-compose.yml for easy, one-command setup and deployment.  
* **Wide Image Support**: Works with .jpg, .png, and Apple's .heic photo formats.

## **Requirements**

* [Docker](https://docs.docker.com/get-docker/)  
* [Docker Compose](https://docs.docker.com/compose/install/)

## **Setup & Installation**

1. **Clone the Repository**  
   git clone \<your-repository-url\>  
   cd photo-collage-generator

2. Create Initial Configuration  
   Run the configuration script once locally. This will create the necessary config.yaml file and the photos directory.  
   python3 config.py

3. Add Your Photos  
   Copy your photo collection into the newly created photos directory. You can organize them into sub-folders (e.g., by date or event), and the script will scan them recursively.  
4. Build and Run the Docker Container  
   This command will build the Docker image and start the web server in the background.  
   docker-compose up \--build \-d

   The \-d flag runs the container in detached mode. To view the logs, you can run docker-compose logs \-f.

## **Configuration**

All application settings are controlled via the config.yaml file.  
\# Web server configuration  
server:  
  host: "0.0.0.0"  \# Leave as 0.0.0.0 to be accessible on your network  
  port: 8000        \# The port the server will run on

\# Display/output image settings  
display:  
  width: 1600       \# Final collage width in pixels  
  height: 1200      \# Final collage height in pixels

\# Photo source and collage settings  
photos:  
  \# Path to your photo library within the container  
  source\_directory: "./photos"

  \# Collage layout style: "grid", "golden\_ratio", or "auto"  
  layout: "auto"

  \# Space between images in pixels  
  padding: 10

  \# Shuffle image order for each collage  
  randomize\_order: true

  \# Max size for temporary images used during layout calculation (performance)  
  max\_image\_size: 800

  \# The target number of images to include in a collage  
  max\_images\_per\_collage: 20

  \# Percentage chance (0-100) to pull all photos from a single sub-folder  
  same\_folder\_percentage: 25

## **Usage**

Once the server is running, you can access your collage from any device on your network.

* **Web Interface**: Open http://\<server\_ip\>:8000 in your browser for instructions.  
* **Collage Endpoint**: The latest collage is always available at http://\<server\_ip\>:8000/collage.png.

Your Inky Impression display or any other digital frame can be pointed to this URL to fetch a new image. Simply refreshing the page will generate a new collage.

## **Project Structure**

.  
├── collage\_generator.py    \# Core logic for creating collage layouts.  
├── config.py               \# Handles loading and creating config.yaml.  
├── main.py                 \# The Flask web server entry point.  
├── Dockerfile              \# Instructions for building the Docker image.  
├── docker-compose.yml      \# Defines the Docker service.  
├── requirements.txt        \# Python package dependencies.  
└── photos/                 \# Directory for your image library (mounted as a volume).  
