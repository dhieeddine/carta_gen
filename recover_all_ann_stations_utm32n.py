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

print("Recuperation vectorisee des stations ann_stations...")
query = "SELECT id, id_station, nom, gouvernorat, longitude AS x, latitude AS y FROM ann_stations WHERE longitude IS NOT NULL AND latitude IS NOT NULL;"
df = pd.read_sql(query, conn)

print(f"Total stations chargees : {len(df)}")

# Filtrer celles qui ont x < 0 (longitudes négatives à corriger)
df_neg = df[df['x'] < 0].copy()
print(f"Stations a corriger (X negatif) : {len(df_neg)}")

if not df_neg.empty:
    # 1. Reprojeter EPSG:32632 -> EPSG:4326 pour retrouver lon, lat
    gdf_neg = gpd.GeoDataFrame(df_neg, geometry=gpd.points_from_xy(df_neg['x'], df_neg['y']), crs="EPSG:32632").to_crs("EPSG:4326")
    
    # 2. Prendre abs(lon) et abs(lat) pour les rendre positives (Tunisie Est & Nord)
    lon_pos = gdf_neg.geometry.x.abs()
    lat_pos = gdf_neg.geometry.y.abs()
    
    # 3. Vectorisé EPSG:4326 -> EPSG:32632
    gdf_pos = gpd.GeoDataFrame(df_neg, geometry=gpd.points_from_xy(lon_pos, lat_pos), crs="EPSG:4326").to_crs("EPSG:32632")
    
    df_neg['new_x'] = gdf_pos.geometry.x
    df_neg['new_y'] = gdf_pos.geometry.y
    
    print("Mise a jour batch en base de donnees...")
    args = [(row['new_x'], row['new_y'], row['id']) for _, row in df_neg.iterrows()]
    cur.executemany("UPDATE ann_stations SET longitude = %s, latitude = %s WHERE id = %s;", args)
    conn.commit()

# Statistiques finales
df_stats = pd.read_sql("SELECT MIN(longitude) as min_x, MAX(longitude) as max_x, MIN(latitude) as min_y, MAX(latitude) as max_y, COUNT(*) as nb_valid FROM ann_stations WHERE longitude BETWEEN 250000 AND 800000 AND latitude BETWEEN 3200000 AND 4300000;", conn)
print("\nStatistiques finales des stations UTM 32N (metres) :")
print(df_stats.to_string(index=False))

cur.close()
conn.close()
