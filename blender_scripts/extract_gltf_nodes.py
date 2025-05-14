# blender_scripts/extract_gltf_nodes.py
#!/usr/bin/env python3
"""
Script pour extraire des nœuds individuels d'un modèle GLTF/GLB et les exporter
comme des sous-modèles indépendants.

Usage:
    1. Depuis Blender:
       blender --background --python extract_gltf_nodes.py -- <chemin_fichier_gltf> <dossier_sortie>
    2. Depuis la ligne de commande:
       python extract_gltf_nodes.py <chemin_fichier_gltf> <dossier_sortie> [--blender-path CHEMIN]
"""

import sys
import os
import json
import logging
import argparse
import subprocess
import re
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

RUNNING_IN_BLENDER = 'bpy' in sys.modules or '--background' in sys.argv

if RUNNING_IN_BLENDER:
    import bpy

def parse_args():
    if RUNNING_IN_BLENDER:
        argv = sys.argv
        if "--" in argv:
            argv = argv[argv.index("--") + 1:]
        else:
            argv = []
        parser = argparse.ArgumentParser(description='Extrait des nœuds de GLTF/GLB')
        parser.add_argument('gltf_file', help='Chemin du fichier GLTF/GLB source')
        parser.add_argument('output_dir', help='Dossier où exporter les sous-modèles')
    else:
        parser = argparse.ArgumentParser(description='Extrait des nœuds de GLTF/GLB')
        parser.add_argument('gltf_file', help='Chemin du fichier GLTF/GLB source')
        parser.add_argument('output_dir', help='Dossier où exporter les sous-modèles')
        parser.add_argument('--blender-path', help='Chemin vers l\'exécutable Blender')
    return parser.parse_args(argv if RUNNING_IN_BLENDER else None)

def auto_detect_blender():
    """Détecte automatiquement l'installation Blender la plus récente disponible"""
    candidates = []

    # Variable d'env
    env = os.environ.get("BLENDER_PATH")
    if env and os.path.isfile(env):
        candidates.append(env)
    if shutil.which("blender"):
        candidates.append(shutil.which("blender"))

    # Dossiers classiques Windows
    if os.name == 'nt':
        for w in [
            r"C:\Program Files\Blender Foundation\Blender 3.6\blender.exe",
            r"C:\Program Files\Blender Foundation\Blender 4.0\blender.exe",
            r"C:\Program Files\Blender Foundation\Blender 4.4\blender.exe",
            r"C:\Program Files\Blender Foundation\Blender\blender.exe",
            r"C:\Blender\blender.exe"
        ]:
            if os.path.isfile(w):
                candidates.append(w)

    # Linux
    else:
        for l in ["/usr/bin/blender", "/usr/local/bin/blender", "/opt/blender/bin/blender",
                 "/opt/blender-3.6/blender", "/opt/blender-4.0/blender"]:
            if os.path.isfile(l):
                candidates.append(l)

    if candidates:
        return candidates[0]  # Retourne le premier trouvé

    raise FileNotFoundError("Aucun exécutable Blender trouvé")

def extract_nodes_from_gltf():
    args = parse_args()
    gltf_file = args.gltf_file
    output_dir = args.output_dir

    # Vérifier que le fichier source existe
    if not os.path.isfile(gltf_file):
        logger.error(f"Le fichier {gltf_file} n'existe pas")
        sys.exit(1)

    # Créer le dossier de sortie s'il n'existe pas
    os.makedirs(output_dir, exist_ok=True)

    # Nettoyer la scène
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()

    # Charger le fichier GLTF/GLB
    try:
        bpy.ops.import_scene.gltf(filepath=gltf_file)
        logger.info(f"Fichier GLTF/GLB chargé avec succès: {gltf_file}")
    except Exception as e:
        logger.error(f"Erreur lors du chargement du fichier GLTF/GLB: {str(e)}")
        sys.exit(1)

    # Récupérer tous les objets dans la scène
    root_objects = [obj for obj in bpy.context.scene.objects if obj.parent is None]

    # Extraire les métadonnées des nœuds
    nodes_data = {}

    # Fonction pour extraire les métadonnées d'un objet
    def extract_metadata(obj, parent_id=None, node_path=""):
        node_id = len(nodes_data) + 1
        node_name = obj.name

        # Position, rotation et échelle
        position = obj.location
        rotation = [rot for rot in obj.rotation_euler]
        scale = obj.scale

        nodes_data[node_id] = {
            "id": node_id,
            "name": node_name,
            "position": {"x": position.x, "y": position.y, "z": position.z},
            "rotation": {"x": rotation[0], "y": rotation[1], "z": rotation[2]},
            "scale": scale.x,  # Simplification: utilisation de l'échelle uniforme
            "parent_id": parent_id,
            "path": node_path + "/" + node_name if node_path else node_name
        }

        # Traiter récursivement les enfants
        for child in obj.children:
            extract_metadata(child, node_id, nodes_data[node_id]["path"])

    # Extraire les métadonnées de tous les objets racine et leurs enfants
    for obj in root_objects:
        extract_metadata(obj)

    # Exporter un fichier JSON avec les métadonnées des nœuds
    metadata_path = os.path.join(output_dir, "nodes_metadata.json")
    with open(metadata_path, 'w') as f:
        json.dump(nodes_data, f, indent=2)

    logger.info(f"Métadonnées des nœuds exportées vers: {metadata_path}")

    # Exporter chaque nœud individuellement
    for node_id, node_data in nodes_data.items():
        node_dir = os.path.join(output_dir, str(node_id))
        os.makedirs(node_dir, exist_ok=True)

        node_name = node_data["name"]

        # Sélectionner uniquement le nœud à exporter
        bpy.ops.object.select_all(action='DESELECT')

        # Trouver l'objet correspondant
        obj = None
        for o in bpy.context.scene.objects:
            if o.name == node_name:
                obj = o
                break

        if obj is None:
            logger.warning(f"Objet {node_name} non trouvé")
            continue

        # Sélectionner l'objet
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj

        # Exporter le nœud en format GLTF
        gltf_path = os.path.join(node_dir, f"{node_name}.gltf")
        try:
            bpy.ops.export_scene.gltf(
                filepath=gltf_path,
                use_selection=True,
                export_format='GLTF_SEPARATE',
                export_texcoords=True,
                export_normals=True,
                export_materials='EXPORT',
                export_animations=True
            )
            logger.info(f"Nœud {node_name} exporté vers: {gltf_path}")

            # Vérifier si un fichier .bin a été généré
            bin_path = os.path.splitext(gltf_path)[0] + ".bin"
            if os.path.exists(bin_path):
                logger.info(f"Fichier binaire associé: {bin_path}")
                # Ajouter le chemin du fichier binaire aux métadonnées
                nodes_data[node_id]["bin_path"] = os.path.basename(bin_path)

            # Ajouter le chemin du fichier GLTF aux métadonnées
            nodes_data[node_id]["gltf_path"] = os.path.basename(gltf_path)

        except Exception as e:
            logger.error(f"Erreur lors de l'exportation du nœud {node_name}: {str(e)}")

    # Mettre à jour le fichier JSON avec les chemins des fichiers
    with open(metadata_path, 'w') as f:
        json.dump(nodes_data, f, indent=2)

    logger.info(f"Extraction des nœuds terminée. {len(nodes_data)} nœuds exportés.")
    print(f"NODES_EXTRACTED={len(nodes_data)}")

def run_from_command_line():
    args = parse_args()

    # Utiliser le chemin Blender spécifié ou détecter automatiquement
    blender_path = args.blender_path if hasattr(args, 'blender_path') and args.blender_path else auto_detect_blender()

    # Construire la commande à exécuter
    cmd = [
        blender_path,
        "--background",
        "--python", os.path.abspath(__file__),
        "--", args.gltf_file, os.path.abspath(args.output_dir)
    ]

    logger.info(f"Exécution de Blender: {' '.join(cmd)}")

    # Exécuter la commande
    process = subprocess.run(cmd, capture_output=True, text=True)

    # Afficher la sortie
    if process.stdout:
        logger.info(f"Sortie de Blender:\n{process.stdout}")
    if process.stderr:
        logger.warning(f"Erreurs Blender:\n{process.stderr}")

    # Vérifier si l'extraction a réussi
    if process.returncode != 0:
        logger.error(f"Échec de l'extraction des nœuds (code {process.returncode})")
        sys.exit(1)

    # Vérifier combien de nœuds ont été extraits
    for line in process.stdout.splitlines():
        if line.startswith("NODES_EXTRACTED="):
            num_nodes = int(line.split('=')[1])
            logger.info(f"{num_nodes} nœuds ont été extraits avec succès")

if __name__ == "__main__":
    import shutil

    if RUNNING_IN_BLENDER:
        extract_nodes_from_gltf()
    else:
        run_from_command_line()