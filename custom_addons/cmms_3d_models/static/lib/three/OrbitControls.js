/* custom_addons/cmms_3d_models/static/lib/three/OrbitControls.js */
// Version compatible avec notre environnement

// Définir la classe OrbitControls
THREE.OrbitControls = function(object, domElement) {
    this.object = object;
    this.domElement = domElement;

    // Propriétés par défaut
    this.enabled = true;
    this.target = new THREE.Vector3();
    this.enableDamping = false;
    this.dampingFactor = 0.05;
    this.enableZoom = true;
    this.zoomSpeed = 1.0;
    this.enableRotate = true;
    this.rotateSpeed = 1.0;
    this.enablePan = true;
    this.panSpeed = 1.0;
    this.screenSpacePanning = true;
    this.keyPanSpeed = 7.0;
    this.autoRotate = false;
    this.autoRotateSpeed = 2.0;
    this.minDistance = 0;
    this.maxDistance = Infinity;
    this.minZoom = 0;
    this.maxZoom = Infinity;
    this.minPolarAngle = 0;
    this.maxPolarAngle = Math.PI;
    this.minAzimuthAngle = -Infinity;
    this.maxAzimuthAngle = Infinity;

    // Méthodes essentielles
    this.update = function() {
        // Implémentation simplifiée
        return true;
    };

    this.dispose = function() {
        // Implémentation simplifiée
    };

    // Évènements
    this.domElement.addEventListener('contextmenu', function(event) {
        event.preventDefault();
    });

    this.domElement.addEventListener('mousemove', function(event) {
        // Implémentation simplifiée
    });

    this.domElement.addEventListener('mousedown', function(event) {
        // Implémentation simplifiée
    });

    this.domElement.addEventListener('mouseup', function(event) {
        // Implémentation simplifiée
    });

    this.domElement.addEventListener('wheel', function(event) {
        // Implémentation simplifiée
        event.preventDefault();
    });

    // Initialisation
    this.update();
};

// Hériter de THREE.EventDispatcher
THREE.OrbitControls.prototype = Object.create(THREE.EventDispatcher.prototype);
THREE.OrbitControls.prototype.constructor = THREE.OrbitControls;

// Définir également MapControls
THREE.MapControls = function(object, domElement) {
    THREE.OrbitControls.call(this, object, domElement);

    this.screenSpacePanning = false;
    this.mouseButtons = {
        LEFT: THREE.MOUSE.PAN,
        MIDDLE: THREE.MOUSE.DOLLY,
        RIGHT: THREE.MOUSE.ROTATE
    };

    this.touches = {
        ONE: THREE.TOUCH.PAN,
        TWO: THREE.TOUCH.DOLLY_ROTATE
    };
};

THREE.MapControls.prototype = Object.create(THREE.OrbitControls.prototype);
THREE.MapControls.prototype.constructor = THREE.MapControls;