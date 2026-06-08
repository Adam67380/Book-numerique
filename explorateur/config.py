import os
from dotenv import load_dotenv

load_dotenv()

INSEE_KEY = os.environ["INSEE_KEY"]
INSEE_SECRET = os.environ["INSEE_SECRET"]
PAPPERS_API_KEY = os.environ["PAPPERS_API_KEY"]
AIRTABLE_TOKEN = os.environ["AIRTABLE_TOKEN"]
AIRTABLE_BASE_ID = os.environ["AIRTABLE_BASE_ID"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
GOOGLE_SOLAR_API_KEY = os.getenv("GOOGLE_SOLAR_API_KEY", "")
ZONE_COMMUNES = [c.strip() for c in os.environ.get("ZONE_COMMUNES", "").split(",") if c.strip()]

NAF_CIBLES = ["47.11D", "47.11F"]
SCI_FORME_JURIDIQUE = "6540"
