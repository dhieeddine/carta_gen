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

print("Recuperation des stations depuis ann_stations...")
query = "SELECT id, id_station, nom, longitude, latitude FROM ann_stations WHERE longitude IS NOT NULL AND latitude IS NOT NULL;"
df = pd.read_sql(query, conn)

print(f"Total stations trouvees : {len(df)}")
df_deg = df[(df['longitude'].abs() <= 180) & (df['latitude'].abs() <= 90)].copy()

print(f"Stations en degres a convertir vers UTM 32N (EPSG:32632) : {len(df_deg)}")

if not df_deg.empty:
    gdf = gpd.GeoDataFrame(df_deg, geometry=gpd.points_from_xy(df_deg['longitude'], df_deg['latitude']), crs="EPSG:4326")
    gdf_utm = gdf.to_crs("EPSG:32632")
    
    df_deg['utm_x'] = gdf_utm.geometry.x
    df_deg['utm_y'] = gdf_utm.geometry.y
    
    print("Mise a jour des coordonnees dans PostgreSQL (UTM Zone 32N)...")
    updated_count = 0
    for idx, row in df_deg.iterrows():
        cur.execute(
            "UPDATE ann_stations SET longitude = %s, latitude = %s WHERE id = %s;",
            (row['utm_x'], row['utm_y'], row['id'])
        )
        updated_count += 1
        
    conn.commit()
    print(f"OK: {updated_count} stations mises a jour avec succes en UTM Zone 32N (EPSG:32632) !")

df_check = pd.read_sql("SELECT id_station, nom, longitude AS x_utm, latitude AS y_utm FROM ann_stations WHERE longitude IS NOT NULL LIMIT 10;", conn)
print("\nEchantillon des stations apres conversion UTM 32N :")
print(df_check.to_string(index=False))

cur.close()
conn.close()
