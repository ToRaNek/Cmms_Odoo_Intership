# CMMS 3D Models Integration

An advanced Odoo 16 module for maintenance management (CMMS) with complete 3D models integration, BIM data, and REST API.

![Odoo Version](https://img.shields.io/badge/Odoo-16.0-blue)
![Python](https://img.shields.io/badge/Python-3.8+-green)
![License](https://img.shields.io/badge/License-LGPL--3-yellow)

## 🎯 Overview

This module transforms your Odoo maintenance system into an interactive 3D platform allowing you to:
- **Visualize your equipment in 3D** directly within Odoo
- **Import Blender, glTF and GLB models** with automatic conversion
- **Manage BIM/IFC data** for technical maintenance
- **Assign tasks precisely** to specific equipment parts
- **Connect external applications** via REST API (Flutter Web supported)

## ✨ Key Features

### 🔧 3D Equipment Management
- **Multi-format import**: Blender (.blend), glTF (.gltf), GLB (.glb)
- **Automatic conversion** from Blender files to glTF
- **Integrated 3D viewer** with Three.js and OrbitControls
- **Texture support** and external resources
- **Sub-model hierarchy** with automatic extraction

### 🏗️ BIM/IFC Support
- **IFC file import** (Industry Foundation Classes)
- **Automatic detection** of IFC versions (2x3, 4, 4.1, 4.3)
- **Technical BIM data storage**
- **Direct download** of IFC files from interface

### 👥 Advanced Personnel Management
- **Hierarchical maintenance roles** (Technician L1-L3, Team Leader, Supervisor, Manager)
- **Automatic Odoo user creation** (with or without email)
- **Multiple assignments** on maintenance requests
- **Team management** and specializations

### 🔩 Part-Based Maintenance
- **Specific part selection** based on 3D sub-models
- **Configurable intervention types** (Cleaning, Repair, Replacement, etc.)
- **Required fields** for equipment, responsible person, and scheduled date
- **Complete intervention history**

### 🌐 Complete REST API
- **Basic Auth authentication** or API keys
- **CORS support** optimized for Flutter Web
- **Complete endpoints** for requests, equipment, personnel
- **Multiple assignments management**
- **Centralized dashboard** in a single call

## 🗂️ Project Structure

```
cmms_internship/
├── 📁 blender_scripts/           # Blender conversion scripts
│   ├── blend_to_gltf.py         # Blender → glTF conversion
│   └── extract_gltf_nodes.py    # Sub-model extraction
├── 📁 custom_addons/
│   └── 📁 cmms_3d_models/       # Main Odoo addon module
│       ├── 📁 controllers/      # HTTP controllers & REST API
│       │   ├── main.py          # 3D model serving & viewer
│       │   └── api_rest.py      # REST API for Flutter/external apps
│       ├── 📁 models/           # Data models
│       │   ├── model3d.py       # 3D models with IFC support
│       │   ├── submodel3d.py    # Sub-models management
│       │   ├── maintenance_*.py # Extended maintenance models
│       │   └── api_access_log.py# API security & logging
│       ├── 📁 security/         # Access control rules
│       ├── 📁 static/           # Static assets
│       │   ├── 📁 lib/three/    # Three.js library
│       │   ├── 📁 src/js/       # JavaScript viewers
│       │   └── 📁 src/css/      # Stylesheets
│       ├── 📁 views/            # Odoo XML views
│       └── 📁 data/             # Default data (roles, etc.)
├── 📁 docker/                   # Docker setup (optional)
└── odoo.conf                    # Odoo configuration file
```

## 🚀 Installation & Setup

### Prerequisites

- **Odoo 16** installed and running
- **Python 3.8+**
- **Blender 3.0+** installed on server (for .blend conversion)
- **PostgreSQL** database

### Step 1: Clone the Repository

```bash
git clone <REPO_URL> cmms_internship
cd cmms_internship
```

### Step 2: Configure Paths

Update the paths in `custom_addons/cmms_3d_models/models/model3d.py`:

```python
# Windows paths (adapt to your environment)
MODELS_DIR = os.path.normpath(r"C:\Users\admin\Desktop\odoo\models")
BLENDER_SCRIPT_PATH = os.path.normpath(r"C:\Users\admin\Desktop\odoo\blender_scripts\blend_to_gltf.py")
BLENDER_EXE = r"C:\Program Files\Blender Foundation\Blender 4.4\blender.exe"
```

### Step 3: Configure Odoo

Update your `odoo.conf`:

```ini
[options]
addons_path = /path/to/odoo/addons,/path/to/cmms_internship/custom_addons
# ... other configurations
```

### Step 4: Install the Module

1. Start Odoo
2. Go to **Apps** menu
3. Update the Apps list
4. Search for "CMMS 3D Models Integration"
5. Click **Install**

## 📖 Usage Guide

### 🎨 Importing 3D Models

#### Option 1: Blender Files (.blend)
1. Go to **Maintenance > Configuration > 3D Models**
2. Create a new record
3. Upload your `.blend` file
4. The system automatically converts it to glTF format
5. Sub-models are extracted automatically

#### Option 2: glTF/GLB Files
1. Upload `.gltf` or `.glb` files directly
2. For glTF with external files, use ZIP upload
3. Include all textures and `.bin` files in the ZIP

#### Option 3: BIM/IFC Integration
1. Upload your 3D model (any format)
2. Add the corresponding IFC file in the "IFC BIM" section
3. IFC version is detected automatically
4. Technical data is available for download

### 🔧 Equipment Management

#### Automatic Equipment Creation
1. When creating a 3D model, select an **Equipment Category**
2. An equipment record is automatically created and linked
3. The equipment inherits 3D model properties (scale, position, rotation)

#### Manual Equipment Linking
1. Go to **Maintenance > Equipment**
2. Edit an existing equipment
3. Select a 3D model in the "3D Model" field
4. Configure display parameters if needed

### 👷 Personnel Management

#### Creating Maintenance Personnel
1. Go to **Maintenance > Configuration > Personnel**
2. Create a new person with:
    - First name and last name (required)
    - Role (required)
    - Email (optional for Odoo user creation)
3. Click **Create User** to generate an Odoo account

#### Managing Roles
1. Go to **Maintenance > Configuration > Roles**
2. Default roles are created automatically:
    - Technician Level 1-3
    - Team Leader
    - Supervisor
    - Manager
    - Operator
    - Quality Manager

### 🔩 Advanced Maintenance Requests

#### Part-Specific Maintenance
1. Create a maintenance request
2. Select an equipment with a 3D model
3. In the "Specific Parts" section:
    - Choose the exact parts requiring intervention
    - Select intervention type (Cleaning, Repair, etc.)
    - Add problem description

#### Multiple Assignments
1. In the "Assignments" section of a request
2. Add multiple personnel to the same request
3. Mark primary assignees
4. Track assignment history and notes

### 🌐 REST API Integration

#### Authentication Setup
1. Go to **Maintenance > Configuration > API Management > API Keys**
2. Create an API key for your application
3. Configure rate limits and allowed IPs

#### Basic Authentication
```bash
# Get maintenance requests
curl -X GET "http://your-odoo.com/api/flutter/maintenance/requests" \
  -H "Authorization: Basic base64(username:password)" \
  -H "Content-Type: application/json"
```

#### Available Endpoints
- `GET /api/flutter/maintenance/requests` - List requests
- `POST /api/flutter/maintenance/requests` - Create request
- `PUT /api/flutter/maintenance/requests/{id}` - Update request
- `GET /api/flutter/maintenance/equipment` - List equipment
- `GET /api/flutter/maintenance/equipment/{id}` - Get equipment details
- `GET /api/flutter/user/profile` - Get user profile
- `GET /api/flutter/maintenance/dashboard` - Get dashboard data

## 🔧 Technical Details

### 3D Model Processing

#### Blender to glTF Conversion
```python
# Automatic conversion pipeline
def _convert_and_save_blend_file(self, record):
    # 1. Save original .blend file
    # 2. Execute Blender in background mode
    # 3. Convert to glTF with textures
    # 4. Extract sub-models hierarchy
    # 5. Update database records
```

#### Sub-model Extraction
- Uses Blender scripting to extract individual nodes
- Creates separate glTF files for each sub-model
- Maintains hierarchy and transformation data
- Generates equipment records for each part

### IFC/BIM Integration

#### Supported Formats
- `.ifc` - Standard IFC format
- `.ifcxml` - XML-based IFC
- `.ifczip` - Compressed IFC archives

#### Version Detection
```python
def _analyze_ifc_file(self, record):
    # Reads IFC header to detect version
    # Supports IFC 2x3, 4, 4.1, 4.3
    # Extracts metadata and file size
```

### API Architecture

#### CORS Configuration
- Optimized for Flutter Web applications
- Supports credentials and custom headers
- Pre-flight request handling

#### Response Format
```json
{
  "success": true,
  "message": "Operation completed successfully",
  "data": { /* response data */ },
  "timestamp": "2024-01-01T12:00:00Z"
}
```

## 🔒 Security Features

### API Security
- **Basic Authentication** support
- **API Key management** with rate limiting
- **IP restrictions** per API key
- **Request logging** and monitoring
- **CORS protection** with origin validation

### Access Control
- **Role-based permissions** for maintenance personnel
- **Equipment access control** based on teams
- **Request visibility** limited to assigned users
- **Hierarchical role system** with inheritance

## 🏗️ Architecture Decisions

### File Storage Strategy
- **3D models**: Stored as binary fields with disk caching
- **Sub-models**: Individual files in structured directories
- **IFC files**: Separate storage with metadata extraction
- **Textures**: ZIP archive extraction to disk

### Database Design
- **Hierarchical models**: Parent-child relationships
- **Flexible assignments**: Many-to-many personnel assignments
- **Audit trails**: Complete change tracking
- **Performance**: Indexed fields for fast queries

### 3D Rendering
- **Three.js**: Client-side 3D rendering
- **OrbitControls**: Interactive navigation
- **Lazy loading**: Models loaded on demand
- **Error handling**: Graceful fallbacks for unsupported formats

## 🔍 Troubleshooting

### Common Issues

#### Blender Conversion Fails
```bash
# Check Blender installation
blender --version

# Check script permissions
ls -la blender_scripts/blend_to_gltf.py

# View conversion logs
tail -f models/blender_debug.log
```

#### 3D Models Not Displaying
1. Check browser console for Three.js errors
2. Verify model file accessibility via URL
3. Ensure CORS headers are properly set
4. Check file format compatibility

#### API Authentication Issues
1. Verify Basic Auth encoding: `base64(username:password)`
2. Check API key validity and expiration
3. Confirm IP address is in allowed list
4. Review CORS configuration for Flutter Web

### File Path Issues (Windows)
```python
# Use raw strings and normpath for Windows compatibility
MODELS_DIR = os.path.normpath(r"C:\Path\To\Models")
BLENDER_EXE = r"C:\Program Files\Blender Foundation\Blender 4.4\blender.exe"
```

### Performance Optimization
- **Model size**: Keep 3D models under 50MB for optimal loading
- **Texture resolution**: Use appropriate resolution for web display
- **Sub-models**: Limit to essential parts only
- **Database**: Regular maintenance and indexing

## 🧪 Testing

### API Testing with Postman
```json
{
  "name": "CMMS API Tests",
  "requests": [
    {
      "name": "Get Requests",
      "method": "GET",
      "url": "{{base_url}}/api/flutter/maintenance/requests",
      "headers": {
        "Authorization": "Basic {{auth_token}}",
        "Content-Type": "application/json"
      }
    }
  ]
}
```

### 3D Model Testing
1. **Test different formats**: .blend, .gltf, .glb
2. **Verify conversion**: Check generated files
3. **Test sub-models**: Ensure proper extraction
4. **Validate viewer**: Test in different browsers

## 🔄 Upgrade Guide

### From Previous Versions
1. **Backup database** before upgrading
2. **Update file paths** in configuration
3. **Restart Odoo** with module upgrade
4. **Test API endpoints** for compatibility
5. **Verify 3D model display** functionality

## 🤝 Contributing

### Development Setup
```bash
# Clone repository
git clone <repo-url>

# Install development dependencies
pip install -r requirements-dev.txt

# Set up pre-commit hooks
pre-commit install
```

### Code Standards
- **Python**: Follow PEP 8 guidelines
- **JavaScript**: Use ESLint configuration
- **XML**: Proper indentation and structure
- **Documentation**: Update README for new features

## 📋 Roadmap

### Planned Features
- [ ] **AR/VR support** for immersive maintenance
- [ ] **IoT sensor integration** for real-time data
- [ ] **Predictive maintenance** using AI/ML
- [ ] **Mobile app** with offline capabilities
- [ ] **Advanced BIM analytics** and reporting
- [ ] **Multi-language support** for international teams

### Version History
- **v1.0** - Initial release with basic 3D integration
- **v1.1** - Added IFC/BIM support and API enhancements
- **v1.2** - Personnel management and multiple assignments
- **Current** - Part-based maintenance and Flutter Web support

## 📄 License

This project is licensed under the **LGPL-3.0 License** - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- **Odoo Community** for the excellent framework
- **Three.js** for 3D rendering capabilities
- **Blender Foundation** for the powerful 3D creation suite
- **BuildingSMART** for IFC standards
- **Open Source Community** for continuous inspiration

## 📞 Support

For support, please:
1. Check the [troubleshooting section](#-troubleshooting)
2. Review the [documentation](#-usage-guide)
3. Open an issue on GitHub
4. Contact the development team

---

**Made with ❤️ for the maintenance community**