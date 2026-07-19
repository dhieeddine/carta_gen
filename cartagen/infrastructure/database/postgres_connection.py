# -*- coding: utf-8 -*-

import psycopg2
import pandas as pd
from typing import List, Dict, Any, Optional

class PostgresConnectionManager:
    """Gère l'accès à la base de données PostgreSQL de la DGRE."""

    def __init__(self, database_url: str):
        self.database_url = database_url

    def get_connection(self):
        """Retourne une nouvelle connexion PostgreSQL."""
        return psycopg2.connect(self.database_url)

    def execute_query(self, query: str) -> pd.DataFrame:
        """Exécute une requête SQL et retourne un DataFrame Pandas."""
        conn = self.get_connection()
        try:
            df = pd.read_sql(query, conn)
            return df
        finally:
            conn.close()

    def get_table_schema(self, table_name: str) -> List[Dict[str, Any]]:
        """Retourne la liste des colonnes et types d'une table pour validation par l'agent SQL."""
        query = f"""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = '{table_name}';
        """
        df = self.execute_query(query)
        return df.to_dict(orient="records")

    def test_connection(self) -> bool:
        """Vérifie la viabilité de la connexion."""
        try:
            conn = self.get_connection()
            conn.close()
            return True
        except Exception:
            return False
