import sys
import os

# Ajoutez le dossier du projet au chemin Python
project_home = os.path.expanduser('~/OIFTracker')
if project_home not in sys.path:
    sys.path.insert(0, project_home)

# Importez l'application Flask
from app import app as application
