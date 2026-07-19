# -*- coding: utf-8 -*-

import os
import re
import json
import requests
from typing import Dict, Any, Tuple

class SQLGeneratorAgent:
    """Agent chargé de traduire sémantiquement l'instruction en requête SQL via RAG Zvec et LLM."""

    def __init__(self, gouv_col: str, reg_col: str):
        self.gouv_col = gouv_col
        self.reg_col = reg_col
        
        # Configuration des providers LLM
        self.llm_provider = os.getenv("LLM_PROVIDER", "local").lower()
        self.groq_api_key = os.getenv("GROQ_API_KEY")
        self.groq_model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.openai_model = os.getenv("OPENAI_MODEL", "gpt-4o")
        self.openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
        self.openrouter_model = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free")
        self.ollama_url = os.getenv("OLLAMA_COLAB_URL", "http://localhost:11434")
        self.ollama_model = os.getenv("OLLAMA_MODEL", "llama3")

    def generate_query(self, prompt: str, vector_context: Dict[str, Any] = None) -> Tuple[str, str]:
        """
        Génère dynamiquement la requête SQL et la colonne cible à l'aide d'un LLM
        en exploitant le contexte vectoriel Zvec.
        """
        try:
            return self._generate_query_llm(prompt, vector_context)
        except Exception as e:
            print(f"[SQL Agent] Erreur lors de la génération LLM ({e}). Repli sur les règles regex historiques.")
            return self._generate_query_fallback(prompt)

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

        system_instruction = (
            "Tu es un traducteur de langage naturel vers PostgreSQL/PostGIS expert pour les ressources en eau de la Tunisie (DGRE).\n"
            "Tu dois impérativement renvoyer UNIQUEMENT un objet JSON valide contenant exactement deux clés: 'sql_query' et 'target_col'.\n"
            "Aucune explication, aucune balise markdown en dehors du JSON.\n\n"
            "Schémas des tables disponibles :\n"
            "1. 'yasra_data' (données de pluie interpolées mensuelles, saisonnières et annuelles) :\n"
            "   - Colonnes : code, station, sept, octo, nove, dece, janv, fev, mar, avr, mai, juin, juil, aout, hiver, print (printemps/fleurs), ete, auto, total (total annuel), moy_ (moyenne historique).\n"
            "   - Pour yasra_data, la requête doit toujours charger toutes les colonnes :\n"
            "     SELECT code, station, ST_X(geom) AS x, ST_Y(geom) AS y, sept, octo, nove, dece, janv, fev, mar, avr, mai, juin, juil, aout, hiver, print, ete, auto, total, moy_ FROM yasra_data WHERE geom IS NOT NULL;\n"
            "2. 'pluies' (précipitations temporelles des stations) :\n"
            "   - Colonnes : id_station, date, valeur (pluie en mm).\n"
            "3. 'debits' (débit des oueds) :\n"
            "   - Colonnes : id_station, date, valeur (m3/s).\n"
            "4. 'cotes' (hauteurs d'eau) :\n"
            "   - Colonnes : id_station, date, valeur (m).\n\n"
            "Pour les tables temporelles (pluies, debits, cotes), effectue une jointure avec 'stations_base' pour avoir les coordonnées x et y, ex :\n"
            "SELECT d.id_station, s.nom as station, ST_X(s.geom) AS x, ST_Y(s.geom) AS y, d.valeur FROM debits d JOIN stations_base s ON d.id_station = s.id_station WHERE s.geom IS NOT NULL;\n\n"
            "Exemple de réponse JSON :\n"
            "{\n"
            "  \"sql_query\": \"SELECT code, station, ST_X(geom) AS x, ST_Y(geom) AS y, sept, octo, nove, dece, janv, fev, mar, avr, mai, juin, juil, aout, hiver, print, ete, auto, total, moy_ FROM yasra_data WHERE geom IS NOT NULL;\",\n"
            "  \"target_col\": \"print\"\n"
            "}"
        )

        user_prompt = (
            f"### Contexte RAG Zvec :\n{rag_text}\n"
            f"### Requête utilisateur :\n\"{prompt}\"\n\n"
            "Génère la requête SQL correcte et détermine la colonne cible (target_col) correspondante."
        )

        # Appel du LLM
        response_text = self._call_llm(system_instruction, user_prompt)
        
        # Nettoyage de la réponse
        clean_text = self._clean_json_response(response_text)
        
        data = json.loads(clean_text)
        sql_query = data["sql_query"].strip()
        target_col = data["target_col"].strip()
        
        return sql_query, target_col

    def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        prompt = f"{system_prompt}\n\n{user_prompt}"
        
        if self.llm_provider == "groq":
            return self._call_groq_api(prompt)
        elif self.llm_provider == "openai":
            return self._call_openai_api(prompt)
        elif self.llm_provider == "openrouter":
            return self._call_openrouter_api(prompt)
        elif self.llm_provider == "ollama":
            return self._call_ollama_api(prompt)
        else:
            raise ValueError(f"LLM Provider '{self.llm_provider}' non pris en charge par l'Agent SQL.")

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
        url = f"{self.ollama_url}/api/generate"
        payload = {"model": self.ollama_model, "prompt": prompt, "stream": False, "options": {"temperature": 0.05}}
        res = requests.post(url, json=payload, timeout=30)
        res.raise_for_status()
        return res.json()["response"]

    def _clean_json_response(self, text: str) -> str:
        # Extraire le bloc JSON s'il est entouré de ```json ... ```
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
        return text.strip()

    def _generate_query_fallback(self, prompt: str) -> Tuple[str, str]:
        """Méthode de repli historique en cas d'erreur du LLM ou d'API réseau."""
        low = prompt.lower()
        target_col = "total"
        for m in ["janv", "fev", "mar", "avr", "mai", "juin", "juil", "aout", "sept", "octo", "nove", "dece"]:
            if m in low:
                target_col = m
                break
        for s in ["hiver", "print", "ete", "auto"]:
            if s in low or (s == "print" and "printemps" in low):
                target_col = s
                break

        query = """
SELECT 
    code,
    station,
    ST_X(geom) AS x,
    ST_Y(geom) AS y,
    sept, octo, nove, dece, janv, fev, mar, avr, mai, juin, juil, aout,
    hiver, print, ete, auto, total, moy_
FROM yasra_data
WHERE geom IS NOT NULL;
"""
        return query.strip(), target_col
