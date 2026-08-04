#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
requirements: pip install pandas pyodbc
Extraction de TOUTES les tables d'une base Access (.mdb)
Avec filtrage optionnel par année pour les tables de mesures (Pluies, Cotes, Debits).

Usage:
    # Exporter toutes les tables (sans filtre année)
    python extract_all_tables_with_year.py --dbpath "D:/chemin/base.mdb"

    # Exporter toutes les tables, mais filtrer les mesures pour une année donnée
    python extract_all_tables_with_year.py --dbpath "D:/chemin/base.mdb" --year 2023

    # Avec dossier de sortie personnalisé
    python extract_all_tables_with_year.py --dbpath "D:/chemin/base.mdb" --year 2023 --output "extraction_2023"
"""

import os
import sys
import argparse
import pyodbc
import pandas as pd

# ============================================
# FONCTIONS
# ============================================

def connect_access(db_path):
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Le fichier {db_path} n'existe pas.")
    conn_str = f'DRIVER={{Microsoft Access Driver (*.mdb, *.accdb)}};DBQ={db_path};'
    try:
        conn = pyodbc.connect(conn_str)
        print(f"✅ Connexion réussie à {db_path}")
        return conn
    except Exception as e:
        raise ConnectionError(f"Impossible de se connecter : {e}")

def get_all_tables(conn):
    cursor = conn.cursor()
    tables = []
    for row in cursor.tables(tableType='TABLE'):
        table_name = row.table_name
        if not table_name.startswith('MSys'):
            tables.append(table_name)
    print(f"📋 {len(tables)} tables utilisateur trouvées :")
    for t in tables:
        print(f"   - {t}")
    return tables

def export_table_to_csv(conn, table_name, output_dir, year=None):
    """
    Exporte une table Access vers un CSV.
    Si table est une table de mesures (Pluies, Cotes, Debits) et qu'une année est fournie,
    on filtre sur YEAR(Date) = year.
    """
    safe_name = table_name.replace(' ', '_').replace('/', '_').replace('\\', '_')
    filepath = os.path.join(output_dir, f"{safe_name}.csv")

    # Déterminer si la table a une colonne 'Date' et est une table de mesures
    is_measure_table = table_name in ['Pluies', 'Cotes', 'Debits']
    has_date_col = True  # par défaut ces tables ont 'Date'

    try:
        print(f"   ⏳ Export de '{table_name}' ...")
        
        # Construction de la requête
        if year is not None and is_measure_table:
            query = f"SELECT * FROM [{table_name}] WHERE YEAR(Date) = ?"
            params = [year]
        else:
            query = f"SELECT * FROM [{table_name}]"
            params = None

        if params:
            df = pd.read_sql(query, conn, params=params)
        else:
            df = pd.read_sql(query, conn)

        if df.empty:
            print(f"   ⚠️ Aucune donnée dans '{table_name}' (ou filtre trop restrictif). Fichier non créé.")
            return

        df.to_csv(filepath, index=False, encoding='utf-8-sig')
        print(f"   ✅ '{table_name}' exporté ({len(df)} lignes, {len(df.columns)} colonnes) → {safe_name}.csv")

    except Exception as e:
        print(f"   ❌ Erreur lors de l'export de '{table_name}' : {e}")

def export_all_tables(db_path, output_dir, year=None):
    os.makedirs(output_dir, exist_ok=True)
    conn = connect_access(db_path)
    try:
        tables = get_all_tables(conn)
        if not tables:
            print("⚠️ Aucune table trouvée.")
            return

        print("\n" + "-"*60)
        if year:
            print(f"📅 Filtrage par année : {year} (appliqué aux tables Pluies, Cotes, Debits)")
        else:
            print("📤 Exportation complète (aucun filtre temporel)")
        print("-"*60)

        for table in tables:
            export_table_to_csv(conn, table, output_dir, year)

        print("\n" + "="*60)
        print(f"✅ Export terminé. Tous les CSV sont dans : {output_dir}")
        print("="*60)

    finally:
        conn.close()
        print("🔒 Connexion fermée.")

# ============================================
# POINT D'ENTRÉE
# ============================================

def main():
    parser = argparse.ArgumentParser(
        description="Extraction de toutes les tables d'une base Access (.mdb) vers des CSV, avec filtrage optionnel par année pour les mesures."
    )
    parser.add_argument(
        "--dbpath", "-d",
        required=True,
        help="Chemin complet vers la base de données .mdb"
    )
    parser.add_argument(
        "--year", "-y",
        type=int,
        help="Année à filtrer (ex: 2023) pour les tables Pluies, Cotes, Debits. Si non fourni, toutes les données sont exportées."
    )
    parser.add_argument(
        "--output", "-o",
        default=".",
        help="Dossier de sortie pour les fichiers CSV (par défaut : répertoire courant)"
    )
    args = parser.parse_args()

    print("="*70)
    print("🗄️  EXTRACTION TOTALE DE LA BASE ACCESS")
    print("="*70)
    print(f"📁 Base : {args.dbpath}")
    print(f"📂 Sortie : {args.output}")
    if args.year:
        print(f"📅 Année : {args.year} (filtrage des tables de mesures)")
    else:
        print("📅 Aucun filtre année (export complet)")
    print("-"*70)

    try:
        export_all_tables(args.dbpath, args.output, args.year)
    except Exception as e:
        print(f"❌ Une erreur critique est survenue : {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()