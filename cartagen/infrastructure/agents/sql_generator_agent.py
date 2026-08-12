# -*- coding: utf-8 -*-

import os
import re
import json
import requests
from typing import Dict, Any, Tuple, Optional

class SQLGeneratorAgent:
    """Agent chargé de traduire sémantiquement l'instruction en requête SQL via RAG Zvec et LLM."""

    def __init__(self, gouv_col: str, reg_col: str, provider_manager: Optional[Any] = None):
        self.gouv_col = gouv_col
        self.reg_col = reg_col
        self.provider_manager = provider_manager
        
        # Configuration des providers LLM
        self.llm_provider = os.getenv("LLM_PROVIDER", "openrouter").lower()
        self.groq_api_key = os.getenv("GROQ_API_KEY")
        self.groq_model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.openai_model = os.getenv("OPENAI_MODEL", "gpt-4o")
        self.openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
        self.openrouter_model = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free")
        self.ollama_url = os.getenv("OLLAMA_COLAB_URL", "http://localhost:11434")
        self.ollama_model = os.getenv("OLLAMA_MODEL", "llama3")
        self.last_system_prompt = ""
        self.last_user_prompt = ""
        self.last_response = "" 

    def generate_query(self, prompt: str, vector_context: Dict[str, Any] = None) -> Tuple[str, str]:
        """
        Génère la requête SQL via le modèle Fine-Tuné LoRA en prioritaire (LLM First),
        avec repli sur le parseur déterministe uniquement en cas de problème réseau LLM.
        """
        # 1. Priorité absolue au Modèle Fine-Tuné LoRA
        try:
            print(f"[SQL Agent] Interrogation prioritaire du modèle LLM fine-tuné ({self.llm_provider})...")
            return self._generate_query_llm(prompt, vector_context)
        except Exception as e:
            print(f"[SQL Agent] Modèle LLM indisponible ou déconnecté ({e}). Repli sur le parseur de secours.")
            
            # 2. Repli de secours (Fallback) sur le parseur déterministe
            result = self._generate_query_deterministic(prompt)
            if result is not None:
                sql_query, target_col = result
                self.last_system_prompt = "Parseur de secours (Règles Python)"
                self.last_user_prompt = prompt
                self.last_response = f"SQL: {sql_query}\nTarget Col: {target_col}"
                return sql_query, target_col
            
            sql_query, target_col = self._generate_query_fallback(prompt)
            return sql_query, target_col

    def _generate_query_llm(self, prompt: str, vector_context: Dict[str, Any]) -> Tuple[str, str]:
        # Formater le contexte RAG
        rag_text = ""
        if vector_context:
            if "stations" in vector_context and vector_context["stations"]:
                rag_text += "Stations suggérées :\n"
                for s in vector_context["stations"]:
                    rag_text += f"- ID: {s['id_station']}, Nom: {s['nom']} (similarité: {s['score']:.3f})\n"
            if "schemas" in vector_context and vector_context["schemas"]:
                rag_text += "Tables et schémas recommandés :\n"
                for sch in vector_context["schemas"]:
                    rag_text += f"- Table: {sch['table_name']} -> {sch['description']}\n"

        # ─────────────────────────────────────────────────────────────────────────
        # SYSTEM PROMPT — Corrigé : few-shots YEAR inclus, redondances supprimées
        # ─────────────────────────────────────────────────────────────────────────
        system_instruction = (
            "Tu es un traducteur de langage naturel vers PostgreSQL/PostGIS expert pour les ressources en eau de la Tunisie (DGRE).\n"
            "Renvoie UNIQUEMENT un objet JSON valide avec exactement deux clés : 'sql_query' et 'target_col'. Sans explication, sans markdown.\n\n"
            "=== TABLES DISPONIBLES (UNIQUEMENT CES TABLES) ===\n"
            "1. station_148 : id_station, nom, gouvernorat, lon, lat, altitude.\n"
            "2. pluies_148 : id_station, date_obs (TIMESTAMP), valeur_mm. Relevés journaliers.\n"
            "3. moy_interannuelle : id_station, moy (DOUBLE PRECISION). Contient la moyenne historique annuelle fixe de chaque station.\n\n"
            "=== RÈGLES DE REQUÊTES SQL POSTGRESQL ===\n"
            "- TOUJOURS inclure : SELECT s.id_station, s.nom AS station, s.gouvernorat, s.lon AS x, s.lat AS y\n"
            "- Pluies/isohyètes habituelles → TOUJOURS pluies_148 p JOIN station_148 s ON p.id_station = s.id_station.\n"
            "- Moyennes interannuelles / Normales climatiques fixes → TOUJOURS JOIN moy_interannuelle m ON s.id_station = m.id_station.\n"
            "- JAMAIS utiliser ann_pluies, ann_stations ou toute autre table obsolète.\n"
            "- Les coordonnées sont lon/lat (WGS84), aliasées s.lon AS x, s.lat AS y.\n"
            "- Inclure TOUJOURS : AND s.lon IS NOT NULL AND s.lat IS NOT NULL.\n"
            "- GROUP BY TOUJOURS : s.id_station, s.nom, s.gouvernorat, s.lon, s.lat.\n\n"
            "=== SAISONS (MOIS EXACTS — OBLIGATOIRE) ===\n"
            "Automne = EXTRACT(MONTH FROM p.date_obs) IN (9, 10, 11)\n"
            "Hiver   = EXTRACT(MONTH FROM p.date_obs) IN (12, 1, 2)\n"
            "Printemps = EXTRACT(MONTH FROM p.date_obs) IN (3, 4, 5)\n"
            "Été     = EXTRACT(MONTH FROM p.date_obs) IN (6, 7, 8)\n"
            "ATTENTION : 'saison de hiver 2015' signifie MONTH IN (12,1,2) avec YEAR = 2015, PAS une carte annuelle.\n\n"
            "=== FEW-SHOT EXAMPLES ===\n"
            "[Exemple 1] Mois seul (tous les septembre) :\n"
            "  SELECT s.id_station, s.nom AS station, s.gouvernorat, s.lon AS x, s.lat AS y, SUM(p.valeur_mm) AS pluie_sept FROM pluies_148 p JOIN station_148 s ON p.id_station = s.id_station WHERE EXTRACT(MONTH FROM p.date_obs) = 9 AND s.lon IS NOT NULL AND s.lat IS NOT NULL GROUP BY s.id_station, s.nom, s.gouvernorat, s.lon, s.lat;\n"
            "  target_col = 'pluie_sept'\n"
            "[Exemple 2] Mois + Année (septembre 2020) :\n"
            "  SELECT s.id_station, s.nom AS station, s.gouvernorat, s.lon AS x, s.lat AS y, SUM(p.valeur_mm) AS pluie_sept_2020 FROM pluies_148 p JOIN station_148 s ON p.id_station = s.id_station WHERE EXTRACT(MONTH FROM p.date_obs) = 9 AND EXTRACT(YEAR FROM p.date_obs) = 2020 AND s.lon IS NOT NULL AND s.lat IS NOT NULL GROUP BY s.id_station, s.nom, s.gouvernorat, s.lon, s.lat;\n"
            "  target_col = 'pluie_sept_2020'\n"
            "[Exemple 3] Année complète (2021) :\n"
            "  SELECT s.id_station, s.nom AS station, s.gouvernorat, s.lon AS x, s.lat AS y, SUM(p.valeur_mm) AS total_2021 FROM pluies_148 p JOIN station_148 s ON p.id_station = s.id_station WHERE EXTRACT(YEAR FROM p.date_obs) = 2021 AND s.lon IS NOT NULL AND s.lat IS NOT NULL GROUP BY s.id_station, s.nom, s.gouvernorat, s.lon, s.lat;\n"
            "  target_col = 'total_2021'\n"
            "[Exemple 4] HIVER 2015 :\n"
            "  SELECT s.id_station, s.nom AS station, s.gouvernorat, s.lon AS x, s.lat AS y, SUM(p.valeur_mm) AS hiver_2015 FROM pluies_148 p JOIN station_148 s ON p.id_station = s.id_station WHERE EXTRACT(MONTH FROM p.date_obs) IN (12, 1, 2) AND EXTRACT(YEAR FROM p.date_obs) = 2015 AND s.lon IS NOT NULL AND s.lat IS NOT NULL GROUP BY s.id_station, s.nom, s.gouvernorat, s.lon, s.lat;\n"
            "  target_col = 'hiver_2015'\n"
            "[Exemple 5] Filtre Spatial Gouvernorat (ex: Bizerte en Janvier 2022) :\n"
            "  SELECT s.id_station, s.nom AS station, s.gouvernorat, s.lon AS x, s.lat AS y, SUM(p.valeur_mm) AS pluie_bizerte_janv_2022 FROM pluies_148 p JOIN station_148 s ON p.id_station = s.id_station WHERE EXTRACT(MONTH FROM p.date_obs) = 1 AND EXTRACT(YEAR FROM p.date_obs) = 2022 AND s.gouvernorat ILIKE 'Bizerte' AND s.lon IS NOT NULL AND s.lat IS NOT NULL GROUP BY s.id_station, s.nom, s.gouvernorat, s.lon, s.lat;\n"
            "  target_col = 'pluie_bizerte_janv_2022'\n"
            "[Exemple 6] AUTOMNE 2020 :\n"
            "  SELECT s.id_station, s.nom AS station, s.gouvernorat, s.lon AS x, s.lat AS y, SUM(p.valeur_mm) AS auto_2020 FROM pluies_148 p JOIN station_148 s ON p.id_station = s.id_station WHERE EXTRACT(MONTH FROM p.date_obs) IN (9, 10, 11) AND EXTRACT(YEAR FROM p.date_obs) = 2020 AND s.lon IS NOT NULL AND s.lat IS NOT NULL GROUP BY s.id_station, s.nom, s.gouvernorat, s.lon, s.lat;\n"
            "  target_col = 'auto_2020'\n"
            "[Exemple 7] Stations uniquement :\n"
            "  SELECT s.id_station, s.nom AS station, s.gouvernorat, s.lon AS x, s.lat AS y, 1 AS nb_stations FROM station_148 s WHERE s.lon IS NOT NULL AND s.lat IS NOT NULL;\n"
            "  target_col = 'nb_stations'\n\n"
            "=== GOUVERNORATS ===\n"
            "Mahdia, Manouba, Mednine, Monastir, Nabeul, Sfax, Sidi bouzid, Siliana, Sousse, Tataouine,\n"
            "Tozeur, Tunis, Zaghouan, Ariana, Beja, Ben arous, Bizerte, Gabes, Gafsa, Jendouba, Kairouan, Kasserine, Kebili, Kef.\n"
            "Note: Pour les filtres de gouvernorats, utilise toujours s.gouvernorat ILIKE '...' (insensible à la casse/accents).\n\n"
            "Format de réponse attendu (JSON strict) :\n"
            "{\"sql_query\": \"SELECT s.id_station, s.nom AS station, s.gouvernorat, s.lon AS x, s.lat AS y, SUM(p.valeur_mm) AS hiver_2015 FROM pluies_148 p JOIN station_148 s ON p.id_station = s.id_station WHERE EXTRACT(MONTH FROM p.date_obs) IN (12, 1, 2) AND EXTRACT(YEAR FROM p.date_obs) = 2015 AND s.lon IS NOT NULL AND s.lat IS NOT NULL GROUP BY s.id_station, s.nom, s.gouvernorat, s.lon, s.lat;\", \"target_col\": \"hiver_2015\"}"
        )

        # [Correction 2] N'injecter le bloc RAG que s'il n'est pas vide
        rag_block = f"### Contexte RAG Zvec :\n{rag_text}\n" if rag_text.strip() else ""

        user_prompt = (
            rag_block
            + f"### Requête utilisateur :\n\"{prompt}\"\n\n"
            + "Génère la requête SQL complète (SELECT ... FROM ... WHERE ... GROUP BY ...) et la target_col."
        )

        self.last_system_prompt = system_instruction
        self.last_user_prompt = user_prompt
        # Appel du LLM
        response_text = self._call_llm(system_instruction, user_prompt)
        self.last_response = response_text
        
        # Nettoyage de la réponse
        clean_text = self._clean_json_response(response_text)
        
        data = json.loads(clean_text)
        sql_query = data["sql_query"].strip()
        target_col = data["target_col"].strip()
        
        return sql_query, target_col

    def _format_chatml(self, system_prompt: str, user_prompt: str) -> str:
        """[Correction 3] Encapsule dans le template ChatML pour les petits modèles locaux.
        Garantit que VisCoder2-7B / Mistral retournent du JSON strict sans bavardage."""
        return (
            f"<|im_start|>system\n{system_prompt}<|im_end|>\n"
            f"<|im_start|>user\n{user_prompt}<|im_end|>\n"
            f"<|im_start|>assistant\n"
        )

    def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        print("\n" + "="*80)
        print(f"[SQL Agent -> Prompt Transmis au LLM] Provider: {self.llm_provider.upper()}")
        print("-" * 80)
        if system_prompt:
            print(f"--- [SYSTEM PROMPT] ---\n{system_prompt}\n")
        print(f"--- [USER PROMPT] ---\n{user_prompt}")
        print("="*80 + "\n")

        # [Correction 3] Petits modèles locaux → ChatML pour un JSON strict
        small_model_providers = ["kaggle", "ollama", "colab", "local"]
        if self.llm_provider in small_model_providers:
            chatml_prompt = self._format_chatml(system_prompt, user_prompt)
            if self.provider_manager:
                try:
                    return self.provider_manager.call_llm_api(self.llm_provider, chatml_prompt)
                except Exception as e:
                    print(f"[SQL Agent] Avertissement échec ProviderManager ({e}). Repli sur l'API directe.")
            return self._call_ollama_api(chatml_prompt)

        # Cloud APIs (Groq, OpenRouter, OpenAI) → system/user séparés
        if self.provider_manager:
            try:
                return self.provider_manager.call_llm_api(self.llm_provider, user_prompt, system_prompt)
            except Exception as e:
                print(f"[SQL Agent] Avertissement échec ProviderManager ({e}). Repli sur l'implémentation directe.")

        prompt = f"{system_prompt}\n\n{user_prompt}"
        if self.llm_provider == "groq":
            return self._call_groq_api(prompt)
        elif self.llm_provider == "openai":
            return self._call_openai_api(prompt)
        elif self.llm_provider == "openrouter":
            return self._call_openrouter_api(prompt)
        else:
            return self._call_openrouter_api(prompt)

    def _call_groq_api(self, prompt: str) -> str:
        if not self.groq_api_key:
            raise ValueError("GROQ_API_KEY manquante.")
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {self.groq_api_key}", "Content-Type": "application/json"}
        payload = {"model": self.groq_model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.05}
        res = requests.post(url, headers=headers, json=payload, timeout=20)
        res.raise_for_status()
        return res.json()["choices"][0]["message"]["content"]

    def _call_openai_api(self, prompt: str) -> str:
        if not self.openai_api_key:
            raise ValueError("OPENAI_API_KEY manquante.")
        url = "https://api.openai.com/v1/chat/completions"
        headers = {"Authorization": f"Bearer {self.openai_api_key}", "Content-Type": "application/json"}
        payload = {"model": self.openai_model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.05}
        res = requests.post(url, headers=headers, json=payload, timeout=20)
        res.raise_for_status()
        return res.json()["choices"][0]["message"]["content"]

    def _call_openrouter_api(self, prompt: str) -> str:
        if not self.openrouter_api_key:
            raise ValueError("OPENROUTER_API_KEY manquante.")
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.openrouter_api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/dhieeddine/Net2Terraform-WebInterface",
            "X-Title": "CartaGen-SQL"
        }
        payload = {"model": self.openrouter_model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.05}
        res = requests.post(url, headers=headers, json=payload, timeout=20)
        res.raise_for_status()
        return res.json()["choices"][0]["message"]["content"]

    def _call_ollama_api(self, prompt: str) -> str:
        base_url = self.ollama_url.rstrip("/")
        headers = {
            "ngrok-skip-browser-warning": "true",
            "Bypass-Tunnel-Remainder": "true",
            "User-Agent": "CartaGenAgent/1.0",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        payload = {"model": self.ollama_model, "prompt": prompt, "stream": False, "options": {"temperature": 0.05}}
        
        urls = [f"{base_url}/generate", f"{base_url}/api/generate", base_url]
        last_err = None
        for url in urls:
            try:
                res = requests.post(url, headers=headers, json=payload, timeout=120)
                if res.status_code == 404:
                    continue
                res.raise_for_status()
                data = res.json()
                if "response" in data:
                    return data["response"]
                elif "generated_text" in data:
                    return data["generated_text"]
                elif "text" in data:
                    return data["text"]
                elif "choices" in data:
                    return data["choices"][0]["message"]["content"]
                else:
                    return str(data)
            except Exception as e:
                last_err = e
        if last_err:
            raise last_err

    def _clean_json_response(self, text: str) -> str:
        # Extraire le bloc JSON s'il est entouré de ```json ... ```
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
        return text.strip()

    def _generate_query_deterministic(self, prompt: str):
        """
        Parseur déterministe couvrant TOUTES les questions pluviométriques possibles.
        Retourne (sql_query, target_col) ou None si le cas est trop complexe pour les règles.

        Cas couverts :
          - Carte stations uniquement
          - Moyenne interannuelle (toutes années)
          - Rapport à la normale (% de la moyenne historique)
          - Carte annuelle (1 année)
          - Carte saisonnière (hiver/automne/printemps/été) avec ou sans année
          - Carte mensuelle (jan..déc) avec ou sans année
          - Tableau mensuel pivot (12 colonnes) par station/gouvernorat
          - Historique multi-années pour une station
          - Comparaison inter-années (2 ou 3 années)
          - Filtrage par gouvernorat
          - Filtrage par région naturelle (Nord-Ouest, Sud-Est, etc.)
          - Carte 4 saisons simultanées (multi-saison)
        """
        low = prompt.lower()
        import unicodedata

        def norm(s):
            return unicodedata.normalize('NFD', s).encode('ascii', 'ignore').decode().lower().strip()

        # ── Dictionnaires ──────────────────────────────────────────────────────
        MOIS_NOMS = {
            "janvier": (1,"janv"), "jan": (1,"janv"), "janv": (1,"janv"),
            "février": (2,"fev"),  "fevrier": (2,"fev"), "fev": (2,"fev"), "fév": (2,"fev"),
            "mars": (3,"mar"),     "mar": (3,"mar"),
            "avril": (4,"avr"),    "avr": (4,"avr"),
            "mai": (5,"mai"),
            "juin": (6,"juin"),    "jun": (6,"juin"),
            "juillet": (7,"juil"), "juil": (7,"juil"),
            "août": (8,"aout"),    "aout": (8,"aout"), "aou": (8,"aout"),
            "septembre": (9,"sept"),  "sept": (9,"sept"), "sep": (9,"sept"),
            "octobre": (10,"octo"),   "octo": (10,"octo"), "oct": (10,"octo"),
            "novembre": (11,"nove"),  "nove": (11,"nove"), "nov": (11,"nove"),
            "décembre": (12,"dece"),  "decembre": (12,"dece"), "dece": (12,"dece"), "dec": (12,"dece"),
        }
        SAISONS = {
            "hiver":     ([12, 1, 2],  "hiver"),
            "automne":   ([9, 10, 11], "auto"),
            "printemps": ([3, 4, 5],   "print"),
            "ete":       ([6, 7, 8],   "ete"),
        }
        MOIS_NOMS_FR = {
            "janv": "Janvier", "fev": "Février", "mar": "Mars", "avr": "Avril",
            "mai": "Mai", "juin": "Juin", "juil": "Juillet", "aout": "Août",
            "sept": "Septembre", "octo": "Octobre", "nove": "Novembre", "dece": "Décembre",
        }
        SAISON_NOMS_FR = {
            "hiver": "Hiver", "auto": "Automne", "print": "Printemps", "ete": "Été"
        }
        GOUVERNORATS_MAP = {
            "mahdia": "Mahdia", "manouba": "Manouba", "medenine": "Mednine",
            "mednine": "Mednine", "médenine": "Mednine",
            "monastir": "Monastir", "nabeul": "Nabeul", "sfax": "Sfax",
            "sidi bouzid": "Sidi bouzid", "siliana": "Siliana", "sousse": "Sousse",
            "tataouine": "Tataouine", "tozeur": "Tozeur", "tunis": "Tunis",
            "zaghouan": "Zaghouan", "ariana": "Ariana", "beja": "Beja",
            "béja": "Beja", "ben arous": "Ben arous", "bizerte": "Bizerte",
            "gabes": "Gabes", "gabès": "Gabes", "gafsa": "Gafsa",
            "jendouba": "Jendouba", "kairouan": "Kairouan",
            "kasserine": "Kasserine", "kebili": "Kebili", "kébili": "Kebili",
            "kef": "Kef", "le kef": "Kef",
        }
        REGIONS_MAP = {
            "nord-ouest": ["Jendouba", "Beja", "Kef", "Siliana"],
            "nord ouest":  ["Jendouba", "Beja", "Kef", "Siliana"],
            "nord-est":   ["Bizerte", "Ariana", "Tunis", "Manouba", "Zaghouan", "Ben arous", "Nabeul"],
            "nord est":   ["Bizerte", "Ariana", "Tunis", "Manouba", "Zaghouan", "Ben arous", "Nabeul"],
            "centre-ouest": ["Kasserine", "Sidi bouzid"],
            "centre ouest": ["Kasserine", "Sidi bouzid"],
            "centre-est":  ["Kairouan", "Monastir", "Mahdia", "Sousse", "Sfax"],
            "centre est":  ["Kairouan", "Monastir", "Mahdia", "Sousse", "Sfax"],
            "sud-ouest":  ["Gafsa", "Tozeur", "Kebili"],
            "sud ouest":  ["Gafsa", "Tozeur", "Kebili"],
            "sud-est":    ["Gabes", "Mednine", "Tataouine"],
            "sud est":    ["Gabes", "Mednine", "Tataouine"],
        }

        BASE_SELECT = "SELECT s.id_station, s.nom AS station, s.gouvernorat, s.lon AS x, s.lat AS y"
        BASE_FROM   = "FROM pluies_148 p JOIN station_148 s ON p.id_station = s.id_station"
        BASE_NOTNULL = "s.lon IS NOT NULL AND s.lat IS NOT NULL"
        BASE_GROUPBY = "GROUP BY s.id_station, s.nom, s.gouvernorat, s.lon, s.lat"

        low_norm = norm(low)

        # ── 1. CARTE DES STATIONS ─────────────────────────────────────────────
        if any(k in low_norm for k in ["carte des stations", "localisation des stations",
                                        "reseau de stations", "postes pluviometriques",
                                        "implantation", "densite du reseau",
                                        "reseau pluviometrique"]):
            sql = (f"SELECT s.id_station, s.nom AS station, s.gouvernorat, s.lon AS x, s.lat AS y, "
                   f"1 AS nb_stations FROM station_148 s WHERE {BASE_NOTNULL};")
            return sql, "nb_stations"

        # ── 2. RAPPORT À LA NORMALE ───────────────────────────────────────────
        is_rapport = any(k in low_norm for k in ["rapport a la normale", "rapport a la moyenne",
                                                  "pourcentage de la normale", "pourcentage de la moyenne",
                                                  "ecart a la normale", "anomalie pluviometrique",
                                                  "anomalie"])
        if is_rapport:
            year_match = re.search(r'\b(19\d{2}|20\d{2})\b', prompt)
            yr = year_match.group(1) if year_match else None
            if yr:
                sql = (
                    f"{BASE_SELECT}, "
                    f"CASE WHEN COALESCE(hist.moy_hist,0)>0 "
                    f"THEN ROUND((COALESCE(curr.total_{yr},0)/hist.moy_hist)*100,1) "
                    f"ELSE NULL END AS rapport_normale "
                    f"FROM station_148 s "
                    f"LEFT JOIN (SELECT id_station, SUM(valeur_mm) AS total_{yr} FROM pluies_148 "
                    f"WHERE EXTRACT(YEAR FROM date_obs)={yr} GROUP BY id_station) curr "
                    f"ON s.id_station=curr.id_station "
                    f"LEFT JOIN (SELECT id_station, AVG(annual_sum) AS moy_hist FROM "
                    f"(SELECT id_station, EXTRACT(YEAR FROM date_obs) AS yr, SUM(valeur_mm) AS annual_sum "
                    f"FROM pluies_148 GROUP BY id_station,yr) sub GROUP BY id_station) hist "
                    f"ON s.id_station=hist.id_station "
                    f"WHERE {BASE_NOTNULL};"
                )
            else:
                sql = (
                    f"{BASE_SELECT}, "
                    f"CASE WHEN COALESCE(hist.moy_hist,0)>0 "
                    f"THEN ROUND((COALESCE(curr.total_rec,0)/hist.moy_hist)*100,1) "
                    f"ELSE NULL END AS rapport_normale "
                    f"FROM station_148 s "
                    f"LEFT JOIN (SELECT id_station, SUM(valeur_mm) AS total_rec FROM pluies_148 "
                    f"WHERE EXTRACT(YEAR FROM date_obs)=(SELECT MAX(EXTRACT(YEAR FROM date_obs)) FROM pluies_148) "
                    f"GROUP BY id_station) curr ON s.id_station=curr.id_station "
                    f"LEFT JOIN (SELECT id_station, AVG(annual_sum) AS moy_hist FROM "
                    f"(SELECT id_station, EXTRACT(YEAR FROM date_obs) AS yr, SUM(valeur_mm) AS annual_sum "
                    f"FROM pluies_148 GROUP BY id_station,yr) sub GROUP BY id_station) hist "
                    f"ON s.id_station=hist.id_station WHERE {BASE_NOTNULL};"
                )
            return sql, "rapport_normale"

        # ── 3. MOYENNE INTERANNUELLE ──────────────────────────────────────────
        is_interannuel = any(k in low_norm for k in ["interannuelle", "inter-annuelle",
                                                      "moyenne pluriannuelle", "normale climatique",
                                                      "long terme", "historique",
                                                      "moyennes interannuelles"])
        # Attention : 'historique' peut aussi signifier courbe historique d'une station
        is_station_specifique = re.search(
            r'station\s+(?:de\s+)?([A-ZÀ-Ü][a-zà-ü]+(\s+[A-ZÀ-Ü][a-zà-ü]+)*)', prompt
        )
        if is_interannuel and not is_station_specifique:
            sql = (
                f"{BASE_SELECT}, m.moy AS total "
                f"FROM station_148 s "
                f"JOIN moy_interannuelle m ON s.id_station = m.id_station "
                f"WHERE {BASE_NOTNULL} {BASE_GROUPBY.replace('GROUP BY ', 'GROUP BY m.moy, ')};"
            )
            return sql, "total"

        # ── Extraction des entités communes ────────────────────────────────────
        # Années
        all_years = re.findall(r'\b(19\d{2}|20\d{2})\b', prompt)
        all_years = sorted(set(all_years))
        first_year = all_years[0] if all_years else None

        # Gouvernorat
        detected_gouv = None
        is_national_scope = any(kw in low_norm for kw in ["tunisie", "national", "toute la tunisie", "tout le pays"])
        for key_norm, val in GOUVERNORATS_MAP.items():
            if key_norm in low_norm:
                if val == "Tunis" and is_national_scope:
                    continue
                detected_gouv = val
                break

        # Région naturelle
        detected_region_govs = None
        for key_norm, govs in REGIONS_MAP.items():
            if key_norm in low_norm:
                detected_region_govs = govs
                break

        # Saison
        detected_saison = None
        detected_saison_col = None
        detected_saison_months = None
        for key_norm, (months, col) in SAISONS.items():
            if re.search(r'\b' + re.escape(key_norm) + r'\b', low_norm):
                detected_saison = key_norm
                detected_saison_col = col
                detected_saison_months = months
                break

        # Mois
        detected_mois_num = None
        detected_mois_col = None
        for key_norm, (num, col) in MOIS_NOMS.items():
            if re.search(r'\b' + re.escape(key_norm) + r'\b', low_norm) and not detected_saison:  # priorité saison > mois
                detected_mois_num = num
                detected_mois_col = col
                break

        # Filtrage gouvernorat/région
        def gouv_filter():
            if detected_gouv:
                return f"AND s.gouvernorat ILIKE '%{detected_gouv}%'"
            if detected_region_govs:
                arr = ", ".join(f"'%{g}%'" for g in detected_region_govs)
                return f"AND s.gouvernorat ILIKE ANY(ARRAY[{arr}])"
            return ""

        # ── 4. HISTORIQUE D'UNE STATION SPÉCIFIQUE ───────────────────────────
        station_match = re.search(
            r'(?:station\s+(?:de\s+)?|station\s*)([A-ZÀ-Ü][a-zA-Zà-üÀ-Ü\s]+?)(?:\s+entre|\s+pour|\s+de|\s+en|$)',
            prompt
        )
        entre_match = re.search(r'entre\s+(\d{4})\s+et\s+(\d{4})', low)
        if station_match and (entre_match or len(all_years) >= 2):
            station_nom = station_match.group(1).strip()
            if entre_match:
                y1, y2 = entre_match.group(1), entre_match.group(2)
                yr_filter = f"AND EXTRACT(YEAR FROM p.date_obs) BETWEEN {y1} AND {y2}"
            else:
                y1, y2 = min(all_years), max(all_years)
                yr_filter = f"AND EXTRACT(YEAR FROM p.date_obs) BETWEEN {y1} AND {y2}"
            sql = (
                f"{BASE_SELECT}, EXTRACT(YEAR FROM p.date_obs) AS annee, SUM(p.valeur_mm) AS total "
                f"{BASE_FROM} "
                f"WHERE s.nom ILIKE '%{station_nom}%' {yr_filter} AND {BASE_NOTNULL} "
                f"{BASE_GROUPBY}, annee ORDER BY annee;"
            )
            return sql, "total"

        # ── 5. COMPARAISON INTER-ANNÉES ───────────────────────────────────────
        is_compare_yr = any(k in low_norm for k in ["comparatif", "comparaison", "comparer",
                                                     "entre", "evolution", "évolution"])
        if is_compare_yr and len(all_years) >= 2:
            case_cols = ""
            for yr in all_years:
                case_cols += (f", SUM(CASE WHEN EXTRACT(YEAR FROM p.date_obs)={yr} "
                              f"THEN p.valeur_mm ELSE 0 END) AS total_{yr}")
            gf = gouv_filter()
            yr_range = f"AND EXTRACT(YEAR FROM p.date_obs) BETWEEN {min(all_years)} AND {max(all_years)}"
            sql = (
                f"{BASE_SELECT}{case_cols} "
                f"{BASE_FROM} "
                f"WHERE {BASE_NOTNULL} {gf} {yr_range} "
                f"{BASE_GROUPBY};"
            )
            return sql, f"total_{max(all_years)}"

        # ── 6. TABLEAU MENSUEL PIVOT (12 colonnes) ────────────────────────────
        is_tableau = any(k in low_norm for k in ["tableau", "table", "relevé mensuel", "releve mensuel",
                                                  "cumuls mensuels", "pluies mensuelles",
                                                  "precipitations mensuelles"])
        if is_tableau and not detected_mois_num:
            mois_cases = ""
            for col, num in [("sept",9),("octo",10),("nove",11),("dece",12),
                             ("janv",1),("fev",2),("mar",3),("avr",4),
                             ("mai",5),("juin",6),("juil",7),("aout",8)]:
                mois_cases += (f", SUM(CASE WHEN EXTRACT(MONTH FROM p.date_obs)={num} "
                               f"THEN p.valeur_mm ELSE 0 END) AS {col}")
            gf = gouv_filter()
            yr_filter = f"AND EXTRACT(YEAR FROM p.date_obs)={first_year}" if first_year else ""
            yr_filter_stations = re.search(r'station\s+(?:de\s+)?([A-ZÀ-Ü][a-zà-ü]+(?:\s+[A-ZÀ-Ü][a-zà-ü]+)*)', prompt)
            nom_filter = f"AND s.nom ILIKE '%{yr_filter_stations.group(1)}%'" if yr_filter_stations else ""
            sql = (
                f"{BASE_SELECT}{mois_cases}, SUM(p.valeur_mm) AS total "
                f"{BASE_FROM} "
                f"WHERE {BASE_NOTNULL} {gf} {nom_filter} {yr_filter} "
                f"{BASE_GROUPBY};"
            )
            return sql, "total"

        # ── 7. QUATRE SAISONS SIMULTANÉES ─────────────────────────────────────
        is_multi = any(k in low_norm for k in ["quatre saisons", "4 saisons",
                                                "cartes saisonnieres", "cartes saisonnières",
                                                "toutes les saisons", "saisons de",
                                                "subplot", "sous-graphique"])
        if is_multi:
            yr_filter = f"AND EXTRACT(YEAR FROM p.date_obs)={first_year}" if first_year else ""
            sql = (
                f"{BASE_SELECT}, "
                f"SUM(CASE WHEN EXTRACT(MONTH FROM p.date_obs) IN (9,10,11) THEN p.valeur_mm ELSE 0 END) AS auto, "
                f"SUM(CASE WHEN EXTRACT(MONTH FROM p.date_obs) IN (12,1,2)  THEN p.valeur_mm ELSE 0 END) AS hiver, "
                f"SUM(CASE WHEN EXTRACT(MONTH FROM p.date_obs) IN (3,4,5)   THEN p.valeur_mm ELSE 0 END) AS print, "
                f"SUM(CASE WHEN EXTRACT(MONTH FROM p.date_obs) IN (6,7,8)   THEN p.valeur_mm ELSE 0 END) AS ete "
                f"{BASE_FROM} WHERE {BASE_NOTNULL} {yr_filter} {BASE_GROUPBY};"
            )
            return sql, "auto"

        # ── 8. SAISON SPÉCIFIQUE ─────────────────────────────────────────────
        if detected_saison_months:
            months_str = ", ".join(str(m) for m in detected_saison_months)
            yr_filter = f"AND EXTRACT(YEAR FROM p.date_obs)={first_year}" if first_year else ""
            gf = gouv_filter()
            yr_suffix = f"_{first_year}" if first_year else ""
            target = f"{detected_saison_col}{yr_suffix}"
            sql = (
                f"{BASE_SELECT}, SUM(p.valeur_mm) AS {target} "
                f"{BASE_FROM} "
                f"WHERE EXTRACT(MONTH FROM p.date_obs) IN ({months_str}) "
                f"{yr_filter} AND {BASE_NOTNULL} {gf} "
                f"{BASE_GROUPBY};"
            )
            return sql, target

        # ── 9. MOIS SPÉCIFIQUE ────────────────────────────────────────────────
        if detected_mois_num:
            yr_filter = f"AND EXTRACT(YEAR FROM p.date_obs)={first_year}" if first_year else ""
            gf = gouv_filter()
            yr_suffix = f"_{first_year}" if first_year else ""
            target = f"pluie_{detected_mois_col}{yr_suffix}"
            sql = (
                f"{BASE_SELECT}, SUM(p.valeur_mm) AS {target} "
                f"{BASE_FROM} "
                f"WHERE EXTRACT(MONTH FROM p.date_obs)={detected_mois_num} "
                f"{yr_filter} AND {BASE_NOTNULL} {gf} "
                f"{BASE_GROUPBY};"
            )
            return sql, target

        # ── 10. CARTE ANNUELLE ────────────────────────────────────────────────
        if first_year:
            gf = gouv_filter()
            sql = (
                f"{BASE_SELECT}, SUM(p.valeur_mm) AS total "
                f"{BASE_FROM} "
                f"WHERE EXTRACT(YEAR FROM p.date_obs)={first_year} "
                f"AND {BASE_NOTNULL} {gf} {BASE_GROUPBY};"
            )
            return sql, "total"

        # ── 11. FILTRAGE GOUVERNORAT/RÉGION SANS PÉRIODE ──────────────────────
        if detected_gouv or detected_region_govs:
            gf = gouv_filter()
            sql = (
                f"{BASE_SELECT}, SUM(p.valeur_mm) AS total "
                f"{BASE_FROM} "
                f"WHERE {BASE_NOTNULL} {gf} "
                f"{BASE_GROUPBY};"
            )
            return sql, "total"

        # ── Cas non couverts → LLM ───────────────────────────────────────────
        return None

    def _generate_query_fallback(self, prompt: str) -> Tuple[str, str]:
        """Méthode de repli minimale (dernier recours)."""
        year_match = re.search(r'\b(19\d\d|20\d\d)\b', prompt)
        yr = year_match.group(1) if year_match else None
        yr_filter = f"AND EXTRACT(YEAR FROM p.date_obs) = {yr}" if yr else ""
        target_col = f"total_{yr}" if yr else "total"
        sql = (
            f"SELECT s.id_station, s.nom, s.gouvernorat, s.lon AS x, s.lat AS y, "
            f"SUM(p.valeur_mm) AS {target_col} "
            f"FROM pluies_148 p JOIN station_148 s ON p.id_station = s.id_station "
            f"WHERE s.lon IS NOT NULL AND s.lat IS NOT NULL {yr_filter} "
            f"GROUP BY s.id_station, s.nom, s.gouvernorat, s.lon, s.lat;"
        )
        return sql, target_col
