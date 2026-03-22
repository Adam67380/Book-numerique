"""Point d'entrée : python -m vinted_agent"""

import argparse
import sys

from .config import load_config, save_default_config
from .scanner import VintedScanner


def main():
    parser = argparse.ArgumentParser(
        description="Agent Vinted — Détecte les bonnes affaires pour l'achat/revente"
    )
    parser.add_argument(
        "--config", "-c",
        default="config/vinted_config.yaml",
        help="Chemin vers le fichier de configuration YAML",
    )
    parser.add_argument(
        "--init-config",
        action="store_true",
        help="Crée un fichier de configuration par défaut",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Exécute un seul scan puis quitte",
    )
    parser.add_argument(
        "--country",
        default=None,
        choices=["fr", "be", "es", "it", "de", "nl", "uk"],
        help="Pays Vinted (défaut: fr)",
    )

    args = parser.parse_args()

    if args.init_config:
        save_default_config(args.config)
        return

    config = load_config(args.config)
    if args.country:
        config["country"] = args.country

    scanner = VintedScanner(config)

    if args.once:
        deals = scanner.scan_all()
        sys.exit(0 if deals else 1)
    else:
        scanner.run()


if __name__ == "__main__":
    main()
