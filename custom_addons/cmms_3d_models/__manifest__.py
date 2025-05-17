{
    'name': 'CMMS 3D Models Integration',
    'version': '1.0',
    'category': 'Maintenance',
    'summary': 'Integration of 3D models (glTF) from Blender with CMMS',
    'description': """
CMMS 3D Models Integration
=========================
This module integrates 3D models in glTF format exported from Blender with the Maintenance module.

Features:
---------
* Import Blender models in glTF format
* Link maintenance equipment with 3D models
* Visualize equipment in 3D via direct URL
    """,
    'author': 'Your Company',
    'website': 'https://www.yourcompany.com',
    'depends': [
        'base',
        'web',
        'maintenance',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/model3d_views.xml',
        'views/maintenance_views.xml',
        'views/submodel_views.xml',
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
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}