import os
import base64
import zipfile
import io
import json
import subprocess
import tempfile
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
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

    # Relation hiérarchique parent-enfant
    parent_id = fields.Many2one('cmms.model3d', string='Modèle parent',
                               ondelete='cascade', index=True)
    child_ids = fields.One2many('cmms.model3d', 'parent_id', string='Sous-modèles')
    is_submodel = fields.Boolean(compute='_compute_is_submodel', store=False,
                                string='Est un sous-modèle')
    complete_name = fields.Char('Nom complet', compute='_compute_complete_name',
                              store=False)  # Ne pas stocker ce champ
    child_count = fields.Integer(compute='_compute_child_count', string='Nombre de sous-modèles')

    @api.depends('child_ids')
    def _compute_child_count(self):
        for record in self:
            record.child_count = len(record.child_ids)

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

            # Check if it's a GLTF file and parse it to see if it references external files
            if record.model_filename.endswith('.gltf'):
                self._analyze_gltf_references(record, file_path)
                
                # Importer la hiérarchie directement après sauvegarde du glTF principal
                try:
                    with open(file_path, 'r') as f:
                        gltf_data = json.load(f)
                    if 'nodes' in gltf_data and gltf_data['nodes']:
                        _logger.info(f"Import de la hiérarchie depuis le fichier glTF sauvegardé: {file_path}")
                        self.import_hierarchy_from_gltf(gltf_data, record.id)
                except Exception as e:
                    _logger.error(f"Erreur lors de l'importation de la hiérarchie depuis glTF: {str(e)}")

            _logger.info(f"Modèle 3D sauvegardé: {file_path}")
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
                # Vérifier si le fichier GLTF a une structure hiérarchique
                with open(converted_file, 'r') as f:
                    gltf_data = json.load(f)

                # Importer la hiérarchie si le fichier contient des nodes
                if 'nodes' in gltf_data and gltf_data['nodes']:
                    _logger.info(f"Le fichier GLTF contient des nodes, création des sous-modèles et équipements...")
                    
                    # Créer un modèle parent pour la hiérarchie
                    parent_id = record.id
                    
                    # Importer la hiérarchie et créer les équipements
                    created_ids = self.import_hierarchy_from_gltf(gltf_data, parent_id)
                    
                    _logger.info(f"Hiérarchie importée avec succès: {len(created_ids)} sous-modèles et équipements créés")
            except Exception as e:
                _logger.error(f"Erreur lors de l'importation de la hiérarchie GLTF: {str(e)}")
                # Ne pas faire échouer la conversion si l'importation de la hiérarchie échoue
                # juste logger l'erreur

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

                        # Analyser le fichier GLTF pour en extraire la hiérarchie
                        try:
                            # Vérifier si le fichier GLTF a une structure hiérarchique
                            with open(converted_file, 'r') as f:
                                gltf_data = json.load(f)

                            # Importer la hiérarchie si le fichier contient des nodes
                            if 'nodes' in gltf_data and gltf_data['nodes']:
                                _logger.info(f"Le fichier GLTF (ZIP) contient des nodes, création des sous-modèles et équipements...")
                                
                                # Créer un modèle parent pour la hiérarchie
                                parent_id = record.id
                                
                                # Importer la hiérarchie et créer les équipements
                                created_ids = self.import_hierarchy_from_gltf(gltf_data, parent_id)
                                
                                _logger.info(f"Hiérarchie importée avec succès depuis ZIP: {len(created_ids)} sous-modèles et équipements créés")
                        except Exception as e:
                            _logger.error(f"Erreur lors de l'importation de la hiérarchie GLTF (ZIP): {str(e)}")
                            # Ne pas faire échouer la conversion si l'importation de la hiérarchie échoue
                            # juste logger l'erreur
                    else:
                        # Pour les zip contenant gltf ou glb directement
                        record.model_format = 'gltf' if main_file.endswith('.gltf') else 'glb'
                        record.is_converted_from_blend = False
                        with open(main_file_path, 'rb') as f:
                            record.model_file = base64.b64encode(f.read())
                        record.model_filename = os.path.basename(main_file)

                        # Si c'est un fichier GLTF, analyser sa hiérarchie
                        if main_file.endswith('.gltf'):
                            try:
                                with open(main_file_path, 'r') as f:
                                    gltf_data = json.load(f)

                                # Importer la hiérarchie si le fichier contient des nodes
                                if 'nodes' in gltf_data and gltf_data['nodes']:
                                    _logger.info(f"Le fichier GLTF ZIP contient des nodes, création des sous-modèles et équipements...")
                                    
                                    # Créer un modèle parent pour la hiérarchie
                                    parent_id = record.id
                                    
                                    # Importer la hiérarchie et créer les équipements
                                    created_ids = self.import_hierarchy_from_gltf(gltf_data, parent_id)
                                    
                                    _logger.info(f"Hiérarchie importée avec succès depuis ZIP direct: {len(created_ids)} sous-modèles et équipements créés")
                            except Exception as e:
                                _logger.error(f"Erreur lors de l'importation de la hiérarchie GLTF depuis ZIP direct: {str(e)}")

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

        if include_children and self.child_ids:
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
        action = self.env.ref('cmms_3d_models.action_cmms_model3d').read()[0]
        action['domain'] = [('parent_id', '=', self.id)]
        action['context'] = {'default_parent_id': self.id}
        return action

    def import_hierarchy_from_gltf(self, gltf_data, parent_id=False, parent_disk_path=None):
        """
        Crée la hiérarchie de sous-modèles et équipements selon la structure glTF,
        chaque enfant est dans models/<id_parent>/child/<id_enfant>/
        """
        Model3D = self.env['cmms.model3d']
        Equipment = self.env['maintenance.equipment']
        created_ids = []

        nodes = gltf_data.get('nodes', [])
        if not nodes:
            return []

        # Utilisé pour retrouver le parent Odoo de l'ID glTF
        node_odoo_id = {}
        node_disk_path = {}

        # Première passe: créer tous les sous-modèles et équipements
        for idx, node in enumerate(nodes):
            node_name = node.get('name', f'Objet_{idx}')
            
            # Créer le sous-modèle
            submodel = Model3D.create({
                'name': node_name,
                'parent_id': parent_id,
                'model_format': 'gltf',
                'active': True,
                'description': node.get('extras', {}).get('description', 'Sous-modèle importé depuis GLTF'),
            })
            created_ids.append(submodel.id)
            node_odoo_id[idx] = submodel.id

            # Détermine le chemin sur disque du parent (racine ou sous-child)
            if parent_disk_path:
                submodel_disk_root = os.path.join(parent_disk_path, 'child', str(submodel.id))
            else:
                parent_model = Model3D.browse(parent_id)
                submodel_disk_root = os.path.join(MODELS_DIR, str(parent_model.id), 'child', str(submodel.id))
            
            os.makedirs(submodel_disk_root, exist_ok=True)
            node_disk_path[idx] = submodel_disk_root

            # Génère un fichier glTF placeholder pour le sous-modèle
            gltf_file_path = os.path.join(submodel_disk_root, f"{node_name}.gltf")
            with open(gltf_file_path, "w", encoding="utf-8") as f:
                f.write(f'{{"node": {idx}, "name": "{node_name}"}}')  # Placeholder simple

            # Mise à jour des informations du modèle
            submodel.model_filename = f"{node_name}.gltf"
            # URL relative pour le web
            submodel.model_url = f"/models3d/{parent_id}/child/{submodel.id}/{node_name}.gltf"

            # Créer l'équipement automatiquement lié à ce sous-modèle
            equip_vals = {
                'name': f"Équipement {node_name}",
                'model3d_id': submodel.id,
            }
            self.env['maintenance.equipment'].create(equip_vals)
            _logger.info(f"Créé sous-modèle et équipement pour le node {node_name}")

        # Deuxième passe: établir les relations parent/enfant dans la hiérarchie
        for idx, node in enumerate(nodes):
            if 'children' in node:
                for child_idx in node['children']:
                    # Appel récursif pour traiter les enfants de ce nœud
                    self.import_hierarchy_from_gltf(
                        gltf_data,
                        parent_id=node_odoo_id[idx],
                        parent_disk_path=node_disk_path[idx]
                    )

        return created_ids
