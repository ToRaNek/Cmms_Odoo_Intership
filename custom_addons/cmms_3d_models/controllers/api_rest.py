# custom_addons/cmms_3d_models/controllers/api_rest.py
import json
import base64
import logging
from datetime import datetime
from odoo import http, fields
from odoo.http import request
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT
import functools

_logger = logging.getLogger(__name__)

def basic_auth_required(func):
    """Décorateur pour l'authentification Basic Auth"""
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        # Récupérer l'header Authorization
        auth_header = request.httprequest.headers.get('Authorization')
        
        if not auth_header or not auth_header.startswith('Basic '):
            return self._error_response('Authentication required', 401)
        
        try:
            # Décoder les credentials
            encoded_credentials = auth_header.split(' ')[1]
            decoded_credentials = base64.b64decode(encoded_credentials).decode('utf-8')
            username, password = decoded_credentials.split(':', 1)
            
            # Authentifier l'utilisateur
            uid = request.session.authenticate(request.session.db, username, password)
            
            if not uid:
                return self._error_response('Invalid credentials', 401)
                
            # L'utilisateur est authentifié, continuer
            return func(self, *args, **kwargs)
            
        except Exception as e:
            _logger.error(f"Authentication error: {str(e)}")
            return self._error_response('Authentication failed', 401)
    
    return wrapper

class CMSAPIController(http.Controller):
    
    def _success_response(self, data=None, message="Success", status_code=200):
        """Format de réponse standardisé pour les succès"""
        response_data = {
            'success': True,
            'message': message,
            'data': data,
            'timestamp': fields.Datetime.now().strftime(DEFAULT_SERVER_DATETIME_FORMAT)
        }
        
        response = request.make_response(
            json.dumps(response_data, default=str),
            headers=[
                ('Content-Type', 'application/json'),
                ('Access-Control-Allow-Origin', '*'),
                ('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS'),
                ('Access-Control-Allow-Headers', 'Content-Type, Authorization'),
            ]
        )
        response.status_code = status_code
        return response
    
    def _error_response(self, message="Error", status_code=400, error_details=None):
        """Format de réponse standardisé pour les erreurs"""
        response_data = {
            'success': False,
            'message': message,
            'error_details': error_details,
            'timestamp': fields.Datetime.now().strftime(DEFAULT_SERVER_DATETIME_FORMAT)
        }
        
        response = request.make_response(
            json.dumps(response_data, default=str),
            headers=[
                ('Content-Type', 'application/json'),
                ('Access-Control-Allow-Origin', '*'),
                ('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS'),
                ('Access-Control-Allow-Headers', 'Content-Type, Authorization'),
            ]
        )
        response.status_code = status_code
        return response
    
    def _get_user_teams(self):
        """Récupérer les équipes de l'utilisateur connecté"""
        user = request.env.user
        
        # Récupérer la personne de maintenance correspondante
        person = request.env['maintenance.person'].search([('user_id', '=', user.id)], limit=1)
        
        if person:
            return person.team_ids.ids
        else:
            # Si pas de personne de maintenance, chercher dans les équipes directement via user
            # Fallback pour les utilisateurs standards
            teams = request.env['maintenance.team'].search([
                ('member_ids', 'in', [user.id])
            ])
            return teams.ids
    
    def _get_allowed_requests_domain(self):
        """Construire le domaine pour les demandes autorisées"""
        user = request.env.user
        
        # Dans Odoo 16, les champs standards sont :
        # - user_id : créateur de la demande
        # - owner_user_id : propriétaire 
        # - technician_user_id : technicien assigné (optionnel)
        # - assigned_user_id : notre champ personnalisé (peut ne pas exister)
        # - assigned_person_id : personne de maintenance assignée (notre extension)
        
        # Créer le domaine avec les champs qui existent vraiment
        domain = []
        request_model = request.env['maintenance.request']
        
        # Toujours inclure les demandes créées par l'utilisateur
        domain.append(('user_id', '=', user.id))
        
        # Ajouter les demandes dont il est propriétaire (si le champ existe)
        if 'owner_user_id' in request_model._fields:
            domain = ['|'] + domain + [('owner_user_id', '=', user.id)]
        
        # Ajouter les demandes dont il est technicien (si le champ existe)
        if 'technician_user_id' in request_model._fields:
            domain = ['|'] + domain + [('technician_user_id', '=', user.id)]
        
        # Ajouter notre champ personnalisé assigned_user_id (si il existe)
        if 'assigned_user_id' in request_model._fields:
            domain = ['|'] + domain + [('assigned_user_id', '=', user.id)]
        
        # IMPORTANT: Ajouter les demandes assignées via assigned_person_id
        if 'assigned_person_id' in request_model._fields:
            domain = ['|'] + domain + [('assigned_person_id.user_id', '=', user.id)]
        
        # Ajouter les demandes des équipes
        team_ids = self._get_user_teams()
        if team_ids:
            domain = ['|'] + domain + [('maintenance_team_id', 'in', team_ids)]
        
        return domain
    
    def _get_allowed_equipment_domain(self):
        """Construire le domaine pour les équipements autorisés"""
        user = request.env.user
        
        # Domaine de base : équipements dont l'utilisateur est technicien ou propriétaire
        domain = [
            '|', 
            ('technician_user_id', '=', user.id),
            ('owner_user_id', '=', user.id)
        ]
        
        # Ajouter les équipements des équipes (si le champ existe)
        team_ids = self._get_user_teams()
        if team_ids:
            # Vérifier si le champ maintenance_team_id existe
            equipment_model = request.env['maintenance.equipment']
            if 'maintenance_team_id' in equipment_model._fields:
                domain = ['|'] + domain + [('maintenance_team_id', 'in', team_ids)]
        
        return domain
    
    def _serialize_request(self, request_record):
        """Sérialiser une demande de maintenance"""
        # URL du viewer 3D si disponible
        viewer_url = None
        if request_record.equipment_id and request_record.equipment_id.model3d_id:
            viewer_url = request_record.equipment_id.model3d_id.viewer_url
        
        # Gérer l'utilisateur assigné (plusieurs champs possibles)
        assigned_user = None
        if hasattr(request_record, 'assigned_user_id') and request_record.assigned_user_id:
            assigned_user = request_record.assigned_user_id
        elif hasattr(request_record, 'technician_user_id') and request_record.technician_user_id:
            assigned_user = request_record.technician_user_id
        elif hasattr(request_record, 'owner_user_id') and request_record.owner_user_id:
            assigned_user = request_record.owner_user_id
        
        return {
            'id': request_record.id,
            'name': request_record.name,
            'description': request_record.description or '',
            'request_date': request_record.request_date.strftime(DEFAULT_SERVER_DATETIME_FORMAT) if request_record.request_date else None,
            'schedule_date': request_record.schedule_date.strftime(DEFAULT_SERVER_DATETIME_FORMAT) if request_record.schedule_date else None,
            'stage_id': {
                'id': request_record.stage_id.id,
                'name': request_record.stage_id.name
            } if request_record.stage_id else None,
            'equipment_id': {
                'id': request_record.equipment_id.id,
                'name': request_record.equipment_id.name,
                'category': request_record.equipment_id.category_id.name if request_record.equipment_id.category_id else None,
                'location': request_record.equipment_id.location or '',
                'model_3d_viewer_url': viewer_url
            } if request_record.equipment_id else None,
            'assigned_user_id': {
                'id': assigned_user.id,
                'name': assigned_user.name
            } if assigned_user else None,
            'assigned_person_id': {
                'id': request_record.assigned_person_id.id,
                'name': request_record.assigned_person_id.display_name,
                'role': request_record.assigned_person_id.role_id.name if request_record.assigned_person_id.role_id else None
            } if hasattr(request_record, 'assigned_person_id') and request_record.assigned_person_id else None,
            'maintenance_team_id': {
                'id': request_record.maintenance_team_id.id,
                'name': request_record.maintenance_team_id.name
            } if request_record.maintenance_team_id else None,
            'maintenance_type': request_record.maintenance_type,
            'priority': request_record.priority,
            'kanban_state': request_record.kanban_state,
            'color': request_record.color,
            'duration': request_record.duration,
            # Supprimé: 'archive': not request_record.active (le champ active n'existe pas)
            'close_date': request_record.close_date.strftime(DEFAULT_SERVER_DATETIME_FORMAT) if request_record.close_date else None,
            # Champs utilisateur standard
            'user_id': {
                'id': request_record.user_id.id,
                'name': request_record.user_id.name
            } if request_record.user_id else None,
            'owner_user_id': {
                'id': request_record.owner_user_id.id,
                'name': request_record.owner_user_id.name
            } if hasattr(request_record, 'owner_user_id') and request_record.owner_user_id else None,
            'technician_user_id': {
                'id': request_record.technician_user_id.id,
                'name': request_record.technician_user_id.name
            } if hasattr(request_record, 'technician_user_id') and request_record.technician_user_id else None,
        }
    
    def _serialize_equipment(self, equipment_record):
        """Sérialiser un équipement"""
        # URLs des modèles 3D
        model_3d_url = None
        viewer_url = None
        if equipment_record.model3d_id:
            model_3d_url = equipment_record.model3d_id.model_url
            viewer_url = equipment_record.model3d_id.viewer_url
        
        return {
            'id': equipment_record.id,
            'name': equipment_record.name,
            'serial_no': equipment_record.serial_no or '',
            'location': equipment_record.location or '',
            'category_id': {
                'id': equipment_record.category_id.id,
                'name': equipment_record.category_id.name
            } if equipment_record.category_id else None,
            'partner_id': {
                'id': equipment_record.partner_id.id,
                'name': equipment_record.partner_id.name
            } if equipment_record.partner_id else None,
            'technician_user_id': {
                'id': equipment_record.technician_user_id.id,
                'name': equipment_record.technician_user_id.name
            } if equipment_record.technician_user_id else None,
            'owner_user_id': {
                'id': equipment_record.owner_user_id.id,
                'name': equipment_record.owner_user_id.name
            } if equipment_record.owner_user_id else None,
            'model3d_id': {
                'id': equipment_record.model3d_id.id,
                'name': equipment_record.model3d_id.name,
                'model_url': model_3d_url,
                'viewer_url': viewer_url
            } if equipment_record.model3d_id else None,
            'assign_date': equipment_record.assign_date.strftime(DEFAULT_SERVER_DATETIME_FORMAT) if equipment_record.assign_date else None,
            'cost': float(equipment_record.cost) if equipment_record.cost else 0.0,
            'note': equipment_record.note or '',
            'warranty_date': equipment_record.warranty_date.strftime('%Y-%m-%d') if equipment_record.warranty_date else None,
            'color': equipment_record.color,
            'cost_center': equipment_record.cost_center or '' if hasattr(equipment_record, 'cost_center') else '',
        }
    
    # ===== OPTIONS (CORS) =====
    @http.route([
        '/api/maintenance/requests',
        '/api/maintenance/equipment',
        '/api/maintenance/preventive',
        '/api/maintenance/history',
        '/api/maintenance/teams',
        '/api/maintenance/persons',
        '/api/maintenance/dashboard',
        '/api/maintenance/all',
        '/api/maintenance/debug'
    ], type='http', auth='none', methods=['OPTIONS'], csrf=False)
    def api_options(self, **kwargs):
        """Gestion des requêtes OPTIONS pour CORS"""
        return request.make_response(
            '',
            headers=[
                ('Access-Control-Allow-Origin', '*'),
                ('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS'),
                ('Access-Control-Allow-Headers', 'Content-Type, Authorization'),
                ('Access-Control-Max-Age', '3600'),
            ]
        )
    
    # ===== MAINTENANCE REQUESTS =====
    @http.route('/api/maintenance/requests', type='http', auth='none', methods=['GET'], csrf=False)
    @basic_auth_required
    def get_requests(self, limit=10000, offset=0, status=None, equipment_id=None, **kwargs):
        """Récupérer les demandes de maintenance de l'utilisateur"""
        try:
            limit = int(limit) if limit else 10000
            offset = int(offset) if offset else 0
            
            # Construire le domaine de recherche
            domain = self._get_allowed_requests_domain()
            
            # Filtres supplémentaires
            if status:
                # Mapper les statuts courrants
                status_mapping = {
                    'new': [('stage_id.name', 'ilike', 'new')],
                    'in_progress': [('stage_id.name', 'ilike', 'progress')],
                    'done': [('stage_id.done', '=', True)],
                    'cancelled': [('kanban_state', '=', 'blocked')]
                }
                if status in status_mapping:
                    domain.extend(status_mapping[status])
            
            if equipment_id:
                domain.append(('equipment_id', '=', int(equipment_id)))
            
            # Récupérer les demandes
            requests = request.env['maintenance.request'].search(
                domain, 
                limit=limit, 
                offset=offset,
                order='request_date desc, id desc'
            )
            
            # Sérialiser les données
            data = {
                'requests': [self._serialize_request(req) for req in requests],
                'total_count': request.env['maintenance.request'].search_count(domain),
                'limit': limit,
                'offset': offset
            }
            
            return self._success_response(data, "Requests retrieved successfully")
            
        except Exception as e:
            _logger.error(f"Error getting requests: {str(e)}")
            return self._error_response(f"Error retrieving requests: {str(e)}", 500)
    
    @http.route('/api/maintenance/requests/<int:request_id>', type='http', auth='none', methods=['GET'], csrf=False)
    @basic_auth_required
    def get_request(self, request_id, **kwargs):
        """Récupérer une demande spécifique"""
        try:
            domain = self._get_allowed_requests_domain()
            domain.append(('id', '=', request_id))
            
            maintenance_request = request.env['maintenance.request'].search(domain, limit=1)
            
            if not maintenance_request:
                return self._error_response("Request not found", 404)
            
            data = self._serialize_request(maintenance_request)
            return self._success_response(data, "Request retrieved successfully")
            
        except Exception as e:
            _logger.error(f"Error getting request {request_id}: {str(e)}")
            return self._error_response(f"Error retrieving request: {str(e)}", 500)
    
    @http.route('/api/maintenance/requests', type='json', auth='none', methods=['POST'], csrf=False)
    @basic_auth_required
    def create_request(self, **kwargs):
        """Créer une nouvelle demande de maintenance"""
        try:
            data = request.get_json_data()
            
            # Valider les données requises
            if not data.get('name'):
                return self._error_response("Name is required", 400)
            
            # Préparer les valeurs pour la création
            vals = {
                'name': data['name'],
                'description': data.get('description', ''),
                'maintenance_type': data.get('maintenance_type', 'corrective'),
                'user_id': request.env.user.id,
                'request_date': fields.Datetime.now(),
            }
            
            # Champs optionnels
            if data.get('equipment_id'):
                vals['equipment_id'] = data['equipment_id']
            if data.get('schedule_date'):
                vals['schedule_date'] = data['schedule_date']
            if data.get('priority'):
                vals['priority'] = data['priority']
            if data.get('maintenance_team_id'):
                vals['maintenance_team_id'] = data['maintenance_team_id']
            if data.get('assigned_user_id'):
                vals['assigned_user_id'] = data['assigned_user_id']
            
            # Créer la demande
            new_request = request.env['maintenance.request'].create(vals)
            
            return self._success_response(
                self._serialize_request(new_request),
                "Request created successfully",
                201
            )
            
        except ValidationError as e:
            return self._error_response(f"Validation error: {str(e)}", 400)
        except Exception as e:
            _logger.error(f"Error creating request: {str(e)}")
            return self._error_response(f"Error creating request: {str(e)}", 500)
    
    @http.route('/api/maintenance/requests/<int:request_id>', type='json', auth='none', methods=['PUT'], csrf=False)
    @basic_auth_required
    def update_request(self, request_id, **kwargs):
        """Mettre à jour une demande de maintenance"""
        try:
            # Vérifier les permissions
            domain = self._get_allowed_requests_domain()
            domain.append(('id', '=', request_id))
            
            maintenance_request = request.env['maintenance.request'].search(domain, limit=1)
            
            if not maintenance_request:
                return self._error_response("Request not found", 404)
            
            data = request.get_json_data()
            
            # Préparer les valeurs de mise à jour
            vals = {}
            allowed_fields = [
                'name', 'description', 'schedule_date', 'priority', 
                'kanban_state', 'stage_id', 'assigned_user_id', 'maintenance_team_id'
            ]
            
            for field in allowed_fields:
                if field in data:
                    vals[field] = data[field]
            
            # Mettre à jour
            maintenance_request.write(vals)
            
            return self._success_response(
                self._serialize_request(maintenance_request),
                "Request updated successfully"
            )
            
        except ValidationError as e:
            return self._error_response(f"Validation error: {str(e)}", 400)
        except Exception as e:
            _logger.error(f"Error updating request {request_id}: {str(e)}")
            return self._error_response(f"Error updating request: {str(e)}", 500)
    
    @http.route('/api/maintenance/requests/<int:request_id>', type='http', auth='none', methods=['DELETE'], csrf=False)
    @basic_auth_required
    def delete_request(self, request_id, **kwargs):
        """Supprimer une demande de maintenance"""
        try:
            # Vérifier les permissions
            domain = self._get_allowed_requests_domain()
            domain.append(('id', '=', request_id))
            
            maintenance_request = request.env['maintenance.request'].search(domain, limit=1)
            
            if not maintenance_request:
                return self._error_response("Request not found", 404)
            
            # Archiver au lieu de supprimer pour conserver l'historique
            maintenance_request.action_archive()
            
            return self._success_response(None, "Request archived successfully")
            
        except Exception as e:
            _logger.error(f"Error deleting request {request_id}: {str(e)}")
            return self._error_response(f"Error archiving request: {str(e)}", 500)
    
    # ===== EQUIPMENT =====
    @http.route('/api/maintenance/equipment', type='http', auth='none', methods=['GET'], csrf=False)
    @basic_auth_required
    def get_equipment(self, limit=10000, offset=0, category_id=None, has_3d_model=None, **kwargs):
        """Récupérer les équipements"""
        try:
            limit = int(limit) if limit else 10000
            offset = int(offset) if offset else 0
            
            # Utiliser la nouvelle fonction pour le domaine
            domain = self._get_allowed_equipment_domain()
            
            # Filtres supplémentaires
            if category_id:
                domain.append(('category_id', '=', int(category_id)))
            
            if has_3d_model == 'true':
                domain.append(('model3d_id', '!=', False))
            elif has_3d_model == 'false':
                domain.append(('model3d_id', '=', False))
            
            # Récupérer les équipements
            equipment_records = request.env['maintenance.equipment'].search(
                domain,
                limit=limit,
                offset=offset,
                order='name asc'
            )
            
            # Sérialiser les données
            data = {
                'equipment': [self._serialize_equipment(eq) for eq in equipment_records],
                'total_count': request.env['maintenance.equipment'].search_count(domain),
                'limit': limit,
                'offset': offset
            }
            
            return self._success_response(data, "Equipment retrieved successfully")
            
        except Exception as e:
            _logger.error(f"Error getting equipment: {str(e)}")
            return self._error_response(f"Error retrieving equipment: {str(e)}", 500)
    
    @http.route('/api/maintenance/equipment/<int:equipment_id>', type='http', auth='none', methods=['GET'], csrf=False)
    @basic_auth_required
    def get_single_equipment(self, equipment_id, **kwargs):
        """Récupérer un équipement spécifique"""
        try:
            equipment = request.env['maintenance.equipment'].browse(equipment_id)
            
            if not equipment.exists():
                return self._error_response("Equipment not found", 404)
            
            # Vérifier les permissions (simplifiées pour cet exemple)
            # En production, vous pouvez ajouter des vérifications plus strictes
            
            data = self._serialize_equipment(equipment)
            return self._success_response(data, "Equipment retrieved successfully")
            
        except Exception as e:
            _logger.error(f"Error getting equipment {equipment_id}: {str(e)}")
            return self._error_response(f"Error retrieving equipment: {str(e)}", 500)
    
    # ===== MAINTENANCE PREVENTIVE =====
    @http.route('/api/maintenance/preventive', type='http', auth='none', methods=['GET'], csrf=False)
    @basic_auth_required
    def get_preventive_maintenance(self, limit=10000, offset=0, **kwargs):
        """Récupérer les maintenances préventives de l'utilisateur"""
        try:
            limit = int(limit) if limit else 10000
            offset = int(offset) if offset else 0
            
            # Domaine pour les maintenances préventives
            domain = self._get_allowed_requests_domain()
            domain.append(('maintenance_type', '=', 'preventive'))
            
            # Récupérer les demandes préventives
            preventive_requests = request.env['maintenance.request'].search(
                domain,
                limit=limit,
                offset=offset,
                order='schedule_date asc, id desc'
            )
            
            # Sérialiser les données
            data = {
                'preventive_maintenance': [self._serialize_request(req) for req in preventive_requests],
                'total_count': request.env['maintenance.request'].search_count(domain),
                'limit': limit,
                'offset': offset
            }
            
            return self._success_response(data, "Preventive maintenance retrieved successfully")
            
        except Exception as e:
            _logger.error(f"Error getting preventive maintenance: {str(e)}")
            return self._error_response(f"Error retrieving preventive maintenance: {str(e)}", 500)
    
    # ===== MAINTENANCE HISTORY =====
    @http.route('/api/maintenance/history', type='http', auth='none', methods=['GET'], csrf=False)
    @basic_auth_required
    def get_maintenance_history(self, limit=10000, offset=0, equipment_id=None, **kwargs):
        """Récupérer l'historique des maintenances"""
        try:
            limit = int(limit) if limit else 10000
            offset = int(offset) if offset else 0
            
            # Domaine pour l'historique (demandes terminées)
            domain = self._get_allowed_requests_domain()
            domain.append(('stage_id.done', '=', True))
            
            if equipment_id:
                domain.append(('equipment_id', '=', int(equipment_id)))
            
            # Récupérer l'historique
            history_requests = request.env['maintenance.request'].search(
                domain,
                limit=limit,
                offset=offset,
                order='close_date desc, id desc'
            )
            
            # Sérialiser les données
            data = {
                'history': [self._serialize_request(req) for req in history_requests],
                'total_count': request.env['maintenance.request'].search_count(domain),
                'limit': limit,
                'offset': offset
            }
            
            return self._success_response(data, "Maintenance history retrieved successfully")
            
        except Exception as e:
            _logger.error(f"Error getting maintenance history: {str(e)}")
            return self._error_response(f"Error retrieving maintenance history: {str(e)}", 500)
    
    # ===== TEAMS =====
    @http.route('/api/maintenance/teams', type='http', auth='none', methods=['GET'], csrf=False)
    @basic_auth_required
    def get_teams(self, **kwargs):
        """Récupérer les équipes de maintenance de l'utilisateur"""
        try:
            team_ids = self._get_user_teams()
            teams = request.env['maintenance.team'].browse(team_ids)
            
            data = []
            for team in teams:
                team_data = {
                    'id': team.id,
                    'name': team.name,
                    'color': team.color,
                    'member_ids': [{'id': member.id, 'name': member.name} for member in team.member_ids],
                    'member_count': len(team.member_ids),
                }
                data.append(team_data)
            
            return self._success_response(data, "Teams retrieved successfully")
            
        except Exception as e:
            _logger.error(f"Error getting teams: {str(e)}")
            return self._error_response(f"Error retrieving teams: {str(e)}", 500)
    
    # ===== PERSONS =====
    @http.route('/api/maintenance/persons', type='http', auth='none', methods=['GET'], csrf=False)
    @basic_auth_required
    def get_persons(self, **kwargs):
        """Récupérer les personnes de maintenance des équipes de l'utilisateur"""
        try:
            team_ids = self._get_user_teams()
            
            if team_ids:
                # Récupérer les personnes des équipes de l'utilisateur
                persons = request.env['maintenance.person'].search([
                    ('team_ids', 'in', team_ids),
                    ('active', '=', True)
                ])
            else:
                # Si pas d'équipe, récupérer seulement la personne correspondant à l'utilisateur
                persons = request.env['maintenance.person'].search([
                    ('user_id', '=', request.env.user.id),
                    ('active', '=', True)
                ])
            
            data = []
            for person in persons:
                person_data = {
                    'id': person.id,
                    'name': person.display_name,
                    'email': person.email or '',
                    'phone': person.phone or '',
                    'role': {
                        'id': person.role_id.id,
                        'name': person.role_id.name
                    } if person.role_id else None,
                    'available': person.available,
                    'request_count': person.request_count,
                    'specialties': person.specialties or '',
                    'teams': [{'id': team.id, 'name': team.name} for team in person.team_ids]
                }
                data.append(person_data)
            
            return self._success_response(data, "Persons retrieved successfully")
            
        except Exception as e:
            _logger.error(f"Error getting persons: {str(e)}")
            return self._error_response(f"Error retrieving persons: {str(e)}", 500)
    
    # ===== DASHBOARD - TOUTES LES DONNÉES EN UNE FOIS =====
    @http.route('/api/maintenance/dashboard', type='http', auth='none', methods=['GET'], csrf=False)
    @basic_auth_required
    def get_dashboard(self, **kwargs):
        """Récupérer toutes les données de maintenance en un seul appel"""
        try:
            user = request.env.user
            team_ids = self._get_user_teams()
            dashboard_data = {}
            
            # 1. Informations utilisateur
            person = request.env['maintenance.person'].search([('user_id', '=', user.id)], limit=1)
            dashboard_data['user_info'] = {
                'id': user.id,
                'name': user.name,
                'email': user.email or '',
                'person_info': {
                    'id': person.id,
                    'display_name': person.display_name,
                    'role': person.role_id.name if person.role_id else None,
                    'available': person.available,
                    'phone': person.phone or '',
                    'specialties': person.specialties or ''
                } if person else None
            }
            
            # 2. Demandes de maintenance (limitées à 20 récentes)
            request_domain = self._get_allowed_requests_domain()
            requests = request.env['maintenance.request'].search(
                request_domain, 
                limit=20,
                order='request_date desc, id desc'
            )
            dashboard_data['requests'] = {
                'recent': [self._serialize_request(req) for req in requests],
                'total_count': request.env['maintenance.request'].search_count(request_domain)
            }
            
            # 3. Statistiques des demandes par statut
            stats = {}
            for status in ['new', 'in_progress', 'done']:
                if status == 'new':
                    domain = request_domain + [('stage_id.done', '=', False), ('kanban_state', '!=', 'blocked')]
                elif status == 'in_progress':
                    domain = request_domain + [('stage_id.done', '=', False), ('kanban_state', '=', 'normal')]
                elif status == 'done':
                    domain = request_domain + [('stage_id.done', '=', True)]
                
                stats[status] = request.env['maintenance.request'].search_count(domain)
            
            dashboard_data['request_stats'] = stats
            
            # 4. Maintenance préventive (prochaines 10)
            preventive_domain = request_domain + [('maintenance_type', '=', 'preventive')]
            preventive_requests = request.env['maintenance.request'].search(
                preventive_domain,
                limit=10,
                order='schedule_date asc'
            )
            dashboard_data['preventive_maintenance'] = [
                self._serialize_request(req) for req in preventive_requests
            ]
            
            # 5. Équipements avec modèles 3D (limités à 10)
            equipment_domain = self._get_allowed_equipment_domain()
            
            equipment_records = request.env['maintenance.equipment'].search(
                equipment_domain,
                limit=10,
                order='name asc'
            )
            
            # Séparer les équipements avec et sans modèle 3D
            equipment_with_3d = [eq for eq in equipment_records if eq.model3d_id]
            equipment_without_3d = [eq for eq in equipment_records if not eq.model3d_id]
            
            dashboard_data['equipment'] = {
                'with_3d_models': [self._serialize_equipment(eq) for eq in equipment_with_3d],
                'without_3d_models': [self._serialize_equipment(eq) for eq in equipment_without_3d],
                'total_count': request.env['maintenance.equipment'].search_count(equipment_domain),
                'with_3d_count': len(equipment_with_3d),
                'without_3d_count': len(equipment_without_3d)
            }
            
            # 6. Historique récent (5 dernières)
            history_domain = request_domain + [('stage_id.done', '=', True)]
            history_requests = request.env['maintenance.request'].search(
                history_domain,
                limit=5,
                order='close_date desc'
            )
            dashboard_data['recent_history'] = [
                self._serialize_request(req) for req in history_requests
            ]
            
            # 7. Équipes
            teams = request.env['maintenance.team'].browse(team_ids)
            dashboard_data['teams'] = []
            for team in teams:
                team_data = {
                    'id': team.id,
                    'name': team.name,
                    'color': team.color,
                    'member_ids': [{'id': member.id, 'name': member.name} for member in team.member_ids],
                    'member_count': len(team.member_ids),
                }
                dashboard_data['teams'].append(team_data)
            
            # 8. Collègues (personnes des équipes)
            if team_ids:
                colleagues = request.env['maintenance.person'].search([
                    ('team_ids', 'in', team_ids),
                    ('active', '=', True),
                    ('id', '!=', person.id if person else 0)  # Exclure l'utilisateur actuel
                ])
            else:
                colleagues = request.env['maintenance.person'].browse([])
            
            dashboard_data['colleagues'] = []
            for colleague in colleagues:
                colleague_data = {
                    'id': colleague.id,
                    'name': colleague.display_name,
                    'role': colleague.role_id.name if colleague.role_id else None,
                    'available': colleague.available,
                    'request_count': colleague.request_count,
                    'teams': [team.name for team in colleague.team_ids]
                }
                dashboard_data['colleagues'].append(colleague_data)
            
            # 9. Résumé rapide
            dashboard_data['summary'] = {
                'total_active_requests': stats.get('new', 0) + stats.get('in_progress', 0),
                'completed_requests': stats.get('done', 0),
                'preventive_scheduled': len(preventive_requests),
                'equipment_with_3d': len(equipment_with_3d),
                'teams_count': len(teams),
                'colleagues_count': len(colleagues)
            }
            
            return self._success_response(dashboard_data, "Dashboard data retrieved successfully")
            
        except Exception as e:
            _logger.error(f"Error getting dashboard: {str(e)}")
            return self._error_response(f"Error retrieving dashboard: {str(e)}", 500)
    
    # ===== ENDPOINT COMPLET (ALIAS) =====
    @http.route('/api/maintenance/all', type='http', auth='none', methods=['GET'], csrf=False)
    @basic_auth_required
    def get_all_data(self, **kwargs):
        """Alias pour récupérer toutes les données (même que dashboard)"""
        return self.get_dashboard(**kwargs)
    
    # ===== DEBUG ENDPOINT =====
    @http.route('/api/maintenance/debug', type='http', auth='none', methods=['GET'], csrf=False)
    @basic_auth_required
    def debug_fields(self, **kwargs):
        """Endpoint de debug pour voir les champs disponibles"""
        try:
            user = request.env.user
            debug_info = {
                'user_info': {
                    'id': user.id,
                    'name': user.name,
                    'login': user.login
                },
                'request_fields': list(request.env['maintenance.request']._fields.keys()),
                'equipment_fields': list(request.env['maintenance.equipment']._fields.keys()),
                'team_fields': list(request.env['maintenance.team']._fields.keys()),
                'test_requests': []
            }
            
            # Tester quelques demandes
            all_requests = request.env['maintenance.request'].search([], limit=5)
            for req in all_requests:
                req_info = {
                    'id': req.id,
                    'name': req.name,
                    'user_id': req.user_id.name if req.user_id else None,
                    'has_assigned_user_id': hasattr(req, 'assigned_user_id'),
                    'has_technician_user_id': hasattr(req, 'technician_user_id'),
                    'has_owner_user_id': hasattr(req, 'owner_user_id'),
                    'maintenance_team_id': req.maintenance_team_id.name if req.maintenance_team_id else None,
                }
                
                # Ajouter les valeurs des champs s'ils existent
                if hasattr(req, 'assigned_user_id'):
                    req_info['assigned_user_id'] = req.assigned_user_id.name if req.assigned_user_id else None
                if hasattr(req, 'technician_user_id'):
                    req_info['technician_user_id'] = req.technician_user_id.name if req.technician_user_id else None
                if hasattr(req, 'owner_user_id'):
                    req_info['owner_user_id'] = req.owner_user_id.name if req.owner_user_id else None
                
                debug_info['test_requests'].append(req_info)
            
            return self._success_response(debug_info, "Debug info retrieved successfully")
            
        except Exception as e:
            _logger.error(f"Error getting debug info: {str(e)}")
            return self._error_response(f"Error retrieving debug info: {str(e)}", 500)
