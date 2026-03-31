import sys
import os

# Insert project root before tests/ so `launcher` resolves to the top-level
# package, not tests/launcher/.
project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)
