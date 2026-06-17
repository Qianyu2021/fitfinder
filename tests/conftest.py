"""
conftest.py

Pytest configuration file. Runs before tests to set up the environment.
Ensures .env is loaded from the project root.
"""

import os
from dotenv import load_dotenv

# Load .env from project root
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
env_path = os.path.join(project_root, ".env")
load_dotenv(env_path)
