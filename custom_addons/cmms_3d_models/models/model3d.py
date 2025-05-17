import os
import base64
import zipfile
import io
import json
import subprocess
import tempfile
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from odoo.tools.safe_eval import safe_eval
import logging

_logger = logging.getLogger(__name__)

# Define Windows paths - Utiliser raw strings et normaliser les chemins
MODELS_DIR = os.path.normpath(r"C:\Users\admin\Desktop\odoo\models")
BLENDER_SCRIPT_PATH = os.path.normpath(r"C:\Users\admin\Desktop\odoo\blender_scripts\blend_to_gltf.py")
DEBUG_LOG_PATH = os.path.normpath(r"C:\Users\admin\Desktop\odoo\models\blender_debug.log")
# Chemin vers l'exécutable Blender - à adapter selon votre installation
BLENDER_EXE = r"C:\Program Files\Blender Foundation\Blender 4.4\blender.exe"

class Model3D(models.Model):
    _name = 'cmms.model3d'
    _description = '3D Model'
    # Suppression de toutes les options qui nécessitent des colonnes spéciales en base
    # _rec_name = 'complete_name'  # On utilise le champ 'name' par défaut

    name = fields.Char('Name', required=True)
    description = fields.Text('Description')
    model_file = fields.Binary('Model File (glTF/GLB/Blend)', attachment=True,
                              help="Upload the main 3D model file (glTF, GLB, or Blend format)")
    model_filename = fields.Char('File Name')
    model_url = fields.Char('Model URL', compute='_compute_model_url', store=True)
    viewer_url = fields.Char('Viewer URL', compute='_compute_viewer_url')
    thumbnail = fields.Binary('Thumbnail', attachment=True)
    active = fields.Boolean('Active', default=True)

    # New field for uploading all model files as a ZIP
    model_zip = fields.Binary('Complete Model (ZIP)',
                              help="Upload a ZIP file containing the main glTF/GLB file and all associated files "
                                   "(textures, binaries, etc.)")
    model_zip_filename = fields.Char('ZIP File Name')

    # Bin file for model (if needed separately)
    model_bin = fields.Binary('Model Binary (.bin)',
                             help="Upload the binary file associated with the glTF model (if using separate files)")
    model_bin_filename = fields.Char('Binary File Name')

    # Information about model structure
    has_external_files = fields.Boolean('Has External Files', default=False,
                                        help="Indicates if this 3D model references external files like textures or binaries")
    files_list = fields.Text('Associated Files', readonly=True,
                             help="List of files associated with this 3D model")

    # Information for tracking Blender file conversion
    source_blend_file = fields.Binary('Source Blend File', attachment=True, readonly=True,
                                     help="Original Blender file before conversion")
    source_blend_filename = fields.Char('Source Blend Filename', readonly=True)
    is_converted_from_blend = fields.Boolean('Converted from Blender', default=False, readonly=True)

    # Relations
    equipment_ids = fields.One2many('maintenance.equipment', 'model3d_id', string='Equipment')

    # Technical fields
    model_format = fields.Selection([
        ('gltf', 'glTF'),
        ('glb', 'GLB'),
        ('blend', 'Blender'),
    ], string='Model Format', default='glb', required=True)

    scale = fields.Float('Scale', default=1.0)
    position_x = fields.Float('Position X', default=0.0)
    position_y = fields.Float('Position Y', default=0.0)
    position_z = fields.Float('Position Z', default=0.0)
    rotation_x = fields.Float('Rotation X', default=0.0)
    rotation_y = fields.Float('Rotation Y', default=0.0)
    rotation_z = fields.Float('Rotation Z', default=0.0)

    # Relation hiérarchique parent-enfant (conservée pour rétrocompatibilité)
    parent_id = fields.Many2one('cmms.model3d', string='Modèle parent',
                               ondelete='cascade', index=True)
    child_ids = fields.One2many('cmms.model3d', 'parent_id', string='Sous-modèles')
    is_submodel = fields.Boolean(compute='_compute_is_submodel', store=False,
                                string='Est un sous-modèle')
    # Correction: Ajout de recursive=True pour résoudre l'avertissement
    complete_name = fields.Char('Nom complet', compute='_compute_complete_name',
                              recursive=True, store=False)  # Ne pas stocker ce champ
    child_count = fields.Integer(compute='_compute_child_count', string='Nombre de sous-modèles')

    # Nouveau champ pour stocker les sous-modèles en JSON
    submodels_json = fields.Text('Sous-modèles (JSON)', default='[]',
                               help="Structure hiérarchique des sous-modèles au format JSON")

    submodel_ids = fields.One2many('cmms.submodel3d', 'parent_id', string='Sous-modèles')
    submodel_count = fields.Integer('Nombre de sous-modèles', compute='_compute_submodel_count')

    @api.depends('submodel_ids')
    def _compute_submodel_count(self):
        for record in self:
            record.submodel_count = len(record.submodel_ids)

    @api.depends('child_ids')
    def _compute_child_count(self):
        for record in self:
            # Compter les sous-modèles enregistrés comme records indépendants (ancien système)
            old_child_count = len(record.child_ids)

            # Compter les sous-modèles stockés dans le JSON (nouveau système)
            new_child_count = 0
            if record.submodels_json:
                try:
                    submodels = json.loads(record.submodels_json)
                    new_child_count = len(submodels)
                except (json.JSONDecodeError, ValueError):
                    _logger.warning(f"Impossible de décoder le JSON des sous-modèles pour {record.id}")

            # Utiliser le plus grand des deux nombres (transition)
            record.child_count = max(old_child_count, new_child_count)

    @api.depends('parent_id')
    def _compute_is_submodel(self):
        for record in self:
            record.is_submodel = bool(record.parent_id)

    @api.depends('name', 'parent_id.complete_name')
    def _compute_complete_name(self):
        for record in self:
            if record.parent_id:
                record.complete_name = '%s / %s' % (record.parent_id.complete_name, record.name)
            else:
                record.complete_name = record.name

    def _filter_alsa_errors(self, stderr):
        """Enlève le bruit ALSA/ALSA lib du stderr, retourne erreurs restantes."""
        filtered = []
        for line in stderr.splitlines():
            # On ignore les classiques ALSA/AL lib/pcm
            if "ALSA lib" in line or "AL lib:" in line:
                continue
            if "pcm.c:" in line or "Could not open playback device" in line:
                continue
            if "function snd_func_" in line or "cannot find card '0'" in line:
                continue
            if "Unknown PCM default" in line:
                continue
            filtered.append(line)
        return "\n".join(filtered)

    @api.depends('model_file', 'model_filename')
    def _compute_model_url(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        for record in self:
            if record.model_file and record.id and record.model_filename:
                # Pour les fichiers Blender, on utilise le fichier GLTF converti
                if record.model_format == 'blend' and record.is_converted_from_blend:
                    # On assume que le fichier converti a le même nom mais avec l'extension .gltf
                    blend_basename = os.path.splitext(record.model_filename)[0]
                    gltf_filename = f"{blend_basename}.gltf"
                    # Use forward slashes in URLs even on Windows
                    record.model_url = f"{base_url}/models3d/{record.id}/{gltf_filename}"
                else:
                    record.model_url = f"{base_url}/models3d/{record.id}/{record.model_filename}"
            else:
                record.model_url = False

    def _compute_viewer_url(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        for record in self:
            if record.id:
                record.viewer_url = f"{base_url}/web/cmms/viewer/{record.id}"
            else:
                record.viewer_url = False

    @api.model
    def create(self, vals):
        # Log initial state for debugging
        if 'model_format' in vals:
            _logger.info(f"Création d'un modèle 3D au format: {vals['model_format']}")
        if 'model_filename' in vals:
            _logger.info(f"Nom du fichier: {vals['model_filename']}")

        # Create the record first
        res = super(Model3D, self).create(vals)

        # Détermine si c'est un fichier Blend à convertir
        is_blend = res.model_format == 'blend' and res.model_file

        # Handle model file - prevent ZIP processing for Blend files
        if res.model_file:
            try:
                if is_blend:
                    # Blend file workflow - convert to GLTF
                    _logger.info(f"Traitement d'un fichier Blender: {res.model_filename}")
                    self._convert_and_save_blend_file(res)
                else:
                    # Standard model file (GLTF/GLB)
                    _logger.info(f"Traitement d'un fichier modèle: {res.model_filename}")
                    self._save_model_file(res)
            except Exception as e:
                _logger.error(f"Erreur lors du traitement du fichier modèle: {str(e)}")
                raise ValidationError(f"Erreur lors du traitement du fichier modèle: {str(e)}")

        # Handle binary file separately if needed
        if res.model_bin and not is_blend:  # Skip for Blend files as they're handled in conversion
            try:
                _logger.info(f"Traitement du fichier binaire: {res.model_bin_filename or 'sans nom'}")
                self._save_bin_file(res)
            except Exception as e:
                _logger.error(f"Erreur lors du traitement du fichier binaire: {str(e)}")
                raise ValidationError(f"Erreur lors du traitement du fichier binaire: {str(e)}")

        # Handle ZIP file ONLY if it's not a blend file
        if res.model_zip and not is_blend:
            try:
                _logger.info("Traitement du fichier ZIP")
                self._extract_zip_model(res)
            except Exception as e:
                _logger.error(f"Erreur lors de l'extraction de l'archive ZIP: {str(e)}")
                raise ValidationError(f"Erreur lors de l'extraction de l'archive ZIP: {str(e)}")

        return res

    def write(self, vals):
        res = super(Model3D, self).write(vals)
        try:
            for record in self:
                if 'model_file' in vals and vals['model_file']:
                    if record.model_format == 'blend':
                        self._convert_and_save_blend_file(record)
                    else:
                        self._save_model_file(record)
                if 'model_bin' in vals and vals['model_bin']:
                    self._save_bin_file(record)
                if 'model_zip' in vals and vals['model_zip'] and bool(vals['model_zip'].strip()):
                    self._extract_zip_model(record)
        except Exception as e:
            _logger.error(f"Erreur lors de la mise à jour du modèle 3D: {str(e)}")
            raise ValidationError(f"Erreur lors de la mise à jour du modèle 3D: {str(e)}")
        return res

    def _save_model_file(self, record):
        try:
            # Vérifier que model_filename est bien une chaîne
            if not isinstance(record.model_filename, str):
                _logger.warning(f"model_filename n'est pas une chaîne: {record.model_filename}, type: {type(record.model_filename)}")
                record.model_filename = str(record.model_filename)  # Conversion en chaîne

            # Créer le dossier si nécessaire
            models_dir = os.path.normpath(os.path.join(MODELS_DIR, str(record.id)))
            os.makedirs(models_dir, exist_ok=True)

            # Sauvegarder le fichier
            file_path = os.path.normpath(os.path.join(models_dir, record.model_filename))
            with open(file_path, 'wb') as f:
                f.write(base64.b64decode(record.model_file))

            _logger.info(f"Modèle 3D sauvegardé: {file_path}")

            # Check if it's a GLTF file and parse it to see if it references external files
            if record.model_filename.endswith('.gltf'):
                self._analyze_gltf_references(record, file_path)

                # Importer la hiérarchie après sauvegarde du fichier GLTF
                try:
                    _logger.info(f"Import de la hiérarchie depuis le fichier glTF sauvegardé: {file_path}")

                    # Au lieu de charger le fichier JSON, on passe directement le chemin du fichier GLTF
                    # à la méthode import_hierarchy_from_gltf qui va l'analyser avec Blender
                    self.import_hierarchy_from_gltf(file_path, record.id)
                except Exception as e:
                    _logger.error(f"Erreur lors de l'importation de la hiérarchie depuis glTF: {str(e)}")

            # Pour les fichiers GLB également
            elif record.model_filename.endswith('.glb'):
                try:
                    _logger.info(f"Import de la hiérarchie depuis le fichier GLB sauvegardé: {file_path}")
                    self.import_hierarchy_from_gltf(file_path, record.id)
                except Exception as e:
                    _logger.error(f"Erreur lors de l'importation de la hiérarchie depuis GLB: {str(e)}")
        except Exception as e:
            _logger.error(f"Erreur lors de la sauvegarde du modèle 3D: {e}")
            raise ValidationError(f"Erreur lors de la sauvegarde du modèle 3D: {e}")

    def _convert_and_save_blend_file(self, record):
        """Convertit un fichier Blender en GLTF et le sauvegarde"""
        try:
            # Vérifier que model_filename est bien une chaîne
            if not isinstance(record.model_filename, str):
                _logger.warning(f"model_filename n'est pas une chaîne: {record.model_filename}, type: {type(record.model_filename)}")
                record.model_filename = str(record.model_filename)  # Conversion en chaîne

            # Sauvegarder le fichier Blender original
            models_dir = os.path.normpath(os.path.join(MODELS_DIR, str(record.id)))
            os.makedirs(models_dir, exist_ok=True)

            # Sauvegarder l'original comme référence
            record.source_blend_file = record.model_file
            record.source_blend_filename = record.model_filename

            blend_path = os.path.normpath(os.path.join(models_dir, record.model_filename))
            with open(blend_path, 'wb') as f:
                f.write(base64.b64decode(record.model_file))

            _logger.info(f"Fichier Blender original sauvegardé: {blend_path}")

            # Vérifier que le fichier .blend existe réellement
            if not os.path.isfile(blend_path):
                raise ValidationError(f"Le fichier Blender sauvegardé n'existe pas: {blend_path}")

            # Convertir le fichier Blender en GLTF
            blend_basename = os.path.splitext(record.model_filename)[0]
            output_file = os.path.normpath(os.path.join(models_dir, f"{blend_basename}.gltf"))

            # Ensure script path and blender executable exist
            if not os.path.isfile(BLENDER_SCRIPT_PATH):
                raise ValidationError(f"Le script de conversion Blender n'existe pas: {BLENDER_SCRIPT_PATH}")

            # Utiliser le chemin absolu vers Blender
            blender_exe = BLENDER_EXE
            if not os.path.isfile(blender_exe):
                _logger.warning(f"Exécutable Blender non trouvé à {blender_exe}, utilisation du PATH")
                # Tenter de trouver blender dans le PATH
                blender_exe = 'blender'

            _logger.info(f"Utilisation de l'exécutable Blender: {blender_exe}")

            # Appeler Blender en ligne de commande pour la conversion
            cmd = [
                blender_exe,
                '--background',
                '-noaudio',  # Désactive l'audio pour éviter les erreurs ALSA
                '--python',
                BLENDER_SCRIPT_PATH,  # Utiliser le script GLTF au lieu de GLB
                '--',
                blend_path,
                output_file
            ]

            _logger.info(f"Exécution de la commande: {' '.join(cmd)}")

            # Exécuter la commande et capturer la sortie
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            stdout, stderr = process.communicate()

            # ALWAYS log ALL output for debugging
            _logger.info(f"[DEBUG][BLENDER STDOUT]\n{stdout}\n[DEBUG][BLENDER STDERR]\n{stderr}\n[DEBUG][RETURNCODE]: {process.returncode}")

            # Write debug info to file for post-mortem analysis
            debug_log = os.path.normpath(DEBUG_LOG_PATH)
            with open(debug_log, "w", encoding="utf-8") as debugfile:
                debugfile.write(f"CMD: {' '.join(cmd)}\n")
                debugfile.write(f"RETURNCODE: {process.returncode}\n")
                debugfile.write("-- STDOUT --\n")
                debugfile.write(stdout)
                debugfile.write("\n-- STDERR --\n")
                debugfile.write(stderr)

            # Filtrer les erreurs ALSA
            alsa_filtered_errors = self._filter_alsa_errors(stderr)

            # CORRECTION: Vérifier uniquement le code de retour, pas le contenu des logs
            if process.returncode != 0:
                _logger.error(f"[BLENDER ERROR] Erreur lors de la conversion du fichier Blender:"
                              f"\n--Stderr Filtré--\n{alsa_filtered_errors}")
                raise ValidationError(
                    f"Erreur conversion Blender! returncode={process.returncode}\n"
                    f"stdout:\n{stdout}\n"
                    f"stderr:\n{stderr}\n"
                    f"stderr filtré:\n{alsa_filtered_errors}"
                )

            # Extraire le chemin du fichier converti de la sortie
            converted_file = None
            binary_file = None
            for line in stdout.split('\n'):
                if line.startswith('CONVERTED_FILE='):
                    converted_file = line.split('=', 1)[1].strip()
                elif line.startswith('BINARY_FILE='):
                    binary_file = line.split('=', 1)[1].strip()

            if not converted_file or not os.path.exists(converted_file):
                raise ValidationError(
                    f"Conversion échouée: Aucun fichier de sortie {converted_file}\nSIGNAUX STDOUT:\n{stdout}\nSTDERR:\n{stderr}"
                )

            # Lire le fichier GLTF converti
            with open(converted_file, 'rb') as f:
                gltf_content = f.read()
                record.model_file = base64.b64encode(gltf_content)

            # Si un fichier binaire a été généré, le sauvegarder aussi
            if binary_file and os.path.exists(binary_file):
                with open(binary_file, 'rb') as f:
                    bin_content = f.read()
                    record.model_bin = base64.b64encode(bin_content)
                    record.model_bin_filename = os.path.basename(binary_file)
                    record.has_external_files = True

            # Mettre à jour les informations du modèle
            gltf_filename = os.path.basename(converted_file)
            record.model_filename = gltf_filename
            record.model_format = 'gltf'  # Changer en 'gltf' au lieu de 'glb'
            record.is_converted_from_blend = True

            _logger.info(f"Fichier Blender converti avec succès en GLTF: {converted_file}")
            if binary_file:
                _logger.info(f"Fichier binaire associé: {binary_file}")

            # Mettre à jour l'URL du modèle
            record._compute_model_url()

            # Si un fichier binaire a été généré, ajouter son nom à la liste des fichiers
            if binary_file:
                file_list = []
                if record.files_list:
                    try:
                        file_list = json.loads(record.files_list)
                    except Exception:
                        file_list = []

                bin_filename = os.path.basename(binary_file)
                if bin_filename not in file_list:
                    file_list.append(bin_filename)
                    record.files_list = json.dumps(file_list)

            # Analyser le fichier GLTF pour en extraire la hiérarchie
            try:
                # Importer la hiérarchie directement avec le chemin du fichier
                self.import_hierarchy_from_gltf(converted_file, record.id)
                _logger.info(f"Hiérarchie importée avec succès depuis {converted_file}")
            except Exception as e:
                _logger.error(f"Erreur lors de l'importation de la hiérarchie GLTF: {str(e)}")

            return True
        except Exception as e:
            _logger.error(f"[DEBUG][PYTHON] Erreur lors de la conversion du fichier Blender (catch python): {str(e)}")
            raise ValidationError(f"[DEBUG][PYTHON] Erreur lors de la conversion du fichier Blender: {str(e)}")

    def _save_bin_file(self, record):
        try:
            # Make sure directory exists
            models_dir = os.path.normpath(os.path.join(MODELS_DIR, str(record.id)))
            os.makedirs(models_dir, exist_ok=True)

            # Check if a filename is provided, otherwise use a default name
            bin_filename = record.model_bin_filename
            if not bin_filename:
                # If the main file is named X.gltf, the bin file should be named X.bin
                if record.model_filename and record.model_filename.endswith('.gltf'):
                    bin_filename = record.model_filename.replace('.gltf', '.bin')
                else:
                    bin_filename = 'model.bin'

            # Vérifier que bin_filename est bien une chaîne
            if not isinstance(bin_filename, str):
                _logger.warning(f"bin_filename n'est pas une chaîne: {bin_filename}, type: {type(bin_filename)}")
                bin_filename = str(bin_filename)  # Conversion en chaîne

            # Save the binary file
            file_path = os.path.normpath(os.path.join(models_dir, bin_filename))
            with open(file_path, 'wb') as f:
                f.write(base64.b64decode(record.model_bin))

            # Update file list
            file_list = []
            if record.files_list:
                try:
                    file_list = json.loads(record.files_list)
                except:
                    file_list = []

            if bin_filename not in file_list:
                file_list.append(bin_filename)
                record.files_list = json.dumps(file_list)

            record.has_external_files = True
            _logger.info(f"Fichier binaire sauvegardé: {file_path}")
        except Exception as e:
            _logger.error(f"Erreur lors de la sauvegarde du fichier binaire: {e}")
            raise ValidationError(f"Erreur lors de la sauvegarde du fichier binaire: {e}")

    def _extract_zip_model(self, record):
        """Extrait une archive ZIP contenant un modèle 3D et ses fichiers associés"""
        try:
            # Vérifier que le modèle_zip existe et n'est pas vide
            if not record.model_zip or not record.model_zip.strip():
                _logger.warning("Tentative d'extraction d'une archive ZIP vide ou non existante")
                return False

            # Create directory if needed - utiliser backslashes pour Windows
            models_dir = os.path.normpath(os.path.join(MODELS_DIR, str(record.id)))
            _logger.info(f"Dossier d'extraction: {models_dir}")

            # S'assurer que le dossier existe
            os.makedirs(models_dir, exist_ok=True)
            if not os.path.isdir(models_dir):
                raise ValidationError(f"Impossible de créer le dossier: {models_dir}")

            # Decode the ZIP file
            try:
                zip_data = base64.b64decode(record.model_zip)

                # Vérifier que les données ZIP sont valides
                if not zip_data or len(zip_data) < 100:  # Un fichier ZIP valide a au moins une signature minimale
                    _logger.warning(f"Données ZIP invalides ou trop petites: {len(zip_data) if zip_data else 0} octets")
                    return False
            except Exception as e:
                _logger.error(f"Erreur lors du décodage base64 du ZIP: {str(e)}")
                return False

            # Créer un fichier ZIP temporaire pour diagnostiquer d'éventuels problèmes
            temp_zip_path = os.path.join(models_dir, "temp_archive.zip")
            try:
                with open(temp_zip_path, 'wb') as f:
                    f.write(zip_data)
                _logger.info(f"Archive ZIP temporaire créée: {temp_zip_path}")
            except Exception as e:
                _logger.error(f"Erreur lors de l'écriture du fichier ZIP temporaire: {str(e)}")
                raise ValidationError(f"Erreur lors de l'écriture du fichier ZIP temporaire: {str(e)}")

            # Extract the ZIP file
            try:
                with zipfile.ZipFile(io.BytesIO(zip_data)) as zip_ref:
                    # Log ZIP content for debugging
                    file_list = zip_ref.namelist()
                    _logger.info(f"Contenu de l'archive ZIP: {file_list}")

                    # Get main model file from ZIP
                    main_file = None
                    for file in file_list:
                        if file.lower().endswith(('.gltf', '.glb', '.blend')):
                            main_file = file
                            _logger.info(f"Fichier principal trouvé dans ZIP: {main_file}")
                            break

                    if not main_file:
                        raise ValidationError("Aucun fichier glTF, GLB ou Blend trouvé dans l'archive ZIP")

                    # Extract all files with explicit paths
                    for file in file_list:
                        # Vérifier que file est une chaîne de caractères (et non un booléen ou autre)
                        if not isinstance(file, str):
                            _logger.warning(f"Élément non-chaîne dans la liste des fichiers: {file}, type: {type(file)}")
                            continue  # Ignorer les éléments non-chaînes

                        _logger.info(f"Extraction du fichier: {file}")
                        # Extraire en gérant les séparateurs de chemin
                        extract_path = os.path.normpath(os.path.join(models_dir, file))
                        # S'assurer que le dossier parent existe
                        os.makedirs(os.path.dirname(extract_path), exist_ok=True)
                        # Extraction du fichier avec gestion des erreurs
                        try:
                            with zip_ref.open(file) as source, open(extract_path, 'wb') as target:
                                target.write(source.read())
                        except Exception as e:
                            _logger.error(f"Erreur lors de l'extraction du fichier {file}: {str(e)}")
                            # Continuer avec les autres fichiers au lieu d'échouer complètement

                    # Vérifier si les fichiers ont été extraits
                    main_file_path = os.path.normpath(os.path.join(models_dir, main_file))
                    if not os.path.isfile(main_file_path):
                        _logger.error(f"Le fichier principal n'a pas été extrait correctement: {main_file_path}")
                        raise ValidationError(f"Le fichier principal n'a pas été extrait correctement: {main_file_path}")
                    else:
                        _logger.info(f"Fichier principal vérifié: {main_file_path}")

                    # Traitement des fichiers extraits
                    if main_file.lower().endswith('.blend'):
                        # Save .blend as source
                        with open(main_file_path, "rb") as f:
                            record.source_blend_file = base64.b64encode(f.read())
                            record.source_blend_filename = os.path.basename(main_file)

                        # Détermine fichier de sortie attendu
                        blend_basename = os.path.splitext(os.path.basename(main_file))[0]
                        output_file = os.path.normpath(os.path.join(models_dir, f"{blend_basename}.gltf"))

                        # Ensure script path and blender executable exist
                        if not os.path.isfile(BLENDER_SCRIPT_PATH):
                            _logger.error(f"Script de conversion Blender non trouvé: {BLENDER_SCRIPT_PATH}")
                            raise ValidationError(f"Script de conversion Blender non trouvé: {BLENDER_SCRIPT_PATH}")

                        # Utiliser le chemin absolu vers Blender
                        blender_exe = BLENDER_EXE
                        if not os.path.isfile(blender_exe):
                            _logger.error(f"Exécutable Blender non trouvé: {blender_exe}")
                            # Tenter de trouver blender dans le PATH
                            blender_exe = 'blender'

                        _logger.info(f"Utilisation de l'exécutable Blender: {blender_exe}")

                        cmd = [
                            blender_exe,
                            '--background',
                            '-noaudio',  # Désactive l'audio pour éviter les erreurs ALSA
                            '--python',
                            BLENDER_SCRIPT_PATH,
                            '--',
                            main_file_path,
                            output_file
                        ]

                        _logger.info(f"Exécution de la commande: {' '.join(cmd)}")

                        process = subprocess.Popen(
                            cmd,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            universal_newlines=True
                        )
                        stdout, stderr = process.communicate()

                        # ALWAYS log ALL output for debugging
                        _logger.info(f"[DEBUG][BLENDER ZIP STDOUT]\n{stdout}\n[DEBUG][BLENDER ZIP STDERR]\n{stderr}\n[DEBUG][RETURNCODE]: {process.returncode}")

                        # Write debug info to file for post-mortem analysis
                        debug_log = os.path.normpath(DEBUG_LOG_PATH.replace(".log", "_zip.log"))
                        with open(debug_log, "w", encoding="utf-8") as debugfile:
                            debugfile.write(f"CMD: {' '.join(cmd)}\n")
                            debugfile.write(f"RETURNCODE: {process.returncode}\n")
                            debugfile.write("-- STDOUT --\n")
                            debugfile.write(stdout)
                            debugfile.write("\n-- STDERR --\n")
                            debugfile.write(stderr)

                        # Filtrer les erreurs ALSA
                        alsa_filtered_errors = self._filter_alsa_errors(stderr)

                        # CORRECTION: Vérifier uniquement le code de retour, pas le contenu des logs
                        if process.returncode != 0:
                            _logger.error(f"[BLENDER ZIP ERROR] Erreur lors de la conversion: {alsa_filtered_errors}")
                            raise ValidationError(
                                f"Erreur conversion Blender (ZIP)! returncode={process.returncode}\n"
                                f"stdout:\n{stdout}\n"
                                f"stderr:\n{stderr}\n"
                                f"stderr filtré:\n{alsa_filtered_errors}"
                            )

                        # Analyse de la sortie pour vrais chemins générés
                        converted_file = None
                        binary_file = None
                        for line in stdout.split('\n'):
                            if line.startswith("CONVERTED_FILE="):
                                converted_file = line.split('=', 1)[1].strip()
                            elif line.startswith("BINARY_FILE="):
                                binary_file = line.split('=', 1)[1].strip()

                        # Sécurité: fallback si pas renvoyé
                        if not converted_file:
                            converted_file = output_file
                        if not os.path.exists(converted_file):
                            raise ValidationError(
                                f"Conversion ZIP échouée: Aucun fichier de sortie {converted_file}\nSIGNAUX STDOUT:\n{stdout}\nSTDERR:\n{stderr}"
                            )

                        # Met à jour le record sur le vrai fichier .gltf
                        with open(converted_file, 'rb') as f:
                            record.model_file = base64.b64encode(f.read())
                        record.model_filename = os.path.basename(converted_file)
                        record.model_format = 'gltf'
                        record.is_converted_from_blend = True

                        # Gère le .bin associé
                        if binary_file and os.path.exists(binary_file):
                            with open(binary_file, 'rb') as f:
                                record.model_bin = base64.b64encode(f.read())
                                record.model_bin_filename = os.path.basename(binary_file)
                                record.has_external_files = True

                        # Remet main_file_path sur le .gltf réel
                        main_file = os.path.basename(converted_file)
                        main_file_path = converted_file

                        # Importer la hiérarchie
                        try:
                            # Utiliser le chemin direct du fichier converti pour extraire la hiérarchie
                            self.import_hierarchy_from_gltf(converted_file, record.id)
                            _logger.info(f"Hiérarchie importée avec succès depuis le fichier converti: {converted_file}")
                        except Exception as e:
                            _logger.error(f"Erreur lors de l'importation de la hiérarchie depuis le fichier converti: {str(e)}")
                    else:
                        # Pour les zip contenant gltf ou glb directement
                        record.model_format = 'gltf' if main_file.endswith('.gltf') else 'glb'
                        record.is_converted_from_blend = False
                        with open(main_file_path, 'rb') as f:
                            record.model_file = base64.b64encode(f.read())
                        record.model_filename = os.path.basename(main_file)

                        # Importer la hiérarchie à partir du fichier principal
                        try:
                            self.import_hierarchy_from_gltf(main_file_path, record.id)
                            _logger.info(f"Hiérarchie importée avec succès depuis le fichier ZIP: {main_file_path}")
                        except Exception as e:
                            _logger.error(f"Erreur lors de l'importation de la hiérarchie depuis le fichier ZIP: {str(e)}")

                    # Check et ajoute les bin/textures/autres, MAJ files_list
                    texture_files = []
                    bin_files = []
                    other_files = []
                    additional_files = []

                    for file in file_list:
                        # S'assurer que file est une chaîne
                        if not isinstance(file, str):
                            continue

                        # On ignore déjà pris comme main file
                        if file == main_file:
                            continue
                        if file.lower().endswith(('.png', '.jpg', '.jpeg')):
                            texture_files.append(file)
                        elif file.lower().endswith('.bin'):
                            bin_files.append(file)
                            # Charge aussi la première bin trouvée, si ce n'est fait
                            if not record.model_bin and not record.model_bin_filename:
                                bin_path = os.path.normpath(os.path.join(models_dir, file))
                                with open(bin_path, 'rb') as f:
                                    record.model_bin = base64.b64encode(f.read())
                                    record.model_bin_filename = os.path.basename(file)
                                    record.has_external_files = True
                        else:
                            other_files.append(file)
                        # Ajouter seulement si c'est une chaîne
                        additional_files.append(os.path.basename(file))

                    # Si un .gltf: analyse références
                    if main_file.endswith('.gltf'):
                        self._analyze_gltf_references(record, main_file_path)

                    # Met à jour files_list et status des fichiers externes
                    record.files_list = json.dumps(additional_files)
                    record.has_external_files = bool(additional_files)

                    _logger.info(f"Archive ZIP extraite: {record.model_zip_filename or 'sans nom'}, {len(file_list)} fichiers")
                    _logger.info(f"Textures trouvées: {len(texture_files)}, Fichiers binaires: {len(bin_files)}, Autres: {len(other_files)}")

                    return True

            except zipfile.BadZipFile as e:
                _logger.error(f"Erreur d'archive ZIP invalide: {str(e)}")
                raise ValidationError(f"Archive ZIP invalide: {str(e)}")
            except Exception as e:
                _logger.error(f"Erreur lors de l'extraction de l'archive ZIP: {str(e)}")
                raise ValidationError(f"Erreur lors de l'extraction de l'archive ZIP: {str(e)}")
        except Exception as e:
            _logger.error(f"Erreur générale lors du traitement ZIP: {str(e)}")
            raise ValidationError(f"Erreur générale lors du traitement ZIP: {str(e)}")

    def _analyze_gltf_references(self, record, gltf_path):
        """Analyze a GLTF file to find referenced external files"""
        try:
            # Vérifier que gltf_path est bien une chaîne
            if not isinstance(gltf_path, str):
                _logger.warning(f"gltf_path n'est pas une chaîne: {gltf_path}, type: {type(gltf_path)}")
                gltf_path = str(gltf_path)  # Conversion en chaîne

            # Read and parse the GLTF file
            with open(gltf_path, 'r') as f:
                gltf_data = json.load(f)

            referenced_files = []

            # Check for images
            if 'images' in gltf_data:
                for image in gltf_data['images']:
                    if 'uri' in image:
                        referenced_files.append(image['uri'])

            # Check for buffers
            if 'buffers' in gltf_data:
                for buffer in gltf_data['buffers']:
                    if 'uri' in buffer:
                        referenced_files.append(buffer['uri'])

            # Store the list of referenced files
            if referenced_files:
                record.files_list = json.dumps(referenced_files)
                record.has_external_files = True

                _logger.info(f"Fichiers référencés dans le modèle GLTF: {', '.join(referenced_files)}")
        except Exception as e:
            _logger.error(f"Erreur lors de l'analyse du fichier GLTF: {e}")

    def import_from_blender(self, model_data, filename, description=None):
        """
        Importe un modèle depuis Blender
        :param model_data: Contenu du fichier encodé en base64
        :param filename: Nom du fichier
        :param description: Description du modèle
        :return: Record créé
        """
        # Déterminer le format du fichier
        if filename.endswith('.blend'):
            format = 'blend'
        elif filename.endswith('.gltf'):
            format = 'gltf'
        elif filename.endswith('.glb'):
            format = 'glb'
        else:
            raise ValidationError("Format de fichier non supporté. Utilisez .blend, .gltf ou .glb")

        return self.create({
            'name': os.path.splitext(filename)[0],
            'description': description or '',
            'model_file': model_data,
            'model_filename': filename,
            'model_format': format,
        })

    def action_view_3d(self, include_children=False):
        """Affiche le modèle 3D dans le visualiseur"""
        self.ensure_one()
        base_url = self.viewer_url

        if include_children and (self.child_ids or self.submodels_json):
            # Ajouter un paramètre pour indiquer d'inclure les enfants
            base_url += "?include_children=1"

        return {
            'type': 'ir.actions.act_url',
            'url': base_url,
            'target': 'new',
        }

    def action_view_3d_with_children(self):
        """Affiche le modèle 3D avec tous ses sous-modèles"""
        return self.action_view_3d(include_children=True)

    # Action pour voir les sous-modèles
    def action_view_submodels(self):
        """Affiche la liste des sous-modèles"""
        self.ensure_one()

        # Utiliser le nouveau système avec cmms.submodel3d
        return {
            'type': 'ir.actions.act_window',
            'name': _('Sous-modèles'),
            'res_model': 'cmms.submodel3d',
            'view_mode': 'tree,form',
            'domain': [('parent_id', '=', self.id)],
            'context': {'default_parent_id': self.id}
        }

    def _create_equipment_for_submodels(self, parent_model):
        """Crée des équipements pour les sous-modèles"""
        # Cette méthode peut être améliorée selon vos besoins
        # Pour l'instant, on vérifie juste qu'elle est appelée
        _logger.info(f"Création d'équipements pour les sous-modèles du modèle {parent_model.id}")

        # Exemple de comment créer des équipements pour chaque sous-modèle
        if hasattr(self, 'auto_create_equipment') and parent_model.auto_create_equipment:
            submodels = self.env['cmms.submodel3d'].search([('parent_id', '=', parent_model.id)])

            # Récupérer l'équipement parent
            parent_equipment = parent_model.auto_equipment_id or self.env['maintenance.equipment'].search(
                [('model3d_id', '=', parent_model.id)], limit=1)

            # Si l'équipement parent n'existe pas, on peut le créer
            if not parent_equipment and parent_model.auto_create_equipment:
                parent_equipment = self.env['maintenance.equipment'].create({
                    'name': f"Équipement {parent_model.name}",
                    'model3d_id': parent_model.id,
                })
                parent_model.write({'auto_equipment_id': parent_equipment.id})

            # Créer des équipements pour chaque sous-modèle
            for submodel in submodels:
                # Vérifier si cet équipement existe déjà
                equipment_name = f"Équipement {submodel.name}"
                existing_equipment = self.env['maintenance.equipment'].search([
                    ('name', '=', equipment_name),
                    ('parent_id', '=', parent_equipment.id if parent_equipment else False)
                ], limit=1)

                if not existing_equipment:
                    equipment_vals = {
                        'name': equipment_name,
                        'parent_id': parent_equipment.id if parent_equipment else False,
                        'model3d_scale': submodel.scale,
                        'model3d_position_x': submodel.position_x,
                        'model3d_position_y': submodel.position_y,
                        'model3d_position_z': submodel.position_z,
                        'model3d_rotation_x': submodel.rotation_x,
                        'model3d_rotation_y': submodel.rotation_y,
                        'model3d_rotation_z': submodel.rotation_z,
                    }

                    self.env['maintenance.equipment'].create(equipment_vals)
                    _logger.info(f"Équipement créé pour le sous-modèle: {equipment_name}")
        else:
            _logger.info("Création automatique d'équipements désactivée pour ce modèle")

    def import_hierarchy_from_gltf(self, gltf_data, parent_id=False):
        """
        Crée la hiérarchie de sous-modèles selon la structure glTF,
        en utilisant Blender pour extraire chaque nœud individuellement.
        Crée des enregistrements réels dans la table cmms.submodel3d.
        """
        parent_model = self.browse(parent_id)
        if not parent_model.exists():
            _logger.warning(f"Modèle parent ID {parent_id} introuvable")
            return False

        # Créer un fichier GLTF temporaire si c'est un objet de données et non un chemin
        if isinstance(gltf_data, dict):
            import tempfile

            temp_dir = tempfile.mkdtemp()
            temp_gltf_path = os.path.join(temp_dir, "temp_model.gltf")

            try:
                with open(temp_gltf_path, 'w') as f:
                    json.dump(gltf_data, f)
                gltf_file_path = temp_gltf_path
            except Exception as e:
                _logger.error(f"Erreur lors de la création du fichier GLTF temporaire: {str(e)}")
                return False
        else:
            # On suppose que c'est déjà un chemin de fichier
            gltf_file_path = gltf_data

        # Préparer le dossier parent pour les sous-modèles
        parent_dir = os.path.normpath(os.path.join(MODELS_DIR, str(parent_id)))
        childs_dir = os.path.normpath(os.path.join(parent_dir, 'childs'))
        os.makedirs(childs_dir, exist_ok=True)

        # Chemin vers le script d'extraction
        extract_script_path = os.path.normpath(os.path.join(
            os.path.dirname(BLENDER_SCRIPT_PATH),
            "extract_gltf_nodes.py"
        ))

        # Vérifier que le script existe
        if not os.path.isfile(extract_script_path):
            _logger.error(f"Script d'extraction non trouvé: {extract_script_path}")
            return False

        # Exécuter le script Blender pour extraire les nœuds
        cmd = [
            BLENDER_EXE,
            "--background",
            "-noaudio",
            "--python", extract_script_path,
            "--", gltf_file_path, childs_dir
        ]

        _logger.info(f"Exécution de la commande d'extraction: {' '.join(cmd)}")

        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            stdout, stderr = process.communicate()

            # Journaliser la sortie pour le débogage
            _logger.info(f"[EXTRACTION STDOUT]\n{stdout}")
            if stderr:
                _logger.warning(f"[EXTRACTION STDERR]\n{stderr}")

            if process.returncode != 0:
                _logger.error(f"Échec de l'extraction des nœuds (code {process.returncode})")
                return False
        except Exception as e:
            _logger.error(f"Erreur lors de l'exécution du script d'extraction: {str(e)}")
            return False

        # Charger les métadonnées des nœuds extraits
        metadata_path = os.path.join(childs_dir, "nodes_metadata.json")
        if not os.path.isfile(metadata_path):
            _logger.error(f"Métadonnées des nœuds non trouvées: {metadata_path}")
            return False

        try:
            with open(metadata_path, 'r') as f:
                nodes_data = json.load(f)
        except Exception as e:
            _logger.error(f"Erreur lors du chargement des métadonnées: {str(e)}")
            return False

        # Supprimer les anciens sous-modèles s'il y en a
        old_submodels = self.env['cmms.submodel3d'].search([('parent_id', '=', parent_id)])
        if old_submodels:
            _logger.info(f"Suppression de {len(old_submodels)} anciens sous-modèles")
            old_submodels.unlink()

        # Créer les sous-modèles en tant qu'enregistrements réels dans cmms.submodel3d
        submodels_created = 0
        for node_id, node_data in nodes_data.items():
            try:
                node_id_int = int(node_id)  # Convertir l'ID en entier

                # Vérifier que le nœud a été exporté correctement
                node_dir = os.path.join(childs_dir, str(node_id))
                gltf_path = node_data.get("gltf_path")
                bin_path = node_data.get("bin_path")

                if not os.path.isdir(node_dir) or not gltf_path:
                    _logger.warning(f"Dossier ou fichier GLTF manquant pour le nœud {node_id}")
                    continue

                # Ajustement de l'échelle selon les règles définies
                original_scale = float(node_data.get("scale", 1.0))
                adjusted_scale = original_scale
                if original_scale < 0.1:
                    # Si échelle < 0.1, ajouter +2
                    adjusted_scale = original_scale + 2.0
                elif original_scale < 0.5:
                    # Si échelle < 0.5 mais >= 0.1, ajouter +1
                    adjusted_scale = original_scale + 1.0
                else:
                    # Sinon, laisser à 1 par défaut
                    adjusted_scale = 1.0

                _logger.info(f"Échelle ajustée pour le sous-modèle {node_data['name']}: {original_scale} → {adjusted_scale}")

                # Créer un sous-modèle pour ce nœud
                submodel_vals = {
                    "name": node_data["name"],
                    "description": f"Sous-modèle extrait de {parent_model.name}: {node_data['name']}",
                    "parent_id": parent_id,
                    "relative_id": node_id_int,
                    "gltf_filename": os.path.basename(gltf_path),
                    "bin_filename": os.path.basename(bin_path) if bin_path else False,
                    "scale": adjusted_scale,  # Utiliser l'échelle ajustée
                    "position_x": float(node_data.get("position", {}).get("x", 0)),
                    "position_y": float(node_data.get("position", {}).get("y", 0)),
                    "position_z": float(node_data.get("position", {}).get("z", 0)),
                    "rotation_x": float(node_data.get("rotation", {}).get("x", 0)),
                    "rotation_y": float(node_data.get("rotation", {}).get("y", 0)),
                    "rotation_z": float(node_data.get("rotation", {}).get("z", 0)),
                }

                # Créer l'enregistrement du sous-modèle
                submodel = self.env['cmms.submodel3d'].create(submodel_vals)
                submodels_created += 1

                _logger.info(f"Sous-modèle créé: {submodel.name} (ID: {submodel.id}, Relatif: {submodel.relative_id}, Échelle: {adjusted_scale})")

            except Exception as e:
                _logger.error(f"Erreur lors de la création du sous-modèle {node_id}: {str(e)}")
                continue

        # Conserver la structure JSON pour la rétrocompatibilité
        try:
            # Conversion des données des sous-modèles au format JSON
            submodels_json = []
            for node_id, node_data in nodes_data.items():
                # Appliquer la même logique d'ajustement d'échelle pour le JSON
                original_scale = float(node_data.get("scale", 1.0))
                adjusted_scale = original_scale
                if original_scale < 0.1:
                    adjusted_scale = original_scale + 2.0
                elif original_scale < 0.5:
                    adjusted_scale = original_scale + 1.0
                else:
                    adjusted_scale = 1.0

                submodel_data = {
                    "id": int(node_id),
                    "name": node_data["name"],
                    "gltf_path": f"childs/{node_id}/{os.path.basename(node_data.get('gltf_path', ''))}",
                    "bin_path": f"childs/{node_id}/{os.path.basename(node_data.get('bin_path', ''))}" if node_data.get('bin_path') else None,
                    "description": f"Sous-modèle extrait de {parent_model.name}: {node_data['name']}",
                    "scale": adjusted_scale,  # Utiliser l'échelle ajustée
                    "position": {
                        "x": node_data.get("position", {}).get("x", 0),
                        "y": node_data.get("position", {}).get("y", 0),
                        "z": node_data.get("position", {}).get("z", 0)
                    },
                    "rotation": {
                        "x": node_data.get("rotation", {}).get("x", 0),
                        "y": node_data.get("rotation", {}).get("y", 0),
                        "z": node_data.get("rotation", {}).get("z", 0)
                    },
                    "parent_id": node_data.get("parent_id")
                }
                submodels_json.append(submodel_data)

            # Mettre à jour la structure JSON du modèle parent (pour rétrocompatibilité)
            parent_model.write({
                'submodels_json': json.dumps(submodels_json, indent=2)
            })
        except Exception as e:
            _logger.error(f"Erreur lors de la mise à jour du JSON des sous-modèles: {str(e)}")

        # Créer les équipements automatiquement pour les sous-modèles
        try:
            self._create_equipment_for_submodels(parent_model)
        except Exception as e:
            _logger.error(f"Erreur lors de la création des équipements pour les sous-modèles: {str(e)}")

        _logger.info(f"Hiérarchie importée avec succès: {submodels_created} sous-modèles ajoutés au modèle {parent_id}")
        return True

    def _create_equipment_for_submodels(self, parent_model, submodels):
        """Crée des équipements pour chaque sous-modèle"""
        # Cette méthode peut être améliorée pour créer des équipements
        # liés aux sous-modèles virtuels, en se basant sur les métadonnées
        # Pour l'instant, elle ne fait rien pour éviter les doublons
        pass