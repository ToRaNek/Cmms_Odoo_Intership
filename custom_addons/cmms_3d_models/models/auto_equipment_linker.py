import os
import json
import logging
from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)

class Model3DWithAutoEquipmentLinking(models.Model):
    _inherit = 'cmms.model3d'

    # Option pour activer/désactiver la création automatique d'équipements
    auto_create_equipment = fields.Boolean(
        'Créer automatiquement les équipements',
        default=True,
        help="Créera automatiquement des équipements de maintenance liés à chaque sous-modèle importé"
    )

    # Information sur l'équipement créé automatiquement
    auto_equipment_id = fields.Many2one(
        'maintenance.equipment',
        string='Équipement auto-créé',
        readonly=True
    )

    def _create_linked_equipment(self, model, metadata=None, parent_equipment_id=False):
        """
        Crée un équipement de maintenance lié au modèle 3D
        avec des métadonnées optionnelles pour l'enrichir
        """
        if metadata is None:
            metadata = {}

        # Préparer les valeurs pour l'équipement
        equipment_vals = {
            'name': metadata.get('equipment_name', model.name),
            'model3d_id': model.id,
            'model3d_scale': model.scale,
            'model3d_position_x': model.position_x,
            'model3d_position_y': model.position_y,
            'model3d_position_z': model.position_z,
            'model3d_rotation_x': model.rotation_x,
            'model3d_rotation_y': model.rotation_y,
            'model3d_rotation_z': model.rotation_z,
        }

        # Ajouter le parent si spécifié
        if parent_equipment_id:
            equipment_vals['parent_id'] = parent_equipment_id

        # Ajouter des métadonnées supplémentaires si disponibles
        if 'serial_no' in metadata:
            equipment_vals['serial_no'] = metadata['serial_no']

        if 'location' in metadata:
            equipment_vals['location'] = metadata['location']

        if 'category_id' in metadata and metadata['category_id']:
            # Rechercher la catégorie par nom
            category = self.env['maintenance.equipment.category'].search(
                [('name', '=', metadata['category_id'])], limit=1
            )
            if category:
                equipment_vals['category_id'] = category.id

        # Créer l'équipement de maintenance
        equipment = self.env['maintenance.equipment'].create(equipment_vals)
        _logger.info(f"Équipement créé et lié au modèle 3D: {equipment.name} (ID: {equipment.id})")

        # Mettre à jour le modèle 3D avec l'équipement créé
        model.write({'auto_equipment_id': equipment.id})

        return equipment

    # Adapté pour créer des équipements pour les sous-modèles JSON
    def _create_equipment_for_submodels(self, parent_model, submodels):
        """Crée des équipements pour les sous-modèles stockés en JSON"""
        if not parent_model.auto_create_equipment:
            return
            
        # Équipement parent
        parent_equipment = parent_model.auto_equipment_id or self.env['maintenance.equipment'].search(
            [('model3d_id', '=', parent_model.id)], limit=1)
        
        if not parent_equipment:
            # Créer un équipement pour le modèle parent s'il n'en a pas
            parent_equipment = self.env['maintenance.equipment'].create({
                'name': f"Équipement {parent_model.name}",
                'model3d_id': parent_model.id,
            })
            parent_model.write({'auto_equipment_id': parent_equipment.id})
            
        # Créer les équipements pour les sous-modèles
        for submodel in submodels:
            # Vérifier si cet équipement existe déjà (par son nom)
            equipment_name = f"Équipement {submodel['name']}"
            existing_equipment = self.env['maintenance.equipment'].search([
                ('name', '=', equipment_name),
                ('parent_id', '=', parent_equipment.id if parent_equipment else False)
            ], limit=1)
            
            if not existing_equipment:
                equipment_vals = {
                    'name': equipment_name,
                    'parent_id': parent_equipment.id if parent_equipment else False,
                    # Pas de model3d_id car ce n'est pas un vrai modèle dans la base
                    'model3d_scale': submodel.get('scale', 1.0),
                    'model3d_position_x': submodel.get('position', {}).get('x', 0.0),
                    'model3d_position_y': submodel.get('position', {}).get('y', 0.0),
                    'model3d_position_z': submodel.get('position', {}).get('z', 0.0),
                    'model3d_rotation_x': submodel.get('rotation', {}).get('x', 0.0),
                    'model3d_rotation_y': submodel.get('rotation', {}).get('y', 0.0),
                    'model3d_rotation_z': submodel.get('rotation', {}).get('z', 0.0),
                }
                
                equipment = self.env['maintenance.equipment'].create(equipment_vals)
                _logger.info(f"Équipement créé pour le sous-modèle JSON: {equipment.name} (ID: {equipment.id})")
                
                # Stocker l'ID de l'équipement dans le sous-modèle JSON
                submodel['equipment_id'] = equipment.id
        
        # Mettre à jour le JSON avec les IDs d'équipement
        parent_model.write({
            'submodels_json': json.dumps(submodels, indent=2)
        })