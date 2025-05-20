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

        except (ValueError, UnicodeDecodeError) as e:
            _logger.error(f"Authentication decode error: {str(e)}")
            return self._error_response('Invalid authentication format', 401)
        except Exception as e:
            _logger.error(f"Authentication error: {str(e)}")
            return self._error_response('Authentication failed', 401)

    return wrapper

class CMSAPIController(http.Controller):

    def _get_cors_headers(self):
        """Retourne les headers CORS standard avec support complet pour Authorization"""
        return [
            ('Access-Control-Allow-Origin', '*'),
            ('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS'),
            ('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-Requested-With, Accept'),
            ('Access-Control-Allow-Credentials', 'false'),  # Important pour Flutter Web
            ('Access-Control-Max-Age', '3600'),
        ]

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
            headers=self._get_cors_headers() + [('Content-Type', 'application/json')]
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
            headers=self._get_cors_headers() + [('Content-Type', 'application/json')]
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
        '/api/flutter/maintenance/requests',
        '/api/flutter/maintenance/equipment',
        '/api/flutter/maintenance/preventive',
        '/api/flutter/maintenance/history',
        '/api/flutter/maintenance/teams',
        '/api/flutter/maintenance/persons',
        '/api/flutter/user/profile',
        '/api/flutter/user/profile/update',
        '/api/flutter/user/profile/email-check',
        '/api/flutter/maintenance/dashboard',
        '/api/flutter/maintenance/all',
        '/api/flutter/maintenance/stages',
        '/api/flutter/maintenance/request-states'
    ], type='http', auth='none', methods=['OPTIONS'], csrf=False)
    def api_options(self, **kwargs):
        """Gestion des requêtes OPTIONS pour CORS"""
        return request.make_response('', headers=self._get_cors_headers())

    # OPTIONS spéciaux pour Flutter Web
    @http.route([
        '/api/flutter/maintenance/equipment/<int:equipment_id>',
        '/api/flutter/maintenance/requests/<int:request_id>'
    ], type='http', auth='none', methods=['OPTIONS'], csrf=False)
    def api_options_flutter(self, **kwargs):
        """Gestion des requêtes OPTIONS pour Flutter Web avec support Authorization"""
        # Headers CORS spéciaux pour Flutter Web avec Authorization
        flutter_headers = [
            ('Access-Control-Allow-Origin', '*'),
            ('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS'),
            ('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-Requested-With, Accept, Origin'),
            ('Access-Control-Allow-Credentials', 'false'),
            ('Access-Control-Max-Age', '86400'),  # Cache plus long
            ('Vary', 'Origin'),
        ]

        response = request.make_response('', headers=flutter_headers)
        response.status_code = 200
        return response

    # OPTIONS pour toutes les autres routes avec motifs dynamiques
    @http.route('/api/maintenance/<path:path>', type='http', auth='none', methods=['OPTIONS'], csrf=False)
    def api_options_catch_all(self, path=None, **kwargs):
        """Gestion des requêtes OPTIONS pour CORS (toutes les autres routes)"""
        return request.make_response('', headers=self._get_cors_headers())

    # ===== MAINTENANCE REQUESTS =====
    @http.route('/api/flutter/maintenance/requests', type='http', auth='none', methods=['GET'], csrf=False)
    @basic_auth_required
    def get_requests(self, limit=10000, offset=0, stage_id=None, status=None, equipment_id=None, **kwargs):
        """Récupérer les demandes de maintenance de l'utilisateur - Version Flutter Web optimisée"""
        try:
            limit = int(limit) if limit else 10000
            offset = int(offset) if offset else 0

            # Construire le domaine de recherche
            domain = self._get_allowed_requests_domain()

            # Filtre par stage_id (prioritaire sur status)
            if stage_id:
                try:
                    stage_id_int = int(stage_id)
                    domain.append(('stage_id', '=', stage_id_int))
                except (ValueError, TypeError):
                    _logger.warning(f"Ignoring invalid stage_id: {stage_id}")
            # Filtres supplémentaires
            elif status:
                # Mapper les statuts courants
                status_mapping = {
                    'new': [('stage_id.name', 'ilike', 'new')],
                    'in_progress': [('stage_id.name', 'ilike', 'progress')],
                    'done': [('stage_id.done', '=', True)],
                    'cancelled': [('kanban_state', '=', 'blocked')]
                }
                if status in status_mapping:
                    domain.extend(status_mapping[status])

            if equipment_id:
                try:
                    equipment_id_int = int(equipment_id)
                    domain.append(('equipment_id', '=', equipment_id_int))
                except (ValueError, TypeError):
                    _logger.warning(f"Ignoring invalid equipment_id: {equipment_id}")

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
                'offset': offset,
                'filters': {
                    'stage_id': int(stage_id) if stage_id and stage_id.isdigit() else None,
                    'equipment_id': int(equipment_id) if equipment_id and equipment_id.isdigit() else None,
                    'status': status
                }
            }

            # Réponse spéciale sans cookie pour Flutter Web
            response_data = {
                'success': True,
                'message': "Requests retrieved successfully",
                'data': data,
                'timestamp': fields.Datetime.now().strftime(DEFAULT_SERVER_DATETIME_FORMAT)
            }

            response = request.make_response(
                json.dumps(response_data, default=str),
                headers=self._get_cors_headers() + [('Content-Type', 'application/json')]
            )
            response.status_code = 200
            return response

        except Exception as e:
            _logger.error(f"Error getting requests: {str(e)}")
            return self._error_response(f"Error retrieving requests: {str(e)}", 500)

    @http.route('/api/flutter/maintenance/equipment/<int:equipment_id>', type='http', auth='none', methods=['GET'], csrf=False)
    @basic_auth_required
    def get_equipment_by_id(self, equipment_id, **kwargs):
        """Récupérer un équipement spécifique - Version Flutter Web optimisée"""
        try:
            domain = self._get_allowed_equipment_domain()
            domain.append(('id', '=', equipment_id))

            equipment = request.env['maintenance.equipment'].search(domain, limit=1)

            if not equipment:
                return self._error_response("Equipment not found", 404)

            data = self._serialize_equipment(equipment)

            # Réponse spéciale sans cookie pour Flutter Web
            response_data = {
                'success': True,
                'message': "Equipment retrieved successfully",
                'data': data,
                'timestamp': fields.Datetime.now().strftime(DEFAULT_SERVER_DATETIME_FORMAT)
            }

            response = request.make_response(
                json.dumps(response_data, default=str),
                headers=self._get_cors_headers() + [('Content-Type', 'application/json')]
            )
            response.status_code = 200
            return response

        except Exception as e:
            _logger.error(f"Error getting equipment {equipment_id}: {str(e)}")
            return self._error_response(f"Error retrieving equipment: {str(e)}", 500)

    @http.route('/api/flutter/maintenance/requests/<int:request_id>', type='http', auth='none', methods=['GET'], csrf=False)
    @basic_auth_required
    def get_request(self, request_id, **kwargs):
        """Récupérer une demande spécifique - Version Flutter Web optimisée"""
        try:
            domain = self._get_allowed_requests_domain()
            domain.append(('id', '=', request_id))

            maintenance_request = request.env['maintenance.request'].search(domain, limit=1)

            if not maintenance_request:
                return self._error_response("Request not found", 404)

            data = self._serialize_request(maintenance_request)

            # Réponse spéciale sans cookie pour Flutter Web
            response_data = {
                'success': True,
                'message': "Request retrieved successfully",
                'data': data,
                'timestamp': fields.Datetime.now().strftime(DEFAULT_SERVER_DATETIME_FORMAT)
            }

            response = request.make_response(
                json.dumps(response_data, default=str),
                headers=self._get_cors_headers() + [('Content-Type', 'application/json')]
            )
            response.status_code = 200
            return response

        except Exception as e:
            _logger.error(f"Error getting request {request_id}: {str(e)}")
            return self._error_response(f"Error retrieving request: {str(e)}", 500)

    @http.route('/api/flutter/maintenance/requests', type='http', auth='none', methods=['POST'], csrf=False)
    @basic_auth_required
    def create_request(self, **kwargs):
        """Créer une nouvelle demande de maintenance - Version Flutter Web optimisée"""
        try:
            # Récupérer les données JSON du body pour Flutter Web
            try:
                body = request.httprequest.data.decode('utf-8')
                data = json.loads(body) if body else {}
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                _logger.error(f"Error parsing JSON data: {str(e)}")
                return self._error_response("Invalid JSON data", 400)

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

            # Réponse spéciale sans cookie pour Flutter Web
            response_data = {
                'success': True,
                'message': "Request created successfully",
                'data': self._serialize_request(new_request),
                'timestamp': fields.Datetime.now().strftime(DEFAULT_SERVER_DATETIME_FORMAT)
            }

            response = request.make_response(
                json.dumps(response_data, default=str),
                headers=self._get_cors_headers() + [('Content-Type', 'application/json')]
            )
            response.status_code = 201
            return response

        except ValidationError as e:
            return self._error_response(f"Validation error: {str(e)}", 400)
        except Exception as e:
            _logger.error(f"Error creating request: {str(e)}")
            return self._error_response(f"Error creating request: {str(e)}", 500)

    @http.route('/api/flutter/maintenance/requests/<int:request_id>', type='http', auth='none', methods=['PUT'], csrf=False)
    @basic_auth_required
    def update_request_flutter(self, request_id, **kwargs):
        """Mettre à jour une demande de maintenance - Version Flutter Web optimisée"""
        try:
            # Vérifier les permissions
            domain = self._get_allowed_requests_domain()
            domain.append(('id', '=', request_id))

            maintenance_request = request.env['maintenance.request'].search(domain, limit=1)

            if not maintenance_request:
                return self._error_response("Request not found", 404)

            # Récupérer les données JSON du body pour Flutter Web
            try:
                # Pour les requêtes HTTP avec Flutter, les données sont dans le body
                body = request.httprequest.data.decode('utf-8')
                data = json.loads(body) if body else {}
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                _logger.error(f"Error parsing JSON data: {str(e)}")
                return self._error_response("Invalid JSON data", 400)

            # Préparer les valeurs de mise à jour
            vals = {}
            allowed_fields = [
                'name', 'description', 'schedule_date', 'priority',
                'kanban_state', 'stage_id', 'assigned_user_id', 'maintenance_team_id',
                'maintenance_type'
            ]

            for field in allowed_fields:
                if field in data:
                    vals[field] = data[field]

            # Gestion spéciale pour le changement de stage
            if 'stage_id' in vals:
                stage = request.env['maintenance.stage'].browse(vals['stage_id'])
                if stage.exists():
                    vals['stage_id'] = stage.id
                    # Si le stage est marqué comme "done", fermer automatiquement la demande
                    if stage.done:
                        vals['close_date'] = fields.Datetime.now()
                        vals['kanban_state'] = 'done'
                    else:
                        # Si on revient à un stage non-done, réouvrir la demande
                        vals['close_date'] = False
                        if vals.get('kanban_state') == 'done':
                            vals['kanban_state'] = 'normal'
                else:
                    return self._error_response(f"Stage with ID {vals['stage_id']} not found", 400)

            # Gestion spéciale pour kanban_state
            if 'kanban_state' in vals:
                valid_states = ['normal', 'blocked', 'done']
                if vals['kanban_state'] not in valid_states:
                    return self._error_response(f"Invalid kanban_state. Must be one of: {valid_states}", 400)

                # Si on marque comme done sans stage done, mettre close_date
                if vals['kanban_state'] == 'done' and not maintenance_request.stage_id.done:
                    vals['close_date'] = fields.Datetime.now()
                elif vals['kanban_state'] != 'done':
                    # Si on change de done à autre chose, enlever close_date (sauf si stage reste done)
                    if not (maintenance_request.stage_id.done or
                           (vals.get('stage_id') and request.env['maintenance.stage'].browse(vals['stage_id']).done)):
                        vals['close_date'] = False

            # Mettre à jour
            maintenance_request.write(vals)

            # Réponse spéciale sans cookie pour Flutter Web
            response_data = {
                'success': True,
                'message': "Request updated successfully",
                'data': self._serialize_request(maintenance_request),
                'updated_fields': list(vals.keys()),
                'timestamp': fields.Datetime.now().strftime(DEFAULT_SERVER_DATETIME_FORMAT)
            }

            response = request.make_response(
                json.dumps(response_data, default=str),
                headers=self._get_cors_headers() + [('Content-Type', 'application/json')]
            )
            response.status_code = 200
            return response

        except ValidationError as e:
            return self._error_response(f"Validation error: {str(e)}", 400)
        except Exception as e:
            _logger.error(f"Error updating request {request_id}: {str(e)}")
            return self._error_response(f"Error updating request: {str(e)}", 500)

    @http.route('/api/flutter/maintenance/requests/<int:request_id>', type='http', auth='none', methods=['DELETE'], csrf=False)
    @basic_auth_required
    def delete_request(self, request_id, **kwargs):
        """Supprimer une demande de maintenance - Version Flutter Web optimisée"""
        try:
            # Vérifier les permissions
            domain = self._get_allowed_requests_domain()
            domain.append(('id', '=', request_id))

            maintenance_request = request.env['maintenance.request'].search(domain, limit=1)

            if not maintenance_request:
                return self._error_response("Request not found", 404)

            # Archiver au lieu de supprimer pour conserver l'historique
            maintenance_request.action_archive()

            # Réponse spéciale sans cookie pour Flutter Web
            response_data = {
                'success': True,
                'message': "Request archived successfully",
                'data': None,
                'timestamp': fields.Datetime.now().strftime(DEFAULT_SERVER_DATETIME_FORMAT)
            }

            response = request.make_response(
                json.dumps(response_data, default=str),
                headers=self._get_cors_headers() + [('Content-Type', 'application/json')]
            )
            response.status_code = 200
            return response

        except Exception as e:
            _logger.error(f"Error deleting request {request_id}: {str(e)}")
            return self._error_response(f"Error archiving request: {str(e)}", 500)

    # ===== EQUIPMENT =====
    @http.route('/api/flutter/maintenance/equipment', type='http', auth='none', methods=['GET'], csrf=False)
    @basic_auth_required
    def get_equipment(self, limit=10000, offset=0, category_id=None, has_3d_model=None, **kwargs):
        """Récupérer les équipements - Version Flutter Web optimisée"""
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

            # Réponse spéciale sans cookie pour Flutter Web
            response_data = {
                'success': True,
                'message': "Equipment retrieved successfully",
                'data': data,
                'timestamp': fields.Datetime.now().strftime(DEFAULT_SERVER_DATETIME_FORMAT)
            }

            response = request.make_response(
                json.dumps(response_data, default=str),
                headers=self._get_cors_headers() + [('Content-Type', 'application/json')]
            )
            response.status_code = 200
            return response

        except Exception as e:
            _logger.error(f"Error getting equipment: {str(e)}")
            return self._error_response(f"Error retrieving equipment: {str(e)}", 500)
        """Récupérer le profil de l'utilisateur connecté - Version Flutter Web optimisée"""
        try:
            user = request.env.user

            # Récupérer la personne de maintenance associée si elle existe
            person = request.env['maintenance.person'].search([('user_id', '=', user.id)], limit=1)

            # Récupérer les équipes de l'utilisateur
            team_ids = self._get_user_teams()
            teams = request.env['maintenance.team'].browse(team_ids)

            # Construire les données du profil
            profile_data = {
                'user': {
                    'id': user.id,
                    'name': user.name,
                    'login': user.login,
                    'email': user.email or '',
                    'has_email': bool(user.email),
                    'active': user.active,
                    'lang': user.lang,
                    'tz': user.tz,
                    'company_id': {
                        'id': user.company_id.id,
                        'name': user.company_id.name
                    } if user.company_id else None,
                    'partner_id': {
                        'id': user.partner_id.id,
                        'name': user.partner_id.name,
                        'email': user.partner_id.email or '',
                        'phone': user.partner_id.phone or '',
                        'mobile': user.partner_id.mobile or ''
                    } if user.partner_id else None
                },
                'maintenance_person': {
                    'id': person.id,
                    'display_name': person.display_name,
                    'first_name': person.first_name or '',
                    'name': person.name or '',
                    'email': person.email or '',
                    'phone': person.phone or '',
                    'mobile': person.mobile or '',
                    'available': person.available,
                    'role': {
                        'id': person.role_id.id,
                        'name': person.role_id.name,
                        'description': person.role_id.description or ''
                    } if person.role_id else None,
                    'specialties': person.specialties or '',
                    'certifications': person.certifications or '',
                    'hire_date': person.hire_date.strftime('%Y-%m-%d') if person.hire_date else None,
                    'employee_number': person.employee_number or '',
                    'request_count': person.request_count,
                } if person else None,
                'teams': [
                    {
                        'id': team.id,
                        'name': team.name,
                        'color': team.color,
                        'member_count': len(team.member_ids)
                    } for team in teams
                ],
                'permissions': {
                    'can_create_request': True,  # Tous les utilisateurs peuvent créer des demandes
                    'can_manage_team_requests': bool(team_ids),  # Peut gérer les demandes d'équipe s'il appartient à une équipe
                    'can_assign_requests': person.role_id.can_assign_request if person and person.role_id else False,
                    'can_manage_all_requests': person.role_id.can_manage_all_requests if person and person.role_id else False,
                    'can_validate_requests': person.role_id.can_validate_requests if person and person.role_id else False,
                }
            }

            # Réponse spéciale sans cookie pour Flutter Web
            response_data = {
                'success': True,
                'message': "User profile retrieved successfully",
                'data': profile_data,
                'timestamp': fields.Datetime.now().strftime(DEFAULT_SERVER_DATETIME_FORMAT)
            }

            response = request.make_response(
                json.dumps(response_data, default=str),
                headers=self._get_cors_headers() + [('Content-Type', 'application/json')]
            )
            response.status_code = 200
            return response

        except Exception as e:
            _logger.error(f"Error getting user profile: {str(e)}")
            return self._error_response(f"Error retrieving user profile: {str(e)}", 500)

    @http.route('/api/flutter/user/profile', type='http', auth='none', methods=['GET'], csrf=False)
    @basic_auth_required
    def get_user_profile(self, **kwargs):
        """Récupérer le profil de l'utilisateur connecté - Version Flutter Web optimisée"""
        try:
            user = request.env.user

            # Récupérer la personne de maintenance associée si elle existe
            person = request.env['maintenance.person'].search([('user_id', '=', user.id)], limit=1)

            # Récupérer les équipes de l'utilisateur
            team_ids = self._get_user_teams()
            teams = request.env['maintenance.team'].browse(team_ids)

            # Construire les données du profil
            profile_data = {
                'user': {
                    'id': user.id,
                    'name': user.name,
                    'login': user.login,
                    'email': user.email or '',
                    # Ajoutez d'autres champs selon vos besoins
                },
                # Ajoutez d'autres sections selon vos besoins
            }

            return self._success_response(profile_data, "User profile retrieved successfully")

        except Exception as e:
            _logger.error(f"Error getting user profile: {str(e)}")
            return self._error_response(f"Error retrieving user profile: {str(e)}", 500)

    # Route pour mettre à jour le profil utilisateur dans Flutter Web
    @http.route('/api/flutter/user/profile/update', type='http', auth='none', methods=['PUT'], csrf=False)
    @basic_auth_required
    def update_user_profile_flutter(self, **kwargs):
        """Mettre à jour le profil de l'utilisateur connecté - Version Flutter Web optimisée"""
        try:
            user = request.env.user

            # Récupérer les données JSON du body
            try:
                body = request.httprequest.data.decode('utf-8')
                data = json.loads(body) if body else {}
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                _logger.error(f"Error parsing JSON data: {str(e)}")
                return self._error_response("Invalid JSON data", 400)

            if not data:
                return self._error_response("No data provided", 400)

            # Champs autorisés pour la mise à jour
            user_updates = {}
            partner_updates = {}
            person_updates = {}

            # Mise à jour de l'email (priorité principale)
            if 'email' in data and data['email']:
                email = data['email'].strip()

                # Vérifier que l'email est valide (simple validation)
                if '@' in email and '.' in email:
                    # Vérifier que l'email n'est pas déjà utilisé par un autre utilisateur
                    existing_user = request.env['res.users'].search([
                        ('email', '=', email),
                        ('id', '!=', user.id)
                    ], limit=1)

                    if existing_user:
                        return self._error_response(f"Email {email} is already used by another user", 400)

                    # Mettre à jour l'email sur l'utilisateur et son partner
                    user_updates['email'] = email
                    if user.partner_id:
                        partner_updates['email'] = email

                    # Mettre à jour l'email sur la personne de maintenance si elle existe
                    person = request.env['maintenance.person'].search([('user_id', '=', user.id)], limit=1)
                    if person:
                        person_updates['email'] = email
                else:
                    return self._error_response("Invalid email format", 400)

            # Autres champs optionnels
            if 'name' in data and data['name']:
                user_updates['name'] = data['name']
                if user.partner_id:
                    partner_updates['name'] = data['name']

            if 'phone' in data:
                if user.partner_id:
                    partner_updates['phone'] = data['phone']
                # Mettre à jour sur la personne de maintenance si elle existe
                person = request.env['maintenance.person'].search([('user_id', '=', user.id)], limit=1)
                if person:
                    person_updates['phone'] = data['phone']

            if 'mobile' in data:
                if user.partner_id:
                    partner_updates['mobile'] = data['mobile']
                # Mettre à jour sur la personne de maintenance si elle existe
                person = request.env['maintenance.person'].search([('user_id', '=', user.id)], limit=1)
                if person:
                    person_updates['mobile'] = data['mobile']

            # Champs spécifiques à la personne de maintenance
            person = request.env['maintenance.person'].search([('user_id', '=', user.id)], limit=1)
            if person:
                if 'first_name' in data:
                    person_updates['first_name'] = data['first_name']
                if 'specialties' in data:
                    person_updates['specialties'] = data['specialties']
                if 'certifications' in data:
                    person_updates['certifications'] = data['certifications']
                if 'available' in data:
                    person_updates['available'] = bool(data['available'])

            # Appliquer les mises à jour
            updated_fields = []

            if user_updates:
                user.write(user_updates)
                updated_fields.extend([f"user.{field}" for field in user_updates.keys()])

            if partner_updates and user.partner_id:
                user.partner_id.write(partner_updates)
                updated_fields.extend([f"partner.{field}" for field in partner_updates.keys()])

            if person_updates and person:
                person.write(person_updates)
                updated_fields.extend([f"person.{field}" for field in person_updates.keys()])

            # Réponse spéciale sans cookie pour Flutter Web
            response_data = {
                'success': True,
                'message': "Profile updated successfully",
                'updated_fields': updated_fields,
                'timestamp': fields.Datetime.now().strftime(DEFAULT_SERVER_DATETIME_FORMAT)
            }

            response = request.make_response(
                json.dumps(response_data, default=str),
                headers=self._get_cors_headers() + [('Content-Type', 'application/json')]
            )
            response.status_code = 200
            return response

        except Exception as e:
            _logger.error(f"Error updating user profile: {str(e)}")
            return self._error_response(f"Error updating profile: {str(e)}", 500)

    # Vérification email pour Flutter
    @http.route('/api/flutter/user/profile/email-check', type='http', auth='none', methods=['GET', 'POST'], csrf=False)
    @basic_auth_required
    def check_email_availability_flutter(self, **kwargs):
        """Vérifier si un email est disponible - Version Flutter Web optimisée"""
        try:
            email = None

            # Récupérer l'email selon la méthode HTTP
            if request.httprequest.method == 'GET':
                # Pour GET: récupérer l'email depuis les paramètres de query string
                email = request.httprequest.args.get('email', '').strip()

                if not email:
                    return self._error_response(
                        "Email parameter is required. Usage: GET /api/flutter/user/profile/email-check?email=your@email.com",
                        400
                    )

            elif request.httprequest.method == 'POST':
                # Pour POST: récupérer l'email depuis le body JSON
                try:
                    body = request.httprequest.data.decode('utf-8')
                    data = json.loads(body) if body else {}
                    email = data.get('email', '').strip()

                    if not email:
                        return self._error_response(
                            "Email is required in JSON body. Usage: POST /api/flutter/user/profile/email-check with {\"email\": \"your@email.com\"}",
                            400
                        )

                except (json.JSONDecodeError, UnicodeDecodeError) as e:
                    return self._error_response(
                        "Invalid JSON data in request body",
                        400
                    )

            # Validation basique du format email
            if '@' not in email or '.' not in email.split('@')[-1]:
                return self._error_response("Invalid email format", 400)

            # Vérifier si l'email est déjà utilisé (excluant l'utilisateur actuel)
            existing_user = request.env['res.users'].search([
                ('email', '=', email),
                ('id', '!=', request.env.user.id)
            ], limit=1)

            is_available = not bool(existing_user)
            current_user_has_this_email = request.env.user.email == email

            # Informations supplémentaires pour la réponse
            additional_info = {
                'email': email,
                'available': is_available,
                'current_user_email': current_user_has_this_email,
                'method_used': request.httprequest.method,
                'message': 'Available' if is_available else 'Email already in use'
            }

            # Réponse spéciale sans cookie pour Flutter Web
            response_data = {
                'success': True,
                'message': f"Email availability checked",
                'data': additional_info,
                'timestamp': fields.Datetime.now().strftime(DEFAULT_SERVER_DATETIME_FORMAT)
            }

            response = request.make_response(
                json.dumps(response_data, default=str),
                headers=self._get_cors_headers() + [('Content-Type', 'application/json')]
            )
            response.status_code = 200
            return response

        except Exception as e:
            _logger.error(f"Error checking email availability: {str(e)}")
            return self._error_response(f"Error checking email: {str(e)}", 500)

    # Dashboard pour Flutter
    @http.route('/api/flutter/maintenance/dashboard', type='http', auth='none', methods=['GET'], csrf=False)
    @basic_auth_required
    def get_dashboard_flutter(self, **kwargs):
        """Récupérer toutes les données de maintenance en un seul appel - Version Flutter Web optimisée"""
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

            # ... Autres parties du dashboard selon vos besoins...

            # Réponse spéciale sans cookie pour Flutter Web
            response_data = {
                'success': True,
                'message': "Dashboard data retrieved successfully",
                'data': dashboard_data,
                'timestamp': fields.Datetime.now().strftime(DEFAULT_SERVER_DATETIME_FORMAT)
            }

            response = request.make_response(
                json.dumps(response_data, default=str),
                headers=self._get_cors_headers() + [('Content-Type', 'application/json')]
            )
            response.status_code = 200
            return response

        except Exception as e:
            _logger.error(f"Error getting dashboard: {str(e)}")
            return self._error_response(f"Error retrieving dashboard: {str(e)}", 500)

    # All data pour Flutter
    @http.route('/api/flutter/maintenance/all', type='http', auth='none', methods=['GET'], csrf=False)
    @basic_auth_required
    def get_all_data_flutter(self, **kwargs):
        """Récupérer toutes les données (même que dashboard) - Version Flutter Web optimisée"""
        return self.get_dashboard_flutter(**kwargs)