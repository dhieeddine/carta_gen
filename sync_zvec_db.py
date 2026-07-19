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
    
    # 4. Traiter et synchroniser les STATIONS (Stations_Base)
    print("[FETCH] Récupération des stations de stations_base...")
    try:
        query = """
            SELECT id_station, nom, district, localite, bassin, riviere, gestionnaire 
            FROM stations_base;
        """
        df_stations = pd.read_sql(query, engine)
        print(f"[INFO] {len(df_stations)} stations trouvées. Génération des embeddings...")
        
        station_docs = []
        for index, row in df_stations.iterrows():
            # Remplacer les valeurs nulles
            nom = str(row['nom'] or '').strip()
            district = str(row['district'] or '').strip()
            localite = str(row['localite'] or '').strip()
            bassin = str(row['bassin'] or '').strip()
            riviere = str(row['riviere'] or '').strip()
            gestionnaire = str(row['gestionnaire'] or '').strip()
            id_station = row['id_station']
            
            if not nom or id_station is None:
                continue
                
            # Texte sémantique descriptif de la station
            text_desc = (
                f"Station: {nom} | ID: {id_station} | District: {district} | "
                f"Localité: {localite} | Bassin: {bassin} | Rivière: {riviere} | "
                f"Gestionnaire: {gestionnaire}"
            )
            
            # Encoder
            embedding = model.encode(text_desc).tolist()
            
            station_docs.append({
                "id_station": int(id_station),
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
            "table_name": "yasra_data",
            "description": "Contient les précipitations interpolées mensuelles (janv, fev, mar, avr, mai, juin, juil, aout, sept, octo, nove, dece), saisonnières (hiver, print, ete, auto) et annuelles (total, moy_). Utile pour générer des isohyètes globales ou régionales."
        },
        {
            "table_name": "pluies",
            "description": "Données brutes de précipitations ou de hauteurs de pluie journalières et horaires enregistrées par les capteurs. Colonnes principales : id_station, date, valeur (pluie en mm), capteur."
        },
        {
            "table_name": "cotes",
            "description": "Contient les hauteurs d'eau limnimétriques mesurées au cours du temps dans les stations hydrologiques. Colonnes principales : id_station, date, valeur (hauteur en m)."
        },
        {
            "table_name": "debits",
            "description": "Mesures temporelles des débits des oueds et cours d'eau. Colonnes principales : id_station, date, valeur (débit en m³/s)."
        },
        {
            "table_name": "stations_base",
            "description": "Fiche descriptive et administrative de toutes les stations (pluvio, météo ou hydro). Contient : id_station, nom, latitude, longitude, altitude, district, localite, bassin, riviere, gestionnaire."
        },
        {
            "table_name": "capteurs",
            "description": "Index de tous les capteurs (type_station, id_station, capteur, table, nature, description, unite)."
        },
        {
            "table_name": "jaugeages",
            "description": "Contient les mesures de jaugeage en débit et hauteur d'eau pour calibrer les courbes de tarage. Colonnes principales : id_station, date, hauteur, debit, methode."
        },
        {
            "table_name": "equipements",
            "description": "Liste et état d'installation des équipements sur chaque station. Colonnes : id_station, type_equipement, date_installation, date_retrait, etat."
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
