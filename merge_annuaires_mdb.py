# -*- coding: utf-8 -*-
"""
merge_annuaires_mdb.py
======================
Extraction et fusion des données hydrologiques des fichiers .mdb
(bases HYDRAS) de tous les gouvernorats vers une base PostgreSQL unifiée.

Données extraites : Pluies, Débits, Jaugeages, Stations_Base
Filtre temporel   : à partir du 01/01/2015 jusqu'à la dernière date disponible

Gouvernorats traités : 24 gouvernorats (E:\ann2023-2024\*)
"""

import os
import sys
import glob
import traceback
from datetime import datetime

import pyodbc
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────

# Charger les variables d'environnement (.env du projet)
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

# Date de début (filtrage)
DATE_DEBUT = datetime(2015, 1, 1)

# Répertoire racine des annuaires MDB
ANN_ROOT = r"E:\ann2023-2024"

# Liste complète des gouvernorats
GOUVERNORATS = [
    "Mahdia", "Manouba", "Mednine", "Monastir", "Nabeul",
    "Sfax", "Sidi bouzid", "siliana", "sousse", "Tatouine",
    "Tozeur", "Tunis", "Zaghouan", "Ariana", "Beja",
    "Ben arous", "Bizerte", "Gabes", "Gafsa", "jandouba",
    "Kairouan", "Kassrine", "Kebeli", "Kef"
]

# URL de la base PostgreSQL de destination (depuis .env)
PG_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/cartagen")

# Taille des lots d'insertion
BATCH_SIZE = 5000


# ─────────────────────────────────────────────────────────────────────────────
# CONNEXION POSTGRESQL
# ─────────────────────────────────────────────────────────────────────────────

def get_pg_connection():
    """Ouvre une connexion PostgreSQL depuis DATABASE_URL."""
    url = PG_URL.replace("postgresql://", "").replace("postgres://", "")
    if "@" in url:
        creds, rest = url.split("@", 1)
        user, password = creds.split(":", 1) if ":" in creds else (creds, "")
        host_port, dbname = rest.rsplit("/", 1)
        host, port = host_port.split(":") if ":" in host_port else (host_port, "5432")
    else:
        user, password, host, port, dbname = "postgres", "postgres", "localhost", "5432", url

    return psycopg2.connect(
        host=host, port=int(port), dbname=dbname,
        user=user, password=password,
        options="-c client_encoding=UTF8"
    )


# ─────────────────────────────────────────────────────────────────────────────
# CRÉATION DES TABLES POSTGRESQL
# ─────────────────────────────────────────────────────────────────────────────

CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS ann_stations (
    id               SERIAL PRIMARY KEY,
    gouvernorat      TEXT NOT NULL,
    source_mdb       TEXT NOT NULL,
    type_station     VARCHAR(5),
    id_station       TEXT NOT NULL,
    nom              TEXT,
    latitude         DOUBLE PRECISION,
    longitude        DOUBLE PRECISION,
    altitude         DOUBLE PRECISION,
    bassin           TEXT,
    grand_bassin     TEXT,
    riviere          TEXT,
    debut_activite   DATE,
    UNIQUE (gouvernorat, id_station, source_mdb)
);

CREATE TABLE IF NOT EXISTS ann_pluies (
    id           BIGSERIAL PRIMARY KEY,
    gouvernorat  TEXT NOT NULL,
    source_mdb   TEXT NOT NULL,
    id_station   TEXT NOT NULL,
    capteur      TEXT,
    date_obs     TIMESTAMP NOT NULL,
    valeur_mm    DOUBLE PRECISION,
    origine      TEXT,
    qualite      TEXT,
    nature       TEXT
);
CREATE INDEX IF NOT EXISTS idx_ann_pluies_date    ON ann_pluies (date_obs);
CREATE INDEX IF NOT EXISTS idx_ann_pluies_station ON ann_pluies (id_station);
CREATE INDEX IF NOT EXISTS idx_ann_pluies_gouv    ON ann_pluies (gouvernorat);

CREATE TABLE IF NOT EXISTS ann_debits (
    id           BIGSERIAL PRIMARY KEY,
    gouvernorat  TEXT NOT NULL,
    source_mdb   TEXT NOT NULL,
    id_station   TEXT NOT NULL,
    capteur      TEXT,
    date_obs     TIMESTAMP NOT NULL,
    valeur_m3s   DOUBLE PRECISION,
    origine      TEXT,
    qualite      TEXT
);
CREATE INDEX IF NOT EXISTS idx_ann_debits_date    ON ann_debits (date_obs);
CREATE INDEX IF NOT EXISTS idx_ann_debits_station ON ann_debits (id_station);
CREATE INDEX IF NOT EXISTS idx_ann_debits_gouv    ON ann_debits (gouvernorat);

CREATE TABLE IF NOT EXISTS ann_jaugeages (
    id              BIGSERIAL PRIMARY KEY,
    gouvernorat     TEXT NOT NULL,
    source_mdb      TEXT NOT NULL,
    id_station      TEXT NOT NULL,
    date_jaug       TIMESTAMP,
    hauteur_m       DOUBLE PRECISION,
    debit_m3s       DOUBLE PRECISION,
    commentaire     TEXT
);
CREATE INDEX IF NOT EXISTS idx_ann_jaugeages_date    ON ann_jaugeages (date_jaug);
CREATE INDEX IF NOT EXISTS idx_ann_jaugeages_station ON ann_jaugeages (id_station);

CREATE TABLE IF NOT EXISTS ann_ingestion_log (
    id              SERIAL PRIMARY KEY,
    horodatage      TIMESTAMP DEFAULT NOW(),
    gouvernorat     TEXT,
    fichier_mdb     TEXT,
    nb_stations     INT DEFAULT 0,
    nb_pluies       BIGINT DEFAULT 0,
    nb_debits       BIGINT DEFAULT 0,
    nb_jaugeages    INT DEFAULT 0,
    statut          TEXT,
    erreur          TEXT
);
"""


# ─────────────────────────────────────────────────────────────────────────────
# CONNEXION ACCESS (MDB)
# ─────────────────────────────────────────────────────────────────────────────

def open_mdb(mdb_path):
    conn_str = (
        f"Driver={{Microsoft Access Driver (*.mdb, *.accdb)}};"
        f"DBQ={mdb_path};"
        f"ExtendedAnsiSQL=1;"
    )
    return pyodbc.connect(conn_str, timeout=30)


def get_mdb_tables(mdb_conn):
    cursor = mdb_conn.cursor()
    return [row.table_name for row in cursor.tables(tableType="TABLE")]


# ─────────────────────────────────────────────────────────────────────────────
# UTILITAIRES
# ─────────────────────────────────────────────────────────────────────────────

def _safe_float(val):
    try:
        return float(val) if val is not None else None
    except (TypeError, ValueError):
        return None

def _safe_date(val):
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.date()
    return None

def log_progress(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


# ─────────────────────────────────────────────────────────────────────────────
# EXTRACTION
# ─────────────────────────────────────────────────────────────────────────────

def extract_stations(mdb_conn, gouvernorat, mdb_name):
    cursor = mdb_conn.cursor()
    tables = get_mdb_tables(mdb_conn)
    if "Stations_Base" not in tables:
        return []
    cursor.execute("""
        SELECT Type_Station, Id_Station, Nom, Latitude, Longitude, Altitude,
               Bassin, GrandBassin, Riviere, Debut_Activite
        FROM Stations_Base
    """)
    cols = [d[0] for d in cursor.description]
    rows = []
    for row in cursor.fetchall():
        r = dict(zip(cols, row))
        rows.append((
            gouvernorat, mdb_name,
            str(r.get("Type_Station") or ""),
            str(r.get("Id_Station") or ""),
            str(r.get("Nom") or ""),
            _safe_float(r.get("Latitude")),
            _safe_float(r.get("Longitude")),
            _safe_float(r.get("Altitude")),
            str(r.get("Bassin") or ""),
            str(r.get("GrandBassin") or ""),
            str(r.get("Riviere") or ""),
            _safe_date(r.get("Debut_Activite")),
        ))
    return rows


def extract_pluies(mdb_conn, gouvernorat, mdb_name, date_debut):
    cursor = mdb_conn.cursor()
    tables = get_mdb_tables(mdb_conn)
    if "Pluies" not in tables:
        return []
    cols_info = [row.column_name for row in cursor.columns(table="Pluies")]
    has_nature = "Nature" in cols_info
    if has_nature:
        cursor.execute("SELECT Id_Station, Capteur, Date, Valeur, Origine, Qualite, Nature FROM Pluies WHERE Date >= ?", (date_debut,))
    else:
        cursor.execute("SELECT Id_Station, Capteur, Date, Valeur, Origine, Qualite FROM Pluies WHERE Date >= ?", (date_debut,))
    rows = []
    for row in cursor.fetchall():
        if has_nature:
            id_st, cap, dt, val, ori, qual, nat = row
        else:
            id_st, cap, dt, val, ori, qual = row; nat = None
        rows.append((gouvernorat, mdb_name, str(id_st or ""), str(cap or ""), dt,
                     _safe_float(val), str(ori or ""), str(qual or ""), str(nat or "")))
    return rows


def extract_debits(mdb_conn, gouvernorat, mdb_name, date_debut):
    cursor = mdb_conn.cursor()
    tables = get_mdb_tables(mdb_conn)
    if "Debits" not in tables:
        return []
    cursor.execute("SELECT Id_Station, Capteur, Date, Valeur, Origine, Qualite FROM Debits WHERE Date >= ?", (date_debut,))
    rows = []
    for row in cursor.fetchall():
        id_st, cap, dt, val, ori, qual = row
        rows.append((gouvernorat, mdb_name, str(id_st or ""), str(cap or ""), dt,
                     _safe_float(val), str(ori or ""), str(qual or "")))
    return rows


def extract_jaugeages(mdb_conn, gouvernorat, mdb_name, date_debut):
    cursor = mdb_conn.cursor()
    tables = get_mdb_tables(mdb_conn)
    if "Jaugeages" not in tables:
        return []
    cols_info = [row.column_name for row in cursor.columns(table="Jaugeages")]
    date_col    = next((c for c in cols_info if "Date"    in c), None)
    hauteur_col = next((c for c in cols_info if "Hauteur" in c or "HautMoy" in c), None)
    debit_col   = next((c for c in cols_info if "Debit"   in c or "Q_"      in c), None)
    comment_col = next((c for c in cols_info if "Comment" in c or "Observ"  in c), None)
    if not date_col:
        return []
    select_parts = ["Id_Station", date_col]
    if hauteur_col: select_parts.append(hauteur_col)
    if debit_col:   select_parts.append(debit_col)
    if comment_col: select_parts.append(comment_col)
    try:
        cursor.execute(f"SELECT {', '.join(select_parts)} FROM Jaugeages WHERE {date_col} >= ?", (date_debut,))
    except Exception:
        cursor.execute(f"SELECT {', '.join(select_parts)} FROM Jaugeages")
    rows = []
    for row in cursor.fetchall():
        idx = 0
        id_st = str(row[idx] or ""); idx += 1
        dt = row[idx]; idx += 1
        hauteur = _safe_float(row[idx]) if hauteur_col else None
        if hauteur_col: idx += 1
        debit = _safe_float(row[idx]) if debit_col else None
        if debit_col: idx += 1
        comment = str(row[idx] or "") if comment_col else ""
        if dt and dt >= date_debut:
            rows.append((gouvernorat, mdb_name, id_st, dt, hauteur, debit, comment))
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# INSERTION POSTGRESQL
# ─────────────────────────────────────────────────────────────────────────────

def insert_stations(pg_conn, rows):
    if not rows:
        return 0
    sql = """INSERT INTO ann_stations
        (gouvernorat, source_mdb, type_station, id_station, nom,
         latitude, longitude, altitude, bassin, grand_bassin, riviere, debut_activite)
        VALUES %s ON CONFLICT (gouvernorat, id_station, source_mdb) DO NOTHING"""
    with pg_conn.cursor() as cur:
        execute_values(cur, sql, rows, page_size=BATCH_SIZE)
    pg_conn.commit()
    return len(rows)

def insert_pluies(pg_conn, rows):
    if not rows:
        return 0
    sql = """INSERT INTO ann_pluies
        (gouvernorat, source_mdb, id_station, capteur, date_obs,
         valeur_mm, origine, qualite, nature) VALUES %s"""
    total = 0
    for i in range(0, len(rows), BATCH_SIZE):
        with pg_conn.cursor() as cur:
            execute_values(cur, sql, rows[i:i+BATCH_SIZE], page_size=BATCH_SIZE)
        pg_conn.commit()
        total += len(rows[i:i+BATCH_SIZE])
    return total

def insert_debits(pg_conn, rows):
    if not rows:
        return 0
    sql = """INSERT INTO ann_debits
        (gouvernorat, source_mdb, id_station, capteur, date_obs,
         valeur_m3s, origine, qualite) VALUES %s"""
    total = 0
    for i in range(0, len(rows), BATCH_SIZE):
        with pg_conn.cursor() as cur:
            execute_values(cur, sql, rows[i:i+BATCH_SIZE], page_size=BATCH_SIZE)
        pg_conn.commit()
        total += len(rows[i:i+BATCH_SIZE])
    return total

def insert_jaugeages(pg_conn, rows):
    if not rows:
        return 0
    sql = """INSERT INTO ann_jaugeages
        (gouvernorat, source_mdb, id_station, date_jaug, hauteur_m, debit_m3s, commentaire)
        VALUES %s"""
    with pg_conn.cursor() as cur:
        execute_values(cur, sql, rows, page_size=BATCH_SIZE)
    pg_conn.commit()
    return len(rows)

def log_ingestion(pg_conn, gouvernorat, fichier, nb_s, nb_p, nb_d, nb_j, statut, erreur=""):
    with pg_conn.cursor() as cur:
        cur.execute("""INSERT INTO ann_ingestion_log
            (gouvernorat, fichier_mdb, nb_stations, nb_pluies, nb_debits, nb_jaugeages, statut, erreur)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
            (gouvernorat, fichier, nb_s, nb_p, nb_d, nb_j, statut, erreur[:500] if erreur else ""))
    pg_conn.commit()


# ─────────────────────────────────────────────────────────────────────────────
# TRAITEMENT D'UN FICHIER MDB
# ─────────────────────────────────────────────────────────────────────────────

def process_mdb(mdb_path, gouvernorat, pg_conn):
    mdb_name = os.path.basename(mdb_path)
    nb_s = nb_p = nb_d = nb_j = 0
    log_progress(f"  Fichier : {mdb_name}")
    try:
        mdb_conn = open_mdb(mdb_path)
        stations = extract_stations(mdb_conn, gouvernorat, mdb_name)
        nb_s = insert_stations(pg_conn, stations)
        log_progress(f"    Stations  : {nb_s}")
        pluies = extract_pluies(mdb_conn, gouvernorat, mdb_name, DATE_DEBUT)
        nb_p = insert_pluies(pg_conn, pluies)
        log_progress(f"    Pluies    : {nb_p:,}")
        debits = extract_debits(mdb_conn, gouvernorat, mdb_name, DATE_DEBUT)
        nb_d = insert_debits(pg_conn, debits)
        log_progress(f"    Debits    : {nb_d:,}")
        jaugeages = extract_jaugeages(mdb_conn, gouvernorat, mdb_name, DATE_DEBUT)
        nb_j = insert_jaugeages(pg_conn, jaugeages)
        log_progress(f"    Jaugeages : {nb_j:,}")
        mdb_conn.close()
        log_ingestion(pg_conn, gouvernorat, mdb_name, nb_s, nb_p, nb_d, nb_j, "OK")
    except Exception as e:
        log_progress(f"    ERREUR : {e}")
        log_ingestion(pg_conn, gouvernorat, mdb_name, nb_s, nb_p, nb_d, nb_j, "ERREUR", str(e))
    return nb_s, nb_p, nb_d, nb_j


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    start_time = datetime.now()
    print("=" * 65)
    print("  FUSION DES ANNUAIRES HYDROLOGIQUES MDB -> PostgreSQL")
    print(f"  Filtre : donnees >= {DATE_DEBUT.strftime('%d/%m/%Y')}")
    print(f"  Source : {ANN_ROOT}")
    print("=" * 65)

    log_progress("Connexion a PostgreSQL...")
    try:
        pg_conn = get_pg_connection()
        log_progress("OK - Connexion PostgreSQL etablie.")
    except Exception as e:
        print(f"\nERREUR connexion PostgreSQL : {e}")
        sys.exit(1)

    log_progress("Creation des tables...")
    with pg_conn.cursor() as cur:
        cur.execute(CREATE_TABLES_SQL)
    pg_conn.commit()
    log_progress("OK - Tables pretes.")

    total = {"gouvernorats": 0, "fichiers": 0, "stations": 0,
             "pluies": 0, "debits": 0, "jaugeages": 0, "erreurs": 0}

    for gouvernorat in GOUVERNORATS:
        gouv_dir = os.path.join(ANN_ROOT, gouvernorat)
        if not os.path.isdir(gouv_dir):
            log_progress(f"AVERTISSEMENT : dossier introuvable : {gouv_dir}")
            continue
        mdb_files = glob.glob(os.path.join(gouv_dir, "*.mdb"))
        if not mdb_files:
            log_progress(f"AVERTISSEMENT : aucun .mdb dans {gouv_dir}")
            continue
        print(f"\n--- GOUVERNORAT : {gouvernorat.upper()} ({len(mdb_files)} fichier(s)) ---")
        total["gouvernorats"] += 1
        for mdb_path in sorted(mdb_files):
            total["fichiers"] += 1
            nb_s, nb_p, nb_d, nb_j = process_mdb(mdb_path, gouvernorat, pg_conn)
            total["stations"]  += nb_s
            total["pluies"]    += nb_p
            total["debits"]    += nb_d
            total["jaugeages"] += nb_j

    elapsed = (datetime.now() - start_time).total_seconds()
    print("\n" + "=" * 65)
    print("  RESUME FINAL")
    print("=" * 65)
    print(f"  Gouvernorats traites : {total['gouvernorats']}")
    print(f"  Fichiers MDB traites : {total['fichiers']}")
    print(f"  Stations             : {total['stations']:,}")
    print(f"  Pluies               : {total['pluies']:,}")
    print(f"  Debits               : {total['debits']:,}")
    print(f"  Jaugeages            : {total['jaugeages']:,}")
    print(f"  Duree totale         : {elapsed:.1f} secondes")
    print("=" * 65)

    log_progress("Verification des totaux en base PostgreSQL...")
    with pg_conn.cursor() as cur:
        for table in ["ann_stations", "ann_pluies", "ann_debits", "ann_jaugeages"]:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            count = cur.fetchone()[0]
            print(f"  {table:<22} : {count:>12,} lignes")

    pg_conn.close()
    print("\nIngestion terminee avec succes !")


if __name__ == "__main__":
    main()
