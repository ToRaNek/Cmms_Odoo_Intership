/* custom_addons/cmms_3d_models/static/lib/three/three.js */
// Version corrigée de la bibliothèque Three.js pour Odoo

// Définition de l'espace de noms global THREE
window.THREE = {
    // Constantes essentielles
    REVISION: '147',
    MOUSE: { LEFT: 0, MIDDLE: 1, RIGHT: 2 },
    TOUCH: { ROTATE: 0, PAN: 1, DOLLY_PAN: 2, DOLLY_ROTATE: 3 },

    // Classes principales
    Vector2: function(x, y) {
        this.x = x || 0;
        this.y = y || 0;

        this.set = function(x, y) {
            this.x = x;
            this.y = y;
            return this;
        };

        this.subVectors = function(a, b) {
            this.x = a.x - b.x;
            this.y = a.y - b.y;
            return this;
        };

        this.multiplyScalar = function(scalar) {
            this.x *= scalar;
            this.y *= scalar;
            return this;
        };
    },

    Vector3: function(x, y, z) {
        this.x = x || 0;
        this.y = y || 0;
        this.z = z || 0;

        this.set = function(x, y, z) {
            this.x = x;
            this.y = y;
            this.z = z;
            return this;
        };

        this.copy = function(v) {
            this.x = v.x;
            this.y = v.y;
            this.z = v.z;
            return this;
        };

        this.add = function(v) {
            this.x += v.x;
            this.y += v.y;
            this.z += v.z;
            return this;
        };

        // Méthode manquante qui était la cause de l'erreur
        this.addVectors = function(a, b) {
            this.x = a.x + b.x;
            this.y = a.y + b.y;
            this.z = a.z + b.z;
            return this;
        };

        this.sub = function(v) {
            this.x -= v.x;
            this.y -= v.y;
            this.z -= v.z;
            return this;
        };

        this.multiplyScalar = function(scalar) {
            this.x *= scalar;
            this.y *= scalar;
            this.z *= scalar;
            return this;
        };

        this.crossVectors = function(a, b) {
            var ax = a.x, ay = a.y, az = a.z;
            var bx = b.x, by = b.y, bz = b.z;

            this.x = ay * bz - az * by;
            this.y = az * bx - ax * bz;
            this.z = ax * by - ay * bx;

            return this;
        };

        this.applyQuaternion = function(q) {
            // Implementation simplifiée
            return this;
        };

        this.setFromSpherical = function(s) {
            // Implementation simplifiée
            var sinPhiRadius = Math.sin(s.phi) * s.radius;

            this.x = sinPhiRadius * Math.sin(s.theta);
            this.y = Math.cos(s.phi) * s.radius;
            this.z = sinPhiRadius * Math.cos(s.theta);

            return this;
        };

        this.distanceTo = function(v) {
            return Math.sqrt(this.distanceToSquared(v));
        };

        this.distanceToSquared = function(v) {
            var dx = this.x - v.x;
            var dy = this.y - v.y;
            var dz = this.z - v.z;

            return dx * dx + dy * dy + dz * dz;
        };

        // Ajouter la méthode length pour les calculs de Box3
        this.length = function() {
            return Math.sqrt(this.x * this.x + this.y * this.y + this.z * this.z);
        };
    },

    Euler: function(x, y, z, order) {
        this.x = x || 0;
        this.y = y || 0;
        this.z = z || 0;
        this.order = order || 'XYZ';

        this.set = function(x, y, z, order) {
            this.x = x;
            this.y = y;
            this.z = z;
            this.order = order || this.order;
            return this;
        };
    },

    Quaternion: function(x, y, z, w) {
        this.x = x || 0;
        this.y = y || 0;
        this.z = z || 0;
        this.w = (w !== undefined) ? w : 1;

        this.copy = function(q) {
            this.x = q.x;
            this.y = q.y;
            this.z = q.z;
            this.w = q.w;
            return this;
        };

        this.setFromUnitVectors = function(vFrom, vTo) {
            // Implementation simplifiée
            this.w = 1;
            this.x = 0;
            this.y = 0;
            this.z = 0;
            return this;
        };

        this.invert = function() {
            this.x *= -1;
            this.y *= -1;
            this.z *= -1;
            return this;
        };

        this.dot = function(v) {
            return this.x * v.x + this.y * v.y + this.z * v.z + this.w * v.w;
        };

        this.clone = function() {
            return new THREE.Quaternion(this.x, this.y, this.z, this.w);
        };
    },

    Matrix4: function() {
        this.elements = [
            1, 0, 0, 0,
            0, 1, 0, 0,
            0, 0, 1, 0,
            0, 0, 0, 1
        ];

        this.setFromMatrixColumn = function(matrix, index) {
            return this;
        };

        this.fromArray = function(array, offset) {
            // Implementation simplifiée
            return this;
        };
    },

    Spherical: function(radius, phi, theta) {
        this.radius = (radius !== undefined) ? radius : 1.0;
        this.phi = (phi !== undefined) ? phi : 0;
        this.theta = (theta !== undefined) ? theta : 0;

        this.set = function(radius, phi, theta) {
            this.radius = radius;
            this.phi = phi;
            this.theta = theta;
            return this;
        };

        this.setFromVector3 = function(vec3) {
            this.radius = vec3.length();
            if (this.radius === 0) {
                this.phi = 0;
                this.theta = 0;
            } else {
                this.phi = Math.acos(Math.min(Math.max(vec3.y / this.radius, -1), 1));
                this.theta = Math.atan2(vec3.x, vec3.z);
            }
            return this;
        };

        this.makeSafe = function() {
            this.phi = Math.max(0.000001, Math.min(Math.PI - 0.000001, this.phi));
            return this;
        };
    },

    Box3: function() {
        this.min = new THREE.Vector3(+Infinity, +Infinity, +Infinity);
        this.max = new THREE.Vector3(-Infinity, -Infinity, -Infinity);

        this.setFromObject = function(object) {
            // Implementation simplifiée - assurer un minimum fonctionnel
            if (object && object.position) {
                var pos = object.position;
                var size = 1;

                if (object.scale) {
                    size = Math.max(object.scale.x || 1, object.scale.y || 1, object.scale.z || 1);
                }

                this.min.set(pos.x - size, pos.y - size, pos.z - size);
                this.max.set(pos.x + size, pos.y + size, pos.z + size);
            }
            return this;
        };

        this.getCenter = function(target) {
            if (target === undefined) {
                console.warn('THREE.Box3: .getCenter() target is now required');
                target = new THREE.Vector3();
            }

            // Vérification explicite que target est bien un Vector3 et possède addVectors
            if (!target.addVectors && target instanceof THREE.Vector3) {
                // Si target est un Vector3 mais sans la méthode, on l'ajoute
                target.addVectors = function(a, b) {
                    this.x = a.x + b.x;
                    this.y = a.y + b.y;
                    this.z = a.z + b.z;
                    return this;
                };
            } else if (!target.addVectors) {
                // Si ce n'est pas un Vector3, on en crée un nouveau
                console.warn('THREE.Box3: target n\'est pas un Vector3 valide, création d\'un nouveau Vector3');
                var oldTarget = target;
                target = new THREE.Vector3();
                // On copie les propriétés si possible
                if (oldTarget.x !== undefined) {
                    target.x = oldTarget.x;
                    target.y = oldTarget.y;
                    target.z = oldTarget.z;
                }
            }

            // Implementation sure de getCenter
            if (this.min && this.max) {
                target.x = (this.min.x + this.max.x) * 0.5;
                target.y = (this.min.y + this.max.y) * 0.5;
                target.z = (this.min.z + this.max.z) * 0.5;
            } else {
                // Valeur par défaut si min/max ne sont pas définis
                target.set(0, 0, 0);
            }

            return target;
        };

        this.getSize = function(target) {
            if (target === undefined) {
                console.warn('THREE.Box3: .getSize() target is now required');
                target = new THREE.Vector3();
            }

            // Vérification similaire à getCenter
            if (!target.subVectors && target instanceof THREE.Vector3) {
                target.subVectors = function(a, b) {
                    this.x = a.x - b.x;
                    this.y = a.y - b.y;
                    this.z = a.z - b.z;
                    return this;
                };
            } else if (!target.subVectors) {
                console.warn('THREE.Box3: target n\'est pas un Vector3 valide, création d\'un nouveau Vector3');
                var oldTarget = target;
                target = new THREE.Vector3();
                if (oldTarget.x !== undefined) {
                    target.x = oldTarget.x;
                    target.y = oldTarget.y;
                    target.z = oldTarget.z;
                }
            }

            // Implementation sure de getSize
            if (this.min && this.max) {
                target.x = this.max.x - this.min.x;
                target.y = this.max.y - this.min.y;
                target.z = this.max.z - this.min.z;
            } else {
                // Valeur par défaut si min/max ne sont pas définis
                target.set(0, 0, 0);
            }

            return target;
        };
    },

    Sphere: function(center, radius) {
        this.center = (center !== undefined) ? center : new THREE.Vector3();
        this.radius = (radius !== undefined) ? radius : 0;
    },

    EventDispatcher: function() {
        var listeners = {};

        this.addEventListener = function(type, listener) {
            if (listeners[type] === undefined) {
                listeners[type] = [];
            }

            if (listeners[type].indexOf(listener) === -1) {
                listeners[type].push(listener);
            }
        };

        this.removeEventListener = function(type, listener) {
            if (listeners[type] !== undefined) {
                var index = listeners[type].indexOf(listener);

                if (index !== -1) {
                    listeners[type].splice(index, 1);
                }
            }
        };

        this.dispatchEvent = function(event) {
            var listenerArray = listeners[event.type];

            if (listenerArray !== undefined) {
                event.target = this;

                var array = listenerArray.slice(0);

                for (var i = 0, l = array.length; i < l; i++) {
                    array[i].call(this, event);
                }
            }
        };
    },

    // Scène et caméra
    Scene: function() {
        this.background = null;
        this.children = [];

        this.add = function(object) {
            if (arguments.length > 1) {
                for (var i = 0; i < arguments.length; i++) {
                    this.add(arguments[i]);
                }
                return this;
            }

            if (object === this) {
                console.error("THREE.Object3D.add: object can't be added as a child of itself.", object);
                return this;
            }

            this.children.push(object);
            object.parent = this;

            return this;
        };

        this.remove = function(object) {
            var index = this.children.indexOf(object);

            if (index !== -1) {
                this.children.splice(index, 1);
                object.parent = null;
            }

            return this;
        };
    },

    PerspectiveCamera: function(fov, aspect, near, far) {
        this.fov = fov || 50;
        this.aspect = aspect || 1;
        this.near = near || 0.1;
        this.far = far || 2000;
        this.position = new THREE.Vector3(0, 0, 0);
        this.quaternion = new THREE.Quaternion();
        this.up = new THREE.Vector3(0, 1, 0);
        this.isPerspectiveCamera = true;

        this.updateProjectionMatrix = function() {
            // Implementation simplifiée
        };

        this.lookAt = function(v) {
            // Implementation simplifiée
        };
    },

    // Renderer
    WebGLRenderer: function(parameters) {
        parameters = parameters || {};

        this.domElement = document.createElement('canvas');
        this.setSize = function(width, height) {
            this.domElement.width = width;
            this.domElement.height = height;
        };

        this.setPixelRatio = function(value) {
            // Implementation simplifiée
        };

        this.render = function(scene, camera) {
            // Implementation simplifiée
        };

        this.dispose = function() {
            // Implementation simplifiée
        };

        this.outputColorSpace = null;
    },

    // Lumières
    AmbientLight: function(color, intensity) {
        this.color = new THREE.Color(color || 0xffffff);
        this.intensity = intensity !== undefined ? intensity : 1;
    },

    DirectionalLight: function(color, intensity) {
        this.color = new THREE.Color(color || 0xffffff);
        this.intensity = intensity !== undefined ? intensity : 1;
        this.position = new THREE.Vector3(0, 1, 0);
        this.target = {
            position: new THREE.Vector3(0, 0, 0)
        };
    },

    // Couleur - Corrigée
    Color: function(r, g, b) {
        // Initialiser les valeurs par défaut
        this.r = 1;
        this.g = 1;
        this.b = 1;

        // Définir d'abord toutes les méthodes
        this.setHex = function(hex) {
            hex = Math.floor(hex);

            this.r = (hex >> 16 & 255) / 255;
            this.g = (hex >> 8 & 255) / 255;
            this.b = (hex & 255) / 255;

            return this;
        };

        this.set = function(value) {
            if (value && typeof value === 'object') {
                if (value.r !== undefined) {
                    this.r = value.r;
                    this.g = value.g;
                    this.b = value.b;
                }
            } else if (typeof value === 'number') {
                this.setHex(value);
            } else if (typeof value === 'string') {
                // Simplifié - traiter comme un entier hexadécimal si possible
                if (value.startsWith('#')) {
                    this.setHex(parseInt(value.substring(1), 16));
                } else if (value === 'white') {
                    this.r = this.g = this.b = 1;
                } else if (value === 'black') {
                    this.r = this.g = this.b = 0;
                } else {
                    // Couleurs de base
                    var basicColors = {
                        'red': 0xff0000,
                        'green': 0x00ff00,
                        'blue': 0x0000ff,
                        'yellow': 0xffff00,
                        'cyan': 0x00ffff,
                        'magenta': 0xff00ff,
                        'gray': 0x808080
                    };

                    if (basicColors[value]) {
                        this.setHex(basicColors[value]);
                    } else {
                        this.r = this.g = this.b = 1; // Par défaut: blanc
                    }
                }
            }

            return this;
        };

        this.fromArray = function(array, offset) {
            offset = offset || 0;

            this.r = array[offset];
            this.g = array[offset + 1];
            this.b = array[offset + 2];

            return this;
        };

        // Après avoir défini toutes les méthodes, maintenant initialiser la couleur
        if (r !== undefined) {
            // Si trois paramètres sont fournis, les traiter comme RGB
            if (g !== undefined && b !== undefined) {
                this.r = r;
                this.g = g;
                this.b = b;
            } else {
                // Sinon utiliser la méthode set
                this.set(r);
            }
        }
    },

    // Utilitaires
    MathUtils: {
        degToRad: function(degrees) {
            return degrees * Math.PI / 180;
        },
        radToDeg: function(radians) {
            return radians * 180 / Math.PI;
        }
    },

    // Chargeurs - Corrigés avec setPath et setResponseType
    FileLoader: function(manager) {
        this.manager = manager || { itemError: function() {} };
        this.path = '';
        this.responseType = '';
        this.withCredentials = false;

        this.setPath = function(path) {
            this.path = path;
            return this;
        };

        this.setResponseType = function(responseType) {
            this.responseType = responseType;
            return this;
        };

        this.setWithCredentials = function(value) {
            this.withCredentials = value;
            return this;
        };

        this.load = function(url, onLoad, onProgress, onError) {
            var self = this;
            var fullUrl = this.path !== '' ? this.path + url : url;

            var request = new XMLHttpRequest();
            request.open('GET', fullUrl, true);

            if (this.responseType) {
                request.responseType = this.responseType;
            }

            if (this.withCredentials) {
                request.withCredentials = this.withCredentials;
            }

            request.addEventListener('load', function(event) {
                if (onLoad) onLoad(request.response);
            });

            request.addEventListener('error', function(event) {
                if (onError) onError(event);
                if (self.manager) self.manager.itemError(fullUrl);
            });

            request.addEventListener('progress', function(event) {
                if (onProgress) onProgress(event);
            });

            request.send(null);

            return request;
        };
    },

    TextureLoader: function(manager) {
        this.manager = manager || { itemError: function() {} };
        this.path = '';

        this.setPath = function(path) {
            this.path = path;
            return this;
        };

        this.load = function(url, onLoad, onProgress, onError) {
            var texture = new THREE.Texture();
            var fullUrl = this.path !== '' ? this.path + url : url;

            var loader = new THREE.ImageLoader();
            loader.setPath(this.path);

            loader.load(url, function(image) {
                texture.image = image;
                texture.needsUpdate = true;

                if (onLoad) onLoad(texture);
            }, onProgress, onError);

            return texture;
        };
    },

    ImageLoader: function(manager) {
        this.manager = manager || { itemError: function() {} };
        this.path = '';

        this.setPath = function(path) {
            this.path = path;
            return this;
        };

        this.load = function(url, onLoad, onProgress, onError) {
            var self = this;
            var fullUrl = this.path !== '' ? this.path + url : url;

            var image = new Image();

            image.addEventListener('load', function() {
                if (onLoad) onLoad(image);
            });

            image.addEventListener('error', function(event) {
                if (onError) onError(event);
                if (self.manager) self.manager.itemError(fullUrl);
            });

            image.src = fullUrl;
            return image;
        };
    },

    Texture: function(image) {
        this.image = image;
        this.needsUpdate = false;
        this.flipY = true;
        this.encoding = 0; // LinearEncoding
        this.name = '';
    },

    // Mesh et géométrie
    Mesh: function(geometry, material) {
        this.geometry = geometry || {};
        this.material = material || {};
        this.position = new THREE.Vector3();
        this.rotation = new THREE.Euler(0, 0, 0, 'XYZ');
        this.scale = new THREE.Vector3(1, 1, 1);
        this.parent = null;

        this.add = function(child) {
            child.parent = this;
            return this;
        };

        this.remove = function(child) {
            child.parent = null;
            return this;
        };
    },

    Object3D: function() {
        this.position = new THREE.Vector3();
        this.rotation = new THREE.Euler(0, 0, 0, 'XYZ');
        this.scale = new THREE.Vector3(1, 1, 1);
        this.parent = null;
        this.children = [];

        this.add = function(child) {
            if (child === this) {
                console.error("THREE.Object3D.add: object can't be added as a child of itself.");
                return this;
            }

            this.children.push(child);
            child.parent = this;
            return this;
        };

        this.remove = function(child) {
            const index = this.children.indexOf(child);
            if (index !== -1) {
                this.children.splice(index, 1);
                child.parent = null;
            }
            return this;
        };

        this.traverse = function(callback) {
            callback(this);
            const children = this.children;
            for (let i = 0, l = children.length; i < l; i++) {
                children[i].traverse(callback);
            }
        };
    },

    // Auxiliaires
    GridHelper: function(size, divisions) {
        this.size = size;
        this.divisions = divisions;
    },

    LoaderUtils: {
        extractUrlBase: function(url) {
            var index = url.lastIndexOf('/');
            return index === -1 ? './' : url.substr(0, index + 1);
        },

        decodeText: function(array) {
            if (typeof TextDecoder !== 'undefined') {
                return new TextDecoder().decode(array);
            }

            // Fallback pour les navigateurs plus anciens
            var s = '';

            for (var i = 0, il = array.length; i < il; i++) {
                s += String.fromCharCode(array[i]);
            }

            return s;
        }
    }
};

// Ajouter SRGBColorSpace pour la compatibilité
THREE.SRGBColorSpace = 'srgb';

// Exporter explicitement les classes principales
window.THREE.Loader = function(manager) {
    this.manager = manager || {
        itemError: function() {},
        getHandler: function() {}
    };
    this.path = '';

    this.setPath = function(path) {
        this.path = path;
        return this;
    };
};

// S'assurer que Euler est accessible depuis l'extérieur
window.THREE.Euler = THREE.Euler;

// Faire hériter Object3D de EventDispatcher
THREE.Object3D.prototype = Object.create(THREE.EventDispatcher.prototype);
THREE.Object3D.prototype.constructor = THREE.Object3D;

// Helper function pour OrbitControls
window.THREE.OrbitControls = {};