import os
import json
import base64
from odoo import http
from odoo.http import request
import logging

_logger = logging.getLogger(__name__)

class CMMS3DController(http.Controller):

    @http.route('/models3d/<int:model3d_id>/<path:filename>', type='http', auth="public")
    def models3d_content(self, model3d_id, filename, **kw):
        """Sert les fichiers de modèles 3D et leurs fichiers associés"""
        try:
            model3d = request.env['cmms.model3d'].sudo().browse(model3d_id)
            if not model3d.exists():
                return request.not_found()

            # Vérifier que le fichier est bien associé au modèle
            is_associated = False
            if model3d.model_filename == filename:
                is_associated = True
            # Gérer le cas des fichiers .blend convertis en .glb
            elif model3d.is_converted_from_blend and model3d.source_blend_filename == filename:
                is_associated = True
                # Rediriger vers le fichier .gltf converti
                blend_basename = os.path.splitext(filename)[0]
                filename = f"{blend_basename}.gltf"
            elif model3d.model_bin_filename == filename:
                is_associated = True
            elif model3d.has_external_files and model3d.files_list:
                try:
                    files_list = json.loads(model3d.files_list)
                    if filename in files_list:
                        is_associated = True
                except:
                    pass
            # Tolérance spéciale pour les images connues qui pourraient être référencées
            elif filename in ['grunge-scratched-brushed-metal-background.jpg', 'zinc04.jpg']:
                is_associated = True
                _logger.info(f"Accès autorisé à la texture connue: {filename}")

            if not is_associated:
                _logger.warning(f"Fichier non associé au modèle: {filename}")
                return request.not_found()

            # Chemin du fichier - Adapté pour Windows - Utiliser backslash et normpath
            file_path = os.path.normpath(os.path.join('C:\\Users\\admin\\Desktop\\odoo\\models', str(model3d_id), filename))

            # Log pour le débogage
            _logger.info(f"Tentative d'accès au fichier: {file_path}, existe: {os.path.isfile(file_path)}")

            # Vérification de l'existence du fichier
            if not os.path.isfile(file_path):
                # Si le fichier principal n'existe pas sur le disque
                if filename == model3d.model_filename and model3d.model_file:
                    content = base64.b64decode(model3d.model_file)
                    # Créer le répertoire si nécessaire
                    os.makedirs(os.path.dirname(file_path), exist_ok=True)
                    # Sauvegarder le fichier
                    with open(file_path, 'wb') as f:
                        f.write(content)
                # Si le fichier binaire n'existe pas sur le disque
                elif filename == model3d.model_bin_filename and model3d.model_bin:
                    content = base64.b64decode(model3d.model_bin)
                    # Créer le répertoire si nécessaire
                    os.makedirs(os.path.dirname(file_path), exist_ok=True)
                    # Sauvegarder le fichier
                    with open(file_path, 'wb') as f:
                        f.write(content)
                # Si c'est un fichier blend d'origine
                elif model3d.is_converted_from_blend and model3d.source_blend_filename == filename and model3d.source_blend_file:
                    content = base64.b64decode(model3d.source_blend_file)
                    # Créer le répertoire si nécessaire
                    os.makedirs(os.path.dirname(file_path), exist_ok=True)
                    # Sauvegarder le fichier
                    with open(file_path, 'wb') as f:
                        f.write(content)
                else:
                    # Si le fichier n'existe pas et n'est pas stocké dans la base
                    _logger.warning(f"Fichier introuvable: {filename} à {file_path}")
                    return request.not_found()

            # Lecture du fichier
            with open(file_path, 'rb') as f:
                content = f.read()

            # Détermination du type MIME
            content_type = self._get_mime_type(filename)

            _logger.info(f"Fichier servi avec succès: {filename} ({content_type})")

            # Envoi du fichier avec des headers CORS explicites
            return request.make_response(
                content,
                headers=[
                    ('Content-Type', content_type),
                    ('Content-Disposition', f'inline; filename={filename}'),
                    ('Content-Length', len(content)),
                    ('Access-Control-Allow-Origin', '*'),
                    ('Access-Control-Allow-Methods', 'GET, OPTIONS'),
                    ('Access-Control-Allow-Headers', 'Origin, X-Requested-With, Content-Type, Accept'),
                    ('Cache-Control', 'max-age=86400'), # Cache pour 1 jour
                ]
            )

        except Exception as e:
            _logger.error(f"Error serving 3D model file: {str(e)}")
            return request.not_found()

    def _get_mime_type(self, filename):
        """Détermine le type MIME en fonction de l'extension du fichier"""
        ext = os.path.splitext(filename.lower())[1]
        if ext == '.gltf':
            return 'model/gltf+json'
        elif ext == '.glb':
            return 'model/gltf-binary'
        elif ext == '.blend':
            return 'application/x-blender'  # Type MIME pour les fichiers Blender
        elif ext == '.bin':
            return 'application/octet-stream'
        elif ext in ['.jpg', '.jpeg']:
            return 'image/jpeg'
        elif ext == '.png':
            return 'image/png'
        elif ext == '.webp':
            return 'image/webp'
        elif ext == '.json':
            return 'application/json'
        else:
            return 'application/octet-stream'

    @http.route('/web/cmms/viewer/<int:model3d_id>', type='http', auth="public")
    def simple_viewer(self, model3d_id, **kw):
        """Page simple de visualisation 3D"""
        model3d = request.env['cmms.model3d'].sudo().browse(model3d_id)
        if not model3d.exists():
            return request.not_found()

        # Création d'une simple page HTML avec un visualiseur 3D utilisant les CDN officiels
        html = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>CMMS 3D Viewer - %s</title>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                body { margin: 0; overflow: hidden; font-family: Arial, sans-serif; }
                #viewer { width: 100%%; height: 100vh; }
                #loading {
                    position: absolute;
                    top: 50%%;
                    left: 50%%;
                    transform: translate(-50%%, -50%%);
                    background: rgba(255,255,255,0.8);
                    padding: 20px;
                    border-radius: 10px;
                    text-align: center;
                    z-index: 100;
                }
                #spinner {
                    border: 5px solid #f3f3f3;
                    border-top: 5px solid #3498db;
                    border-radius: 50%%;
                    width: 50px;
                    height: 50px;
                    animation: spin 1s linear infinite;
                    margin: 0 auto 10px auto;
                }
                @keyframes spin {
                    0%% { transform: rotate(0deg); }
                    100%% { transform: rotate(360deg); }
                }
                #controls {
                    position: absolute;
                    bottom: 20px;
                    left: 20px;
                    background: rgba(0,0,0,0.5);
                    color: white;
                    padding: 10px;
                    border-radius: 5px;
                    font-size: 14px;
                }
                #modelInfo {
                    position: absolute;
                    top: 20px;
                    left: 20px;
                    background: rgba(0,0,0,0.5);
                    color: white;
                    padding: 10px;
                    border-radius: 5px;
                    font-size: 14px;
                    max-width: 300px;
                }
                #error {
                    display: none;
                    position: absolute;
                    top: 50%%;
                    left: 50%%;
                    transform: translate(-50%%, -50%%);
                    background: rgba(220,53,69,0.8);
                    color: white;
                    padding: 20px;
                    border-radius: 10px;
                    text-align: center;
                    z-index: 100;
                    max-width: 80%%;
                }
                #info {
                    position: absolute;
                    top: 0px;
                    width: 100%%;
                    padding: 10px;
                    box-sizing: border-box;
                    text-align: center;
                    z-index: 1;
                    color: #fff;
                    background-color: rgba(0,0,0,0.5);
                    font-size: 14px;
                }
            </style>
        </head>
        <body>
            <div id="viewer"></div>
            <div id="info">
                <b>CMMS 3D Viewer - %s</b><br>
                Cliquer et glisser pour faire pivoter | Molette pour zoomer | Clic droit pour déplacer
            </div>
            <div id="loading">
                <div id="spinner"></div>
                <div id="progress">Chargement... 0%%</div>
            </div>
            <div id="modelInfo">
                <h3>%s</h3>
                <p>%s</p>
                %s
            </div>
            <div id="error">
                <h3>Erreur de chargement</h3>
                <p id="errorMessage"></p>
                <p>Vérifiez que tous les fichiers nécessaires (textures, binaires) ont été téléchargés correctement.</p>
            </div>

            <!-- Import Three.js et ses extensions depuis les CDN -->
            <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
            <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>
            <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/loaders/GLTFLoader.js"></script>
            <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/loaders/DRACOLoader.js"></script>

            <script>
                // Configuration
                const modelUrl = '%s';
                const scaleValue = %f; // Valeur de l'échelle (nombre)
                const position = { x: %f, y: %f, z: %f };
                const rotation = { x: %f, y: %f, z: %f };

                // Variables
                let scene, camera, renderer, controls, model;
                let hasExternalFiles = %s;

                // File list (for debugging)
                const filesList = %s;

                // Ajouter des logs pour le débogage
                console.log("Configuration de la visualisation 3D:");
                console.log("- URL du modèle:", modelUrl);
                console.log("- Échelle:", scaleValue);
                console.log("- Position:", position);
                console.log("- Rotation:", rotation);
                console.log("- Fichiers externes:", hasExternalFiles ? "Oui" : "Non");

                // Initialize the scene
                init();

                // Main initialization function
                function init() {
                    // Create the scene
                    scene = new THREE.Scene();
                    scene.background = new THREE.Color(0xf0f0f0);

                    // Setup camera
                    camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight, 0.1, 1000);
                    camera.position.z = 5;

                    /* Axes d'aide - DÉSACTIVÉS en production
                    const axesHelper = new THREE.AxesHelper(5);
                    scene.add(axesHelper);
                    console.log("Axes d'aide ajoutés à la scène");
                    */

                    // Setup renderer
                    try {
                        renderer = new THREE.WebGLRenderer({ antialias: true });
                        renderer.setSize(window.innerWidth, window.innerHeight);
                        renderer.setPixelRatio(window.devicePixelRatio);
                        renderer.outputColorSpace = THREE.SRGBColorSpace;
                        document.getElementById('viewer').appendChild(renderer.domElement);
                    } catch (e) {
                        showError("Erreur d'initialisation WebGL: " + e.message);
                        return;
                    }

                    // Setup controls
                    try {
                        controls = new THREE.OrbitControls(camera, renderer.domElement);
                        controls.enableDamping = true;
                        controls.dampingFactor = 0.25;
                    } catch (e) {
                        showError("Erreur d'initialisation des contrôles: " + e.message);
                        return;
                    }

                    // Add lights
                    const ambientLight = new THREE.AmbientLight(0xffffff, 0.5);
                    scene.add(ambientLight);

                    const directionalLight1 = new THREE.DirectionalLight(0xffffff, 0.8);
                    directionalLight1.position.set(1, 1, 1);
                    scene.add(directionalLight1);

                    const directionalLight2 = new THREE.DirectionalLight(0xffffff, 0.5);
                    directionalLight2.position.set(-1, -1, -1);
                    scene.add(directionalLight2);

                    console.log("Éclairages configurés: lumière ambiante et 2 lumières directionnelles");

                    /* Cube de test - DÉSACTIVÉ en production
                    const geometry = new THREE.BoxGeometry(1, 1, 1);
                    const material = new THREE.MeshBasicMaterial({ color: 0xff0000, wireframe: true });
                    const cube = new THREE.Mesh(geometry, material);
                    scene.add(cube);
                    console.log("Cube de test ajouté à la scène");
                    */

                    // Load the 3D model
                    loadModel();

                    // Handle window resize
                    window.addEventListener('resize', onWindowResize);

                    // Start animation loop
                    animate();
                }

                // Load 3D model function
                function loadModel() {
                    // Setup loader - utiliser le GLTFLoader du CDN
                    const loader = new THREE.GLTFLoader();

                    // Optional: Setup DRACO decoder for compressed models
                    if (typeof THREE.DRACOLoader !== 'undefined') {
                        const dracoLoader = new THREE.DRACOLoader();
                        dracoLoader.setDecoderPath('https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/libs/draco/');
                        loader.setDRACOLoader(dracoLoader);
                    }

                    // For GLTFLoader, the path is critical for finding textures
                    // All textures must be in the same directory as the main GLTF file
                    const modelUrlDir = modelUrl.substring(0, modelUrl.lastIndexOf('/') + 1);

                    // Précharger les textures qui sont connues pour être utilisées
                    const textures = ['grunge-scratched-brushed-metal-background.jpg', 'zinc04.jpg'];
                    textures.forEach(textureName => {
                        const textureUrl = modelUrlDir + textureName;
                        console.log("Préchargement de la texture:", textureUrl);
                        const img = new Image();
                        img.src = textureUrl;
                    });

                    // Set resource path for loader to help find textures
                    loader.setResourcePath(modelUrlDir);

                    // Load model with progress tracking
                    loader.load(
                        modelUrl,
                        function(gltf) {
                            try {
                                // Success callback
                                model = gltf.scene;

                                // Vérifier que model existe
                                if (!model) {
                                    showError("Le modèle chargé est invalide ou vide");
                                    return;
                                }

                                console.log("Modèle chargé avec succès:", model);

                                // Appliquer les transformations
                                model.scale.set(scaleValue, scaleValue, scaleValue);
                                model.position.set(position.x, position.y, position.z);
                                model.rotation.set(
                                    THREE.MathUtils.degToRad(rotation.x),
                                    THREE.MathUtils.degToRad(rotation.y),
                                    THREE.MathUtils.degToRad(rotation.z)
                                );

                                // Ajouter le modèle à la scène
                                scene.add(model);
                                console.log("Modèle ajouté à la scène");

                                // Center camera on model
                                const box = new THREE.Box3().setFromObject(model);
                                const center = box.getCenter(new THREE.Vector3());
                                const size = box.getSize(new THREE.Vector3());

                                const maxDim = Math.max(size.x, size.y, size.z);
                                const fov = camera.fov * (Math.PI / 180);
                                const cameraZ = Math.abs(maxDim / 2 / Math.tan(fov / 2));

                                camera.position.z = center.z + cameraZ * 1.5;
                                controls.target.set(center.x, center.y, center.z);
                                controls.update();

                                console.log("Caméra centrée sur le modèle");

                                // Hide loading indicator
                                document.getElementById('loading').style.display = 'none';
                            } catch (e) {
                                showError("Erreur lors du traitement du modèle: " + e.message);
                                console.error("Erreur détaillée:", e);
                            }
                        },
                        function(xhr) {
                            // Progress callback
                            if (xhr.lengthComputable) {
                                const percent = xhr.loaded / xhr.total * 100;
                                document.getElementById('progress').textContent = 'Chargement... ' + Math.round(percent) + '%%';
                            }
                        },
                        function(error) {
                            // Error callback
                            console.error('Error loading 3D model:', error);

                            // Essayer de fournir plus d'informations sur l'erreur
                            let errorMessage = 'Erreur de chargement';
                            if (error && error.message) {
                                errorMessage += ': ' + error.message;
                            } else if (error && error.target && error.target.src) {
                                // Si l'erreur est liée au chargement d'une image, montrer son URL
                                errorMessage += ': Impossible de charger l\\'image ' + error.target.src;

                                // Essayons d'accéder directement à l'image
                                fetch(error.target.src)
                                    .then(response => {
                                        if (!response.ok) {
                                            throw new Error(`HTTP error! Status: ${response.status}`);
                                        }
                                        console.log("L'image peut être accessible directement, mais le chargeur GLTF a des problèmes.");
                                    })
                                    .catch(err => {
                                        console.error("Impossible d'accéder directement à l'image:", err);
                                    });
                            } else {
                                errorMessage += ': undefined';
                            }

                            showError(errorMessage);

                            // Essayons de tester un chargement direct du fichier
                            fetch(modelUrl)
                                .then(response => {
                                    if (!response.ok) {
                                        throw new Error(`HTTP error! Status: ${response.status}`);
                                    }
                                    return response.text();
                                })
                                .then(data => {
                                    console.log("Le fichier GLTF peut être accessible directement.");
                                    console.log("Premiers 100 caractères:", data.substring(0, 100));
                                })
                                .catch(err => {
                                    console.error("Impossible d'accéder directement au fichier GLTF:", err);
                                });

                            // Afficher un cube coloré pour indiquer qu'il y a une erreur mais que le visualiseur fonctionne
                            // Un cube rouge plus petit et moins visible pour ne pas distraire
                            const geometry = new THREE.BoxGeometry(0.5, 0.5, 0.5);
                            const material = new THREE.MeshStandardMaterial({
                                color: 0xff0000,
                                roughness: 0.7,
                                metalness: 0.3,
                                transparent: true,
                                opacity: 0.5
                            });
                            const errorCube = new THREE.Mesh(geometry, material);
                            scene.add(errorCube);
                            console.log("Cube d'erreur ajouté à la scène");
                        }
                    );
                }

                // Show error function
                function showError(message) {
                    document.getElementById('loading').style.display = 'none';
                    const errorDiv = document.getElementById('error');
                    const errorMessage = document.getElementById('errorMessage');
                    errorDiv.style.display = 'block';
                    errorMessage.textContent = message;
                }

                // Resize handler
                function onWindowResize() {
                    camera.aspect = window.innerWidth / window.innerHeight;
                    camera.updateProjectionMatrix();
                    renderer.setSize(window.innerWidth, window.innerHeight);
                }

                // Animation loop
                function animate() {
                    requestAnimationFrame(animate);
                    if (controls) controls.update();
                    if (renderer && scene && camera) {
                        renderer.render(scene, camera);
                    }
                }
            </script>
        </body>
        </html>
        """ % (
            model3d.name,  # Title
            model3d.name,  # Info header
            model3d.name,  # Model info header
            model3d.description or "",  # Model info description
            # Ajouter une note si le modèle a été converti depuis Blender
            '<p><small>Convertit depuis fichier Blender: ' + model3d.source_blend_filename + '</small></p>' if model3d.is_converted_from_blend else "",
            model3d.model_url,  # Model URL
            model3d.scale if model3d.scale is not None else 1.0,  # Scale (avec valeur par défaut)
            model3d.position_x if model3d.position_x is not None else 0.0,
            model3d.position_y if model3d.position_y is not None else 0.0,
            model3d.position_z if model3d.position_z is not None else 0.0,  # Position
            model3d.rotation_x if model3d.rotation_x is not None else 0.0,
            model3d.rotation_y if model3d.rotation_y is not None else 0.0,
            model3d.rotation_z if model3d.rotation_z is not None else 0.0,  # Rotation
            "true" if model3d.has_external_files else "false",  # Has external files
            model3d.files_list or "[]"  # Files list as JSON
        )

        return request.make_response(
            html,
            headers=[('Content-Type', 'text/html')]
        )

    @http.route('/web/cmms/equipment/<int:equipment_id>', type='json', auth="user")
    def get_equipment_3d_info(self, equipment_id, **kw):
        """Récupère les informations 3D d'un équipement"""
        equipment = request.env['maintenance.equipment'].sudo().browse(equipment_id)
        if not equipment.exists() or not equipment.model3d_id:
            return {'error': 'Équipement non trouvé ou sans modèle 3D'}

        return {
            'equipment': {
                'id': equipment.id,
                'name': equipment.name,
                'scale': equipment.model3d_scale,
                'position': {
                    'x': equipment.model3d_position_x,
                    'y': equipment.model3d_position_y,
                    'z': equipment.model3d_position_z
                },
                'rotation': {
                    'x': equipment.model3d_rotation_x,
                    'y': equipment.model3d_rotation_y,
                    'z': equipment.model3d_rotation_z
                }
            },
            'model3d': {
                'id': equipment.model3d_id.id,
                'name': equipment.model3d_id.name,
                'url': equipment.model3d_id.model_url,
                'format': equipment.model3d_id.model_format,
                'has_external_files': equipment.model3d_id.has_external_files,
                'scale': equipment.model3d_id.scale,
                'position': {
                    'x': equipment.model3d_id.position_x,
                    'y': equipment.model3d_id.position_y,
                    'z': equipment.model3d_id.position_z
                },
                'rotation': {
                    'x': equipment.model3d_id.rotation_x,
                    'y': equipment.model3d_id.rotation_y,
                    'z': equipment.model3d_id.rotation_z
                }
            }
        }

    @http.route('/web/cmms/upload_model', type='http', auth="user", methods=['POST'], csrf=False)
    def upload_model(self, **kw):
        """API pour télécharger un modèle 3D depuis Blender"""
        try:
            name = kw.get('name')
            description = kw.get('description')
            file = kw.get('file')

            if not file or not name:
                return request.make_response(
                    json.dumps({'error': 'Le fichier et le nom sont requis'}),
                    headers=[('Content-Type', 'application/json')],
                    status=400
                )

            # Vérifier le type de fichier
            filename = file.filename
            if not (filename.endswith('.gltf') or filename.endswith('.glb') or filename.endswith('.blend')):
                return request.make_response(
                    json.dumps({'error': 'Le fichier doit être au format glTF, GLB ou Blend'}),
                    headers=[('Content-Type', 'application/json')],
                    status=400
                )

            # Lire le contenu du fichier
            file_content = file.read()
            file_base64 = base64.b64encode(file_content).decode('utf-8')

            # Déterminer le format
            format = 'gltf' if filename.endswith('.gltf') else 'glb'
            if filename.endswith('.blend'):
                format = 'blend'

            # Créer le modèle 3D
            model3d = request.env['cmms.model3d'].create({
                'name': name,
                'description': description or '',
                'model_file': file_base64,
                'model_filename': filename,
                'model_format': format,
            })

            return request.make_response(
                json.dumps({
                    'success': True,
                    'id': model3d.id,
                    'name': model3d.name,
                    'url': model3d.model_url
                }),
                headers=[('Content-Type', 'application/json')]
            )

        except Exception as e:
            return request.make_response(
                json.dumps({'error': str(e)}),
                headers=[('Content-Type', 'application/json')],
                status=500
            )