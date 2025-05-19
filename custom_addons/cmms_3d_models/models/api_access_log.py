# custom_addons/cmms_3d_models/models/api_access_log.py
from odoo import api, fields, models
import logging

_logger = logging.getLogger(__name__)

class APIAccessLog(models.Model):
    _name = 'cmms.api.access.log'
    _description = 'API Access Log'
    _order = 'create_date desc'
    _rec_name = 'user_id'
    
    user_id = fields.Many2one('res.users', string='Utilisateur', required=True, ondelete='cascade')
    endpoint = fields.Char('Endpoint', required=True)
    method = fields.Char('Méthode HTTP', required=True)
    ip_address = fields.Char('Adresse IP')
    user_agent = fields.Text('User Agent')
    status_code = fields.Integer('Code de statut')
    response_time = fields.Float('Temps de réponse (ms)')
    error_message = fields.Text('Message d\'erreur')
    request_data = fields.Text('Données de la requête')
    
    @api.model
    def log_api_access(self, user_id, endpoint, method, ip_address=None, 
                      user_agent=None, status_code=None, response_time=None, 
                      error_message=None, request_data=None):
        """Enregistrer un accès API"""
        try:
            vals = {
                'user_id': user_id,
                'endpoint': endpoint,
                'method': method,
                'ip_address': ip_address,
                'user_agent': user_agent,
                'status_code': status_code,
                'response_time': response_time,
                'error_message': error_message,
                'request_data': request_data,
            }
            self.create(vals)
        except Exception as e:
            _logger.error(f"Error logging API access: {str(e)}")

class APIKey(models.Model):
    _name = 'cmms.api.key'
    _description = 'API Key Management'
    _rec_name = 'name'
    
    name = fields.Char('Nom', required=True)
    user_id = fields.Many2one('res.users', string='Utilisateur', required=True, ondelete='cascade')
    api_key = fields.Char('Clé API', required=True, copy=False)
    active = fields.Boolean('Actif', default=True)
    last_used = fields.Datetime('Dernière utilisation')
    usage_count = fields.Integer('Nombre d\'utilisations', default=0)
    rate_limit = fields.Integer('Limite de taux (req/minute)', default=60)
    allowed_ips = fields.Text('IPs autorisées (une par ligne)')
    expires_at = fields.Datetime('Expire le')
    
    @api.model
    def create(self, vals):
        """Générer automatiquement une clé API"""
        if not vals.get('api_key'):
            import secrets
            vals['api_key'] = secrets.token_urlsafe(32)
        return super().create(vals)
    
    def check_rate_limit(self, ip_address=None):
        """Vérifier les limites de taux"""
        if not self.rate_limit:
            return True
        
        # Compter les appels dans la dernière minute
        now = fields.Datetime.now()
        minute_ago = now - fields.timedelta(minutes=1)
        
        recent_calls = self.env['cmms.api.access.log'].search_count([
            ('user_id', '=', self.user_id.id),
            ('create_date', '>=', minute_ago)
        ])
        
        return recent_calls < self.rate_limit
    
    def check_ip_allowed(self, ip_address):
        """Vérifier si l'IP est autorisée"""
        if not self.allowed_ips:
            return True
        
        allowed_ips = [ip.strip() for ip in self.allowed_ips.split('\n') if ip.strip()]
        return ip_address in allowed_ips
    
    def is_valid(self):
        """Vérifier si la clé API est valide"""
        if not self.active:
            return False
        
        if self.expires_at and self.expires_at < fields.Datetime.now():
            return False
        
        return True
    
    def log_usage(self):
        """Enregistrer l'utilisation de la clé"""
        self.write({
            'last_used': fields.Datetime.now(),
            'usage_count': self.usage_count + 1
        })