import os
import json
import base64
from odoo import http
from odoo.http import request
import logging

_logger = logging.getLogger(__name__)

# Importer le chemin des modèles depuis model3d.py
from ..models.model3d import MODELS_DIR

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
            # Amélioration: autoriser tous les fichiers .bin et fichiers image
            elif filename.endswith(('.bin', '.jpg', '.jpeg', '.png', '.webp')):
                is_associated = True
                _logger.info(f"Accès autorisé à la ressource: {filename}")

            if not is_associated:
                _logger.warning(f"Fichier non associé au modèle: {filename}")
                return request.not_found()

            # Chemin du fichier - Adapté pour Windows - Utiliser backslash et normpath
            file_path = os.path.normpath(os.path.join(MODELS_DIR, str(model3d_id), filename))

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

    @http.route('/models3d/<int:model3d_id>/childs/<int:submodel_id>/<path:filename>', type='http', auth="public")
    def models3d_child_content(self, model3d_id, submodel_id, filename, **kw):
        """Sert les fichiers de sous-modèles avec la nouvelle structure"""
        try:
            _logger.info(f"Requête pour sous-modèle: model_id={model3d_id}, submodel_id={submodel_id}, filename={filename}")

            # Vérifier que le parent existe
            parent_model = request.env['cmms.model3d'].sudo().browse(model3d_id)
            if not parent_model.exists():
                _logger.error(f"Modèle parent {model3d_id} non trouvé")
                return request.not_found()

            # Vérifier d'abord la nouvelle structure JSON
            if parent_model.submodels_json:
                try:
                    submodels = json.loads(parent_model.submodels_json)
                    submodel = next((sm for sm in submodels if sm.get('id') == submodel_id), None)

                    if submodel:
                        _logger.info(f"Sous-modèle trouvé dans JSON: {submodel['name']}")

                        # Chemin du fichier pour la structure basée sur l'arborescence des sous-dossiers
                        file_path = os.path.normpath(os.path.join(
                            MODELS_DIR, str(model3d_id), 'childs', str(submodel_id), filename
                        ))

                        # Si le fichier n'existe pas, essayer dans le dossier racine du modèle parent
                        if not os.path.isfile(file_path):
                            alt_file_path = os.path.normpath(os.path.join(
                                MODELS_DIR, str(model3d_id), filename
                            ))
                            if os.path.isfile(alt_file_path):
                                file_path = alt_file_path

                        _logger.info(f"Chemin du fichier: {file_path}, existe: {os.path.isfile(file_path)}")

                        # Vérifier si le fichier existe
                        if os.path.isfile(file_path):
                            # Lecture du fichier
                            with open(file_path, 'rb') as f:
                                content = f.read()

                            # Détermination du type MIME
                            content_type = self._get_mime_type(filename)

                            _logger.info(f"Fichier sous-modèle servi avec succès: {filename} ({content_type})")

                            # Envoi du fichier
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
                        else:
                            _logger.warning(f"Fichier sous-modèle introuvable: {file_path}")
                    else:
                        _logger.warning(f"Sous-modèle ID {submodel_id} non trouvé dans JSON")
                except Exception as e:
                    _logger.error(f"Erreur lors de l'accès au sous-modèle JSON: {str(e)}")

            # Si on arrive ici, on vérifie l'ancien système de child_ids
            _logger.info("Recherche du sous-modèle dans l'ancien système")
            child_model = request.env['cmms.model3d'].sudo().browse(submodel_id)
            if not child_model.exists():
                _logger.error(f"Sous-modèle {submodel_id} non trouvé dans l'ancien système")
                return request.not_found()

            if child_model.parent_id.id != model3d_id:
                _logger.error(f"Le sous-modèle {submodel_id} n'appartient pas au parent {model3d_id}")
                return request.not_found()

            # Chercher le fichier dans le dossier du sous-modèle lui-même (ancien système)
            file_path = os.path.normpath(os.path.join(MODELS_DIR, str(submodel_id), filename))

            _logger.info(f"Chemin du fichier ancien système: {file_path}, existe: {os.path.isfile(file_path)}")

            # Si le fichier n'existe pas, vérifier si le fichier est stocké dans la base de données
            if not os.path.isfile(file_path):
                if filename == child_model.model_filename and child_model.model_file:
                    content = base64.b64decode(child_model.model_file)
                    # Créer les répertoires si nécessaire
                    os.makedirs(os.path.dirname(file_path), exist_ok=True)
                    # Sauvegarder le fichier
                    with open(file_path, 'wb') as f:
                        f.write(content)
                elif filename == child_model.model_bin_filename and child_model.model_bin:
                    content = base64.b64decode(child_model.model_bin)
                    # Créer les répertoires si nécessaire
                    os.makedirs(os.path.dirname(file_path), exist_ok=True)
                    # Sauvegarder le fichier
                    with open(file_path, 'wb') as f:
                        f.write(content)
                else:
                    _logger.warning(f"Fichier sous-modèle introuvable: {filename} à {file_path}")
                    return request.not_found()

            # Lecture du fichier
            with open(file_path, 'rb') as f:
                content = f.read()

            # Détermination du type MIME
            content_type = self._get_mime_type(filename)

            _logger.info(f"Fichier sous-modèle servi avec succès: {filename} ({content_type})")

            # Envoi du fichier
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
            _logger.error(f"Error serving submodel file: {str(e)}")
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

        # Vérifier si on doit inclure les enfants
        include_children = bool(kw.get('include_children'))

        # Préparer les données pour tous les modèles à afficher
        models_data = []

        # Toujours inclure le modèle principal
        models_data.append({
            'id': model3d.id,
            'name': model3d.name,
            'url': model3d.model_url,
            'scale': model3d.scale if model3d.scale is not None else 1.0,
            'position': {
                'x': model3d.position_x if model3d.position_x is not None else 0.0,
                'y': model3d.position_y if model3d.position_y is not None else 0.0,
                'z': model3d.position_z if model3d.position_z is not None else 0.0,
            },
            'rotation': {
                'x': model3d.rotation_x if model3d.rotation_x is not None else 0.0,
                'y': model3d.rotation_y if model3d.rotation_y is not None else 0.0,
                'z': model3d.rotation_z if model3d.rotation_z is not None else 0.0,
            },
            'is_child': False,
            'parent_id': model3d.parent_id.id if model3d.parent_id else False,
        })

        # Ajouter les sous-modèles si demandé
        if include_children:
            # Pour l'ancien système
            def add_legacy_children(parent):
                for child in parent.child_ids:
                    # Construire l'URL correcte pour l'ancien système
                    child_url = None
                    if child.model_url:
                        # Utiliser l'URL du modèle directement - peut causer des problèmes
                        child_url = child.model_url
                    else:
                        # Construire une URL basée sur le parent (plus fiable)
                        child_name = child.model_filename or f"{child.name}.gltf"
                        child_url = f"/models3d/{parent.id}/childs/{child.id}/{child_name}"

                    # Vérifier si ce sous-modèle n'est pas déjà inclu (cas de double définition)
                    if not any(m.get('id') == child.id for m in models_data):
                        models_data.append({
                            'id': child.id,
                            'name': child.name,
                            'url': child_url,
                            'scale': child.scale if child.scale is not None else 1.0,
                            'position': {
                                'x': child.position_x if child.position_x is not None else 0.0,
                                'y': child.position_y if child.position_y is not None else 0.0,
                                'z': child.position_z if child.position_z is not None else 0.0,
                            },
                            'rotation': {
                                'x': child.rotation_x if child.rotation_x is not None else 0.0,
                                'y': child.rotation_y if child.rotation_y is not None else 0.0,
                                'z': child.rotation_z if child.rotation_z is not None else 0.0,
                            },
                            'is_child': True,
                            'parent_id': parent.id,
                            'legacy': True  # Marquer comme ancien système
                        })
                    # Récursion pour les enfants des enfants
                    add_legacy_children(child)

            # D'abord, ajouter les sous-modèles en JSON si disponibles
            if model3d.submodels_json:
                try:
                    submodels_json = json.loads(model3d.submodels_json)
                    for submodel in submodels_json:
                        # Construire l'URL correcte pour chaque sous-modèle
                        gltf_path = submodel.get('gltf_path', '')
                        if gltf_path:
                            basename = os.path.basename(gltf_path)
                            submodel_url = f"/models3d/{model3d.id}/childs/{submodel.get('id')}/{basename}"

                            # Ajouter le sous-modèle à la liste
                            models_data.append({
                                'id': submodel.get('id'),
                                'name': submodel.get('name', 'Sous-modèle'),
                                'url': submodel_url,
                                'scale': submodel.get('scale', 1.0),
                                'position': {
                                    'x': submodel.get('position', {}).get('x', 0.0),
                                    'y': submodel.get('position', {}).get('y', 0.0),
                                    'z': submodel.get('position', {}).get('z', 0.0)
                                },
                                'rotation': {
                                    'x': submodel.get('rotation', {}).get('x', 0.0),
                                    'y': submodel.get('rotation', {}).get('y', 0.0),
                                    'z': submodel.get('rotation', {}).get('z', 0.0)
                                },
                                'is_child': True,
                                'parent_id': model3d.id,
                                'json': True  # Marquer comme nouveau système JSON
                            })
                except Exception as e:
                    _logger.error(f"Erreur lors du traitement des sous-modèles JSON: {str(e)}")

            # Ensuite, ajouter les sous-modèles de l'ancien système
            add_legacy_children(model3d)

        # Passer les données des modèles au template
        models_json = json.dumps(models_data)

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
                #debug {
                    position: absolute;
                    bottom: 10px;
                    right: 10px;
                    background: rgba(0,0,0,0.5);
                    color: white;
                    padding: 10px;
                    border-radius: 5px;
                    font-size: 12px;
                    max-width: 300px;
                    max-height: 150px;
                    overflow: auto;
                    z-index: 100;
                }

                /* Nouveau style pour le sélecteur de sous-modèles */
                #submodelSelector {
                    position: absolute;
                    top: 50px;
                    right: 20px;
                    background: rgba(0,0,0,0.7);
                    color: white;
                    padding: 10px;
                    border-radius: 5px;
                    z-index: 100;
                    max-width: 200px;
                    overflow-y: auto;
                    max-height: 80vh;
                }
                .submodel-item {
                    padding: 5px;
                    cursor: pointer;
                    border-bottom: 1px solid rgba(255,255,255,0.2);
                }
                .submodel-item:hover {
                    background: rgba(255,255,255,0.1);
                }
                .submodel-item.active {
                    background: rgba(0,150,255,0.3);
                    font-weight: bold;
                }
                .child-model {
                    padding-left: 15px;
                    font-size: 0.9em;
                }
            </style>
        </head>
        <body>
            <div id="viewer"></div>
            <div id="info">
                <b>CMMS 3D Viewer - <span id="currentModelName">%s</span></b><br>
                Cliquer et glisser pour faire pivoter | Molette pour zoomer | Clic droit pour déplacer
            </div>

            <!-- Sélecteur de sous-modèles si on a des enfants -->
            <div id="submodelSelector" style="%s">
                <h4>Modèles</h4>
                <div id="modelList"></div>
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
            <div id="debug"></div>

            <!-- Import Three.js et ses extensions depuis les CDN -->
            <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
            <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>
            <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/loaders/GLTFLoader.js"></script>
            <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/loaders/DRACOLoader.js"></script>

            <script>
                // Debug log helper
                function debugLog(message) {
                    const debugEl = document.getElementById('debug');
                    const entry = document.createElement('div');
                    entry.textContent = message;
                    debugEl.appendChild(entry);

                    // Scroll to bottom
                    debugEl.scrollTop = debugEl.scrollHeight;

                    // Limit entries
                    while (debugEl.children.length > 20) {
                        debugEl.removeChild(debugEl.firstChild);
                    }

                    console.log(message);
                }

                // Données des modèles
                const modelsData = %s;
                debugLog(`Modèles chargés: ${modelsData.length}`);

                // Log modèle principal
                if (modelsData.length > 0) {
                    debugLog(`Modèle principal: ${modelsData[0].name}, URL: ${modelsData[0].url}`);
                }

                // Log sous-modèles
                if (modelsData.length > 1) {
                    debugLog(`Nombre de sous-modèles: ${modelsData.length - 1}`);
                    for (let i = 1; i < Math.min(5, modelsData.length); i++) {
                        debugLog(`Sous-modèle #${i}: ${modelsData[i].name}, URL: ${modelsData[i].url}`);
                    }
                    if (modelsData.length > 5) {
                        debugLog(`... et ${modelsData.length - 5} autres sous-modèles`);
                    }
                }

                // Variables pour Three.js
                let scene, camera, renderer, controls;
                let loadedModels = {}; // Stocke les modèles chargés par ID

                // Initialiser la scène
                init();

                // Fonction d'initialisation principale
                function init() {
                    // Créer la scène
                    scene = new THREE.Scene();
                    scene.background = new THREE.Color(0xf0f0f0);

                    // Setup caméra
                    const container = document.getElementById('viewer');
                    const width = container.clientWidth;
                    const height = container.clientHeight;
                    camera = new THREE.PerspectiveCamera(75, width / height, 0.1, 1000);
                    camera.position.z = 5;

                    // Setup renderer
                    try {
                        renderer = new THREE.WebGLRenderer({ antialias: true });
                        renderer.setSize(width, height);
                        renderer.setPixelRatio(window.devicePixelRatio);
                        renderer.outputColorSpace = THREE.SRGBColorSpace;
                        container.appendChild(renderer.domElement);
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

                    // Ajouter des lumières
                    const ambientLight = new THREE.AmbientLight(0xffffff, 0.5);
                    scene.add(ambientLight);

                    const directionalLight1 = new THREE.DirectionalLight(0xffffff, 0.8);
                    directionalLight1.position.set(1, 1, 1);
                    scene.add(directionalLight1);

                    const directionalLight2 = new THREE.DirectionalLight(0xffffff, 0.5);
                    directionalLight2.position.set(-1, -1, -1);
                    scene.add(directionalLight2);

                    // Charger les modèles
                    if (modelsData.length > 0) {
                        // Toujours charger le modèle principal en premier
                        loadModel(modelsData[0], function() {
                            // Après chargement du modèle principal, charger les sous-modèles si présents
                            if (modelsData.length > 1) {
                                for (let i = 1; i < modelsData.length; i++) {
                                    loadModel(modelsData[i]);
                                }
                            }
                        });

                        // Remplir le sélecteur de modèles
                        populateModelSelector();
                    }

                    // Animation
                    animate();

                    // Gestion du redimensionnement
                    window.addEventListener('resize', onWindowResize);
                }

                // Fonction pour charger un modèle
                function loadModel(modelData, callback) {
                    const loader = new THREE.GLTFLoader();

                    // Setup DRACO decoder for compressed models
                    if (typeof THREE.DRACOLoader !== 'undefined') {
                        const dracoLoader = new THREE.DRACOLoader();
                        dracoLoader.setDecoderPath('https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/libs/draco/');
                        loader.setDRACOLoader(dracoLoader);
                    }

                    // Ajouter un indicateur de chargement
                    document.getElementById('loading').style.display = 'block';

                    debugLog(`Chargement du modèle: ${modelData.name} (${modelData.url})`);

                    // For GLTFLoader, the path is critical for finding textures
                    // All textures must be in the same directory as the main GLTF file
                    const modelUrlDir = modelData.url.substring(0, modelData.url.lastIndexOf('/') + 1);
                    debugLog(`Répertoire de ressources: ${modelUrlDir}`);

                    // Set resource path for loader to help find textures
                    loader.setResourcePath(modelUrlDir);

                    loader.load(
                        modelData.url,
                        function (gltf) {
                            try {
                                debugLog(`Modèle chargé avec succès: ${modelData.name}`);
                                const model = gltf.scene;

                                // Appliquer les transformations
                                model.scale.set(
                                    modelData.scale,
                                    modelData.scale,
                                    modelData.scale
                                );

                                model.position.set(
                                    modelData.position.x,
                                    modelData.position.y,
                                    modelData.position.z
                                );

                                model.rotation.set(
                                    THREE.MathUtils.degToRad(modelData.rotation.x),
                                    THREE.MathUtils.degToRad(modelData.rotation.y),
                                    THREE.MathUtils.degToRad(modelData.rotation.z)
                                );

                                // Ajouter une propriété pour l'identifier
                                model.userData.modelId = modelData.id;
                                model.userData.modelName = modelData.name;

                                // Ajouter le modèle à la scène
                                scene.add(model);

                                // Stocker le modèle par ID
                                loadedModels[modelData.id] = model;

                                // Si c'est le modèle principal (premier de la liste)
                                if (modelData.id === modelsData[0].id) {
                                    // Centre la caméra sur le modèle
                                    centerCameraOnModel(model);

                                    // Masque l'indicateur de chargement
                                    document.getElementById('loading').style.display = 'none';

                                    // Appeler le callback si fourni
                                    if (callback) callback();
                                }
                            } catch (e) {
                                showError("Erreur lors du traitement du modèle 3D: " + e.message);
                                debugLog(`Erreur lors du traitement du modèle: ${e.message}`);
                                console.error("Model processing error:", e);
                            }
                        },
                        function (xhr) {
                            const percent = xhr.loaded / xhr.total * 100;
                            document.getElementById('progress').textContent = 'Chargement... ' + Math.round(percent) + '%%';
                        },
                        function (error) {
                            console.error('Error loading 3D model:', error);
                            debugLog(`Erreur de chargement: ${error.message}`);
                            showError("Erreur lors du chargement du modèle 3D: " + error.message);
                        }
                    );
                }

                // Centrer la caméra sur un modèle
                function centerCameraOnModel(model) {
                    const box = new THREE.Box3().setFromObject(model);
                    const center = box.getCenter(new THREE.Vector3());
                    const size = box.getSize(new THREE.Vector3());

                    const maxDim = Math.max(size.x, size.y, size.z);
                    const fov = camera.fov * (Math.PI / 180);
                    const cameraZ = Math.abs(maxDim / 2 / Math.tan(fov / 2));

                    camera.position.z = center.z + cameraZ * 1.5;
                    controls.target.set(center.x, center.y, center.z);
                    controls.update();
                }

                // Fonction pour afficher/masquer un modèle spécifique
                function toggleModel(modelId, visible = true) {
                    // Mettre à jour l'interface
                    document.querySelectorAll('.submodel-item').forEach(item => {
                        if (parseInt(item.dataset.id) === modelId) {
                            if (visible) {
                                item.classList.add('active');
                            } else {
                                item.classList.remove('active');
                            }
                        }
                    });

                    // Mettre à jour le modèle 3D
                    if (loadedModels[modelId]) {
                        loadedModels[modelId].visible = visible;

                        // Si on active un modèle, mettre à jour le nom affiché
                        if (visible) {
                            const modelName = loadedModels[modelId].userData.modelName;
                            document.getElementById('currentModelName').textContent = modelName;

                            // Centrer la caméra sur ce modèle
                            centerCameraOnModel(loadedModels[modelId]);
                        }
                    }
                }

                // Fonction pour afficher uniquement un modèle spécifique
                function showOnlyModel(modelId) {
                    // Masquer tous les modèles
                    Object.keys(loadedModels).forEach(id => {
                        loadedModels[id].visible = false;
                    });

                    // Afficher uniquement le modèle sélectionné
                    if (loadedModels[modelId]) {
                        loadedModels[modelId].visible = true;
                    }

                    // Mettre à jour l'interface
                    document.querySelectorAll('.submodel-item').forEach(item => {
                        if (parseInt(item.dataset.id) === modelId) {
                            item.classList.add('active');
                        } else {
                            item.classList.remove('active');
                        }
                    });

                    // Mettre à jour le nom affiché
                    const modelName = loadedModels[modelId].userData.modelName;
                    document.getElementById('currentModelName').textContent = modelName;

                    // Centrer la caméra sur ce modèle
                    centerCameraOnModel(loadedModels[modelId]);
                }

                // Fonction pour afficher tous les modèles
                function showAllModels() {
                    Object.keys(loadedModels).forEach(id => {
                        loadedModels[id].visible = true;
                    });

                    // Mettre à jour l'interface
                    document.querySelectorAll('.submodel-item').forEach(item => {
                        item.classList.add('active');
                    });

                    // Mettre à jour le nom affiché
                    document.getElementById('currentModelName').textContent = "Tous les modèles";

                    // Recalculer la vue pour englober tous les modèles
                    const allObjects = new THREE.Group();
                    Object.values(loadedModels).forEach(model => {
                        allObjects.add(model.clone());
                    });
                    centerCameraOnModel(allObjects);
                }

                // Fonction pour remplir le sélecteur de modèles
                function populateModelSelector() {
                    const modelList = document.getElementById('modelList');

                    // Ajouter une option pour tout afficher
                    if (modelsData.length > 1) {
                        const allItem = document.createElement('div');
                        allItem.classList.add('submodel-item', 'active');
                        allItem.textContent = "Tous les modèles";
                        allItem.addEventListener('click', function() {
                            showAllModels();
                        });
                        modelList.appendChild(allItem);
                    }

                    // Fonction récursive pour ajouter les modèles avec indentation
                    function addModelToList(model, level = 0) {
                        const item = document.createElement('div');
                        item.classList.add('submodel-item', 'active');
                        if (level > 0) {
                            item.classList.add('child-model');
                        }
                        item.textContent = model.name;
                        item.dataset.id = model.id;
                        item.style.paddingLeft = (5 + level * 15) + 'px';

                        item.addEventListener('click', function() {
                            showOnlyModel(parseInt(this.dataset.id));
                        });

                        modelList.appendChild(item);

                        // Ajouter les enfants de ce modèle
                        const children = modelsData.filter(m => m.parent_id === model.id);
                        children.forEach(child => {
                            addModelToList(child, level + 1);
                        });
                    }

                    // Commencer par le modèle principal
                    const rootModels = modelsData.filter(m => !m.parent_id);
                    rootModels.forEach(model => {
                        addModelToList(model);
                    });
                }

                // Fonctions standard de Three.js
                function animate() {
                    requestAnimationFrame(animate);
                    if (controls) controls.update();
                    if (renderer && scene && camera) {
                        renderer.render(scene, camera);
                    }
                }

                function onWindowResize() {
                    const container = document.getElementById('viewer');
                    const width = container.clientWidth;
                    const height = container.clientHeight;

                    camera.aspect = width / height;
                    camera.updateProjectionMatrix();
                    renderer.setSize(width, height);
                }

                function showError(message) {
                    document.getElementById('loading').style.display = 'none';
                    const errorDiv = document.getElementById('error');
                    const errorMessage = document.getElementById('errorMessage');
                    errorDiv.style.display = 'block';
                    errorMessage.textContent = message;
                }
            </script>
        </body>
        </html>
        """ % (
            model3d.name,  # Title
            model3d.name,  # Current model name display
            "display: " + ("block" if include_children or model3d.child_ids else "none"),  # Afficher le sélecteur uniquement s'il y a des enfants
            model3d.name,  # Model info header
            model3d.description or "",  # Model info description
            # Ajouter une note si le modèle a été converti depuis Blender
            '<p><small>Convertit depuis fichier Blender: ' + model3d.source_blend_filename + '</small></p>' if model3d.is_converted_from_blend else "",
            models_json  # Données des modèles en JSON
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

    @http.route('/web/cmms/submodels/<int:model3d_id>', type='json', auth="user")
    def get_model_submodels(self, model3d_id, **kw):
        """Récupère les sous-modèles d'un modèle 3D"""
        model = request.env['cmms.model3d'].sudo().browse(model3d_id)
        if not model.exists() or not model.submodels_json:
            return []

        try:
            submodels = json.loads(model.submodels_json)
            return submodels
        except json.JSONDecodeError:
            _logger.error(f"Erreur de décodage JSON pour le modèle {model3d_id}")
            return []