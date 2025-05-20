# custom_addons/cmms_3d_models/models/maintenance_request_assignment.py
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

class MaintenanceRequestAssignment(models.Model):
    _name = 'maintenance.request.assignment'
    _description = 'Assignation de demande de maintenance'
    _rec_name = 'person_id'
    _order = 'assigned_date desc'  # Modification: suppression de is_primary du tri

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
        help="Si coché, cette personne est un assigné principal pour cette demande"
    )
    notes = fields.Text('Notes')

    _sql_constraints = [
        ('unique_request_person', 'unique(request_id, person_id)',
         'Une personne ne peut être assignée qu\'une seule fois à une demande!')
    ]

    # Suppression de la méthode _check_single_primary qui empêchait d'avoir plusieurs assignés principaux

    @api.model
    def create(self, vals):
        """Permet de définir automatiquement le premier assigné comme principal"""
        res = super(MaintenanceRequestAssignment, self).create(vals)
        # S'il n'y a pas d'autre enregistrement pour cette demande, définir celui-ci comme principal
        if not self.search_count([('request_id', '=', res.request_id.id), ('id', '!=', res.id)]):
            res.is_primary = True
        
        # Forcer le recalcul des personnes assignées sur la demande
        if res.request_id:
            res.request_id._compute_assigned_person_ids()
            res.request_id._compute_primary_assignment()
            
        return res
        
    def write(self, vals):
        """Gère les mises à jour d'assignation"""
        result = super(MaintenanceRequestAssignment, self).write(vals)
        
        # Si on modifie is_primary, recalculer les assignations
        if 'is_primary' in vals or 'person_id' in vals:
            for record in self:
                if record.request_id:
                    record.request_id._compute_assigned_person_ids()
                    record.request_id._compute_primary_assignment()
        
        return result
        
    def unlink(self):
        """Gère la suppression d'assignation"""
        request_ids = self.mapped('request_id')
        result = super(MaintenanceRequestAssignment, self).unlink()
        
        # Recalculer les assignations pour les demandes concernées
        for request in request_ids:
            request._compute_assigned_person_ids()
            request._compute_primary_assignment()
            
        return result