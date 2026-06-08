"""Client DVF Etalab — contexte de mutations (sans identification de propriétaire)."""
import requests

_BASE = "https://api.cquest.org/dvf"


def dvf_context(commune: str, section: str, numero: str) -> dict:
    """
    Retourne les mutations connues sur la parcelle (date, type, surface, valeur).
    Usage : contexte patrimonial uniquement — pas de ré-identification, pas d'indexation externe.
    """
    params = {"code_commune": commune, "section": section, "no_plan": numero}
    try:
        resp = requests.get(_BASE, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        mutations = data.get("resultats", [])
        return {
            "nb_mutations": len(mutations),
            "dernier_type": mutations[-1].get("type_local", "") if mutations else "",
            "derniere_valeur": mutations[-1].get("valeur_fonciere", 0) if mutations else 0,
            "derniere_date": mutations[-1].get("date_mutation", "") if mutations else "",
        }
    except Exception:
        return {"nb_mutations": 0, "dernier_type": "", "derniere_valeur": 0, "derniere_date": ""}
