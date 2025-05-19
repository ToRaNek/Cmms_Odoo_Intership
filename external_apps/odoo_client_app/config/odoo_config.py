# external_apps/odoo_client_app/config/odoo_config.py
"""
Configuration pour la connexion à Odoo
Modifiez ces valeurs selon votre environnement
"""

# Configuration principale Odoo
ODOO_CONFIG = {
    'url': 'http://localhost:8069',    # URL de votre instance Odoo
    'db': 'odoo_cmms',                 # Nom de votre base de données
    'username': 'admin',               # Nom d'utilisateur Odoo
    'password': 'admin'                # Mot de passe ou clé API
}

# Configuration alternative pour tests
ODOO_CONFIG_TEST = {
    'url': 'http://localhost:8069',
    'db': 'test_db',
    'username': 'demo',
    'password': 'demo'
}

# Configuration pour production (exemple)
ODOO_CONFIG_PROD = {
    'url': 'https://your-domain.odoo.com',
    'db': 'production_db',
    'username': 'api_user',
    'password': 'your_api_key'
}

# Sélectionnez la configuration à utiliser
# Changez cette ligne pour basculer entre environnements
CURRENT_CONFIG = ODOO_CONFIG

# Paramètres additionnels
TIMEOUT = 60  # Timeout en secondes pour les requêtes
MAX_RETRIES = 3  # Nombre de tentatives de reconnexion