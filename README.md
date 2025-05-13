# CMMS 3D Models Integration

## About the Project

This project is an Odoo addon module that adds 3D model visualization for maintenance equipment. The module allows importing, converting, and displaying 3D models directly within Odoo, providing a visual representation of maintenance assets.

## Key Features

- **Import** 3D models in various formats (glTF, GLB, Blender)
- **Automatic conversion** of Blender (`.blend`) files to glTF
- **Built-in 3D viewer** using Three.js
- **Link** 3D models to existing maintenance equipment records
- **Customize** display parameters (scale, position, rotation)
- **Support** for textures and external resources for realistic rendering

## Project Structure

```plaintext
cmms_internship/
├── blender_scripts/
│   └── blend_to_gltf.py       # Blender-to-glTF conversion script
├── custom_addons/
│   └── cmms_3d_models/        # Main Odoo addon module
│       ├── controllers/       # HTTP controllers
│       ├── models/            # Data models
│       ├── security/          # Access control rules
│       ├── static/            # Static assets (JS, CSS, libraries)
│       └── views/             # Odoo XML views
├── docker/                    # Docker setup (not used)
└── odoo.conf                  # Odoo configuration file
```  

## Technologies Used

- **Odoo**: Framework for maintenance management
- **Python**: Backend language
- **Blender**: Used for 3D model conversion
- **Three.js**: JavaScript library for 3D rendering
- **PostgreSQL**: Database
- **glTF/GLB**: Standard 3D model formats

## Installation & Configuration

1. Clone this repository into your Odoo addons directory:
   ```bash
   git clone <REPO_URL>
   ```
2. Install Blender 3.x or higher on the server.
3. Update the paths in `models/model3d.py` to match your environment:
   ```python
   MODELS_DIR = os.path.normpath(r"C:\Users\admin\Desktop\odoo\models")
   BLENDER_SCRIPT_PATH = os.path.normpath(r"C:\Users\admin\Desktop\odoo\blender_scripts\blend_to_gltf.py")
   BLENDER_EXE = r"C:\Program Files\Blender Foundation\Blender 4.4\blender.exe"
   ```
4. Install the module in Odoo via the Apps interface.

## Usage

1. In Odoo, navigate to **Maintenance > Configuration > 3D Models** to create a new 3D model record.
2. Upload a `.blend`, `.gltf`, or `.glb` file.
3. Link the 3D model record to a maintenance equipment record.
4. Click the **3D View** button on the equipment form to visualize the model.

## Technical Notes

- The `blend_to_gltf.py` script can be used standalone, outside of Odoo.
- Supported import formats:
  - Blender (`.blend`) files with automatic conversion
  - glTF/GLB files directly
  - ZIP archives containing the main model file and associated textures/resources
- The 3D viewer in the web client uses Three.js with `OrbitControls` for interactive navigation.
