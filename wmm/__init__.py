"""Windows Maintenance Manager: local maintenance suite for Windows with a web console."""
import sys
from pathlib import Path

APP_NAME = "Windows Maintenance Manager"
VERSION = "2.1.0"
ROOT = Path(__file__).resolve().parent.parent

# The suite reuses the logic of ottimizza_pc.py, which lives next to the package.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
