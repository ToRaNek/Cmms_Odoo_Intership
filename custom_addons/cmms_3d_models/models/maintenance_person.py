# custom_addons/cmms_3d_models/models/maintenance_person.py - Version modifiée

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)

class MaintenancePerson(models.Model):
    _name = 'maintenance.person'
    _description = 'Personne de maintenance'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name'
    _rec_name = 'display_name'

    # Informations de base
    name = fields.Char('Nom', required=True, tracking=True)
    first_name = fields.Char('Prénom', required=True, tracking=True)
    display_name = fields.Char('Nom complet', compute='_compute_display_name', store=True)
    email = fields.Char('Email', required=False, help="Email optionnel pour créer un utilisateur Odoo")
    phone = fields.Char('Téléphone', required=False)
    mobile = fields.Char('Mobile', required=False)
    
    # Rôle
    role_id = fields.Many2one('maintenance.role', string='Rôle', required=True, tracking=True)
    
    # Informations professionnelles
    employee_number = fields.Char('Numéro d\'employé')
    hire_date = fields.Date('Date d\'embauche')
    specialties = fields.Text('Spécialités')
    certifications = fields.Text('Certifications')
    
    # Statut
    active = fields.Boolean('Actif', default=True, tracking=True)
    available = fields.Boolean('Disponible', default=True, tracking=True)
    
    # Relations
    user_id = fields.Many2one('res.users', string='Utilisateur Odoo', readonly=True)
    partner_id = fields.Many2one('res.partner', string='Contact associé', readonly=True)
    
    # Demandes de maintenance assignées (direct + relations inverse)
    assigned_request_ids = fields.One2many('maintenance.request', 'assigned_person_id', string='Demandes assignées directement')
    
    # Nouvelle relation pour les demandes via assignations multiples
    all_assigned_request_ids = fields.Many2many(
        'maintenance.request',
        string='Toutes les demandes assignées',
        compute='_compute_all_assigned_requests',
        store=True
    )
    
    # Calcul du nombre total de demandes
    request_count = fields.Integer('Nombre de demandes', compute='_compute_request_count')
    
    # Équipes
    team_ids = fields.Many2many('maintenance.team', string='Équipes de maintenance')

    @api.depends('name', 'first_name')
    def _compute_display_name(self):
        for person in self:
            if person.first_name and person.name:
                person.display_name = f"{person.first_name} {person.name}"
            else:
                person.display_name = person.name or person.first_name or 'Personne sans nom'
    
    @api.depends('assigned_request_ids', 'all_assigned_request_ids')
    def _compute_request_count(self):
        for person in self:
            # Combiner les demandes directes et les demandes via assignations
            all_requests = person.assigned_request_ids | person.all_assigned_request_ids
            person.request_count = len(all_requests)
    
    @api.depends('user_id')
    def _compute_all_assigned_requests(self):
        """Calcule toutes les demandes assignées à cette personne via les assignations multiples"""
        for person in self:
            # Rechercher les assignations où cette personne est mentionnée
            assignments = self.env['maintenance.request.assignment'].search([
                ('person_id', '=', person.id)
            ])
            
            # Récupérer les demandes correspondantes
            requests = assignments.mapped('request_id')
            
            person.all_assigned_request_ids = requests

    def _create_odoo_user(self):
        """Crée un utilisateur Odoo pour cette personne - Version simplifiée"""
        self.ensure_one()
        
        if self.user_id:
            _logger.warning(f"Utilisateur déjà existant pour {self.display_name}")
            return self.user_id
        
        # Générer un login unique basé sur le nom/prénom si pas d'email
        if self.email:
            login = self.email.lower().strip()
            partner_email = login
        else:
            # Générer un login unique basé sur nom/prénom
            base_login = f"{self.first_name.lower()}.{self.name.lower()}".replace(' ', '.')
            # Supprimer les caractères spéciaux
            import re
            base_login = re.sub(r'[^a-z0-9.]', '', base_login)
            
            # Vérifier l'unicité et ajouter un numéro si nécessaire
            login = base_login
            counter = 1
            while self.env['res.users'].search([('login', '=', login)], limit=1):
                login = f"{base_login}.{counter}"
                counter += 1
            
            partner_email = False  # Pas d'email pour le partenaire
        
        _logger.info(f"Création d'utilisateur pour {self.display_name} avec login: {login}")
        
        # 1. Créer le partenaire d'abord
        partner_vals = {
            'name': self.display_name,
            'is_company': False,
            'active': True,
        }
        
        # Ajouter l'email seulement s'il existe
        if partner_email:
            partner_vals['email'] = partner_email
            
        # Ajouter les champs optionnels s'ils ne sont pas vides
        if self.phone:
            partner_vals['phone'] = self.phone
        if self.mobile:
            partner_vals['mobile'] = self.mobile
        
        # Ajouter les champs de ranking seulement s'ils existent dans le modèle
        partner_model = self.env['res.partner']
        if 'supplier_rank' in partner_model._fields:
            partner_vals['supplier_rank'] = 0
        if 'customer_rank' in partner_model._fields:
            partner_vals['customer_rank'] = 0
        
        try:
            partner = self.env['res.partner'].create(partner_vals)
            _logger.info(f"Partenaire créé: {partner.name} (ID: {partner.id})")
        except Exception as e:
            _logger.error(f"Erreur création partenaire: {str(e)}")
            raise UserError(f"Impossible de créer le contact: {str(e)}")
        
        # 2. Créer l'utilisateur  
        user_vals = {
            'name': self.display_name,
            'login': login,
            'email': partner_email,
            'partner_id': partner.id,
            'active': self.active,
            'groups_id': [(6, 0, self._get_user_groups())],
            'notification_type': 'email' if partner_email else 'inbox',
            'tz': self.env.user.tz or 'Europe/Paris',
            'lang': self.env.user.lang or 'fr_FR',
            # Ajouter un mot de passe par défaut
            'password': 'odoo123',  # Mot de passe temporaire
        }
        
        try:
            # Créer sans email d'invitation
            user = self.env['res.users'].with_context(no_reset_password=True).create(user_vals)
            
            # Mettre à jour les références
            self.write({
                'user_id': user.id,
                'partner_id': partner.id,
            })
            
            _logger.info(f"Utilisateur créé avec succès: {user.login} pour {self.display_name}")
            return user
            
        except Exception as e:
            # Nettoyer en cas d'erreur
            if partner:
                try:
                    partner.unlink()
                except:
                    pass
            _logger.error(f"Erreur création utilisateur: {str(e)}")
            raise UserError(f"Impossible de créer l'utilisateur: {str(e)}")
    
    def _get_user_groups(self):
        """Retourne les groupes à assigner à l'utilisateur"""
        groups = [
            self.env.ref('base.group_user').id,
        ]
        
        try:
            maintenance_group = self.env.ref('maintenance.group_equipment_manager')
            if maintenance_group:
                groups.append(maintenance_group.id)
        except ValueError:
            pass
        
        return list(set(groups))
    
    @api.constrains('email')
    def _check_email_unique(self):
        """Vérification de l'unicité de l'email si rempli"""
        for person in self:
            if person.email:
                clean_email = person.email.lower().strip()
                duplicate = self.search([
                    ('email', '=', clean_email),
                    ('id', '!=', person.id),
                ], limit=1)
                if duplicate:
                    raise ValidationError(f"L'email {clean_email} est déjà utilisé par {duplicate.display_name}")
    
    def action_view_requests(self):
        """Action pour voir les demandes assignées"""
        self.ensure_one()
        
        # Combiner les demandes assignées directement et via assignations multiples
        all_requests = self.assigned_request_ids | self.all_assigned_request_ids
        
        return {
            'type': 'ir.actions.act_window',
            'name': f'Demandes de {self.display_name}',
            'res_model': 'maintenance.request',
            'view_mode': 'tree,form,kanban',
            'domain': [('id', 'in', all_requests.ids)],
            'context': {'default_assigned_person_id': self.id}
        }
    
    def action_create_user(self):
        """Action pour créer manuellement l'utilisateur - Version simplifiée"""
        self.ensure_one()
        
        if self.user_id:
            raise UserError("Un utilisateur existe déjà pour cette personne")
        
        # Plus besoin de vérifier l'email, on peut créer sans
        if not self.name or not self.first_name:
            raise UserError("Le nom et le prénom sont requis pour créer un utilisateur")
        
        try:
            user = self._create_odoo_user()
            
            msg = f'Utilisateur créé avec succès pour {self.display_name}'
            if not self.email:
                msg += f'\nLogin: {user.login}\nMot de passe temporaire: odoo123'
            else:
                msg += f'\nLogin: {user.login}\nMot de passe temporaire: odoo123'
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Utilisateur créé'),
                    'message': msg,
                    'sticky': False,
                    'type': 'success',
                }
            }
        except Exception as e:
            raise UserError(f"Erreur lors de la création de l'utilisateur: {str(e)}")
    
    def action_reset_password(self):
        """Action pour renvoyer l'invitation par email"""
        self.ensure_one()
        if not self.user_id:
            raise UserError("Aucun utilisateur associé à cette personne")
        
        if not self.email:
            raise UserError("Un email est requis pour envoyer une invitation")
        
        try:
            self.user_id.action_reset_password()
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Invitation envoyée'),
                    'message': f'Email d\'invitation envoyé à {self.email}',
                    'sticky': False,
                    'type': 'success',
                }
            }
        except Exception as e:
            raise UserError(f"Erreur lors de l'envoi de l'invitation: {str(e)}")


# Autres classes identiques...
class MaintenanceRole(models.Model):
    _name = 'maintenance.role'
    _description = 'Rôle de maintenance'
    _order = 'sequence, name'

    name = fields.Char('Nom du rôle', required=True)
    description = fields.Text('Description')
    sequence = fields.Integer('Séquence', default=10)
    active = fields.Boolean('Actif', default=True)
    color = fields.Integer('Couleur')
    
    can_create_request = fields.Boolean('Peut créer des demandes', default=True)
    can_assign_request = fields.Boolean('Peut assigner des demandes', default=False)
    can_manage_all_requests = fields.Boolean('Peut gérer toutes les demandes', default=False)
    can_validate_requests = fields.Boolean('Peut valider les demandes', default=False)
    
    person_ids = fields.One2many('maintenance.person', 'role_id', string='Personnes')
    person_count = fields.Integer('Nombre de personnes', compute='_compute_person_count')
    
    @api.depends('person_ids')
    def _compute_person_count(self):
        for role in self:
            role.person_count = len(role.person_ids)
    
    @api.model
    def create_default_roles(self):
        """Crée les rôles par défaut"""
        default_roles = [
            {'name': 'Technicien Niveau 1', 'sequence': 10, 'description': 'Technicien de maintenance de base'},
            {'name': 'Technicien Niveau 2', 'sequence': 20, 'description': 'Technicien de maintenance expérimenté'},
            {'name': 'Technicien Niveau 3', 'sequence': 30, 'description': 'Technicien de maintenance expert'},
            {'name': 'Chef d\'équipe', 'sequence': 40, 'description': 'Responsable d\'équipe de maintenance', 'can_assign_request': True},
            {'name': 'Superviseur', 'sequence': 50, 'description': 'Superviseur de maintenance', 'can_assign_request': True, 'can_validate_requests': True},
            {'name': 'Manager', 'sequence': 60, 'description': 'Manager de maintenance', 'can_assign_request': True, 'can_manage_all_requests': True, 'can_validate_requests': True},
            {'name': 'Opérateur', 'sequence': 70, 'description': 'Opérateur d\'équipement'},
            {'name': 'Responsable Qualité', 'sequence': 80, 'description': 'Responsable qualité maintenance', 'can_validate_requests': True},
        ]
        
        for role_data in default_roles:
            existing = self.search([('name', '=', role_data['name'])], limit=1)
            if not existing:
                self.create(role_data)
                _logger.info(f"Rôle créé: {role_data['name']}")


class MaintenanceRequestExtended(models.Model):
    _inherit = 'maintenance.request'
    
    assigned_user_id = fields.Many2one(
        'res.users',
        string='Assigné à',
        help="Utilisateur spécifiquement assigné à cette demande de maintenance",
        tracking=True
    )
    
    assigned_person_id = fields.Many2one(
        'maintenance.person',
        string='Personne assignée',
        help="Personne de maintenance assignée à cette demande",
        tracking=True
    )
    
    assigned_person_role = fields.Char(
        'Rôle de la personne',
        related='assigned_person_id.role_id.name',
        readonly=True
    )
    
    @api.onchange('assigned_person_id')
    def _onchange_assigned_person_id(self):
        if self.assigned_person_id and self.assigned_person_id.user_id:
            self.assigned_user_id = self.assigned_person_id.user_id
        else:
            self.assigned_user_id = False
    
    @api.onchange('assigned_user_id')
    def _onchange_assigned_user_id(self):
        if self.assigned_user_id:
            person = self.env['maintenance.person'].search([
                ('user_id', '=', self.assigned_user_id.id)
            ], limit=1)
            if person:
                self.assigned_person_id = person
        else:
            self.assigned_person_id = False


class MaintenanceTeamExtended(models.Model):
    _inherit = 'maintenance.team'
    
    person_ids = fields.Many2many(
        'maintenance.person',
        string='Membres de l\'équipe',
        help="Personnes de maintenance membres de cette équipe"
    )
    
    person_count = fields.Integer(
        'Nombre de personnes',
        compute='_compute_person_count'
    )
    
    @api.depends('person_ids')
    def _compute_person_count(self):
        for team in self:
            team.person_count = len(team.person_ids)
    
    def action_view_persons(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Membres de {self.name}',
            'res_model': 'maintenance.person',
            'view_mode': 'tree,form',
            'domain': [('team_ids', 'in', [self.id])],
            'context': {'default_team_ids': [(6, 0, [self.id])]}
        }