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

    # Champs pour l'assignation multiple
    assignment_ids = fields.One2many(
        'maintenance.request.assignment',
        'request_id',
        string='Assignations'
    )

    assigned_person_ids = fields.Many2many(
        'maintenance.person',
        string='Personnes assignées',
        compute='_compute_assigned_person_ids',
        store=True
    )

    primary_assignment_id = fields.Many2one(
        'maintenance.request.assignment',
        string='Assignation principale',
        compute='_compute_primary_assignment',
        store=True
    )

    @api.depends('assignment_ids.person_id')
    def _compute_assigned_person_ids(self):
        for request in self:
            request.assigned_person_ids = request.assignment_ids.mapped('person_id')

    @api.depends('assignment_ids.is_primary')
    def _compute_primary_assignment(self):
        for request in self:
            primary = request.assignment_ids.filtered(lambda a: a.is_primary)
            if primary:
                request.primary_assignment_id = primary[0]
                # Mise à jour des champs de compatibilité
                request.assigned_person_id = primary[0].person_id
                if primary[0].person_id and primary[0].person_id.user_id:
                    request.assigned_user_id = primary[0].person_id.user_id
            else:
                request.primary_assignment_id = False
                # Si aucun assigné principal mais des assignés existent
                if request.assignment_ids:
                    request.assigned_person_id = request.assignment_ids[0].person_id
                    if request.assignment_ids[0].person_id.user_id:
                        request.assigned_user_id = request.assignment_ids[0].person_id.user_id
                else:
                    request.assigned_person_id = False
                    request.assigned_user_id = False

    @api.onchange('assigned_person_id')
    def _onchange_assigned_person_id(self):
        """Gestion de l'assignation unique (pour compatibilité)"""
        if self.assigned_person_id and self.assigned_person_id.user_id:
            self.assigned_user_id = self.assigned_person_id.user_id
        else:
            self.assigned_user_id = False

        # Mettre à jour les assignations multiples
        if self.assigned_person_id:
            # Vérifier si un enregistrement d'assignation existe déjà
            existing = self.assignment_ids.filtered(lambda a: a.person_id == self.assigned_person_id)
            if not existing:
                # Créer une nouvelle assignation
                self.assignment_ids = [(0, 0, {
                    'person_id': self.assigned_person_id.id,
                    'is_primary': True
                })]
            else:
                # Marquer comme principal
                for assignment in self.assignment_ids:
                    assignment.is_primary = (assignment.person_id == self.assigned_person_id)

    @api.onchange('assigned_user_id')
    def _onchange_assigned_user_id(self):
        """Gestion de l'assignation à partir de l'utilisateur (pour compatibilité)"""
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

    def assign_multiple_persons(self, person_ids, make_primary=None):
        """
        Méthode d'assistant pour assigner plusieurs personnes à une demande

        :param person_ids: Liste d'IDs de maintenance.person à assigner
        :param make_primary: ID de la personne à définir comme principale (facultatif)
        :return: True en cas de succès
        """
        self.ensure_one()

        # Si aucun ID principal spécifié mais la liste n'est pas vide,
        # utiliser le premier comme principal
        if not make_primary and person_ids:
            make_primary = person_ids[0]

        # Créer les assignations qui n'existent pas encore
        for person_id in person_ids:
            # Vérifier si cette personne est déjà assignée
            if not self.assignment_ids.filtered(lambda a: a.person_id.id == person_id):
                self.env['maintenance.request.assignment'].create({
                    'request_id': self.id,
                    'person_id': person_id,
                    'is_primary': (person_id == make_primary)
                })
            elif person_id == make_primary:
                # Si la personne existe déjà et doit être principale, la mettre à jour
                assignment = self.assignment_ids.filtered(lambda a: a.person_id.id == person_id)
                assignment.write({'is_primary': True})

        return True