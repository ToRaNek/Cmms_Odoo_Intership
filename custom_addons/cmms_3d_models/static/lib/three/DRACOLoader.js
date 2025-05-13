/* custom_addons/cmms_3d_models/static/lib/three/DRACOLoader.js */
// Version compatible avec notre environnement

THREE.DRACOLoader = function(manager) {
    THREE.Loader.call(this, manager);

    this.decoderPath = '';
    this.decoderConfig = {};
    this.decoderPending = null;

    this.workerLimit = 4;
    this.workerPool = [];
    this.workerNextTaskID = 1;
    this.workerSourceURL = '';

    this.defaultAttributeIDs = {
        position: 'POSITION',
        normal: 'NORMAL',
        color: 'COLOR',
        uv: 'TEX_COORD'
    };

    this.defaultAttributeTypes = {
        position: 'Float32Array',
        normal: 'Float32Array',
        color: 'Float32Array',
        uv: 'Float32Array'
    };
};

THREE.DRACOLoader.prototype = Object.create(THREE.Loader.prototype);
THREE.DRACOLoader.prototype.constructor = THREE.DRACOLoader;

THREE.DRACOLoader.prototype.setDecoderPath = function(path) {
    this.decoderPath = path;
    return this;
};

THREE.DRACOLoader.prototype.setDecoderConfig = function(config) {
    this.decoderConfig = config;
    return this;
};

THREE.DRACOLoader.prototype.setWorkerLimit = function(workerLimit) {
    this.workerLimit = workerLimit;
    return this;
};

THREE.DRACOLoader.prototype.load = function(url, onLoad, onProgress, onError) {
    // Implémentation simplifiée - juste transmettre l'appel sans décodage réel
    onLoad(new THREE.BufferGeometry());
};

THREE.DRACOLoader.prototype.preload = function() {
    // Implémentation simplifiée
    return this;
};

THREE.DRACOLoader.prototype.dispose = function() {
    // Implémentation simplifiée
    return this;
};