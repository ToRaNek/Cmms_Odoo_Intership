# custom_addons/cmms_3d_models/models/maintenance_request_extended.py
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError
from datetime import datetime, timedelta

class MaintenanceRequestExtended(models.Model):
    _inherit = 'maintenance.request'
    
    # Hériter des champs pour les rendre obligatoires
    equipment_id = fields.Many2one(
        'maintenance.equipment', 
        string='Equipment',
        required=True,  # Rendre obligatoire
        help="Équipement concerné par cette demande de maintenance"
    )
    
    user_id = fields.Many2one(
        'res.users', 
        string='Responsable',
        required=True,  # Rendre obligatoire
        help="Utilisateur responsable de cette demande"
    )
    
    schedule_date = fields.Datetime(
        'Date prévue',
        required=True,  # Rendre obligatoire
        help="Date prévue pour effectuer la maintenance"
    )
    
    # Champs d'assignation existants (avec assignation obligatoire)
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
    
    @api.constrains('equipment_id', 'user_id', 'schedule_date', 'assigned_user_id', 'assigned_person_id')
    def _check_required_fields(self):
        """Vérifier que tous les champs obligatoires sont définis"""
        for record in self:
            if not record.equipment_id:
                raise ValidationError(
                    _("L'équipement est obligatoire pour toute demande de maintenance.")
                )
            
            if not record.user_id:
                raise ValidationError(
                    _("Le responsable est obligatoire pour toute demande de maintenance.")
                )
            
            if not record.schedule_date:
                raise ValidationError(
                    _("La date prévue est obligatoire pour toute demande de maintenance.")
                )
            
            # Au moins une assignation doit être définie (personne ou utilisateur)
            if not record.assigned_user_id and not record.assigned_person_id:
                raise ValidationError(
                    _("Une assignation est obligatoire. "
                      "Veuillez assigner cette demande à un utilisateur ou une personne.")
                )
    
    @api.model
    def create(self, vals):
        """S'assurer que tous les champs obligatoires sont présents lors de la création"""
        errors = []
        
        if not vals.get('equipment_id'):
            errors.append("l'équipement")
        
        if not vals.get('user_id'):
            errors.append("le responsable")
        
        if not vals.get('schedule_date'):
            errors.append("la date prévue")
        
        # Vérifier qu'au moins une assignation est définie
        if not vals.get('assigned_user_id') and not vals.get('assigned_person_id'):
            errors.append("l'assignation (personne ou utilisateur)")
        
        if errors:
            error_msg = "Impossible de créer une demande de maintenance sans : " + ", ".join(errors) + "."
            raise UserError(_(error_msg))
        
        return super().create(vals)
    
    def write(self, vals):
        """S'assurer que les champs obligatoires ne peuvent pas être supprimés"""
        errors = []
        
        if 'equipment_id' in vals and not vals['equipment_id']:
            errors.append("L'équipement ne peut pas être supprimé")
        
        if 'user_id' in vals and not vals['user_id']:
            errors.append("Le responsable ne peut pas être supprimé")
        
        if 'schedule_date' in vals and not vals['schedule_date']:
            errors.append("La date prévue ne peut pas être supprimée")
        
        # Vérifier l'assignation seulement si les deux champs sont modifiés
        if ('assigned_user_id' in vals and 'assigned_person_id' in vals and 
            not vals['assigned_user_id'] and not vals['assigned_person_id']):
            errors.append("Au moins une assignation (personne ou utilisateur) doit être définie")
        
        if errors:
            raise UserError(_(". ".join(errors) + "."))
        
        return super().write(vals)
    
    @api.model
    def default_get(self, fields_list):
        """Définir des valeurs par défaut intelligentes"""
        defaults = super().default_get(fields_list)
        
        # Si on accède via le contexte d'un équipement, le définir par défaut
        if self.env.context.get('default_equipment_id'):
            defaults['equipment_id'] = self.env.context['default_equipment_id']
        
        # Définir l'utilisateur actuel comme responsable par défaut
        if 'user_id' in fields_list and not defaults.get('user_id'):
            defaults['user_id'] = self.env.user.id
        
        # Définir une date prévue par défaut (dans 7 jours)
        if 'schedule_date' in fields_list and not defaults.get('schedule_date'):
            defaults['schedule_date'] = datetime.now() + timedelta(days=7)
        
        # Si l'utilisateur actuel a une personne de maintenance associée, l'assigner
        if 'assigned_person_id' in fields_list and not defaults.get('assigned_person_id'):
            person = self.env['maintenance.person'].search([
                ('user_id', '=', self.env.user.id)
            ], limit=1)
            if person:
                defaults['assigned_person_id'] = person.id
                defaults['assigned_user_id'] = self.env.user.id
        elif 'assigned_user_id' in fields_list and not defaults.get('assigned_user_id'):
            # Si pas de personne associée, assigner quand même l'utilisateur actuel
            defaults['assigned_user_id'] = self.env.user.id
        
        return defaults
