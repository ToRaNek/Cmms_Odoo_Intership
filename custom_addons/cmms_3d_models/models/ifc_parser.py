# custom_addons/cmms_3d_models/models/ifc_parser.py
"""
Parser IFC ciblé pour extraire uniquement :
1. Le Header du fichier IFC
2. Les IFCPROPERTYSET et leur contenu
3. Les objets référencés par ces PropertySets (matériaux, etc.)
"""

import re
import json
import logging
from collections import defaultdict

_logger = logging.getLogger(__name__)


class TargetedIfcParser:
    """Parser IFC ciblé pour PropertySets et objets référencés"""

    def __init__(self):
        self.header_info = {}
        self.property_sets = {}
        self.referenced_objects = {}
        self.all_entities = {}  # Cache temporaire pour les références

    def parse_file(self, file_path):
        """Parse un fichier IFC et retourne uniquement les données ciblées"""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()

            return self.parse_content(content)

        except Exception as e:
            _logger.error(f"Erreur lors du parsing IFC: {str(e)}")
            return self._create_error_response(str(e))

    def parse_content(self, content_str):
        """Parse le contenu IFC directement depuis une chaîne"""
        try:
            # 1. Parser le header
            self._parse_header(content_str)

            # 2. Parser toutes les entités (pour les références)
            self._parse_all_entities(content_str)

            # 3. Extraire les IFCPROPERTYSET spécifiquement
            self._extract_property_sets()

            # 4. Extraire les objets référencés par les PropertySets
            self._extract_referenced_objects()

            # 5. Construire la réponse JSON finale
            return self._build_targeted_json()

        except Exception as e:
            _logger.error(f"Erreur lors du parsing IFC: {str(e)}")
            return self._create_error_response(str(e))

    def _parse_header(self, content):
        """Extrait uniquement les informations du header IFC"""
        header_section = re.search(r'HEADER;(.*?)ENDSEC;', content, re.DOTALL)
        if not header_section:
            return

        header_content = header_section.group(1)

        # Extraire FILE_DESCRIPTION
        file_desc = re.search(r"FILE_DESCRIPTION\((.*?)\);", header_content, re.DOTALL)
        if file_desc:
            self.header_info['FILE_DESCRIPTION'] = file_desc.group(1)

        # Extraire FILE_NAME
        file_name = re.search(r"FILE_NAME\('([^']*)'", header_content)
        if file_name:
            self.header_info['FILE_NAME'] = file_name.group(1)

        # Extraire FILE_SCHEMA - Version IFC
        file_schema = re.search(r"FILE_SCHEMA\(\('([^']*)'", header_content)
        if file_schema:
            self.header_info['FILE_SCHEMA'] = file_schema.group(1)
            self.header_info['IFC_VERSION'] = file_schema.group(1)

    def _parse_all_entities(self, content):
        """Parse toutes les entités pour créer un cache des références"""
        data_section = re.search(r'DATA;(.*?)ENDSEC;', content, re.DOTALL)
        if not data_section:
            return

        data_content = data_section.group(1)

        # Pattern pour toutes les entités #ID=TYPE(...)
        entity_pattern = r'#(\d+)=(\w+)\((.*?)\);'
        entities = re.findall(entity_pattern, data_content, re.DOTALL)

        for entity_id, entity_type, entity_data in entities:
            self.all_entities[entity_id] = {
                'id': entity_id,
                'type': entity_type,
                'data': entity_data.strip()
            }

    def _extract_property_sets(self):
        """Extrait uniquement les IFCPROPERTYSET"""
        for entity_id, entity in self.all_entities.items():
            if entity['type'] == 'IFCPROPERTYSET':
                # Parser les paramètres du PropertySet
                params = self._parse_entity_parameters(entity['data'])

                property_set = {
                    'Entity': 'IFCPROPERTYSET',
                    'Id': entity_id,
                    'Guid': self._clean_parameter(params[0]) if len(params) > 0 else None,
                    'OwnerHistory': self._clean_parameter(params[1]) if len(params) > 1 else None,
                    'Name': self._clean_parameter(params[2]) if len(params) > 2 else None,
                    'Description': self._clean_parameter(params[3]) if len(params) > 3 else None,
                    'HasProperties': []
                }

                # Extraire les propriétés du PropertySet (ObjectType dans votre exemple)
                if len(params) > 4:
                    properties_param = params[4]
                    property_refs = self._extract_references(properties_param)

                    for prop_ref in property_refs:
                        if prop_ref in self.all_entities:
                            prop_entity = self.all_entities[prop_ref]
                            property_data = self._parse_property(prop_entity)
                            if property_data:
                                property_set['HasProperties'].append(property_data)

                # Ajouter ObjectType formaté comme dans votre exemple
                if len(params) > 4:
                    property_set['ObjectType'] = params[4]

                # Stocker le PropertySet
                pset_name = property_set['Name'] or f"PropertySet_{entity_id}"
                self.property_sets[pset_name] = property_set

                _logger.info(f"PropertySet extrait: {pset_name} avec {len(property_set['HasProperties'])} propriétés")

    def _parse_property(self, prop_entity):
        """Parse une propriété individuelle (IFCPROPERTYSINGLEVALUE, etc.)"""
        try:
            prop_type = prop_entity['type']
            params = self._parse_entity_parameters(prop_entity['data'])

            if prop_type == 'IFCPROPERTYSINGLEVALUE':
                return {
                    'Type': prop_type,
                    'Id': prop_entity['id'],
                    'Name': self._clean_parameter(params[0]) if len(params) > 0 else None,
                    'Description': self._clean_parameter(params[1]) if len(params) > 1 else None,
                    'NominalValue': self._clean_parameter(params[2]) if len(params) > 2 else None,
                    'Unit': self._clean_parameter(params[3]) if len(params) > 3 else None
                }
            elif prop_type in ['IFCPROPERTYENUMERATEDVALUE', 'IFCPROPERTYBOUNDEDVALUE', 'IFCPROPERTYLISTVALUE']:
                return {
                    'Type': prop_type,
                    'Id': prop_entity['id'],
                    'Name': self._clean_parameter(params[0]) if len(params) > 0 else None,
                    'Description': self._clean_parameter(params[1]) if len(params) > 1 else None,
                    'Values': params[2:] if len(params) > 2 else []
                }
            else:
                # Propriété générique
                return {
                    'Type': prop_type,
                    'Id': prop_entity['id'],
                    'RawData': params
                }

        except Exception as e:
            _logger.warning(f"Erreur lors du parsing de la propriété {prop_entity['id']}: {str(e)}")
            return None

    def _extract_referenced_objects(self):
        """Extrait les objets référencés par les PropertySets (matériaux, etc.)"""
        referenced_ids = set()

        # Collecter toutes les références dans les PropertySets
        for pset_name, pset in self.property_sets.items():
            for prop in pset.get('HasProperties', []):
                # Chercher des références dans les valeurs
                for key, value in prop.items():
                    if isinstance(value, str):
                        refs = self._extract_references(value)
                        referenced_ids.update(refs)
                    elif isinstance(value, list):
                        for item in value:
                            if isinstance(item, str):
                                refs = self._extract_references(item)
                                referenced_ids.update(refs)

        # Extraire les objets référencés
        for ref_id in referenced_ids:
            if ref_id in self.all_entities:
                entity = self.all_entities[ref_id]
                entity_type = entity['type']

                # Ne garder que les types d'objets intéressants
                interesting_types = [
                    'IFCMATERIAL', 'IFCMATERIALLAYER', 'IFCMATERIALLAYERSET',
                    'IFCMATERIALCONSTITUENT', 'IFCMATERIALCONSTITUENTSET',
                    'IFCMATERIALDEFINITION', 'IFCMATERIALPROPERTIES',
                    'IFCPHYSICALQUANTITY', 'IFCQUANTITYLENGTH', 'IFCQUANTITYAREA',
                    'IFCQUANTITYVOLUME', 'IFCQUANTITYWEIGHT', 'IFCQUANTITYCOUNT',
                    'IFCUNIT', 'IFCSIUNIT', 'IFCCONVERSIONBASEDUNIT'
                ]

                if entity_type in interesting_types:
                    self.referenced_objects[ref_id] = self._parse_referenced_object(entity)

    def _parse_referenced_object(self, entity):
        """Parse un objet référencé (matériau, unité, etc.)"""
        params = self._parse_entity_parameters(entity['data'])

        if entity['type'] == 'IFCMATERIAL':
            return {
                'Type': 'IFCMATERIAL',
                'Id': entity['id'],
                'Name': self._clean_parameter(params[0]) if len(params) > 0 else None,
                'Description': self._clean_parameter(params[1]) if len(params) > 1 else None,
                'Category': self._clean_parameter(params[2]) if len(params) > 2 else None
            }
        elif entity['type'] in ['IFCSIUNIT', 'IFCCONVERSIONBASEDUNIT']:
            return {
                'Type': entity['type'],
                'Id': entity['id'],
                'UnitType': self._clean_parameter(params[0]) if len(params) > 0 else None,
                'Name': self._clean_parameter(params[1]) if len(params) > 1 else None,
                'Prefix': self._clean_parameter(params[2]) if len(params) > 2 else None
            }
        else:
            # Objet générique
            return {
                'Type': entity['type'],
                'Id': entity['id'],
                'Parameters': [self._clean_parameter(p) for p in params]
            }

    def _extract_references(self, text):
        """Extrait les références #ID depuis un texte"""
        if not text:
            return []

        # Pattern pour trouver les références #123
        refs = re.findall(r'#(\d+)', str(text))
        return refs

    def _parse_entity_parameters(self, entity_data):
        """Parse les paramètres d'une entité IFC"""
        params = []
        current_param = ""
        paren_count = 0
        quote_count = 0

        for char in entity_data:
            if char == "'" and paren_count == 0:
                quote_count = (quote_count + 1) % 2
            elif char == '(' and quote_count == 0:
                paren_count += 1
            elif char == ')' and quote_count == 0:
                paren_count -= 1
            elif char == ',' and paren_count == 0 and quote_count == 0:
                params.append(current_param.strip())
                current_param = ""
                continue

            current_param += char

        if current_param.strip():
            params.append(current_param.strip())

        return params

    def _clean_parameter(self, param):
        """Nettoie un paramètre IFC"""
        if not param or param == '$':
            return None

        param = param.strip()

        # Enlever les quotes
        if param.startswith("'") and param.endswith("'"):
            param = param[1:-1]

        # Décoder les caractères spéciaux IFC
        param = self._decode_ifc_string(param)

        return param if param else None

    def _decode_ifc_string(self, s):
        """Décode les caractères spéciaux IFC (format \\X2\\...\\X0\\)"""
        if not s:
            return s

        # Pattern pour les séquences unicode IFC - utilisation d'un raw string
        pattern = r'\\X2\\([0-9A-F]+)\\X0\\'

        def replace_unicode(match):
            hex_code = match.group(1)
            try:
                return chr(int(hex_code, 16))
            except ValueError:
                return match.group(0)

        return re.sub(pattern, replace_unicode, s)

    def _build_targeted_json(self):
        """Construit la structure JSON ciblée finale"""
        result = {
            'parsing_mode': 'targeted',
            'description': 'Parser IFC ciblé - Header + PropertySets + Objets référencés',
            'header': self.header_info,
            'file_info': {
                'name': self.header_info.get('FILE_NAME', 'unknown.ifc'),
                'version': self.header_info.get('IFC_VERSION', 'Unknown'),
                'schema': self.header_info.get('FILE_SCHEMA', 'Unknown')
            },
            'property_sets': self.property_sets,
            'referenced_objects': self.referenced_objects,
            'summary': {
                'property_sets_count': len(self.property_sets),
                'referenced_objects_count': len(self.referenced_objects),
                'property_sets_names': list(self.property_sets.keys())
            }
        }

        _logger.info(f"Parser IFC ciblé terminé: {len(self.property_sets)} PropertySets, "
                    f"{len(self.referenced_objects)} objets référencés")

        return result

    def _create_error_response(self, error_message):
        """Crée une réponse d'erreur"""
        return {
            'error': True,
            'message': error_message,
            'parsing_mode': 'targeted',
            'header': self.header_info,
            'file_info': {
                'name': self.header_info.get('FILE_NAME', 'unknown.ifc'),
                'version': 'Error parsing',
                'schema': 'Error parsing'
            },
            'property_sets': {},
            'referenced_objects': {},
            'summary': {
                'property_sets_count': 0,
                'referenced_objects_count': 0,
                'property_sets_names': []
            }
        }


def parse_ifc_file_targeted(file_path):
    """Fonction utilitaire pour parser un fichier IFC de manière ciblée"""
    parser = TargetedIfcParser()
    return parser.parse_file(file_path)


def parse_ifc_content_targeted(content):
    """Fonction utilitaire pour parser le contenu IFC de manière ciblée"""
    parser = TargetedIfcParser()
    return parser.parse_content(content)


# Exemple d'utilisation
if __name__ == "__main__":
    # Test avec l'exemple fourni
    test_content = r"""ISO-10303-21;
HEADER;
FILE_DESCRIPTION(('ViewDefinition[DesignTransferView]'),'2;1');
FILE_NAME('Escovas.ifc','2025-05-19T17:27:26+01:00',(''),(''),'IfcOpenShell 0.8.1','Bonsai 0.8.1','Nobody');
FILE_SCHEMA(('IFC4'));
ENDSEC;
DATA;
#1=IFCPROJECT('3RbYoGs1TDoxuin$YYdftm',$,'My Project',$,$,$,$,(#14,#26),#9);
#10650=IFCPROPERTYSET('2tvYLV7_93sQAW9wY7_ii1',$,'Pset_EscovaPantografo',$,(#10652,#10653,#10654));
#10652=IFCPROPERTYSINGLEVALUE('Material',$,IFCLABEL('Graphite'),$);
#10653=IFCPROPERTYSINGLEVALUE('Conductivity',$,IFCREAL(0.75),$);
#10654=IFCPROPERTYSINGLEVALUE('Resistance',$,IFCREAL(0.25),$);
#10655=IFCPROPERTYSET('34u7R33IXBBwuU3O59Sp76',$,'Pset_EscovaPantografo_cobre',$,(#10657,#10658,#10659));
#10657=IFCPROPERTYSINGLEVALUE('Material',$,IFCLABEL('Copper'),$);
#10658=IFCPROPERTYSINGLEVALUE('Conductivity',$,IFCREAL(0.95),$);
#10659=IFCPROPERTYSINGLEVALUE('Resistance',$,IFCREAL(0.05),$);
#2=IFCDISCRETEACCESSORY('2qwcb7o29869TSTrSREy$_',$,'Escova de grafite pantógrafo',$,$,$,$,$,$,.NOTDEFINED.);
#3=IFCDISCRETEACCESSORY('18XZ3qWxbEWxii7Ol2ZZ$Z',$,'Cobre Condutor',$,$,$,$,$,$,.NOTDEFINED.);
ENDSEC;
END-ISO-10303-21;"""

    parser = TargetedIfcParser()
    result = parser.parse_content(test_content)
    print(json.dumps(result, indent=2, ensure_ascii=False))