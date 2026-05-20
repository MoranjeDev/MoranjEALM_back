# Permet d'utiliser PyMySQL en remplacement de mysqlclient quand ce dernier
# ne se compile pas (cas fréquent en développement sur macOS).
# En production (Docker), c'est mysqlclient qui est utilisé via Dockerfile.prod.
try:
    import pymysql
    pymysql.install_as_MySQLdb()
except ImportError:
    # mysqlclient est installé : on l'utilise tel quel.
    pass

from .celery import app as celery_app

__all__ = ("celery_app",)
