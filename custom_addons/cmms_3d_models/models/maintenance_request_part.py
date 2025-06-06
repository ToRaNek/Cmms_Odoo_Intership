# custom_addons/cmms_3d_models/models/maintenance_request_part.py
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

class MaintenanceRequestPart(models.Model):
    _name = 'maintenance.request.part'
    _description = 'Pièce de demande de maintenance'
    _rec_name = 'part_name'
    _order = 'sequence, id'

    # Relations
    request_id = fields.Many2one(
        'maintenance.request',
        string='Demande de maintenance',
        required=True,
        ondelete='cascade',
        index=True
    )
    
    submodel_id = fields.Many2one(
        'cmms.submodel3d',
        string='Pièce/Sous-modèle',
        required=True,
        help="Sélectionner la pièce spécifique de l'équipement"
    )
    
    # Champs calculés et liés
    part_name = fields.Char(
        'Nom de la pièce',
        related='submodel_id.name',
        readonly=True,
        store=True
    )
    
    equipment_id = fields.Many2one(
        'maintenance.equipment',
        related='request_id.equipment_id',
        readonly=True,
        store=True,
        string='Équipement'
    )
    
    parent_model3d_id = fields.Many2one(
        'cmms.model3d',
        related='submodel_id.parent_id',
        readonly=True,
        store=True,
        string='Modèle 3D parent'
    )
    
    # Type d'intervention
    intervention_type = fields.Selection([
        ('nettoyage', 'Nettoyage'),
        ('reparation', 'Réparation'),
        ('remplacement', 'Remplacement'),
        ('inspection', 'Inspection'),
        ('lubrification', 'Lubrification'),
        ('other', 'Autre')
    ], string='Type d\'intervention', required=True, 
       help="Sélectionner le type d'intervention à effectuer sur cette pièce")
    
    intervention_other = fields.Char(
        'Autre intervention',
        help="Préciser le type d'intervention si 'Autre' est sélectionné"
    )
    
    # Description du problème
    description = fields.Text(
        'Description du problème',
        help="Décrire le problème spécifique sur cette pièce (optionnel)"
    )

    done = fields.Boolean(
            'Terminé',
            default=False,
            help="Cocher si l'intervention sur cette pièce est terminée"
        )

    # Ordre/priorité
    sequence = fields.Integer('Séquence', default=10)

    # Champs informatifs (calculés)
    submodel_relative_id = fields.Integer(
        'ID relatif',
        related='submodel_id.relative_id',
        readonly=True
    )

    submodel_scale = fields.Float(
        'Échelle',
        related='submodel_id.scale',
        readonly=True
    )

    @api.constrains('intervention_type', 'intervention_other')
    def _check_intervention_other(self):
        """Valider que le champ 'Autre intervention' est rempli si 'Autre' est sélectionné"""
        for record in self:
            if record.intervention_type == 'other' and not record.intervention_other:
                raise ValidationError(
                    _("Vous devez préciser le type d'intervention si vous sélectionnez 'Autre'.")
                )

    @api.onchange('intervention_type')
    def _onchange_intervention_type(self):
        """Vider le champ 'autre intervention' si on ne sélectionne pas 'Autre'"""
        if self.intervention_type != 'other':
            self.intervention_other = False

    @api.model
    def default_get(self, fields_list):
        """Définir des valeurs par défaut intelligentes"""
        defaults = super().default_get(fields_list)

        # Si on accède via le contexte d'une demande, filtrer les sous-modèles
        if self.env.context.get('default_request_id'):
            request = self.env['maintenance.request'].browse(self.env.context['default_request_id'])
            if request.equipment_id and request.equipment_id.model3d_id:
                # On peut définir un domaine par défaut si nécessaire
                pass

        return defaults

    def name_get(self):
        """Affichage personnalisé du nom"""
        result = []
        for record in self:
            name = f"{record.part_name} - {dict(record._fields['intervention_type'].selection)[record.intervention_type]}"
            if record.intervention_type == 'other' and record.intervention_other:
                name = f"{record.part_name} - {record.intervention_other}"
            result.append((record.id, name))
        return result


class MaintenanceRequestExtendedParts(models.Model):
    _inherit = 'maintenance.request'

    # Relation avec les pièces
    part_ids = fields.One2many(
        'maintenance.request.part',
        'request_id',
        string='Pièces concernées',
        help="Sélectionner les pièces spécifiques à maintenir"
    )

    part_count = fields.Integer(
        'Nombre de pièces',
        compute='_compute_part_count'
    )

    @api.depends('part_ids')
    def _compute_part_count(self):
        for record in self:
            record.part_count = len(record.part_ids)

    def action_view_parts(self):
        """Ouvrir la vue des pièces"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Pièces de {self.name}',
            'res_model': 'maintenance.request.part',
            'view_mode': 'tree,form',
            'domain': [('request_id', '=', self.id)],
            'context': {
                'default_request_id': self.id,
                'default_equipment_id': self.equipment_id.id if self.equipment_id else False,
            }
        }
