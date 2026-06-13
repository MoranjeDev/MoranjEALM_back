# Deploiement PythonAnywhere en SQLite

Ce guide prepare le serveur de test en SQLite. MySQL reste disponible pour un
deploiement production-like, mais le profil ci-dessous evite `mysqlclient` et
reduit le risque de depasser le quota disque PythonAnywhere.

## 1. Variables d'environnement

Dans le fichier WSGI PythonAnywhere, ou dans un fichier `.env` charge par le
WSGI, utiliser au minimum :

```bash
DJANGO_SETTINGS_MODULE=alm.settings.pythonanywhere
DJANGO_SECRET_KEY=change-me-with-a-long-random-secret
DJANGO_DEBUG=0
DJANGO_ALLOWED_HOSTS=moranjealmback.pythonanywhere.com
DJANGO_CORS_ALLOWED_ORIGINS=https://alm.moranjetrade.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://alm.moranjetrade.com
DJANGO_DB_ENGINE=sqlite
SQLITE_PATH=/home/moranjealmback/MoranjEALM_back/db.sqlite3
LICENSE_BYPASS=1
```

Important : `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS` et
`CSRF_TRUSTED_ORIGINS` ne doivent pas contenir de slash final.

## 2. Installation des dependances

Depuis le dossier backend sur PythonAnywhere :

```bash
cd /home/moranjealmback/MoranjEALM_back
python -m venv ~/.virtualenvs/venv
source ~/.virtualenvs/venv/bin/activate
pip install --upgrade pip
pip install -r requirements-pythonanywhere-sqlite.txt
```

Le fichier `requirements-pythonanywhere-sqlite.txt` n'installe pas
`mysqlclient`, `django-auth-ldap` ni `python-ldap`. Si LDAP est necessaire plus
tard, il faudra les rajouter et configurer `LDAP_SERVER_URI`.

## 3. Initialisation SQLite

Pour preparer une base vide avec les tables, groupes, permissions, parametres,
hypotheses, referentiels et un compte administrateur :

```bash
python manage.py prepare_pythonanywhere_sqlite \
  --settings=alm.settings.pythonanywhere \
  --admin-username admin \
  --admin-password 'AdminPass123!' \
  --admin-email admin@local
```

Pour charger aussi le jeu de donnees de demonstration et recalculer les outputs :

```bash
python manage.py prepare_pythonanywhere_sqlite \
  --settings=alm.settings.pythonanywhere \
  --admin-username admin \
  --admin-password 'AdminPass123!' \
  --admin-email admin@local \
  --with-sample \
  --reset-sample
```

La commande execute :

1. `migrate`
2. `bootstrap_alm`
3. `load_sample_data` si demande
4. regeneration des outputs ALM
5. `collectstatic`

## 4. WSGI PythonAnywhere

Dans `/var/www/moranjealmback_pythonanywhere_com_wsgi.py`, verifier que le
chemin backend est bien ajoute et que le module settings est force :

```python
import os
import sys

path = "/home/moranjealmback/MoranjEALM_back"
if path not in sys.path:
    sys.path.insert(0, path)

os.environ["DJANGO_SETTINGS_MODULE"] = "alm.settings.pythonanywhere"
os.environ.setdefault("DJANGO_DB_ENGINE", "sqlite")
os.environ.setdefault("SQLITE_PATH", "/home/moranjealmback/MoranjEALM_back/db.sqlite3")
os.environ.setdefault("DJANGO_ALLOWED_HOSTS", "moranjealmback.pythonanywhere.com")
os.environ.setdefault("DJANGO_CORS_ALLOWED_ORIGINS", "https://alm.moranjetrade.com")
os.environ.setdefault("DJANGO_CSRF_TRUSTED_ORIGINS", "https://alm.moranjetrade.com")
os.environ.setdefault("LICENSE_BYPASS", "1")

from django.core.wsgi import get_wsgi_application

application = get_wsgi_application()
```

Apres modification, cliquer sur **Reload** dans l'onglet Web de PythonAnywhere.

## 5. Mappings static/media PythonAnywhere

Dans l'onglet Web :

| URL | Directory |
| --- | --- |
| `/static/` | `/home/moranjealmback/MoranjEALM_back/staticfiles` |
| `/media/` | `/home/moranjealmback/MoranjEALM_back/media` |

## 6. Verification rapide

```bash
python manage.py check --settings=alm.settings.pythonanywhere
python manage.py showmigrations --settings=alm.settings.pythonanywhere
python manage.py shell --settings=alm.settings.pythonanywhere -c "from django.conf import settings; print(settings.DATABASES['default']); from apps.accounts.models import User; print(User.objects.count())"
```

Ensuite verifier depuis le navigateur :

- `https://moranjealmback.pythonanywhere.com/api/`
- `https://alm.moranjetrade.com`

## 7. Notes importantes

- SQLite convient pour le serveur de test et la recette fonctionnelle.
- Pour plusieurs utilisateurs en charge forte, exports lourds ou gros imports,
  MySQL/PostgreSQL sera preferable.
- Ne pas commiter `db.sqlite3` comme base de production. Elle sert seulement de
  base locale ou de base de test PythonAnywhere.
