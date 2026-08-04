# -*- coding: utf-8 -*-
"""
cartagen/infrastructure/database/mdb_ingest.py
===============================================
Service d'ingestion centralisé pour bases MS Access (.mdb / .accdb)
vers la base de données PostgreSQL unifiée de la DGRE.
"""

import os
import sys
import traceback
from datetime import datetime
from typing import Optional, Dict, Any, List

import pyodbc
import psycopg2
from psycopg2.extras import execute_values


class MdbIngestionService:
    """Service d'ingestion et de normalisation des bases Access régionales vers PostgreSQL."""

    def __init__(self, database_url: str):
        self.database_url = database_url
        self._init_database_tables()

    def _get_pg_connection(self):
        return psycopg2.connect(self.database_url)

    def _init_database_tables(self):
        """Initialise la structure des tables PostgreSQL si elles n'existent pas encore."""
        sql = """
        CREATE TABLE IF NOT EXISTS ann_stations (
            id SERIAL PRIMARY KEY,
            gouvernorat TEXT NOT NULL,
            source_mdb TEXT NOT NULL,
            type_station VARCHAR(50),
            id_station TEXT NOT NULL,
            nom TEXT,
            latitude DOUBLE PRECISION,
            longitude DOUBLE PRECISION,
            altitude DOUBLE PRECISION,
            bassin TEXT,
            grand_bassin TEXT,
            riviere TEXT,
            debut_activite DATE,
            UNIQUE (gouvernorat, id_station, source_mdb)
        );

        CREATE TABLE IF NOT EXISTS ann_pluies (
            id BIGSERIAL PRIMARY KEY,
            gouvernorat TEXT NOT NULL,
            source_mdb TEXT NOT NULL,
            id_station TEXT NOT NULL,
            capteur TEXT,
            date_obs TIMESTAMP WITHOUT TIME ZONE NOT NULL,
            valeur_mm DOUBLE PRECISION,
            origine TEXT,
            qualite TEXT,
            nature TEXT
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_ann_pluies_unique 
        ON ann_pluies (gouvernorat, id_station, date_obs);

        CREATE TABLE IF NOT EXISTS ann_debits (
            id BIGSERIAL PRIMARY KEY,
            gouvernorat TEXT NOT NULL,
            source_mdb TEXT NOT NULL,
            id_station TEXT NOT NULL,
            capteur TEXT,
            date_obs TIMESTAMP WITHOUT TIME ZONE NOT NULL,
            valeur_m3s DOUBLE PRECISION,
            origine TEXT,
            qualite TEXT
        );

        CREATE TABLE IF NOT EXISTS ann_jaugeages (
            id BIGSERIAL PRIMARY KEY,
            gouvernorat TEXT NOT NULL,
            source_mdb TEXT NOT NULL,
            id_station TEXT NOT NULL,
            date_jaug TIMESTAMP WITHOUT TIME ZONE NOT NULL,
            hauteur_m DOUBLE PRECISION,
            debit_m3s DOUBLE PRECISION,
            commentaire TEXT
        );

        CREATE TABLE IF NOT EXISTS ann_ingestion_log (
            id SERIAL PRIMARY KEY,
            horodatage TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
            gouvernorat TEXT,
            fichier_mdb TEXT,
            nb_stations INT DEFAULT 0,
            nb_pluies BIGINT DEFAULT 0,
            nb_debits BIGINT DEFAULT 0,
            nb_jaugeages INT DEFAULT 0,
            statut TEXT,
            erreur TEXT
        );
        """
        try:
            with self._get_pg_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql)
                conn.commit()
        except Exception as e:
            print(f"[MDB Ingest] Info vérification des tables PostgreSQL : {repr(e)}")

    def _open_mdb(self, mdb_path: str):
        drivers = [d for d in pyodbc.drivers() if 'access' in d.lower()]
        if not drivers:
            raise RuntimeError("Aucun pilote ODBC Microsoft Access ('Microsoft Access Driver (*.mdb, *.accdb)') n'est installé sur cette machine.")
        driver = drivers[0]
        conn_str = (
            f"Driver={{{driver}}};"
            f"DBQ={mdb_path};"
            f"ExtendedAnsiSQL=1;"
        )
        return pyodbc.connect(conn_str, timeout=30)

    def _get_mdb_tables(self, mdb_conn) -> List[str]:
        cursor = mdb_conn.cursor()
        return [row.table_name for row in cursor.tables(tableType="TABLE")]

    def _safe_float(self, val):
        try:
            return float(val) if val is not None else None
        except (TypeError, ValueError):
            return None

    def _safe_date(self, val):
        if val is None:
            return None
        if isinstance(val, datetime):
            return val.date()
        return None

    def ingest_mdb_file(self, mdb_path: str, gouvernorat: Optional[str] = None, date_debut: Optional[datetime] = None) -> Dict[str, Any]:
        """Ingère un fichier MDB / ACCDB régional et insère ses données dans PostgreSQL."""
        if not os.path.exists(mdb_path):
            return {"success": False, "error": f"Le fichier spécifié n'existe pas : {mdb_path}"}

        if date_debut is None:
            date_debut = datetime(2010, 1, 1)

        mdb_name = os.path.basename(mdb_path)
        log_entry = {
            "gouvernorat": gouvernorat,
            "fichier": mdb_name,
            "nb_s": 0, "nb_p": 0, "nb_d": 0, "nb_j": 0,
            "statut": "EN_COURS", "erreur": ""
        }

        try:
            mdb_conn = self._open_mdb(mdb_path)
            tables = self._get_mdb_tables(mdb_conn)

            # Extraction EXCLUSIVE de la table des Pluies (pluies, pluie, pluviometrie, etc.)
            p_rows = []
            p_table = next((t for t in tables if t.lower() in ["pluies", "pluie", "pluviometrie", "donnees_pluies", "pluies_base"]), None)
            if p_table:
                cur = mdb_conn.cursor()
                cur.execute(f"SELECT * FROM {p_table} WHERE 1=0")
                cols = [desc[0] for desc in cur.description]
                id_col = next((c for c in cols if c.lower() in ["id_station", "code_st", "num_poste", "idstation", "code"]), cols[0])
                dt_col = next((c for c in cols if c.lower() in ["date", "date_obs", "horodatage", "date_mesure"]), cols[1] if len(cols) > 1 else cols[0])
                val_col = next((c for c in cols if c.lower() in ["valeur", "valeur_mm", "hauteur", "pluie_mm", "p_mm", "pluie"]), cols[2] if len(cols) > 2 else cols[0])
                
                try:
                    cur.execute(f"SELECT {id_col}, {dt_col}, {val_col} FROM {p_table} WHERE {dt_col} >= ?", (date_debut,))
                except Exception:
                    cur.execute(f"SELECT {id_col}, {dt_col}, {val_col} FROM {p_table}")

                raw_tuples = []
                for row in cur.fetchall():
                    if row[1] is not None:
                        raw_tuples.append((
                            str(row[0] or ""),
                            row[1],
                            self._safe_float(row[2])
                        ))

            mdb_conn.close()

            # Auto-détection du gouvernorat :
            # 1. Via l'ID de la première station dans ann_stations
            # 2. Sinon via le nom du fichier (ex: Beja_2022.mdb)
            # 3. Sinon fallback sur "Inconnu"
            sample_st_id = raw_tuples[0][0] if raw_tuples else None
            detected_gouv = None

            if sample_st_id:
                try:
                    with self._get_pg_connection() as conn:
                        with conn.cursor() as cur:
                            cur.execute(
                                "SELECT gouvernorat FROM ann_stations WHERE id_station = %s LIMIT 1",
                                (sample_st_id,)
                            )
                            res = cur.fetchone()
                            if res and res[0]:
                                detected_gouv = res[0]
                except Exception as check_e:
                    print(f"[MDB Ingest] Avertissement vérification station {sample_st_id}: {check_e}")

            if detected_gouv:
                final_gouv = detected_gouv
            elif gouvernorat and gouvernorat.strip():
                final_gouv = gouvernorat
            else:
                # Tentative d'extraction depuis le nom du fichier (ex: Beja_pluies.mdb)
                name_part = mdb_name.split('_')[0].split('.')[0]
                final_gouv = name_part.capitalize() if name_part else "Inconnu"

            p_rows = [
                (final_gouv, mdb_name, st_id, "Pluie", dt_obs, val_mm, "MDB_IMPORT", "VALIDE", "")
                for (st_id, dt_obs, val_mm) in raw_tuples
            ]
            log_entry["gouvernorat"] = final_gouv

            # Statistiques du rapport de mise à jour
            nb_inserted = len(p_rows)
            min_date_str = "N/A"
            max_date_str = "N/A"
            stations_impacted = 0

            if p_rows:
                dates = [r[4] for r in p_rows if r[4] is not None]
                if dates:
                    min_date_str = str(min(dates))[:10]
                    max_date_str = str(max(dates))[:10]
                unique_st = {r[2] for r in p_rows if r[2]}
                stations_impacted = len(unique_st)

            # Deduplication en mémoire Python des lignes du fichier MDB avant insertion
            seen_keys = set()
            unique_p_rows = []
            for r in p_rows:
                # r format: (gouvernorat, mdb_name, id_station, "Pluie", date_obs, valeur_mm, origine, qualite, nature)
                k = (r[0], r[2], r[4])
                if k not in seen_keys:
                    seen_keys.add(k)
                    unique_p_rows.append(r)
            p_rows = unique_p_rows

            # Insertion exclusive dans la table ann_pluies de PostgreSQL (Union dédupliquée)
            inserted_count = 0
            with self._get_pg_connection() as pg_conn:
                if p_rows:
                    sql_p = """INSERT INTO ann_pluies
                        (gouvernorat, source_mdb, id_station, capteur, date_obs,
                         valeur_mm, origine, qualite, nature) VALUES %s
                        ON CONFLICT (gouvernorat, id_station, date_obs) DO NOTHING"""
                    with pg_conn.cursor() as cur:
                        try:
                            execute_values(cur, sql_p, p_rows, page_size=2000)
                        except Exception as conf_e:
                            pg_conn.rollback()
                            print(f"[MDB Ingest] Purge des doublons existants et création de l'index d'unicité...")
                            # 1. Purger les doublons existants dans la table PostgreSQL
                            cur.execute("""
                                DELETE FROM ann_pluies a
                                USING ann_pluies b
                                WHERE a.id > b.id
                                  AND a.gouvernorat = b.gouvernorat
                                  AND a.id_station = b.id_station
                                  AND a.date_obs = b.date_obs;
                            """)
                            # 2. Créer l'index d'unicité
                            cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_ann_pluies_unique ON ann_pluies (gouvernorat, id_station, date_obs);")
                            pg_conn.commit()
                            # 3. Ré-essayer l'insertion
                            execute_values(cur, sql_p, p_rows, page_size=2000)

                        inserted_count = cur.rowcount if cur.rowcount >= 0 else len(p_rows)
                    log_entry["nb_p"] = inserted_count

                pg_conn.commit()

            log_entry["statut"] = "SUCCES"
            self._log_to_db(final_gouv, mdb_name, 0, log_entry["nb_p"], 0, 0, "SUCCES", "")
            
            return {
                "success": True,
                "gouvernorat": final_gouv,
                "fichier": mdb_name,
                "nb_stations": stations_impacted,
                "nb_pluies": inserted_count,
                "date_min": min_date_str,
                "date_max": max_date_str,
                "message": f"Union réussie pour {final_gouv} : {inserted_count} nouveaux relevés de la table 'pluies' ajoutés à 'ann_pluies'."
            }

        except Exception as e:
            err_msg = traceback.format_exc()
            self._log_to_db(gouvernorat, mdb_name, 0, 0, 0, 0, "ERREUR", str(e))
            return {
                "success": False,
                "gouvernorat": gouvernorat,
                "fichier": mdb_name,
                "error": f"Erreur d'ingestion : {str(e)}",
                "traceback": err_msg
            }

    def _log_to_db(self, gouvernorat, fichier, nb_s, nb_p, nb_d, nb_j, statut, erreur=""):
        try:
            with self._get_pg_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO ann_ingestion_log
                        (gouvernorat, fichier_mdb, nb_stations, nb_pluies, nb_debits, nb_jaugeages, statut, erreur)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """, (gouvernorat, fichier, nb_s, nb_p, nb_d, nb_j, statut, erreur))
                conn.commit()
        except Exception:
            pass
