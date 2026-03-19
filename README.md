# Job Matching Agent

Agent IA de matching d'offres d'emploi qui analyse votre profil, recherche les offres les plus pertinentes via l'API France Travail, calcule un pourcentage de compatibilité et vous prépare pour l'entretien.

## Fonctionnalités

- **Matching intelligent** : score pondéré basé sur compétences, localisation, expérience, formation, salaire et type de contrat
- **Détection de synonymes** : reconnaît que "GA4" = "Google Analytics 4", "IA" = "Intelligence Artificielle", etc.
- **Conseils d'entretien** : analyse les écarts entre votre profil et l'offre, propose des axes de préparation
- **Questions probables** : génère des questions d'entretien adaptées au type de poste
- **Recherche web multi-plateformes** : cherche sur Indeed, Welcome to the Jungle, APEC, LinkedIn et Hellowork avec filtrage IA par Claude Haiku (vérification des dates, pertinence)

## Installation

```bash
pip install -r requirements.txt
```

## Configuration

### 1. Clés API France Travail (gratuit)

1. Créez un compte sur [francetravail.io](https://francetravail.io/data/api/offres-emploi)
2. Créez une application pour obtenir `client_id` et `client_secret`
3. Renseignez-les dans `config/profile.yaml`

### 2. Profil candidat

Créez votre profil de deux façons :

**Mode interactif :**
```bash
python -m job_agent init-profile
```

**Mode manuel :** copiez et éditez le fichier d'exemple :
```bash
cp config/profile_example.yaml config/profile.yaml
```

## Utilisation

```bash
# Afficher votre profil
python -m job_agent profile

# Rechercher des offres (utilise les mots-clés du profil)
python -m job_agent search

# Rechercher avec des mots-clés spécifiques
python -m job_agent search --keywords "data analyst" --location "Paris"

# Limiter le nombre de résultats
python -m job_agent search -k "UX analyst" -n 10

# Conseils d'entretien pour une offre spécifique
python -m job_agent tips <ID_OFFRE>

# Recherche web (Indeed, WTTJ, APEC, LinkedIn, Hellowork)
python -m job_agent web-search

# Recherche web avec mots-clés spécifiques
python -m job_agent web-search -k "data analyst" -l "Paris"

# Chercher uniquement sur certaines plateformes
python -m job_agent web-search --platforms "indeed,wttj,apec"

# Mode rapide (sans récupération du contenu des pages)
python -m job_agent web-search --fast
```

## Algorithme de scoring

| Composante     | Poids | Description |
|---------------|-------|-------------|
| Compétences   | 40%   | Matching des skills avec synonymes et fuzzy matching |
| Localisation  | 15%   | Correspondance géographique + détection télétravail |
| Expérience    | 15%   | Adéquation années d'expérience |
| Formation     | 10%   | Niveau d'études requis vs obtenu |
| Salaire       | 10%   | Chevauchement des fourchettes salariales |
| Contrat       | 10%   | CDI/CDD/VIE/Freelance |

## Structure du projet

```
├── config/
│   ├── profile.yaml           # Votre profil (à créer)
│   └── profile_example.yaml   # Exemple de profil
├── job_agent/
│   ├── main.py                # CLI principal
│   ├── profile.py             # Gestion du profil
│   ├── matching.py            # Algorithme de matching
│   ├── interview.py           # Générateur de conseils
│   ├── web_search.py          # Recherche web + filtrage IA
│   └── api/
│       ├── base.py            # Modèle JobOffer
│       └── france_travail.py  # Client API France Travail
└── tests/
    └── test_matching.py       # Tests unitaires
```
