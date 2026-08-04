import os
import psycopg2
import pandas as pd
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL non définie")

conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

MAPPING_GOUV = {
    'jandouba': 'Jendouba',
    'jendouba': 'Jendouba',
    'siliana': 'Siliana',
    'sousse': 'Sousse',
    'beja': 'Beja',
    'kebeli': 'Kebeli',
    'kebili': 'Kebeli',
    'tatouine': 'Tatouine',
    'tataouine': 'Tatouine',
    'sidi bouzid': 'Sidi bouzid',
    'sidibouzid': 'Sidi bouzid',
    'ben arous': 'Ben arous',
    'benarous': 'Ben arous',
    'mednine': 'Mednine',
    'medenine': 'Mednine',
    'kassrine': 'Kassrine',
    'kasserine': 'Kassrine',
    'kairouan': 'Kairouan',
    'monastir': 'Monastir',
    'mahdia': 'Mahdia',
    'sfax': 'Sfax',
    'gafsa': 'Gafsa',
    'tozeur': 'Tozeur',
    'bizerte': 'Bizerte',
    'tunis': 'Tunis',
    'nabeul': 'Nabeul',
    'zaghouan': 'Zaghouan',
    'gabes': 'Gabes',
    'ariana': 'Ariana',
    'manouba': 'Manouba',
    'kef': 'Kef'
}

print("Normalisation des noms de gouvernorats...")
df = pd.read_sql("SELECT DISTINCT gouvernorat FROM ann_stations;", conn)

updated = 0
for old_name in df['gouvernorat'].dropna().unique():
    key = old_name.strip().lower()
    if key in MAPPING_GOUV:
        target = MAPPING_GOUV[key]
        cur.execute("UPDATE ann_stations SET gouvernorat = %s WHERE LOWER(TRIM(gouvernorat)) = %s;", (target, key))
        updated += cur.rowcount

conn.commit()
print(f"OK: Normalisation terminee ({updated} lignes mises a jour) !")

df_jendouba = pd.read_sql("SELECT COUNT(*) as nb FROM ann_stations WHERE LOWER(gouvernorat) IN ('jendouba', 'jandouba');", conn)
print(f"Total stations Jendouba dans ann_stations : {df_jendouba['nb'].iloc[0]}")

cur.close()
conn.close()
