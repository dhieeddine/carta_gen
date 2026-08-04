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
        Génère dynamiquement la requête SQL et la colonne cible à l'aide d'un LLM
        en exploitant le contexte vectoriel Zvec.
        """
        try:
            return self._generate_query_llm(prompt, vector_context)
        except Exception as e:
            print(f"[SQL Agent] Erreur lors de la génération LLM ({e}). Repli sur les règles regex historiques.")
            sql_query, target_col = self._generate_query_fallback(prompt)
            self.last_system_prompt = "Regles Regex de Secours (Fallback)"
            self.last_user_prompt = prompt
            self.last_response = f"SQL: {sql_query}\nTarget Col: {target_col}"
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
            "1. station_148 : id_station, nom, gouvernorat, lon, lat, altitude. Contient les 148 stations pluviométriques officielles de la DGRE.\n"
            "2. pluies_148 : id_station, date_obs (TIMESTAMP), valeur_mm. Relevés journaliers des 148 stations. Jointure : p.id_station=s.id_station.\n\n"
            "=== RÈGLE ABSOLUE ===\n"
            "- Pluies/isohyètes → TOUJOURS pluies_148 p JOIN station_148 s ON p.id_station = s.id_station.\n"
            "- JAMAIS utiliser ann_pluies, ann_stations, yasra_data ou toute autre table.\n"
            "- Les coordonnées spatiales sont lon/lat (WGS84), PAS x/y UTM.\n"
            "- Inclure TOUJOURS : AND s.lon IS NOT NULL AND s.lat IS NOT NULL.\n\n"
            "=== FEW-SHOT EXAMPLES (à reproduire fidèlement) ===\n"
            "\n[Exemple 1] Mois sans année (tous les septembre) :\n"
            "  WHERE EXTRACT(MONTH FROM p.date_obs) = 9 AND s.lon IS NOT NULL AND s.lat IS NOT NULL\n"
            "  target_col = 'pluie_sept'\n"
            "\n[Exemple 2] Mois + Année — OBLIGATOIRE si une année est citée (ex: septembre 2020) :\n"
            "  WHERE EXTRACT(MONTH FROM p.date_obs) = 9 AND EXTRACT(YEAR FROM p.date_obs) = 2020\n"
            "        AND s.lon IS NOT NULL AND s.lat IS NOT NULL\n"
            "  target_col = 'pluie_sept_2020'\n"
            "\n[Exemple 3] Année complète (ex: 2021) :\n"
            "  WHERE EXTRACT(YEAR FROM p.date_obs) = 2021 AND s.lon IS NOT NULL AND s.lat IS NOT NULL\n"
            "  target_col = 'total_2021'\n"
            "\n[Exemple 4] Saison avec année (ex: Hiver 2020 = Déc+Jan+Fév) :\n"
            "  WHERE EXTRACT(MONTH FROM p.date_obs) IN (12, 1, 2) AND EXTRACT(YEAR FROM p.date_obs) = 2020\n"
            "        AND s.lon IS NOT NULL AND s.lat IS NOT NULL\n"
            "  target_col = 'hiver_2020'\n"
            "\n[Exemple 5] Stations uniquement :\n"
            "  SELECT s.id_station, s.nom AS station, s.lon, s.lat, 1 AS nb_stations FROM station_148 s WHERE s.lon IS NOT NULL AND s.lat IS NOT NULL;\n"
            "  target_col = 'nb_stations'\n\n"
            "=== GOUVERNORATS DISPONIBLES ===\n"
            "Mahdia, Manouba, Mednine, Monastir, Nabeul, Sfax, Sidi bouzid, Siliana, Sousse, Tataouine,\n"
            "Tozeur, Tunis, Zaghouan, Ariana, Beja, Ben arous, Bizerte, Gabes, Gafsa, Jendouba, Kairouan, Kasserine, Kebili, Kef\n\n"
            "Format de réponse attendu (JSON strict) :\n"
            "{\"sql_query\": \"SELECT ... FROM pluies_148 p JOIN station_148 s ON p.id_station = s.id_station WHERE ... GROUP BY ...;\", \"target_col\": \"pluie_sept_2020\"}"
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

    def _generate_query_fallback(self, prompt: str) -> Tuple[str, str]:
        """Méthode de repli en cas d'erreur du LLM ou d'API réseau — utilise pluies_148/station_148."""
        low = prompt.lower()

        mois_dict = {
            "sept": 9, "octo": 10, "nove": 11, "dece": 12,
            "janv": 1, "fev": 2, "mar": 3, "avr": 4, "mai": 5, "juin": 6, "juil": 7, "aout": 8
        }

        selected_month = None
        target_col = "total"

        for m_key, m_num in mois_dict.items():
            if m_key in low:
                selected_month = m_num
                target_col = f"pluie_{m_key}"
                break

        # Extraction de l'année (ex: 2018, 2021)
        year_match = re.search(r'\b(19\d\d|20\d\d)\b', prompt)
        selected_year = year_match.group(1) if year_match else None
        if selected_year:
            target_col = f"{target_col}_{selected_year}"

        where_conds = ["s.lon IS NOT NULL AND s.lat IS NOT NULL"]
        if selected_month:
            where_conds.append(f"EXTRACT(MONTH FROM p.date_obs) = {selected_month}")
        if selected_year:
            where_conds.append(f"EXTRACT(YEAR FROM p.date_obs) = {selected_year}")

        where_clause = " AND ".join(where_conds)

        query = f"""
SELECT p.id_station, s.nom AS station, s.lon, s.lat, SUM(p.valeur_mm) AS {target_col}
FROM pluies_148 p
JOIN station_148 s ON p.id_station = s.id_station
WHERE {where_clause}
GROUP BY p.id_station, s.nom, s.lon, s.lat;
""".strip()

        return query, target_col
