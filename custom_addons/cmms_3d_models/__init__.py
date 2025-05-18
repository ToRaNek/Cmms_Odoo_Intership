from . import models
from . import controllers

def post_init_hook(cr, registry):
    """Hook exécuté après l'installation du module"""
    from odoo import api, SUPERUSER_ID

    # Créer les rôles par défaut
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['maintenance.role'].create_default_roles()