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
            ('Access-Control-Allow-Credentials', 'false'),
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

        # Domain de base
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

        # NOUVELLE PARTIE: Ajouter les demandes assignées via les assignations multiples
        person = request.env['maintenance.person'].search([('user_id', '=', user.id)], limit=1)
        if person:
            # Rechercher toutes les assignations de cette personne
            assignments = request.env['maintenance.request.assignment'].search([
                ('person_id', '=', person.id)
            ])

            # Ajouter les demandes correspondantes au domaine
            if assignments:
                request_ids = assignments.mapped('request_id.id')
                domain = ['|'] + domain + [('id', 'in', request_ids)]

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

    def _serialize_ifc_data(self, model3d_record):
        """Sérialise toutes les données IFC d'un modèle 3D de manière complète et structurée"""
        try:
            if not model3d_record or not model3d_record.has_ifc_file:
                return None

            # Données de base du fichier IFC
            ifc_base_data = {
                'file_info': {
                    'filename': model3d_record.ifc_filename or '',
                    'version': model3d_record.ifc_version or 'Non détectée',
                    'file_size': model3d_record.ifc_file_size or 0,
                    'download_url': model3d_record.ifc_url or None,
                },
                'parsing_info': {
                    'status': model3d_record.ifc_parsing_status or 'not_parsed',
                    'entities_count': model3d_record.ifc_entities_count or 0,
                    'entity_types': model3d_record.ifc_entity_types or '',
                    'error_message': model3d_record.ifc_parsing_error or None,
                },
                'structured_data': None,
                'raw_json': None
            }

            # Ajouter les données JSON structurées si disponibles
            if model3d_record.ifc_data_json and model3d_record.ifc_parsing_status == 'parsed':
                try:
                    # Parser le JSON des données IFC
                    ifc_json_data = json.loads(model3d_record.ifc_data_json)

                    # Extraire les informations structurées principales
                    structured_data = {
                        'header': ifc_json_data.get('header', {}),
                        'file_info': ifc_json_data.get('file_info', {}),
                        'property_sets': ifc_json_data.get('property_sets', {}),
                        'referenced_objects': ifc_json_data.get('referenced_objects', {}),
                        'summary': ifc_json_data.get('summary', {}),
                        'parsing_mode': ifc_json_data.get('parsing_mode', 'unknown')
                    }

                    # Enrichir avec des informations de maintenance spécifiques
                    maintenance_data = self._extract_maintenance_relevant_data(ifc_json_data)
                    if maintenance_data:
                        structured_data['maintenance_relevant'] = maintenance_data

                    ifc_base_data['structured_data'] = structured_data

                    # Optionnel : inclure le JSON brut pour les besoins avancés (mais limité)
                    if len(model3d_record.ifc_data_json) < 50000:  # Limite pour éviter de surcharger l'API
                        ifc_base_data['raw_json'] = ifc_json_data
                    else:
                        ifc_base_data['raw_json_note'] = 'Données JSON trop volumineuses - utilisez l\'endpoint dédié pour les récupérer'

                except json.JSONDecodeError as e:
                    _logger.error(f"Erreur de décodage JSON IFC pour le modèle {model3d_record.id}: {str(e)}")
                    ifc_base_data['parsing_info']['error_message'] = f"Erreur de décodage JSON: {str(e)}"
                except Exception as e:
                    _logger.error(f"Erreur lors du traitement des données IFC pour le modèle {model3d_record.id}: {str(e)}")
                    ifc_base_data['parsing_info']['error_message'] = f"Erreur de traitement: {str(e)}"

            return ifc_base_data

        except Exception as e:
            _logger.error(f"Erreur lors de la sérialisation IFC pour le modèle {model3d_record.id if model3d_record else 'Unknown'}: {str(e)}")
            return {
                'file_info': {'error': 'Erreur lors du chargement des données IFC'},
                'parsing_info': {'status': 'error', 'error_message': str(e)},
                'structured_data': None,
                'raw_json': None
            }

    def _extract_maintenance_relevant_data(self, ifc_json_data):
        """Extrait les données IFC particulièrement pertinentes pour la maintenance"""
        try:
            maintenance_data = {
                'materials': [],
                'properties': [],
                'quantities': [],
                'maintenance_properties': []
            }

            # Extraire les informations sur les matériaux
            referenced_objects = ifc_json_data.get('referenced_objects', {})
            for obj_id, obj_data in referenced_objects.items():
                if obj_data.get('Type') == 'IFCMATERIAL':
                    material_info = {
                        'id': obj_id,
                        'name': obj_data.get('Name'),
                        'description': obj_data.get('Description'),
                        'category': obj_data.get('Category')
                    }
                    maintenance_data['materials'].append(material_info)

            # Extraire les propriétés liées à la maintenance
            property_sets = ifc_json_data.get('property_sets', {})
            for pset_name, pset_data in property_sets.items():
                # Rechercher les propriétés de maintenance spécifiques
                properties = pset_data.get('HasProperties', [])
                for prop in properties:
                    prop_name = prop.get('Name', '').lower()

                    # Identifier les propriétés pertinentes pour la maintenance
                    if any(keyword in prop_name for keyword in ['maintenance', 'service', 'life', 'durability', 'material', 'resistance', 'conductivity']):
                        maintenance_prop = {
                            'property_set': pset_name,
                            'name': prop.get('Name'),
                            'type': prop.get('Type'),
                            'value': prop.get('NominalValue') or prop.get('Values'),
                            'unit': prop.get('Unit'),
                            'description': prop.get('Description')
                        }
                        maintenance_data['maintenance_properties'].append(maintenance_prop)

                    # Toutes les propriétés pour référence
                    general_prop = {
                        'property_set': pset_name,
                        'name': prop.get('Name'),
                        'value': prop.get('NominalValue') or prop.get('Values'),
                        'type': prop.get('Type')
                    }
                    maintenance_data['properties'].append(general_prop)

            # Filtrer les données vides
            maintenance_data = {k: v for k, v in maintenance_data.items() if v}

            return maintenance_data if maintenance_data else None

        except Exception as e:
            _logger.error(f"Erreur lors de l'extraction des données de maintenance IFC: {str(e)}")
            return None

    def _serialize_part(self, part_record):
        """Sérialiser une pièce de maintenance request avec toutes ses informations"""
        try:
            # Récupérer le sous-modèle 3D associé
            submodel = part_record.submodel_id

            # Déterminer le type d'intervention (avec gestion du champ 'other')
            intervention_display = dict(part_record._fields['intervention_type'].selection)[part_record.intervention_type]
            if part_record.intervention_type == 'other' and part_record.intervention_other:
                intervention_display = part_record.intervention_other

            part_data = {
                'id': part_record.id,
                'part_name': part_record.part_name or '',
                'description': part_record.description or '',
                'intervention_type': part_record.intervention_type,
                'intervention_type_display': intervention_display,
                'intervention_other': part_record.intervention_other or '',
                'done': part_record.done,
                'sequence': part_record.sequence,

                # Informations du sous-modèle 3D
                'submodel': {
                    'id': submodel.id if submodel else None,
                    'name': submodel.name if submodel else '',
                    'relative_id': submodel.relative_id if submodel else None,
                    'gltf_filename': submodel.gltf_filename if submodel else '',
                    'viewer_url': submodel.viewer_url if submodel else None,
                    'gltf_url': submodel.gltf_url if submodel else None,
                    'bin_url': submodel.bin_url if submodel else None,
                    'scale': submodel.scale if submodel else 1.0,
                    'position': {
                        'x': submodel.position_x if submodel else 0.0,
                        'y': submodel.position_y if submodel else 0.0,
                        'z': submodel.position_z if submodel else 0.0,
                    } if submodel else None,
                    'rotation': {
                        'x': submodel.rotation_x if submodel else 0.0,
                        'y': submodel.rotation_y if submodel else 0.0,
                        'z': submodel.rotation_z if submodel else 0.0,
                    } if submodel else None,
                } if submodel else None,

                # Informations du modèle 3D parent
                'parent_model3d': {
                    'id': part_record.parent_model3d_id.id if part_record.parent_model3d_id else None,
                    'name': part_record.parent_model3d_id.name if part_record.parent_model3d_id else '',
                    'viewer_url': part_record.parent_model3d_id.viewer_url if part_record.parent_model3d_id else None,
                } if part_record.parent_model3d_id else None,
            }

            return part_data

        except Exception as e:
            _logger.error(f"Erreur lors de la sérialisation de la pièce {part_record.id}: {str(e)}")
            return {
                'id': part_record.id,
                'part_name': part_record.part_name or '',
                'description': part_record.description or '',
                'intervention_type': part_record.intervention_type,
                'intervention_type_display': part_record.intervention_type,
                'error': 'Erreur lors du chargement des données 3D'
            }

    def _serialize_assignment(self, assignment_record):
        """Sérialiser une assignation de maintenance"""
        try:
            return {
                'id': assignment_record.id,
                'person': {
                    'id': assignment_record.person_id.id,
                    'name': assignment_record.person_id.display_name,
                    'first_name': assignment_record.person_id.first_name or '',
                    'last_name': assignment_record.person_id.name or '',
                    'email': assignment_record.person_id.email or '',
                    'phone': assignment_record.person_id.phone or '',
                    'mobile': assignment_record.person_id.mobile or '',
                    'available': assignment_record.person_id.available,
                    'role': {
                        'id': assignment_record.person_id.role_id.id if assignment_record.person_id.role_id else None,
                        'name': assignment_record.person_id.role_id.name if assignment_record.person_id.role_id else '',
                        'description': assignment_record.person_id.role_id.description if assignment_record.person_id.role_id else '',
                    } if assignment_record.person_id.role_id else None,
                    'specialties': assignment_record.person_id.specialties or '',
                    'certifications': assignment_record.person_id.certifications or '',
                },
                'user': {
                    'id': assignment_record.user_id.id if assignment_record.user_id else None,
                    'name': assignment_record.user_id.name if assignment_record.user_id else '',
                    'login': assignment_record.user_id.login if assignment_record.user_id else '',
                } if assignment_record.user_id else None,
                'assigned_date': assignment_record.assigned_date.strftime(DEFAULT_SERVER_DATETIME_FORMAT) if assignment_record.assigned_date else None,
                'assigned_by': {
                    'id': assignment_record.assigned_by_id.id if assignment_record.assigned_by_id else None,
                    'name': assignment_record.assigned_by_id.name if assignment_record.assigned_by_id else '',
                } if assignment_record.assigned_by_id else None,
                'is_primary': assignment_record.is_primary,
                'notes': assignment_record.notes or '',
            }
        except Exception as e:
            _logger.error(f"Erreur lors de la sérialisation de l'assignation {assignment_record.id}: {str(e)}")
            return {
                'id': assignment_record.id,
                'person': {
                    'id': assignment_record.person_id.id,
                    'name': assignment_record.person_id.display_name,
                },
                'error': 'Erreur lors du chargement des données d\'assignation'
            }

    def _serialize_request(self, request_record):
        """Sérialiser une demande de maintenance avec toutes les informations enrichies INCLUANT LES DONNÉES IFC"""
        try:
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

            # Sérialiser toutes les assignations
            assignments = []
            if hasattr(request_record, 'assignment_ids') and request_record.assignment_ids:
                for assignment in request_record.assignment_ids:
                    assignments.append(self._serialize_assignment(assignment))

            # Préparer la liste de toutes les personnes assignées
            assigned_persons = []
            if hasattr(request_record, 'assigned_person_ids') and request_record.assigned_person_ids:
                for person in request_record.assigned_person_ids:
                    assigned_persons.append({
                        'id': person.id,
                        'name': person.display_name,
                        'first_name': person.first_name or '',
                        'last_name': person.name or '',
                        'email': person.email or '',
                        'phone': person.phone or '',
                        'role': {
                            'id': person.role_id.id if person.role_id else None,
                            'name': person.role_id.name if person.role_id else None,
                        } if person.role_id else None,
                        'available': person.available,
                    })

            # NOUVEAU: Sérialiser toutes les pièces/sous-modèles
            parts = []
            if hasattr(request_record, 'part_ids') and request_record.part_ids:
                for part in request_record.part_ids:
                    parts.append(self._serialize_part(part))

            # Informations sur l'équipement enrichies
            equipment_info = None
            if request_record.equipment_id:
                equipment = request_record.equipment_id
                equipment_info = {
                    'id': equipment.id,
                    'name': equipment.name,
                    'serial_no': equipment.serial_no or '',
                    'location': equipment.location or '',
                    'category': {
                        'id': equipment.category_id.id if equipment.category_id else None,
                        'name': equipment.category_id.name if equipment.category_id else '',
                    } if equipment.category_id else None,
                    'model_3d': {
                        'id': equipment.model3d_id.id if equipment.model3d_id else None,
                        'name': equipment.model3d_id.name if equipment.model3d_id else '',
                        'viewer_url': viewer_url,
                        'has_ifc': equipment.model3d_id.has_ifc_file if equipment.model3d_id else False,
                        'ifc_version': equipment.model3d_id.ifc_version if equipment.model3d_id else None,
                        'ifc_url': equipment.model3d_id.ifc_url if equipment.model3d_id else None,
                    } if equipment.model3d_id else None,
                    'has_3d_model': bool(equipment.model3d_id),
                }

                # NOUVEAU: Ajouter les données IFC complètes si disponibles
                if equipment.model3d_id and equipment.model3d_id.has_ifc_file:
                    equipment_info['model_3d']['ifc_data'] = self._serialize_ifc_data(equipment.model3d_id)

            # Construire la réponse complète
            request_data = {
                'id': request_record.id,
                'name': request_record.name,
                'description': request_record.description or '',
                'request_date': request_record.request_date.strftime(DEFAULT_SERVER_DATETIME_FORMAT) if request_record.request_date else None,
                'schedule_date': request_record.schedule_date.strftime(DEFAULT_SERVER_DATETIME_FORMAT) if request_record.schedule_date else None,
                'close_date': request_record.close_date.strftime(DEFAULT_SERVER_DATETIME_FORMAT) if request_record.close_date else None,

                # Statut et étape
                'stage': {
                    'id': request_record.stage_id.id if request_record.stage_id else None,
                    'name': request_record.stage_id.name if request_record.stage_id else '',
                    'done': request_record.stage_id.done if request_record.stage_id else False,
                } if request_record.stage_id else None,
                'maintenance_type': request_record.maintenance_type,
                'priority': request_record.priority,
                'kanban_state': request_record.kanban_state,
                'color': request_record.color,
                'duration': request_record.duration,

                # Équipement enrichi AVEC DONNÉES IFC
                'equipment': equipment_info,

                # Équipe
                'maintenance_team': {
                    'id': request_record.maintenance_team_id.id if request_record.maintenance_team_id else None,
                    'name': request_record.maintenance_team_id.name if request_record.maintenance_team_id else '',
                } if request_record.maintenance_team_id else None,

                # Utilisateurs (compatibilité)
                'user': {
                    'id': request_record.user_id.id if request_record.user_id else None,
                    'name': request_record.user_id.name if request_record.user_id else '',
                } if request_record.user_id else None,
                'assigned_user': {
                    'id': assigned_user.id if assigned_user else None,
                    'name': assigned_user.name if assigned_user else '',
                } if assigned_user else None,
                'owner_user': {
                    'id': request_record.owner_user_id.id if hasattr(request_record, 'owner_user_id') and request_record.owner_user_id else None,
                    'name': request_record.owner_user_id.name if hasattr(request_record, 'owner_user_id') and request_record.owner_user_id else '',
                } if hasattr(request_record, 'owner_user_id') and request_record.owner_user_id else None,
                'technician_user': {
                    'id': request_record.technician_user_id.id if hasattr(request_record, 'technician_user_id') and request_record.technician_user_id else None,
                    'name': request_record.technician_user_id.name if hasattr(request_record, 'technician_user_id') and request_record.technician_user_id else '',
                } if hasattr(request_record, 'technician_user_id') and request_record.technician_user_id else None,

                # Assignations enrichies
                'assigned_person': {
                    'id': request_record.assigned_person_id.id if hasattr(request_record, 'assigned_person_id') and request_record.assigned_person_id else None,
                    'name': request_record.assigned_person_id.display_name if hasattr(request_record, 'assigned_person_id') and request_record.assigned_person_id else '',
                    'role': request_record.assigned_person_id.role_id.name if hasattr(request_record, 'assigned_person_id') and request_record.assigned_person_id and request_record.assigned_person_id.role_id else None,
                } if hasattr(request_record, 'assigned_person_id') and request_record.assigned_person_id else None,
                'assigned_persons': assigned_persons,
                'assignments': assignments,

                # NOUVEAU: Pièces/sous-modèles avec visualisation 3D
                'parts': parts,
                'parts_count': len(parts),

                # Compteurs
                'assignment_count': len(assignments),
            }

            return request_data

        except Exception as e:
            _logger.error(f"Erreur lors de la sérialisation de la demande {request_record.id}: {str(e)}")
            # Retourner une version minimale en cas d'erreur
            return {
                'id': request_record.id,
                'name': request_record.name,
                'description': request_record.description or '',
                'error': 'Erreur lors du chargement des données complètes'
            }

    def _serialize_equipment(self, equipment_record):
        """Sérialiser un équipement AVEC DONNÉES IFC"""
        # URLs des modèles 3D
        model_3d_url = None
        viewer_url = None
        if equipment_record.model3d_id:
            model_3d_url = equipment_record.model3d_id.model_url
            viewer_url = equipment_record.model3d_id.viewer_url

        equipment_data = {
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
                'viewer_url': viewer_url,
                'has_ifc': equipment_record.model3d_id.has_ifc_file,
                'ifc_version': equipment_record.model3d_id.ifc_version,
                'ifc_url': equipment_record.model3d_id.ifc_url,
            } if equipment_record.model3d_id else None,
            'assign_date': equipment_record.assign_date.strftime(DEFAULT_SERVER_DATETIME_FORMAT) if equipment_record.assign_date else None,
            'cost': float(equipment_record.cost) if equipment_record.cost else 0.0,
            'note': equipment_record.note or '',
            'warranty_date': equipment_record.warranty_date.strftime('%Y-%m-%d') if equipment_record.warranty_date else None,
            'color': equipment_record.color,
            'cost_center': equipment_record.cost_center or '' if hasattr(equipment_record, 'cost_center') else '',
        }

        # NOUVEAU: Ajouter les données IFC complètes si disponibles
        if equipment_record.model3d_id and equipment_record.model3d_id.has_ifc_file:
            equipment_data['model3d_id']['ifc_data'] = self._serialize_ifc_data(equipment_record.model3d_id)

        return equipment_data

    # ===== NOUVELLES ROUTES POUR LES DONNÉES IFC =====

    @http.route('/api/flutter/maintenance/ifc/<int:model3d_id>', type='http', auth='none', methods=['GET'], csrf=False)
    @basic_auth_required
    def get_ifc_data(self, model3d_id, **kwargs):
        """Récupérer les données IFC complètes d'un modèle 3D"""
        try:
            model3d = request.env['cmms.model3d'].sudo().browse(model3d_id)

            if not model3d.exists():
                return self._error_response("Model 3D not found", 404)

            if not model3d.has_ifc_file:
                return self._error_response("No IFC file associated with this 3D model", 404)

            # Sérialiser toutes les données IFC
            ifc_data = self._serialize_ifc_data(model3d)

            if not ifc_data:
                return self._error_response("Failed to load IFC data", 500)

            return self._success_response(
                ifc_data,
                f"IFC data retrieved successfully for model {model3d.name}"
            )

        except Exception as e:
            _logger.error(f"Error getting IFC data for model {model3d_id}: {str(e)}")
            return self._error_response(f"Error retrieving IFC data: {str(e)}", 500)

    @http.route('/api/flutter/maintenance/ifc/<int:model3d_id>/raw', type='http', auth='none', methods=['GET'], csrf=False)
    @basic_auth_required
    def get_ifc_raw_data(self, model3d_id, **kwargs):
        """Récupérer les données IFC JSON brutes complètes d'un modèle 3D"""
        try:
            model3d = request.env['cmms.model3d'].sudo().browse(model3d_id)

            if not model3d.exists():
                return self._error_response("Model 3D not found", 404)

            if not model3d.has_ifc_file or not model3d.ifc_data_json:
                return self._error_response("No IFC JSON data available for this 3D model", 404)

            try:
                # Parser et retourner le JSON brut complet
                raw_ifc_data = json.loads(model3d.ifc_data_json)

                response_data = {
                    'model_info': {
                        'id': model3d.id,
                        'name': model3d.name,
                        'ifc_filename': model3d.ifc_filename,
                        'ifc_version': model3d.ifc_version,
                        'parsing_status': model3d.ifc_parsing_status,
                        'entities_count': model3d.ifc_entities_count,
                    },
                    'ifc_raw_data': raw_ifc_data
                }

                return self._success_response(
                    response_data,
                    f"Raw IFC JSON data retrieved successfully for model {model3d.name}"
                )

            except json.JSONDecodeError as e:
                return self._error_response(f"Invalid IFC JSON data: {str(e)}", 500)

        except Exception as e:
            _logger.error(f"Error getting raw IFC data for model {model3d_id}: {str(e)}")
            return self._error_response(f"Error retrieving raw IFC data: {str(e)}", 500)

    @http.route('/api/flutter/maintenance/ifc/search', type='http', auth='none', methods=['GET'], csrf=False)
    @basic_auth_required
    def search_ifc_data(self, property_name=None, property_value=None, entity_type=None, **kwargs):
        """Rechercher dans les données IFC de tous les modèles accessibles"""
        try:
            # Récupérer tous les modèles 3D avec des données IFC
            models_with_ifc = request.env['cmms.model3d'].search([
                ('has_ifc_file', '=', True),
                ('ifc_parsing_status', '=', 'parsed'),
                ('ifc_data_json', '!=', False)
            ])

            search_results = []

            for model in models_with_ifc:
                try:
                    ifc_data = json.loads(model.ifc_data_json)

                    # Recherche dans les PropertySets
                    property_sets = ifc_data.get('property_sets', {})
                    for pset_name, pset_data in property_sets.items():
                        properties = pset_data.get('HasProperties', [])

                        for prop in properties:
                            prop_name = prop.get('Name', '').lower()
                            prop_value = str(prop.get('NominalValue', '') or prop.get('Values', '')).lower()

                            # Filtres de recherche
                            matches = True

                            if property_name and property_name.lower() not in prop_name:
                                matches = False

                            if property_value and property_value.lower() not in prop_value:
                                matches = False

                            if matches:
                                search_results.append({
                                    'model': {
                                        'id': model.id,
                                        'name': model.name,
                                        'ifc_filename': model.ifc_filename
                                    },
                                    'property_set': pset_name,
                                    'property': {
                                        'name': prop.get('Name'),
                                        'value': prop.get('NominalValue') or prop.get('Values'),
                                        'type': prop.get('Type'),
                                        'unit': prop.get('Unit'),
                                        'description': prop.get('Description')
                                    }
                                })

                    # Recherche dans les objets référencés
                    if entity_type:
                        referenced_objects = ifc_data.get('referenced_objects', {})
                        for obj_id, obj_data in referenced_objects.items():
                            if obj_data.get('Type', '').upper() == entity_type.upper():
                                search_results.append({
                                    'model': {
                                        'id': model.id,
                                        'name': model.name,
                                        'ifc_filename': model.ifc_filename
                                    },
                                    'entity_type': obj_data.get('Type'),
                                    'entity_id': obj_id,
                                    'entity_data': obj_data
                                })

                except json.JSONDecodeError:
                    _logger.warning(f"Invalid JSON in IFC data for model {model.id}")
                    continue

            return self._success_response({
                'search_criteria': {
                    'property_name': property_name,
                    'property_value': property_value,
                    'entity_type': entity_type
                },
                'results_count': len(search_results),
                'results': search_results
            }, f"IFC search completed - {len(search_results)} results found")

        except Exception as e:
            _logger.error(f"Error searching IFC data: {str(e)}")
            return self._error_response(f"Error searching IFC data: {str(e)}", 500)

    # ===== OPTIONS (CORS) MISES À JOUR =====
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
        '/api/flutter/maintenance/request-states',
        '/api/flutter/maintenance/ifc/<int:model3d_id>',
        '/api/flutter/maintenance/ifc/<int:model3d_id>/raw',
        '/api/flutter/maintenance/ifc/search'
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

    # ===== MAINTENANCE REQUESTS AVEC DONNÉES IFC =====
    @http.route('/api/flutter/maintenance/requests', type='http', auth='none', methods=['GET'], csrf=False)
    @basic_auth_required
    def get_requests(self, limit=10000, offset=0, stage_id=None, status=None, equipment_id=None, include_ifc=None, **kwargs):
        """Récupérer les demandes de maintenance avec pièces, assignations ET DONNÉES IFC complètes"""
        try:
            limit = int(limit) if limit else 10000
            offset = int(offset) if offset else 0
            include_ifc_data = include_ifc and include_ifc.lower() in ['true', '1', 'yes']

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

            # Récupérer les demandes avec toutes les relations
            requests = request.env['maintenance.request'].search(
                domain,
                limit=limit,
                offset=offset,
                order='request_date desc, id desc'
            )

            # Précharger toutes les relations pour optimiser les performances
            requests.read(['assignment_ids', 'part_ids', 'equipment_id', 'assigned_person_ids'])

            # Sérialiser les données avec toutes les informations enrichies (y compris IFC)
            data = {
                'requests': [self._serialize_request(req) for req in requests],
                'total_count': request.env['maintenance.request'].search_count(domain),
                'limit': limit,
                'offset': offset,
                'include_ifc_data': include_ifc_data,
                'filters': {
                    'stage_id': int(stage_id) if stage_id and stage_id.isdigit() else None,
                    'equipment_id': int(equipment_id) if equipment_id and equipment_id.isdigit() else None,
                    'status': status
                }
            }

            # Ajouter des statistiques utiles
            if requests:
                ifc_equipped_count = len([req for req in requests
                                        if req.equipment_id and req.equipment_id.model3d_id
                                        and req.equipment_id.model3d_id.has_ifc_file])

                data['statistics'] = {
                    'total_parts': sum(len(req.part_ids) for req in requests),
                    'total_assignments': sum(len(req.assignment_ids) for req in requests),
                    'requests_with_3d': len([req for req in requests if req.equipment_id and req.equipment_id.model3d_id]),
                    'requests_with_parts': len([req for req in requests if req.part_ids]),
                    'requests_with_ifc': ifc_equipped_count,
                }

            # Message spécial si des données IFC sont incluses
            message = "Requests with parts and assignments retrieved successfully"
            if include_ifc_data:
                message += " (including IFC BIM data)"

            return self._success_response(data, message)

        except Exception as e:
            _logger.error(f"Error getting requests: {str(e)}")
            return self._error_response(f"Error retrieving requests: {str(e)}", 500)

    @http.route('/api/flutter/maintenance/requests/<int:request_id>', type='http', auth='none', methods=['GET'], csrf=False)
    @basic_auth_required
    def get_request(self, request_id, include_ifc=None, **kwargs):
        """Récupérer une demande spécifique avec toutes ses pièces, assignations ET DONNÉES IFC"""
        try:
            include_ifc_data = include_ifc and include_ifc.lower() in ['true', '1', 'yes']

            domain = self._get_allowed_requests_domain()
            domain.append(('id', '=', request_id))

            maintenance_request = request.env['maintenance.request'].search(domain, limit=1)

            if not maintenance_request:
                return self._error_response("Request not found", 404)

            # Précharger toutes les relations
            maintenance_request.read(['assignment_ids', 'part_ids', 'equipment_id', 'assigned_person_ids'])

            # Sérialiser avec toutes les données enrichies (y compris IFC automatiquement)
            data = self._serialize_request(maintenance_request)

            # Ajouter des informations supplémentaires pour la vue détaillée
            has_ifc = (maintenance_request.equipment_id and
                      maintenance_request.equipment_id.model3d_id and
                      maintenance_request.equipment_id.model3d_id.has_ifc_file)

            data['detailed_info'] = {
                'can_edit': True,  # Logique à adapter selon vos besoins
                'has_parts': len(maintenance_request.part_ids) > 0,
                'has_assignments': len(maintenance_request.assignment_ids) > 0,
                'has_3d_model': bool(maintenance_request.equipment_id and maintenance_request.equipment_id.model3d_id),
                'has_ifc_data': has_ifc,
                'ifc_data_included': include_ifc_data,
                'created_date': maintenance_request.create_date.strftime(DEFAULT_SERVER_DATETIME_FORMAT) if maintenance_request.create_date else None,
                'last_update': maintenance_request.write_date.strftime(DEFAULT_SERVER_DATETIME_FORMAT) if maintenance_request.write_date else None,
            }

            # Message adapté selon les données IFC
            message = "Request with complete details retrieved successfully"
            if has_ifc:
                message += " (including IFC BIM data)"

            return self._success_response(data, message)

        except Exception as e:
            _logger.error(f"Error getting request {request_id}: {str(e)}")
            return self._error_response(f"Error retrieving request: {str(e)}", 500)
    # OPTIONS pour la route de mise à jour des pièces de requête de maintenance
    @http.route('/api/flutter/maintenance/requests/<int:request_id>/part/<int:part_id>',
                type='http', auth='none', methods=['OPTIONS'], csrf=False)
    def api_options_request_part_update(self, **kwargs):
        """Gestion des requêtes OPTIONS pour la mise à jour des pièces de requête"""
        flutter_headers = [
            ('Access-Control-Allow-Origin', '*'),
            ('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS'),
            ('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-Requested-With, Accept, Origin'),
            ('Access-Control-Allow-Credentials', 'false'),
            ('Access-Control-Max-Age', '86400'),
            ('Vary', 'Origin'),
        ]
        response = request.make_response('', headers=flutter_headers)
        response.status_code = 200
        return response

    # Route pour mettre à jour une pièce d'une requête de maintenance spécifique
    @http.route('/api/flutter/maintenance/requests/<int:request_id>/part/<int:part_id>',
                type='http', auth='none', methods=['PUT', 'GET'],
                csrf=False, cors='*')
    def update_maintenance_request_part(self, request_id, part_id, **kwargs):
        """API pour mettre à jour une pièce d'une requête de maintenance"""
        try:
            if request.httprequest.method == 'GET':
                return self._get_maintenance_request_part(request_id, part_id)

            elif request.httprequest.method == 'PUT':
                return self._update_maintenance_request_part(request_id, part_id, **kwargs)

        except Exception as e:
            return request.make_response(
                json.dumps({'error': str(e)}),
                headers=[('Content-Type', 'application/json')],
                status=500
            )

    def _get_maintenance_request_part(self, request_id, part_id):
        """Récupérer les données d'une pièce spécifique d'une requête"""
        try:
            # Utiliser sudo() pour contourner les restrictions d'accès
            part = request.env['maintenance.request.part'].sudo().browse(part_id)

            if not part.exists():
                return request.make_response(
                    json.dumps({'error': 'Pièce non trouvée'}),
                    headers=[('Content-Type', 'application/json')],
                    status=404
                )

            # Vérifier que la pièce appartient bien à la requête de maintenance
            if part.request_id.id != request_id:
                return request.make_response(
                    json.dumps({'error': 'Pièce non associée à cette requête de maintenance'}),
                    headers=[('Content-Type', 'application/json')],
                    status=400
                )

            # Sérialiser la pièce
            part_data = self._serialize_part(part)

            return request.make_response(
                json.dumps({
                    'success': True,
                    'data': part_data
                }),
                headers=[('Content-Type', 'application/json')]
            )

        except Exception as e:
            return request.make_response(
                json.dumps({'error': f'Erreur lors de la récupération: {str(e)}'}),
                headers=[('Content-Type', 'application/json')],
                status=500
            )

    def _update_maintenance_request_part(self, request_id, part_id, **kwargs):
        """Mettre à jour une pièce d'une requête de maintenance"""
        try:
            # Récupérer les données JSON du body
            data = json.loads(request.httprequest.data.decode('utf-8'))

            # Utiliser sudo() pour contourner les restrictions d'accès
            part = request.env['maintenance.request.part'].sudo().browse(part_id)

            if not part.exists():
                return request.make_response(
                    json.dumps({'error': 'Pièce non trouvée'}),
                    headers=[('Content-Type', 'application/json')],
                    status=404
                )

            # Vérifier que la pièce appartient bien à la requête de maintenance
            if part.request_id.id != request_id:
                return request.make_response(
                    json.dumps({'error': 'Pièce non associée à cette requête de maintenance'}),
                    headers=[('Content-Type', 'application/json')],
                    status=400
                )

            # Préparer les valeurs à mettre à jour
            update_vals = {}

            # Champs autorisés à être mis à jour
            allowed_fields = [
                'intervention_type',
                'intervention_other',
                'description',
                'done',
                'sequence'
            ]

            for field in allowed_fields:
                if field in data:
                    update_vals[field] = data[field]

            # Validation spécifique pour intervention_type
            if 'intervention_type' in update_vals:
                valid_types = ['repair', 'replace', 'check', 'clean', 'other']
                if update_vals['intervention_type'] not in valid_types:
                    return request.make_response(
                        json.dumps({'error': f'Type d\'intervention invalide. Types autorisés: {valid_types}'}),
                        headers=[('Content-Type', 'application/json')],
                        status=400
                    )

            # Validation pour intervention_other (obligatoire si type = other)
            if update_vals.get('intervention_type') == 'other' and not update_vals.get('intervention_other'):
                return request.make_response(
                    json.dumps({'error': 'Le champ "intervention_other" est obligatoire quand le type est "other"'}),
                    headers=[('Content-Type', 'application/json')],
                    status=400
                )

            # Mettre à jour la pièce avec sudo()
            if update_vals:
                part.write(update_vals)

            # Sérialiser la pièce mise à jour
            updated_part_data = self._serialize_part(part)

            # Retourner la réponse de succès
            return request.make_response(
                json.dumps({
                    'success': True,
                    'message': 'Pièce mise à jour avec succès',
                    'data': updated_part_data
                }),
                headers=[('Content-Type', 'application/json')]
            )

        except json.JSONDecodeError:
            return request.make_response(
                json.dumps({'error': 'Format JSON invalide'}),
                headers=[('Content-Type', 'application/json')],
                status=400
            )
        except Exception as e:
            return request.make_response(
                json.dumps({'error': f'Erreur lors de la mise à jour: {str(e)}'}),
                headers=[('Content-Type', 'application/json')],
                status=500
            )

    @http.route('/api/flutter/maintenance/equipment/<int:equipment_id>', type='http', auth='none', methods=['GET'], csrf=False)
    @basic_auth_required
    def get_equipment_by_id(self, equipment_id, include_ifc=None, **kwargs):
        """Récupérer un équipement spécifique AVEC DONNÉES IFC - Version Flutter Web optimisée"""
        try:
            include_ifc_data = include_ifc and include_ifc.lower() in ['true', '1', 'yes']

            domain = self._get_allowed_equipment_domain()
            domain.append(('id', '=', equipment_id))

            equipment = request.env['maintenance.equipment'].search(domain, limit=1)

            if not equipment:
                return self._error_response("Equipment not found", 404)

            # La sérialisation inclut automatiquement les données IFC si disponibles
            data = self._serialize_equipment(equipment)

            # Message adapté selon les données IFC
            message = "Equipment retrieved successfully"
            if equipment.model3d_id and equipment.model3d_id.has_ifc_file:
                message += " (including IFC BIM data)"

            return self._success_response(data, message)

        except Exception as e:
            _logger.error(f"Error getting equipment {equipment_id}: {str(e)}")
            return self._error_response(f"Error retrieving equipment: {str(e)}", 500)

    # Autres méthodes existantes continuent ici...
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

            # La sérialisation incluera automatiquement les données IFC si l'équipement en a
            return self._success_response(
                self._serialize_request(new_request),
                "Request created successfully"
            )

        except ValidationError as e:
            return self._error_response(f"Validation error: {str(e)}", 400)
        except Exception as e:
            _logger.error(f"Error creating request: {str(e)}")
            return self._error_response(f"Error creating request: {str(e)}", 500)

    # Continuer avec les autres méthodes existantes...
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

            return self._success_response(profile_data, "User profile retrieved successfully")

        except Exception as e:
            _logger.error(f"Error getting user profile: {str(e)}")
            return self._error_response(f"Error retrieving user profile: {str(e)}", 500)

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