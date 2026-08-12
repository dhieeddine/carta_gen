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

    # Si la question parle de toute la Tunisie ou échelle nationale, ignorer 'Tunis'
    is_national_scope = any(kw in q_norm for kw in ["tunisie", "national", "toute la tunisie", "tout le pays"])

    # 1. Correspondance exacte sur les variantes
    for variant, official in _VARIANT_TO_OFFICIAL.items():
        v_norm = _normalize(variant)
        if v_norm and len(v_norm) >= 3 and v_norm in q_norm:
            if official == "Tunis" and is_national_scope and v_norm in ["tunis", "tous"]:
                continue
            detected.add(official)

    # 2. Fuzzy matching sur les mots de la question
    tokens = re.findall(r'\b\w{3,}\b', q_norm)
    for token in tokens:
        if is_national_scope and token in ["tunisie", "tunisie2021", "tunisien"]:
            continue
        matches = difflib.get_close_matches(token, _ALL_VARIANTS_FLAT, n=1, cutoff=0.82)
        if matches:
            official = _VARIANT_TO_OFFICIAL.get(matches[0])
            if official:
                if official == "Tunis" and is_national_scope:
                    continue
                detected.add(official)

    return list(detected)


class AnnuaireRAGAgent:
    """
    Agent RAG dédié aux questions sur les annuaires pluviométriques.
    Utilise exclusivement station_148 et pluies_148.
    """

    def __init__(self, database_url: str, vector_manager, provider_manager, orchestrator=None):
        self.database_url = database_url
        self.vector_manager = vector_manager
        self.provider_manager = provider_manager
        self.orchestrator = orchestrator
        self.llm_provider = os.getenv("LLM_PROVIDER", "openrouter").lower()
        self.last_system_prompt = ""
        self.last_user_prompt = ""
        self.last_response = ""

    # ...

    def answer(self, question: str, llm_provider: Optional[str] = None, use_rag: bool = True) -> Dict[str, Any]:
        """Pipeline RAG principal avec génération dynamique de code Python SIG / Matplotlib via l'Orchestrateur."""
        if llm_provider:
            self.llm_provider = llm_provider.lower()

        print(f"[AnnuaireRAG] Question : '{question}' | Provider: {self.llm_provider} | RAG: {use_rag}")

        # 1. Détection des entités
        entities = self._detect_entities(question)

        # 2. Vérification si la demande nécessite une Carte / Graphique dynamique
        q_low = question.lower()
        is_visual_request = any(kw in q_low for kw in ["carte", "isohyete", "isohyète", "map", "histogramme", "camembert", "pie", "top 10", "thiessen", "graphe"])
        
        detected_images = []
        generated_code = ""
        gen_map_traces = {}
        
        # 2. Détection prioritaire d'images/cartes statiques pré-existantes dans les annuaires
        if is_visual_request:
            detected_images = self._detect_images(question, entities)
            if detected_images:
                print(f"[AnnuaireRAG] Carte d'annuaire officielle pré-existante trouvée : {detected_images}")

        # 3. Si aucune carte statique officielle n'existe, solliciter l'Orchestrateur Multi-Agents LLM
        if is_visual_request and not detected_images and self.orchestrator:
            try:
                print(f"[AnnuaireRAG -> Orchestrateur] Aucune carte statique d'annuaire trouvée. Génération dynamique de code Python SIG pour : '{question}'")
                from cartagen.domain.models.map_request import MapRequest
                map_req = MapRequest(prompt=question, request_id="chat_gen", created_at=None, user_id=None)
                gen_map = self.orchestrator.process_request(map_req, llm_provider=self.llm_provider)
                if gen_map and gen_map.image_url:
                    detected_images.append(gen_map.image_url)
                if gen_map and gen_map.python_code:
                    generated_code = gen_map.python_code
                if gen_map and hasattr(gen_map, "agent_traces") and gen_map.agent_traces:
                    gen_map_traces = gen_map.agent_traces
            except Exception as e:
                print(f"[AnnuaireRAG] Erreur lors de la génération dynamique de code : {e}")

        if use_rag:
            # Mode RAG Textuel Complet (Passages Zvec + SQL + Table HTML)
            passages = self.retrieve(question, entities, topk=12)
            sql_context = self.enrich_with_sql(question, entities)
            table_html = self._generate_table_html(entities)
        else:
            # Mode Pure LLM Textuel (Bypass contextes textuels Zvec et Postgres)
            passages = []
            sql_context = ""
            table_html = None

        # 5. Prompt Direct vers le LLM Fine-Tuné
        has_map = len(detected_images) > 0
        system_prompt, user_prompt, sources = self._build_prompt(
            question, passages, sql_context, has_map_image=has_map
        )

        answer_text = self._call_llm(system_prompt, user_prompt)
        if not answer_text:
            answer_text = "Désolé, le modèle n'a pas pu générer de réponse pour le moment."

        # Si du code Python a été généré dynamiquement par le modèle, l'inclure dans la réponse
        if generated_code:
            answer_text = f"{answer_text}\n\n```python\n{generated_code}\n```"

        agent_traces = {
            "annuaire_rag_agent": {
                "system_prompt": getattr(self, "last_system_prompt", ""),
                "user_prompt": getattr(self, "last_user_prompt", ""),
                "response": getattr(self, "last_response", "")
            }
        }
        if gen_map_traces:
            agent_traces.update(gen_map_traces)

        return {
            "answer": str(answer_text).strip(),
            "sources": list(set(sources)),
            "nb_passages": len(passages),
            "images": detected_images,
            "table_html": table_html,
            "agent_traces": agent_traces
        } 

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
        """Extrait stations, gouvernorats, années, mois et jours depuis la question."""
        entities = {"stations": [], "gouvernorats": [], "annees": [], "mois": [], "jours": []}
        q_low = question.lower()

        # 1. Années (ex: 2017, 2018-2019)
        years = re.findall(r'\b(20\d{2}|19\d{2})\b', question)
        entities["annees"] = list(set(int(y) for y in years))

        # 2. Mois (ex: janvier, fevrier, oct, nov, etc.)
        mois_mapping = {
            "janvier": 1, "janv": 1, "jan": 1,
            "février": 2, "fevrier": 2, "févr": 2, "fevr": 2, "fev": 2,
            "mars": 3, "mar": 3,
            "avril": 4, "avr": 4,
            "mai": 5,
            "juin": 6,
            "juillet": 7, "juil": 7,
            "août": 8, "aout": 8,
            "septembre": 9, "sept": 9, "sep": 9,
            "octobre": 10, "octo": 10, "oct": 10,
            "novembre": 11, "nove": 11, "nov": 11,
            "décembre": 12, "decembre": 12, "dece": 12, "dec": 12
        }
        for m_name, m_num in mois_mapping.items():
            if re.search(r'\b' + re.escape(m_name) + r'\b', q_low):
                if m_num not in entities["mois"]:
                    entities["mois"].append(m_num)

        # 3. Jours (ex: 15 janvier, le 20)
        days = re.findall(r'\b([1-9]|[12]\d|3[01])\b', question)
        # On ne conserve que si des mois ou années entourent le nombre
        if entities["mois"] or entities["annees"]:
            entities["jours"] = list(set(int(d) for d in days if 1 <= int(d) <= 31))

        # 4. Gouvernorats avec fuzzy matching
        entities["gouvernorats"] = _detect_gouvernorats_fuzzy(question)

        # 5. Détection dynamique des noms de stations depuis station_148 uniquement
        try:
            conn = self._get_connection()
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT DISTINCT LOWER(nom) FROM station_148
                    WHERE nom IS NOT NULL AND nom != '' AND LENGTH(nom) >= 4
                """)
                st_names = [r[0] for r in cur.fetchall()]
                for st in st_names:
                    if len(st) >= 4 and re.search(r'\b' + re.escape(st) + r'\b', q_low):
                        entities["stations"].append(st)
            conn.close()
        except Exception as e:
            print(f"[AnnuaireRAG] Avertissement détection stations SQL: {e}")

        print(f"[AnnuaireRAG] Entités détectées -> gouvernorats={entities['gouvernorats']}, "
              f"stations={entities['stations']}, années={entities['annees']}, mois={entities['mois']}")
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
                    where_conds = []
                    params_fb = []
                    if entities["annees"]:
                        where_conds.append(f"EXTRACT(YEAR FROM p.date_obs) IN ({','.join(['%s']*len(entities['annees']))})")
                        params_fb.extend(entities["annees"])
                    if entities["mois"]:
                        where_conds.append(f"EXTRACT(MONTH FROM p.date_obs) IN ({','.join(['%s']*len(entities['mois']))})")
                        params_fb.extend(entities["mois"])

                    year_filter = ("WHERE " + " AND ".join(where_conds)) if where_conds else ""

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

            if entities["mois"]:
                where_clauses.append(
                    f"EXTRACT(MONTH FROM p.date_obs) IN ({','.join(['%s']*len(entities['mois']))})"
                )
                params.extend(entities["mois"])

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

        needed_files = []

        # 1. Utilisation du LLM Provider pour classifier la figure exacte dans le catalogue d'annuaire
        if self.provider_manager:
            try:
                system_prompt = (
                    "Tu es l'agent d'intelligence visuelle de la DGRE.\n"
                    "Voici la liste des figures officielles enregistrées dans l'annuaire pluviométrique :\n"
                    "- carte_saison_auto.png / carte_saison_hiver.png / carte_saison_print.png / carte_saison_ete.png : Cartes isohyètes individuelles séparées pour une saison spécifique.\n"
                    "- carte_mois_sept.png / carte_mois_octo.png / carte_mois_nove.png / carte_mois_dece.png / carte_mois_janv.png / carte_mois_fev.png / carte_mois_mar.png / carte_mois_avr.png / carte_mois_mai.png / carte_mois_juin.png / carte_mois_juil.png / carte_mois_aout.png : Cartes isohyètes individuelles séparées pour un mois spécifique.\n"
                    "- carte_annuelle.png : Carte isohyète de pluie cumulée sur toute l'année (annuelle globale).\n"
                    "- carte_interannuelle.png : Carte des moyennes historiques sur plusieurs dizaines d'années (normale climatique).\n"
                    "- carte_saisons_subplots.png : Subplots 4 cartes des 4 saisons de l'année (pour le rapport PDF).\n"
                    "- carte_rapport_normale.png : Carte d'écart/anomalie par rapport à la normale.\n"
                    "- carte_stations.png : Carte des emplacements des stations météo.\n"
                    "- hist_mensuel.png : Histogramme des cumuls mensuels de pluie.\n"
                    "- hist_classes.png : Histogramme de distribution des classes de précipitation.\n"
                    "- pie_saisons.png : Graphique en camembert (pie chart) de la répartition par saison.\n"
                    "- comparaison_nord.png / comparaison_centrale.png / comparaison_sud.png : Graphiques comparatifs régionaux.\n\n"
                    "TÂCHE :\n"
                    "Si la question de l'utilisateur demande une figure officielle appartenant à cette liste, réponds UNIQUEMENT avec le nom exact du fichier image (ex: 'carte_saison_auto.png' ou 'carte_mois_janv.png' ou 'carte_annuelle.png').\n"
                    "Si la demande nécessite une carte inédite non présente dans ce catalogue (ex: une région custom), réponds EXCLUSIVEMENT 'GENERATION_DYNAMIQUE'."
                )
                user_prompt = f"Question Utilisateur : '{question}'"
                res = self.provider_manager.call_llm_api(
                    provider_id=self.llm_provider,
                    prompt=user_prompt,
                    system_prompt=system_prompt
                ).strip().lower()

                print(f"[AnnuaireRAG -> LLM Visual Decision] Résultat du LLM ('{self.llm_provider}') : '{res}'")
                
                catalog = [
                    "carte_saison_auto.png", "carte_saison_hiver.png", "carte_saison_print.png", "carte_saison_ete.png",
                    "carte_mois_sept.png", "carte_mois_octo.png", "carte_mois_nove.png", "carte_mois_dece.png",
                    "carte_mois_janv.png", "carte_mois_fev.png", "carte_mois_mar.png", "carte_mois_avr.png",
                    "carte_mois_mai.png", "carte_mois_juin.png", "carte_mois_juil.png", "carte_mois_aout.png",
                    "carte_annuelle.png", "carte_interannuelle.png", "carte_saisons_subplots.png",
                    "carte_rapport_normale.png", "carte_stations.png", "hist_mensuel.png", "hist_classes.png",
                    "pie_saisons.png", "comparaison_nord.png", "comparaison_centrale.png", "comparaison_sud.png"
                ]
                
                for filename in catalog:
                    if filename in res:
                        print(f"[AnnuaireRAG -> LLM Decision] Le LLM a sélectionné la figure officielle : '{filename}'")
                        needed_files.append(filename)
                        break

            except Exception as e:
                print(f"[AnnuaireRAG] Avertissement décision LLM visual ({e}).")

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
        """Construit un System Prompt unique et combiné ainsi que le User Prompt pour le LLM."""
        system_prompt = (
            "Tu es l'assistant IA officiel expert pour les ressources en eau et la pluviométrie de la Tunisie (DGRE).\n"
            "DIRECTIVES UNIVERSELLES ET IMPÉRATIVES DE FORMAT :\n"
            "1. CAS DEMANDE DE CARTE OU GRAPHIQUE VISUEL (IMAGE PRÉSENTE OU GÉNÉRÉE) :\n"
            "   - Démarre OBLIGATOIREMENT par : 'Voici la carte des isohyètes / le graphique pluviométrique demandé :'\n"
            "   - Donne UNIQUEMENT une synthèse globale synthétique de 2 à 3 lignes (cumul moyen national/régional, gouvernorat le plus arrosé, gouvernorat le moins arrosé).\n"
            "   - INTERDICTION ABSOLUE de lister les stations individuelles une par une (pas de '- Station X - 2020: Y mm').\n"
            "2. CAS DEMANDE DE DONNÉES / SYNTHÈSE EN LANGAGE NATUREL :\n"
            "   - Démarre par une courte phrase d'introduction.\n"
            "   - Donne les informations directement sous forme de puces synthétiques (bullet points).\n"
            "   - Reste ultra-concis, direct et précis (exprime toujours les précipitations en mm).\n"
            "3. RÈGLE DES SOURCES ET CONFLITS :\n"
            "   - S'il y a des données '=== DONNÉES TEMPS RÉEL (PostgreSQL) ===', utilise-les prioritairement pour les chiffres exacts.\n"
            "   - S'il y a des données '=== DONNÉES INDEXÉES (Zvec) ===', utilise-les pour enrichir l'explication historique.\n"
            "   - En l'absence de données RAG ou SQL, réponds de manière autonome avec une grande précision métier."
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

        if not rag_text and not sql_text:
            user_prompt = f"=== QUESTION ===\n{question}\n\nRéponds directement de manière précise et naturelle :"
        else:
            context_type = "CARTE/GRAPHIQUE GÉNÉRÉ" if has_map_image else "ANALYSE DE DONNÉES"
            user_prompt = (
                f"=== CONTEXTE VISUEL : {context_type} ===\n"
                f"{rag_text}{sql_text}\n"
                f"=== QUESTION ===\n{question}\n\n"
                "Réponds directement en appliquant les directives universelles :"
            )

        return system_prompt, user_prompt, sources

    def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        """Appelle le LLM via le provider_manager."""
        self.last_system_prompt = system_prompt
        self.last_user_prompt = user_prompt
        try:
            res = self.provider_manager.call_llm_api(
                self.llm_provider, user_prompt, system_prompt
            )
            self.last_response = res
            return res
        except Exception as e:
            print(f"[AnnuaireRAG] Erreur LLM ({self.llm_provider}): {e}")
            err_msg = f"[Erreur LLM: {str(e)}] Données disponibles dans les sources."
            self.last_response = err_msg
            return err_msg


