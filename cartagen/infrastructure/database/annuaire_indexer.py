# -*- coding: utf-8 -*-
"""
cartagen/infrastructure/database/annuaire_indexer.py
=====================================================
Service d'indexation des données de l'annuaire pluviométrique dans Zvec.
Génère des chunks textuels riches et sémantiques pour améliorer la précision
de la recherche vectorielle (pas de comparaisons statiques de chaînes).
"""

import os
import psycopg2
import pandas as pd
from typing import List, Dict, Any


# ── Métadonnées géographiques enrichies ────────────────────────────────────────
GOUV_META = {
    "Bizerte":     {"zone": "nord", "syns": ["bizerte", "bizerta", "البنزرت"]},
    "Béja":        {"zone": "nord", "syns": ["beja", "béja", "bèja", "بجة"]},
    "Jendouba":    {"zone": "nord", "syns": ["jendouba", "جndوبة", "جndouba", "جندوبة"]},
    "Kef":         {"zone": "nord", "syns": ["le kef", "kef", "الكاف"]},
    "Siliana":     {"zone": "nord", "syns": ["siliana", "سليانة"]},
    "Ariana":      {"zone": "nord", "syns": ["ariana", "أriana", "أريانة"]},
    "Tunis":       {"zone": "nord", "syns": ["tunis", "تونس", "la capitale"]},
    "Ben Arous":   {"zone": "nord", "syns": ["ben arous", "بن عروس"]},
    "Manouba":     {"zone": "nord", "syns": ["manouba", "منوبة"]},
    "Nabeul":      {"zone": "nord", "syns": ["nabeul", "نابل", "cap bon", "rdc"]},
    "Zaghouan":    {"zone": "nord", "syns": ["zaghouan", "زغوان"]},
    "Sousse":      {"zone": "centre", "syns": ["sousse", "سوسة", "sahel"]},
    "Monastir":    {"zone": "centre", "syns": ["monastir", "المنستير", "mounastir"]},
    "Mahdia":      {"zone": "centre", "syns": ["mahdia", "مهدية"]},
    "Sfax":        {"zone": "centre", "syns": ["sfax", "صفاقس"]},
    "Kairouan":    {"zone": "centre", "syns": ["kairouan", "القيروان"]},
    "Kasserine":   {"zone": "centre", "syns": ["kasserine", "القصرين"]},
    "Sidi Bouzid": {"zone": "centre", "syns": ["sidi bouzid", "سيدي بوزيد"]},
    "Gafsa":       {"zone": "sud",    "syns": ["gafsa", "قفصة"]},
    "Tozeur":      {"zone": "sud",    "syns": ["tozeur", "توزر", "touzeur"]},
    "Kébili":      {"zone": "sud",    "syns": ["kebili", "kébili", "قبلي"]},
    "Gabès":       {"zone": "sud",    "syns": ["gabes", "gabès", "قابس"]},
    "Médenine":    {"zone": "sud",    "syns": ["medenine", "médenine", "مدنين"]},
    "Tataouine":   {"zone": "sud",    "syns": ["tataouine", "تطاوين"]},
}

ZONE_LABELS = {
    "nord":   "nord de la Tunisie (région la plus arrosée)",
    "centre": "centre de la Tunisie (région semi-aride)",
    "sud":    "sud de la Tunisie (région aride et désertique)"
}

MOIS_NOM = {
    1: 'Janvier', 2: 'Février', 3: 'Mars', 4: 'Avril',
    5: 'Mai', 6: 'Juin', 7: 'Juillet', 8: 'Août',
    9: 'Septembre', 10: 'Octobre', 11: 'Novembre', 12: 'Décembre'
}

PLUIE_SYNONYMES = (
    "pluie, précipitations, cumul pluviométrique, pluviométrie, "
    "hauteur de pluie, apport pluvial, isohyètes"
)


def _get_zone(gouvernorat: str) -> str:
    """Retourne la zone climatique d'un gouvernorat."""
    for k, v in GOUV_META.items():
        if gouvernorat and gouvernorat.lower() in [s.lower() for s in [k] + v["syns"]]:
            return v["zone"]
    return "centre"


def _get_synonymes(gouvernorat: str) -> str:
    """Retourne les synonymes d'un gouvernorat sous forme de chaîne."""
    for k, v in GOUV_META.items():
        if gouvernorat and gouvernorat.lower() in [s.lower() for s in [k] + v["syns"]]:
            return ", ".join(v["syns"])
    return gouvernorat or ""


class AnnuaireIndexer:
    """
    Indexe les données des annuaires pluviométriques dans la base vectorielle Zvec.
    Génère des chunks textuels riches avec contexte sémantique complet.
    """

    def __init__(self, database_url: str, vector_manager):
        self.database_url = database_url
        self.vector_manager = vector_manager
        self._model = None

    def _get_connection(self):
        return psycopg2.connect(self.database_url)

    def _get_embedding_model(self):
        from sentence_transformers import SentenceTransformer
        if self._model is None:
            self._model = SentenceTransformer('all-MiniLM-L6-v2')
        return self._model

    # ── Générateurs de chunks ──────────────────────────────────────────────────

    def _chunk_stations_list(self, df_stations: pd.DataFrame) -> List[Dict]:
        """Chunk global: liste enrichie de toutes les stations."""
        chunks = []
        if df_stations.empty:
            return chunks

        # ── Chunk liste complète ──
        station_lines = []
        for _, row in df_stations.iterrows():
            gouv = str(row.get('gouvernorat', 'Inconnu'))
            zone = _get_zone(gouv)
            syns = _get_synonymes(gouv)
            line = (
                f"- Station {row['nom']} (ID: {row['id_station']}) | "
                f"Gouvernorat: {gouv} (aussi appelé: {syns}) | "
                f"Zone: {ZONE_LABELS.get(zone, zone)}"
            )
            if pd.notna(row.get('altitude')) and str(row['altitude']).strip() not in ('', 'None'):
                line += f" | Altitude: {row['altitude']} m"
            if pd.notna(row.get('lon')) and pd.notna(row.get('lat')):
                line += f" | Coordonnées: lon={row['lon']:.3f}, lat={row['lat']:.3f}"
            station_lines.append(line)

        chunks.append({
            "doc_name": "annuaire_stations_liste_complete",
            "page": 0,
            "text_content": (
                "Liste complète des stations pluviométriques de l'annuaire hydrologique de la DGRE Tunisie.\n"
                "Ces stations mesurent les précipitations (pluie, cumul pluviométrique) sur tout le territoire tunisien.\n"
                "Synonymes: postes pluviométriques, capteurs de pluie, stations météo, stations hydro.\n\n"
                + "\n".join(station_lines)
            )
        })

        # ── Un chunk par gouvernorat (très enrichi) ──
        for gouv, g_df in df_stations.groupby('gouvernorat'):
            zone = _get_zone(str(gouv))
            syns = _get_synonymes(str(gouv))
            zone_label = ZONE_LABELS.get(zone, zone)

            # Générer les infos par station
            st_details = []
            for _, r in g_df.iterrows():
                detail = f"  • {r['nom']} (ID: {r['id_station']})"
                if pd.notna(r.get('altitude')) and str(r.get('altitude', '')).strip() not in ('', 'None'):
                    detail += f", altitude {r['altitude']} m"
                st_details.append(detail)

            chunks.append({
                "doc_name": f"stations_gouvernorat_{gouv}",
                "page": 0,
                "text_content": (
                    f"Stations pluviométriques du gouvernorat de {gouv} ({syns}) — {zone_label}.\n"
                    f"Nombre de stations: {len(g_df)}.\n"
                    f"Ces stations enregistrent les précipitations (pluie, cumul, {PLUIE_SYNONYMES}) "
                    f"dans le gouvernorat de {gouv}, situé dans le {zone_label}.\n"
                    f"Liste des stations:\n"
                    + "\n".join(st_details)
                )
            })

        # ── Un chunk par zone climatique ──
        for zone_key, zone_label in ZONE_LABELS.items():
            zone_df = df_stations[df_stations['gouvernorat'].apply(
                lambda g: _get_zone(str(g)) == zone_key
            )]
            if zone_df.empty:
                continue
            gouv_list = zone_df['gouvernorat'].unique().tolist()
            st_names = zone_df['nom'].tolist()
            chunks.append({
                "doc_name": f"stations_zone_{zone_key}",
                "page": 0,
                "text_content": (
                    f"Stations pluviométriques de la zone {zone_label}.\n"
                    f"Gouvernorats couverts: {', '.join(str(g) for g in gouv_list)}.\n"
                    f"Nombre total de stations: {len(zone_df)}.\n"
                    f"Ces stations mesurent les précipitations ({PLUIE_SYNONYMES}) "
                    f"dans le {zone_label}.\n"
                    f"Noms des stations: {', '.join(str(n) for n in st_names[:40])}."
                )
            })

        return chunks

    def _chunk_annuels(self, df_annual: pd.DataFrame) -> List[Dict]:
        """
        Chunks sémantiques pour les totaux annuels.
        Génère :
          - Un chunk Q&A par (gouvernorat, année)
          - Un chunk synthèse nationale par année
          - Un chunk historique par station
        """
        chunks = []
        if df_annual.empty:
            return chunks

        # ── Chunk (gouvernorat × année) — format Q&A naturel ──
        for (gouv, annee), ga_df in df_annual.groupby(['gouvernorat', 'annee']):
            zone = _get_zone(str(gouv))
            syns = _get_synonymes(str(gouv))
            zone_label = ZONE_LABELS.get(zone, zone)
            lines = []
            for _, r in ga_df.iterrows():
                val = f"{r['total_annuel_mm']:.1f}" if pd.notna(r['total_annuel_mm']) else "N/D"
                lines.append(f"  • {r['nom']} (ID: {r['id_station']}): {val} mm")

            total_gouv = ga_df['total_annuel_mm'].sum()
            moy_gouv = ga_df['total_annuel_mm'].mean()

            chunks.append({
                "doc_name": f"cumul_annuel_{gouv}_{int(annee)}",
                "page": int(annee),
                "text_content": (
                    f"Question: Quels sont les cumuls pluviométriques dans le gouvernorat de {gouv} en {int(annee)} ?\n"
                    f"Réponse: Voici les précipitations enregistrées en {int(annee)} "
                    f"dans le gouvernorat de {gouv} (aussi connu sous: {syns}), "
                    f"situé dans le {zone_label}.\n"
                    f"Cumul total du gouvernorat: {total_gouv:.1f} mm | Moyenne: {moy_gouv:.1f} mm/station.\n"
                    f"Détail par station ({PLUIE_SYNONYMES}):\n"
                    + "\n".join(lines)
                )
            })

        # ── Chunk synthèse nationale par année ──
        for annee, a_df in df_annual.groupby('annee'):
            gouv_summary = a_df.groupby('gouvernorat').agg(
                nb_stations=('nom', 'count'),
                total=('total_annuel_mm', 'sum'),
                moy=('total_annuel_mm', 'mean')
            ).reset_index()

            lines = []
            for _, r in gouv_summary.iterrows():
                g = str(r['gouvernorat'])
                zone = _get_zone(g)
                lines.append(
                    f"  • {g} ({ZONE_LABELS.get(zone, zone)}): "
                    f"{r['nb_stations']} stations, total={r['total']:.1f} mm, "
                    f"moyenne={r['moy']:.1f} mm"
                )

            chunks.append({
                "doc_name": f"synthese_nationale_{int(annee)}",
                "page": int(annee),
                "text_content": (
                    f"Bilan pluviométrique national de la Tunisie pour l'année {int(annee)}.\n"
                    f"Cumuls des précipitations ({PLUIE_SYNONYMES}) pour toutes les régions de la Tunisie en {int(annee)} :\n"
                    f"Résumé par gouvernorat (nord, centre, sud) :\n"
                    + "\n".join(lines)
                )
            })

        # ── Chunk historique par station ──
        for (sid, nom, gouv), s_df in df_annual.groupby(['id_station', 'nom', 'gouvernorat']):
            zone = _get_zone(str(gouv))
            syns = _get_synonymes(str(gouv))
            hist_lines = [
                f"  • Année {int(r['annee'])}: {r['total_annuel_mm']:.1f} mm"
                for _, r in s_df.iterrows()
                if pd.notna(r['total_annuel_mm'])
            ]
            if not hist_lines:
                continue
            first_year = int(s_df['annee'].min())
            last_year = int(s_df['annee'].max())
            moy_hist = s_df['total_annuel_mm'].mean()

            chunks.append({
                "doc_name": f"historique_station_{sid}",
                "page": 0,
                "text_content": (
                    f"Historique pluviométrique complet de la station {nom} "
                    f"(ID: {sid}, Gouvernorat: {gouv}, synonymes du gouvernorat: {syns}, "
                    f"zone: {ZONE_LABELS.get(zone, zone)}).\n"
                    f"Période: {first_year}–{last_year} | Moyenne interannuelle: {moy_hist:.1f} mm/an.\n"
                    f"Cumuls annuels de précipitations enregistrés:\n"
                    + "\n".join(hist_lines)
                )
            })

        return chunks

    def _chunk_mensuels(self, df_monthly: pd.DataFrame) -> List[Dict]:
        """Chunks sémantiques pour les totaux mensuels."""
        chunks = []
        if df_monthly.empty:
            return chunks

        for (sid, nom, gouv, annee), m_df in df_monthly.groupby(
                ['id_station', 'nom', 'gouvernorat', 'annee']):
            zone = _get_zone(str(gouv))
            parts = []
            for _, mrow in m_df.sort_values('mois').iterrows():
                m_label = MOIS_NOM.get(int(mrow['mois']), str(int(mrow['mois'])))
                val = f"{mrow['total_mensuel_mm']:.1f}" if pd.notna(mrow['total_mensuel_mm']) else "0"
                parts.append(f"{m_label}: {val} mm")

            chunks.append({
                "doc_name": f"mensuel_{sid}_{int(annee)}",
                "page": int(annee),
                "text_content": (
                    f"Répartition mensuelle des précipitations en {int(annee)} "
                    f"pour la station {nom} (ID: {sid}), "
                    f"gouvernorat de {gouv} ({zone}).\n"
                    f"Totaux pluviométriques mois par mois ({PLUIE_SYNONYMES}) :\n"
                    + " | ".join(parts)
                )
            })

        return chunks

    def _chunk_macro_stats(self, conn) -> List[Dict]:
        """Génère des résumés statistiques globaux et records pour enrichir l'indexation sémantique (Macro Stats)."""
        chunks = []
        try:
            # 1. Record absolu de pluie (station, année)
            df_max = pd.read_sql("""
                SELECT s.nom, s.gouvernorat, EXTRACT(YEAR FROM p.date_obs)::int AS annee, SUM(p.valeur_mm) AS total
                FROM pluies_148 p
                JOIN station_148 s ON p.id_station = s.id_station
                GROUP BY s.nom, s.gouvernorat, EXTRACT(YEAR FROM p.date_obs)
                ORDER BY total DESC LIMIT 1
            """, conn)
            
            # 2. Moyenne nationale par année
            df_avg_years = pd.read_sql("""
                SELECT annee, ROUND(AVG(total_station)::numeric, 1) AS moy_nationale
                FROM (
                    SELECT p.id_station, EXTRACT(YEAR FROM p.date_obs)::int AS annee, SUM(p.valeur_mm) AS total_station
                    FROM pluies_148 p
                    GROUP BY p.id_station, EXTRACT(YEAR FROM p.date_obs)
                ) sub
                GROUP BY annee
                ORDER BY annee
            """, conn)
            
            # 3. Stations les plus arrosées par année
            df_tops = pd.read_sql("""
                WITH ranked AS (
                    SELECT s.nom, s.gouvernorat, EXTRACT(YEAR FROM p.date_obs)::int AS annee, SUM(p.valeur_mm) AS total,
                           ROW_NUMBER() OVER (PARTITION BY EXTRACT(YEAR FROM p.date_obs) ORDER BY SUM(p.valeur_mm) DESC) as rn
                    FROM pluies_148 p
                    JOIN station_148 s ON p.id_station = s.id_station
                    GROUP BY s.nom, s.gouvernorat, EXTRACT(YEAR FROM p.date_obs)
                )
                SELECT nom, gouvernorat, annee, total FROM ranked WHERE rn = 1 ORDER BY annee
            """, conn)

            lines = []
            if not df_max.empty:
                r = df_max.iloc[0]
                total_val = float(r['total']) if r['total'] is not None else 0.0
                lines.append(f"Record absolu de précipitations : La station la plus arrosée est {r['nom']} ({r['gouvernorat']}) en {r['annee']} avec un cumul record de {total_val:.1f} mm.")
            
            for _, r in df_tops.iterrows():
                total_val = float(r['total']) if r['total'] is not None else 0.0
                lines.append(f"En {r['annee']}, la station la plus arrosée de Tunisie a été {r['nom']} (Gouvernorat de {r['gouvernorat']}) avec un cumul de {total_val:.1f} mm.")

            for _, r in df_avg_years.iterrows():
                moy_val = float(r['moy_nationale']) if r['moy_nationale'] is not None else 0.0
                lines.append(f"En {r['annee']}, la moyenne estimée des précipitations annuelles à l'échelle nationale était de {moy_val:.1f} mm par station.")

            if lines:
                chunks.append({
                    "doc_name": "records_et_statistiques_macro",
                    "page": 0,
                    "text_content": (
                        "Bilan des records pluviométriques et statistiques macro-climatiques de la Tunisie (DGRE).\n"
                        "Ce document contient les valeurs extrêmes (maxima, records) et les moyennes nationales annuelles.\n\n"
                        + "\n".join(lines)
                    )
                })
        except Exception as e:
            print(f"[AnnuaireIndexer] Erreur macro_stats: {e}")
        return chunks

    # ── Pipeline principal ─────────────────────────────────────────────────────

    def build_chunks(self) -> List[Dict[str, Any]]:
        """Génère l'ensemble des chunks textuels sémantiques depuis PostgreSQL."""
        all_chunks = []
        conn = self._get_connection()

        try:
            # ── 1. Stations ──────────────────────────────────────────────────
            df_stations = pd.read_sql("""
                SELECT id_station, nom, gouvernorat, lon, lat, altitude
                FROM station_148
                ORDER BY gouvernorat, nom
            """, conn)

            all_chunks.extend(self._chunk_stations_list(df_stations))

            # ── 2. Totaux annuels (pluies_148) ───────────────────────────────
            try:
                df_annual = pd.read_sql("""
                    SELECT
                        p.id_station,
                        s.nom,
                        s.gouvernorat,
                        EXTRACT(YEAR FROM p.date_obs)::int AS annee,
                        SUM(p.valeur_mm) AS total_annuel_mm
                    FROM pluies_148 p
                    JOIN station_148 s ON p.id_station = s.id_station
                    WHERE p.valeur_mm IS NOT NULL
                    GROUP BY p.id_station, s.nom, s.gouvernorat,
                             EXTRACT(YEAR FROM p.date_obs)
                    ORDER BY s.gouvernorat, s.nom, annee
                """, conn)
                all_chunks.extend(self._chunk_annuels(df_annual))
            except Exception as e:
                print(f"[AnnuaireIndexer] Avertissement totaux annuels : {e}")
                conn.rollback()

            # ── 3. Totaux mensuels (3 dernières années) ──────────────────────
            try:
                df_monthly = pd.read_sql("""
                    SELECT
                        p.id_station,
                        s.nom,
                        s.gouvernorat,
                        EXTRACT(YEAR FROM p.date_obs)::int AS annee,
                        EXTRACT(MONTH FROM p.date_obs)::int AS mois,
                        SUM(p.valeur_mm) AS total_mensuel_mm
                    FROM pluies_148 p
                    JOIN station_148 s ON p.id_station = s.id_station
                    WHERE EXTRACT(YEAR FROM p.date_obs) IN (
                        SELECT DISTINCT EXTRACT(YEAR FROM date_obs)::int
                        FROM pluies_148
                        ORDER BY 1 DESC LIMIT 5
                    )
                    GROUP BY p.id_station, s.nom, s.gouvernorat,
                             EXTRACT(YEAR FROM p.date_obs),
                             EXTRACT(MONTH FROM p.date_obs)
                    ORDER BY s.gouvernorat, s.nom, annee, mois
                """, conn)
                all_chunks.extend(self._chunk_mensuels(df_monthly))
            except Exception as e:
                print(f"[AnnuaireIndexer] Avertissement totaux mensuels : {e}")
                conn.rollback()

            # ── 4. Records & Statistiques Macro ──────────────────────────────
            all_chunks.extend(self._chunk_macro_stats(conn))

        finally:
            conn.close()

        # Enrichir chaque chunk avec une entête de métadonnées sémantiques (Hybrid Chunks)
        for chunk in all_chunks:
            meta_header = f"[META: doc_name='{chunk['doc_name']}', page={chunk['page']}]\n"
            chunk["text_content"] = meta_header + chunk["text_content"]

        print(f"[AnnuaireIndexer] {len(all_chunks)} chunks sémantiques générés.")
        return all_chunks

    def index(self) -> Dict[str, Any]:
        """Pipeline complet : génère les chunks enrichis, vectorise, insère dans Zvec. """
        import zvec

        print("[AnnuaireIndexer] Démarrage de l'indexation sémantique enrichie...")
        chunks = self.build_chunks()

        if not chunks:
            return {"success": False, "error": "Aucun chunk généré — BDD vide ?", "nb_chunks": 0}

        self.vector_manager.initialize_annuaires_only(dimension=384)

        model = self._get_embedding_model()
        print(f"[AnnuaireIndexer] Vectorisation de {len(chunks)} chunks...")

        BATCH = 64
        z_docs = []
        for i, chunk in enumerate(chunks):
            text = chunk["text_content"]
            embedding = model.encode(text).tolist()
            z_docs.append(zvec.Doc(
                id=f"ann_{i}",
                vectors={"embedding": embedding},
                fields={
                    "doc_name": str(chunk["doc_name"]),
                    "page": int(chunk["page"]),
                    "text_content": str(text[:3000])
                }
            ))

            if len(z_docs) >= BATCH:
                self.vector_manager.annuaires_collection.insert(z_docs)
                z_docs = []

        if z_docs:
            self.vector_manager.annuaires_collection.insert(z_docs)

        self.index_images()

        print(f"[AnnuaireIndexer] Indexation terminée — {len(chunks)} chunks insérés dans Zvec.")
        return {
            "success": True,
            "nb_chunks": len(chunks),
            "message": (
                f"Indexation sémantique réussie : {len(chunks)} passages pluviométriques "
                f"enrichis indexés dans Zvec."
            )
        }

    def index_images(self):
        """Indexe les descriptions sémantiques des types d'images via Zvec."""
        print("[AnnuaireIndexer] Indexation des métadonnées d'images...")
        mapping = {
            "carte_stations.png": (
                "Carte de localisation géographique des postes et capteurs d'observation pluviométrique. "
                "Répartition spatiale des stations de mesure de pluie sur la carte de la Tunisie. "
                "Réseau pluviométrique, densité des stations, positions géographiques."
            ),
            "carte_annuelle.png": (
                "Carte isohyète annuelle de la Tunisie. Répartition spatiale de la pluie cumulée sur une année entière. "
                "Cartographie par interpolation des précipitations annuelles, courbes isohyètes, "
                "couleurs selon l'intensité des cumuls pluviométriques annuels."
            ),
            "carte_interannuelle.png": (
                "Carte des Isohyètes moyennes interannuelles (50 ans) du 1959-2009. "
                "Moyenne interannuelle sur 50 ans, calculée à partir des valeurs réelles de moy_interannuelle. "
                "Normale climatologique cinquantennale 1959-2009 de la DGRE."
            ),
            "carte_mensuelle_group1.png": (
                "Cartes mensuelles des isohyètes pour septembre, octobre et novembre (automne). "
                "Précipitations des mois d'automne, cumuls mensuels automnaux, saison des pluies d'automne."
            ),
            "carte_mensuelle_group2.png": (
                "Cartes mensuelles des isohyètes pour décembre, janvier, février et mars (hiver). "
                "Précipitations des mois d'hiver, cumuls mensuels hivernaux, saison des pluies d'hiver."
            ),
            "carte_mensuelle_group3.png": (
                "Cartes mensuelles des isohyètes pour avril, mai, juin, juillet et août (printemps-été). "
                "Précipitations printanières et estivales, cumuls mensuels du printemps et de l'été."
            ),
            "carte_rapport_normale.png": (
                "Carte de l'écart à la normale pluviométrique. Rapport aux précipitations normales. "
                "Anomalie pluviométrique, déficit ou excédent par rapport à la normale climatologique. "
                "Comparaison avec la moyenne interannuelle de référence."
            ),
            "carte_saisons_subplots.png": (
                "Cartes saisonnières des isohyètes par saison (automne, hiver, printemps, été). "
                "Répartition saisonnière de la pluie sur la Tunisie, quatre saisons en subplots."
            ),
            "comparaison_centrale.png": (
                "Graphique de comparaison des cumuls pluviométriques des stations de la zone centrale de la Tunisie. "
                "Diagramme en barres, comparatif des précipitations enregistrées dans les gouvernorats du centre."
            ),
            "comparaison_nord.png": (
                "Graphique de comparaison des cumuls pluviométriques des stations de la zone nord de la Tunisie. "
                "Diagramme en barres, comparatif des précipitations enregistrées dans les gouvernorats du nord."
            ),
            "comparaison_sud.png": (
                "Graphique de comparaison des cumuls pluviométriques des stations de la zone sud de la Tunisie. "
                "Diagramme en barres, comparatif des précipitations enregistrées dans les gouvernorats du sud."
            ),
            "hist_classes.png": (
                "Histogramme de distribution des classes de précipitations. "
                "Répartition des cumuls pluviométriques par tranches (classes d'intensité). "
                "Distribution statistique des hauteurs de pluie enregistrées."
            ),
            "hist_mensuel.png": (
                "Histogramme des totaux mensuels de précipitations. "
                "Barres mensuelles, cumul de pluie mois par mois sur l'année. "
                "Comparaison des précipitations entre les différents mois."
            ),
            "pie_saisons.png": (
                "Graphique circulaire camembert de la répartition saisonnière des précipitations. "
                "Diagramme en secteurs (pie chart), proportion de pluie par saison. "
                "Part relative des cumuls pluviométriques par saison de l'année."
            ),
            "carte_saison_auto.png": "Carte isohyète individuelle de la saison d'Automne (Septembre, Octobre, Novembre). Précipitations automnales.",
            "carte_saison_hiver.png": "Carte isohyète individuelle de la saison d'Hiver (Décembre, Janvier, Février). Précipitations hivernales.",
            "carte_saison_print.png": "Carte isohyète individuelle de la saison du Printemps (Mars, Avril, Mai). Précipitations printanières.",
            "carte_saison_ete.png": "Carte isohyète individuelle de la saison d'Été (Juin, Juillet, Août). Précipitations estivales.",
            "carte_mois_sept.png": "Carte isohyète individuelle du mois de Septembre.",
            "carte_mois_octo.png": "Carte isohyète individuelle du mois d'Octobre.",
            "carte_mois_nove.png": "Carte isohyète individuelle du mois de Novembre.",
            "carte_mois_dece.png": "Carte isohyète individuelle du mois de Décembre.",
            "carte_mois_janv.png": "Carte isohyète individuelle du mois de Janvier.",
            "carte_mois_fev.png": "Carte isohyète individuelle du mois de Février.",
            "carte_mois_mar.png": "Carte isohyète individuelle du mois de Mars.",
            "carte_mois_avr.png": "Carte isohyète individuelle du mois d'Avril.",
            "carte_mois_mai.png": "Carte isohyète individuelle du mois de Mai.",
            "carte_mois_juin.png": "Carte isohyète individuelle du mois de Juin.",
            "carte_mois_juil.png": "Carte isohyète individuelle du mois de Juillet.",
            "carte_mois_aout.png": "Carte isohyète individuelle du mois d'Août."
        }

        model = self._get_embedding_model()
        docs = []
        for filename, description in mapping.items():
            embedding = model.encode(description).tolist()
            docs.append({
                "filename": filename,
                "description": description,
                "embedding": embedding
            })

        self.vector_manager.insert_images(docs)
        print(f"[AnnuaireIndexer] {len(docs)} descriptions d'images indexées.")
