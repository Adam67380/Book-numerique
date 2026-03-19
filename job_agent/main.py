"""CLI principal de l'agent de matching d'offres d'emploi."""

import argparse
import os
import sys

from job_agent.profile import load_profile, create_profile_interactive, PROFILE_PATH
from job_agent.api.france_travail import FranceTravailClient
from job_agent.api.base import JobOffer
from job_agent.matching import compute_match
from job_agent.interview import generate_tips
from job_agent.web_search import web_search_jobs, offers_to_job_offers


def display_results(results: list[dict]):
    """Affiche les résultats de matching sous forme de tableau."""
    if not results:
        print("\n  Aucune offre trouvée. Essayez d'élargir vos critères.\n")
        return

    has_ia = any(r["match"].get("raison_ia") for r in results)

    print(f"\n{'=' * 100}")
    print(f"  {'#':<4} {'SCORE':<8} {'POSTE':<30} {'ENTREPRISE':<20} {'CONTRAT':<8} {'LIEU'}")
    print(f"{'─' * 100}")

    for i, r in enumerate(results, 1):
        offer = r["offer"]
        match = r["match"]
        score = match["score"]

        # Indicateur visuel du score
        if score >= 75:
            indicator = "★★★"
        elif score >= 50:
            indicator = "★★ "
        else:
            indicator = "★  "

        titre = offer.titre[:28] if len(offer.titre) > 28 else offer.titre
        entreprise = offer.entreprise[:18] if len(offer.entreprise) > 18 else offer.entreprise
        lieu = offer.localisation[:20] if len(offer.localisation) > 20 else offer.localisation

        print(
            f"  {i:<4} {score:>5.1f}% {indicator} {titre:<30} {entreprise:<20} "
            f"{offer.type_contrat:<8} {lieu}"
        )
        # Afficher la raison IA sur la ligne suivante
        raison = match.get("raison_ia", "")
        if raison:
            print(f"       {'':>8} -> {raison}")

    print(f"{'=' * 100}")
    mode = "IA (Claude)" if has_ia else "algorithmique"
    print(f"  {len(results)} offre(s) trouvée(s) — scoring {mode}\n")


def display_offer_detail(offer: JobOffer, match: dict):
    """Affiche le détail d'une offre avec son analyse de matching."""
    print(f"\n{'=' * 60}")
    print(f"  {offer.titre}")
    print(f"  {offer.entreprise} - {offer.localisation}")
    print(f"{'─' * 60}")
    print(f"  Contrat : {offer.type_contrat}")
    if offer.salaire_min or offer.salaire_max:
        sal = ""
        if offer.salaire_min:
            sal += f"{offer.salaire_min:,.0f}"
        if offer.salaire_max and offer.salaire_max != offer.salaire_min:
            sal += f" - {offer.salaire_max:,.0f}"
        print(f"  Salaire : {sal} EUR/an")
    if offer.experience_requise:
        print(f"  Expérience : {offer.experience_requise}")
    if offer.formation_requise:
        print(f"  Formation : {offer.formation_requise}")
    if offer.teletravail:
        print(f"  Télétravail : Oui")
    print(f"\n  Lien : {offer.url}")

    # Score détaillé
    print(f"\n{'─' * 60}")
    print(f"  SCORE GLOBAL : {match['score']}%")
    print(f"{'─' * 60}")
    for comp, score in match["details"].items():
        bar = "█" * int(score / 5) + "░" * (20 - int(score / 5))
        print(f"  {comp:<15} {bar} {score}%")

    if match.get("raison_ia"):
        print(f"\n  Avis IA : {match['raison_ia']}")

    if match["matched_skills"]:
        print(f"\n  ✓ Compétences matchées : {', '.join(match['matched_skills'])}")
    if match["skill_gaps"]:
        print(f"  ✗ Compétences manquantes : {', '.join(match['skill_gaps'])}")
    print(f"{'=' * 60}")


def _try_llm_scoring(profile: dict, offers: list) -> dict | None:
    """Tente le scoring IA. Retourne None si indisponible."""
    import os
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    try:
        from job_agent.llm_scoring import score_offers_with_llm
        print("\n  Analyse IA des offres en cours (Claude lit chaque offre)...")
        return score_offers_with_llm(profile, offers)
    except ImportError:
        print("  pip install anthropic pour activer le scoring IA")
        return None
    except Exception as e:
        print(f"  Erreur scoring IA : {e}")
        return None


def cmd_search(args):
    """Commande de recherche d'offres."""
    profile = load_profile(args.profile)
    keywords = args.keywords or profile.get("mots_cles", "")
    location = args.location or profile.get("localisation", "")
    limit = args.limit

    if not keywords:
        print("Erreur : spécifiez des mots-clés avec --keywords ou dans votre profil.")
        sys.exit(1)

    # Initialiser le client API (profil YAML prioritaire, .env en fallback)
    api_config = profile.get("api", {}).get("france_travail", {})
    client_id = api_config.get("client_id", "") or os.environ.get("FRANCE_TRAVAIL_CLIENT_ID", "")
    client_secret = api_config.get("client_secret", "") or os.environ.get("FRANCE_TRAVAIL_CLIENT_SECRET", "")

    if not client_id or not client_secret:
        print("Erreur : clés API France Travail manquantes.")
        print("Renseignez-les dans config/profile.yaml ou dans un fichier .env")
        print("Inscription gratuite : https://francetravail.io/data/api/offres-emploi")
        sys.exit(1)

    client = FranceTravailClient(client_id, client_secret)

    # Découper les mots-clés en sous-recherches pour maximiser les résultats
    search_terms = [kw.strip() for kw in keywords.split() if len(kw.strip()) > 2]
    # Grouper par 2-3 mots et aussi chercher des termes individuels importants
    search_queries = []
    # Recherche complète d'abord
    search_queries.append(keywords)
    # Puis des sous-groupes de 2 mots
    for i in range(0, len(search_terms), 2):
        group = " ".join(search_terms[i:i+2])
        if group != keywords:
            search_queries.append(group)
    # Termes individuels importants
    for term in search_terms:
        if len(term) >= 4 and term not in search_queries:
            search_queries.append(term)

    # Dédupliquer
    seen_queries = []
    for q in search_queries:
        if q not in seen_queries:
            seen_queries.append(q)
    search_queries = seen_queries[:8]  # Max 8 requêtes

    print(f"\n  Recherche d'offres à {location or 'toute la France'}...")
    print(f"  Termes de recherche : {', '.join(search_queries)}")

    offers = []
    seen_ids = set()
    for query in search_queries:
        try:
            batch = client.search(
                keywords=query,
                location=location,
                radius_km=profile.get("rayon_km", 30),
                limit=limit,
            )
            for offer in batch:
                if offer.id not in seen_ids:
                    seen_ids.add(offer.id)
                    offers.append(offer)
            if batch:
                print(f"    '{query}' → {len(batch)} offre(s)")
        except Exception as e:
            print(f"    '{query}' → Erreur : {e}")

    print(f"\n  Total : {len(offers)} offre(s) unique(s) trouvée(s)")

    # Calculer le matching algorithmique
    results = []
    for offer in offers:
        match = compute_match(profile, offer)
        results.append({"offer": offer, "match": match})

    # Scoring IA : Claude lit chaque offre et évalue la pertinence réelle
    llm_scores = _try_llm_scoring(profile, offers)
    if llm_scores:
        for r in results:
            offer_id = r["offer"].id
            if offer_id in llm_scores:
                llm = llm_scores[offer_id]
                r["match"]["score"] = float(llm["score"])
                r["match"]["raison_ia"] = llm["raison"]
    else:
        print("  (Scoring algorithmique uniquement — ajoutez ANTHROPIC_API_KEY pour le scoring IA)")

    # Trier par score décroissant
    results.sort(key=lambda r: r["match"]["score"], reverse=True)
    display_results(results)

    # Mode interactif : détail d'une offre
    if results and not args.no_interactive:
        while True:
            choice = input(
                "  Entrez le n° d'une offre pour voir le détail (ou 'q' pour quitter) : "
            ).strip()
            if choice.lower() in ("q", "quit", "exit", ""):
                break
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(results):
                    r = results[idx]
                    display_offer_detail(r["offer"], r["match"])

                    see_tips = input(
                        "\n  Voir les conseils d'entretien ? (o/n) : "
                    ).strip().lower()
                    if see_tips in ("o", "oui", "y", "yes"):
                        tips = generate_tips(profile, r["offer"], r["match"])
                        print(tips)
                else:
                    print(f"  Numéro invalide (1-{len(results)})")
            except ValueError:
                print("  Entrez un numéro valide.")


def cmd_tips(args):
    """Commande de conseils d'entretien pour une offre spécifique."""
    profile = load_profile(args.profile)

    api_config = profile.get("api", {}).get("france_travail", {})
    client_id = api_config.get("client_id", "") or os.environ.get("FRANCE_TRAVAIL_CLIENT_ID", "")
    client_secret = api_config.get("client_secret", "") or os.environ.get("FRANCE_TRAVAIL_CLIENT_SECRET", "")

    if not client_id or not client_secret:
        print("Erreur : clés API France Travail manquantes.")
        sys.exit(1)

    client = FranceTravailClient(client_id, client_secret)

    print(f"\n  Récupération de l'offre {args.job_id}...")
    try:
        offer = client.get_offer(args.job_id)
    except Exception as e:
        print(f"\nErreur : {e}")
        sys.exit(1)

    match = compute_match(profile, offer)
    display_offer_detail(offer, match)
    tips = generate_tips(profile, offer, match)
    print(tips)


def cmd_web_search(args):
    """Commande de recherche web multi-plateformes avec filtrage IA."""
    profile = load_profile(args.profile)
    keywords = args.keywords or profile.get("mots_cles", "")
    location = args.location or profile.get("localisation", "")

    if not keywords:
        print("Erreur : spécifiez des mots-clés avec --keywords ou dans votre profil.")
        sys.exit(1)

    print(f"\n  Recherche web : \"{keywords}\" à {location or 'toute la France'}")
    print()

    web_offers = web_search_jobs(
        profile=profile,
        keywords=keywords,
        location=location,
    )

    if not web_offers:
        print("\n  Aucune offre pertinente trouvée. Essayez d'autres mots-clés.")
        return

    # Convertir en JobOffer pour réutiliser l'affichage
    job_offers = offers_to_job_offers(web_offers)

    # Construire les résultats avec les scores IA
    results = []
    for offer, web_data in zip(job_offers, web_offers):
        match_data = compute_match(profile, offer)
        # Remplacer le score algo par le score IA de Haiku
        match_data["score"] = float(web_data.get("score", match_data["score"]))
        match_data["raison_ia"] = web_data.get("raison", "")
        if web_data.get("date_estimee"):
            match_data["raison_ia"] += f" [Date: {web_data['date_estimee']}]"
        results.append({"offer": offer, "match": match_data})

    # Trier par score
    results.sort(key=lambda r: r["match"]["score"], reverse=True)
    display_results(results)

    # Mode interactif
    if results and not args.no_interactive:
        while True:
            choice = input(
                "  Entrez le n° d'une offre pour voir le détail (ou 'q' pour quitter) : "
            ).strip()
            if choice.lower() in ("q", "quit", "exit", ""):
                break
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(results):
                    r = results[idx]
                    display_offer_detail(r["offer"], r["match"])

                    see_tips = input(
                        "\n  Voir les conseils d'entretien ? (o/n) : "
                    ).strip().lower()
                    if see_tips in ("o", "oui", "y", "yes"):
                        tips = generate_tips(profile, r["offer"], r["match"])
                        print(tips)
                else:
                    print(f"  Numéro invalide (1-{len(results)})")
            except ValueError:
                print("  Entrez un numéro valide.")


def cmd_init_profile(args):
    """Commande de création interactive du profil."""
    create_profile_interactive(args.output)


def cmd_profile(args):
    """Affiche le profil actuel."""
    try:
        profile = load_profile(args.profile)
    except (FileNotFoundError, ValueError) as e:
        print(f"\n  {e}")
        sys.exit(1)

    print(f"\n{'=' * 50}")
    print(f"  PROFIL : {profile.get('nom', 'Non renseigné')}")
    print(f"{'─' * 50}")
    print(f"  Formation    : {profile.get('formation', '')} (niveau {profile.get('formation_niveau', '')})")
    print(f"  Expérience   : {profile.get('experience_annees', 0)} ans")
    print(f"  Localisation : {profile.get('localisation', '')} ({profile.get('rayon_km', 30)} km)")
    print(f"  Contrats     : {', '.join(profile.get('types_contrat', []))}")
    if profile.get("salaire_min") or profile.get("salaire_max"):
        print(f"  Salaire      : {profile.get('salaire_min', '?')} - {profile.get('salaire_max', '?')} EUR/an")
    print(f"  Langues      : {', '.join(profile.get('langues', []))}")
    print(f"\n  Compétences ({len(profile.get('competences', []))}) :")
    for s in profile.get("competences", []):
        print(f"    • {s}")
    print(f"{'=' * 50}\n")


def main():
    parser = argparse.ArgumentParser(
        prog="job_agent",
        description="Agent IA de matching d'offres d'emploi",
    )
    subparsers = parser.add_subparsers(dest="command", help="Commandes disponibles")

    # init-profile
    p_init = subparsers.add_parser("init-profile", help="Créer un profil interactif")
    p_init.add_argument("-o", "--output", default=PROFILE_PATH, help="Chemin du fichier de sortie")

    # profile
    p_show = subparsers.add_parser("profile", help="Afficher le profil actuel")
    p_show.add_argument("-p", "--profile", default=PROFILE_PATH, help="Chemin du profil")

    # search
    p_search = subparsers.add_parser("search", help="Rechercher des offres")
    p_search.add_argument("-k", "--keywords", help="Mots-clés de recherche")
    p_search.add_argument("-l", "--location", help="Ville ou département")
    p_search.add_argument("-n", "--limit", type=int, default=20, help="Nombre max de résultats")
    p_search.add_argument("-p", "--profile", default=PROFILE_PATH, help="Chemin du profil")
    p_search.add_argument("--no-interactive", action="store_true", help="Désactiver le mode interactif")

    # tips
    p_tips = subparsers.add_parser("tips", help="Conseils d'entretien pour une offre")
    p_tips.add_argument("job_id", help="ID de l'offre France Travail")
    p_tips.add_argument("-p", "--profile", default=PROFILE_PATH, help="Chemin du profil")

    # web-search
    p_web = subparsers.add_parser(
        "web-search",
        help="Rechercher sur le web (Indeed, WTTJ, APEC, LinkedIn) via Claude IA",
    )
    p_web.add_argument("-k", "--keywords", help="Mots-clés de recherche")
    p_web.add_argument("-l", "--location", help="Ville ou département")
    p_web.add_argument("-p", "--profile", default=PROFILE_PATH, help="Chemin du profil")
    p_web.add_argument("--no-interactive", action="store_true",
                       help="Désactiver le mode interactif")

    args = parser.parse_args()

    if args.command == "init-profile":
        cmd_init_profile(args)
    elif args.command == "profile":
        cmd_profile(args)
    elif args.command == "search":
        cmd_search(args)
    elif args.command == "web-search":
        cmd_web_search(args)
    elif args.command == "tips":
        cmd_tips(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
