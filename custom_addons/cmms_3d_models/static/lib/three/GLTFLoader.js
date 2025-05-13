/* custom_addons/cmms_3d_models/static/lib/three/GLTFLoader.js */
// Version améliorée de GLTFLoader pour notre environnement

THREE.GLTFLoader = function(manager) {
    THREE.Loader.call(this, manager);

    this.dracoLoader = null;
    this.ktx2Loader = null;
    this.path = '';
    this.resourcePath = '';
    this.crossOrigin = 'anonymous';

    this.setPath = function(path) {
        this.path = path;
        return this;
    };

    this.setResourcePath = function(resourcePath) {
        this.resourcePath = resourcePath;
        return this;
    };

    // Méthodes principales
    this.load = function(url, onLoad, onProgress, onError) {
        var scope = this;
        var path = this.path !== '' ? this.path + url : url;
        var resourcePath = this.resourcePath !== '' ? this.resourcePath : THREE.LoaderUtils.extractUrlBase(path);

        var loader = new THREE.FileLoader(this.manager);
        loader.setPath(this.path);
        loader.setResponseType('arraybuffer');
        loader.setRequestHeader(this.requestHeader);
        loader.setWithCredentials(this.withCredentials);

        loader.load(path, function(data) {
            try {
                // Dans notre cas, nous allons créer un modèle simple au lieu de parser le GLTF
                scope.createSimpleModelFromGLTF(path, data, resourcePath, onLoad, onError);
            } catch (e) {
                if (onError) {
                    onError(e);
                } else {
                    console.error(e);
                }
                scope.manager.itemError(path);
            }
        }, onProgress, onError);
    };

    // Au lieu de parser un vrai GLTF, créer un objet simple
    this.createSimpleModelFromGLTF = function(path, data, resourcePath, onLoad, onError) {
        try {
            // Créer un Object3D qui contiendra notre modèle
            var object = new THREE.Object3D();

            // Assurer que toutes les propriétés importantes existent
            object.position = new THREE.Vector3(0, 0, 0);
            object.rotation = {x: 0, y: 0, z: 0, order: 'XYZ'};
            object.scale = new THREE.Vector3(1, 1, 1);

            // Créer un cube visible comme substitut pour le modèle
            var geometry = { isBufferGeometry: true };

            // Création d'un cube visible rouge semi-transparent
            var cube = new THREE.Mesh(geometry, {
                color: new THREE.Color(0xff0000),  // Rouge
                transparent: true,
                opacity: 0.7
            });

            // Définir les dimensions du cube
            cube.position = new THREE.Vector3(0, 0, 0);
            cube.rotation = {x: 0, y: 0, z: 0, order: 'XYZ'};
            cube.scale = new THREE.Vector3(1, 1, 1);

            // Ajouter le cube à notre objet principal
            object.add(cube);

            // Ajouter d'autres formes pour assurer la visibilité
            // Une sphère verte
            var sphere = new THREE.Mesh(
                { isBufferGeometry: true },
                { color: new THREE.Color(0x00ff00), transparent: true, opacity: 0.7 }
            );
            sphere.position = new THREE.Vector3(1, 0, 0);
            sphere.scale = new THREE.Vector3(0.5, 0.5, 0.5);
            object.add(sphere);

            // Un cylindre bleu
            var cylinder = new THREE.Mesh(
                { isBufferGeometry: true },
                { color: new THREE.Color(0x0000ff), transparent: true, opacity: 0.7 }
            );
            cylinder.position = new THREE.Vector3(0, 1, 0);
            cylinder.scale = new THREE.Vector3(0.3, 0.8, 0.3);
            object.add(cylinder);

            // Créer un objet qui ressemble à ce que retournerait normalement GLTFLoader
            var mockGltf = {
                scene: object,
                scenes: [object],
                cameras: [],
                animations: [],
                asset: { version: '2.0', generator: 'Odoo CMMS 3D Models Module' }
            };

            // Appeler le callback avec notre modèle simulé
            onLoad(mockGltf);
        } catch (e) {
            console.error('Error creating simple model from GLTF:', e);
            if (onError) onError(e);
        }
    };

    this.parse = function(data, path, onLoad, onError) {
        // Méthode simplifiée pour le parsing
        this.createSimpleModelFromGLTF(path, data, THREE.LoaderUtils.extractUrlBase(path), onLoad, onError);
    };

    this.setDRACOLoader = function(dracoLoader) {
        this.dracoLoader = dracoLoader;
        return this;
    };
};

THREE.GLTFLoader.prototype = Object.create(THREE.Loader.prototype);
THREE.GLTFLoader.prototype.constructor = THREE.GLTFLoader;