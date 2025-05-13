# auto_equipment_linker.py
# Script à placer dans custom_addons/cmms_3d_models/models/
"""
Script qui améliore l'importation de la hiérarchie GLTF
et crée automatiquement des équipements liés pour chaque modèle 3D
"""

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

    def import_hierarchy_from_gltf(self, gltf_data, parent_id=False, auto_create_equipment=True):
        """
        Version améliorée qui importe la hiérarchie et crée des équipements liés
        """
        _logger.info(f"Import de la hiérarchie GLTF avec création d'équipements: {auto_create_equipment}")

        # Si le GLTF n'a pas de nodes, on ne peut pas continuer
        if 'nodes' not in gltf_data:
            _logger.warning("Aucun nœud trouvé dans le GLTF, impossible d'importer la hiérarchie")
            return []

        nodes = gltf_data.get('nodes', [])

        # Vérifier si la hiérarchie contient des métadonnées utiles pour les équipements
        has_equipment_metadata = False
        equipment_metadata = {}

        # Rechercher les métadonnées dans les extensions ou extras du GLTF
        if 'extensions' in gltf_data and 'CMMS_equipment_data' in gltf_data['extensions']:
            has_equipment_metadata = True
            equipment_metadata = gltf_data['extensions']['CMMS_equipment_data']
            _logger.info(f"Métadonnées d'équipement trouvées dans le GLTF: {equipment_metadata}")

        # Fonction récursive pour créer la hiérarchie avec équipements associés
        def create_node_hierarchy(node_index, parent_id=False, parent_equipment_id=False):
            node = nodes[node_index]
            node_name = node.get('name', f'Node_{node_index}')

            # Extraire les métadonnées d'équipement pour ce nœud si disponibles
            node_metadata = {}
            if has_equipment_metadata and str(node_index) in equipment_metadata:
                node_metadata = equipment_metadata[str(node_index)]

            # Créer un nouveau modèle 3D pour ce nœud
            model_values = {
                'name': node_name,
                'parent_id': parent_id,
                'description': node_metadata.get('description', f'Sous-modèle importé depuis GLTF: {node_name}'),
                'auto_create_equipment': auto_create_equipment,
            }

            # Ajouter les transformations si présentes dans le nœud
            if 'translation' in node:
                model_values['position_x'] = node['translation'][0]
                model_values['position_y'] = node['translation'][1]
                model_values['position_z'] = node['translation'][2]

            if 'rotation' in node:
                # Convertir quaternion en angles d'Euler (simplifié)
                # Dans une implémentation complète, utilisez une bibliothèque de math 3D
                model_values['rotation_x'] = node['rotation'][0] * 90.0
                model_values['rotation_y'] = node['rotation'][1] * 90.0
                model_values['rotation_z'] = node['rotation'][2] * 90.0

            if 'scale' in node:
                # Prendre la moyenne des 3 axes pour simplifier
                scale_avg = sum(node['scale']) / 3.0
                model_values['scale'] = scale_avg

            # Créer le modèle 3D
            new_model = self.create(model_values)
            _logger.info(f"Modèle 3D créé: {new_model.name} (ID: {new_model.id})")

            # Si la création auto d'équipement est activée, créer un équipement lié
            if auto_create_equipment:
                self._create_linked_equipment(new_model, node_metadata, parent_equipment_id)

            # Créer les enfants récursivement
            if 'children' in node:
                for child_index in node['children']:
                    create_node_hierarchy(
                        child_index,
                        new_model.id,
                        new_model.auto_equipment_id.id if new_model.auto_equipment_id else False
                    )

            return new_model.id

        # Identifier les nœuds racines (ceux qui ne sont pas des enfants)
        root_nodes = []
        for i, node in enumerate(nodes):
            # Si le nœud n'est pas référencé comme enfant, c'est un nœud racine
            is_child = False
            for other_node in nodes:
                if 'children' in other_node and i in other_node['children']:
                    is_child = True
                    break
            if not is_child:
                root_nodes.append(i)

        # Journaliser le nombre de nœuds racines trouvés
        _logger.info(f"Nombre de nœuds racines dans le GLTF: {len(root_nodes)}")

        # Créer la hiérarchie pour chaque nœud racine
        result_ids = []
        for root_index in root_nodes:
            parent_equipment_id = False
            # Si nous avons un parent_id, chercher l'équipement parent
            if parent_id:
                parent_model = self.browse(parent_id)
                if parent_model.auto_equipment_id:
                    parent_equipment_id = parent_model.auto_equipment_id.id

            # Créer la hiérarchie en commençant par ce nœud racine
            new_id = create_node_hierarchy(root_index, parent_id, parent_equipment_id)
            result_ids.append(new_id)

        _logger.info(f"Hiérarchie GLTF importée: {len(result_ids)} modèles de premier niveau créés")
        return result_ids

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

    # Redéfinir les méthodes existantes pour utiliser la nouvelle méthode d'importation

    def _convert_and_save_blend_file(self, record):
        """Surcharge pour ajouter la création d'équipements après la conversion"""
        result = super(Model3DWithAutoEquipmentLinking, self)._convert_and_save_blend_file(record)

        # Vérifier si la conversion a réussi et si l'enregistrement a un ID
        if not result or not record.id:
            return result

        # Vérifier si l'option de création automatique est activée
        auto_create = record.auto_create_equipment if hasattr(record, 'auto_create_equipment') else True

        if auto_create and not record.auto_equipment_id:
            # Créer l'équipement principal pour le modèle 3D
            self._create_linked_equipment(record)

        return result

    def _extract_zip_model(self, record):
        """Surcharge pour ajouter la création d'équipements après l'extraction ZIP"""
        result = super(Model3DWithAutoEquipmentLinking, self)._extract_zip_model(record)

        # Vérifier si l'extraction a réussi et si l'enregistrement a un ID
        if not result or not record.id:
            return result

        # Vérifier si l'option de création automatique est activée
        auto_create = record.auto_create_equipment if hasattr(record, 'auto_create_equipment') else True

        if auto_create and not record.auto_equipment_id:
            # Créer l'équipement principal pour le modèle 3D
            self._create_linked_equipment(record)

        return result