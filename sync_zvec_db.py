# -*- coding: utf-8 -*-

import os
import sys
import pandas as pd
import sqlalchemy
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from cartagen.infrastructure.database.vector_manager import VectorManager

# Charger l'environnement
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:dhiadhia@localhost:5432/dgre_db")
WORKSPACE_ROOT = os.getenv("WORKSPACE_ROOT", r"D:\Desktop\stage_dgre\carta_gen")

def main():
    print("[SYNC] Initialisation du pipeline de synchronisation Zvec...")
    
    # 1. Connexion à PostgreSQL
    try:
        engine = sqlalchemy.create_engine(DATABASE_URL)
        # Tester la connexion
        with engine.connect() as conn:
            print("[SUCCESS] Connexion à PostgreSQL établie avec succès.")
    except Exception as e:
        print(f"[ERROR] Erreur lors de la connexion à PostgreSQL : {e}")
        sys.exit(1)
        
    # 2. Charger le modèle d'embedding léger (all-MiniLM-L6-v2, dimension=384)
    print("[MODEL] Chargement du modèle de phrase sentence-transformers...")
    try:
        model = SentenceTransformer('all-MiniLM-L6-v2')
        print("[SUCCESS] Modèle chargé avec succès.")
    except Exception as e:
        print(f"[ERROR] Impossible de charger le modèle : {e}")
        sys.exit(1)
        
    # 3. Initialiser le gestionnaire vectoriel
    v_manager = VectorManager(WORKSPACE_ROOT)
    print("[RESET] Réinitialisation des collections Zvec...")
    v_manager.initialize_collections(dimension=384)
    
    # 4. Traiter et synchroniser les STATIONS (ann_stations)
    print("[FETCH] Récupération des stations de ann_stations...")
    try:
        query = """
            SELECT id_station, nom, gouvernorat, bassin, grand_bassin, riviere, altitude 
            FROM ann_stations;
        """
        df_stations = pd.read_sql(query, engine)
        print(f"[INFO] {len(df_stations)} stations trouvées. Génération des embeddings...")
        
        station_docs = []
        for index, row in df_stations.iterrows():
            # Remplacer les valeurs nulles
            nom = str(row['nom'] or '').strip()
            gouvernorat = str(row['gouvernorat'] or '').strip()
            bassin = str(row['bassin'] or '').strip()
            grand_bassin = str(row['grand_bassin'] or '').strip()
            riviere = str(row['riviere'] or '').strip()
            altitude = row['altitude']
            id_station = str(row['id_station'] or '').strip()
            
            if not nom or not id_station:
                continue
                
            # Texte sémantique descriptif de la station
            text_desc = (
                f"Station: {nom} | ID: {id_station} | Gouvernorat: {gouvernorat} | "
                f"Bassin: {bassin} | Grand Bassin: {grand_bassin} | Rivière: {riviere} | "
                f"Altitude: {altitude}"
            )
            
            # Encoder
            embedding = model.encode(text_desc).tolist()
            
            station_docs.append({
                "id_station": id_station,
                "nom": nom,
                "embedding": embedding
            })
            
        if station_docs:
            v_manager.insert_stations(station_docs)
            print(f"[SUCCESS] {len(station_docs)} stations indexées dans Zvec.")
        else:
            print("[WARNING] Aucune station valide à indexer.")
            
    except Exception as e:
        print(f"[ERROR] Erreur lors de l'indexation des stations : {e}")
 
    # 5. Traiter et synchroniser les SCHÉMAS DE TABLES
    print("[FETCH] Préparation de l'indexation des schémas de base de données...")
    schemas = [
        {
            "table_name": "ann_pluies",
            "description": "Données unifiées de précipitations journalières, mensuelles et annuelles de tous les gouvernorats tunisiens (2015-2024). Précipitations (valeur_mm) par date_obs. TOUJOURS utiliser cette table jointe avec ann_stations pour extraire la pluie et générer des cartes d'isohyètes ou des analyses."
        },
        {
            "table_name": "ann_stations",
            "description": "Référentiel unifié de toutes les stations des annuaires hydrologiques (2015-2024). Colonnes : id, gouvernorat, source_mdb, type_station, id_station, nom, latitude, longitude, altitude, bassin, grand_bassin, riviere, debut_activite. 3715 stations couvrant 24 gouvernorats."
        },
        {
            "table_name": "ann_debits",
            "description": "Débits journaliers unifiés de tous les gouvernorats (2015-2024). Colonnes : id, gouvernorat, source_mdb, id_station, capteur, date_obs (TIMESTAMP), valeur_m3s (m3/s), origine, qualite. ~848k lignes. Jointure avec ann_stations via id_station + gouvernorat."
        },
        {
            "table_name": "ann_jaugeages",
            "description": "Jaugeages de terrain unifiés (2015-2024). Colonnes : id, gouvernorat, source_mdb, id_station, date_jaug (TIMESTAMP), hauteur_m (m), debit_m3s (m3/s), commentaire. ~4700 lignes."
        },
        {
            "table_name": "capteurs",
            "description": "Index de tous les capteurs (type_station, id_station, capteur, table, nature, description, unite)."
        },
        {
            "table_name": "isohyet_map_standard_template",
            "description": (
                "Code Python de référence pour générer des cartes isohyètes normalisées (generate_isohyet_map) avec interpolation IDW, "
                "désactivation de la notation scientifique 1e6 sur les axes UTM (ScalarFormatter(useOffset=False).set_scientific(False)), "
                "palette standard de 8 couleurs (du bleu foncé pour le max vers le vert, le jaune, le rouge et le 1er intervalle 'none' sans couleur: "
                "['none', '#ff0000', '#ffff00', '#90ee90', '#228b22', '#4292c6', '#2171b5', '#08306b']), "
                "et niveaux par catégories de période (<1 mois: [0, 5, 10, 20, 30, 50, 75, 100, 150] (<5 à >100 mm), "
                "1 mois à <1 an: [0, 20, 50, 75, 100, 150, 200, 250, 350] (<20 à >250 mm), "
                ">=1 an: [0, 50, 100, 200, 400, 600, 800, 1000, 1200] (<50 à >1200 mm)), "
                "boussole / rose des vents (N, S, E, O) et légende par Patches."
            )
        }
    ]
    
    schema_docs = []
    for schema_item in schemas:
        text_desc = f"Table: {schema_item['table_name']} | Description: {schema_item['description']}"
        embedding = model.encode(text_desc).tolist()
        schema_docs.append({
            "table_name": schema_item["table_name"],
            "description": schema_item["description"],
            "embedding": embedding
        })
        
    try:
        v_manager.insert_schemas(schema_docs)
        print(f"[SUCCESS] {len(schema_docs)} schémas de table indexés dans Zvec.")
    except Exception as e:
        print(f"[ERROR] Erreur lors de l'indexation des schémas : {e}")
 
    print("[COMPLETE] Synchronisation Zvec terminée avec succès !")

if __name__ == "__main__":
    main()
