/* custom_addons/cmms_3d_models/static/src/js/submodel_viewer.js */
odoo.define('cmms_3d_models.submodel_viewer', function (require) {
    "use strict";

    var core = require('web.core');
    var AbstractAction = require('web.AbstractAction');
    var ajax = require('web.ajax');

    var _t = core._t;

    // Fonction utilitaire pour charger dynamiquement un script JS
    function loadScript(url) {
        return new Promise(function(resolve, reject) {
            var script = document.createElement('script');
            script.src = url;
            script.onload = resolve;
            script.onerror = reject;
            document.head.appendChild(script);
        });
    }

    var SubModel3DViewer = AbstractAction.extend({
        template: 'CMMS3DSubmodelViewer',
        events: {
            'click .o_close_viewer': '_onCloseViewer',
        },

        init: function (parent, action) {
            this._super.apply(this, arguments);
            this.parentModelId = action.params.parent_id;
            this.submodelId = action.params.submodel_id;
            this.renderer = null;
            this.scene = null;
            this.camera = null;
            this.controls = null;
            this.model = null;
        },

        start: function () {
            var self = this;
            return this._super.apply(this, arguments).then(function () {
                // Charger les dépendances JS globales AVANT d'initialiser le viewer
                return Promise.all([
                    loadScript('/cmms_3d_models/static/lib/three/three.js'),
                    loadScript('/cmms_3d_models/static/lib/three/OrbitControls.js'),
                    loadScript('/cmms_3d_models/static/lib/three/GLTFLoader.js'),
                    loadScript('/cmms_3d_models/static/lib/three/DRACOLoader.js'),
                ]).then(function () {
                    self._setupViewer();
                }).catch(function(error) {
                    self._showError(_t("Erreur lors du chargement des dépendances 3D: ") + error.message);
                    console.error("Failed to load 3D dependencies:", error);
                });
            });
        },

        _setupViewer: function () {
            var self = this;
            var container = this.$el.find('.o_3d_container')[0];

            // Récupération des infos sur le sous-modèle
            ajax.jsonRpc('/web/cmms/submodel/' + this.parentModelId + '/' + this.submodelId + '/info', 'call', {})
                .then(function (data) {
                    self._initThree(container, data);
                })
                .fail(function (error) {
                    self._showError(_t("Erreur lors du chargement du sous-modèle 3D: ") + error.message);
                });
        },

        _initThree: function (container, data) {
            var self = this;
            var width = container.clientWidth;
            var height = container.clientHeight;

            // S'assurer que THREE existe dans le scope global
            if (typeof THREE === 'undefined') {
                this._showError(_t("Erreur: THREE.js n'est pas chargé correctement"));
                return;
            }

            // Mettre à jour le titre
            this.$el.find('.o_3d_viewer_title').text('Visualiseur 3D - ' + data.submodel.name);

            // Création de la scène
            this.scene = new THREE.Scene();
            this.scene.background = new THREE.Color(0xf0f0f0);

            // Création de la caméra
            this.camera = new THREE.PerspectiveCamera(75, width / height, 0.1, 1000);
            this.camera.position.z = 5;

            // Création du renderer
            try {
                this.renderer = new THREE.WebGLRenderer({ antialias: true });
                this.renderer.setSize(width, height);
                this.renderer.setPixelRatio(window.devicePixelRatio);
                this.renderer.outputColorSpace = THREE.SRGBColorSpace;
                container.appendChild(this.renderer.domElement);
            } catch (e) {
                this._showError(_t("Erreur lors de l'initialisation du renderer WebGL: ") + e.message);
                console.error("WebGL error:", e);
                return;
            }

            // Ajout des contrôles OrbitControls
            try {
                this.controls = new THREE.OrbitControls(this.camera, this.renderer.domElement);
                this.controls.enableDamping = true;
                this.controls.dampingFactor = 0.25;
                this.controls.screenSpacePanning = false;
                this.controls.maxPolarAngle = Math.PI / 2;
            } catch (e) {
                this._showError(_t("Erreur lors de l'initialisation des contrôles: ") + e.message);
                console.error("Controls error:", e);
                return;
            }

            // Ajout de lumières
            var ambientLight = new THREE.AmbientLight(0xffffff, 0.5);
            this.scene.add(ambientLight);

            var directionalLight = new THREE.DirectionalLight(0xffffff, 0.8);
            directionalLight.position.set(1, 1, 1);
            this.scene.add(directionalLight);

            // Chargement du sous-modèle 3D
            this._loadModel(data);

            // Animation
            var animate = function () {
                requestAnimationFrame(animate);
                if (self.controls) {
                    self.controls.update();
                }
                if (self.renderer && self.scene && self.camera) {
                    self.renderer.render(self.scene, self.camera);
                }
            };
            animate();

            // Gestion du redimensionnement
            window.addEventListener('resize', function () {
                if (!self.camera || !self.renderer) return;

                var width = container.clientWidth;
                var height = container.clientHeight;
                self.camera.aspect = width / height;
                self.camera.updateProjectionMatrix();
                self.renderer.setSize(width, height);
            });
        },

        _loadModel: function (data) {
            var self = this;
            var submodelData = data.submodel;

            // Vérifier que GLTFLoader existe
            if (typeof THREE.GLTFLoader === 'undefined') {
                this._showError(_t("Erreur: GLTFLoader n'est pas disponible"));
                return;
            }

            var loader = new THREE.GLTFLoader();

            // Configure DRACOLoader pour les modèles compressés si disponible
            if (typeof THREE.DRACOLoader !== 'undefined') {
                var dracoLoader = new THREE.DRACOLoader();
                dracoLoader.setDecoderPath('/cmms_3d_models/static/lib/three/draco/');
                loader.setDRACOLoader(dracoLoader);
            }

            // Ajout d'un indicateur de chargement
            this.$el.find('.o_3d_loading').removeClass('d-none');

            // URL du sous-modèle
            var modelUrl = submodelData.gltf_url;
            console.log("Chargement du sous-modèle:", modelUrl);

            loader.load(
                modelUrl,
                function (gltf) {
                    try {
                        self.model = gltf.scene;

                        // Application des transformations
                        self.model.scale.set(
                            submodelData.scale,
                            submodelData.scale,
                            submodelData.scale
                        );

                        self.model.position.set(
                            submodelData.position_x,
                            submodelData.position_y,
                            submodelData.position_z
                        );

                        self.model.rotation.set(
                            THREE.MathUtils.degToRad(submodelData.rotation_x),
                            THREE.MathUtils.degToRad(submodelData.rotation_y),
                            THREE.MathUtils.degToRad(submodelData.rotation_z)
                        );

                        // Ajout du modèle à la scène
                        self.scene.add(self.model);

                        // Centre la caméra sur le modèle
                        var box = new THREE.Box3().setFromObject(self.model);
                        var center = box.getCenter(new THREE.Vector3());
                        var size = box.getSize(new THREE.Vector3());

                        var maxDim = Math.max(size.x, size.y, size.z);
                        var fov = self.camera.fov * (Math.PI / 180);
                        var cameraZ = Math.abs(maxDim / 2 / Math.tan(fov / 2));

                        self.camera.position.z = center.z + cameraZ * 1.5;
                        self.controls.target.set(center.x, center.y, center.z);
                        self.controls.update();

                        // Masque l'indicateur de chargement
                        self.$el.find('.o_3d_loading').addClass('d-none');
                    } catch (e) {
                        self._showError(_t("Erreur lors du traitement du sous-modèle 3D: ") + e.message);
                        console.error("Model processing error:", e);
                    }
                },
                function (xhr) {
                    var percent = xhr.loaded / xhr.total * 100;
                    self.$el.find('.o_3d_loading_progress').text(Math.round(percent) + '%');
                },
                function (error) {
                    console.error('Error loading 3D model:', error);
                    self._showError(_t("Erreur lors du chargement du sous-modèle 3D: ") + error.message);
                }
            );
        },

        _showError: function (message) {
            this.$el.find('.o_3d_loading').addClass('d-none');
            this.$el.find('.o_3d_error')
                .removeClass('d-none')
                .find('.o_3d_error_message')
                .text(message);
        },

        _onCloseViewer: function () {
            this.destroy();
            this.trigger_up('history_back');
        },

        destroy: function () {
            // Nettoyage des ressources Three.js
            if (this.renderer) {
                this.renderer.dispose();
            }
            if (this.model) {
                this.scene.remove(this.model);
                this.model.traverse(function (child) {
                    if (child.geometry) {
                        child.geometry.dispose();
                    }
                    if (child.material) {
                        if (Array.isArray(child.material)) {
                            child.material.forEach(function (material) {
                                material.dispose();
                            });
                        } else {
                            child.material.dispose();
                        }
                    }
                });
            }
            this.model = null;
            this.scene = null;
            this.camera = null;
            this.controls = null;

            this._super.apply(this, arguments);
        }
    });

    core.action_registry.add('cmms_3d_submodel_viewer', SubModel3DViewer);

    return {
        SubModel3DViewer: SubModel3DViewer,
    };
});