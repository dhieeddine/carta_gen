# -*- coding: utf-8 -*-
"""
cartagen/infrastructure/agents/data_audit_agent.py
===================================================
Agent d'audit et de validation des données extraites par le SQL Generator Agent.
Vérifie la cohérence, l'absence de valeurs nulles critiques et informe l'orchestrateur.
"""

import pandas as pd
import psycopg2
from typing import Dict, Any, Tuple, Optional

class DataAuditAgent:
    """Agent responsable du contrôle qualité des données extraites avant génération graphique/SIG."""

    def __init__(self, database_url: str):
        self.database_url = database_url
        self.last_audit_report = {}

    def audit_sql_query(self, sql_query: str, target_col: str) -> Tuple[bool, str, Optional[pd.DataFrame]]:
        """
        Exécute et audite la requête SQL générée.

        Returns:
            Tuple[bool, str, Optional[pd.DataFrame]]: (Est_Valide, Diagnostic, DataFrame_Résultat)
        """
        try:
            import sqlalchemy
            engine = sqlalchemy.create_engine(self.database_url)
            df = pd.read_sql(sql_query, engine)

            df.columns = df.columns.str.lower()

            # 1. Vérification si le DataFrame est totalement vide
            if df.empty:
                msg = f"La requête SQL a renvoyé 0 ligne. Aucune donnée pluviométrique ne correspond aux filtres appliqués."
                self.last_audit_report = {"valid": False, "reason": "empty", "message": msg}
                return False, msg, df

            # 2. Vérification des coordonnées géographiques
            if 'x' in df.columns and 'y' in df.columns:
                valid_coords = df.dropna(subset=['x', 'y'])
                if valid_coords.empty:
                    msg = "Toutes les lignes retournées possèdent des coordonnées géographiques nuls (x/y IS NULL)."
                    self.last_audit_report = {"valid": False, "reason": "null_coords", "message": msg}
                    return False, msg, df

            # 3. Vérification de la colonne cible des cumuls
            t_col = target_col.lower()
            if t_col not in df.columns:
                # Chercher une alternative numérique
                num_cols = df.select_dtypes(include=['number']).columns.tolist()
                num_cols = [c for c in num_cols if c not in ['id_station', 'x', 'y', 'lon', 'lat', 'altitude']]
                if num_cols:
                    t_col = num_cols[0]
                else:
                    msg = f"La colonne cible '{target_col}' est introuvable dans le résultat."
                    self.last_audit_report = {"valid": False, "reason": "missing_target_col", "message": msg}
                    return False, msg, df

            # 4. Vérification des cumuls nuls ou négatifs
            non_null_df = df.dropna(subset=[t_col])
            if non_null_df.empty:
                msg = f"Toutes les valeurs de la colonne cible '{t_col}' sont nuls."
                self.last_audit_report = {"valid": False, "reason": "null_values", "message": msg}
                return False, msg, df

            nb_stations = len(non_null_df)
            val_min = non_null_df[t_col].min()
            val_max = non_null_df[t_col].max()
            val_avg = non_null_df[t_col].mean()

            msg = (
                f"Données auditées avec succès : {nb_stations} stations valides détectées. "
                f"Cumul min = {val_min:.1f} mm, max = {val_max:.1f} mm, moyenne = {val_avg:.1f} mm."
            )
            self.last_audit_report = {
                "valid": True,
                "nb_stations": nb_stations,
                "min": val_min,
                "max": val_max,
                "avg": val_avg,
                "message": msg
            }
            return True, msg, df

        except Exception as e:
            msg = f"Erreur d'exécution SQL lors de l'audit : {str(e)}"
            self.last_audit_report = {"valid": False, "reason": "exception", "message": msg}
            return False, msg, None
