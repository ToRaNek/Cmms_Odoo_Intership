# external_apps/odoo_client_app/odoo_client/xmlrpc_client.py
import xmlrpc.client
import ssl
import logging

# Configuration du logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class OdooXMLRPCClient:
    """Client d'authentification XML-RPC pour Odoo 16
    
    Cette méthode est la solution recommandée pour les applications externes 
    car elle évite complètement les problèmes de protection CSRF.
    
    Usage:
        client = OdooXMLRPCClient('http://localhost:8069', 'mydb', 'admin', 'admin')
        if client.authenticate():
            # Utiliser le client...
            partners = client.search_read('res.partner', [['is_company', '=', True]])
    """
    
    def __init__(self, url, db, username, password, timeout=60):
        """Initialise le client XML-RPC
        
        Args:
            url (str): URL de base d'Odoo (ex: http://localhost:8069)
            db (str): Nom de la base de données
            username (str): Nom d'utilisateur Odoo
            password (str): Mot de passe ou clé API
            timeout (int): Timeout en secondes pour les requêtes
        """
        self.url = url.rstrip('/')
        self.db = db
        self.username = username
        self.password = password
        self.uid = None
        
        # Configuration SSL pour ignorer les certificats auto-signés (optionnel)
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        
        # Points de terminaison XML-RPC
        try:
            self.common = xmlrpc.client.ServerProxy(
                f'{self.url}/xmlrpc/2/common',
                context=context,
                allow_none=True
            )
            self.models = xmlrpc.client.ServerProxy(
                f'{self.url}/xmlrpc/2/object',
                context=context,
                allow_none=True
            )
            logger.info(f"Client XML-RPC initialisé pour {self.url}")
        except Exception as e:
            logger.error(f"Erreur lors de l'initialisation du client: {e}")
            raise
    
    def get_version(self):
        """Récupère la version du serveur Odoo"""
        try:
            version = self.common.version()
            logger.info(f"Version du serveur: {version}")
            return version
        except Exception as e:
            logger.error(f"Erreur lors de la récupération de la version: {e}")
            return None
    
    def authenticate(self):
        """Authentifie l'utilisateur et retourne True si réussie
        
        Returns:
            bool: True si l'authentification réussit, False sinon
        """
        try:
            # Vérification de la version du serveur (facultatif mais recommandé)
            version = self.get_version()
            if not version:
                logger.warning("Impossible de récupérer la version du serveur")
            
            # Tentative d'authentification
            self.uid = self.common.authenticate(self.db, self.username, self.password, {})
            
            if self.uid:
                logger.info(f"Authentification réussie. UID: {self.uid}")
                # Vérifier les permissions
                self._check_access_rights()
                return True
            else:
                logger.error("Échec de l'authentification - Vérifiez vos identifiants")
                return False
                
        except xmlrpc.client.Fault as e:
            logger.error(f"Erreur XML-RPC lors de l'authentification: {e}")
            return False
        except Exception as e:
            logger.error(f"Erreur inattendue lors de l'authentification: {e}")
            return False
    
    def _check_access_rights(self):
        """Vérifie les droits d'accès de base"""
        try:
            # Test de lecture sur res.users
            access = self.models.execute_kw(
                self.db, self.uid, self.password,
                'res.users', 'check_access_rights',
                ['read'], {'raise_exception': False}
            )
            logger.info(f"Droits d'accès en lecture: {'OK' if access else 'NOK'}")
        except Exception as e:
            logger.warning(f"Impossible de vérifier les droits d'accès: {e}")
    
    def execute_kw(self, model, method, args=None, kwargs=None):
        """Exécute une méthode sur un modèle Odoo
        
        Args:
            model (str): Nom du modèle (ex: 'res.partner')
            method (str): Méthode à exécuter (ex: 'search', 'read', 'create')
            args (list): Arguments positionnels
            kwargs (dict): Arguments nommés
            
        Returns:
            Résultat de l'exécution de la méthode
        """
        if not self.uid:
            raise Exception("Vous devez d'abord vous authentifier avec authenticate()")
        
        args = args or []
        kwargs = kwargs or {}
        
        try:
            result = self.models.execute_kw(
                self.db, self.uid, self.password,
                model, method, args, kwargs
            )
            logger.debug(f"Exécution réussie: {model}.{method}")
            return result
        except xmlrpc.client.Fault as e:
            logger.error(f"Erreur XML-RPC pour {model}.{method}: {e}")
            raise
        except Exception as e:
            logger.error(f"Erreur inattendue pour {model}.{method}: {e}")
            raise
    
    # Méthodes de convenance pour les opérations CRUD
    
    def search(self, model, domain=None, offset=0, limit=None, order=None):
        """Recherche des IDs d'enregistrements
        
        Args:
            model (str): Nom du modèle
            domain (list): Domaine de recherche
            offset (int): Décalage
            limit (int): Limite de résultats
            order (str): Ordre de tri
            
        Returns:
            list: Liste des IDs trouvés
        """
        domain = domain or []
        kwargs = {'offset': offset}
        if limit is not None:
            kwargs['limit'] = limit
        if order:
            kwargs['order'] = order
            
        return self.execute_kw(model, 'search', [domain], kwargs)
    
    def read(self, model, ids, fields=None):
        """Lit des enregistrements par leurs IDs
        
        Args:
            model (str): Nom du modèle
            ids (list): Liste des IDs à lire
            fields (list): Liste des champs à récupérer
            
        Returns:
            list: Liste des enregistrements
        """
        kwargs = {}
        if fields:
            kwargs['fields'] = fields
            
        return self.execute_kw(model, 'read', [ids], kwargs)
    
    def search_read(self, model, domain=None, fields=None, offset=0, limit=None, order=None):
        """Recherche et lit des enregistrements en une seule opération
        
        Args:
            model (str): Nom du modèle
            domain (list): Domaine de recherche
            fields (list): Champs à récupérer
            offset (int): Décalage
            limit (int): Limite de résultats
            order (str): Ordre de tri
            
        Returns:
            list: Liste des enregistrements trouvés
        """
        domain = domain or []
        kwargs = {'offset': offset}
        if fields:
            kwargs['fields'] = fields
        if limit is not None:
            kwargs['limit'] = limit
        if order:
            kwargs['order'] = order
            
        return self.execute_kw(model, 'search_read', [domain], kwargs)
    
    def create(self, model, values):
        """Crée un nouvel enregistrement
        
        Args:
            model (str): Nom du modèle
            values (dict): Valeurs du nouvel enregistrement
            
        Returns:
            int: ID de l'enregistrement créé
        """
        return self.execute_kw(model, 'create', [values])
    
    def write(self, model, ids, values):
        """Met à jour des enregistrements existants
        
        Args:
            model (str): Nom du modèle
            ids (list): Liste des IDs à mettre à jour
            values (dict): Nouvelles valeurs
            
        Returns:
            bool: True si la mise à jour réussit
        """
        return self.execute_kw(model, 'write', [ids, values])
    
    def unlink(self, model, ids):
        """Supprime des enregistrements
        
        Args:
            model (str): Nom du modèle
            ids (list): Liste des IDs à supprimer
            
        Returns:
            bool: True si la suppression réussit
        """
        return self.execute_kw(model, 'unlink', [ids])
    
    def search_count(self, model, domain=None):
        """Compte le nombre d'enregistrements correspondant au domaine
        
        Args:
            model (str): Nom du modèle
            domain (list): Domaine de recherche
            
        Returns:
            int: Nombre d'enregistrements
        """
        domain = domain or []
        return self.execute_kw(model, 'search_count', [domain])
    
    def fields_get(self, model, fields=None):
        """Récupère la définition des champs d'un modèle
        
        Args:
            model (str): Nom du modèle
            fields (list): Liste des champs spécifiques (optionnel)
            
        Returns:
            dict: Définition des champs
        """
        args = [fields] if fields else []
        return self.execute_kw(model, 'fields_get', args)