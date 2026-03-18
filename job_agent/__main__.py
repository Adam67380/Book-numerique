"""Point d'entrée : python -m job_agent"""
import os
from pathlib import Path

# Charger .env si présent (sans dépendance externe)
env_path = Path(__file__).resolve().parent.parent / ".env"
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())

from job_agent.main import main

main()
