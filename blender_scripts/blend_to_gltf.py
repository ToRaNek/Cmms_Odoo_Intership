#!/usr/bin/env python3
"""
Script universel de conversion de fichiers Blender (.blend) en GLTF/GLB
Adapté pour Windows pour le module CMMS 3D Models d'Odoo

Usage:
    1. Depuis Blender:
       blender --background --python blend_to_gltf.py -- <chemin_fichier_blend> <fichier_sortie.gltf/glb>
    2. Depuis la ligne de commande:
       python blend_to_gltf.py <chemin_fichier_blend> <fichier_sortie.gltf/glb> [--blender-path CHEMIN]
Arguments:
    <chemin_fichier_blend>    Chemin vers le fichier .blend à convertir
    <fichier_sortie>          Chemin du fichier de sortie (.gltf ou .glb)
    --blender-path            Chemin vers l'exécutable Blender (optionnel)
"""

import sys
import os
import json
import logging
import argparse
import subprocess
import shutil
import re
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Version minimale de Blender requise pour l'export GLTF
MINIMUM_BLENDER_VERSION = (3, 0, 0)
RUNNING_IN_BLENDER = 'bpy' in sys.modules or '--background' in sys.argv

if RUNNING_IN_BLENDER:
    import bpy

def parse_blender_version(version_line):
    """Extrait la version de Blender à partir de la sortie de la commande --version"""
    m = re.search(r'Blender (\d+)\.(\d+)(?:\.(\d+))?', version_line)
    if m:
        major = int(m.group(1))
        minor = int(m.group(2))
        patch = int(m.group(3) or 0)
        return (major, minor, patch)
    raise ValueError(f"Impossible de détecter la version Blender dans la sortie: {version_line}")

def get_blender_version(blender_path):
    """Récupère la version de Blender à partir d'un chemin d'exécutable"""
    try:
        result = subprocess.run(
            [blender_path, '--version'],
            capture_output=True, text=True, timeout=5
        )
        first_line = result.stdout.splitlines()[0]
        return parse_blender_version(first_line)
    except Exception as e:
        logger.warning(f"Impossible de déterminer la version de Blender à {blender_path}: {e}")
        return None

def auto_detect_blender(min_version=MINIMUM_BLENDER_VERSION):
    """Détecte automatiquement l'installation Blender la plus récente disponible"""
    checked = []
    candidates = []

    # Priorité : variable d'env → chemin par défaut → d'autres emplacements classiques
    env = os.environ.get("BLENDER_PATH")
    if env and shutil.which(env):
        candidates.append(env)
    if shutil.which("blender"):
        candidates.append(shutil.which("blender"))

    # Dossiers classiques Windows
    if os.name == 'nt':
        for w in [
            r"C:\Program Files\Blender Foundation\Blender 3.6\blender.exe",
            r"C:\Program Files\Blender Foundation\Blender 4.0\blender.exe",
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

    # Trouver la version la plus récente qui satisfait la version minimale
    best_version = None
    best_path = None

    for bpath in candidates:
        v = get_blender_version(bpath)
        if v:
            checked.append((bpath, v))
            if v >= min_version and (best_version is None or v > best_version):
                best_version = v
                best_path = bpath

    if best_path:
        logger.info(f"Version Blender sélectionnée: {best_path} (version {'.'.join(map(str, best_version))})")
        return best_path
    elif checked:
        # Si on a trouvé des versions mais aucune n'est assez récente
        versions_str = ", ".join([f"{p} (v{'.'.join(map(str, v))})" for p, v in checked])
        raise RuntimeError(f"Aucune version récente de Blender trouvée. Minimum requis: {'.'.join(map(str, min_version))}. Testées: {versions_str}")
    else:
        raise FileNotFoundError(f"Aucun exécutable Blender trouvé dans les chemins testés: {candidates}")

def parse_args():
    if RUNNING_IN_BLENDER:
        argv = sys.argv
        if "--" in argv:
            argv = argv[argv.index("--") + 1:]
        else:
            argv = []
        parser = argparse.ArgumentParser(description='Convertit un fichier .blend en GLTF/GLB')
        parser.add_argument('blend_file')
        parser.add_argument('output_file')
    else:
        parser = argparse.ArgumentParser(description='Convertit un fichier .blend en GLTF/GLB')
        parser.add_argument('blend_file')
        parser.add_argument('output_file')
        parser.add_argument('--blender-path', help='Chemin vers l\'exécutable Blender (détection auto si non spécifié)')
    return parser.parse_args(argv if RUNNING_IN_BLENDER else None)

def filter_alsa_stderr(stderr_str):
    """Supprime le bruit ALSA inutile du stderr Blender."""
    # Pas nécessaire sous Windows, mais gardé pour compatibilité
    return stderr_str

def convert_via_subprocess(blend_file, output_file, blender_path="blender"):
    if not os.path.isfile(blend_file):
        raise FileNotFoundError(f"Fichier .blend introuvable: {blend_file}")

    output_dir = os.path.dirname(output_file)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    abs_blend_file = os.path.abspath(blend_file)
    abs_output_file = os.path.abspath(output_file)
    script_path = os.path.abspath(__file__)

    blender_cmd = [
        blender_path,
        "--background",
        "--python", script_path,
        "--", abs_blend_file, abs_output_file
    ]

    logger.info(f"Exécution de Blender: {' '.join(blender_cmd)}")
    result = subprocess.run(blender_cmd, capture_output=True, text=True)

    # Pour Windows, nous n'avons pas les erreurs ALSA
    stderr_clean = result.stderr
    if result.stdout:
        logger.info(f"Sortie de Blender:\n{result.stdout}")
    if stderr_clean.strip():
        logger.warning(f"Erreurs Blender:\n{stderr_clean}")

    # Statut process
    if result.returncode != 0 or stderr_clean.strip():
        print("FATAL_ERROR=" + (stderr_clean.strip() or "Erreur inconnue"), file=sys.stderr)
        raise RuntimeError(f"Échec de la conversion avec Blender (code {result.returncode}):\n{stderr_clean}")

    # Vérifier si le fichier a bien été créé
    if not os.path.exists(output_file):
        raise FileNotFoundError(f"Le fichier de sortie n'a pas été créé: {output_file}")

    # Extraire les chemins signalés dans stdout (utile pour Odoo)
    output_files = {'output_file': output_file}
    for line in result.stdout.splitlines():
        if line.startswith("CONVERTED_FILE="):
            output_files['gltf_file'] = line.split('=', 1)[1]
        elif line.startswith("BINARY_FILE="):
            output_files['bin_file'] = line.split('=', 1)[1]

    return output_files

def clear_scene():
    logger.info("Nettoyage de la scène...")
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()
    for collection in bpy.data.collections:
        bpy.data.collections.remove(collection)
    for material in bpy.data.materials:
        bpy.data.materials.remove(material)
    for mesh in bpy.data.meshes:
        bpy.data.meshes.remove(mesh)

def load_blend_file(blend_file):
    logger.info(f"Chargement du fichier .blend: {blend_file}")
    with bpy.data.libraries.load(blend_file) as (data_from, data_to):
        data_to.objects = data_from.objects
        data_to.collections = data_from.collections
    for obj in data_to.objects:
        if obj is not None:
            bpy.context.scene.collection.objects.link(obj)
    for coll in data_to.collections:
        if coll is not None:
            bpy.context.scene.collection.children.link(coll)
    for obj in bpy.context.scene.objects:
        obj.select_set(True)
    logger.info(f"Chargé {len(data_to.objects)} objets et {len(data_to.collections)} collections")

def export_to_gltf(output_file, blend_file):
    output_dir = os.path.dirname(output_file)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    if output_file.lower().endswith(".glb"):
        export_format = "GLB"
        logger.info(f"Exportation au format GLB: {output_file}")
    else:
        export_format = "GLTF_SEPARATE"
        logger.info(f"Exportation au format GLTF: {output_file}")

    bin_file = None
    if export_format == "GLTF_SEPARATE":
        bin_file = os.path.splitext(output_file)[0] + ".bin"

    export_options = {
        'filepath': output_file,
        'export_format': export_format,      # 'GLB' or 'GLTF_SEPARATE'
        'export_normals': True,              # Boolean for Blender 4.4.3
        'export_materials': 'EXPORT',        # Enum (string)
        'export_animations': True,           # Boolean for Blender 4.4.3
        'export_yup': True,
        'export_apply': True,
        'will_save_settings': False
    }
    try:
        bpy.ops.export_scene.gltf(**export_options)
        print(f"CONVERTED_FILE={output_file}")
        if bin_file and os.path.exists(bin_file):
            print(f"BINARY_FILE={bin_file}")
        logger.info(f"Export réussi: {output_file}")
    except Exception as e:
        logger.error(f"Erreur d'export GLTF/GLB: {str(e)}")
        print("EXPORT_ERROR=" + str(e), file=sys.stderr)
        sys.exit(3)

def blender_conversion(blend_file, output_file):
    if not os.path.isfile(blend_file):
        logger.error(f"Le fichier {blend_file} n'existe pas ou n'est pas accessible.")
        sys.exit(1)
    try:
        clear_scene()
        load_blend_file(blend_file)
        export_to_gltf(output_file, blend_file)
        print("CONVERT_OK=1")
        sys.exit(0)
    except Exception as e:
        logger.error("FATAL_ERROR: %s", str(e))
        print("FATAL_ERROR=" + str(e), file=sys.stderr)
        sys.exit(2)

def main():
    args = parse_args()
    if RUNNING_IN_BLENDER:
        blender_conversion(args.blend_file, args.output_file)
    else:
        try:
            # Utiliser le chemin Blender spécifié ou détecter automatiquement
            blender_path = args.blender_path if hasattr(args, 'blender_path') and args.blender_path else auto_detect_blender()
            result = convert_via_subprocess(args.blend_file, args.output_file, blender_path)
            logger.info(f"Conversion réussie: {result['output_file']}")
            sys.exit(0)
        except Exception as e:
            logger.error(f"Erreur lors de la conversion: {str(e)}")
            sys.exit(1)



def collect_equipment_metadata(scene):
    equipment_data = {}

    # Parcourir tous les objets de la scène
    for i, obj in enumerate(scene.objects):
        # Vérifier si l'objet a des propriétés personnalisées (custom properties)
        if obj and hasattr(obj, 'keys'):
            node_data = {}
            # Chercher des propriétés pour l'équipement
            for key in obj.keys():
                # Filtrer uniquement les propriétés commençant par 'equipment_'
                if key.startswith('equipment_') or key in ['serial_no', 'category_id', 'location']:
                    node_data[key.replace('equipment_', '')] = obj[key]

            # Si l'objet a un nom, l'utiliser comme nom d'équipement par défaut
            if obj.name and 'name' not in node_data:
                node_data['equipment_name'] = obj.name

            # Ajouter une description basée sur l'objet
            if 'description' not in node_data:
                node_data['description'] = f"Équipement créé à partir de l'objet {obj.name} dans Blender"

            # Si des métadonnées ont été trouvées, les ajouter
            if node_data:
                equipment_data[str(i)] = node_data

    return equipment_data

def add_equipment_metadata_to_gltf(gltf_data, scene):
    """
    Ajoute les métadonnées d'équipement au fichier GLTF
    """
    # Collecter les métadonnées
    equipment_data = collect_equipment_metadata(scene)

    # Si des métadonnées ont été trouvées, les ajouter au GLTF
    if equipment_data:
        # Initialiser les extensions si elles n'existent pas
        if 'extensions' not in gltf_data:
            gltf_data['extensions'] = {}

        # Ajouter l'extension CMMS_equipment_data
        gltf_data['extensions']['CMMS_equipment_data'] = equipment_data

        # Ajouter l'extension utilisée à extensionsUsed si elle n'existe pas déjà
        if 'extensionsUsed' not in gltf_data:
            gltf_data['extensionsUsed'] = ['CMMS_equipment_data']
        elif 'CMMS_equipment_data' not in gltf_data['extensionsUsed']:
            gltf_data['extensionsUsed'].append('CMMS_equipment_data')

    return gltf_data

if __name__ == "__main__":
    main()
