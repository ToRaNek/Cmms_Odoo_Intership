# external_apps/odoo_client_app/main.py
#!/usr/bin/env python3
"""
Application cliente pour se connecter à Odoo via XML-RPC
Résout le problème de protection CSRF d'Odoo 16
"""

import sys
import os
from datetime import datetime

# Ajouter le répertoire parent au PYTHONPATH si nécessaire
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from odoo_client import OdooXMLRPCClient
from config.odoo_config import CURRENT_CONFIG

def test_basic_connection():
    """Test de connexion de base"""
    print("=== Test de connexion Odoo via XML-RPC ===")
    print(f"URL: {CURRENT_CONFIG['url']}")
    print(f"DB: {CURRENT_CONFIG['db']}")
    print(f"User: {CURRENT_CONFIG['username']}")
    print("-" * 50)
    
    # Créer le client
    client = OdooXMLRPCClient(**CURRENT_CONFIG)
    
    # Tenter la connexion
    if client.authenticate():
        print("✅ Connexion réussie - Problème CSRF résolu !")
        return client
    else:
        print("❌ Échec de la connexion")
        print("Vérifiez votre configuration dans config/odoo_config.py")
        return None

def test_users(client):
    """Test de lecture des utilisateurs"""
    print("\n=== Test des utilisateurs ===")
    try:
        users = client.search_read(
            'res.users',
            domain=[['active', '=', True]],
            fields=['name', 'login', 'email'],
            limit=5
        )
        
        print(f"Utilisateurs actifs trouvés: {len(users)}")
        for user in users:
            print(f"  - {user['name']} ({user['login']}) - {user.get('email', 'N/A')}")
        
        return True
    except Exception as e:
        print(f"Erreur lors de la lecture des utilisateurs: {e}")
        return False

def test_partners(client):
    """Test de lecture des partenaires"""
    print("\n=== Test des partenaires ===")
    try:
        # Compter les partenaires
        partner_count = client.search_count('res.partner')
        print(f"Nombre total de partenaires: {partner_count}")
        
        # Lire quelques partenaires entreprises
        companies = client.search_read(
            'res.partner',
            domain=[['is_company', '=', True]],
            fields=['name', 'email', 'phone', 'website'],
            limit=3
        )
        
        print(f"Entreprises trouvées: {len(companies)}")
        for company in companies:
            print(f"  - {company['name']}")
            print(f"    Email: {company.get('email', 'N/A')}")
            print(f"    Téléphone: {company.get('phone', 'N/A')}")
            print(f"    Site: {company.get('website', 'N/A')}")
            print()
        
        return True
    except Exception as e:
        print(f"Erreur lors de la lecture des partenaires: {e}")
        return False

def test_create_partner(client):
    """Test de création d'un partenaire"""
    print("\n=== Test de création d'un partenaire ===")
    try:
        # Créer un nouveau partenaire
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        partner_data = {
            'name': f'Test Partner {timestamp}',
            'email': f'test_{timestamp}@example.com',
            'phone': '+33123456789',
            'is_company': False,
            'comment': f'Créé via XML-RPC le {datetime.now().strftime("%d/%m/%Y %H:%M:%S")}'
        }
        
        partner_id = client.create('res.partner', partner_data)
        print(f"✅ Nouveau partenaire créé avec l'ID: {partner_id}")
        
        # Lire le partenaire créé pour vérification
        created_partner = client.read('res.partner', [partner_id])
        print(f"Vérification - Nom: {created_partner[0]['name']}")
        
        return partner_id
    except Exception as e:
        print(f"❌ Erreur lors de la création du partenaire: {e}")
        return None

def test_update_partner(client, partner_id):
    """Test de mise à jour d'un partenaire"""
    print("\n=== Test de mise à jour d'un partenaire ===")
    try:
        # Mettre à jour le partenaire
        update_data = {
            'mobile': '+33987654321',
            'comment': f'Mis à jour via XML-RPC le {datetime.now().strftime("%d/%m/%Y %H:%M:%S")}'
        }
        
        success = client.write('res.partner', [partner_id], update_data)
        if success:
            print("✅ Partenaire mis à jour avec succès")
            
            # Vérifier la mise à jour
            updated_partner = client.read('res.partner', [partner_id], ['mobile', 'comment'])
            print(f"Mobile: {updated_partner[0]['mobile']}")
            print(f"Commentaire: {updated_partner[0]['comment']}")
        else:
            print("❌ Échec de la mise à jour")
        
        return success
    except Exception as e:
        print(f"❌ Erreur lors de la mise à jour: {e}")
        return False

def test_fields_info(client):
    """Test de récupération des informations sur les champs"""
    print("\n=== Test des informations sur les champs ===")
    try:
        # Récupérer les définitions de quelques champs
        fields_info = client.fields_get('res.partner', ['name', 'email', 'phone', 'is_company'])
        
        print("Champs du modèle res.partner:")
        for field_name, field_def in fields_info.items():
            field_type = field_def.get('type', 'N/A')
            field_string = field_def.get('string', 'N/A')
            required = field_def.get('required', False)
            readonly = field_def.get('readonly', False)
            
            print(f"  - {field_name}: {field_string} ({field_type})")
            if required:
                print(f"    ⚠️  Obligatoire")
            if readonly:
                print(f"    🔒 Lecture seule")
        
        return True
    except Exception as e:
        print(f"❌ Erreur lors de la récupération des champs: {e}")
        return False

def run_all_tests():
    """Exécute tous les tests"""
    print("=" * 60)
    print("  APPLICATION CLIENT ODOO XML-RPC")
    print("  Résolution du problème CSRF Odoo 16")
    print("=" * 60)
    
    # Test de connexion
    client = test_basic_connection()
    if not client:
        return False
    
    # Tests de lecture
    test_users(client)
    test_partners(client)
    test_fields_info(client)
    
    # Tests d'écriture (création/modification)
    partner_id = test_create_partner(client)
    if partner_id:
        test_update_partner(client, partner_id)
        
        # Optionnel: supprimer le partenaire de test
        try:
            client.unlink('res.partner', [partner_id])
            print(f"🗑️  Partenaire de test (ID: {partner_id}) supprimé")
        except Exception as e:
            print(f"⚠️  Impossible de supprimer le partenaire de test: {e}")
    
    print("\n" + "=" * 60)
    print("  TOUS LES TESTS TERMINÉS")
    print("=" * 60)
    return True

def interactive_mode():
    """Mode interactif pour tester diverses opérations"""
    print("\n=== Mode interactif ===")
    client = test_basic_connection()
    if not client:
        return
    
    while True:
        print("\nOptions disponibles:")
        print("1. Lister les partenaires")
        print("2. Créer un partenaire")
        print("3. Rechercher des partenaires")
        print("4. Informations sur les champs")
        print("5. Quitter")
        
        choice = input("\nChoisissez une option (1-5): ").strip()
        
        if choice == '1':
            partners = client.search_read('res.partner', [], ['name', 'email'], limit=10)
            for p in partners:
                print(f"  - {p['name']} ({p.get('email', 'N/A')})")
        
        elif choice == '2':
            name = input("Nom du partenaire: ").strip()
            email = input("Email (optionnel): ").strip()
            if name:
                data = {'name': name}
                if email:
                    data['email'] = email
                partner_id = client.create('res.partner', data)
                print(f"Partenaire créé avec l'ID: {partner_id}")
        
        elif choice == '3':
            search_term = input("Terme de recherche: ").strip()
            if search_term:
                partners = client.search_read(
                    'res.partner',
                    domain=[['name', 'ilike', search_term]],
                    fields=['name', 'email'],
                    limit=5
                )
                print(f"Résultats pour '{search_term}':")
                for p in partners:
                    print(f"  - {p['name']} ({p.get('email', 'N/A')})")
        
        elif choice == '4':
            model = input("Modèle (ex: res.partner): ").strip()
            if model:
                try:
                    fields = client.fields_get(model)
                    print(f"Champs du modèle {model}:")
                    for fname, fdef in list(fields.items())[:10]:  # Limiter à 10
                        print(f"  - {fname}: {fdef.get('string', 'N/A')}")
                except Exception as e:
                    print(f"Erreur: {e}")
        
        elif choice == '5':
            print("Au revoir !")
            break
        
        else:
            print("Option invalide")

def main():
    """Fonction principale"""
    if len(sys.argv) > 1 and sys.argv[1] == '--interactive':
        interactive_mode()
    else:
        run_all_tests()

if __name__ == "__main__":
    main()