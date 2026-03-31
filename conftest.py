import sys
import os

# Ensure the project root is on sys.path so `launcher` and other top-level
# packages are importable during test collection without installation.
sys.path.insert(0, os.path.dirname(__file__))
