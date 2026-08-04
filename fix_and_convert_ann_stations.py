import pandas as pd
import numpy as np
import geopandas as gpd
import matplotlib.pyplot as plt
from matplotlib.ticker import ScalarFormatter
from matplotlib.colors import ListedColormap, BoundaryNorm
from matplotlib.patches import Patch
import sqlalchemy
import os
from shapely.vectorized import contains
from scipy.spatial import cKDTree
from dotenv import load_dotenv

load_dotenv()
engine = sqlalchemy.create_engine(os.environ['DATABASE_URL'])

# 1. Chargement des données
query = """SELECT s.id_station, s.nom AS station, s.y, s.x, SUM(p.valeur_mm) AS pluie_avr_2023 FROM ann_pluies p JOIN ann_stations s ON p.id_station = s.id_station AND p.gouvernorat = s.gouvernorat WHERE EXTRACT(MONTH FROM p.date_obs) = 4 AND EXTRACT(YEAR FROM p.date_obs) = 2023 AND s.y IS NOT NULL AND s.x IS NOT NULL GROUP BY s.id_station, s.nom, s.y, s.x;"""
df = pd.read_sql(query, engine)
df.columns = df.columns.str.lower()
df = df.dropna(subset=['pluie_avr_2023', 'x', 'y']).reset_index(drop=True)

# 2. Rejection spatiale UTM 32N
gdf_pays = gpd.read_postgis('SELECT geom FROM limite_pays_polygon', engine, geom_col='geom').to_crs('EPSG:32632')
gdf_gouv = gpd.read_postgis('SELECT lib_fr, geom FROM gouvernorats', engine, geom_col='geom').to_crs('EPSG:32632')
gdf_rgion = gpd.read_postgis('SELECT lib_fr, geom FROM rgion_hydrographique', engine, geom_col='geom').to_crs('EPSG:32632')

if not df.empty and df['x'].abs().max() <= 180:
    gdf_st_proj = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df['x'], df['y']), crs='EPSG:4326').to_crs('EPSG:32632')
    df['x'] = gdf_st_proj.geometry.x
    df['y'] = gdf_st_proj.geometry.y

# 3. Grille et Simplification
niveaux = [0, 20, 50, 75, 100, 150, 200, 250, 350]
couleurs = ['none', '#ff0000', '#ffff00', '#90ee90', '#228b22', '#4292c6', '#2171b5', '#08306b']
cmap = ListedColormap(couleurs)
norm = BoundaryNorm(niveaux, cmap.N)

bounds = gdf_pays.total_bounds
margin = 20000
x_grid = np.arange(bounds[0]-margin, bounds[2]+margin, 2500)
y_grid = np.arange(bounds[1]-margin, bounds[3]+margin, 2500)
x_mesh, y_mesh = np.meshgrid(x_grid, y_grid)
grid_points = np.column_stack([x_mesh.ravel(), y_mesh.ravel()])

k_val = min(10, len(df))
tree = cKDTree(df[['x', 'y']].values)
distances, indices = tree.query(grid_points, k=k_val)
distances = np.maximum(distances, 1e-10)
weights = 1.0 / (distances ** 2)
weights /= weights.sum(axis=1, keepdims=True)
z_1d = np.sum(weights * df['pluie_avr_2023'].values[indices], axis=1)

# 4. Rendu Cartographique
fig, ax = plt.subplots(figsize=(7, 9))
ax.set_aspect('equal')
gdf_pays.plot(ax=ax, facecolor='none', edgecolor='black', linewidth=1.5, zorder=4)
gdf_gouv.plot(ax=ax, facecolor='none', edgecolor='grey', linewidth=0.5, linestyle='--', zorder=3)
gdf_rgion.plot(ax=ax, facecolor='none', edgecolor='grey', linewidth=0.5, linestyle=':', zorder=3)

geom_simplified = gdf_pays.geometry.unary_union.simplify(100, preserve_topology=True)
mask_1d = contains(geom_simplified, grid_points[:, 0], grid_points[:, 1])
z_1d = np.where(mask_1d, z_1d, np.nan).reshape(x_mesh.shape)
z_1d = np.ma.masked_invalid(z_1d)

ax.yaxis.set_major_formatter(ScalarFormatter(useOffset=False))
ax.xaxis.set_major_formatter(ScalarFormatter(useOffset=False))
gdf_pays.boundary.plot(ax=ax, color='black', linewidth=1.5, zorder=4)
gdf_rgion.boundary.plot(ax=ax, color='grey', linewidth=0.5, linestyle=':', zorder=3)

# 5. Isohyètes
norm = BoundaryNorm(niveaux, cmap.N)
cmap = ListedColormap(couleurs)
ax.set_aspect('equal')
gdf_couv = gpd.GeoDataFrame(None, geometry=gdf_pays.geometry.simplify(100, preserve_topology=True), crs='EPSG:32632')
gdf_couv['z'] = z_1d.mean()
gdf_couv['col'] = 'none'
gdf_couv = gdf_couv.dropna(subset=['z', 'col']).reset_index(drop=True)
gdf_couv.plot(ax=ax, facecolor=cmap(norm(gdf_couv['z'].values[0])), edgecolor=cmap(norm(gdf_couv['z'].values[0])), linewidth=2.5, zorder=5)

# 6. TOUJOURS TERMINER PAR CETTE Ligne!!!
plt.savefig('output_isohyete.png', dpi=300, bbox_inches='tight')
plt.show()