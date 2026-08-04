import os
import psycopg2
import pandas as pd
import geopandas as gpd
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL non définie")

conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

print("Nettoyage et conversion propre de ann_stations vers UTM Zone 32N...")

# Charger toutes les stations
query = "SELECT id, id_station, nom, gouvernorat, longitude, latitude FROM ann_stations;"
df = pd.read_sql(query, conn)

print(f"Total stations dans ann_stations : {len(df)}")

# Reconstituer les coordonnées WGS84 (degrés positifs pour la Tunisie)
records_to_update = []
for idx, row in df.iterrows():
    val1, val2 = row['longitude'], row['latitude']
    if val1 is None or val2 is None:
        continue
    
    # Prendre la valeur absolue pour corriger les faux signes négatifs (-10.77 -> +10.77)
    v1, v2 = abs(val1), abs(val2)
    
    lon, lat = None, None
    
    # Si c'est déjà en mètres UTM 32N valides pour la Tunisie
    if 250000 <= v1 <= 800000 and 3200000 <= v2 <= 4300000:
        # Déjà UTM 32N correct
        continue
    elif 3200000 <= v1 <= 4300000 and 250000 <= v2 <= 800000:
        # Inversé X et Y en UTM 32N
        records_to_update.append((v2, v1, row['id']))
        continue
    
    # Sinon, si c'est en degrés WGS84 (ex: lon~7..12, lat~30..38)
    if 7.0 <= v1 <= 12.0 and 30.0 <= v2 <= 38.0:
        lon, lat = v1, v2
    elif 30.0 <= v1 <= 38.0 and 7.0 <= v2 <= 12.0:
        lon, lat = v2, v1
        
    if lon is not None and lat is not None:
        # Convertir WGS84 -> UTM 32N (mètres)
        gdf = gpd.GeoDataFrame([{'id': row['id']}], geometry=gpd.points_from_xy([lon], [lat]), crs="EPSG:4326")
        gdf_utm = gdf.to_crs("EPSG:32632")
        utm_x = float(gdf_utm.geometry.x.iloc[0])
        utm_y = float(gdf_utm.geometry.y.iloc[0])
        records_to_update.append((utm_x, utm_y, row['id']))

print(f"Mise a jour de {len(records_to_update)} stations dans PostgreSQL...")
for utm_x, utm_y, st_id in records_to_update:
    cur.execute("UPDATE ann_stations SET longitude = %s, latitude = %s WHERE id = %s;", (utm_x, utm_y, st_id))

conn.commit()
print("Commit effectue avec succes !")

# Vérification des coordonnées finales
df_check = pd.read_sql("SELECT id_station, nom, gouvernorat, longitude AS x_utm, latitude AS y_utm FROM ann_stations WHERE longitude IS NOT NULL AND latitude IS NOT NULL LIMIT 10;", conn)
print("\nEchantillon des stations nettoyees en UTM Zone 32N (metres) :")
print(df_check.to_string(index=False))

# Statistiques sur les bornes UTM 32N
df_stats = pd.read_sql("SELECT MIN(longitude) as min_x, MAX(longitude) as max_x, MIN(latitude) as min_y, MAX(latitude) as max_y, COUNT(*) as nb_valid FROM ann_stations WHERE longitude > 200000 AND latitude > 3000000;", conn)
print("\nStatistiques globales des stations UTM 32N :")
print(df_stats.to_string(index=False))

cur.close()
conn.close()
