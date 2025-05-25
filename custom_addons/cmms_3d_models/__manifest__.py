{
    'name': 'CMMS 3D Models Integration',
    'version': '1.0',
    'category': 'Maintenance',
    'summary': 'Integration of 3D models (glTF) from Blender with CMMS and personnel management - Compatible Odoo 16',
    'description': """
CMMS 3D Models Integration with Personnel Management - Odoo 16 Compatible
=========================================================================
This module integrates 3D models in glTF format exported from Blender with the Maintenance module
and adds comprehensive personnel and role management for maintenance operations.

Corrections Odoo 16:
--------------------
* Fixed button_box inheritance issues
* Compatible with Odoo 16 maintenance module structure
* Optimized view inheritance for better stability

Features:
---------
* Import Blender models in glTF format
* Link maintenance equipment with 3D models
* Visualize equipment in 3D via direct URL
* Create maintenance personnel with automatic Odoo user creation
* Define maintenance roles (Technician, Supervisor, Manager, etc.)
* Assign specific users to maintenance requests
* Team management with personnel integration
* Select specific parts/sub-models for maintenance requests
* Define intervention types for each part (Cleaning, Repair, Replacement, etc.)
    """,
    'author': 'Your Company',
    'website': 'https://www.yourcompany.com',
    'depends': [
        'base',
        'web',
        'maintenance',
        'mail',  # Pour le chatter sur les personnes
        'contacts',  # Pour les partenaires
    ],
    'data': [
        'data/maintenance_role_data.xml',
        'security/ir.model.access.csv',
        'views/model3d_views.xml',
        'views/maintenance_views.xml',
        'views/submodel_views.xml',
        'views/maintenance_person_views.xml',
        'views/maintenance_request_views_parts.xml',  # Vue corrigée principale
        'views/maintenance_request_views_extended.xml',  # Vue simplifiée
        'views/maintenance_team_views_extended.xml',
        'views/maintenance_equipment_views_3d.xml',  # Vue corrigée
        'views/api_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'cmms_3d_models/static/src/js/model_viewer.js',
            'cmms_3d_models/static/src/js/submodel_viewer.js',
            'cmms_3d_models/static/src/css/model_viewer.css',
            # Three.js libraries
            'cmms_3d_models/static/lib/three/three.js',
            'cmms_3d_models/static/lib/three/OrbitControls.js',
            'cmms_3d_models/static/lib/three/GLTFLoader.js',
            'cmms_3d_models/static/lib/three/DRACOLoader.js',
        ],
        'web.assets_qweb': [
            'cmms_3d_models/static/src/xml/model_viewer_template.xml',
            'cmms_3d_models/static/src/xml/submodel_viewer_template.xml',
        ],
    },
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}