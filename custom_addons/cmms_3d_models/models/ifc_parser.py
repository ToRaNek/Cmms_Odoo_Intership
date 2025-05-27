# custom_addons/cmms_3d_models/models/ifc_parser.py
"""
Parser IFC simple pour extraire les données BIM au format JSON
Compatible avec les environnements sans IfcOpenShell
"""

import re
import json
import logging
from collections import defaultdict

_logger = logging.getLogger(__name__)


class SimpleIfcParser:
    """Parser IFC simple pour extraire les données essentielles"""
    
    def __init__(self):
        self.entities = {}
        self.header_info = {}
        self.property_sets = defaultdict(dict)
        self.elements = defaultdict(dict)
    
    def parse_file(self, file_path):
        """Parse un fichier IFC et retourne les données JSON"""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            # Parser le header
            self._parse_header(content)
            
            # Parser les entités
            self._parse_entities(content)
            
            # Construire la structure JSON finale
            return self._build_json_structure()
            
        except Exception as e:
            _logger.error(f"Erreur lors du parsing IFC: {str(e)}")
            return self._create_error_response(str(e))
    
    def parse_content(self, content_str):
        """Parse le contenu IFC directement depuis une chaîne"""
        try:
            # Parser le header
            self._parse_header(content_str)
            
            # Parser les entités
            self._parse_entities(content_str)
            
            # Construire la structure JSON finale
            return self._build_json_structure()
            
        except Exception as e:
            _logger.error(f"Erreur lors du parsing IFC: {str(e)}")
            return self._create_error_response(str(e))
    
    def _parse_header(self, content):
        """Extrait les informations du header IFC"""
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
        
        # Extraire FILE_SCHEMA - C'est la version IFC
        file_schema = re.search(r"FILE_SCHEMA\(\('([^']*)'", header_content)
        if file_schema:
            self.header_info['FILE_SCHEMA'] = file_schema.group(1)
            self.header_info['IFC_VERSION'] = file_schema.group(1)
    
    def _parse_entities(self, content):
        """Parse les entités IFC de la section DATA"""
        data_section = re.search(r'DATA;(.*?)ENDSEC;', content, re.DOTALL)
        if not data_section:
            return
        
        data_content = data_section.group(1)
        
        # Trouver toutes les entités avec pattern #ID=IFCTYPE(...)
        entity_pattern = r'#(\d+)=(\w+)\((.*?)\);'
        entities = re.findall(entity_pattern, data_content, re.DOTALL)
        
        for entity_id, entity_type, entity_data in entities:
            self.entities[entity_id] = {
                'id': entity_id,
                'type': entity_type,
                'data': entity_data.strip()
            }
            
            # Parser les données spécifiques selon le type
            if entity_type.startswith('IFC'):
                self._parse_ifc_entity(entity_id, entity_type, entity_data)
    
    def _parse_ifc_entity(self, entity_id, entity_type, entity_data):
        """Parse une entité IFC spécifique"""
        # Parser les paramètres de base
        params = self._parse_entity_parameters(entity_data)
        
        # Structure de base pour l'entité
        entity_info = {
            'Entity': entity_type,
            'Id': entity_id,
            'Guid': None,
            'Name': None,
            'Description': None,
            'ObjectType': None,
            'Tag': None,
            'PredefinedType': None
        }
        
        # Extraire les paramètres courants selon l'ordre IFC standard
        if len(params) > 0:
            entity_info['Guid'] = self._clean_parameter(params[0])
        if len(params) > 2:
            entity_info['Name'] = self._clean_parameter(params[2])
        if len(params) > 3:
            entity_info['Description'] = self._clean_parameter(params[3])
        if len(params) > 4:
            entity_info['ObjectType'] = self._clean_parameter(params[4])
        
        # Chercher les Property Sets associés
        if entity_type in ['IFCDISCRETEACCESSORY', 'IFCBUILDINGELEMENT', 'IFCPRODUCT']:
            self._find_property_sets_for_entity(entity_id, entity_info)
        
        # Stocker l'entité
        if entity_type not in self.elements:
            self.elements[entity_type] = []
        
        self.elements[entity_type].append(entity_info)
    
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
        """Décode les caractères spéciaux IFC (format \X2\...\X0\)"""
        if not s:
            return s
        
        # Pattern pour les séquences unicode IFC
        pattern = r'\\X2\\([0-9A-F]+)\\X0\\'
        
        def replace_unicode(match):
            hex_code = match.group(1)
            try:
                # Convertir le code hexadécimal en caractère unicode
                return chr(int(hex_code, 16))
            except ValueError:
                return match.group(0)  # Retourner l'original si erreur
        
        return re.sub(pattern, replace_unicode, s)
    
    def _find_property_sets_for_entity(self, entity_id, entity_info):
        """Trouve les Property Sets associés à une entité"""
        # Cette méthode devrait être améliorée pour parser les relations IFC
        # Pour l'instant, on cherche les Pset_ dans les entités
        psets = {}
        
        for eid, entity in self.entities.items():
            if entity['type'] == 'IFCPROPERTYSET':
                # Parser les propriétés du Property Set
                props = self._parse_property_set(entity['data'])
                if props and 'name' in props:
                    # Ajouter au Property Set si le nom commence par Pset_
                    if props['name'] and props['name'].startswith('Pset_'):
                        psets[props['name']] = props.get('properties', {})
        
        if psets:
            entity_info.update(psets)
    
    def _parse_property_set(self, pset_data):
        """Parse un Property Set IFC"""
        params = self._parse_entity_parameters(pset_data)
        
        result = {
            'name': None,
            'properties': {}
        }
        
        if len(params) > 2:
            result['name'] = self._clean_parameter(params[2])
        
        # Parser les propriétés (très simplifié)
        # Dans un vrai parser, il faudrait suivre les références
        return result
    
    def _build_json_structure(self):
        """Construit la structure JSON finale"""
        result = {
            'header': self.header_info,
            'file_info': {
                'name': self.header_info.get('FILE_NAME', 'unknown.ifc'),
                'version': self.header_info.get('IFC_VERSION', 'Unknown'),
                'schema': self.header_info.get('FILE_SCHEMA', 'Unknown')
            },
            'entities': {},
            'summary': {
                'total_entities': len(self.entities),
                'entity_types': {}
            }
        }
        
        # Compter les types d'entités
        for entity_type, entities_list in self.elements.items():
            result['entities'][entity_type] = entities_list
            result['summary']['entity_types'][entity_type] = len(entities_list)
        
        # Exemple de structure pour correspondre à l'exemple demandé
        if 'IFCDISCRETEACCESSORY' in self.elements:
            # Restructurer pour correspondre à l'exemple
            accessories = []
            for entity in self.elements['IFCDISCRETEACCESSORY']:
                accessory = {
                    'Entity': entity['Entity'],
                    'Guid': entity['Guid'],
                    'Name': entity['Name'],
                    'Description': entity['Description'],
                    'ObjectType': entity['ObjectType'],
                    'Tag': entity['Tag'],
                    'PredefinedType': entity.get('PredefinedType', 'NOTDEFINED')
                }
                
                # Ajouter tous les autres champs comme Property Sets
                for key, value in entity.items():
                    if key not in ['Entity', 'Guid', 'Name', 'Description', 'ObjectType', 'Tag', 'PredefinedType', 'Id']:
                        accessory[key] = value
                
                accessories.append(accessory)
            
            if accessories:
                result['IfcDiscreteAccessory'] = accessories
        
        return result
    
    def _create_error_response(self, error_message):
        """Crée une réponse d'erreur"""
        return {
            'error': True,
            'message': error_message,
            'header': self.header_info,
            'file_info': {
                'name': self.header_info.get('FILE_NAME', 'unknown.ifc'),
                'version': self.header_info.get('IFC_VERSION', 'Error parsing'),
                'schema': self.header_info.get('FILE_SCHEMA', 'Error parsing')
            },
            'entities': {},
            'summary': {
                'total_entities': 0,
                'entity_types': {}
            }
        }


def parse_ifc_file(file_path):
    """Fonction utilitaire pour parser un fichier IFC"""
    parser = SimpleIfcParser()
    return parser.parse_file(file_path)


def parse_ifc_content(content):
    """Fonction utilitaire pour parser le contenu IFC"""
    parser = SimpleIfcParser()
    return parser.parse_content(content)


# Exemple d'utilisation et test
if __name__ == "__main__":
    # Test avec l'exemple fourni
    test_content = """ISO-10303-21;
HEADER;
FILE_DESCRIPTION(('ViewDefinition[DesignTransferView]'),'2;1');
FILE_NAME('Escovas.ifc','2025-05-19T17:27:26+01:00',(''),(''),'IfcOpenShell 0.8.1','Bonsai 0.8.1','Nobody');
FILE_SCHEMA(('IFC4'));
ENDSEC;
DATA;
#1=IFCPROJECT('3RbYoGs1TDoxuin$YYdftm',$,'My Project',$,$,$,$,(#14,#26),#9);
#2=IFCDISCRETEACCESSORY('2qwcb7o29869TSTrSREy$_',$,'Escova de grafite pant\\X2\\00F3\\X0\\grafo',$,$,$,$,$,$,.NOTDEFINED.);
#3=IFCDISCRETEACCESSORY('18XZ3qWxbEWxii7Ol2ZZ$Z',$,'Cobre Condutor',$,$,$,$,$,$,.NOTDEFINED.);
ENDSEC;
END-ISO-10303-21;"""
    
    parser = SimpleIfcParser()
    result = parser.parse_content(test_content)
    print(json.dumps(result, indent=2, ensure_ascii=False))
