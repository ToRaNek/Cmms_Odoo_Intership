# custom_addons/cmms_3d_models/models/maintenance_request_assignment.py
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

class MaintenanceRequestAssignment(models.Model):
    _name = 'maintenance.request.assignment'
    _description = 'Assignation de demande de maintenance'
    _rec_name = 'person_id'
    _order = 'is_primary desc, assigned_date desc'

    request_id = fields.Many2one(
        'maintenance.request',
        string='Demande',
        required=True,
        ondelete='cascade',
        index=True
    )
    person_id = fields.Many2one(
        'maintenance.person',
        string='Personne assignée',
        required=True,
        ondelete='cascade',
        index=True
    )
    user_id = fields.Many2one(
        'res.users',
        related='person_id.user_id',
        string="Utilisateur associé",
        store=True,
        readonly=True
    )
    assigned_date = fields.Datetime('Date d\'assignation', default=fields.Datetime.now)
    assigned_by_id = fields.Many2one('res.users', string='Assigné par', default=lambda self: self.env.user.id)
    role_id = fields.Many2one(related='person_id.role_id', string='Rôle', readonly=True, store=True)
    is_primary = fields.Boolean(
        'Assigné principal',
        default=False,
        help="Si coché, cette personne est l'assigné principal pour cette demande"
    )
    notes = fields.Text('Notes')

    _sql_constraints = [
        ('unique_request_person', 'unique(request_id, person_id)',
         'Une personne ne peut être assignée qu\'une seule fois à une demande!')
    ]

    @api.constrains('is_primary', 'request_id')
    def _check_single_primary(self):
        """S'assurer qu'il n'y a qu'un seul assigné principal par demande"""
        for assignment in self:
            if assignment.is_primary:
                other_primary = self.search([
                    ('request_id', '=', assignment.request_id.id),
                    ('is_primary', '=', True),
                    ('id', '!=', assignment.id)
                ])
                if other_primary:
                    # Si un autre assigné principal existe, on le désactive
                    other_primary.write({'is_primary': False})

    @api.model
    def create(self, vals):
        """Permet de définir automatiquement le premier assigné comme principal"""
        res = super(MaintenanceRequestAssignment, self).create(vals)
        # S'il n'y a pas d'autre enregistrement pour cette demande, définir celui-ci comme principal
        if not self.search_count([('request_id', '=', res.request_id.id), ('id', '!=', res.id)]):
            res.is_primary = True
        return res