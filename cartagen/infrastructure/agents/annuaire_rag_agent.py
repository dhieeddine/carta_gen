# -*- coding: utf-8 -*-
"""
cartagen/infrastructure/agents/annuaire_rag_agent.py
=====================================================
Agent RAG spécialisé pour répondre aux questions sur les annuaires pluviométriques.
Pipeline : détection sémantique des entités -> Zvec retrieve -> SQL enrichissement -> LLM answer.
"""

import os
import re
import sys
import subprocess
import difflib
import unicodedata
import psycopg2
import pandas as pd
from typing import List, Dict, Any, Optional

# Référentiel gouvernorats avec variantes orthographiques
GOUV_VARIANTS: Dict[str, List[str]] = {
    "Bizerte":     ["bizerte", "bizerta", "bizert", "benzert", "بنزرت"],
    "Béja":        ["beja", "béja", "bèja", "bêja", "بجة"],
    "Jendouba":    ["jendouba", "jandouba", "جndوبة", "جndouba", "جndouba", "جndouba", "جندوبة"],
    "Kef":         ["kef", "le kef", "el kef", "الكاف"],
    "Siliana":     ["siliana", "siliena", "سليانة"],
    "Ariana":      ["ariana", "aryana", "أريانة"],
    "Tunis":       ["tunis", "تونس"],
    "Ben Arous":   ["ben arous", "benarous", "ben-arous", "بن عروس"],
    "Manouba":     ["manouba", "mannouba", "منوبة"],
    "Nabeul":      ["nabeul", "nabeoul", "cap bon", "نابل"],
    "Zaghouan":    ["zaghouan", "zaghwan", "زغwan", "زغوان"],
    "Sousse":      ["sousse", "sousa", "سوسة"],
    "Monastir":    ["monastir", "mounastir", "monstir", "المنستير"],
    "Mahdia":      ["mahdia", "mahdhia", "مهdية", "مهدية"],
    "Sfax":        ["sfax", "safaqis", "صفاقس"],
    "Kairouan":    ["kairouan", "kairouane", "القيروان"],
    "Kasserine":   ["kasserine", "kassarine", "القصرين"],
    "Sidi Bouzid": ["sidi bouzid", "sidi-bouzid", "sidibouzid", "سيدي بوزيد"],
    "Gafsa":       ["gafsa", "kafsa", "قفصة"],
    "Tozeur":      ["tozeur", "touzeur", "touzer", "توزر"],
    "Kébili":      ["kebili", "kébili", "qibili", "قبلي"],
    "Gabès":       ["gabes", "gabès", "gabs", "قابس"],
    "Médenine":    ["medenine", "médenine", "madanin", "مدنين"],
    "Tataouine":   ["tataouine", "tataouin", "تطاوين"],
}

# Variantes à plat pour difflib
_ALL_VARIANTS_FLAT = []
_VARIANT_TO_OFFICIAL: Dict[str, str] = {}
for _official, _variants in GOUV_VARIANTS.items():
    for _v in _variants:
        _ALL_VARIANTS_FLAT.append(_v)
        _VARIANT_TO_OFFICIAL[_v] = _official


def _normalize(text: str) -> str:
    """Normalise une chaîne : minuscules, sans accents, sans caractères spéciaux."""
    s = unicodedata.normalize('NFKD', str(text)).encode('ascii', errors='ignore').decode('utf-8')
    return s.lower().strip()


def _detect_gouvernorats_fuzzy(question: str) -> List[str]:
    """Détecte les gouvernorats mentionnés dans la question avec fuzzy matching."""
    detected = set()
    q_norm = _normalize(question)

    # 1. Correspondance exacte sur les variantes
    for variant, official in _VARIANT_TO_OFFICIAL.items():
        v_norm = _normalize(variant)
        if v_norm and len(v_norm) >= 3 and v_norm in q_norm:
            detected.add(official)

    # 2. Fuzzy matching sur les mots de la question
    tokens = re.findall(r'\b\w{3,}\b', q_norm)
    for token in tokens:
        matches = difflib.get_close_matches(token, _ALL_VARIANTS_FLAT, n=1, cutoff=0.82)
        if matches:
            official = _VARIANT_TO_OFFICIAL.get(matches[0])
            if official:
                detected.add(official)

    return list(detected)


class AnnuaireRAGAgent:
    """
    Agent RAG dédié aux questions sur les annuaires pluviométriques.
    Utilise exclusivement station_148 et pluies_148.
    """

    def __init__(self, database_url: str, vector_manager, provider_manager):
        self.database_url = database_url
        self.vector_manager = vector_manager
        self.provider_manager = provider_manager
        self.llm_provider = os.getenv("LLM_PROVIDER", "openrouter").lower()

    def _get_connection(self):
        return psycopg2.connect(self.database_url)

    # ── Retrieve Zvec ─────────────────────────────────────────────────────────

    def retrieve(self, question: str, entities: Dict[str, Any] = None, topk: int = 12) -> List[Dict[str, Any]]:
        """Recherche sémantique dans Zvec avec filtrage sémantique et re-scoring métadonnées."""
        try:
            # Query Zvec avec le double de la limite pour pouvoir filtrer et ré-ordonner ensuite
            raw_passages = self.vector_manager.query_annuaires_by_text(question, topk=topk * 2)
            if not raw_passages:
                return []

            if not entities:
                entities = self._detect_entities(question)

            filtered = []
            
            # 1. Filtrage strict par année si des années sont détectées dans le message
            if entities["annees"]:
                for p in raw_passages:
                    page_val = p.get("page")
                    # page=0 correspond aux métadonnées globales de stations qui sont toujours valides
                    if page_val == 0 or int(page_val) in entities["annees"]:
                        filtered.append(p)
            else:
                filtered = list(raw_passages)

            # 2. Boost (Re-scoring) par gouvernorat
            if entities["gouvernorats"]:
                scored_passages = []
                for p in filtered:
                    score = p.get("score", 1.0) # distance cosinus (plus petite = meilleure)
                    doc_name = p.get("doc_name", "").lower()
                    
                    boosted = False
                    for g in entities["gouvernorats"]:
                        if g.lower() in doc_name:
                            boosted = True
                            break
                    
                    if boosted:
                        # Réduire artificiellement la distance de 30% pour favoriser le passage
                        new_score = score * 0.7
                    else:
                        new_score = score
                        
                    p["boosted_score"] = new_score
                    scored_passages.append(p)
                
                # Trier par score boosté ascendant
                scored_passages.sort(key=lambda x: x.get("boosted_score", 1.0))
                filtered = scored_passages

            return filtered[:topk]
        except Exception as e:
            print(f"[AnnuaireRAG] Erreur retrieve Zvec : {e}")
            return []

    # ── Détection des entités ──────────────────────────────────────────────────

    def _detect_entities(self, question: str) -> Dict[str, Any]:
        """Extrait stations, gouvernorats et années depuis la question."""
        entities = {"stations": [], "gouvernorats": [], "annees": []}

        # Années (ex: 2017, 2018-2019)
        years = re.findall(r'\b(20\d{2}|19\d{2})\b', question)
        entities["annees"] = list(set(int(y) for y in years))

        # Gouvernorats avec fuzzy matching
        entities["gouvernorats"] = _detect_gouvernorats_fuzzy(question)

        # Détection dynamique des noms de stations depuis station_148 uniquement
        try:
            conn = self._get_connection()
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT DISTINCT LOWER(nom) FROM station_148
                    WHERE nom IS NOT NULL AND nom != '' AND LENGTH(nom) >= 4
                """)
                st_names = [r[0] for r in cur.fetchall()]
                q_low = question.lower()
                for st in st_names:
                    if len(st) >= 4 and st in q_low:
                        entities["stations"].append(st)
            conn.close()
        except Exception as e:
            print(f"[AnnuaireRAG] Avertissement détection stations SQL: {e}")

        print(f"[AnnuaireRAG] Entités détectées -> gouvernorats={entities['gouvernorats']}, "
              f"stations={entities['stations']}, années={entities['annees']}")
        return entities

    # ── Enrichissement SQL direct ─────────────────────────────────────────────

    def enrich_with_sql(self, question: str, entities: Dict[str, Any] = None) -> str:
        """Exécute des requêtes SQL ciblées sur station_148 et pluies_148."""
        if entities is None:
            entities = self._detect_entities(question)

        extra_context = []
        conn = None

        try:
            conn = self._get_connection()

            # ── 1. Recherche directe par Station ──────────────────────────────
            for st in entities["stations"]:
                try:
                    query = """
                        SELECT s.nom, s.gouvernorat, s.id_station,
                               EXTRACT(YEAR FROM p.date_obs)::int AS annee,
                               ROUND(SUM(p.valeur_mm)::numeric, 1) AS total_mm
                        FROM pluies_148 p
                        JOIN station_148 s ON p.id_station = s.id_station
                        WHERE LOWER(s.nom) LIKE %s
                    """
                    params = [f"%{st}%"]
                    if entities["annees"]:
                        placeholders = ", ".join(["%s"] * len(entities["annees"]))
                        query += f" AND EXTRACT(YEAR FROM p.date_obs) IN ({placeholders})"
                        params.extend(entities["annees"])
                    query += " GROUP BY s.nom, s.gouvernorat, s.id_station, EXTRACT(YEAR FROM p.date_obs) ORDER BY annee"

                    df = pd.read_sql(query, conn, params=params)
                    if not df.empty:
                        lines = [
                            f"  - Station {row['nom']} ({row['gouvernorat']}) - {int(row['annee'])}: {row['total_mm']} mm"
                            for _, row in df.iterrows()
                        ]
                        extra_context.append(
                            f"Données pluviométriques de la station '{st.title()}' :\n"
                            + "\n".join(lines)
                        )
                except Exception as e:
                    print(f"[AnnuaireRAG] Erreur SQL station {st}: {e}")

            # ── 2. Données pour Gouvernorats mentionnés ───────────────────────
            for gouv in entities["gouvernorats"]:
                try:
                    gouv_variants = GOUV_VARIANTS.get(gouv, [gouv.lower()])
                    gouv_conditions = " OR ".join(
                        ["LOWER(s.gouvernorat) LIKE %s"] * len(gouv_variants)
                    )
                    params_gouv = [f"%{v}%" for v in gouv_variants]

                    query = f"""
                        SELECT s.nom, s.id_station,
                               EXTRACT(YEAR FROM p.date_obs)::int AS annee,
                               ROUND(SUM(p.valeur_mm)::numeric, 1) AS total_mm
                        FROM pluies_148 p
                        JOIN station_148 s ON p.id_station = s.id_station
                        WHERE ({gouv_conditions})
                    """
                    if entities["annees"]:
                        placeholders = ", ".join(["%s"] * len(entities["annees"]))
                        query += f" AND EXTRACT(YEAR FROM p.date_obs) IN ({placeholders})"
                        params_gouv.extend(entities["annees"])
                    query += " GROUP BY s.nom, s.id_station, EXTRACT(YEAR FROM p.date_obs) ORDER BY s.nom, annee"

                    df = pd.read_sql(query, conn, params=params_gouv)
                    if not df.empty:
                        lines = [
                            f"  - {row['nom']} (ID: {row['id_station']}) - {int(row['annee'])}: {row['total_mm']} mm"
                            for _, row in df.iterrows()
                        ]
                        extra_context.append(
                            f"Données pluviométriques du Gouvernorat de {gouv} :\n"
                            + "\n".join(lines[:50])
                        )
                except Exception as e:
                    print(f"[AnnuaireRAG] Erreur SQL gouvernorat {gouv}: {e}")

            # ── 3. Recherche par mot-clé station si pas de résultat encore ───
            if not extra_context and not entities["gouvernorats"] and not entities["stations"]:
                STOP_WORDS = {
                    "quel", "quelle", "est", "le", "la", "les", "du", "de", "des",
                    "cumul", "total", "pluie", "station", "annee", "dans", "pour",
                    "carte", "isohyete", "tableau", "donner", "donnez",
                    "montrer", "montrez", "afficher", "affiche"
                }
                words = [
                    w for w in re.findall(r'\b[a-zA-Z\u00C0-\u024F]{4,}\b', question.lower())
                    if _normalize(w) not in STOP_WORDS
                ]
                for word in words[:5]:
                    try:
                        df = pd.read_sql("""
                            SELECT s.nom, s.gouvernorat,
                                   EXTRACT(YEAR FROM p.date_obs)::int AS annee,
                                   ROUND(SUM(p.valeur_mm)::numeric, 1) AS total_mm
                            FROM pluies_148 p
                            JOIN station_148 s ON p.id_station = s.id_station
                            WHERE LOWER(s.nom) LIKE %s
                            GROUP BY s.nom, s.gouvernorat, EXTRACT(YEAR FROM p.date_obs)
                            ORDER BY annee
                        """, conn, params=[f"%{_normalize(word)}%"])
                        if not df.empty:
                            lines = [
                                f"  - Station {row['nom']} ({row['gouvernorat']}) - {int(row['annee'])}: {row['total_mm']} mm"
                                for _, row in df.iterrows()
                            ]
                            extra_context.append(
                                f"Données trouvées pour '{word.title()}' :\n" + "\n".join(lines)
                            )
                            break
                    except Exception:
                        pass

            # ── 4. Fallback distribué (couvre toute la Tunisie) ──────────────
            if not extra_context:
                try:
                    year_filter = ""
                    params_fb = []
                    if entities["annees"]:
                        year_filter = f"WHERE EXTRACT(YEAR FROM p.date_obs) IN ({','.join(['%s']*len(entities['annees']))})"
                        params_fb = entities["annees"]

                    fallback_sql = f"""
                        WITH ranked AS (
                            SELECT
                                s.gouvernorat AS gouv,
                                s.nom AS station,
                                EXTRACT(YEAR FROM p.date_obs)::int AS annee,
                                ROUND(SUM(p.valeur_mm)::numeric, 1) AS total_mm,
                                ROW_NUMBER() OVER (
                                    PARTITION BY s.gouvernorat
                                    ORDER BY SUM(p.valeur_mm) DESC
                                ) AS rn
                            FROM pluies_148 p
                            JOIN station_148 s ON p.id_station = s.id_station
                            {year_filter}
                            GROUP BY s.gouvernorat, s.nom, EXTRACT(YEAR FROM p.date_obs)
                        )
                        SELECT gouv, station, annee, total_mm
                        FROM ranked
                        WHERE rn <= 2
                        ORDER BY gouv, annee, total_mm DESC
                        LIMIT 60
                    """
                    df_fallback = pd.read_sql(fallback_sql, conn,
                                              params=params_fb if params_fb else None)
                    if not df_fallback.empty:
                        lines = [
                            f"  - Station {r['station']} ({r['gouv']}) - {r['annee']}: {r['total_mm']} mm"
                            for _, r in df_fallback.iterrows()
                        ]
                        extra_context.append(
                            "Aperçu distribué des cumuls pluviométriques (toutes régions) :\n"
                            + "\n".join(lines)
                        )
                except Exception as fb_err:
                    print(f"[AnnuaireRAG] Avertissement SQL fallback : {fb_err}")

        except Exception as e:
            print(f"[AnnuaireRAG] Erreur connexion SQL : {e}")
        finally:
            if conn:
                conn.close()

        return "\n\n".join(extra_context)

    # ── Génération de la table HTML ────────────────────────────────────────────

    def _generate_table_html(self, entities: Dict[str, Any]) -> Optional[str]:
        """Génère toujours une table HTML pertinente depuis station_148 et pluies_148."""
        try:
            conn = self._get_connection()
            where_clauses = []
            params = []

            if entities["annees"]:
                where_clauses.append(
                    f"EXTRACT(YEAR FROM p.date_obs) IN ({','.join(['%s']*len(entities['annees']))})"
                )
                params.extend(entities["annees"])

            if entities["gouvernorats"]:
                gouv_subconds = []
                for g in entities["gouvernorats"]:
                    variants = GOUV_VARIANTS.get(g, [g.lower()])
                    conds = " OR ".join(["LOWER(s.gouvernorat) LIKE %s"] * len(variants))
                    gouv_subconds.append(f"({conds})")
                    params.extend([f"%{v}%" for v in variants])
                where_clauses.append("(" + " OR ".join(gouv_subconds) + ")")

            if entities["stations"]:
                st_conds = " OR ".join(["LOWER(s.nom) LIKE %s"] * len(entities["stations"]))
                where_clauses.append(f"({st_conds})")
                params.extend([f"%{st}%" for st in entities["stations"]])

            where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

            if not where_sql:
                # Si aucun filtre : requête distribuée pour couvrir toute la Tunisie
                query_tbl = """
                    WITH ranked AS (
                        SELECT
                            s.gouvernorat AS "Gouvernorat",
                            s.nom AS "Station",
                            EXTRACT(YEAR FROM p.date_obs)::int AS "Année",
                            ROUND(SUM(p.valeur_mm)::numeric, 1) AS "Cumul (mm)",
                            ROW_NUMBER() OVER (
                                PARTITION BY s.gouvernorat
                                ORDER BY SUM(p.valeur_mm) DESC
                            ) AS rn
                        FROM pluies_148 p
                        JOIN station_148 s ON p.id_station = s.id_station
                        GROUP BY s.gouvernorat, s.nom, EXTRACT(YEAR FROM p.date_obs)
                    )
                    SELECT "Gouvernorat", "Station", "Année", "Cumul (mm)"
                    FROM ranked
                    WHERE rn <= 3
                    ORDER BY "Gouvernorat", "Année", "Cumul (mm)" DESC
                    LIMIT 100
                """
                df_table = pd.read_sql(query_tbl, conn)
            else:
                query_tbl = f"""
                    SELECT
                        s.gouvernorat AS "Gouvernorat",
                        s.nom AS "Station",
                        EXTRACT(YEAR FROM p.date_obs)::int AS "Année",
                        ROUND(SUM(p.valeur_mm)::numeric, 1) AS "Cumul (mm)"
                    FROM pluies_148 p
                    JOIN station_148 s ON p.id_station = s.id_station
                    {where_sql}
                    GROUP BY s.gouvernorat, s.nom, EXTRACT(YEAR FROM p.date_obs)
                    ORDER BY "Gouvernorat", "Station", "Année"
                    LIMIT 300
                """
                df_table = pd.read_sql(query_tbl, conn, params=params if params else None)

            conn.close()

            if not df_table.empty:
                return df_table.to_html(classes="data-table", index=False, border=0)
            return None

        except Exception as e:
            print(f"[AnnuaireRAG] Erreur génération table_html : {e}")
            return None

    # ── Détection des images/cartes ────────────────────────────────────────────

    def _detect_images(self, question: str, entities: Dict[str, Any]) -> List[str]:
        """Détecte les figures/cartes demandées dans la question."""
        q_low = question.lower()
        images = []

        if not entities["gouvernorats"] or any(
            kw in q_low for kw in ["tunisie", "toute", "national", "tout le pays"]
        ):
            gouv_norm = "national"
        else:
            gouv = entities["gouvernorats"][0]
            s = _normalize(gouv)
            s = re.sub(r'[^a-z0-9]', '_', s)
            s = re.sub(r'_+', '_', s)
            gouv_norm = s.strip('_')

        year = entities["annees"][0] if entities["annees"] else 2018
        folder_name = f"images_temp_{gouv_norm}_{year}"
        WORKSPACE_ROOT = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        )

        KEYWORD_FORCED = {
            "carte_annuelle.png": [
                "carte", "map", "isohyete", "isohyète", "isohyètes", "isohyetes", "isohyet",
                "repartition spatiale", "répartition spatiale", "spatiale de la pluie",
                "carte pluviometrique", "carte pluviométrique"
            ],
            "carte_stations.png": [
                "carte des stations", "reseau de stations", "réseau de stations",
                "localisation des stations", "postes pluviometriques", "réseau pluviométrique"
            ],
            "pie_saisons.png": [
                "camembert", "graphe circulaire", "graphique circulaire",
                "diagramme circulaire", "diagramme en secteurs", "pie chart"
            ],
            "hist_mensuel.png": [
                "histogramme mensuel", "histogramme par mois", "barres mensuelles",
                "pluie par mois"
            ],
            "hist_classes.png": [
                "histogramme des classes", "repartition par classe", "classes de precipitation"
            ],
            "carte_rapport_normale.png": [
                "ecart a la normale", "écart à la normale", "rapport a la normale",
                "rapport à la normale", "anomalie pluviometrique", "anomalie pluviométrique"
            ],
            "carte_saisons_subplots.png": [
                "cartes saisonnieres", "cartes saisonnières", "carte saisonniere",
                "saisons subplots", "quatre saisons"
            ],
            "carte_interannuelle.png": [
                "interannuelle", "inter-annuelle", "moyenne pluriannuelle",
                "normale climatique", "long terme"
            ],
        }

        needed_files = []
        forced_file = None
        for filename, kws in KEYWORD_FORCED.items():
            if any(kw in q_low for kw in kws):
                forced_file = filename
                print(f"[AnnuaireRAG] Carte forcée par mot-clé: {filename}")
                break

        if forced_file:
            needed_files.append(forced_file)
        else:
            # Recherche sémantique via Zvec
            matches = self.vector_manager.query_images_by_text(question, topk=2)
            for match in matches:
                if match["score"] < 0.5:
                    print(f"[AnnuaireRAG] Carte détectée sémantiquement: {match['filename']} (distance: {match['score']:.2f})")
                    needed_files.append(match["filename"])
                    break

        if needed_files:
            folder_path = os.path.join(WORKSPACE_ROOT, folder_name)
            missing = any(not os.path.exists(os.path.join(folder_path, f)) for f in needed_files)
            if missing:
                print(f"[AnnuaireRAG] Images manquantes dans {folder_name}. Génération...")
                cmd = [
                    sys.executable,
                    os.path.join(WORKSPACE_ROOT, "generer_annuaire_database.py"),
                    "--year", str(year),
                    "--gouv", str(gouv_norm),
                    "--only-images"
                ]
                subprocess.run(cmd, cwd=WORKSPACE_ROOT, capture_output=True)

            for f in needed_files:
                images.append(f"/api/v1/annuaire/image/{folder_name}/{f}")

        return images

    # ── Construction du prompt LLM ────────────────────────────────────────────

    def _build_prompt(self, question: str, rag_passages: List[Dict], sql_context: str, has_map_image: bool = False) -> tuple:
        """Construit le system prompt et le user prompt pour le LLM."""
        if has_map_image:
            system_prompt = (
                "Tu es l'assistant IA officiel de la DGRE Tunisie.\n"
                "Le client a demandé une CARTE. La carte pluviométrique correspondante a été générée et s'affiche ci-dessous.\n"
                "DIRECTIVE STRICTE DE FORMAT POUR UNE DEMANDE DE CARTE :\n"
                "1. Démarre IMMÉDIATEMENT par : 'Voici la carte pluviométrique générée pour [Région/Année] :'\n"
                "2. Donne un très court résumé en 2-3 puces (ex: cumul max, cumul min, tendance générale).\n"
                "3. NE LISTE SURTOUT PAS toutes les stations une par une."
            )
        else:
            system_prompt = (
                "Tu es l'assistant IA officiel de la DGRE Tunisie.\n"
                "DIRECTIVE STRICTE DE FORMAT :\n"
                "1. Démarre IMMÉDIATEMENT par UNE SEULE petite phrase d'introduction (ex: 'Voici les cumuls pluviométriques enregistrés pour la région X en Y :').\n"
                "2. Donne DIRECTEMENT les données sous forme de liste à puces (bullet points).\n"
                "3. Ne fais NI préambule, NI explications sur la méthode, NI paragraphe de conclusion ('En résumé...', 'Ces stations sont...').\n"
                "4. Sois ultra-concis, direct et précis (donne toujours les valeurs en mm).\n"
                "5. Si les données SQL et Zvec donnent des informations différentes, priorité aux DONNÉES SQL (plus fraîches et précises)."
            )

        rag_text = ""
        sources = []
        if rag_passages:
            rag_text = "=== DONNÉES INDEXÉES (Zvec) ===\n"
            for i, p in enumerate(rag_passages[:8]):
                rag_text += f"\n[Source {i+1}: {p.get('doc_name', 'annuaire')}]\n"
                rag_text += p.get("text_content", "") + "\n"
                sources.append(p.get("doc_name", "annuaire"))

        sql_text = ""
        if sql_context.strip():
            sql_text = f"\n=== DONNÉES TEMPS RÉEL (PostgreSQL — priorité haute) ===\n{sql_context}\n"

        user_prompt = (
            f"{rag_text}{sql_text}\n"
            f"=== QUESTION ===\n{question}\n\n"
            "Réponds directement en appliquant la directive de format :"
        )

        return system_prompt, user_prompt, sources

    def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        """Appelle le LLM via le provider_manager."""
        try:
            return self.provider_manager.call_llm_api(
                self.llm_provider, user_prompt, system_prompt
            )
        except Exception as e:
            print(f"[AnnuaireRAG] Erreur LLM ({self.llm_provider}): {e}")
            return f"[Erreur LLM: {str(e)}] Données disponibles dans les sources."

    # ── Pipeline principal ────────────────────────────────────────────────────

    def answer(self, question: str, llm_provider: Optional[str] = None) -> Dict[str, Any]:
        """Pipeline RAG principal."""
        if llm_provider:
            self.llm_provider = llm_provider.lower()

        print(f"[AnnuaireRAG] Question : '{question}' | Provider: {self.llm_provider}")

        # 1. Détection des entités
        entities = self._detect_entities(question)

        # 2. Détection des images
        detected_images = self._detect_images(question, entities)

        # 3. Retrieve Zvec avec Metadata filtering & Re-scoring
        passages = self.retrieve(question, entities, topk=12)

        # 4. Enrichissement SQL
        sql_context = self.enrich_with_sql(question, entities)

        # 5. Table HTML
        table_html = self._generate_table_html(entities)

        # 6. Fallback si aucune source
        if not passages and not sql_context.strip():
            return {
                "answer": (
                    "Je n'ai pas trouvé de données pertinentes pour répondre à cette question. "
                    "Veuillez d'abord indexer les données via le bouton 'Indexer les données'."
                ),
                "sources": [],
                "nb_passages": 0,
                "images": detected_images,
                "table_html": table_html
            }

        # 7. Prompt & LLM
        has_map = len(detected_images) > 0
        system_prompt, user_prompt, sources = self._build_prompt(
            question, passages, sql_context, has_map_image=has_map
        )

        answer_text = self._call_llm(system_prompt, user_prompt)

        return {
            "answer": answer_text.strip(),
            "sources": list(set(sources)),
            "nb_passages": len(passages),
            "images": detected_images,
            "table_html": table_html
        }
