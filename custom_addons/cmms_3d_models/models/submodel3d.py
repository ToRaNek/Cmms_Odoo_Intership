# custom_addons/cmms_3d_models/models/submodel3d.py
from odoo import api, fields, models, _
import os
import base64
import logging
import json

_logger = logging.getLogger(__name__)

# Importer le chemin des modèles depuis model3d.py
from .model3d import MODELS_DIR

class SubModel3D(models.Model):
    _name = 'cmms.submodel3d'
    _description = 'Sous-modèle 3D'
    _rec_name = 'name'
    
    name = fields.Char('Nom', required=True)
    description = fields.Text('Description')
    
    # Relation avec le modèle parent
    parent_id = fields.Many2one('cmms.model3d', string='Modèle parent', 
                                required=True, ondelete='cascade', index=True)
    
    # ID relatif unique au sein du parent (utilisé dans les chemins de fichiers)
    relative_id = fields.Integer('ID relatif', required=True)
    
    # Informations sur le fichier du sous-modèle
    gltf_filename = fields.Char('Nom du fichier glTF', required=True)
    bin_filename = fields.Char('Nom du fichier binaire')
    
    # Paramètres de transformation
    scale = fields.Float('Échelle', default=1.0)
    position_x = fields.Float('Position X', default=0.0)
    position_y = fields.Float('Position Y', default=0.0)
    position_z = fields.Float('Position Z', default=0.0)
    rotation_x = fields.Float('Rotation X', default=0.0)
    rotation_y = fields.Float('Rotation Y', default=0.0)
    rotation_z = fields.Float('Rotation Z', default=0.0)
    
    # Chemin complet vers le fichier (calculé)
    gltf_path = fields.Char('Chemin du fichier glTF', compute='_compute_file_paths', store=False)
    bin_path = fields.Char('Chemin du fichier binaire', compute='_compute_file_paths', store=False)
    
    # URL pour accéder aux fichiers
    gltf_url = fields.Char('URL du fichier glTF', compute='_compute_urls', store=False)
    bin_url = fields.Char('URL du fichier binaire', compute='_compute_urls', store=False)
    
    # URL pour le visualiseur
    viewer_url = fields.Char('URL du visualiseur', compute='_compute_viewer_url', store=False)
    
    # Champs actif pour l'archivage
    active = fields.Boolean('Actif', default=True)
    
    _sql_constraints = [
        ('unique_relative_id_per_parent', 'unique(parent_id, relative_id)', 
         'L\'ID relatif doit être unique pour chaque modèle parent!')
    ]
    
    @api.depends('parent_id', 'relative_id', 'gltf_filename', 'bin_filename')
    def _compute_file_paths(self):
        for record in self:
            if record.parent_id and record.relative_id and record.gltf_filename:
                # Chemin du fichier glTF: MODELS_DIR/parent_id/childs/relative_id/gltf_filename
                record.gltf_path = os.path.normpath(os.path.join(
                    MODELS_DIR, 
                    str(record.parent_id.id), 
                    'childs',
                    str(record.relative_id),
                    record.gltf_filename
                ))
                
                # Chemin du fichier binaire (si défini)
                if record.bin_filename:
                    record.bin_path = os.path.normpath(os.path.join(
                        MODELS_DIR, 
                        str(record.parent_id.id), 
                        'childs',
                        str(record.relative_id),
                        record.bin_filename
                    ))
                else:
                    record.bin_path = False
            else:
                record.gltf_path = False
                record.bin_path = False
    
    @api.depends('parent_id', 'relative_id', 'gltf_filename', 'bin_filename')
    def _compute_urls(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        for record in self:
            if record.parent_id and record.relative_id and record.gltf_filename:
                # URL du fichier glTF: /models3d/parent_id/childs/relative_id/gltf_filename
                record.gltf_url = f"{base_url}/models3d/{record.parent_id.id}/childs/{record.relative_id}/{record.gltf_filename}"
                
                # URL du fichier binaire (si défini)
                if record.bin_filename:
                    record.bin_url = f"{base_url}/models3d/{record.parent_id.id}/childs/{record.relative_id}/{record.bin_filename}"
                else:
                    record.bin_url = False
            else:
                record.gltf_url = False
                record.bin_url = False
    
    @api.depends('parent_id', 'relative_id')
    def _compute_viewer_url(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        for record in self:
            if record.parent_id and record.relative_id:
                # URL du visualiseur: /web/cmms/submodel/parent_id/relative_id
                record.viewer_url = f"{base_url}/web/cmms/submodel/{record.parent_id.id}/{record.relative_id}"
            else:
                record.viewer_url = False
    
    def action_view_3d(self):
        """Affiche le sous-modèle 3D dans le visualiseur"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': self.viewer_url,
            'target': 'new',
        }
    
    def check_file_exists(self):
        """Vérifie si les fichiers du sous-modèle existent sur le disque"""
        self.ensure_one()
        
        # Mise à jour des chemins
        self._compute_file_paths()
        
        result = {
            'gltf_exists': False,
            'bin_exists': False
        }
        
        # Vérification du fichier glTF
        if self.gltf_path and os.path.isfile(self.gltf_path):
            result['gltf_exists'] = True
        
        # Vérification du fichier binaire
        if self.bin_path and os.path.isfile(self.bin_path):
            result['bin_exists'] = True
        
        return result