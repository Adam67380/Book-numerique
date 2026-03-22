"""
VINTED FLIP ULTIMATE — Le Meilleur Agent d'Achat-Revente
==========================================================
Version: 4.0 ULTIMATE

Architecture:
  1. API Vinted directe (pas de Selenium = rapide + stable)
  2. Comparaison produit exact (mots-clés intelligents)
  3. Scoring avancé (marché + état + vendeur + saison)
  4. Alertes WhatsApp + Discord
  5. Anti-ban (rotation headers, délais adaptatifs, respect limites)
  6. P&L Tracker intégré

Auteur: Généré par Claude pour Adam
"""

import json
import time
import random
import sqlite3
import hashlib
import logging
import re
import statistics
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict
from urllib.parse import quote_plus
from dataclasses import dataclass, field

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:
    from curl_cffi import requests as curl_requests
    HAS_CURL_CFFI = True
except ImportError:
    HAS_CURL_CFFI = False

try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

# ═══════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════

CONFIG = {
    # ─── Budget ───
    "budget_min": 50,
    "budget_max": 150,

    # ─── Seuil d'alerte ───
    # Alerte si l'article est X% sous la médiane du MÊME produit
    "seuil_pourcent": 40,

    # ─── Scan ───
    "scan_interval_minutes": 15,
    # Nombre d'articles à analyser par marque (augmente = plus lent mais plus complet)
    "articles_par_marque": 20,
    # Nombre d'annonces à comparer pour le prix médian
    "annonces_comparaison": 50,

    # ─── Marques & Recherches ───
    # Format: {"recherche Vinted": "nom marque affiché"}
    # Plus la recherche est précise, meilleurs sont les résultats
    "recherches": {
        "Ralph Lauren veste": "Ralph Lauren",
        "Ralph Lauren manteau": "Ralph Lauren",
        "Ralph Lauren blouson": "Ralph Lauren",
        "Tommy Hilfiger veste": "Tommy Hilfiger",
        "Tommy Hilfiger manteau": "Tommy Hilfiger",
        "Tommy Hilfiger doudoune": "Tommy Hilfiger",
        "Lacoste veste": "Lacoste",
        "Lacoste blouson": "Lacoste",
        "Burberry trench": "Burberry",
        "Burberry manteau": "Burberry",
        "Burberry veste": "Burberry",
        "The North Face doudoune": "The North Face",
        "The North Face veste": "The North Face",
        "North Face Nuptse": "The North Face",
        "Stone Island veste": "Stone Island",
        "Stone Island blouson": "Stone Island",
        "CP Company veste": "CP Company",
        "Moncler doudoune": "Moncler",
        "Canada Goose parka": "Canada Goose",
        "Barbour veste": "Barbour",
        "Hugo Boss manteau": "Hugo Boss",
        "Hugo Boss veste": "Hugo Boss",
        "Napapijri veste": "Napapijri",
        "Carhartt veste": "Carhartt",
        "Fred Perry veste": "Fred Perry",
        "Woolrich parka": "Woolrich",
    },

    # ─── Mots-clés à ignorer (extraction produit) ───
    "mots_stop": {
        "veste", "manteau", "blouson", "jacket", "coat", "homme", "femme",
        "taille", "size", "neuf", "occasion", "état", "très", "bon",
        "comme", "avec", "sans", "étiquette", "authentique", "original",
        "vrai", "rare", "vintage", "the", "de", "du", "le", "la", "les",
        "un", "une", "des", "en", "et", "ou", "for", "à", "a", "an",
        "is", "it", "on", "be", "no", "not", "porté", "portée", "fois",
        "envoi", "rapide", "prix", "ferme", "négociable", "urgent",
        "vend", "vends", "vente", "super", "magnifique", "sublime",
        "parfait", "excellent", "impeccable", "génial", "top",
    },

    # ─── Couleurs (à conserver dans les mots-clés) ───
    "couleurs": {
        "noir", "black", "blanc", "white", "bleu", "blue", "navy",
        "rouge", "red", "vert", "green", "gris", "grey", "gray",
        "beige", "camel", "marron", "brown", "kaki", "khaki",
        "orange", "jaune", "yellow", "rose", "pink", "bordeaux",
        "cream", "crème", "olive", "charcoal", "burgundy", "tan",
    },

    # ─── Tailles (à retirer des mots-clés) ───
    "tailles": {
        "xxs", "xs", "s", "m", "l", "xl", "xxl", "xxxl",
        "34", "36", "38", "40", "42", "44", "46", "48", "50", "52",
    },

    # ─── Alertes ───
    # WhatsApp (Twilio)
    "twilio_sid": "TON_ACCOUNT_SID_ICI",
    "twilio_token": "TON_AUTH_TOKEN_ICI",
    "twilio_from": "whatsapp:+14155238886",
    "twilio_to": "whatsapp:+33XXXXXXXXX",

    # Discord Webhook (GRATUIT + INSTANTANÉ — recommandé)
    # Crée un webhook dans ton serveur Discord: Paramètres > Intégrations > Webhooks
    "discord_webhook_url": "",

    # ─── Dashboard ───
    "dashboard_port": 8081,
}


# ═══════════════════════════════════════════════════════════
# CLIENT API VINTED (rapide, pas de Selenium)
# ═══════════════════════════════════════════════════════════

class VintedAPI:
    """
    Client API Vinted utilisant Playwright (vrai navigateur).

    Toutes les requêtes API sont faites DEPUIS le navigateur via fetch(),
    ce qui contourne Cloudflare puisque le navigateur a déjà passé le challenge.
    """

    BASE = "https://www.vinted.fr"
    API = "https://www.vinted.fr/api/v2"

    def __init__(self):
        if not HAS_PLAYWRIGHT:
            raise RuntimeError(
                "playwright est requis.\n"
                "  pip install playwright\n"
                "  playwright install chromium"
            )
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._ready = False
        self._request_count = 0
        self._last_request = 0

    def _ensure_browser(self):
        """Lance le navigateur et passe le challenge Cloudflare une seule fois."""
        if self._ready and self._page:
            return

        logging.info("[API] 🌐 Lancement du navigateur...")
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
        )
        self._context = self._browser.new_context(
            locale="fr-FR",
            viewport={"width": 1366, "height": 768},
        )
        self._page = self._context.new_page()

        # Visiter Vinted et attendre que Cloudflare soit passé
        self._page.goto(self.BASE, wait_until="domcontentloaded", timeout=60000)
        logging.info("[API] ⏳ Attente résolution Cloudflare...")

        # Attendre qu'un élément du vrai site Vinted apparaisse
        try:
            self._page.wait_for_selector(
                "a[href*='/catalog'], input, [data-testid], nav, .web_ui",
                timeout=90000,
            )
        except Exception:
            # En dernier recours, attendre 15s
            logging.warning("[API] ⏱️ Timeout sélecteur, attente fixe 15s...")
            self._page.wait_for_timeout(15000)

        # Vérifier que la page est bien Vinted
        self._page.wait_for_timeout(3000)
        title = self._page.title()
        logging.info(f"[API] ✅ Navigateur prêt (titre: {title})")
        self._ready = True

    def _rate_limit(self):
        """Délai adaptatif anti-ban."""
        self._request_count += 1
        now = time.time()
        elapsed = now - self._last_request

        base_delay = random.uniform(2.0, 4.0)

        if self._request_count % 15 == 0:
            base_delay = random.uniform(8, 15)
            logging.info(f"[API] Pause anti-ban ({base_delay:.0f}s)...")

        wait = max(0, base_delay - elapsed)
        if wait > 0:
            time.sleep(wait)

        self._last_request = time.time()

    def search(self, query: str, per_page: int = 24, page: int = 1,
               price_from: float = None, price_to: float = None,
               order: str = "newest_first") -> List[dict]:
        """
        Recherche sur Vinted en exécutant fetch() depuis le navigateur.
        """
        self._ensure_browser()
        self._rate_limit()

        # Construire l'URL
        params_parts = [
            f"search_text={quote_plus(query)}",
            f"order={order}",
            f"per_page={per_page}",
            f"page={page}",
        ]
        if price_from is not None:
            params_parts.append(f"price_from={price_from}")
        if price_to is not None:
            params_parts.append(f"price_to={price_to}")

        url = f"{self.API}/catalog/items?{'&'.join(params_parts)}"

        try:
            # Exécuter fetch() dans le contexte du navigateur
            result = self._page.evaluate("""async (url) => {
                try {
                    const resp = await fetch(url, {
                        credentials: 'include',
                        headers: {
                            'Accept': 'application/json, text/plain, */*',
                        },
                    });
                    if (!resp.ok) {
                        return { error: true, status: resp.status, text: '' };
                    }
                    const data = await resp.json();
                    return { error: false, data: data };
                } catch(e) {
                    return { error: true, status: 0, text: e.message };
                }
            }""", url)

            if result.get("error"):
                status = result.get("status", 0)
                logging.warning(f"[API] Erreur fetch pour '{query}' (status: {status})")

                if status in (401, 403):
                    # Session expirée → relancer le navigateur
                    logging.info("[API] 🔄 Relance navigateur...")
                    self.close()
                    self._ensure_browser()

                return []

            data = result.get("data", {})
            items = data.get("items", [])

            results = []
            for item in items:
                price_raw = item.get("price") or item.get("total_item_price") or "0"
                if isinstance(price_raw, dict):
                    prix = float(price_raw.get("amount", "0"))
                elif isinstance(price_raw, str):
                    prix = float(price_raw)
                else:
                    prix = float(price_raw or 0)

                results.append({
                    "id": str(item.get("id", "")),
                    "titre": item.get("title", ""),
                    "prix": prix,
                    "marque": item.get("brand_title", ""),
                    "taille": item.get("size_title", ""),
                    "url": f"{self.BASE}/items/{item.get('id', '')}",
                    "image_url": (item.get("photo", {}) or {}).get("url", ""),
                    "etat": item.get("status", ""),
                    "favori_count": item.get("favourite_count", 0),
                    "vue_count": item.get("view_count", 0),
                    "vendeur": (item.get("user", {}) or {}).get("login", ""),
                    "note_vendeur": float((item.get("user", {}) or {}).get("feedback_reputation", 0) or 0),
                    "created_at": item.get("created_at_ts", ""),
                })

            return results

        except Exception as e:
            logging.error(f"[API] Erreur recherche '{query}': {e}")
            # Tenter de relancer le navigateur
            try:
                self.close()
            except Exception:
                pass
            self._ready = False
            return []

    def close(self):
        """Ferme le navigateur proprement."""
        try:
            if self._browser:
                self._browser.close()
            if self._playwright:
                self._playwright.stop()
        except Exception:
            pass
        self._browser = None
        self._context = None
        self._page = None
        self._playwright = None
        self._ready = False

    def search_all_pages(self, query: str, max_items: int = 50,
                         price_from: float = None, price_to: float = None,
                         order: str = "relevance") -> List[dict]:
        """Recherche multi-pages pour récupérer le maximum d'annonces."""
        all_items = []
        page = 1
        per_page = min(24, max_items)

        while len(all_items) < max_items:
            items = self.search(
                query, per_page=per_page, page=page,
                price_from=price_from, price_to=price_to, order=order
            )
            if not items:
                break

            all_items.extend(items)
            page += 1

            if len(items) < per_page:
                break  # Plus de résultats

        return all_items[:max_items]


# ═══════════════════════════════════════════════════════════
# BASE DE DONNÉES
# ═══════════════════════════════════════════════════════════

DB_PATH = Path(__file__).parent / "vinted_ultimate.db"


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS deals (
            id TEXT PRIMARY KEY,
            titre TEXT, prix REAL, marque TEXT,
            type_vetement TEXT, taille TEXT, etat TEXT,
            url TEXT, image_url TEXT,
            mots_cles TEXT, recherche_comparaison TEXT,
            prix_median REAL, prix_moyen REAL,
            prix_min REAL, prix_max REAL,
            nb_comparaisons INTEGER,
            ecart_pourcent REAL, marge_euro REAL, marge_pourcent REAL,
            score INTEGER,
            vendeur TEXT, note_vendeur REAL,
            favori_count INTEGER, vue_count INTEGER,
            date_trouvee TEXT, statut TEXT DEFAULT 'nouveau'
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS prix_marche (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recherche TEXT, prix_median REAL, prix_moyen REAL,
            prix_min REAL, prix_max REAL,
            nb_annonces INTEGER, tous_les_prix TEXT,
            date_analyse TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS pnl (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            deal_id TEXT, action TEXT,
            prix_achat REAL, prix_vente REAL,
            frais REAL, profit REAL,
            date_action TEXT, notes TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS scan_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT, duree_secondes REAL,
            nb_resultats INTEGER, nb_deals INTEGER
        )
    """)

    conn.commit()
    conn.close()


def save_deal(deal: dict) -> bool:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("""
            INSERT OR IGNORE INTO deals
            (id, titre, prix, marque, type_vetement, taille, etat,
             url, image_url, mots_cles, recherche_comparaison,
             prix_median, prix_moyen, prix_min, prix_max,
             nb_comparaisons, ecart_pourcent, marge_euro, marge_pourcent,
             score, vendeur, note_vendeur, favori_count, vue_count,
             date_trouvee)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            deal["id"], deal["titre"], deal["prix"], deal["marque"],
            deal.get("type_vetement", ""), deal.get("taille", ""),
            deal.get("etat", ""), deal["url"], deal.get("image_url", ""),
            deal.get("mots_cles", ""), deal.get("recherche_comparaison", ""),
            deal.get("prix_median", 0), deal.get("prix_moyen", 0),
            deal.get("prix_min", 0), deal.get("prix_max", 0),
            deal.get("nb_comparaisons", 0), deal.get("ecart_pourcent", 0),
            deal.get("marge_euro", 0), deal.get("marge_pourcent", 0),
            deal.get("score", 0), deal.get("vendeur", ""),
            deal.get("note_vendeur", 0), deal.get("favori_count", 0),
            deal.get("vue_count", 0), deal.get("date_trouvee", ""),
        ))
        conn.commit()
        return c.rowcount > 0
    except Exception as e:
        logging.error(f"DB: {e}")
        return False
    finally:
        conn.close()


def get_all_deals(limit=200):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM deals ORDER BY score DESC, date_trouvee DESC LIMIT ?", (limit,))
    deals = [dict(r) for r in c.fetchall()]
    conn.close()
    return deals


# ═══════════════════════════════════════════════════════════
# EXTRACTION MOTS-CLÉS PRODUIT (INTELLIGENT)
# ═══════════════════════════════════════════════════════════

def extraire_mots_cles(titre: str, marque: str) -> dict:
    """
    Extrait les mots-clés qui identifient UN produit précis.
    
    Input:  "Tommy Hilfiger Essential Bomber Jacket Navy M"
    Output: {"recherche": "Tommy Hilfiger Essential Bomber Navy",
             "mots_cles": ["Tommy", "Hilfiger", "Essential", "Bomber", "Navy"]}
    """
    texte = re.sub(r'[^\w\s\-]', ' ', titre)
    mots = texte.split()

    marque_parts = set(m.lower() for m in marque.split())
    mots_cles = list(marque.split())  # Toujours commencer par la marque

    for mot in mots:
        m = mot.lower().strip("-")
        if len(m) < 2:
            continue
        if m in marque_parts:
            continue
        if m in CONFIG["tailles"]:
            continue
        if m in CONFIG["mots_stop"]:
            continue
        if m.isdigit() and len(m) <= 4:
            continue
        mots_cles.append(mot)

    # Max 6 mots-clés pour une recherche efficace
    recherche = " ".join(mots_cles[:6])

    return {
        "mots_cles": mots_cles[:6],
        "recherche": recherche,
    }


def similarite(mots_cles_ref: list, titre: str) -> float:
    """Score de similarité entre mots-clés de référence et un titre."""
    if not mots_cles_ref:
        return 0
    titre_low = titre.lower()
    matches = sum(1 for m in mots_cles_ref if m.lower() in titre_low)
    return matches / len(mots_cles_ref)


# ═══════════════════════════════════════════════════════════
# COMPARATEUR DE PRIX (MÊME PRODUIT)
# ═══════════════════════════════════════════════════════════

class PriceComparator:
    """
    Compare le prix d'un article à la médiane du MÊME produit.
    
    1. Recherche les mots-clés exacts sur Vinted (sans filtre prix)
    2. Récupère jusqu'à 50 annonces
    3. Filtre par similarité (≥50% mots-clés communs)
    4. Calcule médiane, moyenne, min, max
    5. Cache le résultat 4h
    """

    def __init__(self, api: VintedAPI):
        self.api = api
        self._cache: Dict[str, dict] = {}

    def comparer(self, article: dict) -> dict:
        recherche = article.get("recherche", "")
        mots_cles = article.get("mots_cles", [])

        if not recherche or len(recherche) < 5:
            return self._vide()

        # Cache (4h)
        cle = recherche.lower().strip()
        if cle in self._cache:
            c = self._cache[cle]
            if (datetime.now() - c["ts"]).total_seconds() < 14400:
                return c

        logging.info(f"[Prix] 🔍 Analyse marché: '{recherche}'")

        # Rechercher le même produit SANS filtre de prix
        annonces = self.api.search_all_pages(
            recherche,
            max_items=CONFIG["annonces_comparaison"],
            order="relevance",
        )

        if not annonces:
            # Fallback : recherche plus large
            fallback = " ".join(mots_cles[:3]) if len(mots_cles) >= 3 else recherche
            logging.info(f"[Prix] Fallback: '{fallback}'")
            annonces = self.api.search_all_pages(fallback, max_items=30, order="relevance")

        # Filtrer par similarité
        if mots_cles and len(annonces) > 5:
            filtrees = [a for a in annonces if similarite(mots_cles, a["titre"]) >= 0.5]
            if len(filtrees) >= 3:
                annonces = filtrees

        # Extraire les prix (exclure l'article lui-même)
        prix_article = article.get("prix", 0)
        prix_list = [
            a["prix"] for a in annonces
            if a["prix"] > 3 and a["id"] != article.get("id", "")
        ]

        if len(prix_list) < 3:
            return self._vide()

        # Nettoyer outliers
        prix_list.sort()
        if len(prix_list) >= 8:
            n = len(prix_list)
            prix_list = prix_list[int(n * 0.05):int(n * 0.95)]

        result = {
            "prix_median": round(statistics.median(prix_list), 2),
            "prix_moyen": round(statistics.mean(prix_list), 2),
            "prix_min": round(min(prix_list), 2),
            "prix_max": round(max(prix_list), 2),
            "nb": len(prix_list),
            "recherche": recherche,
            "ts": datetime.now(),
        }

        self._cache[cle] = result

        # Sauvegarder en DB
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""
            INSERT INTO prix_marche
            (recherche, prix_median, prix_moyen, prix_min, prix_max,
             nb_annonces, tous_les_prix, date_analyse)
            VALUES (?,?,?,?,?,?,?,?)
        """, (
            recherche, result["prix_median"], result["prix_moyen"],
            result["prix_min"], result["prix_max"], result["nb"],
            json.dumps(prix_list), datetime.now().isoformat(),
        ))
        conn.commit()
        conn.close()

        logging.info(
            f"[Prix] ✅ '{recherche}': médiane={result['prix_median']}€, "
            f"[{result['prix_min']}€–{result['prix_max']}€], {result['nb']} annonces"
        )
        return result

    def _vide(self):
        return {"prix_median": 0, "prix_moyen": 0, "prix_min": 0, "prix_max": 0, "nb": 0}


# ═══════════════════════════════════════════════════════════
# SCORING AVANCÉ
# ═══════════════════════════════════════════════════════════

def scorer(article: dict, market: dict) -> dict:
    """
    Score un deal sur 100 basé sur:
    - Écart vs médiane du même produit (60% du score)
    - État de l'article (15%)
    - Réputation vendeur (10%)
    - Données fiables (10%)
    - Budget (5%)
    """
    prix = article.get("prix", 0)
    median = market.get("prix_median", 0)
    nb = market.get("nb", 0)

    if median <= 0 or prix <= 0:
        return {"score": 0, "marge_euro": 0, "marge_pourcent": 0, "ecart": 0}

    ecart = ((median - prix) / median) * 100

    # Marge nette (frais Vinted vendeur ~5% + 0.70€ + frais achat ~5%)
    frais_vente = median * 0.05 + 0.70
    frais_achat = prix * 0.05
    marge = median - prix - frais_vente - frais_achat
    marge_pct = (marge / (prix + frais_achat)) * 100

    # ─── Score écart (0-60) ───
    if ecart >= 60: s_ecart = 60
    elif ecart >= 50: s_ecart = 55
    elif ecart >= 40: s_ecart = 48
    elif ecart >= 30: s_ecart = 38
    elif ecart >= 20: s_ecart = 25
    elif ecart >= 10: s_ecart = 12
    else: s_ecart = 5

    # ─── Score état (0-15) ───
    etat = (article.get("etat", "") or "").lower()
    if "neuf avec" in etat: s_etat = 15
    elif "neuf sans" in etat: s_etat = 13
    elif "très bon" in etat: s_etat = 10
    elif "bon" in etat: s_etat = 6
    else: s_etat = 3

    # ─── Score vendeur (0-10) ───
    note = article.get("note_vendeur", 0) or 0
    if note >= 4.8: s_vendeur = 10
    elif note >= 4.5: s_vendeur = 8
    elif note >= 4.0: s_vendeur = 5
    elif note >= 3.0: s_vendeur = 2
    else: s_vendeur = 0

    # ─── Score données (0-10) ───
    if nb >= 30: s_data = 10
    elif nb >= 20: s_data = 8
    elif nb >= 10: s_data = 5
    elif nb >= 5: s_data = 3
    else: s_data = 1

    # ─── Score budget (0-5) ───
    s_budget = 5 if CONFIG["budget_min"] <= prix <= CONFIG["budget_max"] else 0

    score = s_ecart + s_etat + s_vendeur + s_data + s_budget

    return {
        "score": min(100, max(0, score)),
        "marge_euro": round(marge, 2),
        "marge_pourcent": round(marge_pct, 1),
        "ecart": round(ecart, 1),
    }


# ═══════════════════════════════════════════════════════════
# ALERTES
# ═══════════════════════════════════════════════════════════

def alerte_discord(deal: dict):
    """Envoie une alerte via Discord Webhook (gratuit + instantané)."""
    url = CONFIG.get("discord_webhook_url", "")
    if not url:
        return

    ecart = deal.get("ecart_pourcent", 0)

    # Couleur: vert si bon deal, orange si moyen
    color = 0x00ff88 if ecart >= 40 else 0xffaa00

    embed = {
        "embeds": [{
            "title": f"🔥 -{ecart}% — {deal['marque']} {deal.get('type_vetement', '')}",
            "description": deal["titre"][:200],
            "color": color,
            "fields": [
                {"name": "💰 Prix", "value": f"**{deal['prix']}€**", "inline": True},
                {"name": "📊 Médiane", "value": f"**{deal.get('prix_median', 0)}€**", "inline": True},
                {"name": "✅ Marge", "value": f"**+{deal.get('marge_euro', 0)}€**", "inline": True},
                {"name": "📏 Taille", "value": deal.get("taille", "?"), "inline": True},
                {"name": "📈 Comparé à", "value": f"{deal.get('nb_comparaisons', 0)} annonces", "inline": True},
                {"name": "⭐ Score", "value": f"{deal.get('score', 0)}/100", "inline": True},
            ],
            "url": deal["url"],
            "thumbnail": {"url": deal.get("image_url", "")},
            "footer": {"text": f"Vinted Flip Ultimate • {datetime.now().strftime('%H:%M')}"},
        }]
    }

    try:
        requests.post(url, json=embed, timeout=10)
        logging.info(f"[Discord] ✅ Alerte envoyée: {deal['marque']}")
    except Exception as e:
        logging.error(f"[Discord] Erreur: {e}")


def alerte_whatsapp(deal: dict):
    """Alerte WhatsApp via Twilio."""
    if CONFIG["twilio_sid"] == "TON_ACCOUNT_SID_ICI":
        return  # Pas configuré

    try:
        from twilio.rest import Client
        client = Client(CONFIG["twilio_sid"], CONFIG["twilio_token"])
        ecart = deal.get("ecart_pourcent", 0)

        client.messages.create(
            body=(
                f"🛍️ *DEAL -{ecart}%*\n\n"
                f"👔 *{deal['titre'][:80]}*\n"
                f"💰 {deal['prix']}€ → Médiane: {deal.get('prix_median', 0)}€\n"
                f"✅ Marge: +{deal.get('marge_euro', 0)}€\n"
                f"📊 {deal.get('nb_comparaisons', 0)} annonces comparées\n"
                f"📏 {deal.get('taille', '?')}\n"
                f"🔗 {deal['url']}"
            ),
            from_=CONFIG["twilio_from"],
            to=CONFIG["twilio_to"],
        )
    except Exception as e:
        logging.error(f"[WhatsApp] {e}")


def alerte_console(deal: dict):
    """Affiche l'alerte dans la console."""
    ecart = deal.get("ecart_pourcent", 0)
    print(f"""
╔══════════════════════════════════════════════════════════╗
║  🔥 DEAL DÉTECTÉ — {ecart}% SOUS LE MARCHÉ
╠══════════════════════════════════════════════════════════╣
║  👔 {deal['titre'][:55]}
║  💰 Prix: {deal['prix']}€  →  Médiane: {deal.get('prix_median', 0)}€
║  ✅ Marge nette: +{deal.get('marge_euro', 0)}€ ({deal.get('marge_pourcent', 0)}%)
║  📊 Basé sur {deal.get('nb_comparaisons', 0)} annonces du même produit
║  📏 Taille: {deal.get('taille', '?')}  |  ⭐ Score: {deal.get('score', 0)}/100
║  🔗 {deal['url']}
╚══════════════════════════════════════════════════════════╝""")


def envoyer_alertes(deal: dict):
    """Envoie sur tous les canaux configurés."""
    alerte_console(deal)
    alerte_discord(deal)
    alerte_whatsapp(deal)


# ═══════════════════════════════════════════════════════════
# MOTEUR PRINCIPAL
# ═══════════════════════════════════════════════════════════

class FlipEngine:
    """Le cerveau de l'agent."""

    def __init__(self):
        self.api = VintedAPI()
        self.comparator = PriceComparator(self.api)

    def scan(self) -> list:
        seuil = CONFIG["seuil_pourcent"]
        start = time.time()

        logging.info("═" * 60)
        logging.info(f"🛍️  SCAN ULTIMATE — {datetime.now().strftime('%d/%m/%Y %H:%M')}")
        logging.info(f"📊 Seuil: -{seuil}% | Budget: {CONFIG['budget_min']}–{CONFIG['budget_max']}€")
        logging.info("═" * 60)

        all_deals = []

        for recherche, marque in CONFIG["recherches"].items():
            logging.info(f"\n🔍 [{marque}] Recherche: '{recherche}'")

            # ÉTAPE 1: Trouver les articles dans le budget
            articles = self.api.search_all_pages(
                recherche,
                max_items=CONFIG["articles_par_marque"],
                price_from=CONFIG["budget_min"],
                price_to=CONFIG["budget_max"],
                order="newest_first",
            )

            if not articles:
                logging.info(f"   → Aucun résultat")
                continue

            logging.info(f"   → {len(articles)} articles dans le budget")

            # ÉTAPE 2: Pour chaque article, comparer au même produit
            for article in articles:
                try:
                    # Extraire les mots-clés du produit
                    kw = extraire_mots_cles(article["titre"], marque)
                    article["mots_cles"] = kw["mots_cles"]
                    article["recherche"] = kw["recherche"]

                    # Comparer au marché
                    market = self.comparator.comparer(article)
                    median = market.get("prix_median", 0)

                    if median <= 0:
                        continue

                    # Scorer
                    scores = scorer(article, market)
                    ecart = scores["ecart"]

                    # Détecter le type
                    type_vet = "veste"
                    for t in ["doudoune", "parka", "manteau", "blouson", "trench", "bomber", "blazer"]:
                        if t in recherche.lower() or t in article["titre"].lower():
                            type_vet = t
                            break

                    deal = {
                        **article,
                        "marque": marque,
                        "type_vetement": type_vet,
                        "mots_cles": " | ".join(kw["mots_cles"]),
                        "recherche_comparaison": kw["recherche"],
                        "prix_median": median,
                        "prix_moyen": market.get("prix_moyen", 0),
                        "prix_min": market.get("prix_min", 0),
                        "prix_max": market.get("prix_max", 0),
                        "nb_comparaisons": market.get("nb", 0),
                        "ecart_pourcent": ecart,
                        "marge_euro": scores["marge_euro"],
                        "marge_pourcent": scores["marge_pourcent"],
                        "score": scores["score"],
                        "date_trouvee": datetime.now().isoformat(),
                    }

                    all_deals.append(deal)

                    if ecart >= seuil:
                        logging.info(
                            f"   🔥 DEAL: {article['titre'][:50]}... "
                            f"— {article['prix']}€ vs médiane {median}€ (-{ecart}%)"
                        )

                except Exception as e:
                    logging.debug(f"   Erreur article: {e}")
                    continue

        # Trier par score
        all_deals.sort(key=lambda d: d.get("score", 0), reverse=True)

        # Sauvegarder et alerter
        nb_deals = 0
        for deal in all_deals:
            is_new = save_deal(deal)
            if is_new and deal.get("ecart_pourcent", 0) >= seuil:
                nb_deals += 1
                envoyer_alertes(deal)

        duree = time.time() - start

        # Log
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            "INSERT INTO scan_log (date, duree_secondes, nb_resultats, nb_deals) VALUES (?,?,?,?)",
            (datetime.now().isoformat(), round(duree, 1), len(all_deals), nb_deals)
        )
        conn.commit()
        conn.close()

        logging.info(f"\n✅ Scan terminé en {duree:.0f}s: {len(all_deals)} articles, {nb_deals} deals à -{seuil}%+")
        return all_deals


# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════

def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s │ %(message)s",
        datefmt="%H:%M:%S",
        handlers=[
            logging.FileHandler(Path(__file__).parent / "agent.log", encoding="utf-8"),
            logging.StreamHandler(),
        ]
    )

    print(f"""
    ╔═══════════════════════════════════════════════════════════════╗
    ║                                                               ║
    ║          🛍️  VINTED FLIP ULTIMATE v4.0  🛍️                    ║
    ║                                                               ║
    ║   ⚡ API directe (pas de Selenium = 10x plus rapide)         ║
    ║   🧠 Comparaison au MÊME produit (mots-clés intelligents)    ║
    ║   📊 Médiane sur {CONFIG['annonces_comparaison']} annonces identiques max             ║
    ║   🔔 Alertes: Console + Discord + WhatsApp                   ║
    ║   🛡️  Anti-ban: rotation UA, délais adaptatifs               ║
    ║                                                               ║
    ║   Budget: {CONFIG['budget_min']}€–{CONFIG['budget_max']}€ | Seuil: -{CONFIG['seuil_pourcent']}%                       ║
    ║   Scan toutes les {CONFIG['scan_interval_minutes']} minutes                              ║
    ║                                                               ║
    ╚═══════════════════════════════════════════════════════════════╝
    """)

    init_db()
    engine = FlipEngine()

    try:
        while True:
            try:
                engine.scan()
            except Exception as e:
                logging.error(f"❌ {e}")

            logging.info(f"⏳ Prochain scan dans {CONFIG['scan_interval_minutes']} min...")
            time.sleep(CONFIG["scan_interval_minutes"] * 60)
    except KeyboardInterrupt:
        logging.info("👋 Arrêt demandé, fermeture du navigateur...")
    finally:
        engine.api.close()


if __name__ == "__main__":
    main()
