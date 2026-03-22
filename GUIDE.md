# 🛍️ VINTED FLIP ULTIMATE v4.0 — Guide d'Installation

## Quoi de neuf vs les versions précédentes ?

| Feature | v3 (ancien) | v4 ULTIMATE |
|---------|------------|-------------|
| Méthode | Selenium (Chrome) | API directe (pas besoin de Chrome !) |
| Vitesse | ~2 min/marque | ~15 sec/marque |
| Comparaison | Même produit via mots-clés | Même produit via mots-clés (amélioré) |
| Annonces comparées | 20 max | 50 max |
| Anti-ban | Basique | Rotation UA + délais adaptatifs |
| Alertes | WhatsApp seul | WhatsApp + Discord (gratuit !) |
| Dépendances | 6 packages + Chrome | 3 packages seulement |
| Dashboard | Basique | Pro avec historique marché |

---

## Installation (3 minutes)

### 1. Python (si pas déjà installé)
- https://www.python.org/downloads/
- ⚠️ Cocher "Add Python to PATH"
- Vérifier: `python --version` dans cmd

### 2. Les fichiers
- Crée un dossier **vinted-ultimate** sur ton Bureau
- Copie tous les fichiers dedans

### 3. Lancer
- Double-clic sur **LANCER.bat**
- Dashboard: **http://localhost:8081**

C'est tout ! Plus besoin de Chrome.

---

## Configuration Discord (RECOMMANDÉ — gratuit + instantané)

Discord est le meilleur canal d'alerte: gratuit, instantané, et tu peux le recevoir sur ton téléphone.

### Créer un webhook Discord:
1. Crée un serveur Discord (ou utilise un existant)
2. Va dans **Paramètres du canal** > **Intégrations** > **Webhooks**
3. Clique **Nouveau Webhook**
4. Copie l'**URL du webhook**
5. Dans `scraper.py`, colle l'URL ici:
```python
"discord_webhook_url": "https://discord.com/api/webhooks/TON_WEBHOOK_ICI",
```

Tu recevras des alertes comme ça dans ton canal Discord:
- Titre du deal avec le % sous le marché
- Prix actuel vs médiane
- Marge nette estimée
- Lien direct vers l'article
- Photo de l'article

---

## Configuration WhatsApp (optionnel)

Même procédure que les versions précédentes via Twilio.
Voir le guide de la v1 si besoin.

---

## Personnalisation

### Changer le seuil d'alerte
```python
"seuil_pourcent": 40,  # Change à 30, 50, etc.
```

### Changer le budget
```python
"budget_min": 50,
"budget_max": 150,
```

### Ajouter une marque/recherche
```python
"recherches": {
    ...
    "Nike Tech Fleece": "Nike",
    "Adidas veste": "Adidas",
}
```

### Augmenter la précision (plus lent)
```python
"annonces_comparaison": 80,  # Défaut: 50
```

---

## Comment ça marche

```
1. RECHERCHE    L'agent cherche "Tommy Hilfiger veste" dans ton budget
                → Trouve: "Tommy Essential Bomber Navy" à 45€

2. EXTRACTION   Extrait les mots-clés: Tommy Hilfiger Essential Bomber Navy
                (retire: taille, état, mots génériques)

3. COMPARAISON  Recherche "Tommy Hilfiger Essential Bomber Navy" SANS filtre prix
                → Récupère jusqu'à 50 annonces du MÊME produit
                → Filtre par similarité (≥50% mots en commun)
                → Médiane = 78€

4. SCORING      45€ vs 78€ = -42% sous le marché
                Score = écart (48) + état (10) + vendeur (8) + données (8) + budget (5) = 79/100

5. ALERTE       -42% > seuil -40% → ALERTE Discord + WhatsApp !
```

---

## Architecture

```
vinted-ultimate/
├── scraper.py        ← Le cerveau (API Vinted + comparaison + alertes)
├── dashboard.py      ← Interface web http://localhost:8081
├── requirements.txt  ← 3 dépendances seulement
├── LANCER.bat        ← Double-clic pour tout démarrer
├── vinted_ultimate.db ← Base de données (auto)
└── agent.log         ← Logs (auto)
```

---

## FAQ

**Pourquoi l'API au lieu de Selenium ?**
L'API de Vinted est celle que leur propre site utilise. On fait les mêmes requêtes qu'un navigateur mais sans charger toute la page. Résultat: 10x plus rapide, plus stable, et pas besoin de Chrome.

**L'API peut changer ?**
Oui, Vinted peut modifier son API. Si ça arrive, l'agent affichera des erreurs dans les logs. Contacte-moi et je mettrai à jour.

**Risque de ban ?**
L'agent a des protections anti-ban (rotation de User-Agents, délais aléatoires, pauses longues). Mais le risque zéro n'existe pas. L'agent ne se connecte PAS à ton compte Vinted.

**C'est quoi le P&L tracker ?**
Une table dans la base de données où tu peux suivre tes achats et reventes. Pour l'instant c'est via l'API du dashboard (`/api/stats`). Dans une future version on pourra ajouter une interface graphique.

---

Bonne chasse ! 🛍️🔥
