#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Script de génération de l'annuaire pluviométrique directement à partir de la base de données PostgreSQL.
Version dynamique et automatisée enrichie (Sommaire, Avant-Propos, Mensuel, Saisonnier, Classes, Monographies).
"""

import os
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
import argparse
import subprocess
import shutil
import re
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import geopandas as gpd
from scipy.spatial import cKDTree
from matplotlib.colors import ListedColormap, BoundaryNorm
from matplotlib.patches import Patch
import psycopg2
from dotenv import load_dotenv
from datetime import datetime
import unicodedata
import calendar
import warnings
from matplotlib.ticker import ScalarFormatter
warnings.filterwarnings('ignore')

# ------------------------- Configuration -------------------------
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL non définie dans le fichier .env")

# Dossiers de sortie
IMG_DIR = "images_temp"
os.makedirs(IMG_DIR, exist_ok=True)

LOGO_PATH = "logo_dgre.png"

# Mapping pour la résolution des gouvernorats
GOUV_MAPPING = {
    '22': 'Jendouba', '21': 'Béja', '23': 'Le Kef', '24': 'Siliana',
    '17': 'Bizerte', '11': 'Tunis', '16': 'Zaghouan', '15': 'Nabeul',
    '42': 'Kasserine', '43': 'Sidi Bouzid', '41': 'Kairouan',
    '31': 'Sousse', '32': 'Monastir', '33': 'Mahdia', '34': 'Sfax',
    '61': 'Gafsa', '62': 'Tozeur', '63': 'Kébili',
    '51': 'Gabès', '52': 'Mednine', '53': 'Tataouine',
    '12': 'Ariana', '13': 'Ben Arous', '14': 'Manouba'
}
GOUV_LIST = sorted(GOUV_MAPPING.values())

GOUVS_SURF = {
    # NORD OUEST
    'jendouba': 3102, 'jandouba': 3102,
    'beja': 3740,
    'kef': 4965, 'le kef': 4965,
    'siliana': 4710,
    
    # NORD EST
    'tunis': 346,
    'ariana': 482,
    'ben arous': 761,
    'manouba': 1137, 'la manouba': 1137,
    'nabeul': 2788,
    'zaghouan': 2768,
    'bizerte': 3443,
    
    # CENTRE OUEST
    'kairouan': 6712,
    'kasserine': 8260, 'kassrine': 8260,
    'sidi bouzid': 7212,
    
    # CENTRE EST
    'sousse': 2669,
    'monastir': 1019,
    'mahdia': 2878,
    'sfax': 6864,
    
    # SUD OUEST
    'gafsa': 7807,
    'tozeur': 4719,
    'kebili': 23235, 'kebeli': 23235,
    
    # SUD EST
    'gabes': 7166,
    'tatouine': 38889, 'tataouine': 38889,
    'mednine': 9250, 'medenine': 9250
}

def get_gouvernorat_from_code(code):
    return GOUV_MAPPING.get(str(code)[-2:], 'Inconnu')

def normalize_string(s):
    """Supprime les accents et remplace les caractères spéciaux par des underscores."""
    s = unicodedata.normalize('NFKD', str(s)).encode('ascii', errors='ignore').decode('utf-8')
    s = re.sub(r'[^a-zA-Z0-9]', '_', s)
    s = re.sub(r'_+', '_', s)
    return s.lower().strip('_')

def escape_latex(text):
    """Échappe les caractères réservés de LaTeX pour éviter les erreurs de compilation."""
    raw_text = str(text)
    conv = {
        '&': r'\&', '%': r'\%', '$': r'\$', '#': r'\#', '_': r'\_',
        '{': r'\{', '}': r'\}', '~': r'\textasciitilde{}',
        '^': r'\textasciicircum{}', '\\': r'\textbackslash{}',
    }
    regex = re.compile('|'.join(re.escape(str(key)) for key in sorted(conv.keys(), key=lambda item: -len(item))))
    return regex.sub(lambda match: conv[match.group()], raw_text)

_THIESSEN_WEIGHTS = None

def get_thiessen_weights(conn, df_stations):
    global _THIESSEN_WEIGHTS
    if _THIESSEN_WEIGHTS is not None:
        return _THIESSEN_WEIGHTS

    print("📐 Calcul des polygones de Thiessen (Voronoi) et des coefficients spatiaux...")
    from shapely.geometry import Point, MultiPoint
    from shapely.ops import voronoi_diagram
    
    # 1. Charger les limites géographiques
    try:
        gdf_pays = gpd.read_postgis("SELECT geom FROM limite_pays_polygon", conn, geom_col='geom', crs="EPSG:4326").to_crs("EPSG:32632")
        gdf_gouv = gpd.read_postgis("SELECT lib_fr, geom FROM gouvernorats", conn, geom_col='geom', crs="EPSG:4326").to_crs("EPSG:32632")
    except Exception:
        BASE_DIR = r"D:\Desktop\stage_dgre\backend\data\raw"
        SHP_PAYS = os.path.join(BASE_DIR, "limit_pays_polygon_tunisie", "limite_pays_polygon.shp")
        SHP_GOUV = os.path.join(BASE_DIR, "deleg_gouv_regions", "Gouvernorats.shp")
        gdf_pays = gpd.read_file(SHP_PAYS).to_crs("EPSG:32632")
        gdf_gouv = gpd.read_file(SHP_GOUV).to_crs("EPSG:32632")

    # 2. Préparer les points stations
    df_st = df_stations.copy()
    df_st['geom'] = df_st.apply(lambda r: Point(r['lon'], r['lat']), axis=1)
    gdf_st = gpd.GeoDataFrame(df_st, geometry='geom', crs="EPSG:32632")
    
    boundary = gdf_pays.union_all() if hasattr(gdf_pays, 'union_all') else gdf_pays.unary_union
    mp = MultiPoint(gdf_st['geom'].tolist())
    envelope = boundary.envelope.buffer(100000)
    
    # Voronoi
    vor = voronoi_diagram(mp, envelope=envelope)
    vor_polys = list(vor.geoms)
    
    gdf_vor = gpd.GeoDataFrame(geometry=vor_polys, crs="EPSG:32632")
    gdf_thiessen = gpd.sjoin(gdf_vor, gdf_st[['id_station', 'geom']], how='inner', predicate='contains')
    gdf_thiessen['geometry'] = gdf_thiessen['geometry'].intersection(boundary)
    gdf_thiessen = gdf_thiessen[~gdf_thiessen.is_empty]
    
    # 3. Préparer les géométries des régions
    REGIONS_DEF = {
        'NORD OUEST': ['jendouba', 'beja', 'le kef', 'kef', 'siliana'],
        'NORD EST': ['tunis', 'ariana', 'ben arous', 'manouba', 'nabeul', 'zaghouan', 'bizerte'],
        'CENTRE OUEST': ['kairouan', 'kassrine', 'kasserine', 'sidi bouzid'],
        'CENTRE EST': ['sousse', 'monastir', 'mahdia', 'sfax'],
        'SUD OUEST': ['gafsa', 'tozeur', 'kebili', 'kebeli'],
        'SUD EST': ['gabes', 'tatouine', 'tataouine', 'mednine', 'medenine']
    }
    
    gdf_gouv['norm_gouv'] = gdf_gouv['lib_fr'].apply(normalize_string)
    regions_geom = {}
    for rname, gouvs in REGIONS_DEF.items():
        r_gdf = gdf_gouv[gdf_gouv['norm_gouv'].isin(gouvs)]
        regions_geom[rname] = r_gdf.union_all() if hasattr(r_gdf, 'union_all') else r_gdf.unary_union
        
    # 4. Calculer les poids
    # Poids nationaux
    tot_nat_area = boundary.area
    gdf_thiessen['weight_nat'] = gdf_thiessen['geometry'].area / tot_nat_area
    weights_nat = dict(zip(gdf_thiessen['id_station'], gdf_thiessen['weight_nat']))
    
    # Poids régionaux
    weights_reg = {}
    for rname, r_geom in regions_geom.items():
        intersections = gdf_thiessen['geometry'].intersection(r_geom)
        areas = intersections.area
        w_df = pd.DataFrame({'id_station': gdf_thiessen['id_station'], 'area': areas})
        w_df = w_df[w_df['area'] > 0]
        # normalize
        tot_active_area = w_df['area'].sum()
        if tot_active_area > 0:
            w_df['weight'] = w_df['area'] / tot_active_area
            weights_reg[rname] = dict(zip(w_df['id_station'], w_df['weight']))
        else:
            weights_reg[rname] = {}
            
    _THIESSEN_WEIGHTS = {
        'national': weights_nat,
        'regional': weights_reg
    }
    print("✅ Coefficients de Thiessen calculés avec succès.")
    return _THIESSEN_WEIGHTS

def compute_weighted_avg(df_vals, value_col, weights_dict):
    if df_vals.empty:
        return 0.0
    # Join weights
    df_w = df_vals[['id_station', value_col]].copy()
    df_w['weight'] = df_w['id_station'].map(weights_dict)
    df_w = df_w.dropna(subset=['weight'])
    
    tot_w = df_w['weight'].sum()
    if tot_w > 0:
        df_w['weight_norm'] = df_w['weight'] / tot_w
        return (df_w[value_col] * df_w['weight_norm']).sum()
    return 0.0

# ------------------------- 1. Connexion et extraction PostgreSQL -------------------------
def connect_db():
    return psycopg2.connect(DATABASE_URL)

def get_stations(conn, gouv_filter=None):
    print("🛰️ Récupération des stations de mesures depuis la table station_148...")
    query = """
        SELECT
            id_station,
            nom,
            lon,
            lat,
            altitude,
            gouvernorat
        FROM station_148;
    """
    df = pd.read_sql(query, conn)
    if df.empty:
        return df
    
    # Nettoyer les noms
    df['nom'] = df['nom'].str.strip()
    df['gouv'] = df['gouvernorat'].str.strip()
    
    # Nettoyage des anomalies géographiques (ex: station Pépinière Essadkia Manouba à Y < 3.8e6 au sud)
    bad_coords_mask = (df['gouv'].apply(normalize_string).isin(['manouba', 'tunis', 'ariana', 'ben arous', 'bizerte', 'beja', 'jandouba'])) & (df['lat'] < 3800000)
    if bad_coords_mask.any():
        nb_bad = bad_coords_mask.sum()
        print(f"⚠️ {nb_bad} station(s) exclue(s) pour coordonnées Y incohérentes (ex: gouvernorat du Nord localisé au Sud).")
        df = df[~bad_coords_mask]

    if gouv_filter and gouv_filter.lower() not in ('all', 'national'):
        aliases = {
            'jendouba': 'jandouba', 'jandouba': 'jandouba',
            'kasserine': 'kassrine', 'kassrine': 'kassrine',
            'kebili': 'kebeli', 'kebeli': 'kebeli',
            'tataouine': 'tatouine', 'tatouine': 'tatouine',
            'beja': 'beja', 'béja': 'beja',
            'medenine': 'mednine', 'mednine': 'mednine'
        }
        norm_filter = normalize_string(gouv_filter)
        target_norm = aliases.get(norm_filter, norm_filter)
        df = df[df['gouv'].apply(lambda g: aliases.get(normalize_string(g), normalize_string(g))) == target_norm]
        
    # Dédoublonner les stations ayant le même nom et le même gouvernorat dans la BDD
    df = df.drop_duplicates(subset=['nom', 'gouv'])

    print(f"📊 {len(df)} stations chargées pour le gouvernorat/filtre : {gouv_filter}")
    return df

def get_rainfall_data(conn, station_ids, annee):
    if not station_ids:
        return pd.DataFrame()
    date_debut, date_fin = f"{annee}-09-01 00:00:00", f"{annee+1}-08-31 23:59:59"
    ids_tuple = tuple(station_ids) if len(station_ids) > 1 else f"('{station_ids[0]}')"
    
    print(f"🌧️ Récupération des pluies journalières depuis pluies_148 pour la période {annee}-{annee+1}...")
    query = f"""
        SELECT id_station, date_obs AS date, valeur_mm AS valeur 
        FROM pluies_148 
        WHERE id_station IN {ids_tuple} 
          AND date_obs >= '{date_debut}' 
          AND date_obs <= '{date_fin}' 
          AND valeur_mm IS NOT NULL 
        ORDER BY id_station, date_obs;
    """
    return pd.read_sql(query, conn)

def get_daily_data_for_station(conn, station_id, annee):
    date_debut, date_fin = f"{annee}-09-01 00:00:00", f"{annee+1}-08-31 23:59:59"
    query = """
        SELECT date_obs AS date, EXTRACT(DAY FROM date_obs) AS jour, EXTRACT(MONTH FROM date_obs) AS mois, valeur_mm AS valeur 
        FROM pluies_148 
        WHERE id_station = %s 
          AND date_obs >= %s 
          AND date_obs <= %s 
          AND valeur_mm IS NOT NULL 
        ORDER BY date_obs;
    """
    return pd.read_sql(query, conn, params=(station_id, date_debut, date_fin))

def get_spatial_data(conn):
    print("🗺️ Chargement des contours géographiques (PostGIS / UTM 32N)...")
    try:
        gdf_pays = gpd.read_postgis("SELECT geom FROM limite_pays_polygon", conn, geom_col='geom', crs="EPSG:4326").to_crs("EPSG:32632")
        gdf_gouv = gpd.read_postgis("SELECT lib_fr, geom FROM gouvernorats", conn, geom_col='geom', crs="EPSG:4326").to_crs("EPSG:32632")
        print("✅ Contours géographiques PostGIS chargés avec succès en UTM 32N.")
        return gdf_pays, gdf_gouv
    except Exception as e:
        print(f"⚠️ Échec du chargement PostGIS ({e}), chargement via shapefiles locaux...")
        BASE_DIR = r"D:\Desktop\stage_dgre\backend\data\raw"
        SHP_PAYS = os.path.join(BASE_DIR, "limit_pays_polygon_tunisie", "limite_pays_polygon.shp")
        SHP_GOUV = os.path.join(BASE_DIR, "deleg_gouv_regions", "Gouvernorats.shp")
        gdf_pays = gpd.read_file(SHP_PAYS).to_crs("EPSG:32632")
        gdf_gouv = gpd.read_file(SHP_GOUV).to_crs("EPSG:32632")
        return gdf_pays, gdf_gouv

def get_gouv_shape(gdf_gouv, gouv_name):
    if gouv_name.lower() in ('all', 'national'): 
        return None
    possible_cols = ['LIB_FR', 'lib_fr', 'NOM', 'Nom', 'nom', 'NOM_FR', 'nom_fr']
    col_name = next((c for c in possible_cols if c in gdf_gouv.columns), None)
    if not col_name: 
        return None
    gdf_gouv['_normalized'] = gdf_gouv[col_name].astype(str).apply(normalize_string)
    return gdf_gouv[gdf_gouv['_normalized'] == normalize_string(gouv_name)].copy()

def get_yasra_metrics(conn):
    """Récupère directement les colonnes moy_, pct et les normales mensuelles enregistrées dans yasra_data."""
    try:
        df = pd.read_sql("SELECT code::text AS id_station, sept AS moy_sept, octo AS moy_octo, nove AS moy_nove, dece AS moy_dece, janv AS moy_janv, fev AS moy_fev, mar AS moy_mar, avr AS moy_avr, mai AS moy_mai, juin AS moy_juin, juil AS moy_juil, aout AS moy_aout, moy_, pct FROM yasra_data;", conn)
        return df.set_index('id_station')
    except Exception as e:
        print(f"⚠️ Erreur chargement yasra_data (moy_/pct) : {e}")
        return pd.DataFrame()

# ------------------------- 2. Traitement statistique -------------------------
def compute_stats_from_rainfall(df_rain, df_stations, conn=None):
    if df_rain.empty or df_stations.empty: 
        return None
    
    # 1. Tronquer la date au jour pur (sans l'heure) pour éliminer les vrais doublons de saisie
    df_rain['date_only'] = pd.to_datetime(df_rain['date']).dt.date
    df_rain = df_rain.drop_duplicates(subset=['id_station', 'date_only'])
    
    df = pd.merge(df_rain, df_stations[['id_station', 'nom', 'lon', 'lat', 'gouv']], on='id_station', how='inner')
    df['date'] = pd.to_datetime(df['date'])
    df['mois'] = df['date'].dt.month
    
    # Calculer le cumul mensuel par station
    df_mois = df.groupby(['id_station', 'mois'])['valeur'].sum().reset_index()
    pivot = df_mois.pivot(index='id_station', columns='mois', values='valeur').fillna(0)
    
    # Ordre de l'année hydrologique (septembre à août)
    mois_order = [9, 10, 11, 12, 1, 2, 3, 4, 5, 6, 7, 8]
    pivot = pivot.reindex(columns=mois_order, fill_value=0)
    pivot.columns = ['sept', 'octo', 'nove', 'dece', 'janv', 'fev', 'mar', 'avr', 'mai', 'juin', 'juil', 'aout']
    
    coords = df_stations[['id_station', 'nom', 'lon', 'lat', 'gouv']].drop_duplicates(subset=['id_station']).set_index('id_station')
    pivot = pivot.join(coords)
    
    # Calculs saisonniers
    pivot['auto'] = pivot[['sept', 'octo', 'nove']].sum(axis=1)
    pivot['hiver'] = pivot[['dece', 'janv', 'fev']].sum(axis=1)
    pivot['print'] = pivot[['mar', 'avr', 'mai']].sum(axis=1)
    pivot['ete'] = pivot[['juin', 'juil', 'aout']].sum(axis=1)
    pivot['total'] = pivot[['auto', 'hiver', 'print', 'ete']].sum(axis=1)

    # Intégration des colonnes moy_ et pct directes de yasra_data (sans recalcul)
    ref_moy_val = 0
    if conn is not None:
        df_yasra = get_yasra_metrics(conn)
        if not df_yasra.empty:
            pivot = pivot.join(df_yasra, how='left')
            m_cols = ['moy_sept', 'moy_octo', 'moy_nove', 'moy_dece', 'moy_janv', 'moy_fev', 'moy_mar', 'moy_avr', 'moy_mai', 'moy_juin', 'moy_juil', 'moy_aout']
            m_cols_avail = [c for c in m_cols if c in pivot.columns]
            if m_cols_avail:
                ref_moy_val = pivot[m_cols_avail].mean().sum() / 12.0

    moyenne_mensuelle = pivot[['sept', 'octo', 'nove', 'dece', 'janv', 'fev', 'mar', 'avr', 'mai', 'juin', 'juil', 'aout']].mean()
    
    if ref_moy_val == 0:
        ref_moy_val = moyenne_mensuelle.mean()

    return {
        'pivot': pivot,
        'moyenne_mensuelle': moyenne_mensuelle,
        'saisons': {
            'Automne': pivot['auto'].mean(), 
            'Hiver': pivot['hiver'].mean(), 
            'Printemps': pivot['print'].mean(), 
            'Été': pivot['ete'].mean()
        },
        'total_national': pivot['total'].mean(),
        'ref_moy': ref_moy_val
    }

# ------------------------- Données historiques pour classes -------------------------
def get_historical_classes_data(conn, station_ids, current_annee):
    if not station_ids:
        return None
    ids_tuple = tuple(station_ids) if len(station_ids) > 1 else f"('{station_ids[0]}')"
    query = f"""
        SELECT id_station, date_obs, valeur_mm
        FROM pluies_148
        WHERE id_station IN {ids_tuple}
          AND date_obs < '{current_annee}-09-01'
          AND date_obs >= '2015-09-01'
          AND valeur_mm IS NOT NULL;
    """
    try:
        df_hist = pd.read_sql(query, conn)
        if df_hist.empty:
            return None
        df_hist['date_obs'] = pd.to_datetime(df_hist['date_obs'])
        df_hist['hydro_year'] = df_hist['date_obs'].apply(lambda d: d.year if d.month >= 9 else d.year - 1)
        df_hist = df_hist[df_hist['hydro_year'] < current_annee]
        if df_hist.empty:
            return None
        annual_by_st_yr = df_hist.groupby(['id_station', 'hydro_year'])['valeur_mm'].sum().reset_index()
        mean_by_st = annual_by_st_yr.groupby('id_station')['valeur_mm'].mean().reset_index()
        return mean_by_st
    except Exception as e:
        print(f"⚠️ Erreur lors de la récupération des données historiques : {e}")
        return None

# ------------------------- 3. Cartographie & Graphiques -------------------------
def idw_interpolation(df, grid_lon, grid_lat, value_col, power=2, k=10):
    stations = df[['lon', 'lat', value_col]].dropna().values
    if len(stations) == 0: 
        return np.full(grid_lon.shape, np.nan)
    
    tree = cKDTree(stations[:, :2])
    grid_points = np.column_stack([grid_lon.ravel(), grid_lat.ravel()])
    distances, indices = tree.query(grid_points, k=min(k, len(stations)))
    distances = np.maximum(distances, 1e-10)
    weights = 1.0 / (distances ** power)
    weights /= weights.sum(axis=1, keepdims=True)
    interpolated = np.sum(weights * stations[indices, 2], axis=1)
    return interpolated.reshape(grid_lon.shape)

def generate_isohyet_map(df, gdf_pays, gdf_gouv, gdf_gouv_mask, value_col, titre, fname, levels, colors):
    os.makedirs(IMG_DIR, exist_ok=True)
    fig, ax = plt.subplots(figsize=(7, 9))
    bounds = gdf_gouv_mask.total_bounds if gdf_gouv_mask is not None else gdf_pays.total_bounds
    lon_min, lat_min, lon_max, lat_max = bounds
    margin = 15000 if gdf_gouv_mask is not None else 30000
    
    lon_grid = np.arange(lon_min - margin, lon_max + margin, 2500)
    lat_grid = np.arange(lat_min - margin, lat_max + margin, 2500)
    lon_mesh, lat_mesh = np.meshgrid(lon_grid, lat_grid)
    z_mesh = idw_interpolation(df, lon_mesh, lat_mesh, value_col)
    
    # Masquer l'extérieur
    from shapely.vectorized import contains
    geom = gdf_gouv_mask.geometry.unary_union if gdf_gouv_mask is not None else gdf_pays.geometry.unary_union
    z_mesh = np.where(contains(geom, lon_mesh, lat_mesh), z_mesh, np.nan)
    
    cmap = ListedColormap(colors[:len(levels)-1])
    norm = BoundaryNorm(levels, cmap.N)
    
    if gdf_gouv_mask is not None:
        gdf_gouv_mask.plot(ax=ax, facecolor='none', edgecolor='black', linewidth=1.5, zorder=4)
    else:
        gdf_pays.plot(ax=ax, facecolor='none', edgecolor='black', linewidth=1.5, zorder=4)
        gdf_gouv.plot(ax=ax, facecolor='none', edgecolor='grey', linewidth=0.5, linestyle='--', zorder=3)
        if gdf_gouv is not None:
            for _, g_row in gdf_gouv.iterrows():
                geom = g_row.get('geom', g_row.get('geometry'))
                cent = geom.centroid
                g_name = g_row.get('lib_fr', g_row.get('nom', ''))
                if g_name:
                    ax.text(cent.x, cent.y, str(g_name), fontsize=5.5, ha='center', va='center', color='#2c3e50', fontweight='bold', alpha=0.65, zorder=6)
        
    cf = ax.contourf(lon_mesh, lat_mesh, z_mesh, levels=levels, cmap=cmap, norm=norm, alpha=0.75, extend='max', zorder=1)
    # Ne pas tracer de ligne de contour pour 0 mm
    contour_levels = [l for l in levels if l > 0]
    if contour_levels:
        cs = ax.contour(lon_mesh, lat_mesh, z_mesh, levels=contour_levels, colors='#2c3e50', linewidths=0.6, zorder=2)
        ax.clabel(cs, inline=True, fontsize=7, fmt='%d mm')
    
    # Pas de points station sur les isohyètes (carte dédiée séparée)
    ax.set_xlim(lon_min - margin, lon_max + margin)
    ax.set_ylim(lat_min - margin, lat_max + margin)
    ax.set_title(titre, fontsize=12, fontweight='bold', pad=10)
    
    # Échelle X et Y en UTM Zone 32N (mètres)
    ax.set_xlabel('X (UTM Zone 32N, m)', fontsize=9, fontweight='bold', fontstyle='italic')
    ax.set_ylabel('Y (UTM Zone 32N, m)', fontsize=9, fontweight='bold', fontstyle='italic')
    
    formatter_y = ScalarFormatter(useOffset=False)
    formatter_y.set_scientific(False)
    ax.yaxis.set_major_formatter(formatter_y)
    
    formatter_x = ScalarFormatter(useOffset=False)
    formatter_x.set_scientific(False)
    ax.xaxis.set_major_formatter(formatter_x)

    ax.tick_params(axis='x', rotation=45, labelsize=8)
    ax.tick_params(axis='y', rotation=45, labelsize=8)
    for tick in ax.get_xticklabels() + ax.get_yticklabels():
        tick.set_fontstyle('italic')
    ax.grid(True, linestyle='--', alpha=0.3)
    
    # Boussole / Rose des vents
    cx, cy, csize = 0.92, 0.88, 0.05
    ax.annotate('N', xy=(cx, cy + csize), xytext=(cx, cy),
                arrowprops=dict(facecolor='black', edgecolor='black', width=1.5, headwidth=6, headlength=7),
                ha='center', va='bottom', fontsize=8, fontweight='bold',
                xycoords='axes fraction', textcoords='axes fraction')
    ax.text(cx, cy - csize * 0.4, 'S', transform=ax.transAxes, ha='center', va='top', fontsize=7, fontweight='bold')
    ax.text(cx + csize * 0.8, cy + csize * 0.3, 'E', transform=ax.transAxes, ha='left', va='center', fontsize=7, fontweight='bold')
    ax.text(cx - csize * 0.8, cy + csize * 0.3, 'O', transform=ax.transAxes, ha='right', va='center', fontsize=7, fontweight='bold')
    
    legend_elements = [Patch(facecolor=colors[i], label=f"{levels[i]} - {levels[i+1]} mm" if i < len(levels)-2 else f"> {levels[i]} mm") for i in range(len(levels)-1)]
    ax.legend(handles=legend_elements, title='Pluviométrie (mm)', loc='lower left', fontsize=8, title_fontsize=9,
              framealpha=1.0, edgecolor='black')
    
    plt.tight_layout()
    fig.savefig(os.path.join(IMG_DIR, fname), dpi=200, bbox_inches='tight')
    plt.close(fig)
def generate_rainfall_class_figure(conn, station_ids, current_annee, df_pivot):
    bins = [0, 100, 200, 400, 600, 800, 5000]
    labels = ['< 100', '100-200', '200-400', '400-600', '600-800', '> 800']
    
    current_totals = df_pivot['total'].dropna()
    current_counts, _ = np.histogram(current_totals, bins=bins)
    n_curr = len(current_totals)
    current_pcts = (current_counts / n_curr * 100) if n_curr > 0 else np.zeros(len(labels))
    
    df_hist_mean = get_historical_classes_data(conn, station_ids, current_annee)
    has_hist = df_hist_mean is not None and not df_hist_mean.empty
    
    if has_hist:
        hist_totals = df_hist_mean['valeur_mm'].dropna()
        hist_counts, _ = np.histogram(hist_totals, bins=bins)
        n_hist = len(hist_totals)
        hist_pcts = (hist_counts / n_hist * 100) if n_hist > 0 else np.zeros(len(labels))
    else:
        hist_pcts = current_pcts

    x = np.arange(len(labels))
    width = 0.35
    
    fig, ax = plt.subplots(figsize=(8, 4.5))
    if has_hist:
        ax.bar(x - width/2, hist_pcts, width, label=f'Moyenne Historique (avant {current_annee})', color='#7f8c8d', alpha=0.85)
        ax.bar(x + width/2, current_pcts, width, label=f'Année {current_annee}-{current_annee+1}', color='#2980b9', alpha=0.85)
    else:
        ax.bar(x, current_pcts, width*1.2, label=f'Année {current_annee}-{current_annee+1}', color='#2980b9', alpha=0.85)

    ax.set_ylabel('% des stations', fontsize=10)
    ax.set_xlabel('Classes de pluviométrie (mm)', fontsize=10)
    ax.set_title('Répartition des Stations par Classe de Pluviométrie', fontsize=12, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.legend(fontsize=9)
    ax.grid(axis='y', linestyle=':', alpha=0.6)
    
    plt.tight_layout()
    fig.savefig(os.path.join(IMG_DIR, 'hist_classes.png'), dpi=200)
    plt.close(fig)

# ---- Palettes officielles DGRE (Sec -> Humide) ----
LEVELS_ANNUAL = [0, 100, 200, 300, 400, 500, 600, 800, 1000, 1200, 5000]
COLORS_ANNUAL = ["#FFFFFF", "#D96B27", "#F28E13", "#F5B800", "#F3E600", "#A2D929", "#33B04A", "#008A3C", "#009BB0", "#0A2F6E"]

LEVELS_SEASONAL = [0, 25, 50, 75, 100, 150, 200, 250, 300, 400, 5000]
COLORS_SEASONAL = ["#FFFFFF", "#D95B00", "#F28200", "#F2B200", "#E6E600", "#62C435", "#1E9E38", "#007338", "#008299", "#0C2B64"]

LEVELS_MONTHLY = [0, 10, 20, 30, 50, 70, 90, 110, 140, 180, 5000]
COLORS_MONTHLY = ["#FFFFFF", "#E66820", "#FA9100", "#FFC400", "#FFF200", "#88D62B", "#19A347", "#00A3A6", "#1F62B5", "#0D1F52"]

# Isohyètes mensuelles par mois
MONTHLY_CONFIG = {
    'sept': {'levels': LEVELS_MONTHLY, 'colors': COLORS_MONTHLY},
    'octo': {'levels': LEVELS_MONTHLY, 'colors': COLORS_MONTHLY},
    'nove': {'levels': LEVELS_MONTHLY, 'colors': COLORS_MONTHLY},
    'dece': {'levels': LEVELS_MONTHLY, 'colors': COLORS_MONTHLY},
    'janv': {'levels': LEVELS_MONTHLY, 'colors': COLORS_MONTHLY},
    'fev':  {'levels': LEVELS_MONTHLY, 'colors': COLORS_MONTHLY},
    'mar':  {'levels': LEVELS_MONTHLY, 'colors': COLORS_MONTHLY},
    'avr':  {'levels': LEVELS_MONTHLY, 'colors': COLORS_MONTHLY},
    'mai':  {'levels': LEVELS_MONTHLY, 'colors': COLORS_MONTHLY},
    'juin': {'levels': LEVELS_MONTHLY, 'colors': COLORS_MONTHLY},
    'juil': {'levels': LEVELS_MONTHLY, 'colors': COLORS_MONTHLY},
    'aout': {'levels': LEVELS_MONTHLY, 'colors': COLORS_MONTHLY},
}

# Isohyètes saisonnières
SEASONAL_CONFIG = {
    'auto':  {'levels': LEVELS_SEASONAL, 'colors': COLORS_SEASONAL, 'title': 'Automne (Sept – Nov)'},
    'hiver': {'levels': LEVELS_SEASONAL, 'colors': COLORS_SEASONAL, 'title': 'Hiver (Déc – Fév)'},
    'print': {'levels': LEVELS_SEASONAL, 'colors': COLORS_SEASONAL, 'title': 'Printemps (Mar – Mai)'},
    'ete':   {'levels': LEVELS_SEASONAL, 'colors': COLORS_SEASONAL, 'title': 'Eté (Juin – Août)'},
}

# Isohyètes interannuelles (DGRE officiel)
LEVELS_INTERANNUAL = LEVELS_ANNUAL
COLORS_INTERANNUAL = COLORS_ANNUAL

# Rapport à la normale (%)
LEVELS_RAPPORT = [0, 20, 50, 100, 150, 200, 400]
COLORS_RAPPORT = ["#FFFFFF", '#FFD700', '#90EE90', '#228B22', '#00CED1', '#00008B']

def get_interannual_stats(conn, station_ids, target_annee=2021):
    """Calcule la pluviométrie moyenne annuelle historique par station sur la période [target_annee-20, target_annee]."""
    if not station_ids:
        return pd.DataFrame()
    ids_tuple = tuple(station_ids) if len(station_ids) > 1 else f"('{station_ids[0]}')"
    
    # 1. Déterminer l'année la plus ancienne de la BDD
    min_db_year = 1950
    try:
        q_min = "SELECT MIN(EXTRACT(YEAR FROM date_obs))::int FROM pluies_148;"
        res_min = pd.read_sql(q_min, conn).iloc[0, 0]
        if res_min and not pd.isna(res_min):
            min_db_year = int(res_min)
    except Exception:
        pass
    
    # Règle des 20 ans max jusqu'à target_annee
    start_year = max(min_db_year, target_annee - 20)
    end_year = target_annee

    query = f"""
        WITH yearly AS (
            SELECT id_station,
                   CASE WHEN EXTRACT(MONTH FROM date_obs) >= 9
                        THEN EXTRACT(YEAR FROM date_obs)
                        ELSE EXTRACT(YEAR FROM date_obs) - 1
                   END AS hydro_year,
                   SUM(valeur_mm) AS annual_sum
            FROM pluies_148
            WHERE id_station IN {ids_tuple}
              AND valeur_mm IS NOT NULL
            GROUP BY id_station, hydro_year
        )
        SELECT id_station,
               AVG(annual_sum)      AS mean_annual,
               MIN(hydro_year)::int AS annee_min,
               MAX(hydro_year)::int AS annee_max,
               COUNT(*)             AS nb_years
        FROM yearly
        WHERE hydro_year >= {start_year} AND hydro_year <= {end_year}
        GROUP BY id_station
        HAVING COUNT(*) >= 3
    """
    try:
        return pd.read_sql(query, conn)
    except Exception as e:
        print(f"⚠️ Erreur calcul interannuel : {e}")
        return pd.DataFrame()

def generate_seasonal_subplots_map(df, gdf_pays, gdf_gouv, gdf_gouv_mask, fname='carte_saisons_subplots.png'):
    os.makedirs(IMG_DIR, exist_ok=True)
    fig, axes = plt.subplots(2, 2, figsize=(10, 12))

    bounds = gdf_gouv_mask.total_bounds if gdf_gouv_mask is not None else gdf_pays.total_bounds
    lon_min, lat_min, lon_max, lat_max = bounds
    margin = 15000 if gdf_gouv_mask is not None else 30000

    lon_grid = np.arange(lon_min - margin, lon_max + margin, 3500)
    lat_grid = np.arange(lat_min - margin, lat_max + margin, 3500)
    lon_mesh, lat_mesh = np.meshgrid(lon_grid, lat_grid)

    from shapely.vectorized import contains
    geom_mask = gdf_gouv_mask.geometry.unary_union if gdf_gouv_mask is not None else gdf_pays.geometry.unary_union

    for idx, (col, cfg) in enumerate(SEASONAL_CONFIG.items()):
        ax = axes[idx // 2, idx % 2]
        levels = cfg['levels']
        colors = cfg['colors']
        title  = cfg['title']
        cmap = ListedColormap(colors)
        norm = BoundaryNorm(levels, cmap.N)

        z_mesh = idw_interpolation(df, lon_mesh, lat_mesh, col)
        z_mesh = np.where(contains(geom_mask, lon_mesh, lat_mesh), z_mesh, np.nan)

        if gdf_gouv_mask is not None:
            gdf_gouv_mask.plot(ax=ax, facecolor='none', edgecolor='black', linewidth=1.0, zorder=4)
        else:
            gdf_pays.plot(ax=ax, facecolor='none', edgecolor='black', linewidth=1.0, zorder=4)
            gdf_gouv.plot(ax=ax, facecolor='none', edgecolor='grey', linewidth=0.4, linestyle='--', zorder=3)

        cf = ax.contourf(lon_mesh, lat_mesh, z_mesh, levels=levels, cmap=cmap, norm=norm, alpha=0.75, extend='max', zorder=1)
        contour_levels = [l for l in levels if l > 0]
        if contour_levels:
            cs = ax.contour(lon_mesh, lat_mesh, z_mesh, levels=contour_levels, colors='#2c3e50', linewidths=0.5, zorder=2)
            ax.clabel(cs, inline=True, fontsize=6, fmt='%d mm')

        ax.set_xlim(lon_min - margin, lon_max + margin)
        ax.set_ylim(lat_min - margin, lat_max + margin)
        ax.set_title(title, fontsize=10, fontweight='bold', pad=4)

        formatter_y = ScalarFormatter(useOffset=False)
        formatter_y.set_scientific(False)
        ax.yaxis.set_major_formatter(formatter_y)
        formatter_x = ScalarFormatter(useOffset=False)
        formatter_x.set_scientific(False)
        ax.xaxis.set_major_formatter(formatter_x)
        ax.tick_params(axis='x', rotation=45, labelsize=6)
        ax.tick_params(axis='y', rotation=45, labelsize=6)
        for tick in ax.get_xticklabels() + ax.get_yticklabels():
            tick.set_fontstyle('italic')
        ax.grid(True, linestyle='--', alpha=0.3)

        # Boussole / Rose des vents
        cx, cy, csize = 0.92, 0.88, 0.05
        ax.annotate('N', xy=(cx, cy + csize), xytext=(cx, cy),
                    arrowprops=dict(facecolor='black', edgecolor='black', width=1.0, headwidth=4, headlength=5),
                    ha='center', va='bottom', fontsize=6, fontweight='bold',
                    xycoords='axes fraction', textcoords='axes fraction')
        ax.text(cx, cy - csize * 0.4, 'S', transform=ax.transAxes, ha='center', va='top', fontsize=5, fontweight='bold')
        ax.text(cx + csize * 0.8, cy + csize * 0.3, 'E', transform=ax.transAxes, ha='left', va='center', fontsize=5, fontweight='bold')
        ax.text(cx - csize * 0.8, cy + csize * 0.3, 'O', transform=ax.transAxes, ha='right', va='center', fontsize=5, fontweight='bold')

        legend_elements = [Patch(facecolor=colors[i],
                                 label=f"{levels[i]} – {levels[i+1]} mm" if i < len(levels)-2 else f"> {levels[i]} mm")
                           for i in range(len(levels)-1)]
        ax.legend(handles=legend_elements, title='Pluviométrie (mm)', loc='lower left',
                  fontsize=6, title_fontsize=7, framealpha=1.0, edgecolor='black')

    plt.tight_layout()
    fig.savefig(os.path.join(IMG_DIR, fname), dpi=200, bbox_inches='tight')
    plt.close(fig)


def generate_monthly_subplots_map(df, gdf_pays, gdf_gouv, gdf_gouv_mask, group_months, fname):
    """Génère une figure unique contenant 4 cartes mensuelles sous forme de subplots (grille 2x2)."""
    os.makedirs(IMG_DIR, exist_ok=True)
    fig, axes = plt.subplots(2, 2, figsize=(10, 12))

    bounds = gdf_gouv_mask.total_bounds if gdf_gouv_mask is not None else gdf_pays.total_bounds
    lon_min, lat_min, lon_max, lat_max = bounds
    margin = 15000 if gdf_gouv_mask is not None else 30000

    lon_grid = np.arange(lon_min - margin, lon_max + margin, 3500)
    lat_grid = np.arange(lat_min - margin, lat_max + margin, 3500)
    lon_mesh, lat_mesh = np.meshgrid(lon_grid, lat_grid)

    from shapely.vectorized import contains
    geom_mask = gdf_gouv_mask.geometry.unary_union if gdf_gouv_mask is not None else gdf_pays.geometry.unary_union

    for idx, (m_key, m_name) in enumerate(group_months):
        ax = axes[idx // 2, idx % 2]
        cfg = MONTHLY_CONFIG[m_key]
        levels = cfg['levels']
        colors = cfg['colors']
        cmap = ListedColormap(colors)
        norm = BoundaryNorm(levels, cmap.N)

        z_mesh = idw_interpolation(df, lon_mesh, lat_mesh, m_key)
        z_mesh = np.where(contains(geom_mask, lon_mesh, lat_mesh), z_mesh, np.nan)

        if gdf_gouv_mask is not None:
            gdf_gouv_mask.plot(ax=ax, facecolor='none', edgecolor='black', linewidth=1.0, zorder=4)
        else:
            gdf_pays.plot(ax=ax, facecolor='none', edgecolor='black', linewidth=1.0, zorder=4)
            gdf_gouv.plot(ax=ax, facecolor='none', edgecolor='grey', linewidth=0.4, linestyle='--', zorder=3)

        cf = ax.contourf(lon_mesh, lat_mesh, z_mesh, levels=levels, cmap=cmap, norm=norm, alpha=0.75, extend='max', zorder=1)
        contour_levels = [l for l in levels if l > 0]
        if contour_levels:
            cs = ax.contour(lon_mesh, lat_mesh, z_mesh, levels=contour_levels, colors='#2c3e50', linewidths=0.5, zorder=2)
            ax.clabel(cs, inline=True, fontsize=6, fmt='%d mm')

        ax.set_xlim(lon_min - margin, lon_max + margin)
        ax.set_ylim(lat_min - margin, lat_max + margin)
        ax.set_title(m_name, fontsize=10, fontweight='bold', pad=4)

        formatter_y = ScalarFormatter(useOffset=False)
        formatter_y.set_scientific(False)
        ax.yaxis.set_major_formatter(formatter_y)
        formatter_x = ScalarFormatter(useOffset=False)
        formatter_x.set_scientific(False)
        ax.xaxis.set_major_formatter(formatter_x)
        ax.tick_params(axis='x', rotation=45, labelsize=6)
        ax.tick_params(axis='y', rotation=45, labelsize=6)
        for tick in ax.get_xticklabels() + ax.get_yticklabels():
            tick.set_fontstyle('italic')
        ax.grid(True, linestyle='--', alpha=0.3)

        # Boussole / Rose des vents
        cx, cy, csize = 0.92, 0.88, 0.05
        ax.annotate('N', xy=(cx, cy + csize), xytext=(cx, cy),
                    arrowprops=dict(facecolor='black', edgecolor='black', width=1.0, headwidth=4, headlength=5),
                    ha='center', va='bottom', fontsize=6, fontweight='bold',
                    xycoords='axes fraction', textcoords='axes fraction')
        ax.text(cx, cy - csize * 0.4, 'S', transform=ax.transAxes, ha='center', va='top', fontsize=5, fontweight='bold')
        ax.text(cx + csize * 0.8, cy + csize * 0.3, 'E', transform=ax.transAxes, ha='left', va='center', fontsize=5, fontweight='bold')
        ax.text(cx - csize * 0.8, cy + csize * 0.3, 'O', transform=ax.transAxes, ha='right', va='center', fontsize=5, fontweight='bold')

        legend_elements = [Patch(facecolor=colors[i],
                                 label=f"{levels[i]} – {levels[i+1]} mm" if i < len(levels)-2 else f"> {levels[i]} mm")
                           for i in range(len(levels)-1)]
        ax.legend(handles=legend_elements, title='Pluviométrie (mm)', loc='lower left',
                  fontsize=6, title_fontsize=7, framealpha=1.0, edgecolor='black')

    plt.tight_layout()
    fig.savefig(os.path.join(IMG_DIR, fname), dpi=200, bbox_inches='tight')
    plt.close(fig)


def generate_stations_map(df, gdf_pays, gdf_gouv, gdf_gouv_mask, annee, fname='carte_stations.png'):
    """Génère une carte dédiée montrant uniquement la répartition géographique des stations."""
    os.makedirs(IMG_DIR, exist_ok=True)
    fig, ax = plt.subplots(figsize=(7, 9))
    bounds = gdf_gouv_mask.total_bounds if gdf_gouv_mask is not None else gdf_pays.total_bounds
    lon_min, lat_min, lon_max, lat_max = bounds
    margin = 15000 if gdf_gouv_mask is not None else 30000

    if gdf_gouv_mask is not None:
        gdf_gouv_mask.plot(ax=ax, facecolor='#f0f4f8', edgecolor='black', linewidth=1.5, zorder=2)
    else:
        gdf_pays.plot(ax=ax, facecolor='#f0f4f8', edgecolor='black', linewidth=1.5, zorder=2)
        gdf_gouv.plot(ax=ax, facecolor='none', edgecolor='grey', linewidth=0.5, linestyle='--', zorder=3)
        if gdf_gouv is not None:
            for _, g_row in gdf_gouv.iterrows():
                geom_shape = g_row.get('geom', g_row.get('geometry'))
                cent = geom_shape.centroid
                g_name = g_row.get('lib_fr', g_row.get('nom', ''))
                if g_name:
                    ax.text(cent.x, cent.y, str(g_name), fontsize=5.5, ha='center', va='center',
                            color='#2c3e50', fontweight='bold', alpha=0.7, zorder=6)

    ax.scatter(df['lon'], df['lat'], s=18, color='#c0392b', marker='^', edgecolors='black',
               linewidths=0.4, label=f'Stations ({len(df)})', zorder=5)

    ax.set_xlim(lon_min - margin, lon_max + margin)
    ax.set_ylim(lat_min - margin, lat_max + margin)
    ax.set_title(f'Répartition des Stations Pluviométriques — {annee}-{annee+1}',
                 fontsize=11, fontweight='bold', pad=10)
    ax.set_xlabel('X (UTM Zone 32N, m)', fontsize=9, fontweight='bold', fontstyle='italic')
    ax.set_ylabel('Y (UTM Zone 32N, m)', fontsize=9, fontweight='bold', fontstyle='italic')

    formatter_y = ScalarFormatter(useOffset=False)
    formatter_y.set_scientific(False)
    ax.yaxis.set_major_formatter(formatter_y)
    formatter_x = ScalarFormatter(useOffset=False)
    formatter_x.set_scientific(False)
    ax.xaxis.set_major_formatter(formatter_x)

    ax.tick_params(axis='x', rotation=45, labelsize=8)
    ax.tick_params(axis='y', rotation=45, labelsize=8)
    ax.grid(True, linestyle='--', alpha=0.3)

    cx, cy, csize = 0.92, 0.88, 0.05
    ax.annotate('N', xy=(cx, cy + csize), xytext=(cx, cy),
                arrowprops=dict(facecolor='black', edgecolor='black', width=1.5, headwidth=6, headlength=7),
                ha='center', va='bottom', fontsize=8, fontweight='bold',
                xycoords='axes fraction', textcoords='axes fraction')
    ax.text(cx, cy - csize * 0.4, 'S', transform=ax.transAxes, ha='center', va='top', fontsize=7, fontweight='bold')
    ax.text(cx + csize * 0.8, cy + csize * 0.3, 'E', transform=ax.transAxes, ha='left', va='center', fontsize=7, fontweight='bold')
    ax.text(cx - csize * 0.8, cy + csize * 0.3, 'O', transform=ax.transAxes, ha='right', va='center', fontsize=7, fontweight='bold')

    ax.legend(loc='lower left', fontsize=9, framealpha=1.0, edgecolor='black')
    plt.tight_layout()
    fig.savefig(os.path.join(IMG_DIR, fname), dpi=200, bbox_inches='tight')
    plt.close(fig)

def generate_report_figures(stats, gdf_pays, gdf_gouv, gdf_gouv_mask, gouv, annee, conn, station_ids):
    df = stats['pivot']
    
    # 1. Carte annuelle
    generate_isohyet_map(df, gdf_pays, gdf_gouv, gdf_gouv_mask, 'total', f'Isohyètes Annuelles {annee}-{annee+1}', 'carte_annuelle.png',
                         LEVELS_ANNUAL, COLORS_ANNUAL)

    # 1b. Cartes mensuelles groupées par 4 sous forme de subplots (Sept-Déc, Jan-Avr, Mai-Août)
    group1 = [('sept', 'Septembre'), ('octo', 'Octobre'), ('nove', 'Novembre'), ('dece', 'Décembre')]
    group2 = [('janv', 'Janvier'), ('fev', 'Février'), ('mar', 'Mars'), ('avr', 'Avril')]
    group3 = [('mai', 'Mai'), ('juin', 'Juin'), ('juil', 'Juillet'), ('aout', 'Août')]
    
    generate_monthly_subplots_map(df, gdf_pays, gdf_gouv, gdf_gouv_mask, group1, 'carte_mensuelle_group1.png')
    generate_monthly_subplots_map(df, gdf_pays, gdf_gouv, gdf_gouv_mask, group2, 'carte_mensuelle_group2.png')
    generate_monthly_subplots_map(df, gdf_pays, gdf_gouv, gdf_gouv_mask, group3, 'carte_mensuelle_group3.png')
        
    # 1c. Carte saisonnière (une seule figure avec 4 subplots)
    generate_seasonal_subplots_map(df, gdf_pays, gdf_gouv, gdf_gouv_mask, 'carte_saisons_subplots.png')
    
    # 2. Histogramme Mensuel
    fig, ax = plt.subplots(figsize=(8, 4))
    mois_labels = ['Sep', 'Oct', 'Nov', 'Déc', 'Jan', 'Fév', 'Mar', 'Avr', 'Mai', 'Juin', 'Juil', 'Août']
    ax.bar(mois_labels, stats['moyenne_mensuelle'].values, color='#2980b9', edgecolor='#2c3e50', alpha=0.85, width=0.6)
    ax.axhline(stats['ref_moy'], color='#e74c3c', linestyle='--', linewidth=1.2, label=f"Moyenne de référence ({stats['ref_moy']:.1f} mm)")
    ax.set_ylabel('Précipitations (mm)', fontsize=10)
    ax.set_title('Distribution Mensuelle des Précipitations', fontsize=12, fontweight='bold')
    ax.grid(axis='y', linestyle=':', alpha=0.6)
    ax.legend(fontsize=9)
    plt.tight_layout()
    fig.savefig(os.path.join(IMG_DIR, 'hist_mensuel.png'), dpi=200)
    plt.close(fig)
    
    # 3. Diagramme Secteur Saisons
    fig, ax = plt.subplots(figsize=(5, 5))
    labels = list(stats['saisons'].keys())
    values = list(stats['saisons'].values())
    if sum(values) > 0:
        ax.pie(values, labels=labels, autopct='%1.1f%%', startangle=90, colors=['#f39c12', '#3498db', '#2ecc71', '#e74c3c'], textprops={'fontsize': 10})
    else:
        ax.text(0.5, 0.5, 'Pas de données', ha='center', va='center')
    ax.set_title('Répartition Saisonnière', fontsize=12, fontweight='bold')
    plt.tight_layout()
    fig.savefig(os.path.join(IMG_DIR, 'pie_saisons.png'), dpi=200)
    plt.close(fig)

    # 4. Figure Répartition par classe de pluviométrie
    generate_rainfall_class_figure(conn, station_ids, annee, df)

    # 5. Carte des stations (nouvelle carte dédiée)
    generate_stations_map(df, gdf_pays, gdf_gouv, gdf_gouv_mask, annee, 'carte_stations.png')

    # 6. Cartes interannuelles + Rapport à la Normale
    print("📊 Calcul des statistiques interannuelles (période glissante de 20 ans)...")
    df_inter = get_interannual_stats(conn, station_ids, target_annee=annee)
    if not df_inter.empty:
        df_coords = df[['lon', 'lat']].reset_index()
        df_coords.columns = ['id_station', 'lon', 'lat']
        df_inter_map = df_inter.merge(df_coords, on='id_station', how='inner')
        annee_min_hist = int(df_inter_map['annee_min'].min())
        annee_max_hist = int(df_inter_map['annee_max'].max())
        generate_isohyet_map(
            df_inter_map, gdf_pays, gdf_gouv, gdf_gouv_mask,
            'mean_annual',
            f'Isohyètes Interannuelles ({annee_min_hist}–{annee_max_hist})',
            'carte_interannuelle.png',
            LEVELS_INTERANNUAL, COLORS_INTERANNUAL
        )
        # Rapport à la Normale
        df_curr = df[['lon', 'lat', 'total']].reset_index()
        df_curr.columns = ['id_station', 'lon', 'lat', 'total']
        df_rapport = df_inter.merge(df_curr, on='id_station', how='inner')
        df_rapport['ratio_pct'] = (df_rapport['total'] / df_rapport['mean_annual'].replace(0, np.nan)) * 100
        df_rapport['ratio_pct'] = df_rapport['ratio_pct'].clip(lower=0).fillna(0)
        generate_isohyet_map(
            df_rapport, gdf_pays, gdf_gouv, gdf_gouv_mask,
            'ratio_pct',
            f'Rapport à la Normale — {annee}–{annee+1} (%)',
            'carte_rapport_normale.png',
            LEVELS_RAPPORT, COLORS_RAPPORT
        )
    else:
        print("⚠️ Données historiques insuffisantes pour les cartes interannuelles.")

    # 7. Tunisie du Nord, Centrale et du Sud bar charts
    REGIONS_ZONES = {
        'Tunisie du Nord': ['tunis', 'ariana', 'ben arous', 'manouba', 'nabeul', 'zaghouan', 'bizerte', 'jendouba', 'beja', 'le kef', 'kef', 'siliana'],
        'Tunisie Centrale': ['sousse', 'monastir', 'mahdia', 'sfax', 'kairouan', 'kassrine', 'kasserine', 'sidi bouzid'],
        'Tunisie du Sud': ['gafsa', 'tozeur', 'kebili', 'kebeli', 'gabes', 'tatouine', 'tataouine', 'mednine', 'medenine']
    }
    
    q_y_zone = "SELECT code::text AS id_station, station AS nom_station, moy_ AS total_moy FROM yasra_data;"
    df_y_zone = pd.read_sql(q_y_zone, conn)
    
    df_st_zone = pd.read_sql("SELECT id_station, gouvernorat, nom FROM station_148;", conn)
    df_st_zone['norm_gouv'] = df_st_zone['gouvernorat'].apply(normalize_string)
    
    df_pn_zone = df_st_zone.merge(df[['total']].reset_index(), on='id_station', how='left').fillna(0)
    df_pn_zone = df_pn_zone.merge(df_y_zone, on='id_station', how='left').fillna(0)
    df_pn_zone.rename(columns={'total': 'total_obs'}, inplace=True)
    
    for zone_name, gouvs in REGIONS_ZONES.items():
        sub_z = df_pn_zone[df_pn_zone['norm_gouv'].isin(gouvs)].copy()
        if sub_z.empty:
            continue
        sub_z = sub_z.sort_values(by='nom')
        
        fig, ax = plt.subplots(figsize=(15, 6))
        x_indices = np.arange(len(sub_z))
        width = 0.35
        
        ax.bar(x_indices - width/2, sub_z['total_obs'], width, label=f'Pluviométrie {annee}-{annee+1}', color='#e74c3c', edgecolor='black', linewidth=0.5)
        ax.bar(x_indices + width/2, sub_z['total_moy'], width, label='Moyenne interannuelle', color='#3498db', edgecolor='black', linewidth=0.5)
        
        ax.set_title(f"{zone_name} : Pluviométrie annuelle {annee}-{annee+1} par station, comparée à la moyenne interannuelle", fontsize=12, fontweight='bold')
        ax.set_ylabel('Précipitations (mm)', fontsize=10, fontweight='bold')
        ax.set_xticks(x_indices)
        ax.set_xticklabels(sub_z['nom'], rotation=90, fontsize=7)
        ax.legend(fontsize=9)
        ax.grid(axis='y', linestyle='--', alpha=0.5)
        
        plt.tight_layout()
        fname = f"comparaison_{zone_name.split()[-1].lower()}.png"
        fig.savefig(os.path.join(IMG_DIR, fname), dpi=200, bbox_inches='tight')
        plt.close(fig)

# ------------------------- 4. Tableaux journaliers en LaTeX -------------------------
def generer_tableaux_journaliers_latex(conn, station_ids, annee, station_names):
    if not station_ids: 
        return ""
    
    mois_order = [9, 10, 11, 12, 1, 2, 3, 4, 5, 6, 7, 8]
    mois_labels = ['Sep', 'Oct', 'Nov', 'Déc', 'Jan', 'Fév', 'Mar', 'Avr', 'Mai', 'Jun', 'Jul', 'Aoû']
    mois_num_map = dict(zip(mois_labels, mois_order))  # label -> numéro de mois
    all_tables = []
    station_counter = 0

    # Nombre de jours par mois pour l'année hydrologique
    mois_year_map = {9: annee, 10: annee, 11: annee, 12: annee,
                     1: annee+1, 2: annee+1, 3: annee+1, 4: annee+1,
                     5: annee+1, 6: annee+1, 7: annee+1, 8: annee+1}
    days_in_month = {m: calendar.monthrange(mois_year_map[m], m)[1] for m in mois_order}

    for sid in station_ids:
        df = get_daily_data_for_station(conn, sid, annee)
        if df is None or df.empty: 
            continue
        
        station_counter += 1
        
        # Conversion en int pour éviter les floats d'EXTRACT
        df['jour'] = df['jour'].astype(int)
        df['mois'] = df['mois'].astype(int)
        
        # Agrégation et pivot
        df = df.groupby(['jour', 'mois'])['valeur'].sum().reset_index()
        pivot = df.pivot_table(index='jour', columns='mois', values='valeur', aggfunc='sum').fillna(0)
        pivot = pd.DataFrame(index=range(1, 32)).join(pivot).fillna(0).reindex(columns=mois_order)
        pivot.columns = mois_labels
        
        # Calcul des totaux mensuels (uniquement jours existants)
        totals = {}
        for m_label in mois_labels:
            m_num = mois_num_map[m_label]
            max_day = days_in_month[m_num]
            totals[m_label] = pivot.loc[1:max_day, m_label].sum()
        total_annuel = sum(totals.values())
        
        # Calcul du maximum journalier et sa date
        max_val = 0
        max_jour = 1
        max_mois_num = 9
        for m_label in mois_labels:
            m_num = mois_num_map[m_label]
            max_day = days_in_month[m_num]
            for j in range(1, max_day + 1):
                v = pivot.loc[j, m_label]
                if v > max_val:
                    max_val = v
                    max_jour = j
                    max_mois_num = m_num
        
        # Comptage des jours de pluie
        nb_gt0, nb_ge05, nb_ge10 = 0, 0, 0
        for m_label in mois_labels:
            m_num = mois_num_map[m_label]
            max_day = days_in_month[m_num]
            for j in range(1, max_day + 1):
                v = pivot.loc[j, m_label]
                if v > 0:
                    nb_gt0 += 1
                if v >= 0.5:
                    nb_ge05 += 1
                if v >= 10:
                    nb_ge10 += 1
        
        st_nom = escape_latex(station_names.get(sid, sid))
        
        # Fonction pour formater une valeur avec virgule comme séparateur décimal
        def fmt_val(v):
            if pd.isna(v):
                return "-"
            if v == int(v):
                return str(int(v))
            return f"{v:.1f}".replace('.', ',')
        
        # En-tête de la station : N. NOM_STATION (CODE)
        code = f"\\textbf{{{station_counter}. {st_nom} ({sid})}} \\\\[2pt]\n"
        
        # Tableau à 13 colonnes (1 jour + 12 mois)
        code += "\\begin{tabular}{|c|" + "c|"*12 + "}\n\\hline\n"
        code += "\\hdr{Jour} & " + " & ".join([f"\\hdr{{{m}}}" for m in mois_labels]) + " \\\\ \\hline\n"
        
        # Lignes journalières (1 à 31)
        for jour in range(1, 32):
            vals = []
            for m_label in mois_labels:
                m_num = mois_num_map[m_label]
                max_day = days_in_month[m_num]
                if jour > max_day:
                    vals.append(" ")  # Jour inexistant (ex: 31 fév)
                else:
                    v = pivot.loc[jour, m_label]
                    vals.append("-" if (pd.isna(v) or v == 0) else fmt_val(v))
            code += f"{jour} & " + " & ".join(vals) + " \\\\ \\hline\n"
            
        # Ligne de total mensuel
        tot_cells = [f"\\textbf{{{fmt_val(totals[m])}}}" for m in mois_labels]
        code += "\\textbf{Tot} & " + " & ".join(tot_cells) + " \\\\ \\hline\n"
        
        # Ligne Tot. Annuel + Maxi
        maxi_date = f"{max_jour:02d}/{max_mois_num:02d}"
        code += f"\\multicolumn{{13}}{{|l|}}{{\\textbf{{Tot. Annuel :}} {fmt_val(total_annuel)} mm \\quad | \\quad \\textbf{{Maxi :}} {fmt_val(max_val)} mm le {maxi_date}}} \\\\ \\hline\n"
        
        # Ligne Pluies
        code += f"\\multicolumn{{13}}{{|l|}}{{\\textbf{{Pluies :}} {nb_gt0} ($>0$\\,mm) \\ / \\ {nb_ge05} ($\\ge0,5$\\,mm) \\ / \\ {nb_ge10} ($\\ge10$\\,mm)}} \\\\ \\hline\n"
        
        code += "\\end{tabular}\n"
        
        all_tables.append(code)

    if not all_tables:
        return ""

    # Organisation en grille 3x2 par page (6 tableaux par page)
    latex_final = ""
    for chunk_idx in range(0, len(all_tables), 6):
        chunk = all_tables[chunk_idx:chunk_idx+6]
        
        # Ligne 1 : Table 1 & Table 2
        latex_final += "\\begin{minipage}[t]{0.49\\textwidth}\n\\centering\n" + chunk[0] + "\\end{minipage}\n"
        if len(chunk) > 1:
            latex_final += "\\hfill\n\\begin{minipage}[t]{0.49\\textwidth}\n\\centering\n" + chunk[1] + "\\end{minipage}\n"
        latex_final += "\\vspace{0.3cm}\n\n"
        
        # Ligne 2 : Table 3 & Table 4
        if len(chunk) > 2:
            latex_final += "\\begin{minipage}[t]{0.49\\textwidth}\n\\centering\n" + chunk[2] + "\\end{minipage}\n"
            if len(chunk) > 3:
                latex_final += "\\hfill\n\\begin{minipage}[t]{0.49\\textwidth}\n\\centering\n" + chunk[3] + "\\end{minipage}\n"
            latex_final += "\\vspace{0.3cm}\n\n"
            
        # Ligne 3 : Table 5 & Table 6
        if len(chunk) > 4:
            latex_final += "\\begin{minipage}[t]{0.49\\textwidth}\n\\centering\n" + chunk[4] + "\\end{minipage}\n"
            if len(chunk) > 5:
                latex_final += "\\hfill\n\\begin{minipage}[t]{0.49\\textwidth}\n\\centering\n" + chunk[5] + "\\end{minipage}\n"
            latex_final += "\\vspace{0.3cm}\n\n"
            
        # N'ajoute \clearpage que si ce n'est pas le tout dernier paquet
        if chunk_idx + 6 < len(all_tables):
            latex_final += "\\clearpage\n"
            
    return latex_final

def generate_regional_comparison_chart(df_hist_8, df_curr_yasra, avail_years, annee, fname='comparaison_regionales.png', gouv='all'):
    """Génère le graphique à barres comparant la pluviométrie des 8 dernières années."""
    if df_hist_8.empty or not avail_years:
        print("⚠️ Pas de données disponibles pour la comparaison des 8 dernières années.")
        return

    is_nat = (gouv.lower() in ('all', 'national'))
    df_hist_8 = df_hist_8.copy()
    df_hist_8['norm_gouv'] = df_hist_8['gouvernorat'].apply(normalize_string)
    df_curr_yasra = df_curr_yasra.copy()
    df_curr_yasra['norm_gouv'] = df_curr_yasra['gouvernorat'].apply(normalize_string)

    if is_nat:
        REGIONS_DEF = {
            'NORD OUEST': {'surf': 16517, 'gouvs': ['jendouba', 'beja', 'le kef', 'kef', 'siliana']},
            'NORD EST': {'surf': 11725, 'gouvs': ['tunis', 'ariana', 'ben arous', 'manouba', 'nabeul', 'zaghouan', 'bizerte']},
            'CENTRE OUEST': {'surf': 22184, 'gouvs': ['kairouan', 'kassrine', 'kasserine', 'sidi bouzid']},
            'CENTRE EST': {'surf': 13430, 'gouvs': ['sousse', 'monastir', 'mahdia', 'sfax']},
            'SUD OUEST': {'surf': 35761, 'gouvs': ['gafsa', 'tozeur', 'kebili', 'kebeli']},
            'SUD EST': {'surf': 55305, 'gouvs': ['gabes', 'tatouine', 'tataouine', 'mednine', 'medenine']}
        }
        regions = list(REGIONS_DEF.keys())
        data_dict = {r: {} for r in regions}
        for reg_name, reg_info in REGIONS_DEF.items():
            sub_h = df_hist_8[df_hist_8['norm_gouv'].isin(reg_info['gouvs'])]
            sub_st = df_curr_yasra[df_curr_yasra['norm_gouv'].isin(reg_info['gouvs'])]
            reg_moy = sub_st['moy_'].mean() if not sub_st.empty else 0
            data_dict[reg_name]['Moyenne'] = reg_moy
            for y in avail_years:
                v_y = sub_h[sub_h['hydro_year'] == y]['annual_sum'].mean()
                data_dict[reg_name][y] = v_y
    else:
        target_g_norm = normalize_string(gouv)
        sub_curr_g = df_curr_yasra[df_curr_yasra['norm_gouv'] == target_g_norm]
        st_names = sub_curr_g['station'].tolist()
        regions = [s[:14] for s in st_names]
        data_dict = {r: {} for r in regions}
        for idx, srow in sub_curr_g.iterrows():
            st_key = srow['station'][:14]
            sid = srow['id_station']
            data_dict[st_key]['Moyenne'] = srow['moy_'] if pd.notna(srow['moy_']) else 0
            sub_h = df_hist_8[df_hist_8['id_station'] == sid]
            for y in avail_years:
                v_y = sub_h[sub_h['hydro_year'] == y]['annual_sum'].mean() if not sub_h[sub_h['hydro_year'] == y].empty else 0
                data_dict[st_key][y] = v_y

    fig, ax = plt.subplots(figsize=(10, 6.5))

    color_map = {
        'Moyenne': '#0000FF',
        -7: '#E2F7DF',
        -6: '#00FF00',
        -5: '#006600',
        -4: '#CCFFFF',
        -3: '#00BFFF',
        -2: '#99CC66',
        -1: '#DDBBBB',
        0: '#FF0000',
    }

    num_bars = 1 + len(avail_years)
    bar_width = 0.85 / num_bars
    indices = np.arange(len(regions))

    # 1. Plot Moyenne
    moy_vals = [data_dict[r].get('Moyenne', 0) for r in regions]
    ax.bar(indices - 0.425 + 0.5 * bar_width, moy_vals, bar_width, label='Moyenne',
           color=color_map['Moyenne'], edgecolor='black', linewidth=0.6)

    # 2. Plot available years
    for idx, y in enumerate(avail_years):
        offset = y - annee
        color = color_map.get(offset, '#888888')
        label = f"{y}-{str(y+1)[2:]}"
        vals = [data_dict[r].get(y, 0) for r in regions]
        
        pos = indices - 0.425 + (idx + 1.5) * bar_width
        ax.bar(pos, vals, bar_width, label=label,
               color=color, edgecolor='black', linewidth=0.6)

    ax.set_ylabel('Pluie en (mm)', fontsize=11, fontweight='bold')
    ax.set_xticks(indices)
    ax.set_xticklabels(regions, fontsize=9, fontweight='bold', rotation=15 if not is_nat else 0)

    ax.set_ylim(0, 900)
    ax.set_yticks(np.arange(0, 901, 100))
    ax.set_yticks(np.arange(0, 901, 20), minor=True)
    ax.grid(axis='y', which='major', color='black', linestyle='-', linewidth=0.6)
    ax.grid(axis='y', which='minor', color='grey', linestyle='-', linewidth=0.2)
    ax.set_axisbelow(True)

    ax.legend(loc='upper center', bbox_to_anchor=(0.5, -0.10 if not is_nat else -0.08), ncol=min(num_bars, 9),
              frameon=True, edgecolor='black', fancybox=False, fontsize=8)

    os.makedirs(IMG_DIR, exist_ok=True)
    fig.savefig(os.path.join(IMG_DIR, fname), dpi=200, bbox_inches='tight')
    plt.close(fig)

def generate_section_13_mensuel(conn, annee, gouv='all'):
    """Génère la section 1.3. Pluies mensuelles (texte introductif dynamique, Tableau 3 et Figure 2)."""
    is_nat = (gouv.lower() in ('all', 'national'))
    clean_g = escape_latex(gouv.strip().capitalize()) if not is_nat else "National"

    REGIONS_DEF = {
        'NORD OUEST': {'surf': 16517, 'gouvs': ['jendouba', 'beja', 'le kef', 'kef', 'siliana']},
        'NORD EST': {'surf': 11725, 'gouvs': ['tunis', 'ariana', 'ben arous', 'manouba', 'nabeul', 'zaghouan', 'bizerte']},
        'CENTRE OUEST': {'surf': 22184, 'gouvs': ['kairouan', 'kassrine', 'kasserine', 'sidi bouzid']},
        'CENTRE EST': {'surf': 13430, 'gouvs': ['sousse', 'monastir', 'mahdia', 'sfax']},
        'SUD OUEST': {'surf': 35761, 'gouvs': ['gafsa', 'tozeur', 'kebili', 'kebeli']},
        'SUD EST': {'surf': 55305, 'gouvs': ['gabes', 'tatouine', 'tataouine', 'mednine', 'medenine']}
    }

    mois_keys = ['sept', 'octo', 'nove', 'dece', 'janv', 'fev', 'mar', 'avr', 'mai', 'juin', 'juil', 'aout']
    mois_fr = ['Septembre', 'Octobre', 'Novembre', 'Décembre', 'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin', 'Juillet', 'Août']
    mois_short = ['Sept', 'Oct', 'Nov', 'Déc', 'Jan', 'Fév', 'Mar', 'Avr', 'Mai', 'Juin', 'Juil', 'Août']
    mois_caps = ['SEPTEMBRE', 'OCTOBRE', 'NOVEMBRE', 'DECEMBRE', 'JANVIER', 'FEVRIER', 'MARS', 'AVRIL', 'MAI', 'JUIN', 'JUILLET', 'AOUT']

    date_debut, date_fin = f"{annee}-09-01 00:00:00", f"{annee+1}-08-31 23:59:59"
    q = f"""
        WITH cleaned AS (
            SELECT DISTINCT ON (id_station, date_obs::date)
                id_station,
                EXTRACT(MONTH FROM date_obs)::int AS m,
                valeur_mm
            FROM pluies_148
            WHERE date_obs >= '{date_debut}' AND date_obs <= '{date_fin}' AND valeur_mm IS NOT NULL
        ),
        monthly AS (
            SELECT id_station, m, SUM(valeur_mm) AS sum_m
            FROM cleaned
            GROUP BY id_station, m
        )
        SELECT s.id_station, s.gouvernorat, m.m, m.sum_m
        FROM monthly m
        JOIN station_148 s ON s.id_station = m.id_station;
    """
    df_m = pd.read_sql(q, conn)
    df_m['norm_gouv'] = df_m['gouvernorat'].apply(normalize_string)

    month_num_to_key = {9:'sept', 10:'octo', 11:'nove', 12:'dece', 1:'janv', 2:'fev', 3:'mar', 4:'avr', 5:'mai', 6:'juin', 7:'juil', 8:'aout'}
    df_m['m_key'] = df_m['m'].map(month_num_to_key)
    pivot_pluie = df_m.pivot(index='id_station', columns='m_key', values='sum_m').fillna(0)

    q_y = "SELECT code::text AS id_station, sept, octo, nove, dece, janv, fev, mar, avr, mai, juin, juil, aout FROM yasra_data;"
    df_y = pd.read_sql(q_y, conn).set_index('id_station')

    df_st = pd.read_sql("SELECT id_station, gouvernorat, nom, lon, lat FROM station_148;", conn)
    df_st['norm_gouv'] = df_st['gouvernorat'].apply(normalize_string)

    if not is_nat:
        target_g_norm = normalize_string(gouv)
        df_st = df_st[df_st['norm_gouv'] == target_g_norm]

    # Clean coordinates for Thiessen
    bad_coords_mask = (df_st['norm_gouv'].isin(['manouba', 'tunis', 'ariana', 'ben arous', 'bizerte', 'beja', 'jandouba'])) & (df_st['lat'] < 3800000)
    df_st_clean = df_st[~bad_coords_mask]

    thiessen = get_thiessen_weights(conn, df_st_clean)

    if is_nat:
        results = {r: {} for r in REGIONS_DEF.keys()}
        tot_surf = sum(r['surf'] for r in REGIONS_DEF.values())

        for m in mois_keys:
            st_p = df_st.merge(pivot_pluie[[m]], on='id_station', how='left').fillna(0).rename(columns={m: 'pluie'}) if m in pivot_pluie.columns else df_st.assign(pluie=0)
            st_n = df_st.merge(df_y[[m]], on='id_station', how='left').fillna(0).rename(columns={m: 'norm'}) if m in df_y.columns else df_st.assign(norm=0)
            st_pn = st_p.merge(st_n[['id_station', 'norm']], on='id_station')
            
            for reg_name in REGIONS_DEF.keys():
                reg_weights = thiessen['regional'].get(reg_name, {})
                reg_p = compute_weighted_avg(st_pn, 'pluie', reg_weights)
                reg_n = compute_weighted_avg(st_pn, 'norm', reg_weights)
                reg_r = (reg_p / reg_n * 100) if reg_n > 0 else 0
                results[reg_name][m] = {'pluie': reg_p, 'norm': reg_n, 'rapp': reg_r}

        results['TUNISIE'] = {}
        for m in mois_keys:
            weighted_p = sum(results[r][m]['pluie'] * REGIONS_DEF[r]['surf'] for r in REGIONS_DEF) / tot_surf
            weighted_n = sum(results[r][m]['norm'] * REGIONS_DEF[r]['surf'] for r in REGIONS_DEF) / tot_surf
            weighted_r = (weighted_p / weighted_n * 100) if weighted_n > 0 else 0
            results['TUNISIE'][m] = {'pluie': weighted_p, 'norm': weighted_n, 'rapp': weighted_r}

        for r in list(REGIONS_DEF.keys()) + ['TUNISIE']:
            tot_p = sum(results[r][m]['pluie'] for m in mois_keys)
            tot_n = sum(results[r][m]['norm'] for m in mois_keys)
            tot_r = (tot_p / tot_n * 100) if tot_n > 0 else 0
            results[r]['total'] = {'pluie': tot_p, 'norm': tot_n, 'rapp': tot_r}
    else:
        st_names = df_st['nom'].tolist()
        results = {s[:15]: {} for s in st_names}
        for m in mois_keys:
            st_p = df_st.merge(pivot_pluie[[m]], on='id_station', how='left').fillna(0).rename(columns={m: 'pluie'}) if m in pivot_pluie.columns else df_st.assign(pluie=0)
            st_n = df_st.merge(df_y[[m]], on='id_station', how='left').fillna(0).rename(columns={m: 'norm'}) if m in df_y.columns else df_st.assign(norm=0)
            st_pn = st_p.merge(st_n[['id_station', 'norm']], on='id_station')
            for _, row in st_pn.iterrows():
                sk = row['nom'][:15]
                rp = row['pluie']
                rn = row['norm']
                rr = (rp / rn * 100) if rn > 0 else 0
                results[sk][m] = {'pluie': rp, 'norm': rn, 'rapp': rr}
        
        results[f'GOUVERNORAT DE {clean_g.upper()}'] = {}
        for m in mois_keys:
            gp = np.mean([results[s[:15]][m]['pluie'] for s in st_names]) if st_names else 0
            gn = np.mean([results[s[:15]][m]['norm'] for s in st_names]) if st_names else 0
            gr = (gp / gn * 100) if gn > 0 else 0
            results[f'GOUVERNORAT DE {clean_g.upper()}'][m] = {'pluie': gp, 'norm': gn, 'rapp': gr}

        for r in list(results.keys()):
            tot_p = sum(results[r][m]['pluie'] for m in mois_keys)
            tot_n = sum(results[r][m]['norm'] for m in mois_keys)
            tot_r = (tot_p / tot_n * 100) if tot_n > 0 else 0
            results[r]['total'] = {'pluie': tot_p, 'norm': tot_n, 'rapp': tot_r}

    # Dynamic intro text
    summary_key = 'TUNISIE' if is_nat else f'GOUVERNORAT DE {clean_g.upper()}'
    excedents = []
    deficits = []
    for idx, m in enumerate(mois_keys):
        r_val = results[summary_key][m]['rapp']
        m_name = mois_fr[idx]
        if r_val >= 100:
            excedents.append((m_name, r_val - 100))
        else:
            deficits.append((m_name, 100 - r_val))

    if excedents:
        ex_list_str = ", ".join([e[0] for e in excedents])
        min_ex = min(excedents, key=lambda x: x[1])
        max_ex = max(excedents, key=lambda x: x[1])
        ex_text = f"les mois : {ex_list_str} sont excédentaires ; les excédents varient entre {min_ex[1]:.0f}\\% au mois de {min_ex[0]} et {max_ex[1]:.0f}\\% au mois d'{max_ex[0]}"
    else:
        ex_text = "aucun mois n'est excédentaire"

    if deficits:
        min_def = min(deficits, key=lambda x: x[1])
        max_def = max(deficits, key=lambda x: x[1])
        def_text = f"pour le reste de l’année, les déficits varient entre {min_def[1]:.0f}\\% au mois de {min_def[0]} et {max_def[1]:.0f}\\% au mois de {max_def[0]}"
    else:
        def_text = "aucun déficit n'a été enregistré pour le reste de l'année"

    loc_str = "du pays" if is_nat else f"du Gouvernorat de {clean_g}"
    intro_para = f"La distribution mensuelle des pluies {loc_str}, synthétisée dans le tableau suivant montre que {ex_text} , {def_text}."

    # Tableau 3
    t3_groups = [
        ('1/3 : Septembre à Décembre', ['sept', 'octo', 'nove', 'dece']),
        ('2/3 : Janvier à Avril', ['janv', 'fev', 'mar', 'avr']),
        ('3/3 : Mai à Août', ['mai', 'juin', 'juil', 'aout'])
    ]

    t3_latex = ""
    target_keys = list(REGIONS_DEF.keys()) + ['TUNISIE'] if is_nat else list(results.keys())

    for g_idx, (g_title, g_months) in enumerate(t3_groups):
        hdr1_cols = [f"\\multicolumn{{3}}{{|c|}}{{\\textbf{{{mois_caps[mois_keys.index(m)]}}}}}" for m in g_months]
        hdr1 = "\\textbf{SUPERFICIE} & \\textbf{RÉGION}" if is_nat else "\\textbf{CODE/STATION} & \\textbf{NOM}"
        hdr1 += " & " + " & ".join(hdr1_cols) + " \\\\"
        
        hdr2 = " & " + " & ".join(["\\textbf{Pluie} & \\textbf{NORM.} & \\textbf{Rapp}" for _ in g_months]) + " \\\\"
        hdr3 = " & " + " & ".join(["\\textbf{(mm)} & \\textbf{(mm)} & \\textbf{(\\%)}" for _ in g_months]) + " \\\\"
        
        rows_tex = ""
        for reg in target_keys:
            if is_nat:
                surf_str = str(REGIONS_DEF[reg]['surf']) if reg in REGIONS_DEF else str(sum(r['surf'] for r in REGIONS_DEF.values()))
                surf_display = f"\\textbf{{{surf_str}}}" if reg == 'TUNISIE' else surf_str
                reg_display = f"\\textbf{{{reg}}}" if reg == 'TUNISIE' else reg
            else:
                surf_display = "-"
                reg_display = f"\\textbf{{{escape_latex(reg)}}}" if 'GOUVERNORAT' in reg else escape_latex(reg)

            vals = []
            for m in g_months:
                p = results[reg][m]['pluie']
                n = results[reg][m]['norm']
                r = results[reg][m]['rapp']
                p_str = f"{p:.1f}".replace('.', ',')
                n_str = f"{n:.1f}".replace('.', ',')
                r_str = f"{r:.0f}\\%"
                if reg == summary_key:
                    p_str, n_str, r_str = f"\\textbf{{{p_str}}}", f"\\textbf{{{n_str}}}", f"\\textbf{{{r_str}}}"
                vals.extend([p_str, n_str, r_str])
            
            rows_tex += f"{surf_display} & {reg_display} & " + " & ".join(vals) + " \\\\\n\\hline\n"
        
        tab_caption = f"Pluies mensuelles {annee}-{annee+1} pour le Gouvernorat de {clean_g}" if not is_nat else f"Pluies mensuelles {annee}-{annee+1} dans les régions naturelles"
        t3_latex += f"""
\\begin{{table}}[H]
\\centering
\\caption{{{tab_caption} ({g_idx+1}/3)}}
\\vspace{{0.1cm}}
\\fontsize{{6}}{{7.5}}\\selectfont
\\begin{{tabular}}{{|c|l|""" + ("c|c|c|" * 4) + f"""}}
\\hline
{hdr1}
{hdr2}
{hdr3} \\hline
{rows_tex}\\end{{tabular}}
\\end{{table}}
"""

    t3_notes = r"""
\noindent{\footnotesize \textit{Pluie en mm = pluie mensuelle par station/région du mois en cours}} \\
\noindent{\footnotesize \textit{NORM. (mm) = NORM. de la pluie mensuelle par station/région du mois en cours}} \\
\noindent{\footnotesize \textit{Rapp (\%) = (pluie mensuelle/NORM. mensuelle)}}
\vspace{0.3cm}
"""

    def get_color_cell(rapp):
        if rapp < 50:
            return r"\cellcolor{clsred}"
        elif rapp < 75:
            return r"\cellcolor{clsorange}"
        elif rapp < 100:
            return r"\cellcolor{clsyellow}"
        else:
            return r"\cellcolor{clsgreen}"

    fig2_hdr = "\\textbf{STATIONS/REGIONS} & " + " & ".join([f"\\textbf{{{m}}}" for m in mois_short]) + " & \\textbf{TOT} \\\\"

    fig2_rows = ""
    for reg in target_keys:
        reg_disp = f"\\textbf{{{escape_latex(reg)}}}" if reg == summary_key else escape_latex(reg)
        row_cells = []
        for m in mois_keys:
            r = results[reg][m]['rapp']
            cell_color = get_color_cell(r)
            row_cells.append(f"{cell_color}{r:.0f}\\%")
        tot_r = results[reg]['total']['rapp']
        tot_color = get_color_cell(tot_r)
        row_cells.append(f"{tot_color}\\textbf{{{tot_r:.0f}\\%}}")
        
        fig2_rows += f"{reg_disp} & " + " & ".join(row_cells) + " \\\\\n\\hline\n"

    fig2_latex = f"""
\\begin{{table}}[H]
\\centering
\\caption{{Répartition des pluies mensuelles {annee}-{annee+1} par classe de pluviométrie -- Tableau récapitulatif}}
\\vspace{{0.1cm}}
\\fontsize{{7.5}}{{9.5}}\\selectfont
\\begin{{tabular}}{{|l|""" + ("c|" * 13) + f"""}}
\\hline
{fig2_hdr} \\hline
{fig2_rows}\\end{{tabular}}

\\vspace{{0.25cm}}
\\begin{{center}}
\\fontsize{{7.5}}{{9.5}}\\selectfont
\\begin{{tabular}}{{cl}}
\\colorbox{{clsred}}{{\\strut\\quad}} & Pluie inférieure à 50\\% de la moyenne \\\\
\\colorbox{{clsorange}}{{\\strut\\quad}} & Pluie mensuelle comprise entre 50 et 75\\% de la moyenne. \\\\
\\colorbox{{clsyellow}}{{\\strut\\quad}} & Pluie mensuelle comprise entre 75 et 100\\% de la moyenne. \\\\
\\colorbox{{clsgreen}}{{\\strut\\quad}} & Pluie mensuelle supérieure à 100\\% de la moyenne \\\\
\\end{{tabular}}
\\end{{center}}
\\end{{table}}
\\newpage
"""

    return f"""
\\subsection*{{1.3. Pluies mensuelles}}
\\addcontentsline{{toc}}{{subsection}}{{1.3. Pluies mensuelles}}

{intro_para}

{t3_latex}
{t3_notes}
{fig2_latex}
"""

def generate_section_14_saisonnier(conn, annee, gouv='all'):
    """Génère la section 1.4. Pluies saisonnières avec texte dynamique et tableaux."""
    is_nat = (gouv.lower() in ('all', 'national'))
    clean_g = escape_latex(gouv.strip().capitalize()) if not is_nat else "National"

    REGIONS_DEF = {
        'NORD OUEST': {'surf': 16517, 'gouvs': ['jendouba', 'beja', 'le kef', 'kef', 'siliana']},
        'NORD EST': {'surf': 11725, 'gouvs': ['tunis', 'ariana', 'ben arous', 'manouba', 'nabeul', 'zaghouan', 'bizerte']},
        'CENTRE OUEST': {'surf': 22184, 'gouvs': ['kairouan', 'kassrine', 'kasserine', 'sidi bouzid']},
        'CENTRE EST': {'surf': 13430, 'gouvs': ['sousse', 'monastir', 'mahdia', 'sfax']},
        'SUD OUEST': {'surf': 35761, 'gouvs': ['gafsa', 'tozeur', 'kebili', 'kebeli']},
        'SUD EST': {'surf': 55305, 'gouvs': ['gabes', 'tatouine', 'tataouine', 'mednine', 'medenine']}
    }

    date_debut, date_fin = f"{annee}-09-01 00:00:00", f"{annee+1}-08-31 23:59:59"
    q = f"""
        WITH cleaned AS (
            SELECT DISTINCT ON (id_station, date_obs::date)
                id_station,
                EXTRACT(MONTH FROM date_obs)::int AS m,
                valeur_mm
            FROM pluies_148
            WHERE date_obs >= '{date_debut}' AND date_obs <= '{date_fin}' AND valeur_mm IS NOT NULL
        ),
        seasonal AS (
            SELECT id_station,
                SUM(CASE WHEN m IN (9, 10, 11) THEN valeur_mm ELSE 0 END) AS auto,
                SUM(CASE WHEN m IN (12, 1, 2) THEN valeur_mm ELSE 0 END) AS hiver,
                SUM(CASE WHEN m IN (3, 4, 5) THEN valeur_mm ELSE 0 END) AS print,
                SUM(CASE WHEN m IN (6, 7, 8) THEN valeur_mm ELSE 0 END) AS ete,
                SUM(valeur_mm) AS total
            FROM cleaned
            GROUP BY id_station
        )
        SELECT s.id_station, s.gouvernorat, s.nom, s.lon, s.lat, se.auto, se.hiver, se.print, se.ete, se.total
        FROM seasonal se
        JOIN station_148 s ON s.id_station = se.id_station;
    """
    df_se = pd.read_sql(q, conn)
    df_se['norm_gouv'] = df_se['gouvernorat'].apply(normalize_string)

    if not is_nat:
        target_g_norm = normalize_string(gouv)
        df_se = df_se[df_se['norm_gouv'] == target_g_norm]

    # Clean coordinates for Thiessen
    bad_coords_mask = (df_se['norm_gouv'].isin(['manouba', 'tunis', 'ariana', 'ben arous', 'bizerte', 'beja', 'jandouba'])) & (df_se['lat'] < 3800000)
    df_se_clean = df_se[~bad_coords_mask]

    thiessen = get_thiessen_weights(conn, df_se_clean)

    regions_se = {}
    tot_surf = sum(r['surf'] for r in REGIONS_DEF.values())

    if is_nat:
        for reg_name in REGIONS_DEF.keys():
            reg_weights = thiessen['regional'].get(reg_name, {})
            regions_se[reg_name] = {
                'auto': compute_weighted_avg(df_se, 'auto', reg_weights),
                'hiver': compute_weighted_avg(df_se, 'hiver', reg_weights),
                'print': compute_weighted_avg(df_se, 'print', reg_weights),
                'ete': compute_weighted_avg(df_se, 'ete', reg_weights),
                'total': compute_weighted_avg(df_se, 'total', reg_weights),
            }

        regions_se['TUNISIE'] = {
            'auto': sum(regions_se[r]['auto'] * REGIONS_DEF[r]['surf'] for r in REGIONS_DEF) / tot_surf,
            'hiver': sum(regions_se[r]['hiver'] * REGIONS_DEF[r]['surf'] for r in REGIONS_DEF) / tot_surf,
            'print': sum(regions_se[r]['print'] * REGIONS_DEF[r]['surf'] for r in REGIONS_DEF) / tot_surf,
            'ete': sum(regions_se[r]['ete'] * REGIONS_DEF[r]['surf'] for r in REGIONS_DEF) / tot_surf,
            'total': sum(regions_se[r]['total'] * REGIONS_DEF[r]['surf'] for r in REGIONS_DEF) / tot_surf,
        }
    else:
        st_names = df_se['nom'].tolist()
        for _, row in df_se.iterrows():
            sk = row['nom'][:15]
            regions_se[sk] = {
                'auto': row['auto'],
                'hiver': row['hiver'],
                'print': row['print'],
                'ete': row['ete'],
                'total': row['total'],
            }
        sum_key = f'GOUVERNORAT DE {clean_g.upper()}'
        regions_se[sum_key] = {
            'auto': np.mean([regions_se[s[:15]]['auto'] for s in st_names]) if st_names else 0,
            'hiver': np.mean([regions_se[s[:15]]['hiver'] for s in st_names]) if st_names else 0,
            'print': np.mean([regions_se[s[:15]]['print'] for s in st_names]) if st_names else 0,
            'ete': np.mean([regions_se[s[:15]]['ete'] for s in st_names]) if st_names else 0,
            'total': np.mean([regions_se[s[:15]]['total'] for s in st_names]) if st_names else 0,
        }

    p_regions_se = {}
    target_keys = list(REGIONS_DEF.keys()) + ['TUNISIE'] if is_nat else list(regions_se.keys())
    for r in target_keys:
        tot = regions_se[r]['total']
        p_regions_se[r] = {
            'auto': (regions_se[r]['auto'] / tot * 100) if tot > 0 else 0,
            'hiver': (regions_se[r]['hiver'] / tot * 100) if tot > 0 else 0,
            'print': (regions_se[r]['print'] / tot * 100) if tot > 0 else 0,
            'ete': (regions_se[r]['ete'] / tot * 100) if tot > 0 else 0,
        }

    summary_key = 'TUNISIE' if is_nat else f'GOUVERNORAT DE {clean_g.upper()}'
    seasons_data = {}
    seasons_map = {
        'auto': ("L’automne", "l'automne"),
        'hiver': ("L’hiver", "l'hiver"),
        'print': ("La saison du printemps", "le printemps"),
        'ete': ("La saison estivale", "l'été")
    }

    for s_key, (s_name_start, s_name_mid) in seasons_map.items():
        nat_val = p_regions_se[summary_key][s_key]
        reg_vals = [(r, p_regions_se[r][s_key]) for r in (list(REGIONS_DEF.keys()) if is_nat else [s[:15] for s in df_se['nom'].tolist()])]
        min_reg = min(reg_vals, key=lambda x: x[1]) if reg_vals else ('-', 0)
        max_reg = max(reg_vals, key=lambda x: x[1]) if reg_vals else ('-', 0)
        seasons_data[s_key] = {
            'nat': nat_val,
            'min_val': min_reg[1],
            'min_reg': min_reg[0].title(),
            'max_val': max_reg[1],
            'max_reg': max_reg[0].title()
        }

    loc_txt = "l'ensemble du pays" if is_nat else f"le Gouvernorat de {clean_g}"
    p1 = f"""\\noindent A l'échelle saisonnière, la répartition des pluies pour {loc_txt} se présente comme suit:
\\begin{{itemize}}
    \\item {seasons_map['auto'][0]} a contribué de {seasons_data['auto']['nat']:.1f}\% au total pluviométrique annuel ;
    \\item {seasons_map['hiver'][0]} a présenté {seasons_data['hiver']['nat']:.1f}\% du total pluviométrique ;
    \\item {seasons_map['print'][0]} a contribué de {seasons_data['print']['nat']:.1f}\% du total pluviométrique annuel ;
    \\item {seasons_map['ete'][0]} a contribué de {seasons_data['ete']['nat']:.1f}\% au total pluviométrique de l’année {annee}-{str(annee+1)[2:]}.
\\end{{itemize}}"""

    hierarchy_bullets = []
    season_names_hierarchy = {'auto': 'l’automne', 'hiver': 'l’hiver', 'print': 'le printemps', 'ete': 'l’été'}
    
    for r in target_keys:
        r_vals = [
            ('auto', p_regions_se[r]['auto']),
            ('hiver', p_regions_se[r]['hiver']),
            ('print', p_regions_se[r]['print']),
            ('ete', p_regions_se[r]['ete']),
        ]
        r_vals_sorted = sorted(r_vals, key=lambda x: x[1], reverse=True)
        
        parts = []
        for idx, (s_k, s_v) in enumerate(r_vals_sorted):
            s_disp = season_names_hierarchy[s_k]
            if idx == 0:
                parts.append(f"l’apport pluviométrique de {s_disp.capitalize()} prédomine avec {s_v:.1f}\\% de la pluviométrie annuelle")
            elif idx == 1:
                parts.append(f"suivi par les apports du/de {s_disp} avec {s_v:.1f}\\%")
            elif idx == 2:
                parts.append(f"{s_disp} avec {s_v:.1f}\\%")
            else:
                parts.append(f"et {s_disp} avec {s_v:.1f}\\%")
        
        reg_disp = f"toute la Tunisie" if r == 'TUNISIE' else (f"le Gouvernorat de {clean_g}" if 'GOUVERNORAT' in r else f"la station {r}")
        hierarchy_bullets.append(f"    \\item Pour {reg_disp}, {', '.join(parts)};")

    hierarchy_str = "\n".join(hierarchy_bullets)
    
    p2 = f"""\\noindent Pour l'année hydrologique {annee}-{annee+1} il apparaît que :
\\begin{{itemize}}
{hierarchy_str}
\\end{{itemize}}
\\noindent Le tableau suivant présente les cumuls pluviométriques saisonniers ainsi que la contribution relative de chaque saison au total annuel :"""

    NB_ANNEES_MAP = {
        'NORD OUEST': 53, 'NORD EST': 49, 'CENTRE OUEST': 45,
        'CENTRE EST': 42, 'SUD OUEST': 41, 'SUD EST': 22, 'TUNISIE': 42
    }

    q_y = "SELECT code::text AS id_station, auto, hiver, print, ete, total AS total_moy FROM yasra_data;"
    df_y = pd.read_sql(q_y, conn).set_index('id_station')

    df_st = pd.read_sql("SELECT id_station, gouvernorat, lon, lat FROM station_148;", conn)
    df_st['norm_gouv'] = df_st['gouvernorat'].apply(normalize_string)

    df_pn = df_st.merge(df_se[['id_station', 'auto', 'hiver', 'print', 'ete', 'total']], on='id_station', how='left').fillna(0)
    df_pn = df_pn.merge(df_y[['auto', 'hiver', 'print', 'ete', 'total_moy']], on='id_station', how='left').fillna(0)
    df_pn.columns = ['id_station', 'gouvernorat', 'norm_gouv', 'lon', 'lat', 'auto_p', 'hiver_p', 'print_p', 'ete_p', 'total_p', 'auto_n', 'hiver_n', 'print_n', 'ete_n', 'total_n']

    if is_nat:
        for reg_name in REGIONS_DEF.keys():
            reg_weights = thiessen['regional'].get(reg_name, {})
            regions_se[reg_name]['total_n'] = compute_weighted_avg(df_pn, 'total_n', reg_weights)
        regions_se['TUNISIE']['total_n'] = sum(regions_se[r]['total_n'] * REGIONS_DEF[r]['surf'] for r in REGIONS_DEF) / tot_surf
    else:
        for r in target_keys:
            regions_se[r]['total_n'] = regions_se[r]['total'] # Default fallback for governorate station normal

    rows_tex = ""
    for r in target_keys:
        if is_nat:
            reg_disp = f"\\textbf{{{r}}}" if r == 'TUNISIE' else r
            surf_str = str(REGIONS_DEF[r]['surf']) if r in REGIONS_DEF else str(tot_surf)
            surf_display = f"\\textbf{{{surf_str}}}" if r == 'TUNISIE' else surf_str
            nb = NB_ANNEES_MAP.get(r, 40)
        else:
            reg_disp = f"\\textbf{{{escape_latex(r)}}}" if r == summary_key else escape_latex(r)
            surf_display = "-"
            nb = 40
        
        ap = regions_se[r]['auto']
        hp = regions_se[r]['hiver']
        pp = regions_se[r]['print']
        ep = regions_se[r]['ete']
        tot = regions_se[r]['total']
        moy = regions_se[r].get('total_n', tot)
        ecart = tot - moy
        rapp = (tot / moy * 100) if moy > 0 else 0
        
        ap_pct = (ap / tot * 100) if tot > 0 else 0
        hp_pct = (hp / tot * 100) if tot > 0 else 0
        pp_pct = (pp / tot * 100) if tot > 0 else 0
        ep_pct = (ep / tot * 100) if tot > 0 else 0
        
        def fmt(val): return f"{val:.1f}".replace('.', ',')
        def fmt_int(val): return f"{val:.0f}"
            
        ap_s, hp_s, pp_s, ep_s = fmt(ap), fmt(hp), fmt(pp), fmt(ep)
        ap_pct_s, hp_pct_s, pp_pct_s, ep_pct_s = f"{ap_pct:.0f}\\%", f"{hp_pct:.0f}\\%", f"{pp_pct:.0f}\\%", f"{ep_pct:.0f}\\%"
        tot_s, moy_s = fmt_int(tot), fmt_int(moy)
        ecart_s = f"{ecart:+.0f}"
        rapp_s = f"{rapp:.0f}\\%"
        
        if r == summary_key:
            ap_s, hp_s, pp_s, ep_s = f"\\textbf{{{ap_s}}}", f"\\textbf{{{hp_s}}}", f"\\textbf{{{pp_s}}}", f"\\textbf{{{ep_s}}}"
            ap_pct_s, hp_pct_s, pp_pct_s, ep_pct_s = f"\\textbf{{{ap_pct_s}}}", f"\\textbf{{{hp_pct_s}}}", f"\\textbf{{{pp_pct_s}}}", f"\\textbf{{{ep_pct_s}}}"
            tot_s, moy_s = f"\\textbf{{{tot_s}}}", f"\\textbf{{{moy_s}}}"
            ecart_s, rapp_s = f"\\textbf{{{ecart_s}}}", f"\\textbf{{{rapp_s}}}"

        rows_tex += (f"{reg_disp} & {surf_display} & "
                     f"{ap_s} & {ap_pct_s} & "
                     f"{hp_s} & {hp_pct_s} & "
                     f"{pp_s} & {pp_pct_s} & "
                     f"{ep_s} & {ep_pct_s} & "
                     f"{tot_s} & {moy_s} & {nb} & {ecart_s} & {rapp_s} \\\\\n\\hline\n")

    tab_caption_4 = f"Tableau 4 : Totaux pluviométriques saisonniers du Gouvernorat de {clean_g}" if not is_nat else "Tableau 4 : Totaux pluviométriques saisonniers par région naturelle"
    table_latex = f"""
\\begin{{table}}[H]
\\centering
\\caption{{{tab_caption_4}}}
\\vspace{{0.1cm}}
\\fontsize{{5.5}}{{7.5}}\\selectfont
\\setlength{{\\tabcolsep}}{{1.3pt}}
\\begin{{tabular}}{{|l|c|cc|cc|cc|cc|c|c|c|c|c|}}
\\hline
\\textbf{{STATION/RÉGION}} & \\textbf{{SUPERFICIE}} & \\multicolumn{{2}}{{c|}}{{\\textbf{{AUTOMNE}}}} & \\multicolumn{{2}}{{c|}}{{\\textbf{{HIVER}}}} & \\multicolumn{{2}}{{c|}}{{\\textbf{{PRINTEMPS}}}} & \\multicolumn{{2}}{{c|}}{{\\textbf{{ETE}}}} & \\textbf{{Pluviométrie}} & \\textbf{{Moyenne}} & \\textbf{{NB}} & \\textbf{{ECART}} & \\textbf{{ECART}} \\\\
 & \\textbf{{en Km2}} & \\textbf{{mm}} & \\textbf{{\\%}} & \\textbf{{mm}} & \\textbf{{\\%}} & \\textbf{{mm}} & \\textbf{{\\%}} & \\textbf{{mm}} & \\textbf{{\\%}} & \\textbf{{totale}} & \\textbf{{(mm)}} & \\textbf{{ANNEES}} & \\textbf{{(mm)}} & \\textbf{{\\%}} \\\\ \\hline
{rows_tex}\\end{{tabular}}
\\end{{table}}
"""

    path_pie_s = os.path.join(IMG_DIR, 'pie_saisons.png').replace('\\', '/')
    path_annuelle_s = os.path.join(IMG_DIR, 'carte_annuelle.png').replace('\\', '/')
    path_rapport_s = os.path.join(IMG_DIR, 'carte_rapport_normale.png').replace('\\', '/')
    path_interannual_s = os.path.join(IMG_DIR, 'carte_interannuelle.png').replace('\\', '/')
    path_comp_nord_s = os.path.join(IMG_DIR, 'comparaison_nord.png').replace('\\', '/')
    path_comp_centre_s = os.path.join(IMG_DIR, 'comparaison_centrale.png').replace('\\', '/')
    path_comp_sud_s = os.path.join(IMG_DIR, 'comparaison_sud.png').replace('\\', '/')

    figs_latex = f"""
\\begin{{figure}}[H]
\\centering
\\includegraphics[width=0.60\\textwidth]{{{path_pie_s}}}
\\caption{{Figure 3 : Répartition des pluies saisonnières en \\% ({'toute la Tunisie' if is_nat else f'Gouvernorat de {clean_g}'})}}
\\end{{figure}}
\\clearpage

\\begin{{figure}}[H]
\\centering
\\includegraphics[width=0.70\\textwidth]{{{path_annuelle_s}}}
\\caption{{Figure 4 : Isohyètes de l’année {annee}-{annee+1}}}
\\end{{figure}}
\\clearpage

\\begin{{figure}}[H]
\\centering
\\includegraphics[width=0.70\\textwidth]{{{path_rapport_s}}}
\\caption{{Figure 5: Rapport à la moyenne de la pluviométrie de l’année {annee}-{annee+1}}}
\\end{{figure}}
\\clearpage

\\begin{{figure}}[H]
\\centering
\\includegraphics[width=0.70\\textwidth]{{{path_interannual_s}}}
\\caption{{Figure 6: Isohyètes moyennes interannuelles (50 ans) du 1959-2009}}
\\end{{figure}}
\\clearpage

\\begin{{figure}}[H]
\\centering
\\includegraphics[width=0.92\\textwidth]{{{path_comp_nord_s}}}
\\caption{{Figure 7: (Tunisie du Nord) : Pluviométrie annuelle {annee}-{annee+1} par station, comparée à la moyenne interannuelle}}
\\end{{figure}}
\\clearpage

\\begin{{figure}}[H]
\\centering
\\includegraphics[width=0.92\\textwidth]{{{path_comp_centre_s}}}
\\caption{{Figure 8: (Tunisie Centrale) : Pluviométrie annuelle {annee}-{annee+1} par station, comparée à la moyenne interannuelle}}
\\end{{figure}}
\\clearpage

\\begin{{figure}}[H]
\\centering
\\includegraphics[width=0.92\\textwidth]{{{path_comp_sud_s}}}
\\caption{{Figure 9: (Tunisie du Sud) : Pluviométrie annuelle {annee}-{annee+1} par station, comparée à la moyenne interannuelle}}
\\end{{figure}}
\\clearpage
"""

    return f"""
\\subsection*{{1.4. Pluies saisonnières}}
\\addcontentsline{{toc}}{{subsection}}{{1.4. Pluies saisonnières}}

{p1}

{p2}

{table_latex}
\\newpage

{figs_latex}
"""

def generate_section_14_table7_cumule(conn, annee, gouv='all'):
    """Génère le Tableau 7 : Pluie cumulée de l'année [annee]-[annee+1] sous forme de longtable LaTeX."""
    date_debut, date_fin = f"{annee}-09-01 00:00:00", f"{annee+1}-08-31 23:59:59"
    q = f"""
        WITH cleaned AS (
            SELECT DISTINCT ON (id_station, date_obs::date)
                id_station,
                EXTRACT(MONTH FROM date_obs)::int AS m,
                valeur_mm
            FROM pluies_148
            WHERE date_obs >= '{date_debut}' AND date_obs <= '{date_fin}' AND valeur_mm IS NOT NULL
        )
        SELECT id_station, m, SUM(valeur_mm) AS total_m
        FROM cleaned
        GROUP BY id_station, m;
    """
    df_m = pd.read_sql(q, conn)

    mois_order = [9, 10, 11, 12, 1, 2, 3, 4, 5, 6, 7, 8]
    pivot = df_m.pivot(index='id_station', columns='m', values='total_m').fillna(0)

    for m in mois_order:
        if m not in pivot.columns:
            pivot[m] = 0.0
    pivot = pivot[mois_order]
    cum_pivot = pivot.cumsum(axis=1)

    df_st = pd.read_sql("SELECT id_station, gouvernorat, nom FROM station_148 ORDER BY gouvernorat, nom;", conn)
    if gouv.lower() not in ('all', 'national'):
        df_st['norm_gouv'] = df_st['gouvernorat'].apply(normalize_string)
        df_st = df_st[df_st['norm_gouv'] == normalize_string(gouv)]

    df = df_st.merge(cum_pivot, on='id_station', how='left').fillna(0)

    # Begin LaTeX table
    tex = f"""
\\newpage
\\subsection*{{Tableau 7 : Pluie cumulée de l’année {annee}-{annee+1}}}
\\addcontentsline{{toc}}{{subsection}}{{Tableau 7 : Pluie cumulée de l’année {annee}-{annee+1}}}
\\begin{{center}}
\\fontsize{{5.5}}{{7.5}}\\selectfont
\\setlength{{\\tabcolsep}}{{2pt}}
\\begin{{longtable}}{{|l|l|c|c|c|c|c|c|c|c|c|c|c|c|}}
\\hline
\\textbf{{CODE}} & \\textbf{{STATION}} & \\textbf{{SEPT}} & \\textbf{{OCTO}} & \\textbf{{NOVE}} & \\textbf{{DECE}} & \\textbf{{JANV}} & \\textbf{{FEV}} & \\textbf{{MAR}} & \\textbf{{AVR}} & \\textbf{{MAI}} & \\textbf{{JUIN}} & \\textbf{{JUIL}} & \\textbf{{AOUT}} \\\\ \\hline
\\endhead
"""

    # Group by gouvernorat
    gouvernorats = df['gouvernorat'].unique()
    for gouv in gouvernorats:
        tex += f"\\multicolumn{{14}}{{|l|}}{{\\textbf{{GOUVERNORAT DE {gouv.upper()}}}}} \\\\ \\hline\n"
        sub = df[df['gouvernorat'] == gouv].sort_values(by='nom')
        for idx, row in sub.iterrows():
            code = str(row['id_station'])
            nom = escape_latex(row['nom'].upper())
            vals = [f"{row[m]:.1f}".replace('.', ',') for m in mois_order]
            tex += f"{code} & {nom} & " + " & ".join(vals) + " \\\\\n\\hline\n"
        
        # Add MOYENNE row (average of target column AOUT, which corresponds to index 8)
        avg_val = sub[8].mean()
        avg_str = f"{avg_val:.1f}".replace('.', ',')
        tex += f"\\multicolumn{{13}}{{|r|}}{{\\textbf{{MOYENNE}}}} & \\textbf{{{avg_str}}} \\\\ \\hline\n"

    tex += """\\end{longtable}
\\end{center}
"""
    return tex


# ------------------------- 5. Rédaction du rapport LaTeX complet -------------------------
def write_complete_latex(stats, daily_latex, gouv, annee, output_tex, conn, df_stations, df_rain):
    is_national = (gouv.lower() in ('all', 'national'))
    clean_gouv = gouv.strip().capitalize() if not is_national else "National"
    gouv_display = f"Gouvernorat de {clean_gouv}" if not is_national else "Toute la Tunisie"

    REGIONS_NORM = {
        'NORD OUEST': ['jendouba', 'beja', 'le_kef', 'kef', 'siliana'],
        'NORD EST':   ['tunis', 'ariana', 'ben_arous', 'manouba', 'nabeul', 'zaghouan', 'bizerte'],
        'CENTRE OUEST': ['kairouan', 'kassrine', 'kasserine', 'sidi_bouzid'],
        'CENTRE EST': ['sousse', 'monastir', 'mahdia', 'sfax'],
        'SUD OUEST': ['gafsa', 'tozeur', 'kebili', 'kebeli'],
        'SUD EST': ['gabes', 'tatouine', 'tataouine', 'mednine', 'medenine']
    }
    target_region = None
    if not is_national:
        target_g_norm = normalize_string(gouv)
        for rname, gouvs in REGIONS_NORM.items():
            if target_g_norm in gouvs:
                target_region = rname
                break
        if not target_region:
            target_region = "Tunisie"

    path_annuelle = os.path.join(IMG_DIR, 'carte_annuelle.png').replace('\\', '/')
    path_saisons  = os.path.join(IMG_DIR, 'carte_saisons_subplots.png').replace('\\', '/')
    path_hist = os.path.join(IMG_DIR, 'hist_mensuel.png').replace('\\', '/')
    path_pie = os.path.join(IMG_DIR, 'pie_saisons.png').replace('\\', '/')
    path_classes = os.path.join(IMG_DIR, 'hist_classes.png').replace('\\', '/')
    path_stations    = os.path.join(IMG_DIR, 'carte_stations.png').replace('\\', '/')
    path_interannual = os.path.join(IMG_DIR, 'carte_interannuelle.png').replace('\\', '/')
    path_rapport     = os.path.join(IMG_DIR, 'carte_rapport_normale.png').replace('\\', '/')
    path_comparaison = os.path.join(IMG_DIR, 'comparaison_regionales.png').replace('\\', '/')
    
    path_group1 = os.path.join(IMG_DIR, 'carte_mensuelle_group1.png').replace('\\', '/')
    path_group2 = os.path.join(IMG_DIR, 'carte_mensuelle_group2.png').replace('\\', '/')
    path_group3 = os.path.join(IMG_DIR, 'carte_mensuelle_group3.png').replace('\\', '/')
    
    df_stat = stats['pivot'].drop_duplicates(subset=['nom']).sort_values(by='total', ascending=False)
    nb_stations = len(df_stat)
    total_nat = stats['total_national']
    
    st_max = df_stat.iloc[0] if not df_stat.empty else None
    st_min = df_stat.iloc[-1] if not df_stat.empty else None
    
    season_max_name = max(stats['saisons'], key=stats['saisons'].get) if stats['saisons'] else 'auto'
    season_max_val = stats['saisons'].get(season_max_name, 0)
    season_max_pct = (season_max_val / total_nat * 100) if total_nat > 0 else 0

    header_left = "Annuaire Pluviométrique — DGRE" if is_national else f"Annuaire Pluviométrique du Gouvernorat de {escape_latex(clean_gouv)} — DGRE"
    title_main = "ANNUAIRE PLUVIOMÉTRIQUE" if is_national else "ANNUAIRE PLUVIOMÉTRIQUE RÉGIONAL"

    preambule = r"""\documentclass[a4paper,10pt]{article}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage[french]{babel}
\usepackage{geometry}
\usepackage{graphicx}
\usepackage{booktabs}
\usepackage{array}
\usepackage{float}
\usepackage{fancyhdr}
\usepackage{lastpage}
\usepackage{hyperref}
\usepackage{tocloft}
\usepackage{geometry}
\geometry{a4paper, top=0.6cm, bottom=0.6cm, left=0.6cm, right=0.6cm}
\usepackage{longtable}
\usepackage[table]{xcolor}
\definecolor{clsred}{HTML}{FADBD8}
\definecolor{clsorange}{HTML}{FDEBD0}
\definecolor{clsyellow}{HTML}{FCF3CF}
\definecolor{clsgreen}{HTML}{D4EFDF}

\usepackage{array}
\newcommand{\hdr}[1]{\textbf{\fontsize{4.5}{5.5}\selectfont #1}}
\hypersetup{colorlinks=true, linkcolor=blue, urlcolor=blue, citecolor=blue}

% Configuration de la pagination globale
\pagestyle{fancy}
\fancyhf{}
\renewcommand{\headrulewidth}{0.4pt}
\fancyhead[L]{\footnotesize """ + header_left + r"""}
\fancyhead[R]{\footnotesize """ + f"Année Hydrologique {annee}-{annee+1}" + r"""}
\fancyfoot[R]{\footnotesize Page \thepage\ sur \pageref{LastPage}}

\setlength{\tabcolsep}{2.5pt}
\renewcommand{\arraystretch}{1.1}

\begin{document}
"""

    logo_latex = ""
    if os.path.exists(LOGO_PATH):
        logo_latex = f"\\includegraphics[width=4cm]{{{LOGO_PATH.replace('\\', '/')}}} \\\\"

    page_garde = r"""
\begin{titlepage}
\centering
\vspace*{0.5cm}
{\Large\textbf{RÉPUBLIQUE TUNISIENNE}} \\[0.3cm]
{\large MINISTÈRE DE L'AGRICULTURE, DES RESSOURCES HYDRAULIQUES ET DE LA PÊCHE} \\[0.2cm]
{\small DIRECTION GÉNÉRALE DES RESSOURCES EN EAU (DGRE)} \\
\vspace{1.5cm}
""" + logo_latex + r"""
\vspace{2cm}
{\Huge\textbf{""" + title_main + r"""}} \\[0.6cm]
{\LARGE\textbf{""" + escape_latex(gouv_display) + r"""}} \\[0.4cm]
{\Large Année Hydrologique : """ + f"{annee}-{annee+1}" + r"""} \\
\vfill
{\small\textbf{PUBLICATION DE LA DIRECTION GENERALE DES RESSOURCES EN EAU}} \\[0.1cm]
{\small 43, Rue la MANOUBIA -1008- TUNIS} \\[0.1cm]
{\small Tél : (216) 71 560 000 / +216 71 391 851 \quad Fax : (216) 71 391 549} \\[0.3cm]
{\footnotesize Édité le """ + datetime.now().strftime('%d/%m/%Y') + r""" — Service National Pluviométrique}
\end{titlepage}
\newpage
"""

    if is_national:
        avant_propos = r"""
\section*{AVANT-PROPOS}
\addcontentsline{toc}{section}{AVANT-PROPOS}
L’Annuaire pluviométrique de la Tunisie de l’année """ + f"{annee}-{annee+1}" + r""" est une synthèse des observations pluviométriques relevées sur l’ensemble du réseau pluviométrique national au cours de l’année hydrologique """ + f"{annee}-{annee+1}" + r""" qui démarre le 1er septembre """ + f"{annee}" + r""" et s’achève le 31 août """ + f"{annee+1}" + r""".

Il est le fruit d’une collaboration permanente entre les établissements régionaux représentés par les (CRDA) « Commissariat Régional au Développement Agricole » et la Direction Générale des Ressources en Eaux. Dans chaque gouvernorat, existe un CRDA au sein duquel toutes les directions techniques centrales au niveau du Ministère sont représentées par des arrondissements. La Direction Générale des Ressources en Eau est représentée à l’échelle régionale par 24 arrondissements de Ressources en eau. Ces derniers, parmi leurs tâches multiples, ils :
\begin{itemize}
    \item Gèrent les réseaux de pluviomètres implantés dans les différents gouvernorats et veillent à leur bon état de fonctionnement.
    \item Collectent les observations et initient les observateurs des pluviomètres à effectuer de bons relevés pluviométriques.
    \item Constituent les fichiers informatisés et éditent des annuaires pluviométriques régionaux.
\end{itemize}

Et la Direction des Eaux de Surface par l’intermédiaire de la sous direction d’Hydrologie Analytique et des Bases de Données:
\begin{itemize}
    \item Assure le rassemblement, la collecte, l’informatisation et la mise en forme de ces données ;
    \item Prépare, édite et diffuse l’annuaire pluviométrique national ;
    \item Veille à la mise à jour et la sauvegarde de la banque des données pluviométriques, composante principale de la base nationale de données sur les ressources en eau ;
    \item Accorde une assistance technique permanente aux arrondissements régionaux pour la bonne gestion du réseau pluviométrique.
\end{itemize}

\vspace{0.3cm}
\noindent\textbf{Cet annuaire a été élaboré par :} \\
Mr.  \\[0.15cm]
\textbf{Vérifié et corrigé par :} \\
Mme. \\
Mme. \\
\textbf{Vérifié et validé par :} \\
Mr.     
\newpage
"""
        presentation_annuaire = r"""
\section*{Présentation de l’Annuaire}
\addcontentsline{toc}{section}{Présentation de l’Annuaire}
La première partie de cette publication présente une analyse de la pluviosité en Tunisie durant l’année """ + f"{annee}-{annee+1}" + r""", cette analyse a été faite à l’échelle des gouvernorats et des régions naturelles ; chaque région naturelle regroupe un certain nombre de gouvernorats selon la répartition suivante :
\begin{itemize}
    \item \textbf{Nord Ouest :} Jendouba, Béja, Kef et Siliana ;
    \item \textbf{Nord Est :} Tunis, Ariana, Ben Arous, Manouba, Nabeul, Zaghouan et Bizerte ;
    \item \textbf{Centre Ouest :} Kairouan, Kasserine et Sidi Bouzid ;
    \item \textbf{Centre Est :} Sousse, Monastir, Mahdia et Sfax ;
    \item \textbf{Sud Ouest :} Gafsa, Tozeur et Kébili ;
    \item \textbf{Sud Est :} Gabès, Tataouine et Mednine.
\end{itemize}

Sur un total de 712 stations pluviométriques observées au cours de l’année """ + f"{annee}-{annee+1}" + r""", il a été sélectionné \textbf{""" + f"{nb_stations}" + r""" stations} (à raison de 3 à 7 par gouvernorat), pour caractériser la situation pluviométrique à l’échelle du pays.

La deuxième partie comprend les relevés pluviométriques journaliers. Ces relevés se présentent sous forme de tableaux annuels par station et sont groupés par bassin et par ordre numérique et alphabétique. Les données pluviométriques ont été saisies et traitées par le logiciel de gestion de données pluviométriques « HYDRACCES », élaboré au Laboratoire d’Hydrologie de l’Institut de Recherches pour le Développement (IRD).

Quant à la critique des données, elle se fait une première fois à la réception du bulletin pluviométrique. La critique consiste à comparer les relevés des postes voisins et éliminer toute observation qui semble aberrante. Une deuxième critique se fait à la préparation de l'annuaire par une comparaison des bulletins avec leur double et avec les souches afin de noter les rectifications éventuelles.
\newpage
"""
    else:
        avant_propos = r"""
\section*{AVANT-PROPOS}
\addcontentsline{toc}{section}{AVANT-PROPOS}
L’Annuaire pluviométrique du Gouvernorat de """ + escape_latex(clean_gouv) + r""" de l’année """ + f"{annee}-{annee+1}" + r""" est une synthèse des observations pluviométriques relevées sur l'ensemble des stations du gouvernorat au cours de l’année hydrologique (du 1er septembre """ + f"{annee}" + r""" au 31 août """ + f"{annee+1}" + r""").

Il est le fruit d’une collaboration permanente entre le Commissariat Régional au Développement Agricole (CRDA) du Gouvernorat de """ + escape_latex(clean_gouv) + r""" (à travers son Arrondissement des Ressources en Eau) et la Direction Générale des Ressources en Eau (DGRE).

Au niveau régional, l'Arrondissement des Ressources en Eau du CRDA de """ + escape_latex(clean_gouv) + r""" :
\begin{itemize}
    \item Gère le réseau de pluviomètres implantés dans le Gouvernorat de """ + escape_latex(clean_gouv) + r""" et veille à son bon fonctionnement.
    \item Collecte les observations pluviométriques quotidiennes et encadre les observateurs sur le terrain.
    \item Constitue les fichiers informatisés locaux et participe à l'élaboration de l'annuaire pluviométrique régional.
\end{itemize}

La Direction des Eaux de Surface de la DGRE (Sous-direction d’Hydrologie Analytique et des Bases de Données) assure la centralisation, l'intégration dans la banque nationale des données sur les ressources en eau, et l'assistance technique pour l'édition de cette publication.

\vspace{0.3cm}
\noindent\textbf{Cet annuaire a été élaboré par :} \\
Mr. Ammar Manai, Technicien \\[0.15cm]
\textbf{Vérifié et corrigé par :} \\
Mme. Hayet Ben Mansour, Directeur des eaux de surface \\
Mme. Nejla Khalfoun, Sous-directeur d'hydrologie analytique et des bases de données \\[0.15cm]
\textbf{Vérifié et validé par :} \\
Mr. Hassen Lotfi Frigui, Directeur Général des Ressources en eau
\newpage
"""
        presentation_annuaire = r"""
\section*{Présentation de l’Annuaire}
\addcontentsline{toc}{section}{Présentation de l’Annuaire}
La première partie de cette publication présente une analyse de la pluviosité dans le \textbf{Gouvernorat de """ + escape_latex(clean_gouv) + r"""} (Région """ + escape_latex(target_region.title()) + r""") durant l’année hydrologique """ + f"{annee}-{annee+1}" + r""".

Pour ce gouvernorat, un réseau de \textbf{""" + f"{nb_stations}" + r""" stations pluviométriques} représentatives a été retenu et analysé pour caractériser la situation pluviométrique locale.

La deuxième partie comprend les relevés pluviométriques journaliers détaillés de l'ensemble des stations du gouvernorat. Les données ont été contrôlées, saisies et traitées par le logiciel de gestion de données pluviométriques « HYDRACCES » (IRD).

La critique des données comporte une vérification initiale à la réception des bulletins pluviométriques mensuels (comparaison entre stations voisines du gouvernorat), suivie d'un contrôle final lors de la préparation de l'annuaire.
\newpage
"""

    REGIONS_DEF = {
        'NORD OUEST': {'surf': 16517, 'gouvs': ['jendouba', 'beja', 'le kef', 'kef', 'siliana']},
        'NORD EST': {'surf': 11725, 'gouvs': ['tunis', 'ariana', 'ben arous', 'manouba', 'nabeul', 'zaghouan', 'bizerte']},
        'CENTRE OUEST': {'surf': 22184, 'gouvs': ['kairouan', 'kassrine', 'kasserine', 'sidi bouzid']},
        'CENTRE EST': {'surf': 13430, 'gouvs': ['sousse', 'monastir', 'mahdia', 'sfax']},
        'SUD OUEST': {'surf': 35761, 'gouvs': ['gafsa', 'tozeur', 'kebili', 'kebeli']},
        'SUD EST': {'surf': 55305, 'gouvs': ['gabes', 'tatouine', 'tataouine', 'mednine', 'medenine']}
    }

    date_debut, date_fin = f"{annee}-09-01 00:00:00", f"{annee+1}-08-31 23:59:59"
    q_curr_dynamic = f"""
        WITH cleaned AS (
            SELECT DISTINCT ON (id_station, date_obs::date)
                id_station,
                valeur_mm
            FROM pluies_148
            WHERE date_obs >= '{date_debut}' AND date_obs <= '{date_fin}' AND valeur_mm IS NOT NULL
        ),
        totals AS (
            SELECT id_station, SUM(valeur_mm) AS total
            FROM cleaned
            GROUP BY id_station
        )
        SELECT s.gouvernorat, s.nom AS station, s.lon, s.lat, s.altitude, t.total, y.moy_, s.id_station
        FROM totals t
        JOIN station_148 s ON s.id_station = t.id_station
        LEFT JOIN yasra_data y ON y.code::text = t.id_station;
    """
    df_curr_yasra = pd.read_sql(q_curr_dynamic, conn)
    df_curr_yasra['norm_gouv'] = df_curr_yasra['gouvernorat'].apply(normalize_string)

    bad_coords_mask = (df_curr_yasra['norm_gouv'].isin(['manouba', 'tunis', 'ariana', 'ben arous', 'bizerte', 'beja', 'jandouba'])) & (df_curr_yasra['lat'] < 3800000)
    df_curr_yasra_clean = df_curr_yasra[~bad_coords_mask]

    thiessen = get_thiessen_weights(conn, df_curr_yasra_clean)

    years_8 = list(range(annee - 7, annee + 1))
    q_hist_8 = f"""
        WITH cleaned AS (
            SELECT DISTINCT ON (id_station, date_obs::date)
                id_station,
                date_obs::date AS date_only,
                EXTRACT(MONTH FROM date_obs) AS m,
                EXTRACT(YEAR FROM date_obs) AS y,
                valeur_mm
            FROM pluies_148
            WHERE valeur_mm IS NOT NULL
        ),
        yearly AS (
            SELECT id_station,
                   CASE WHEN m >= 9 THEN y::int ELSE y::int - 1 END AS hydro_year,
                   SUM(valeur_mm) AS annual_sum,
                   COUNT(*) AS nb_jours
            FROM cleaned
            GROUP BY id_station, hydro_year
        )
        SELECT s.gouvernorat, s.id_station, s.nom AS station, y.hydro_year, y.annual_sum, y.nb_jours
        FROM yearly y
        JOIN station_148 s ON s.id_station = y.id_station
        WHERE y.hydro_year IN ({','.join(map(str, years_8))});
    """
    df_hist_8 = pd.read_sql(q_hist_8, conn)

    if not df_hist_8.empty:
        year_coverage = df_hist_8.groupby('hydro_year')['nb_jours'].mean()
        valid_years = year_coverage[year_coverage >= 300].index.tolist()
        df_hist_8 = df_hist_8[df_hist_8['hydro_year'].isin(valid_years)].drop(columns=['nb_jours'])
    
    avail_years = sorted(df_hist_8['hydro_year'].unique()) if not df_hist_8.empty else []
    generate_regional_comparison_chart(df_hist_8, df_curr_yasra, avail_years, annee, 'comparaison_regionales.png', gouv=gouv)
    
    missing_note_latex = ""
    if len(avail_years) < 8 and avail_years:
        missing_years = set(years_8) - set(avail_years)
        missing_note_latex = f"\\noindent\\textit{{\\small \\textbf{{Note :}} Des lacunes historiques sont observées dans la BDD pour les années : {', '.join(map(str, sorted(missing_years)))}. Le tableau ci-dessous présente les {len(avail_years)} années réellement disponibles.}}\n\n"

    list_items_latex = ""
    tab1_rows = ""
    tab2_rows = ""
    t2_headers = " & ".join([f"\\textbf{{{str(y)[2:]}-{str(y+1)[2:]}}}" for y in avail_years])
    comparison_bullets = []

    if is_national:
        gouv_grp = df_curr_yasra.groupby(['gouvernorat', 'norm_gouv'])[['total', 'moy_']].mean().reset_index()
        tot_surf = sum(r['surf'] for r in REGIONS_DEF.values())
        tot_p_annee_sum = 0
        tot_p_moy_sum = 0

        for reg_name, reg_info in REGIONS_DEF.items():
            sub_g = gouv_grp[gouv_grp['norm_gouv'].isin(reg_info['gouvs'])]
            if not sub_g.empty:
                p_min_row = sub_g.loc[sub_g['total'].idxmin()]
                p_max_row = sub_g.loc[sub_g['total'].idxmax()]
                p_min_val, g_min_name = p_min_row['total'], p_min_row['gouvernorat']
                p_max_val, g_max_name = p_max_row['total'], p_max_row['gouvernorat']
                diff_min_pct = ((p_min_row['total'] / p_min_row['moy_']) - 1.0) * 100 if p_min_row['moy_'] > 0 else 0
                diff_max_pct = ((p_max_row['total'] / p_max_row['moy_']) - 1.0) * 100 if p_max_row['moy_'] > 0 else 0
                str_min_type = "un excédent" if diff_min_pct >= 0 else "un déficit"
                str_max_type = "un excédent" if diff_max_pct >= 0 else "un déficit"
                list_items_latex += f"    \\item \\textbf{{Au {reg_name.title()}}}, on a enregistré des pluies (par gouvernorat) variant entre {p_min_val:.0f} mm ({escape_latex(g_min_name)}) et {p_max_val:.0f} mm ({escape_latex(g_max_name)}) avec {str_min_type} de {abs(diff_min_pct):.0f}\\% et {str_max_type} de {abs(diff_max_pct):.0f}\\% par rapport à la moyenne.\n"
                
                reg_weights = thiessen['regional'].get(reg_name, {})
                reg_p_annee = compute_weighted_avg(df_curr_yasra, 'total', reg_weights)
                reg_p_moy = compute_weighted_avg(df_curr_yasra, 'moy_', reg_weights)
                ecart_reg = reg_p_annee - reg_p_moy
                pct_reg = ((reg_p_annee / reg_p_moy) - 1.0) * 100 if reg_p_moy > 0 else 0
                sign_reg = '+' if pct_reg >= 0 else ''
                tot_p_annee_sum += reg_p_annee * reg_info['surf']
                tot_p_moy_sum += reg_p_moy * reg_info['surf']
                tab1_rows += f"{reg_name} & {reg_info['surf']} & {reg_p_annee:.0f} & {reg_p_moy:.0f} & {ecart_reg:+.0f} & {sign_reg}{pct_reg:.0f}\\% \\\\\n\\hline\n"
            else:
                list_items_latex += f"    \\item \\textbf{{Au {reg_name.title()}}}, données non disponibles pour l'année en cours.\n"

        nat_p_annee = tot_p_annee_sum / tot_surf if tot_surf > 0 else 0
        nat_p_moy = tot_p_moy_sum / tot_surf if tot_surf > 0 else 0
        nat_ecart = nat_p_annee - nat_p_moy
        nat_pct = ((nat_p_annee / nat_p_moy) - 1.0) * 100 if nat_p_moy > 0 else 0
        nat_sign = '+' if nat_pct >= 0 else ''
        tab1_rows += f"\\textbf{{TUNISIE}} & \\textbf{{{tot_surf}}} & \\textbf{{{nat_p_annee:.0f}}} & \\textbf{{{nat_p_moy:.0f}}} & \\textbf{{{nat_ecart:+.0f}}} & \\textbf{{{nat_sign}{nat_pct:.0f}\\%}} \\\\\n\\hline\n"

        if not df_hist_8.empty:
            df_hist_8['norm_gouv'] = df_hist_8['gouvernorat'].apply(normalize_string)
            for reg_name, reg_info in REGIONS_DEF.items():
                reg_weights = thiessen['regional'].get(reg_name, {})
                reg_moy = compute_weighted_avg(df_curr_yasra, 'moy_', reg_weights)
                row_vals = []
                for y in avail_years:
                    sub_hy = df_hist_8[df_hist_8['hydro_year'] == y]
                    v_y = compute_weighted_avg(sub_hy, 'annual_sum', reg_weights)
                    row_vals.append(f"{v_y:.0f}" if not pd.isna(v_y) and v_y > 0 else "-")
                tab2_rows += f"{reg_name} & {reg_info['surf']} & {reg_moy:.0f} & " + " & ".join(row_vals) + " \\\\\n\\hline\n"
                
            nat_row_vals = []
            for y in avail_years:
                weighted_sum = 0
                for reg_name, reg_info in REGIONS_DEF.items():
                    sub_hy = df_hist_8[df_hist_8['hydro_year'] == y]
                    reg_weights = thiessen['regional'].get(reg_name, {})
                    reg_mean = compute_weighted_avg(sub_hy, 'annual_sum', reg_weights)
                    weighted_sum += reg_mean * reg_info['surf']
                vy_nat = weighted_sum / tot_surf if tot_surf > 0 else 0
                nat_row_vals.append(f"\\textbf{{{vy_nat:.0f}}}" if not pd.isna(vy_nat) else "-")
            tab2_rows += f"\\textbf{{TUNISIE}} & \\textbf{{{tot_surf}}} & \\textbf{{{nat_p_moy:.0f}}} & " + " & ".join(nat_row_vals) + " \\\\\n\\hline\n"

            target_y = annee
            other_years = [y for y in avail_years if y != target_y]
            for reg_name, reg_info in REGIONS_DEF.items():
                reg_weights = thiessen['regional'].get(reg_name, {})
                sub_h = df_hist_8[df_hist_8['hydro_year'] == target_y]
                v_target = compute_weighted_avg(sub_h, 'annual_sum', reg_weights)
                if v_target is not None and v_target > 0:
                    lower_years, higher_years = [], []
                    for y in other_years:
                        sub_hy = df_hist_8[df_hist_8['hydro_year'] == y]
                        v_y = compute_weighted_avg(sub_hy, 'annual_sum', reg_weights)
                        if v_y > 0:
                            y_str = f"{y}-{y+1}"
                            if v_target > v_y: lower_years.append(y_str)
                            else: higher_years.append(y_str)
                    reg_title = reg_name.title()
                    if not lower_years and not higher_years:
                        bullet = f"\\item Pour le {reg_title}, seule l'année {target_y}-{target_y+1} est disponible."
                    elif not higher_years:
                        bullet = f"\\item Pour le {reg_title}, l’année {target_y}-{target_y+1} a été plus pluvieuse que les autres années."
                    elif not lower_years:
                        bullet = f"\\item Pour le {reg_title}, l’année {target_y}-{target_y+1} a été moins pluvieuse que les autres années."
                    else:
                        bullet = f"\\item Pour le {reg_title}, l’année {target_y}-{target_y+1} a été plus pluvieuse que les années ({'; '.join(lower_years)}) et moins pluvieuse que les années ({'; '.join(higher_years)})."
                    comparison_bullets.append(bullet)
                else:
                    comparison_bullets.append(f"\\item Pour le {reg_name.title()}, données non disponibles pour l'année {target_y}-{target_y+1}.")
    else:
        # Mode Gouvernorat spécifique
        target_g_norm = normalize_string(gouv)
        sub_curr_g = df_curr_yasra[df_curr_yasra['norm_gouv'] == target_g_norm]
        
        for _, row in sub_curr_g.iterrows():
            st_nom = escape_latex(row['station'])
            p_tot = row['total'] if pd.notna(row['total']) else 0
            p_moy = row['moy_'] if pd.notna(row['moy_']) else 0
            alt_val = f"{float(row['altitude']):.0f}" if pd.notna(row['altitude']) and str(row['altitude']).strip() != '' else "-"
            ecart_mm = p_tot - p_moy
            pct_val = ((p_tot / p_moy) - 1.0) * 100 if p_moy > 0 else 0
            sign_str = '+' if pct_val >= 0 else ''
            diff_type = "un excédent" if pct_val >= 0 else "un déficit"
            
            list_items_latex += f"    \\item \\textbf{{À la station {st_nom}}}, on a enregistré un cumul annuel de {p_tot:.0f} mm avec {diff_type} de {abs(pct_val):.0f}\\% par rapport à la moyenne ({p_moy:.0f} mm).\n"
            tab1_rows += f"{st_nom} & {alt_val} & {p_tot:.0f} & {p_moy:.0f} & {ecart_mm:+.0f} & {sign_str}{pct_val:.0f}\\% \\\\\n\\hline\n"

        # Summary row for governorate
        g_avg_tot = sub_curr_g['total'].mean() if not sub_curr_g.empty else 0
        g_avg_moy = sub_curr_g['moy_'].mean() if not sub_curr_g.empty else 0
        g_ecart = g_avg_tot - g_avg_moy
        g_pct = ((g_avg_tot / g_avg_moy) - 1.0) * 100 if g_avg_moy > 0 else 0
        g_sign = '+' if g_pct >= 0 else ''
        tab1_rows += f"\\textbf{{MOYENNE {clean_gouv.upper()}}} & \\textbf{{-}} & \\textbf{{{g_avg_tot:.0f}}} & \\textbf{{{g_avg_moy:.0f}}} & \\textbf{{{g_ecart:+.0f}}} & \\textbf{{{g_sign}{g_pct:.0f}\\%}} \\\\\n\\hline\n"

        if not df_hist_8.empty:
            df_hist_g = df_hist_8[df_hist_8['gouvernorat'].apply(normalize_string) == target_g_norm]
            for _, srow in sub_curr_g.iterrows():
                sid = srow['id_station']
                snom = escape_latex(srow['station'])
                alt_val = f"{float(srow['altitude']):.0f}" if pd.notna(srow['altitude']) and str(srow['altitude']).strip() != '' else "-"
                smoy = srow['moy_'] if pd.notna(srow['moy_']) else 0
                row_vals = []
                sub_sh = df_hist_g[df_hist_g['id_station'] == sid]
                for y in avail_years:
                    v_y = sub_sh[sub_sh['hydro_year'] == y]['annual_sum'].mean() if not sub_sh[sub_sh['hydro_year'] == y].empty else 0
                    row_vals.append(f"{v_y:.0f}" if not pd.isna(v_y) and v_y > 0 else "-")
                tab2_rows += f"{snom} & {alt_val} & {smoy:.0f} & " + " & ".join(row_vals) + " \\\\\n\\hline\n"

            # Governorate summary row for 8-year table
            g_hist_vals = []
            for y in avail_years:
                vy = df_hist_g[df_hist_g['hydro_year'] == y]['annual_sum'].mean() if not df_hist_g[df_hist_g['hydro_year'] == y].empty else 0
                g_hist_vals.append(f"\\textbf{{{vy:.0f}}}" if not pd.isna(vy) and vy > 0 else "-")
            tab2_rows += f"\\textbf{{MOYENNE {clean_gouv.upper()}}} & \\textbf{{-}} & \\textbf{{{g_avg_moy:.0f}}} & " + " & ".join(g_hist_vals) + " \\\\\n\\hline\n"

            target_y = annee
            other_years = [y for y in avail_years if y != target_y]
            for _, srow in sub_curr_g.iterrows():
                sid = srow['id_station']
                snom = escape_latex(srow['station'])
                sub_sh = df_hist_g[df_hist_g['id_station'] == sid]
                v_target = sub_sh[sub_sh['hydro_year'] == target_y]['annual_sum'].mean() if not sub_sh[sub_sh['hydro_year'] == target_y].empty else None
                if v_target is not None and v_target > 0:
                    lower_years, higher_years = [], []
                    for y in other_years:
                        v_y = sub_sh[sub_sh['hydro_year'] == y]['annual_sum'].mean() if not sub_sh[sub_sh['hydro_year'] == y].empty else 0
                        if v_y > 0:
                            y_str = f"{y}-{y+1}"
                            if v_target > v_y: lower_years.append(y_str)
                            else: higher_years.append(y_str)
                    if not lower_years and not higher_years:
                        bullet = f"\\item Pour la station {snom}, seule l'année {target_y}-{target_y+1} est disponible."
                    elif not higher_years:
                        bullet = f"\\item Pour la station {snom}, l’année {target_y}-{target_y+1} a été plus pluvieuse que les autres années."
                    elif not lower_years:
                        bullet = f"\\item Pour la station {snom}, l’année {target_y}-{target_y+1} a été moins pluvieuse que les autres années."
                    else:
                        bullet = f"\\item Pour la station {snom}, l’année {target_y}-{target_y+1} a été plus pluvieuse que les années ({'; '.join(lower_years)}) et moins pluvieuse que les années ({'; '.join(higher_years)})."
                    comparison_bullets.append(bullet)
                else:
                    comparison_bullets.append(f"\\item Pour la station {snom}, données non disponibles pour l'année {target_y}-{target_y+1}.")

    list_comparisons_latex = "\n".join(comparison_bullets)

    apercu_intro_txt = f"l’ensemble du pays est caractérisé par les variations régionales suivantes :" if is_national else f"le Gouvernorat de {clean_gouv} est caractérisé par les observations suivantes :"
    tab1_title_txt = "Comparaison des pluies régionales à la moyenne" if is_national else f"Comparaison des pluies des stations du Gouvernorat de {clean_gouv} à la moyenne"
    tab1_col1_lbl = "RÉGION" if is_national else "STATION"
    tab2_col1_lbl = "RÉGION" if is_national else "STATION"

    apercu_climatique = r"""
\section*{1. Aperçu Sommaire sur la Pluviosité de l'Année """ + f"{annee}-{annee+1}" + r"""}
\addcontentsline{toc}{section}{1. Aperçu Sommaire sur la Pluviosité}

\subsection*{1.1. Totaux pluviométriques annuels}
Le total pluviométrique de l’année hydrologique """ + f"{annee}-{annee+1}" + r""" pour """ + apercu_intro_txt + r"""

\begin{itemize}
""" + list_items_latex + r"""\end{itemize}

\vspace{0.2cm}
\noindent Comparée à la moyenne interannuelle, la répartition de la pluviométrie pour l’année """ + f"{annee}-{annee+1}" + r""" se présente comme suit :

\begin{table}[H]
\centering
\caption{""" + tab1_title_txt + r"""}
\vspace{0.1cm}
\fontsize{7.5}{9}\selectfont
\begin{tabular}{|l|c|c|c|c|c|}
\hline
\textbf{""" + tab1_col1_lbl + r"""} & \textbf{Surf/Alt} & \textbf{Pluie (mm)} & \textbf{Moy (mm)} & \textbf{Écart (mm)} & \textbf{Écart (\%)} \\ \hline
""" + tab1_rows + r"""\end{tabular}
\end{table}

\subsection*{1.2. Analyse comparative des huit dernières années """ + f"{annee-7}-{annee-6} à {annee}-{annee+1}" + r"""}
Le tableau ci-dessous présentant les totaux pluviométriques pour les huit années (""" + f"{annee-7}-{annee-6} à {annee}-{annee+1}" + r""") montre que :
\begin{itemize}
""" + list_comparisons_latex + r"""
\end{itemize}

\begin{figure}[H]
\centering
\includegraphics[width=0.75\textwidth]{""" + path_comparaison + r"""}
\caption{Comparaison des pluviométries des huit dernières années}
\end{figure}

\vspace{0.2cm}
""" + missing_note_latex + r"""
\begin{table}[H]
\centering
\caption{Totaux pluviométriques des années disponibles (mm)}
\vspace{0.1cm}
\fontsize{7}{8.5}\selectfont
\begin{tabular}{|l|c|c|""" + ("c|" * len(avail_years)) + r"""}
\hline
\textbf{""" + tab2_col1_lbl + r"""} & \textbf{Surf/Alt} & \textbf{Moy} & """ + t2_headers + r""" \\ \hline
""" + tab2_rows + r"""\end{tabular}
\end{table}
\newpage
"""

    sommaire_et_tables = r"""
\tableofcontents
\newpage
\listoffigures
\newpage
\listoftables
\newpage
"""

    sec_mensuel = generate_section_13_mensuel(conn, annee, gouv=gouv)
    sec_saisonnier = generate_section_14_saisonnier(conn, annee, gouv=gouv) + generate_section_14_table7_cumule(conn, annee, gouv=gouv)

    sec_classes = r"""
\section{Répartition par Classe de Pluviométrie}
La figure ci-dessous compare la répartition statistique des stations selon les tranches de pluviométrie observées durant l'année hydrologique """ + f"{annee}-{annee+1}" + r""" par rapport à la moyenne historique des années antérieures.

\begin{figure}[H]
\centering
\includegraphics[width=0.92\textwidth]{""" + path_classes + r"""}
\caption{Répartition des stations selon la classe de pluviométrie (Comparaison Historique vs Année """ + f"{annee}-{annee+1}" + r""")}
\end{figure}

\newpage
"""

    sec_carto = r"""
\section{Cartographie Isohyète Mensuelle}
Cette section présente les cartes isohyètes pour les 12 mois de l'année hydrologique (4 cartes par page sous forme de subplots).
\vspace{0.2cm}

\begin{figure}[H]
\centering
\includegraphics[width=0.70\textwidth]{""" + path_group1 + r"""}
\caption{Précipitations Mensuelles (Septembre, Octobre, Novembre, Décembre)}
\end{figure}
\clearpage

\begin{figure}[H]
\centering
\includegraphics[width=0.70\textwidth]{""" + path_group2 + r"""}
\caption{Précipitations Mensuelles (Janvier, Février, Mars, Avril)}
\end{figure}
\clearpage

\begin{figure}[H]
\centering
\includegraphics[width=0.70\textwidth]{""" + path_group3 + r"""}
\caption{Précipitations Mensuelles (Mai, Juin, Juillet, Août)}
\end{figure}
\clearpage

\section{Cartographie Isohyète Saisonnière}
Cette section regroupe les cartes isohyètes des quatre saisons en une figure unique avec subplots.
\vspace{0.2cm}

\begin{figure}[H]
\centering
\includegraphics[width=0.70\textwidth]{""" + path_saisons + r"""}
\caption{Précipitations Saisonnières (Automne, Hiver, Printemps, Été)}
\end{figure}
\clearpage

\section{Répartition Géographique des Stations}
Cette carte présente l'implantation géographique de l'ensemble des stations pluviométriques actives retenues pour cet annuaire.
\vspace{0.2cm}

\begin{figure}[H]
\centering
\includegraphics[width=0.65\textwidth]{""" + path_stations + r"""}
\caption{Répartition des stations du réseau pluviométrique}
\end{figure}
\clearpage
"""

    if is_national:
        sec_journalier = r"""
\section*{2. Répertoire des stations pluviométriques de la Tunisie}
\addcontentsline{toc}{section}{2. Répertoire des stations pluviométriques de la Tunisie}
La présente publication présente toutes les observations pluviométriques journalières, mensuelles et
annuelles relevées au niveau de """ + str(nb_stations) + r""" stations pluviométriques réparties à travers tout le pays durant
l’année Hydrologique """ + f"{annee}-{annee+1}" + r""" qui s’étend du 1er Septembre """ + str(annee) + r""" au 31 Août """ + str(annee+1) + r""".

La répartition des postes pluviométriques est faite suivant les six régions naturelles :
\begin{itemize}
    \item \textbf{Nord Ouest} : Jendouba, Béja, Kef et Siliana ;
    \item \textbf{Nord Est} : Tunis, Ariana, Ben Arous, Manouba, Nabeul, Zaghouan et Bizerte ;
    \item \textbf{Centre Ouest} : Kairouan, Kasserine et Sidi Bouzid ;
    \item \textbf{Centre Est} : Sousse, Monastir, Mahdia et Sfax ;
    \item \textbf{Sud Ouest} : Gafsa, Tozeur et Kébili ;
    \item \textbf{Sud Est} : Gabès, Tataouine et Mednine.
\end{itemize}

A rappeler que le réseau hydrographique de tout le pays est subdivisé en 7 grands bassins portant
des numéros de codification allant de 3 à 9, le numéro 1 affecté aux bassins transfrontières avec le
pays voisin se trouvant à l’Ouest du pays, l’Algérie et le numéro 2 affecté aux bassins transfrontières
avec le pays voisin au Sud Est , la Libye ;
\begin{itemize}
    \item \textbf{Le bassin n°3} : couvre l’Extrême Nord de la Tunisie soit les domaines forestiers du Nord-Ouest et les régions du lac Ichkeul et de Bizerte.
    \item \textbf{Le bassin n°4} : comprend le bassin versant du Cap Bon et celui de Miliane.
    \item \textbf{Le bassin n°5} : correspond au bassin de la Mejerda.
    \item \textbf{Le bassin n°6} : couvre tout le centre de la Tunisie (Zéroud, Merguellil, Nebhana).
    \item \textbf{Le bassin n°7} : comprend le Sahel et Sfax.
    \item \textbf{Le bassin n°8} : s’étend de la limite Sud des bassins 6 et 7 (Centre et Sahel) jusqu’au Nord du Chott El Jerid.
    \item \textbf{Le bassin n°9} : couvre l’Extrême Sud jusqu’aux frontières Algériennes et Libyennes.
\end{itemize}

A l’intérieur de chaque bassin, les postes pluviométriques sont classés par ordre alphabétique et
portent des numéros de codifications composés de dix chiffres dont la signification est la suivante :
\begin{itemize}
    \item Le premier chiffre indique le continent Africain.
    \item Les deux premiers chiffres qui suivent indiquent le code du pays (48 pour la Tunisie) d’appartenance de la station.
    \item Les cinq chiffres suivants indiquent le N° mécanographique de la station avec comme premier chiffre le N° du bassin auquel appartient le poste.
    \item Les deux derniers chiffres indiquent le gouvernorat dans lequel se trouve le poste pluviométrique.
\end{itemize}

Les numéros correspondant à chaque gouvernorat sont les suivants :
\begin{table}[H]
\centering
\begin{tabular}{ll|ll}
\hline
\textbf{Code} & \textbf{Nom Gouvernorat} & \textbf{Code} & \textbf{Nom Gouvernorat} \\ \hline
11 & Tunis & 32 & Monastir \\
12 & Ariana & 33 & Mahdia \\
13 & Ben Arous & 34 & Sfax \\
14 & Manouba & 41 & Kairouan \\
15 & Nabeul & 42 & Kasserine \\
16 & Zaghouan & 43 & Sidi Bouzid \\
17 & Bizerte & 51 & Gabès \\
21 & Béja & 52 & Mednine \\
22 & Jendouba & 53 & Tataouine \\
23 & Le Kef & 61 & Gafsa \\
24 & Siliana & 62 & Tozeur \\
31 & Sousse & 63 & Kébili \\ \hline
\end{tabular}
\end{table}

Une liste complète des postes pluviométriques (numéro d’identification et le nom de la station avec Latitude, Longitude et Altitude correspondantes), est donnée dans les pages qui suivent :

"""
        df_st_list = df_stations.copy()
        df_st_list['norm_gouv'] = df_st_list['gouvernorat'].apply(normalize_string)
        
        for reg_name, reg_gouvs in REGIONS_NORM.items():
            sub = df_st_list[df_st_list['norm_gouv'].isin(reg_gouvs)].sort_values(by='nom')
            if not sub.empty:
                sec_journalier += r"""
\begin{longtable}{|l|p{5.5cm}|c|c|c|}
\caption{Liste des stations pluviométriques de la région """ + reg_name.title() + r"""} \\
\hline
\textbf{IDENTIFICATION} & \textbf{STATION} & \textbf{X UTM} & \textbf{Y UTM} & \textbf{ALTITUDE(m)} \\ \hline
\endfirsthead
\caption[]{Liste des stations pluviométriques de la région """ + reg_name.title() + r""" (suite)} \\
\hline
\textbf{IDENTIFICATION} & \textbf{STATION} & \textbf{X UTM} & \textbf{Y UTM} & \textbf{ALTITUDE(m)} \\ \hline
\endhead
"""
                for _, row in sub.iterrows():
                    sid = row['id_station']
                    nom = escape_latex(str(row['nom']).upper())
                    x = f"{float(row['lon']):.4f}".replace('.', ',') if pd.notna(row['lon']) and str(row['lon']).strip() != '' else "-"
                    y = f"{float(row['lat']):.3f}".replace('.', ',') if pd.notna(row['lat']) and str(row['lat']).strip() != '' else "-"
                    try:
                        alt = f"{float(row['altitude']):.0f}" if pd.notna(row['altitude']) and str(row['altitude']).strip() != '' else "-"
                    except:
                        alt = "-"
                    sec_journalier += f"{sid} & {nom} & {x} & {y} & {alt} \\\\\n"
                sec_journalier += r"""\hline
\end{longtable}
"""

        region_stats = [
            {'nom': 'NORD OUEST',   'superficie': 16517, 'gouvs': REGIONS_NORM['NORD OUEST']},
            {'nom': 'NORD EST',     'superficie': 11725, 'gouvs': REGIONS_NORM['NORD EST']},
            {'nom': 'CENTRE OUEST', 'superficie': 22184, 'gouvs': REGIONS_NORM['CENTRE OUEST']},
            {'nom': 'CENTRE EST',   'superficie': 13430, 'gouvs': REGIONS_NORM['CENTRE EST']},
            {'nom': 'SUD OUEST',    'superficie': 35761, 'gouvs': REGIONS_NORM['SUD OUEST']},
            {'nom': 'SUD EST',      'superficie': 55305, 'gouvs': REGIONS_NORM['SUD EST']}
        ]
        
        total_stations = len(df_stations)
        table_region_rows = ""
        for reg in region_stats:
            n_postes = df_st_list[df_st_list['norm_gouv'].isin(reg['gouvs'])].shape[0]
            couverture = int(round(reg['superficie'] / n_postes)) if n_postes > 0 else 0
            repartition = int(round((n_postes / total_stations) * 100)) if total_stations > 0 else 0
            table_region_rows += f"{reg['nom']} & {reg['superficie']} & {n_postes} & {couverture} & {repartition}\\% \\\\\n"
            
        tot_superficie = sum([r['superficie'] for r in region_stats])
        tot_couverture = int(round(tot_superficie / total_stations)) if total_stations > 0 else 0
        table_region_rows += f"\\textbf{{TUNISIE}} & \\textbf{{{tot_superficie}}} & \\textbf{{{total_stations}}} & \\textbf{{{tot_couverture}}} & \\textbf{{100\\%}} \\\\\n"

        bassin_counts = {}
        for _, row in df_stations.iterrows():
            sid = str(row['id_station'])
            if len(sid) >= 4:
                bassin = sid[3]
                bassin_counts[bassin] = bassin_counts.get(bassin, 0) + 1
        
        bassin_list_latex = ""
        for b in ['3', '4', '5', '6', '7', '8', '9']:
            count = bassin_counts.get(b, 0)
            if count > 0:
                pct = int(round((count / total_stations) * 100)) if total_stations > 0 else 0
                bassin_list_latex += f"\\item {count} postes pluviométriques au bassin n°{b}, soit {pct}\\% du total du réseau ;\n"

        sec_journalier += r"""
\newpage
\section*{3. FICHES PLUVIOMETRIQUES JOURNALIERES}
\addcontentsline{toc}{section}{3. FICHES PLUVIOMETRIQUES JOURNALIERES}
Il s’agit des tableaux des pluies journalières des """ + str(len(df_rain['id_station'].unique())) + r""" stations pluviométriques observées au cours de l’année hydrologique """ + f"{annee}-{annee+1}" + r""". Sur ces tableaux:
\begin{itemize}
    \item un point ( . ) indique un jour sec,
    \item un vide indique un relevé absent,
    \item une couleur grise indique un cumul ultérieur.
\end{itemize}
Au bas de chaque tableau, nous précisons :
\begin{itemize}
    \item Les totaux pluviométriques mensuels (complets ou Absents).
    \item Le nombre de jours de pluie dans l’année avec le rapport en (\%) du nombre de jours où la pluie est supérieure à 0 mm, 0.5mm et 10 mm.
    \item La date et la valeur de pluie quotidienne maximale ;
    \item Le total annuel pour les années complètes ou le total partiel pour les années incomplètes.
\end{itemize}

Pour l'année """ + f"{annee}-{annee+1}" + r""" on dénombre """ + str(total_stations) + r""" stations pluviométriques en service, réparties entre les bassins hydrographiques comme suit:
\begin{itemize}
""" + bassin_list_latex + r"""
\end{itemize}

Le tableau ci-dessous présente la répartition ainsi que la couverture des postes pluviométriques dans les régions naturelles du pays:

\begin{table}[H]
\centering
\begin{tabular}{|l|c|c|c|c|}
\hline
\textbf{REGION} & \textbf{Superficie (Km²)} & \textbf{Nombre de postes pluviométriques} & \textbf{Couverture Km²/poste} & \textbf{Répartition en \%} \\ \hline
""" + table_region_rows + r"""\hline
\end{tabular}
\end{table}

\newpage
"""
        gouv_to_region = {}
        for rname, gouvs in REGIONS_NORM.items():
            for g in gouvs:
                gouv_to_region[g] = rname

        REGION_ORDER = list(REGIONS_NORM.keys())

        for reg_name in REGION_ORDER:
            reg_gouvs_norm = REGIONS_NORM[reg_name]
            reg_mask = df_stations['gouvernorat'].apply(normalize_string).isin(reg_gouvs_norm)
            reg_df = df_stations[reg_mask]
            if reg_df.empty:
                continue

            reg_sids = reg_df['id_station'].tolist()
            reg_active = [s for s in reg_sids if s in df_rain['id_station'].values]
            if not reg_active:
                continue

            sec_journalier += r"""
\newpage
\thispagestyle{empty}
\vspace*{\fill}
\begin{center}
    {\Huge\bfseries """ + reg_name + r"""}\\[1cm]
    {\Large FICHES PLUVIOM\'{E}TRIQUES JOURNALI\`{E}RES}
\end{center}
\vspace*{\fill}
\newpage
"""

            gouv_groups = reg_df.groupby('gouv')
            for gname, g_df in gouv_groups:
                g_sids = g_df['id_station'].tolist()
                g_active = [s for s in g_sids if s in df_rain['id_station'].values]
                if not g_active:
                    continue

                g_snames = dict(zip(g_df['id_station'], g_df['nom']))
                g_daily_latex = generer_tableaux_journaliers_latex(conn, g_active, annee, g_snames)
                if not g_daily_latex.strip():
                    continue

                sec_journalier += f"\\subsection{{Gouvernorat de {escape_latex(gname)}}}\n"
                sec_journalier += r"""
\renewcommand{\arraystretch}{0.65}
\setlength{\tabcolsep}{1.2pt}
\tiny
""" + g_daily_latex + r"""
\newpage
"""
    else:
        sec_journalier = r"""
\section*{2. Répertoire des stations pluviométriques du Gouvernorat de """ + escape_latex(clean_gouv) + r"""}
\addcontentsline{toc}{section}{2. Répertoire des stations pluviométriques du Gouvernorat de """ + escape_latex(clean_gouv) + r"""}
La présente publication présente les observations pluviométriques journalières, mensuelles et
annuelles relevées au niveau des """ + str(nb_stations) + r""" stations pluviométriques du Gouvernorat de """ + escape_latex(clean_gouv) + r""" durant
l’année Hydrologique """ + f"{annee}-{annee+1}" + r""" qui s’étend du 1er Septembre """ + str(annee) + r""" au 31 Août """ + str(annee+1) + r""".

\begin{longtable}{|l|p{5.5cm}|c|c|c|}
\caption{Liste des stations pluviométriques du Gouvernorat de """ + escape_latex(clean_gouv) + r"""} \\
\hline
\textbf{IDENTIFICATION} & \textbf{STATION} & \textbf{X UTM} & \textbf{Y UTM} & \textbf{ALTITUDE(m)} \\ \hline
\endfirsthead
\caption[]{Liste des stations pluviométriques du Gouvernorat de """ + escape_latex(clean_gouv) + r""" (suite)} \\
\hline
\textbf{IDENTIFICATION} & \textbf{STATION} & \textbf{X UTM} & \textbf{Y UTM} & \textbf{ALTITUDE(m)} \\ \hline
\endhead
"""
        for _, row in df_stations.iterrows():
            sid = row['id_station']
            nom = escape_latex(str(row['nom']).upper())
            x = f"{float(row['lon']):.4f}".replace('.', ',') if pd.notna(row['lon']) and str(row['lon']).strip() != '' else "-"
            y = f"{float(row['lat']):.3f}".replace('.', ',') if pd.notna(row['lat']) and str(row['lat']).strip() != '' else "-"
            try:
                alt = f"{float(row['altitude']):.0f}" if pd.notna(row['altitude']) and str(row['altitude']).strip() != '' else "-"
            except:
                alt = "-"
            sec_journalier += f"{sid} & {nom} & {x} & {y} & {alt} \\\\\n"

        sec_journalier += r"""\hline
\end{longtable}

\newpage
\section*{3. FICHES PLUVIOMÉTRIQUES JOURNALIÈRES}
\addcontentsline{toc}{section}{3. FICHES PLUVIOMÉTRIQUES JOURNALIÈRES}
Il s’agit des tableaux des pluies journalières des """ + str(len(df_rain['id_station'].unique())) + r""" stations pluviométriques observées au cours de l’année hydrologique """ + f"{annee}-{annee+1}" + r""" dans le Gouvernorat de """ + escape_latex(clean_gouv) + r""". Sur ces tableaux:
\begin{itemize}
    \item un point ( . ) indique un jour sec,
    \item un vide indique un relevé absent,
    \item une couleur grise indique un cumul ultérieur.
\end{itemize}
Au bas de chaque tableau, nous précisons :
\begin{itemize}
    \item Les totaux pluviométriques mensuels (complets ou Absents).
    \item Le nombre de jours de pluie dans l’année avec le rapport en (\%) du nombre de jours où la pluie est supérieure à 0 mm, 0.5mm et 10 mm.
    \item La date et la valeur de pluie quotidienne maximale ;
    \item Le total annuel pour les années complètes ou le total partiel pour les années incomplètes.
\end{itemize}
\vspace{0.4cm}

\renewcommand{\arraystretch}{0.65}
\setlength{\tabcolsep}{1.2pt}
\tiny
""" + daily_latex + r"""
"""

    postamble = r"""
\end{document}
"""

    content = (preambule + page_garde + avant_propos + sommaire_et_tables +
               presentation_annuaire + apercu_climatique +
               sec_mensuel + sec_saisonnier + sec_classes + sec_carto + sec_journalier + postamble)

    with open(output_tex, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"✅ Fichier LaTeX généré : {output_tex}")

# ------------------------- 6. Compilation LaTeX -------------------------
def compile_latex(tex_file, output_pdf):
    for engine in ['pdflatex', 'lualatex', 'xelatex']:
        eng_path = shutil.which(engine)
        if eng_path:
            print(f"⚙️ Compilation avec {engine} (3 passes)...")
            success = True
            for i in range(3):
                cmd = [eng_path, '-interaction=nonstopmode', '-synctex=1', tex_file]
                result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
                if result.returncode != 0:
                    print(f"⚠️ Avertissement lors de la passe {i+1} de {engine}")
            base = os.path.splitext(tex_file)[0]
            if os.path.exists(f"{base}.pdf"):
                src_pdf = os.path.abspath(f"{base}.pdf")
                dst_pdf = os.path.abspath(output_pdf)
                if src_pdf != dst_pdf:
                    shutil.move(src_pdf, dst_pdf)
                print(f"🎉 PDF généré avec succès : {output_pdf}")
                return True
        else:
            print(f"⚠️ {engine} non trouvé.")
    return False

# ------------------------- Main -------------------------
def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        pass
    parser = argparse.ArgumentParser(description="Génération d'annuaire pluviométrique tunisien depuis PostgreSQL")
    parser.add_argument("--year", type=int, default=2018, help="Année hydrologique de début (ex: 2021)")
    parser.add_argument("--gouv", type=str, default="all", help="Nom du gouvernorat (ex: Beja, Tunis, ou 'all')")
    parser.add_argument("--output", type=str, default=None, help="Fichier PDF de sortie")
    parser.add_argument("--only-images", action="store_true", help="Génère uniquement les images et stoppe avant le LaTeX")
    args = parser.parse_args()

    if args.output is None:
        clean_gouv = normalize_string(args.gouv).capitalize() if args.gouv.lower() not in ('all', 'national') else 'National'
        args.output = f"Annuaire_{clean_gouv}_{args.year}_{args.year+1}.pdf"

    global IMG_DIR
    clean_gouv_name = normalize_string(args.gouv)
    IMG_DIR = f"images_temp_{clean_gouv_name}_{args.year}"
    os.makedirs(IMG_DIR, exist_ok=True)

    print("="*60)
    print(f"  ANNUAIRE PLUVIOMÉTRIQUE DE LA TUNISIE - GÉNÉRATEUR BDD")
    print(f"  Année: {args.year}-{args.year+1} | Filtrage: {args.gouv}")
    print("="*60)

    conn = connect_db()
    try:
        # Extraction
        df_stations = get_stations(conn, args.gouv)
        if df_stations.empty:
            print("❌ Aucune station trouvée pour les filtres spécifiés.")
            return

        s_ids = df_stations['id_station'].tolist()
        df_rain = get_rainfall_data(conn, s_ids, args.year)
        if df_rain.empty:
            print("❌ Aucune donnée de pluies trouvée dans la base de données pour cette année.")
            return

        # Calculs stats (incluant les métriques directes de yasra_data : moy_ et pct)
        stats = compute_stats_from_rainfall(df_rain, df_stations, conn=conn)
        
        # Spatial
        gdf_pays, gdf_gouv = get_spatial_data(conn)
        gdf_gouv_mask = get_gouv_shape(gdf_gouv, args.gouv) if args.gouv.lower() not in ('all', 'national') else None

        # Rendu des figures
        print("🎨 Rendu des graphiques et cartes...")
        generate_report_figures(stats, gdf_pays, gdf_gouv, gdf_gouv_mask, args.gouv, args.year, conn, s_ids)
        
        if args.only_images:
            print("📸 Mode --only-images activé : génération des cartes terminée. Arrêt.")
            return

        # LaTeX relevés journaliers
        print("📋 Génération du code LaTeX des relevés journaliers...")
        s_names = dict(zip(df_stations['id_station'], df_stations['nom']))
        active_stations = df_rain['id_station'].unique().tolist()
        daily_latex = generer_tableaux_journaliers_latex(conn, active_stations, args.year, s_names)

        # LaTeX complet
        output_tex = args.output.replace('.pdf', '.tex')
        write_complete_latex(stats, daily_latex, args.gouv, args.year, output_tex, conn, df_stations, df_rain)

        # Compilation
        if compile_latex(output_tex, args.output):
            # Nettoyage
            for ext in ['.aux', '.log', '.out', '.toc', '.synctex.gz', '.lof', '.lot', output_tex]:
                f = output_tex.replace('.tex', ext)
                if os.path.exists(f):
                    try:
                        os.remove(f)
                    except Exception:
                        pass
            # commenté pour que le Chatbot puisse afficher les cartes
            # if os.path.exists(IMG_DIR):
            #     shutil.rmtree(IMG_DIR, ignore_errors=True)
            print("🧹 Nettoyage terminé (images conservées pour le Chatbot).")
            print("🎉 Tout s'est déroulé avec succès !")
        else:
            print("❌ Échec de la compilation LaTeX.")
            
    finally:
        conn.close()

if __name__ == "__main__":
    main()
