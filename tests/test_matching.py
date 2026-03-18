"""Tests unitaires pour l'algorithme de matching."""

import unittest
from job_agent.api.base import JobOffer
from job_agent.matching import (
    normalize_text,
    skill_matches,
    compute_match,
    score_competences,
    score_localisation,
    score_experience,
    score_salaire,
    score_contrat,
    score_titre,
    parse_experience_years,
)


def make_offer(**kwargs) -> JobOffer:
    """Helper pour créer une offre de test."""
    defaults = {
        "id": "test-001",
        "titre": "Data Analyst",
        "entreprise": "TestCorp",
        "localisation": "Paris",
        "description": "Poste de data analyst",
        "competences_requises": ["python", "sql", "power bi"],
        "experience_requise": "2 ans",
        "formation_requise": "Bac+5",
        "salaire_min": 35000,
        "salaire_max": 45000,
        "type_contrat": "CDI",
        "url": "https://example.com",
        "teletravail": False,
        "raw": {},
    }
    defaults.update(kwargs)
    return JobOffer(**defaults)


SAMPLE_PROFILE = {
    "nom": "Adam GARANT",
    "competences": ["python", "sql", "power bi", "ga4", "contentsquare", "agile"],
    "experience_annees": 3,
    "formation": "master",
    "formation_niveau": 4,
    "langues": ["francais", "anglais"],
    "localisation": "Paris",
    "rayon_km": 30,
    "salaire_min": 35000,
    "salaire_max": 50000,
    "types_contrat": ["CDI", "CDD", "VIE"],
    "mots_cles": "digital analytics UX data analyst customer experience",
}


class TestNormalize(unittest.TestCase):
    def test_lowercase_and_accents(self):
        self.assertEqual(normalize_text("Développeur"), "developpeur")

    def test_extra_spaces(self):
        self.assertEqual(normalize_text("  power   bi  "), "power bi")


class TestSkillMatches(unittest.TestCase):
    def test_exact_match(self):
        self.assertTrue(skill_matches("python", "python"))

    def test_case_insensitive(self):
        self.assertTrue(skill_matches("Python", "python"))

    def test_substring(self):
        self.assertTrue(skill_matches("python", "développeur Python 3"))

    def test_synonym_ga4(self):
        self.assertTrue(skill_matches("ga4", "google analytics 4"))

    def test_no_match(self):
        self.assertFalse(skill_matches("java", "python"))


class TestScoreCompetences(unittest.TestCase):
    def test_full_match(self):
        offer = make_offer(competences_requises=["python", "sql"])
        score, matched, gaps = score_competences(SAMPLE_PROFILE, offer)
        self.assertEqual(score, 1.0)
        self.assertEqual(len(gaps), 0)

    def test_partial_match(self):
        offer = make_offer(competences_requises=["python", "sql", "kubernetes", "terraform"])
        score, matched, gaps = score_competences(SAMPLE_PROFILE, offer)
        self.assertEqual(score, 0.5)
        self.assertIn("kubernetes", gaps)

    def test_empty_requirements(self):
        offer = make_offer(competences_requises=[])
        score, _, _ = score_competences(SAMPLE_PROFILE, offer)
        self.assertEqual(score, 0.5)  # Neutre quand pas d'info


class TestScoreTitre(unittest.TestCase):
    def test_relevant_title(self):
        """Un titre 'Data Analyst' doit matcher le profil data analyst."""
        offer = make_offer(titre="Data Analyst")
        score = score_titre(SAMPLE_PROFILE, offer)
        self.assertGreaterEqual(score, 0.85)

    def test_irrelevant_title(self):
        """Un titre hors-sujet doit avoir un score très bas."""
        offer = make_offer(titre="Directeur Développement des ventes")
        score = score_titre(SAMPLE_PROFILE, offer)
        self.assertLessEqual(score, 0.2)

    def test_partially_relevant(self):
        """Un titre partiellement pertinent doit avoir un score moyen."""
        offer = make_offer(titre="Chef de projet digital")
        score = score_titre(SAMPLE_PROFILE, offer)
        self.assertGreaterEqual(score, 0.5)

    def test_poseur_signaletique(self):
        """POSEUR SIGNALÉTIQUE ne doit pas matcher un profil data analyst."""
        offer = make_offer(titre="POSEUR SIGNALÉTIQUE")
        score = score_titre(SAMPLE_PROFILE, offer)
        self.assertLessEqual(score, 0.2)

    def test_executive_assistant(self):
        """Executive Assistant ne doit pas matcher un profil data analyst."""
        offer = make_offer(titre="Executive Assistant bilingue")
        score = score_titre(SAMPLE_PROFILE, offer)
        self.assertLessEqual(score, 0.2)


class TestScoreLocalisation(unittest.TestCase):
    def test_same_city(self):
        offer = make_offer(localisation="Paris")
        score = score_localisation(SAMPLE_PROFILE, offer)
        self.assertEqual(score, 1.0)

    def test_remote(self):
        offer = make_offer(teletravail=True, localisation="Lyon")
        score = score_localisation(SAMPLE_PROFILE, offer)
        self.assertEqual(score, 1.0)


class TestScoreExperience(unittest.TestCase):
    def test_sufficient(self):
        offer = make_offer(experience_requise="2 ans")
        score, _ = score_experience(SAMPLE_PROFILE, offer)
        self.assertEqual(score, 1.0)

    def test_insufficient(self):
        offer = make_offer(experience_requise="5 ans")
        score, tip = score_experience(SAMPLE_PROFILE, offer)
        self.assertLess(score, 1.0)
        self.assertIn("5 ans", tip)


class TestParseExperience(unittest.TestCase):
    def test_parse_years(self):
        self.assertEqual(parse_experience_years("3 ans d'expérience"), 3)

    def test_debutant(self):
        self.assertEqual(parse_experience_years("Débutant accepté"), 0)

    def test_no_info(self):
        self.assertIsNone(parse_experience_years(""))


class TestScoreSalaire(unittest.TestCase):
    def test_overlap(self):
        offer = make_offer(salaire_min=38000, salaire_max=48000)
        score = score_salaire(SAMPLE_PROFILE, offer)
        self.assertEqual(score, 1.0)

    def test_below(self):
        offer = make_offer(salaire_min=20000, salaire_max=28000)
        score = score_salaire(SAMPLE_PROFILE, offer)
        self.assertLess(score, 1.0)


class TestScoreContrat(unittest.TestCase):
    def test_matching(self):
        offer = make_offer(type_contrat="CDI")
        score = score_contrat(SAMPLE_PROFILE, offer)
        self.assertEqual(score, 1.0)

    def test_not_matching(self):
        offer = make_offer(type_contrat="INTERIM")
        score = score_contrat(SAMPLE_PROFILE, offer)
        self.assertLess(score, 0.5)


class TestComputeMatch(unittest.TestCase):
    def test_perfect_match(self):
        offer = make_offer(
            competences_requises=["python", "sql", "power bi"],
            localisation="Paris",
            experience_requise="2 ans",
            formation_requise="Master",
            salaire_min=38000,
            salaire_max=45000,
            type_contrat="CDI",
        )
        result = compute_match(SAMPLE_PROFILE, offer)
        self.assertGreater(result["score"], 80)

    def test_low_match(self):
        offer = make_offer(
            competences_requises=["java", "spring", "kubernetes", "terraform"],
            localisation="Toulouse",
            experience_requise="10 ans",
            formation_requise="Doctorat",
            salaire_min=80000,
            salaire_max=100000,
            type_contrat="INTERIM",
        )
        result = compute_match(SAMPLE_PROFILE, offer)
        self.assertLess(result["score"], 40)


if __name__ == "__main__":
    unittest.main()
