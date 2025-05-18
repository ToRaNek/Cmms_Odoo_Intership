# custom_addons/cmms_3d_models/models/maintenance_person.py
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)

class MaintenanceRole(models.Model):
    _name = 'maintenance.role'
    _description = 'Rôle de maintenance'
    _order = 'sequence, name'

    name = fields.Char('Nom du rôle', required=True)
    description = fields.Text('Description')
    sequence = fields.Integer('Séquence', default=10)
    active = fields.Boolean('Actif', default=True)
    color = fields.Integer('Couleur')
    
    # Permissions de base (pour plus tard)
    can_create_request = fields.Boolean('Peut créer des demandes', default=True)
    can_assign_request = fields.Boolean('Peut assigner des demandes', default=False)
    can_manage_all_requests = fields.Boolean('Peut gérer toutes les demandes', default=False)
    can_validate_requests = fields.Boolean('Peut valider les demandes', default=False)
    
    # Relation avec les personnes
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
    email = fields.Char('Email', required=False, help="Email requis pour créer un utilisateur Odoo")
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
    
    # Demandes de maintenance assignées
    assigned_request_ids = fields.One2many('maintenance.request', 'assigned_user_id', string='Demandes assignées')
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
    
    @api.depends('user_id')
    def _compute_request_count(self):
        for person in self:
            if person.user_id:
                person.request_count = self.env['maintenance.request'].search_count(
                    [('assigned_user_id', '=', person.user_id.id)]
                )
            else:
                person.request_count = 0
    
    @api.model
    def create(self, vals):
        """Override create pour créer automatiquement l'utilisateur Odoo"""
        # Valider l'email avant la création
        if 'email' in vals and vals['email']:
            if '@' not in vals['email']:
                raise ValidationError(f"Format d'email invalide: {vals['email']}")
        
        person = super(MaintenancePerson, self).create(vals)
        
        # Créer l'utilisateur seulement si tous les champs requis sont présents
        if person.email and person.name and person.first_name:
            try:
                person._create_odoo_user()
            except Exception as e:
                _logger.warning(f"Impossible de créer l'utilisateur pour {person.display_name}: {str(e)}")
        
        return person
    
    def write(self, vals):
        """Override write pour mettre à jour l'utilisateur si nécessaire"""
        res = super(MaintenancePerson, self).write(vals)
        
        # Mettre à jour l'utilisateur si email, nom ou prénom change
        if any(field in vals for field in ['email', 'name', 'first_name']):
            for person in self:
                try:
                    person._update_odoo_user()
                except Exception as e:
                    _logger.warning(f"Impossible de mettre à jour l'utilisateur pour {person.display_name}: {str(e)}")
        
        return res
    
    def _create_odoo_user(self):
        """Crée un utilisateur Odoo pour cette personne"""
        self.ensure_one()
        
        if self.user_id:
            _logger.warning(f"Utilisateur déjà existant pour {self.display_name}")
            return
        
        if not self.email:
            raise UserError("Un email est requis pour créer un utilisateur Odoo")
        
        if '@' not in self.email:
            raise UserError(f"Format d'email invalide: {self.email}")
        
        # Vérifier si l'email est déjà utilisé par un autre utilisateur
        existing_user = self.env['res.users'].search([
            ('login', '=', self.email),
            ('active', 'in', [True, False])  # Inclure les utilisateurs archivés
        ], limit=1)
        
        if existing_user:
            raise UserError(f"L'email {self.email} est déjà utilisé par l'utilisateur {existing_user.name}")
        
        # Créer d'abord le partenaire
        partner_vals = {
            'name': self.display_name,
            'email': self.email,
            'phone': self.phone,
            'mobile': self.mobile,
            'is_company': False,
            'supplier_rank': 0,
            'customer_rank': 0,
        }
        
        try:
            partner = self.env['res.partner'].create(partner_vals)
        except Exception as e:
            _logger.error(f"Erreur lors de la création du partenaire pour {self.display_name}: {str(e)}")
            raise UserError(f"Impossible de créer le contact: {str(e)}")
        
        # Créer l'utilisateur
        user_vals = {
            'name': self.display_name,
            'login': self.email,
            'email': self.email,
            'partner_id': partner.id,
            'groups_id': [(6, 0, self._get_user_groups())],
            'active': self.active,
        }
        
        try:
            user = self.env['res.users'].create(user_vals)
            self.write({
                'user_id': user.id,
                'partner_id': partner.id,
            })
            _logger.info(f"Utilisateur créé: {user.login} pour {self.display_name}")
            
            # Envoyer l'invitation par email
            try:
                user.action_reset_password()
            except Exception as e:
                _logger.warning(f"Impossible d'envoyer l'invitation à {self.email}: {str(e)}")
            
        except Exception as e:
            # Supprimer le partenaire créé en cas d'erreur
            if partner:
                try:
                    partner.unlink()
                except:
                    pass
            _logger.error(f"Erreur lors de la création de l'utilisateur pour {self.display_name}: {str(e)}")
            raise UserError(f"Impossible de créer l'utilisateur: {str(e)}")
    
    def _update_odoo_user(self):
        """Met à jour l'utilisateur Odoo associé"""
        self.ensure_one()
        
        if not self.user_id:
            return
        
        try:
            # Mettre à jour le partenaire
            if self.partner_id:
                self.partner_id.write({
                    'name': self.display_name,
                    'email': self.email,
                    'phone': self.phone,
                    'mobile': self.mobile,
                })
            
            # Mettre à jour l'utilisateur
            self.user_id.write({
                'name': self.display_name,
                'login': self.email,
                'email': self.email,
                'active': self.active,
            })
        except Exception as e:
            _logger.error(f"Erreur lors de la mise à jour de l'utilisateur pour {self.display_name}: {str(e)}")
    
    def _get_user_groups(self):
        """Retourne les groupes à assigner à l'utilisateur selon son rôle"""
        # Groupes de base pour tous les utilisateurs de maintenance
        groups = [
            self.env.ref('base.group_user').id,  # Utilisateur interne
        ]
        
        # Ajouter le groupe de maintenance si il existe
        try:
            maintenance_groups = [
                'maintenance.group_equipment_manager',
                'base.group_user',
            ]
            
            for group_xml_id in maintenance_groups:
                try:
                    group = self.env.ref(group_xml_id)
                    if group:
                        groups.append(group.id)
                        break
                except ValueError:
                    continue
        except Exception as e:
            _logger.warning(f"Erreur lors de la récupération des groupes: {str(e)}")
        
        return list(set(groups))  # Supprimer les doublons
    
    @api.constrains('email')
    def _check_email_unique(self):
        for person in self:
            if person.email:
                # Vérifier l'unicité avec d'autres personnes (seulement si l'email n'est pas vide)
                duplicate = self.search([
                    ('email', '=', person.email),
                    ('id', '!=', person.id),
                    ('email', '!=', False),
                    ('email', '!=', '')
                ], limit=1)
                if duplicate:
                    raise ValidationError(f"L'email {person.email} est déjà utilisé par {duplicate.display_name}")
    
    @api.constrains('email')
    def _check_email_format(self):
        """Vérification basique du format email"""
        for person in self:
            if person.email and '@' not in person.email:
                raise ValidationError(f"Format d'email invalide: {person.email}")
    
    def action_view_requests(self):
        """Action pour voir les demandes assignées"""
        self.ensure_one()
        if not self.user_id:
            raise UserError("Aucun utilisateur associé à cette personne")
        
        return {
            'type': 'ir.actions.act_window',
            'name': f'Demandes de {self.display_name}',
            'res_model': 'maintenance.request',
            'view_mode': 'tree,form,kanban',
            'domain': [('assigned_user_id', '=', self.user_id.id)],
            'context': {'default_assigned_user_id': self.user_id.id}
        }
    
    def action_create_user(self):
        """Action pour créer manuellement l'utilisateur"""
        self.ensure_one()
        if self.user_id:
            raise UserError("Un utilisateur existe déjà pour cette personne")
        
        self._create_odoo_user()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Utilisateur créé'),
                'message': f'Utilisateur créé avec succès pour {self.display_name}',
                'sticky': False,
                'type': 'success',
            }
        }
    
    def action_reset_password(self):
        """Action pour renvoyer l'invitation par email"""
        self.ensure_one()
        if not self.user_id:
            raise UserError("Aucun utilisateur associé à cette personne")
        
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


class MaintenanceRequestExtended(models.Model):
    _inherit = 'maintenance.request'
    
    # Champ pour assigner un utilisateur spécifique
    assigned_user_id = fields.Many2one(
        'res.users',
        string='Assigné à',
        help="Utilisateur spécifiquement assigné à cette demande de maintenance",
        tracking=True
    )
    
    # Relation avec la personne de maintenance
    assigned_person_id = fields.Many2one(
        'maintenance.person',
        string='Personne assignée',
        help="Personne de maintenance assignée à cette demande",
        tracking=True
    )
    
    # Champs computed pour afficher le rôle
    assigned_person_role = fields.Char(
        'Rôle de la personne',
        related='assigned_person_id.role_id.name',
        readonly=True
    )
    
    @api.onchange('assigned_person_id')
    def _onchange_assigned_person_id(self):
        """Met à jour l'utilisateur assigné quand on sélectionne une personne"""
        if self.assigned_person_id and self.assigned_person_id.user_id:
            self.assigned_user_id = self.assigned_person_id.user_id
        else:
            self.assigned_user_id = False
    
    @api.onchange('assigned_user_id')
    def _onchange_assigned_user_id(self):
        """Met à jour la personne assignée quand on sélectionne un utilisateur"""
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
    
    # Relation avec les personnes de maintenance
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
        """Action pour voir les personnes de l'équipe"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Membres de {self.name}',
            'res_model': 'maintenance.person',
            'view_mode': 'tree,form',
            'domain': [('team_ids', 'in', [self.id])],
            'context': {'default_team_ids': [(6, 0, [self.id])]}
        }