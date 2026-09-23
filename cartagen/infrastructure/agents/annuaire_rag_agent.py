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
                print(f"[AnnuaireRAG] Carte d'annuaire officielle pré-existante trouvée directement : {detected_images}")

        # 3. Si aucune carte statique officielle n'existe, solliciter l'Orchestrateur Multi-Agents LLM
        if is_visual_request and not detected_images and self.orchestrator:
            try:
                print(f"[AnnuaireRAG -> Orchestrateur] Aucune carte statique trouvée. Génération dynamique de code Python SIG pour : '{question}'")
                from cartagen.domain.models.map_request import MapRequest
                map_req = MapRequest(prompt=question, request_id="chat_gen", created_at=None, user_id=None)
                gen_map = self.orchestrator.process_request(map_req, llm_provider=self.llm_provider)
                if gen_map and gen_map.image_url:
                    img_url = gen_map.image_url
                    if not img_url.startswith("http") and not img_url.startswith("/"):
                        filename = os.path.basename(img_url)
                        img_url = f"/api/v1/maps/image/{filename}"
                    detected_images.append(img_url)
                if gen_map and gen_map.python_code:
                    generated_code = gen_map.python_code
                if gen_map and hasattr(gen_map, "agent_traces") and gen_map.agent_traces:
                    gen_map_traces = gen_map.agent_traces
            except Exception as e:
                print(f"[AnnuaireRAG] Erreur lors de la génération dynamique de code : {e}")

        # 4. Données tabulaires et contextuelles
        if use_rag:
            passages = self.retrieve(question, entities, topk=12)
            sql_context = self.enrich_with_sql(question, entities)
            table_html = self._generate_table_html(entities)
        else:
            passages = []
            sql_context = ""
            table_html = None

        sources = [p.get("doc_name", "annuaire_dgre") for p in passages] if passages else ["Annuaire Pluviométrique Officiel DGRE"]

        # 5. Si une carte officielle d'annuaire a été détectée, RENDRE DIRECTEMENT SANS APPEL LLM
        if detected_images and not generated_code:
            year_val = entities["annees"][0] if entities["annees"] else 2020
            scope_val = entities["gouvernorats"][0] if entities["gouvernorats"] else "la Tunisie entière"
            img_url = detected_images[0]

            if any(k in img_url.lower() for k in ["carte_annuelle", "isohyete", "isohyetes"]):
                answer_text = (
                    f"🗺️ **Carte Officielle des Isohyètes ({year_val}) — DGRE Tunisie**\n\n"
                    f"Voici la carte officielle des isohyètes pour **{scope_val}** (Année hydrologique **{year_val}**).\n\n"
                    f"• **Source** : Annuaire Pluviométrique Officiel de la DGRE\n"
                    f"• **Méthode** : Interpolation spatiale géostatistique par Inverse Distance Weighting (IDW, $\\alpha=2.0$)\n"
                    f"• **Réseau** : 148 stations pluviométriques de référence certifiées sous UTM 32N (EPSG:32632)\n\n"
                    f"*(La carte officielle a été récupérée directement depuis l'annuaire et est affichée dans l'onglet **Rendu** ci-contre.)*"
                )
            elif "saison" in img_url.lower():
                answer_text = (
                    f"🍂❄️🌸☀️ **Cartes Pluviométriques Saisonnières ({year_val})**\n\n"
                    f"Voici la répartition cartographique des précipitations par saison pour l'année **{year_val}** (Automne, Hiver, Printemps, Été).\n\n"
                    f"• **Source** : Annuaire officiel de la DGRE\n"
                    f"*(Affichée dans l'onglet **Rendu** ci-contre.)*"
                )
            elif any(k in img_url.lower() for k in ["normale", "anomalie"]):
                answer_text = (
                    f"📊 **Carte d'Anomalie Pluviométrique / Rapport à la Normale ({year_val})**\n\n"
                    f"Voici la carte d'écart par rapport à la normale cinquantenaire (1959–2009) pour l'année **{year_val}**, identifiant les zones de déficit et d'excédent hydrique.\n\n"
                    f"*(Affichée dans l'onglet **Rendu** ci-contre.)*"
                )
            elif any(k in img_url.lower() for k in ["station", "reseau"]):
                answer_text = (
                    f"📍 **Carte du Réseau des 148 Stations Nationales de Référence**\n\n"
                    f"Voici la distribution spatiale des 148 stations pluviométriques de référence sur les 24 gouvernorats de la Tunisie.\n\n"
                    f"*(Affichée dans l'onglet **Rendu** ci-contre.)*"
                )
            elif "region" in img_url.lower():
                answer_text = (
                    f"🗺️ **Carte des Régions Naturelles de la Tunisie**\n\n"
                    f"Voici le découpage officiel de la Tunisie en 6 régions hydro-climatiques (Nord-Ouest, Nord-Est, Centre-Ouest, Centre-Est, Sud-Ouest, Sud-Est).\n\n"
                    f"*(Affichée dans l'onglet **Rendu** ci-contre.)*"
                )
            else:
                answer_text = (
                    f"📈 **Figure Officielle de l'Annuaire Pluviométrique ({year_val})**\n\n"
                    f"Voici la figure demandée extraite directement des archives officielles de la DGRE.\n\n"
                    f"*(Affichée dans l'onglet **Rendu** ci-contre.)*"
                )
        else:
            # 6. Traitement standard via LLM pour les requêtes textuelles ou génération dynamique
            has_map = len(detected_images) > 0
            system_prompt, user_prompt, src_list = self._build_prompt(
                question, passages, sql_context, has_map_image=has_map
            )
            if src_list:
                sources = src_list

            answer_text = self._call_llm(system_prompt, user_prompt)
            # Fallback intelligent si le LLM est indisponible mais que des données SQL/RAG existent
            if not answer_text or "Erreur LLM" in answer_text:
                if sql_context:
                    answer_text = (
                        f"📊 **Données Pluviométriques Officielles (DGRE)**\n\n"
                        f"Voici les données enregistrées extraites de la base PostgreSQL centrale :\n\n"
                        f"{sql_context}\n\n"
                        f"*(Données issues des stations de référence de la DGRE.)*"
                    )
                else:
                    answer_text = "Voici les informations pluviométriques extraites de la base de données de la DGRE."

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
            "code": generated_code,
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

    # ── Détection des images/cartes ────────────────────────────────────────────

    def _detect_images(self, question: str, entities: Dict[str, Any]) -> List[str]:
        """Détecte immédiatement les figures/cartes demandées dans la question et vérifie leur existence dans l'annuaire SANS dépendance LLM."""
        q_low = question.lower()
        q_norm = _normalize(question)
        images = []

        if not entities["gouvernorats"] or any(
            kw in q_norm for kw in ["tunisie", "toute", "national", "tout le pays", "pays"]
        ):
            gouv_norm = "national"
            scope_label = "la Tunisie entière"
        else:
            gouv = entities["gouvernorats"][0]
            s = _normalize(gouv)
            s = re.sub(r'[^a-z0-9]', '_', s)
            s = re.sub(r'_+', '_', s)
            gouv_norm = s.strip('_')
            scope_label = f"le Gouvernorat de {gouv}"

        year = entities["annees"][0] if entities["annees"] else 2020
        folder_name = f"images_temp_{gouv_norm}_{year}"
        WORKSPACE_ROOT = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        )

        needed_files = []

        # ── 1. CLASSIFICATION DÉTERMINISTE DE LA FIGURE (DIRECT SANS LLM) ───
        # A. Carte des isohyètes annuelles / pluviométrie globale
        is_annual_isohyet = (
            any(w in q_norm for w in ["isohyete", "isohyetes"]) or
            (any(w in q_norm for w in ["carte", "map"]) and any(w in q_norm for w in ["annuel", "annuelle", "cumul", "pluie", "pluies", "pluviometrique", "pluviometrie", "precipitations", "precipitation", "tunisie"]))
        )
        
        # B. 4 Saisons subplots
        is_seasons_all = (
            any(w in q_norm for w in ["saison", "saisons"]) and
            any(w in q_norm for w in ["4", "quatre", "tous", "toutes", "subplots", "ensemble", "panneaux", "panel"])
        ) or (
            "saisons" in q_norm and not any(w in q_norm for w in ["automne", "hiver", "printemps", "ete"])
        )

        # C. Saisons individuelles (avec frontières de mots strictes)
        is_automne = bool(re.search(r'\b(automne|automnal|automnale)\b', q_norm))
        is_hiver = bool(re.search(r'\b(hiver|hivernale|hivernal)\b', q_norm))
        is_printemps = bool(re.search(r'\b(printemps|printaniere|printanier)\b', q_norm))
        is_ete = bool(re.search(r'\b(ete|estivale|estival)\b', q_norm))

        # D. Anomalie / Rapport normale
        is_anomalie = any(w in q_norm for w in ["anomalie", "anomalies", "rapport normale", "normale", "deficit", "deficits", "ecart", "ecarts"])

        # E. Interannuelle / Climatologique (50 ans)
        is_interannuelle = any(w in q_norm for w in ["interannuel", "interannuelle", "50 ans", "cinquantenaire", "climatologique", "moyenne historique"])

        # F. Stations / Réseau pluviométrique
        is_stations = any(w in q_norm for w in ["station", "stations", "reseau", "réseau", "poste", "postes", "pluviometre", "pluviometres"]) and any(w in q_norm for w in ["carte", "emplacement", "localisation", "map"])

        # G. Régions naturelles
        is_regions = any(w in q_norm for w in ["region naturelle", "regions naturelles", "naturelles", "hydrographique"])

        # H. Mois spécifiques
        mois_files = {
            1: "carte_mois_janv.png", 2: "carte_mois_fev.png", 3: "carte_mois_mar.png",
            4: "carte_mois_avr.png", 5: "carte_mois_mai.png", 6: "carte_mois_juin.png",
            7: "carte_mois_juil.png", 8: "carte_mois_aout.png", 9: "carte_mois_sept.png",
            10: "carte_mois_octo.png", 11: "carte_mois_nove.png", 12: "carte_mois_dece.png"
        }

        # Attribution prioritaire rigoureuse
        if is_regions:
            needed_files.append("regions_naturelles_tunisie.png")
        elif is_annual_isohyet and not (is_seasons_all or is_automne or is_hiver or is_printemps or is_ete or is_anomalie):
            needed_files.append("carte_annuelle.png")
        elif is_seasons_all:
            needed_files.append("carte_saisons_subplots.png")
        elif is_automne:
            needed_files.append("carte_saison_auto.png")
        elif is_hiver:
            needed_files.append("carte_saison_hiver.png")
        elif is_printemps:
            needed_files.append("carte_saison_print.png")
        elif is_ete:
            needed_files.append("carte_saison_ete.png")
        elif is_anomalie:
            needed_files.append("carte_rapport_normale.png")
        elif is_interannuelle:
            needed_files.append("carte_interannuelle.png")
        elif is_stations:
            needed_files.append("carte_stations.png")
        elif entities["mois"] and any(w in q_norm for w in ["carte", "mois", "isohyete"]):
            m = entities["mois"][0]
            if m in mois_files:
                needed_files.append(mois_files[m])
        elif is_annual_isohyet:
            needed_files.append("carte_annuelle.png")
        elif any(w in q_norm for w in ["pie", "camembert", "repartition"]):
            needed_files.append("pie_saisons.png")
        elif any(w in q_norm for w in ["histogramme", "barres", "hist"]):
            needed_files.append("hist_mensuel.png")
        elif any(w in q_norm for w in ["comparatif", "comparaison"]):
            needed_files.append("comparatif_pluviometrique_regional.png")

        print(f"[AnnuaireRAG -> Direct Detection] Figures demandées détectées : {needed_files}")

        # ── 2. VÉRIFICATION D'EXISTENCE SUR LE DISQUE DANS L'ANNUAIRE ─────────
        for filename in needed_files:
            candidate_paths = [
                (os.path.join(WORKSPACE_ROOT, folder_name, filename), f"/api/v1/annuaire/image/{folder_name}/{filename}"),
                (os.path.join(WORKSPACE_ROOT, f"images_temp_national_{year}", filename), f"/api/v1/annuaire/image/images_temp_national_{year}/{filename}"),
                (os.path.join(WORKSPACE_ROOT, f"images_temp_all_{year}", filename), f"/api/v1/annuaire/image/images_temp_all_{year}/{filename}"),
                (os.path.join(WORKSPACE_ROOT, "images_temp_national_2020", filename), f"/api/v1/annuaire/image/images_temp_national_2020/{filename}"),
                (os.path.join(WORKSPACE_ROOT, "images_temp", filename), f"/api/v1/annuaire/image/images_temp/{filename}"),
                (os.path.join(WORKSPACE_ROOT, "figures", filename), f"/figures/{filename}"),
            ]
            
            # Correspondance des noms dans figures/ (rapport de stage officiel)
            fig_aliases = {
                "carte_annuelle.png": "carte_isohyetes_annuelle_2020.png",
                "carte_saisons_subplots.png": "cartes_saisonnieres_4panneaux.png",
                "carte_rapport_normale.png": "carte_anomalie_normale_2020.png",
                "carte_stations.png": "carte_reseau_148_stations.png",
                "pie_saisons.png": "repartition_pluie_saisons.png",
                "comparatif_pluviometrique_regional.png": "comparatif_pluviometrique_regional.png",
                "regions_naturelles_tunisie.png": "regions_naturelles_tunisie.png"
            }
            if filename in fig_aliases:
                alias_f = fig_aliases[filename]
                candidate_paths.append((os.path.join(WORKSPACE_ROOT, "figures", alias_f), f"/figures/{alias_f}"))

            found = False
            for disk_path, url in candidate_paths:
                if os.path.exists(disk_path) and os.path.getsize(disk_path) > 0:
                    images.append(url)
                    found = True
                    print(f"[AnnuaireRAG] Figure officielle d'annuaire trouvée : {disk_path} -> {url}")
                    break

            if not found:
                print(f"[AnnuaireRAG] Figure {filename} absente dans les caches. Génération via script annuaire...")
                try:
                    cmd = [
                        sys.executable,
                        os.path.join(WORKSPACE_ROOT, "generer_annuaire_database.py"),
                        "--year", str(year),
                        "--gouv", str(gouv_norm),
                        "--only-images"
                    ]
                    subprocess.run(cmd, cwd=WORKSPACE_ROOT, capture_output=True, timeout=30)
                    for disk_path, url in candidate_paths:
                        if os.path.exists(disk_path) and os.path.getsize(disk_path) > 0:
                            images.append(url)
                            found = True
                            print(f"[AnnuaireRAG] Figure générée et validée : {disk_path} -> {url}")
                            break
                except Exception as e:
                    print(f"[AnnuaireRAG] Erreur génération image annuaire : {e}")

        return images

    # ── Construction du prompt LLM ────────────────────────────────────────────

    def _build_prompt(self, question: str, rag_passages: List[Dict], sql_context: str, has_map_image: bool = False) -> tuple:
        """Construit un System Prompt unique et combiné ainsi que le User Prompt pour le LLM."""
        system_prompt = (
            "Tu es l'assistant IA officiel expert pour les ressources en eau et la pluviométrie de la Tunisie (DGRE).\n"
            "DIRECTIVES UNIVERSELLES ET IMPÉRATIVES DE FORMAT :\n"
            "1. CAS DEMANDE DE CARTE OU GRAPHIQUE VISUEL (IMAGE PRÉSENTE OU GÉNÉRÉE) :\n"
            "   - Si la demande concerne les régions naturelles ou le découpage territorial : démarre par 'Voici la carte des régions naturelles demandée :' et résume brièvement les 6 régions officielles DGRE (Nord-Ouest, Nord-Est, Centre-Ouest, Centre-Est, Sud-Ouest, Sud-Est).\n"
            "   - Si la demande concerne la pluviométrie / isohyètes : démarre par 'Voici la carte des isohyètes / le graphique pluviométrique demandé :' et donne une synthèse globale synthétique de 2 à 3 lignes (cumul moyen national/régional, gouvernorat le plus arrosé, gouvernorat le moins arrosé).\n"
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


