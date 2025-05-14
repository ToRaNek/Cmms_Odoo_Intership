from odoo import api, fields, models, _

class MaintenanceEquipment(models.Model):
    parent_id = fields.Many2one('maintenance.equipment', string='Parent Equipment', index=True)
    child_ids = fields.One2many('maintenance.equipment', 'parent_id', string='Sub Equipments')
    
    _inherit = 'maintenance.equipment'

    # Relations avec les modèles 3D
    model3d_id = fields.Many2one('cmms.model3d', string='Modèle 3D')
    has_3d_model = fields.Boolean(compute='_compute_has_3d_model', store=True)

    # Paramètres d'affichage 3D
    model3d_scale = fields.Float('Échelle du modèle', default=1.0)
    model3d_position_x = fields.Float('Position X', default=0.0)
    model3d_position_y = fields.Float('Position Y', default=0.0)
    model3d_position_z = fields.Float('Position Z', default=0.0)
    model3d_rotation_x = fields.Float('Rotation X', default=0.0)
    model3d_rotation_y = fields.Float('Rotation Y', default=0.0)
    model3d_rotation_z = fields.Float('Rotation Z', default=0.0)

    @api.depends('model3d_id')
    def _compute_has_3d_model(self):
        for record in self:
            record.has_3d_model = bool(record.model3d_id)

    def action_view_3d(self):
        """Affiche le modèle 3D de l'équipement"""
        self.ensure_one()
        if not self.has_3d_model:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Aucun modèle 3D'),
                    'message': _("Cet équipement n'a pas de modèle 3D associé."),
                    'sticky': False,
                    'type': 'warning',
                }
            }

        # Use viewer_url instead of model_url to properly visualize the model
        return {
            'type': 'ir.actions.act_url',
            'url': self.model3d_id.viewer_url,
            'target': 'new',
        }