# -*- coding: utf-8 -*-

import os
import time
import json
import requests
from typing import Dict, Any, Optional, Tuple, List
from cartagen.infrastructure.database.postgres_connection import PostgresConnectionManager
from cartagen.infrastructure.database.vector_manager import VectorManager

class SIGGeneratorAgent:
    """Agent chargé de générer et corriger du code Python géospatial robuste (Matplotlib/GeoPandas/PostGIS)."""

    def __init__(
        self,
        hf_token: str,
        db_manager: PostgresConnectionManager,
        vector_manager: Optional[VectorManager] = None,
        score_cutoff: float = 0.70,
        provider_manager: Optional[Any] = None
    ):
        self.hf_token = hf_token
        self.db_manager = db_manager
        self.vector_manager = vector_manager
        self.score_cutoff = score_cutoff
        self.provider_manager = provider_manager
        
        # Configuration des providers LLM
        self.llm_provider = os.getenv("LLM_PROVIDER", "openrouter").lower()
        self.groq_api_key = os.getenv("GROQ_API_KEY")
        self.groq_model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.openai_model = os.getenv("OPENAI_MODEL", "gpt-4o")
        self.openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
        self.openrouter_model = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free")
        self.last_system_prompt = ""
        self.last_user_prompt = ""
        self.last_response = ""
        self.last_correction_system_prompt = ""
        self.last_correction_user_prompt = ""
        self.last_correction_response = "" 
        self.ollama_url = os.getenv("OLLAMA_COLAB_URL", "http://localhost:11434")
        self.ollama_model = os.getenv("OLLAMA_MODEL", "llama3")
        
        self.model_name = "TIGER-Lab/VisCoder2-7B"
        self.tokenizer = None
        self.model = None
        
        # Identification des caractéristiques des tables
        self.gouv_col = "lib_fr"  # Colonne nom français dans la table gouvernorats
        self.reg_col  = "lib_fr"  # Colonne nom français dans la table rgion_hydrographique

    def _retrieve_zvec_context(self, prompt: str) -> Dict[str, Any]:
        """Effectue la recherche sémantique active dans Zvec avec filtrage par score (Score Cutoff).

        Args:
            prompt (str): Requête ou description en langage naturel.

        Returns:
            Dict[str, Any]: Contexte RAG contenant les clés 'stations' et 'schemas' filtrées.
        """
        if not self.vector_manager:
            return {}
        try:
            raw_stations = self.vector_manager.query_stations_by_text(prompt, topk=5)
            raw_schemas = self.vector_manager.query_schemas_by_text(prompt, topk=3)

            # Filtrage dynamique par seuil (Score Cutoff / Distance Cosine)
            filtered_stations = [
                st for st in raw_stations
                if st.get("score", 0.0) <= self.score_cutoff or st.get("score", 0.0) >= (1.0 - self.score_cutoff)
            ]
            filtered_schemas = [
                sch for sch in raw_schemas
                if sch.get("score", 0.0) <= self.score_cutoff or sch.get("score", 0.0) >= (1.0 - self.score_cutoff)
            ]

            return {
                "stations": filtered_stations,
                "schemas": filtered_schemas
            }
        except Exception as e:
            print(f"[SIG Agent] Avertissement recherche sémantique Zvec : {e}")
            return {}

    def _format_rag_context(self, vector_context: Optional[Dict[str, Any]]) -> str:
        """Formate de manière synthétique et compacte le contexte RAG Zvec (format DDL / Schéma concis).

        Args:
            vector_context (Optional[Dict[str, Any]]): Contexte RAG contenant les stations et schémas.

        Returns:
            str: Chaîne de caractères formatée pour le prompt.
        """
        if not vector_context:
            return ""

        stations = vector_context.get("stations", [])
        schemas = vector_context.get("schemas", [])

        if not stations and not schemas:
            return ""

        lines = ["\n### Extraits de Code de Référence & Schémas (Zvec RAG) :"]

        if schemas:
            for sch in schemas:
                tname = sch.get("table_name", "")
                desc = sch.get("description", "")
                if tname:
                    lines.append(f"- Référence [{tname}] : {desc}")

        if stations:
            station_items = [
                f"{st.get('nom', '')} (ID: {st.get('id_station', '')})"
                for st in stations if st.get("nom")
            ]
            if station_items:
                lines.append(f"- Stations pertinentes : [{', '.join(station_items)}]")

        return "\n".join(lines)

    def initialize_model(self) -> None:
        """Initialise le modèle LLM choisi (local ou cloud)."""
        if self.llm_provider not in ["local", "viscoder"]:
            print(f"[SIG Agent] Utilisation du provider externe : '{self.llm_provider}'. Aucun modele local ne sera charge.")
            return

        if self.model is not None:
            return

        # Lazy imports pour accélérer le démarrage de l'application
        import torch
        from huggingface_hub import login, scan_cache_dir, snapshot_download
        from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig

        login(token=self.hf_token, add_to_git_credential=False)
        
        # Vérification cache local
        is_cached = False
        try:
            cached_repos = {r.repo_id for r in scan_cache_dir().repos}
            if self.model_name in cached_repos:
                is_cached = True
        except Exception:
            pass

        model_path = self.model_name
        use_local_only = is_cached

        if not is_cached:
            print("[SIG Agent] Modele absent du cache local. Telechargement...")
            os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "1"
            model_path = snapshot_download(
                repo_id=self.model_name,
                token=self.hf_token,
                max_workers=8,
                ignore_patterns=["*.msgpack", "*.h5", "*.ot"]
            )
            use_local_only = True

        quant_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.float16,
            bnb_4bit_use_double_quant=True,
        )

        self.tokenizer = AutoTokenizer.from_pretrained(
            model_path,
            token=self.hf_token,
            trust_remote_code=True,
            local_files_only=use_local_only
        )
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token

        self.model = AutoModelForCausalLM.from_pretrained(
            model_path,
            quantization_config=quant_config,
            device_map="auto",
            trust_remote_code=True,
            token=self.hf_token,
            local_files_only=use_local_only
        )
        print("[SIG Agent] Modele VisCoder2-7B charge en VRAM avec succes.")

    def _build_title_from_sql(self, sql_query: str, prompt: str) -> str:
        """
        Construit le titre officiel de la carte de manière déterministe
        à partir de la requête SQL et du prompt. Couvre tous les cas possibles.
        """
        import re, unicodedata
        sql_low = sql_query.lower()

        # Extraire année(s)
        years = re.findall(r'\b(19\d{2}|20\d{2})\b', sql_query)
        years = sorted(set(years))
        year_str = years[0] if len(years) == 1 else (f"{min(years)}–{max(years)}" if years else "")

        # Gouvernorat dans le SQL
        gouv_match = re.search(r"gouvernorat ilike '%(\w[\w\s]*)%'", sql_low)
        gouv_str = gouv_match.group(1).title() if gouv_match else ""

        # Carte des stations
        if 'nb_stations' in sql_low or 'station_148 s where' in sql_low.replace('\n',' ') and 'pluies_148' not in sql_low:
            return "Réseau des Stations Pluviométriques DGRE (148 stations)"

        # Rapport à la normale
        if 'rapport_normale' in sql_low or 'moy_hist' in sql_low:
            suffix = f" {year_str}" if year_str else ""
            return f"Rapport à la Normale Pluviométrique{suffix} — Tunisie"

        # Anomalie
        if 'anomalie' in sql_low:
            suffix = f" {year_str}" if year_str else ""
            return f"Anomalie Pluviométrique{suffix} — Tunisie"

        # Moyenne interannuelle
        if 'avg(annual_sum)' in sql_low or 'moy_hist' in sql_low:
            return "IsohYètes Moyennes Interannuelles — Tunisie"

        # Historique station (ORDER BY annee)
        if 'order by annee' in sql_low:
            st_match = re.search(r"nom ilike '%(\w[\w\s]*)%'", sql_low)
            st_name = st_match.group(1).title() if st_match else "Station"
            return f"Historique Pluviométrique — Station {st_name} ({year_str})"

        # Comparaison inter-années (CASE WHEN YEAR = N)
        multi_yr = re.findall(r'extract\(year from p\.date_obs\)=(\d{4})', sql_low)
        if len(multi_yr) >= 2:
            yrs = sorted(set(multi_yr))
            return f"Comparatif Pluviométrique {'–'.join(yrs)}{' — ' + gouv_str if gouv_str else ' — Tunisie'}"

        # 4 saisons simultanées
        if 'as auto' in sql_low and 'as hiver' in sql_low:
            suffix = f" {year_str}" if year_str else ""
            return f"Cartes Saisonnières{suffix} — Tunisie"

        # Tableau mensuel pivot (12 colonnes)
        if 'as sept' in sql_low and 'as janv' in sql_low:
            suffix = f" {year_str}" if year_str else ""
            loc = f" — {gouv_str}" if gouv_str else " — Tunisie"
            return f"Tableau Mensuel des Pluies{suffix}{loc}"

        # Saisons (MONTH IN (...))
        SAISON_MOIS = {
            "hiver":     ([12, 1, 2],  "Hiver"),
            "auto":      ([9, 10, 11], "Automne"),
            "print":     ([3, 4, 5],   "Printemps"),
            "ete":       ([6, 7, 8],   "Été"),
        }
        for col, (months, nom_fr) in SAISON_MOIS.items():
            months_str = re.escape(", ".join(str(m) for m in months))
            # Check if SQL contains MONTH IN (9,10,11) or (9, 10, 11)
            months_nosp = ",".join(str(m) for m in months)
            if f"in ({months_nosp}" in sql_low.replace(" ", "") or f"in({months_nosp}" in sql_low.replace(" ", ""):
                suffix = f" {year_str}" if year_str else ""
                loc = f" — {gouv_str}" if gouv_str else " — Tunisie"
                return f"Carte des Pluies — {nom_fr}{suffix}{loc}"

        # Mois spécifique (MONTH = N)
        MOIS_MAP = {
            1: "Janvier", 2: "Février", 3: "Mars", 4: "Avril",
            5: "Mai", 6: "Juin", 7: "Juillet", 8: "Août",
            9: "Septembre", 10: "Octobre", 11: "Novembre", 12: "Décembre",
        }
        mois_match = re.search(r'extract\(month from p\.date_obs\)\s*=\s*(\d{1,2})', sql_low)
        if mois_match:
            m_num = int(mois_match.group(1))
            m_nom = MOIS_MAP.get(m_num, f"Mois {m_num}")
            suffix = f" {year_str}" if year_str else ""
            loc = f" — {gouv_str}" if gouv_str else " — Tunisie"
            return f"Carte des Isohyètes — {m_nom}{suffix}{loc}"

        # Carte annuelle
        if year_str:
            loc = f" — {gouv_str}" if gouv_str else " — Tunisie"
            return f"Carte des Isohyètes Annuelles {year_str}{loc}"

        # Défaut
        return "Carte Pluviométrique — Tunisie"

    def detect_prompt_type(self, prompt: str) -> str:
        """Utilise le modèle LLM du provider actif pour classifier dynamiquement et intelligemment l'intention du prompt."""
        if self.provider_manager:
            try:
                system_prompt = (
                    "Tu es un classificateur d'intention expert pour le système CartaGen.\n"
                    "Analyse la demande de l'utilisateur et réponds EXCLUSIVEMENT par un seul mot parmi cette liste :\n"
                    "- analysis (si l'utilisateur demande un histogramme, une courbe, un graphique, un camembert, des barres ou un tableau statistique HTML)\n"
                    "- multi_season (si l'utilisateur demande 4 saisons ou un subplot 2x2)\n"
                    "- compare_gouv (si l'utilisateur demande une comparaison entre gouvernorats)\n"
                    "- single_gouv (si la carte concerne un gouvernorat unique spécifique)\n"
                    "- region_hydro (si la carte concerne une région hydrographique ou bassin versant)\n"
                    "- difference (si l'utilisateur demande une différence, un écart ou une évolution entre deux périodes)\n"
                    "- anomalie (si l'utilisateur demande un pourcentage par rapport à la normale/moyenne)\n"
                    "- stations_density (si l'utilisateur demande l'emplacement/implantation des stations météo)\n"
                    "- mono (pour toute carte d'isohyètes standard pays ou région)\n\n"
                    "Ne réponds rien d'autre que ce mot unique."
                )
                res = self.provider_manager.call_llm_api(
                    provider_id=self.llm_provider,
                    prompt=f"Classification d'intention pour : '{prompt}'",
                    system_prompt=system_prompt
                ).strip().lower()
                
                # Extraire le premier mot clé valide
                valid_types = ["analysis", "multi_season", "compare_gouv", "single_gouv", "region_hydro", "difference", "anomalie", "stations_density", "mono"]
                for vt in valid_types:
                    if vt in res:
                        print(f"[SIG Agent -> LLM Classification] Intention détectée intelligemment par LLM ('{self.llm_provider}') : '{vt}'")
                        return vt
            except Exception as e:
                print(f"[SIG Agent] Avertissement classification LLM ({e}). Repli sur l'analyse sémantique.")

        # Fallback sémantique
        low = prompt.lower()
        if any(k in low for k in ["histogramme", "courbe", "graphe", "plot", "tableau", "table", "analyse", "statistique", "camembert", "barres", "données"]):
            return "analysis"
        if any(k in low for k in ["4 sous-graphique", "subplot 2×2", "quatre saison", "4 saison", "subplot 2x2"]):
            return "multi_season"
        if any(k in low for k in ["comparer", "comparaison", "compare", "côte à côte", "cote a cote", "versus", " vs "]):
            return "compare_gouv"
        if any(k in low for k in ["gouvernorat de ", "gouvernorat d'", "gouvernorat uniquement"]):
            return "single_gouv"
        if any(k in low for k in ["région hydrographique", "region hydrographique", "bassin versant", "bassins versants", "région de sud", "region de sud", "région du sud", "region du sud", "medjerdah"]):
            return "region_hydro"
        if any(k in low for k in ["différence", "difference", "écart", "ecart", " - ", " moins ", "evolution", "évolution"]):
            return "difference"
        if any(k in low for k in ["anomalie", "pourcentage de la normale", "pourcentage de la moyenne", "de la normale", "de la moyenne"]):
            return "anomalie"
        if any(k in low for k in ["emplacement de toutes les stations", "implantation des stations", "densité du réseau", "carte des stations"]):
            return "stations_density"
        return "mono"

    def _get_skeleton(self, ptype: str) -> str:
        """Retourne le squelette de code Python associé au type de prompt."""
        if ptype == "analysis":
            return self._skeleton_analysis()
        if ptype == "multi_season":
            return self._skeleton_multi_season()
        elif ptype == "single_gouv":
            return self._skeleton_single_gouv()
        elif ptype == "compare_gouv":
            return self._skeleton_compare_gouv()
        elif ptype == "region_hydro":
            return self._skeleton_region_hydro()
        elif ptype == "difference":
            return self._skeleton_difference()
        elif ptype == "anomalie":
            return self._skeleton_anomalie()
        elif ptype == "stations_density":
            return self._skeleton_stations_density()
        return self._skeleton_mono()

    def generate_code(
        self, 
        prompt: str, 
        sql_query: str, 
        vector_context: Optional[Dict[str, Any]] = None
    ) -> str:
        """Génère le code Python complet en associant le prompt, la requête SQL et le squelette.

        Args:
            prompt (str): Requête en langage naturel de l'utilisateur.
            sql_query (str): Requête SQL d'extraction générée par l'Agent SQL.
            vector_context (Optional[Dict[str, Any]]): Contexte RAG pré-calculé (ou None pour retrieval actif).

        Returns:
            str: Code Python complet et autonome généré.
        """
        self.initialize_model()

        ptype = self.detect_prompt_type(prompt)
        skeleton = self._get_skeleton(ptype)

        # Titre déterministe calculé AVANT l'appel au LLM
        titre_carte = self._build_title_from_sql(sql_query, prompt)

        # Retrieval dynamique Zvec si non fourni
        if not vector_context:
            vector_context = self._retrieve_zvec_context(prompt)

        # Formatage synthétique et compact du contexte RAG
        rag_context = self._format_rag_context(vector_context)

        if ptype == "analysis":
            context = f"""Tu disposes de la requête SQL d'extraction suivante pour charger les données pluviométriques depuis PostgreSQL :
```sql
{sql_query}
```

{rag_context}
"""
            constraints = (
                "### Contraintes de programmation (IMPÉRATIVES) :\n"
                "- Écris UNIQUEMENT du code Python complet et exécutable, sans explications et sans balises markdown markdown en dehors du bloc de code.\n"
                "- Le code doit être autonome (tous les imports inclus).\n"
                "- Utilise la fonction d'extraction SQL fournie pour charger les données dans un DataFrame Pandas.\n"
                "- Si le prompt demande un graphique (courbe, histogramme, camembert, barres, etc.), génère-le avec Matplotlib ou Seaborn.\n"
                "- Style le graphique avec un design moderne et professionnel (couleurs harmonieuses, grille, légendes claires).\n"
                "- Sauvegarde TOUJOURS le graphique généré en utilisant : plt.savefig('output_isohyete.png', dpi=300, bbox_inches='tight').\n"
                "- Si le prompt demande un tableau de données, ou si l'analyse produit un jeu de données tabulaire, formate-le et sauvegarde-le obligatoirement sous forme de tableau HTML en utilisant : df.to_html('output_table.html', index=False, classes='analysis-table').\n"
                "- Utilise plt.close() à la fin.\n\n"
            )
        else:
            context = f"""Tu disposes de la requête SQL d'extraction suivante pour charger les données pluviométriques depuis PostgreSQL :
```sql
{sql_query}
```
Les couches géographiques (limite_pays_polygon, gouvernorats, rgion_hydrographique) doivent être chargées directement depuis la base de données PostGIS avec gpd.read_postgis(). Ne lis aucun fichier shapefile (.shp) sur le disque.

TITRE OFFICIEL DE LA CARTE (UTILISE EXACTEMENT CE TITRE, ne le modifie pas) : "{titre_carte}"

{rag_context}
"""
            constraints = (
                "### Contraintes de programmation (IMPÉRATIVES) :\n"
                "- Écris UNIQUEMENT du code Python complet et exécutable, sans explications.\n"
                "- Charge les données spatiales depuis PostGIS avec gpd.read_postgis() et reprojette en EPSG:32632.\n"
                "- Remplace [requete_sql], [colonne_cible] et [titre_carte] dans le squelette ci-dessous.\n"
                "- Sauvegarde la figure avec plt.savefig('output_isohyete.png', dpi=300, bbox_inches='tight') et ferme avec plt.close().\n\n"
            )


        # Aiguillage selon le provider choisi (Variables de connexion + Code Snippets RAG Zvec)
        if self.llm_provider != "local":
            api_prompt = (
                f"### Base de données & Connexion :\n"
                f"engine = sqlalchemy.create_engine(os.environ['DATABASE_URL'])\n"
                f"query = \"\"\"{sql_query}\"\"\"\n\n"
                f"### Titre Officiel :\n{titre_carte}\n\n"
                f"### Type de Rendu Détecté par l'IA (Classification LLM) :\n{ptype.upper()}\n\n"
                f"### Instruction Utilisateur :\n{prompt}\n"
                f"{rag_context}\n\n"
                "### Directives de génération (IMPÉRATIVES) :\n"
                "1. Écris un script Python autonome complet.\n"
                "2. Charge les données avec `df = pd.read_sql(query, engine)`. N'utilise JAMAIS de variables fictives comme 'your_query_here' ou 'your_connection_here'.\n"
                "3. Si une carte est demandée, importe cKDTree avec `from scipy.spatial import cKDTree` (JAMAIS depuis shapely.ops) et passe la matrice NumPy 2D `df[['x', 'y']].values`.\n"
                "4. Charge les limites depuis PostGIS avec `gpd.read_postgis('SELECT geom FROM limite_pays_polygon', engine, geom_col='geom')` et `gpd.read_postgis('SELECT lib_fr, geom FROM gouvernorats', engine, geom_col='geom')`. ATTENTION: La table exacte s'appelle 'gouvernorats' (JAMAIS 'gouvernorats_polygon').\n"
                "5. Pour la simplification géométrique, applique `.geometry.simplify(100)` sur la colonne géométrique uniquement. N'invoque JAMAIS `gpd.simplify()` sur un GeoDataFrame complet.\n"
                "6. Si un graphique ou une carte est demandé, enregistre le rendu sous 'output_isohyete.png' avec `plt.savefig('output_isohyete.png', dpi=300, bbox_inches='tight')` et termine avec `plt.close()`.\n"
                "7. Si un tableau de données est demandé (analyse/statistiques), sauvegarde-le aussi sous 'output_table.html' avec `df.to_html('output_table.html', index=False)`.\n"
                "8. Renvoie UNIQUEMENT le bloc de code Python complet sans aucun texte explicatif avant ou après."
            )
            print("\n" + "="*80)
            print(f"[SIG Agent -> Prompt Transmis au LLM (Génération)] Provider: {self.llm_provider.upper()}")
            print("-" * 80)
            print(api_prompt)
            print("="*80 + "\n")

            self.last_system_prompt = "Directives de génération SIG (GeoPandas + PostGIS + Matplotlib)"
            self.last_user_prompt = api_prompt
            if self.provider_manager:
                try:
                    raw = self.provider_manager.call_llm_api(self.llm_provider, api_prompt)
                    self.last_response = raw
                    return self._clean_code(raw)
                except Exception as e:
                    print(f"[SIG Agent] Avertissement échec ProviderManager ({e}). Repli sur l'API directe.")

            if self.llm_provider == "groq":
                raw = self._call_groq_api(api_prompt)
                self.last_response = raw
                return raw
            elif self.llm_provider == "openai":
                raw = self._call_openai_api(api_prompt)
                self.last_response = raw
                return raw
            elif self.llm_provider in ["ollama", "colab", "kaggle"]:
                return self._call_ollama_api(api_prompt)
            else:
                raw = self._call_openrouter_api(api_prompt)
                self.last_response = raw
                return self._clean_code(raw)

        # Mode Local par défaut (VisCoder avec balises ChatML)
        model_prompt = (
            "<|im_start|>system\n"
            "Tu es un expert en géomatique et Python. Tu génères du code Python complet "
            "pour créer des cartes isohyètes de la Tunisie.<|im_end|>\n"
            "<|im_start|>user\n"
            f"{context}\n\n"
            f"### Instruction :\n{prompt}\n\n"
            + constraints
            + "### SQUELETTE DE CODE À SUIVRE OBLIGATOIREMENT :\n"
            "```python\n"
            + skeleton
            + "\n```\n\n"
            "### Code Python :\n<|im_end|>\n"
            "<|im_start|>assistant\n"
        )

        inputs = self.tokenizer(model_prompt, return_tensors="pt", truncation=True, max_length=3072)
        inputs = {k: v.to(self.model.device) for k, v in inputs.items()}
        input_len = inputs["input_ids"].shape[1]

        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=3072,
                temperature=0.1,
                top_p=0.95,
                repetition_penalty=1.1,
                do_sample=True,
                pad_token_id=self.tokenizer.eos_token_id,
            )
        
        generated_ids = outputs[0][input_len:]
        raw_output = self.tokenizer.decode(generated_ids, skip_special_tokens=True)
        self.last_system_prompt = constraints + "\n\n### SQUELETTE DE CODE :\n" + skeleton
        self.last_user_prompt = context + "\n\n### Instruction :\n" + prompt
        self.last_response = raw_output
        return self._clean_code(raw_output)

    def generate_correction(
        self, 
        code: str, 
        error: str, 
        vector_context: Optional[Dict[str, Any]] = None,
        prompt: Optional[str] = None
    ) -> str:
        """Génère un code corrigé à partir d'un code ayant échoué, de son exception et du contexte RAG Zvec.

        Args:
            code (str): Code Python initial ayant échoué.
            error (str): Message d'erreur ou traceback issu de la Sandbox.
            vector_context (Optional[Dict[str, Any]]): Contexte RAG pré-calculé (ou None).
            prompt (Optional[str]): Prompt utilisateur d'origine pour retrieval RAG dynamique si besoin.

        Returns:
            str: Code Python corrigé, complet et autonome.
        """
        # Retrieval dynamique si non fourni mais prompt présent
        if not vector_context and prompt:
            vector_context = self._retrieve_zvec_context(prompt)

        # Injection synthétique du contexte RAG Zvec dans le prompt de correction
        rag_context = self._format_rag_context(vector_context)

        hints = []
        error_lower = error.lower()
        if "take_1d" in error_lower or "take_nd" in error_lower:
            hints.append("\n💡 INDICE : utilise `.values[indices]` au lieu de `.iloc[indices]`.")
        if "lower_level" in error_lower or "cannot be nan" in error_lower:
            hints.append("\n💡 INDICE : reprojette les shapefiles vers EPSG:32632 lors du chargement.")
        if "gouvernerats" in error_lower:
            hints.append("\n💡 INDICE : le fichier s'appelle 'Gouvernorats.shp'.")
        if "buffer has wrong number of dimensions" in error_lower:
            hints.append("\n💡 INDICE : contains() exige des coordonnées 1D.")
        if "finite" in error_lower or "nan or inf" in error_lower or "ckdtree" in error_lower:
            hints.append(
                "\n💡 INDICE CRITIQUE : Le DataFrame contient des valeurs NaN dans les colonnes de coordonnées (x, y) ou de valeur.\n"
                "  OBLIGATOIRE : Ajoute IMMÉDIATEMENT après le chargement du DataFrame (pd.read_sql) :\n"
                "    df = df.dropna(subset=['x', 'y', '[colonne_valeur]'])\n"
                "  Ces lignes doivent être placées AVANT tout appel à cKDTree, np.meshgrid, ou idw."
            )
        
        hint_block = "\n".join(hints) if hints else ""

        task = f"""Erreur détectée :
---
{error[:300]}
---
Code à corriger :
```python
{code}
```

Corrige le code et retourne UNIQUEMENT le bloc Python complet et réparé, enregistrant sous 'output_isohyete.png' avec plt.savefig('output_isohyete.png', dpi=300, bbox_inches='tight') et plt.close()."""

        # Aiguillage pour correction via API Cloud ou Tunnel ProviderManager
        if self.llm_provider != "local":
            print("\n" + "="*80)
            print(f"[SIG Agent -> Prompt Transmis au LLM (Auto-Correction)] Provider: {self.llm_provider.upper()}")
            print("-" * 80)
            print(task)
            print("="*80 + "\n")

            self.last_system_prompt = "Assistant d'Auto-Correction SIG Python (Réparation du Code)"
            self.last_user_prompt = task
            if self.provider_manager:
                try:
                    raw = self.provider_manager.call_llm_api(self.llm_provider, task)
                    self.last_response = raw
                    return self._clean_code(raw)
                except Exception as e:
                    print(f"[SIG Agent] Avertissement échec ProviderManager ({e}). Repli sur l'API directe.")

            if self.llm_provider == "groq":
                raw = self._call_groq_api(task)
                self.last_response = raw
                return raw
            elif self.llm_provider == "openai":
                raw = self._call_openai_api(task)
                self.last_response = raw
                return raw
            elif self.llm_provider in ["ollama", "colab", "kaggle"]:
                raw = self._call_ollama_api(task)
                self.last_response = raw
                return self._clean_code(raw)
            else:
                raw = self._call_openrouter_api(task)
                self.last_response = raw
                return self._clean_code(raw)

        # Mode local correction
        model_prompt = (
            "<|im_start|>system\nTu es un expert Python et SIG. Corrige l'erreur.<|im_end|>\n"
            f"<|im_start|>user\n{task}<|im_end|>\n"
            "<|im_start|>assistant\n"
        )

        inputs = self.tokenizer(model_prompt, return_tensors="pt", truncation=True, max_length=3072)
        inputs = {k: v.to(self.model.device) for k, v in inputs.items()}
        input_len = inputs["input_ids"].shape[1]

        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=3072,
                temperature=0.05,
                top_p=0.95,
                pad_token_id=self.tokenizer.eos_token_id,
            )
        
        generated_ids = outputs[0][input_len:]
        raw_output = self.tokenizer.decode(generated_ids, skip_special_tokens=True)
        self.last_system_prompt = constraints + "\n\n### SQUELETTE DE CODE :\n" + skeleton
        self.last_user_prompt = context + "\n\n### Instruction :\n" + prompt
        self.last_response = raw_output
        return self._clean_code(raw_output)

    def _call_groq_api(self, prompt: str) -> str:
        """Appelle l'API Cloud Groq."""
        if not self.groq_api_key:
            raise ValueError("GROQ_API_KEY manquante dans les variables d'environnement.")
        
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.groq_api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.groq_model,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.1
        }
        
        res = requests.post(url, headers=headers, json=payload, timeout=30)
        try:
            res.raise_for_status()
        except requests.exceptions.HTTPError as e:
            print(f"[Groq API Error Response] : {res.text}")
            raise e
        return self._clean_code(res.json()["choices"][0]["message"]["content"])

    def _call_openai_api(self, prompt: str) -> str:
        """Appelle l'API Cloud OpenAI."""
        if not self.openai_api_key:
            raise ValueError("OPENAI_API_KEY manquante dans les variables d'environnement.")
        
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.openai_api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.openai_model,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.1
        }
        res = requests.post(url, headers=headers, json=payload, timeout=30)
        res.raise_for_status()
        return self._clean_code(res.json()["choices"][0]["message"]["content"])

    def _call_openrouter_api(self, prompt: str) -> str:
        """Appelle l'API Cloud OpenRouter."""
        if not self.openrouter_api_key:
            raise ValueError("OPENROUTER_API_KEY manquante dans les variables d'environnement.")
        
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.openrouter_api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/dhieeddine/Net2Terraform-WebInterface",
            "X-Title": "CartaGen"
        }
        payload = {
            "model": self.openrouter_model,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.1
        }
        res = requests.post(url, headers=headers, json=payload, timeout=30)
        res.raise_for_status()
        return self._clean_code(res.json()["choices"][0]["message"]["content"])

    def _call_ollama_api(self, prompt: str) -> str:
        """Appelle Ollama / Kaggle GPU / Colab via API distante."""
        base_url = self.ollama_url.rstrip("/")
        headers = {
            "ngrok-skip-browser-warning": "true",
            "Bypass-Tunnel-Remainder": "true",
            "User-Agent": "CartaGenAgent/1.0",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.ollama_model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.1
            }
        }

        urls = [f"{base_url}/generate", f"{base_url}/api/generate", base_url]
        last_err = None
        for url in urls:
            try:
                res = requests.post(url, headers=headers, json=payload, timeout=180)
                if res.status_code == 404:
                    continue
                res.raise_for_status()
                data = res.json()
                if "response" in data:
                    return self._clean_code(data["response"])
                elif "generated_text" in data:
                    return self._clean_code(data["generated_text"])
                elif "text" in data:
                    return self._clean_code(data["text"])
                elif "choices" in data:
                    return self._clean_code(data["choices"][0]["message"]["content"])
                else:
                    return self._clean_code(str(data))
            except Exception as e:
                last_err = e

        if last_err:
            raise last_err

    def _clean_code(self, text: str) -> str:
        """Extrait le code Python pur depuis la réponse LLM.

        Gère tous les cas : simple ```python```, double imbrication (```python\\n```python),
        bavardage du LLM avant/après, balises ChatML résiduelles, et code nu sans balises.
        """
        import re

        # 1. Supprimer les balises ChatML résiduelles
        text = re.sub(r'<\|im_(start|end)\|>(system|user|assistant)?', '', text)
        text = text.strip()

        # 2. Si ```python présent → extraire après le DERNIER marqueur ```python
        #    (consomme toutes les imbrications : ```python\n```python\n... → prend le dernier)
        if '```python' in text:
            parts = text.split('```python')
            # Tout ce qui suit le dernier ```python
            inner = parts[-1]
            # Couper à la PREMIÈRE occurrence de ``` (fermeture du bloc de code interne)
            if '```' in inner:
                inner = inner[:inner.find('```')]
            return inner.strip()

        # 3. Balise ``` générique (sans 'python')
        if '```' in text:
            parts = text.split('```')
            # Le code est dans les parties à index impair (1, 3, 5, ...)
            for i in range(1, len(parts), 2):
                candidate = parts[i].strip()
                if candidate:
                    return candidate

        # 4. Code nu sans balises
        # Supprimer les lignes "```" résiduelles en tête/queue
        lines = text.splitlines()
        while lines and lines[0].strip() in ('```python', '```', '~~~python', '~~~'):
            lines.pop(0)
        while lines and lines[-1].strip() in ('```', '~~~'):
            lines.pop()

        return '\n'.join(lines).strip()


    # Définition des squelettes d'injection (Mono, Single Gouv, etc.)
    def _skeleton_mono(self) -> str:
        return (
            "import pandas as pd\n"
            "import numpy as np\n"
            "import geopandas as gpd\n"
            "import matplotlib.pyplot as plt\n"
            "from matplotlib.ticker import ScalarFormatter\n"
            "from matplotlib.colors import ListedColormap, BoundaryNorm\n"
            "from matplotlib.patches import Patch\n"
            "import sqlalchemy\n"
            "import os\n"
            "from shapely.vectorized import contains\n"
            "\n"
            "# Connexion unique via SQLAlchemy\n"
            "engine = sqlalchemy.create_engine(os.environ['DATABASE_URL'])\n"
            "\n"
            "# 1. Charger les données pluviométriques\n"
            "query = \"\"\"[requete_sql]\"\"\"\n"
            "df = pd.read_sql(query, engine)\n"
            "df.columns = df.columns.str.lower()\n"
            "\n"
            "# 2. Chargement des couches géographiques depuis PostGIS\n"
            "gdf_pays = gpd.read_postgis('SELECT geom FROM limite_pays_polygon', engine, geom_col='geom').to_crs('EPSG:32632')\n"
            "gdf_gouv = gpd.read_postgis('SELECT lib_fr, geom FROM gouvernorats', engine, geom_col='geom').to_crs('EPSG:32632')\n"
            "\n"
            "target_col = '[colonne_cible]'\n"
            "titre_carte = '[titre_carte]'\n"
            "\n"
            "# 3. Nettoyage des données et reprojection intelligente des coordonnées en mètres (EPSG:32632)\n"
            "if target_col not in df.columns or target_col in ['id', 'x', 'y']:\n"
            "    df[target_col] = 1.0\n"
            "df = df.dropna(subset=[target_col, 'x', 'y'])\n"
            "df = df.reset_index(drop=True)\n"
            "if df.empty:\n"
            "    raise ValueError(f\"Aucune donnée disponible pour la colonne '{target_col}'\")\n"
            "if not df.empty and df['x'].abs().max() <= 180:\n"
            "    gdf_st_proj = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df['x'], df['y']), crs='EPSG:4326').to_crs('EPSG:32632')\n"
            "    df['x'] = gdf_st_proj.geometry.x\n"
            "    df['y'] = gdf_st_proj.geometry.y\n"
            "\n"
            "# Niveaux par catégories de période :\n"
            "# < 1 mois (journalier) : <5 à >100\n"
            "# 1 mois à < 1 an (mensuel/saisonnier) : <20 à >250\n"
            "# >= 1 an (annuel/total) : <50 à >1200\n"
            "if target_col in ['jour', 'valeur_mm', 'valeur', 'jour_mm', 'debit'] or (isinstance(target_col, str) and ('jour' in target_col or 'day' in target_col)):\n"
            "    niveaux = [0, 5, 10, 20, 30, 50, 75, 100, 150]\n"
            "elif target_col in ['janv','fev','mar','avr','mai','juin','juil','aout','sept','octo','nove','dece','auto','hiver','print','ete']:\n"
            "    niveaux = [0, 20, 50, 75, 100, 150, 200, 250, 350]\n"
            "else:\n"
            "    niveaux = [0, 50, 100, 200, 400, 600, 800, 1000, 1200]\n"
            "\n"
            "# 8 couleurs standardisées : du bleu foncé pour le max vers le vert, jaune, rouge, et premier intervalle sans couleur ('none')\n"
            "couleurs = ['none', '#ff0000', '#ffff00', '#90ee90', '#228b22', '#4292c6', '#2171b5', '#08306b']\n"
            "cmap = ListedColormap(couleurs)\n"
            "norm = BoundaryNorm(niveaux, cmap.N)\n"
            "\n"
            "bounds = gdf_pays.total_bounds\n"
            "x_min, y_min, x_max, y_max = bounds\n"
            "margin = 20000\n"
            "x_min -= margin; x_max += margin; y_min -= margin; y_max += margin\n"
            "x_grid = np.arange(x_min, x_max, 2500)\n"
            "y_grid = np.arange(y_min, y_max, 2500)\n"
            "x_mesh, y_mesh = np.meshgrid(x_grid, y_grid)\n"
            "grid_points = np.column_stack([x_mesh.ravel(), y_mesh.ravel()])\n"
            "k_val = min(10, len(df))\n"
            "tree = cKDTree(df[['x', 'y']].values)\n"
            "distances, indices = tree.query(grid_points, k=k_val)\n"
            "distances = np.maximum(distances, 1e-10)\n"
            "if k_val > 1:\n"
            "    weights = 1.0 / (distances ** 2)\n"
            "    weights /= weights.sum(axis=1, keepdims=True)\n"
            "    z_1d = np.sum(weights * df[target_col].values[indices], axis=1)\n"
            "else:\n"
            "    z_1d = np.repeat(df[target_col].values[0], len(grid_points))\n"
            "\n"
            "geom = gdf_pays.geometry.unary_union\n"
            "mask_1d = contains(geom, grid_points[:, 0], grid_points[:, 1])\n"
            "z_2d = np.where(mask_1d, z_1d, np.nan).reshape(x_mesh.shape)\n"
            "z_2d = np.ma.masked_invalid(z_2d)\n"
            "\n"
            "fig, ax = plt.subplots(figsize=(7, 9))\n"
            "ax.set_aspect('equal')\n"
            "gdf_pays.plot(ax=ax, facecolor='none', edgecolor='black', linewidth=1.5, zorder=4)\n"
            "gdf_gouv.plot(ax=ax, facecolor='none', edgecolor='grey', linewidth=0.5, linestyle='--', zorder=3)\n"
            "for _, g_row in gdf_gouv.iterrows():\n"
            "    cent = g_row.geometry.centroid\n"
            "    g_name = g_row.get('lib_fr', g_row.get('nom', ''))\n"
            "    if g_name:\n"
            "        ax.text(cent.x, cent.y, str(g_name), fontsize=5.5, ha='center', va='center', color='#2c3e50', fontweight='bold', alpha=0.65, zorder=6)\n"
            "cf = ax.contourf(x_mesh, y_mesh, z_2d, levels=niveaux, cmap=cmap, norm=norm, alpha=0.75, extend='max', zorder=1)\n"
            "cs = ax.contour(x_mesh, y_mesh, z_2d, levels=niveaux, colors='#2c3e50', linewidths=0.6, zorder=2)\n"
            "ax.clabel(cs, inline=True, fontsize=7, fmt='%d mm')\n"
            "ax.scatter(df['x'], df['y'], s=12, color='#c0392b', marker='o', zorder=5)\n"
            "ax.set_xlim(bounds[0] - margin, bounds[2] + margin)\n"
            "ax.set_ylim(bounds[1] - margin, bounds[3] + margin)\n"
            "ax.set_title(titre_carte, fontsize=12, fontweight='bold', pad=10)\n"
            "ax.set_xlabel('X (UTM Zone 32N, m)', fontsize=9, fontweight='bold', fontstyle='italic')\n"
            "ax.set_ylabel('Y (UTM Zone 32N, m)', fontsize=9, fontweight='bold', fontstyle='italic')\n"
            "\n"
            "formatter_y = ScalarFormatter(useOffset=False)\n"
            "formatter_y.set_scientific(False)\n"
            "ax.yaxis.set_major_formatter(formatter_y)\n"
            "formatter_x = ScalarFormatter(useOffset=False)\n"
            "formatter_x.set_scientific(False)\n"
            "ax.xaxis.set_major_formatter(formatter_x)\n"
            "\n"
            "ax.tick_params(axis='x', rotation=45, labelsize=8)\n"
            "ax.tick_params(axis='y', rotation=45, labelsize=8)\n"
            "for tick in ax.get_xticklabels() + ax.get_yticklabels():\n"
            "    tick.set_fontstyle('italic')\n"
            "ax.grid(True, linestyle='--', alpha=0.3)\n"
            "cx, cy, csize = 0.92, 0.88, 0.05\n"
            "ax.annotate('N', xy=(cx, cy + csize), xytext=(cx, cy), arrowprops=dict(facecolor='black', edgecolor='black', width=1.5, headwidth=6, headlength=7), ha='center', va='bottom', fontsize=8, fontweight='bold', xycoords='axes fraction', textcoords='axes fraction')\n"
            "ax.text(cx, cy - csize * 0.4, 'S', transform=ax.transAxes, ha='center', va='top', fontsize=7, fontweight='bold')\n"
            "ax.text(cx + csize * 0.8, cy + csize * 0.3, 'E', transform=ax.transAxes, ha='left', va='center', fontsize=7, fontweight='bold')\n"
            "ax.text(cx - csize * 0.8, cy + csize * 0.3, 'O', transform=ax.transAxes, ha='right', va='center', fontsize=7, fontweight='bold')\n"
            "legend_elements = [Patch(facecolor=couleurs[i], label=f\"{niveaux[i]} - {niveaux[i+1]} mm\" if i < len(niveaux)-2 else f\"> {niveaux[i]} mm\") for i in range(len(niveaux)-1)]\n"
            "ax.legend(handles=legend_elements, title='Pluviométrie', loc='lower left', fontsize=8, title_fontsize=9, framealpha=0.9)\n"
            "plt.tight_layout()\n"
            "plt.savefig('output_isohyete.png', dpi=300, bbox_inches='tight')\n"
            "plt.close()\n"
        )

    def _skeleton_analysis(self) -> str:
        return (
            "import os\n"
            "import pandas as pd\n"
            "import numpy as np\n"
            "import matplotlib.pyplot as plt\n"
            "import seaborn as sns\n"
            "import sqlalchemy\n"
            "\n"
            "# 1. Connexion via SQLAlchemy\n"
            "engine = sqlalchemy.create_engine(os.environ['DATABASE_URL'])\n"
            "\n"
            "# 2. Charger les données pluviométriques\n"
            "query = \"\"\"[requete_sql]\"\"\"\n"
            "df = pd.read_sql(query, engine)\n"
            "df.columns = df.columns.str.lower()\n"
            "\n"
            "# 3. Analyse de données et génération de figures (Seaborn/Matplotlib)\n"
            "plt.tight_layout()\n"
            "plt.savefig('output_isohyete.png', dpi=300, bbox_inches='tight')\n"
            "plt.close()\n"
        )

    def _skeleton_single_gouv(self) -> str:
        return (
            "import pandas as pd\n"
            "import numpy as np\n"
            "import geopandas as gpd\n"
            "import matplotlib.pyplot as plt\n"
            "import unicodedata\n"
            "from scipy.spatial import cKDTree\n"
            "from shapely.vectorized import contains\n"
            "from matplotlib.ticker import ScalarFormatter\n"
            "from matplotlib.colors import ListedColormap, BoundaryNorm\n"
            "from matplotlib.patches import Patch\n"
            "import sqlalchemy\n"
            "import os\n"
            "\n"
            "# Connexion unique via SQLAlchemy\n"
            "engine = sqlalchemy.create_engine(os.environ['DATABASE_URL'])\n"
            "\n"
            "# 1. Charger les données pluviométriques\n"
            "query = \"\"\"[requete_sql]\"\"\"\n"
            "df = pd.read_sql(query, engine)\n"
            "df.columns = df.columns.str.lower()\n"
            "\n"
            "# 2. Chargement des couches géographiques depuis PostGIS\n"
            "gdf_pays = gpd.read_postgis('SELECT geom FROM limite_pays_polygon', engine, geom_col='geom').to_crs('EPSG:32632')\n"
            "gdf_gouv_all = gpd.read_postgis('SELECT lib_fr, lib_ar, code, geom FROM gouvernorats', engine, geom_col='geom').to_crs('EPSG:32632')\n"
            "\n"
            "NOM_GOUV   = '[NOM_DU_GOUVERNORAT]'\n"
            "target_col = '[colonne_cible]'\n"
            "titre_carte = f'Isohyetes — Gouvernorat de {NOM_GOUV} (Tunisie)'\n"
            "\n"
            "# 3. Normalisation des accents pour la comparaison (ex: 'Béja' == 'Beja')\n"
            "def normalize(s):\n"
            "    return unicodedata.normalize('NFD', s).encode('ascii', 'ignore').decode().lower().strip()\n"
            "\n"
            f"gdf_cible = gdf_gouv_all[gdf_gouv_all['{self.gouv_col}'].apply(normalize) == normalize(NOM_GOUV)].copy()\n"
            "if gdf_cible.empty:\n"
            f"    raise ValueError(f'Gouvernorat {{NOM_GOUV}} non trouve dans la table gouvernorats')\n"
            "\n"
            "# 4. Nettoyage des données\n"
            "if target_col not in df.columns or target_col in ['id', 'x', 'y']:\n"
            "    df[target_col] = 1.0\n"
            "df = df.dropna(subset=[target_col, 'x', 'y'])\n"
            "df = df.reset_index(drop=True)\n"
            "if df.empty:\n"
            "    raise ValueError(f\"Aucune donnée disponible pour la colonne '{target_col}'\")\n"
            "\n"
            "# 5. Reprojection intelligente des stations et filtrage spatial dans le gouvernorat\n"
            "if not df.empty and df['x'].abs().max() <= 180:\n"
            "    gdf_st_proj = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df['x'], df['y']), crs='EPSG:4326').to_crs('EPSG:32632')\n"
            "    df['x'] = gdf_st_proj.geometry.x\n"
            "    df['y'] = gdf_st_proj.geometry.y\n"
            "gdf_stations = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df['x'], df['y']), crs=\"EPSG:32632\")\n"
            "gdf_stations_gouv = gpd.sjoin(gdf_stations, gdf_cible[['geometry']], how=\"inner\", predicate=\"within\")\n"
            "df_stations_cible = df.loc[df.index.isin(gdf_stations_gouv.index)].copy()\n"
            "\n"
            "if df_stations_cible.empty:\n"
            "    # Fallback : 10 stations les plus proches du centroïde\n"
            "    centroid = gdf_cible.geometry.unary_union.centroid\n"
            "    df['_dist'] = np.sqrt((df['x'] - centroid.x)**2 + (df['y'] - centroid.y)**2)\n"
            "    df_stations_cible = df.nsmallest(10, '_dist').drop(columns=['_dist'])\n"
            "\n"
            "# 6. Grille d'interpolation — zoomée sur le gouvernorat\n"
            "g_bounds = gdf_cible.total_bounds\n"
            "margin = 15000\n"
            "x_min, y_min, x_max, y_max = g_bounds[0]-margin, g_bounds[1]-margin, g_bounds[2]+margin, g_bounds[3]+margin\n"
            "x_grid = np.arange(x_min, x_max, 1000)\n"
            "y_grid = np.arange(y_min, y_max, 1000)\n"
            "x_mesh, y_mesh = np.meshgrid(x_grid, y_grid)\n"
            "grid_points = np.column_stack([x_mesh.ravel(), y_mesh.ravel()])\n"
            "\n"
            "coords_locales = df_stations_cible[['x', 'y']].values\n"
            "valeurs_locales = df_stations_cible[target_col].values\n"
            "tree = cKDTree(coords_locales)\n"
            "k_val = min(10, len(df_stations_cible))\n"
            "distances, indices = tree.query(grid_points, k=k_val)\n"
            "if k_val > 1:\n"
            "    distances = np.maximum(distances, 1e-10)\n"
            "    weights = 1.0 / (distances ** 2)\n"
            "    weights /= weights.sum(axis=1, keepdims=True)\n"
            "    z_1d = np.sum(weights * valeurs_locales[indices], axis=1)\n"
            "else:\n"
            "    z_1d = np.repeat(valeurs_locales[0], len(grid_points))\n"
            "\n"
            "geom_cible = gdf_cible.geometry.unary_union\n"
            "mask_1d = contains(geom_cible, grid_points[:, 0], grid_points[:, 1])\n"
            "z_2d = np.where(mask_1d, z_1d, np.nan).reshape(x_mesh.shape)\n"
            "z_2d = np.ma.masked_invalid(z_2d)\n"
            "\n"
            "if target_col in ['jour', 'valeur_mm', 'valeur', 'jour_mm', 'debit'] or (isinstance(target_col, str) and ('jour' in target_col or 'day' in target_col)):\n"
            "    niveaux = [0, 5, 10, 20, 30, 50, 75, 100, 150]\n"
            "elif target_col in ['janv','fev','mar','avr','mai','juin','juil','aout','sept','octo','nove','dece','auto','hiver','print','ete']:\n"
            "    niveaux = [0, 20, 50, 75, 100, 150, 200, 250, 350]\n"
            "else:\n"
            "    niveaux = [0, 50, 100, 200, 400, 600, 800, 1000, 1200]\n"
            "couleurs = ['none', '#ff0000', '#ffff00', '#90ee90', '#228b22', '#4292c6', '#2171b5', '#08306b']\n"
            "cmap = ListedColormap(couleurs)\n"
            "norm = BoundaryNorm(niveaux, cmap.N)\n"
            "\n"
            "fig, ax = plt.subplots(figsize=(7, 9))\n"
            "ax.set_aspect('equal')\n"
            "gdf_gouv_all.boundary.plot(ax=ax, color='lightgrey', linestyle='--', linewidth=0.6)\n"
            "gdf_pays.boundary.plot(ax=ax, color='black', linewidth=1.5)\n"
            "gdf_cible.boundary.plot(ax=ax, color='black', linewidth=2.0)\n"
            "for _, g_row in gdf_gouv_all.iterrows():\n"
            "    cent = g_row.geometry.centroid\n"
            "    g_name = g_row.get('lib_fr', g_row.get('nom', ''))\n"
            "    if g_name:\n"
            "        ax.text(cent.x, cent.y, str(g_name), fontsize=5.5, ha='center', va='center', color='#2c3e50', fontweight='bold', alpha=0.65, zorder=6)\n"
            "\n"
            "if not np.all(np.isnan(z_2d)):\n"
            "    cf = ax.contourf(x_mesh, y_mesh, z_2d, levels=niveaux, cmap=cmap, norm=norm, alpha=0.75, extend='max')\n"
            "    cs = ax.contour(x_mesh, y_mesh, z_2d, levels=niveaux, colors='#2c3e50', linewidths=0.6)\n"
            "    ax.clabel(cs, inline=True, fontsize=7, fmt='%d mm')\n"
            "\n"
            "ax.scatter(df_stations_cible['x'], df_stations_cible['y'], s=12, color='#c0392b', marker='o', zorder=5)\n"
            "ax.set_xlim(x_min, x_max); ax.set_ylim(y_min, y_max)\n"
            "ax.set_title(titre_carte, fontsize=12, fontweight='bold', pad=10)\n"
            "ax.set_xlabel('X (UTM Zone 32N, m)', fontsize=9, fontweight='bold', fontstyle='italic')\n"
            "ax.set_ylabel('Y (UTM Zone 32N, m)', fontsize=9, fontweight='bold', fontstyle='italic')\n"
            "\n"
            "formatter_y = ScalarFormatter(useOffset=False)\n"
            "formatter_y.set_scientific(False)\n"
            "ax.yaxis.set_major_formatter(formatter_y)\n"
            "\n"
            "formatter_x = ScalarFormatter(useOffset=False)\n"
            "formatter_x.set_scientific(False)\n"
            "ax.xaxis.set_major_formatter(formatter_x)\n"
            "\n"
            "ax.tick_params(axis='x', rotation=45, labelsize=8)\n"
            "ax.tick_params(axis='y', rotation=45, labelsize=8)\n"
            "for tick in ax.get_xticklabels() + ax.get_yticklabels():\n"
            "    tick.set_fontstyle('italic')\n"
            "ax.grid(True, linestyle='--', alpha=0.3)\n"
            "cx, cy, csize = 0.92, 0.88, 0.05\n"
            "ax.annotate('N', xy=(cx, cy + csize), xytext=(cx, cy), arrowprops=dict(facecolor='black', edgecolor='black', width=1.5, headwidth=6, headlength=7), ha='center', va='bottom', fontsize=8, fontweight='bold', xycoords='axes fraction', textcoords='axes fraction')\n"
            "ax.text(cx, cy - csize * 0.4, 'S', transform=ax.transAxes, ha='center', va='top', fontsize=7, fontweight='bold')\n"
            "ax.text(cx + csize * 0.8, cy + csize * 0.3, 'E', transform=ax.transAxes, ha='left', va='center', fontsize=7, fontweight='bold')\n"
            "ax.text(cx - csize * 0.8, cy + csize * 0.3, 'O', transform=ax.transAxes, ha='right', va='center', fontsize=7, fontweight='bold')\n"
            "legend_elements = [Patch(facecolor=couleurs[i], label=f\"{niveaux[i]} - {niveaux[i+1]} mm\" if i < len(niveaux)-2 else f\"> {niveaux[i]} mm\") for i in range(len(niveaux)-1)]\n"
            "ax.legend(handles=legend_elements, title='Pluviométrie', loc='lower left', fontsize=8, title_fontsize=9, framealpha=0.9)\n"
            "plt.tight_layout()\n"
            "plt.savefig('output_isohyete.png', dpi=300, bbox_inches='tight')\n"
            "plt.close()\n"
        )


    def _skeleton_compare_gouv(self) -> str:
        return (
            "import pandas as pd\n"
            "import numpy as np\n"
            "import geopandas as gpd\n"
            "import matplotlib.pyplot as plt\n"
            "from scipy.spatial import cKDTree\n"
            "from shapely.vectorized import contains\n"
            "from matplotlib.colors import ListedColormap, BoundaryNorm\n"
            "from matplotlib.patches import Patch\n"
            "import psycopg2\n"
            "import os\n"
            "\n"
            "conn = psycopg2.connect(os.environ['DATABASE_URL'])\n"
            "query = \"\"\"[requete_sql]\"\"\"\n"
            "df = pd.read_sql(query, conn)\n"
            "conn.close()\n"
            "df.columns = df.columns.str.lower()\n"
            "\n"
            "# Chargement des couches géographiques depuis PostGIS\n"
            "import sqlalchemy\n"
            "engine = sqlalchemy.create_engine(os.environ['DATABASE_URL'])\n"
            "gdf_pays = gpd.read_postgis('SELECT geom FROM limite_pays_polygon', engine, geom_col='geom').to_crs('EPSG:32632')\n"
            "gdf_gouv_all = gpd.read_postgis('SELECT lib_fr, lib_ar, code, geom FROM gouvernorats', engine, geom_col='geom').to_crs('EPSG:32632')\n"
            "\n"
            "NOM_GOUV_1 = '[GOUVERNORAT_1]'\n"
            "NOM_GOUV_2 = '[GOUVERNORAT_2]'\n"
            "target_col  = '[colonne_cible]'\n"
            "titre_global = f'Comparaison isohyetes : {NOM_GOUV_1} vs {NOM_GOUV_2}'\n"
            "\n"
            "if target_col == 'total':\n"
            "    niveaux = [0, 100, 200, 300, 400, 500, 600, 800, 1000, 1200, 1500]\n"
            "    labels  = ['<100 mm','100-200','200-300','300-400','400-500','500-600','600-800','800-1000','1000-1200','>1200 mm']\n"
            "elif target_col in ['auto', 'hiver', 'print', 'ete']:\n"
            "    niveaux = [0, 25, 50, 75, 100, 125, 188, 250, 375, 500, 750]\n"
            "    labels  = ['<25 mm','25-50','50-75','75-100','100-125','125-188','188-250','250-375','375-500','>500 mm']\n"
            "else:\n"
            "    niveaux = [0, 10, 20, 30, 40, 50, 75, 100, 150, 200, 300]\n"
            "    labels  = ['<10 mm','10-20','20-30','30-40','40-50','50-75','75-100','100-150','150-200','>200 mm']\n"
            "couleurs = ['#ff0000','#8B4513','#F5DEB3','#FFFF00','#90EE90','#7CCD7C','#228B22','#0000FF','#8A2BE2','#4B0082']\n"
            "cmap = ListedColormap(couleurs)\n"
            "norm = BoundaryNorm(niveaux, cmap.N)\n"
            "\n"
            f"gdf_compare = gdf_gouv_all[gdf_gouv_all['{self.gouv_col}'].str.lower().isin([NOM_GOUV_1.lower(), NOM_GOUV_2.lower()])].copy()\n"
            "geom_cibles = gdf_compare.geometry.unary_union\n"
            "\n"
            "gdf_stations = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df['x'], df['y']), crs=\"EPSG:32632\")\n"
            "gdf_stations_gouv = gpd.sjoin(gdf_stations, gdf_gouv_all, how=\"inner\", predicate=\"within\")\n"
            f"df_stations_compare = gdf_stations_gouv[gdf_stations_gouv['{self.gouv_col}'].str.lower().isin([NOM_GOUV_1.lower(), NOM_GOUV_2.lower()])].copy()\n"
            "\n"
            "if df_stations_compare.empty:\n"
            "    df_stations_compare = gdf_stations.copy()\n"
            "\n"
            "bounds = gdf_pays.total_bounds\n"
            "x_min, y_min, x_max, y_max = bounds\n"
            "margin = 20000\n"
            "x_min -= margin; x_max += margin; y_min -= margin; y_max += margin\n"
            "x_grid = np.arange(x_min, x_max, 2500)\n"
            "y_grid = np.arange(y_min, y_max, 2500)\n"
            "x_mesh, y_mesh = np.meshgrid(x_grid, y_grid)\n"
            "grid_points = np.column_stack([x_mesh.ravel(), y_mesh.ravel()])\n"
            "\n"
            "coords_locales = df_stations_compare[['x', 'y']].values\n"
            "valeurs_locales = df_stations_compare[target_col].values\n"
            "tree = cKDTree(coords_locales)\n"
            "k_val = min(10, len(df_stations_compare))\n"
            "distances, indices = tree.query(grid_points, k=k_val)\n"
            "if k_val > 1:\n"
            "    distances = np.maximum(distances, 1e-10)\n"
            "    weights = 1.0 / (distances ** 2)\n"
            "    weights /= weights.sum(axis=1, keepdims=True)\n"
            "    z_1d = np.sum(weights * valeurs_locales[indices], axis=1)\n"
            "else:\n"
            "    z_1d = np.repeat(valeurs_locales[0], len(grid_points))\n"
            "\n"
            "mask_1d = contains(geom_cibles, grid_points[:, 0], grid_points[:, 1])\n"
            "z_2d = np.where(mask_1d, z_1d, np.nan).reshape(x_mesh.shape)\n"
            "z_2d = np.ma.masked_invalid(z_2d)\n"
            "\n"
            "fig, ax = plt.subplots(figsize=(9, 12))\n"
            "ax.set_aspect('equal')\n"
            "gdf_gouv_all.boundary.plot(ax=ax, color='lightgrey', linestyle='--', linewidth=0.6)\n"
            "gdf_pays.boundary.plot(ax=ax, color='black', linewidth=1.5)\n"
            "\n"
            "if not np.all(np.isnan(z_2d)):\n"
            "    cf = ax.contourf(x_mesh, y_mesh, z_2d, levels=niveaux, cmap=cmap, norm=norm, alpha=0.8, extend='max')\n"
            "    cl = ax.contour(x_mesh, y_mesh, z_2d, levels=niveaux, colors='black', linewidths=0.5)\n"
            "    ax.clabel(cl, inline=True, fontsize=7, fmt='%d mm')\n"
            "\n"
            "gdf_compare.boundary.plot(ax=ax, color='black', linewidth=1.8)\n"
            "ax.scatter(df_stations_compare['x'], df_stations_compare['y'], s=25, color='red', edgecolor='black', zorder=5)\n"
            "legend_elements = [Patch(facecolor=c, label=l) for c, l in zip(couleurs, labels)]\n"
            "ax.legend(handles=legend_elements, title='Précipitations', loc='lower right', fontsize=8)\n"
            "ax.set_xlim(x_min, x_max); ax.set_ylim(y_min, y_max)\n"
            "ax.set_title(titre_global, fontsize=14, fontweight='bold')\n"
            "ax.grid(True, linestyle='--', alpha=0.2)\n"
            "plt.tight_layout()\n"
            "plt.savefig('output_isohyete.png', dpi=300, bbox_inches='tight')\n"
            "plt.close()\n"
        )

    def _skeleton_region_hydro(self) -> str:
        return (
            "import pandas as pd\n"
            "import numpy as np\n"
            "import geopandas as gpd\n"
            "import matplotlib.pyplot as plt\n"
            "import unicodedata\n"
            "from scipy.spatial import cKDTree\n"
            "from shapely.vectorized import contains\n"
            "from matplotlib.colors import ListedColormap, BoundaryNorm\n"
            "from matplotlib.patches import Patch\n"
            "import sqlalchemy\n"
            "import os\n"
            "\n"
            "# Connexion unique via SQLAlchemy\n"
            "engine = sqlalchemy.create_engine(os.environ['DATABASE_URL'])\n"
            "\n"
            "# 1. Charger les données pluviométriques\n"
            "query = \"\"\"[requete_sql]\"\"\"\n"
            "df = pd.read_sql(query, engine)\n"
            "df.columns = df.columns.str.lower()\n"
            "\n"
            "# 2. Chargement des couches géographiques depuis PostGIS\n"
            "gdf_pays = gpd.read_postgis('SELECT geom FROM limite_pays_polygon', engine, geom_col='geom').to_crs('EPSG:32632')\n"
            "gdf_gouv = gpd.read_postgis('SELECT lib_fr, geom FROM gouvernorats', engine, geom_col='geom').to_crs('EPSG:32632')\n"
            "gdf_reg_all = gpd.read_postgis('SELECT lib_fr, lib_ar, code, geom FROM rgion_hydrographique', engine, geom_col='geom').to_crs('EPSG:32632')\n"
            "\n"
            "NOM_REG   = '[NOM_DE_LA_REGION]'\n"
            "target_col = '[colonne_cible]'\n"
            "titre_carte = f'Isohyetes — Region Hydrographique de {NOM_REG} (Tunisie)'\n"
            "\n"
            "# 3. Normalisation des accents pour la comparaison (ex: 'Sud' == 'sud')\n"
            "def normalize(s):\n"
            "    if s is None: return ''\n"
            "    return unicodedata.normalize('NFD', str(s)).encode('ascii', 'ignore').decode().lower().strip()\n"
            "\n"
            f"gdf_cible = gdf_reg_all[gdf_reg_all['{self.reg_col}'].apply(normalize) == normalize(NOM_REG)].copy()\n"
            "if gdf_cible.empty:\n"
            f"    raise ValueError(f'Region hydrographique {{NOM_REG}} non trouvee dans la table rgion_hydrographique')\n"
            "\n"
            "# 4. Nettoyage des données\n"
            "df = df.dropna(subset=[target_col])\n"
            "df = df.reset_index(drop=True)\n"
            "if df.empty:\n"
            "    raise ValueError(f\"Aucune donnée disponible pour la colonne '{target_col}'\")\n"
            "\n"
            "# 5. Filtrage spatial des stations dans la région hydrographique\n"
            "gdf_stations = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df['x'], df['y']), crs=\"EPSG:32632\")\n"
            "gdf_stations_reg = gpd.sjoin(gdf_stations, gdf_cible[['geometry']], how=\"inner\", predicate=\"within\")\n"
            "df_stations_cible = df.loc[df.index.isin(gdf_stations_reg.index)].copy()\n"
            "\n"
            "if df_stations_cible.empty:\n"
            "    # Fallback : 10 stations les plus proches du centroïde de la région\n"
            "    centroid = gdf_cible.geometry.unary_union.centroid\n"
            "    df['_dist'] = np.sqrt((df['x'] - centroid.x)**2 + (df['y'] - centroid.y)**2)\n"
            "    df_stations_cible = df.nsmallest(10, '_dist').drop(columns=['_dist'])\n"
            "\n"
            "# 6. Grille d'interpolation — zoomée sur la région\n"
            "g_bounds = gdf_cible.total_bounds\n"
            "margin = 15000\n"
            "x_min, y_min, x_max, y_max = g_bounds[0]-margin, g_bounds[1]-margin, g_bounds[2]+margin, g_bounds[3]+margin\n"
            "x_grid = np.arange(x_min, x_max, 1000)\n"
            "y_grid = np.arange(y_min, y_max, 1000)\n"
            "x_mesh, y_mesh = np.meshgrid(x_grid, y_grid)\n"
            "grid_points = np.column_stack([x_mesh.ravel(), y_mesh.ravel()])\n"
            "\n"
            "coords_locales = df_stations_cible[['x', 'y']].values\n"
            "valeurs_locales = df_stations_cible[target_col].values\n"
            "tree = cKDTree(coords_locales)\n"
            "k_val = min(10, len(df_stations_cible))\n"
            "distances, indices = tree.query(grid_points, k=k_val)\n"
            "if k_val > 1:\n"
            "    distances = np.maximum(distances, 1e-10)\n"
            "    weights = 1.0 / (distances ** 2)\n"
            "    weights /= weights.sum(axis=1, keepdims=True)\n"
            "    z_1d = np.sum(weights * valeurs_locales[indices], axis=1)\n"
            "else:\n"
            "    z_1d = np.repeat(valeurs_locales[0], len(grid_points))\n"
            "\n"
            "geom_cible = gdf_cible.geometry.unary_union\n"
            "mask_1d = contains(geom_cible, grid_points[:, 0], grid_points[:, 1])\n"
            "z_2d = np.where(mask_1d, z_1d, np.nan).reshape(x_mesh.shape)\n"
            "z_2d = np.ma.masked_invalid(z_2d)\n"
            "\n"
            "if target_col == 'total':\n"
            "    niveaux = [0, 100, 200, 300, 400, 500, 600, 800, 1000, 1200, 1500]\n"
            "    labels  = ['<100 mm','100-200','200-300','300-400','400-500','500-600','600-800','800-1000','1000-1200','>1200 mm']\n"
            "elif target_col in ['auto', 'hiver', 'print', 'ete']:\n"
            "    niveaux = [0, 25, 50, 75, 100, 125, 188, 250, 375, 500, 750]\n"
            "    labels  = ['<25 mm','25-50','50-75','75-100','100-125','125-188','188-250','250-375','375-500','>500 mm']\n"
            "elif target_col in ['janv','fev','mar','avr','mai','juin','juil','aout','sept','octo','nove','dece']:\n"
            "    niveaux = [0, 10, 20, 30, 40, 50, 75, 100, 150, 200, 300]\n"
            "    labels  = ['<10 mm','10-20','20-30','30-40','40-50','50-75','75-100','100-150','150-200','>200 mm']\n"
            "else:\n"
            "    niveaux = [0, 10, 20, 30, 40, 50, 75, 100, 150, 200, 300]\n"
            "    labels  = ['<10 mm','10-20','20-30','30-40','40-50','50-75','75-100','100-150','150-200','>200 mm']\n"
            "couleurs = ['#ff0000','#8B4513','#F5DEB3','#FFFF00','#90EE90','#7CCD7C','#228B22','#0000FF','#8A2BE2','#4B0082']\n"
            "cmap = ListedColormap(couleurs)\n"
            "norm = BoundaryNorm(niveaux, cmap.N)\n"
            "\n"
            "fig, ax = plt.subplots(figsize=(9, 11))\n"
            "ax.set_aspect('equal')\n"
            "gdf_gouv.boundary.plot(ax=ax, color='lightgrey', linestyle='--', linewidth=0.6)\n"
            "gdf_pays.boundary.plot(ax=ax, color='black', linewidth=1.5)\n"
            "gdf_cible.boundary.plot(ax=ax, color='blue', linewidth=2.0)\n"
            "\n"
            "if not np.all(np.isnan(z_2d)):\n"
            "    ax.contourf(x_mesh, y_mesh, z_2d, levels=niveaux, cmap=cmap, norm=norm, alpha=0.75, extend='max')\n"
            "    cl = ax.contour(x_mesh, y_mesh, z_2d, levels=niveaux, colors='black', linewidths=0.7)\n"
            "    ax.clabel(cl, inline=True, fontsize=8, fmt='%d mm')\n"
            "\n"
            "ax.scatter(df_stations_cible['x'], df_stations_cible['y'], s=25, color='red', edgecolor='black', zorder=5)\n"
            "legend_elements = [Patch(facecolor=c, label=l) for c, l in zip(couleurs, labels)]\n"
            "ax.legend(handles=legend_elements, title='Précipitations', loc='lower right', fontsize=8)\n"
            "ax.set_xlim(x_min, x_max); ax.set_ylim(y_min, y_max)\n"
            "ax.set_title(titre_carte, fontsize=14, fontweight='bold')\n"
            "ax.grid(True, linestyle='--', alpha=0.3)\n"
            "plt.tight_layout()\n"
            "plt.savefig('output_isohyete.png', dpi=300, bbox_inches='tight')\n"
            "plt.close()\n"
        )

    def _skeleton_difference(self) -> str:
        return (
            "import pandas as pd\n"
            "import numpy as np\n"
            "import geopandas as gpd\n"
            "import matplotlib.pyplot as plt\n"
            "from scipy.spatial import cKDTree\n"
            "from shapely.vectorized import contains\n"
            "from matplotlib.colors import ListedColormap, BoundaryNorm\n"
            "from matplotlib.patches import Patch\n"
            "import psycopg2\n"
            "import os\n"
            "\n"
            "conn = psycopg2.connect(os.environ['DATABASE_URL'])\n"
            "query = \"\"\"[requete_sql]\"\"\"\n"
            "df = pd.read_sql(query, conn)\n"
            "conn.close()\n"
            "df.columns = df.columns.str.lower()\n"
            "\n"
            "# Chargement des couches géographiques depuis PostGIS\n"
            "import sqlalchemy\n"
            "engine = sqlalchemy.create_engine(os.environ['DATABASE_URL'])\n"
            "gdf_pays = gpd.read_postgis('SELECT geom FROM limite_pays_polygon', engine, geom_col='geom').to_crs('EPSG:32632')\n"
            "gdf_gouv = gpd.read_postgis('SELECT lib_fr, geom FROM gouvernorats', engine, geom_col='geom').to_crs('EPSG:32632')\n"
            "\n"
            "df['diff'] = df['[colonne_1]'] - df['[colonne_2]']\n"
            "target_col = 'diff'\n"
            "titre_carte = '[titre_de_la_carte]'\n"
            "\n"
            "bounds = gdf_pays.total_bounds\n"
            "x_min, y_min, x_max, y_max = bounds\n"
            "margin = 20000\n"
            "x_min -= margin; x_max += margin; y_min -= margin; y_max += margin\n"
            "x_grid = np.arange(x_min, x_max, 2500)\n"
            "y_grid = np.arange(y_min, y_max, 2500)\n"
            "x_mesh, y_mesh = np.meshgrid(x_grid, y_grid)\n"
            "grid_points = np.column_stack([x_mesh.ravel(), y_mesh.ravel()])\n"
            "\n"
            "tree = cKDTree(df[['lon', 'lat']].values)\n"
            "distances, indices = tree.query(grid_points, k=10)\n"
            "distances = np.maximum(distances, 1e-10)\n"
            "weights = 1.0 / (distances ** 2)\n"
            "weights /= weights.sum(axis=1, keepdims=True)\n"
            "z_1d = np.sum(weights * df[target_col].values[indices], axis=1)\n"
            "\n"
            "geom = gdf_pays.geometry.unary_union\n"
            "mask_1d = contains(geom, grid_points[:, 0], grid_points[:, 1])\n"
            "z_2d = np.where(mask_1d, z_1d, np.nan).reshape(x_mesh.shape)\n"
            "z_2d = np.ma.masked_invalid(z_2d)\n"
            "\n"
            "niveaux = [-200, -100, -50, -25, 0, 25, 50, 100, 200]\n"
            "labels  = ['< -100 mm', '-100 a -50', '-50 a -25', '-25 a 0', '0 a 25', '25 a 50', '50 a 100', '> 100 mm']\n"
            "couleurs = ['#b2182b', '#d6604d', '#f4a582', '#fddbc7', '#d1e5f0', '#92c5de', '#4393c3', '#2166ac']\n"
            "cmap = ListedColormap(couleurs)\n"
            "norm = BoundaryNorm(niveaux, cmap.N)\n"
            "\n"
            "fig, ax = plt.subplots(figsize=(9, 11))\n"
            "ax.set_aspect('equal')\n"
            "gdf_pays.boundary.plot(ax=ax, color='black', linewidth=1.5)\n"
            "gdf_gouv.boundary.plot(ax=ax, color='grey', linestyle='--', linewidth=0.8)\n"
            "ax.contourf(x_mesh, y_mesh, z_2d, levels=niveaux, cmap=cmap, norm=norm, alpha=0.8, extend='both')\n"
            "cl = ax.contour(x_mesh, y_mesh, z_2d, levels=niveaux, colors='black', linewidths=0.5)\n"
            "ax.clabel(cl, inline=True, fontsize=8, fmt='%d mm')\n"
            "\n"
            "legend_elements = [Patch(facecolor=c, label=l) for c, l in zip(couleurs, labels)]\n"
            "ax.legend(handles=legend_elements, title='Evolution Pluie (mm)', loc='lower right', fontsize=8)\n"
            "ax.set_xlim(x_min, x_max); ax.set_ylim(y_min, y_max)\n"
            "ax.set_title(titre_carte, fontsize=14, fontweight='bold')\n"
            "ax.grid(True, linestyle='--', alpha=0.2)\n"
            "plt.tight_layout()\n"
            "plt.savefig('output_isohyete.png', dpi=300, bbox_inches='tight')\n"
            "plt.close()\n"
        )

    def _skeleton_anomalie(self) -> str:
        return (
            "import pandas as pd\n"
            "import numpy as np\n"
            "import geopandas as gpd\n"
            "import matplotlib.pyplot as plt\n"
            "from scipy.spatial import cKDTree\n"
            "from shapely.vectorized import contains\n"
            "from matplotlib.colors import ListedColormap, BoundaryNorm\n"
            "from matplotlib.patches import Patch\n"
            "import psycopg2\n"
            "import os\n"
            "\n"
            "conn = psycopg2.connect(os.environ['DATABASE_URL'])\n"
            "query = \"\"\"[requete_sql]\"\"\"\n"
            "df = pd.read_sql(query, conn)\n"
            "conn.close()\n"
            "df.columns = df.columns.str.lower()\n"
            "\n"
            "# Chargement des couches géographiques depuis PostGIS\n"
            "import sqlalchemy\n"
            "engine = sqlalchemy.create_engine(os.environ['DATABASE_URL'])\n"
            "gdf_pays = gpd.read_postgis('SELECT geom FROM limite_pays_polygon', engine, geom_col='geom').to_crs('EPSG:32632')\n"
            "gdf_gouv = gpd.read_postgis('SELECT lib_fr, geom FROM gouvernorats', engine, geom_col='geom').to_crs('EPSG:32632')\n"
            "\n"
            "target_col = '%'\n"
            "titre_carte = 'Anomalie Pluviometrique — Pourcentage de la Normale (%)'\n"
            "\n"
            "bounds = gdf_pays.total_bounds\n"
            "x_min, y_min, x_max, y_max = bounds\n"
            "margin = 20000\n"
            "x_min -= margin; x_max += margin; y_min -= margin; y_max += margin\n"
            "x_grid = np.arange(x_min, x_max, 2500)\n"
            "y_grid = np.arange(y_min, y_max, 2500)\n"
            "x_mesh, y_mesh = np.meshgrid(x_grid, y_grid)\n"
            "grid_points = np.column_stack([x_mesh.ravel(), y_mesh.ravel()])\n"
            "\n"
            "tree = cKDTree(df[['lon', 'lat']].values)\n"
            "distances, indices = tree.query(grid_points, k=10)\n"
            "distances = np.maximum(distances, 1e-10)\n"
            "weights = 1.0 / (distances ** 2)\n"
            "weights /= weights.sum(axis=1, keepdims=True)\n"
            "z_1d = np.sum(weights * df[target_col].values[indices], axis=1)\n"
            "\n"
            "geom = gdf_pays.geometry.unary_union\n"
            "mask_1d = contains(geom, grid_points[:, 0], grid_points[:, 1])\n"
            "z_2d = np.where(mask_1d, z_1d, np.nan).reshape(x_mesh.shape)\n"
            "z_2d = np.ma.masked_invalid(z_2d)\n"
            "\n"
            "niveaux = [0, 50, 75, 90, 110, 150, 300]\n"
            "labels  = ['< 50% (Deficit Severe)', '50-75% (Deficit)', '75-90% (Deficit Leger)',\n"
            "          '90-110% (Proche Normale)', '110-150% (Excedent)', '> 150% (Excedent Fort)']\n"
            "couleurs = ['#d73027', '#f46d43', '#fee090', '#ffffbf', '#abd9e9', '#4575b4']\n"
            "cmap = ListedColormap(couleurs)\n"
            "norm = BoundaryNorm(niveaux, cmap.N)\n"
            "\n"
            "fig, ax = plt.subplots(figsize=(9, 11))\n"
            "ax.set_aspect('equal')\n"
            "gdf_pays.boundary.plot(ax=ax, color='black', linewidth=1.5)\n"
            "gdf_gouv.boundary.plot(ax=ax, color='grey', linestyle='--', linewidth=0.8)\n"
            "ax.contourf(x_mesh, y_mesh, z_2d, levels=niveaux, cmap=cmap, norm=norm, alpha=0.8, extend='both')\n"
            "cl = ax.contour(x_mesh, y_mesh, z_2d, levels=niveaux, colors='black', linewidths=0.5)\n"
            "ax.clabel(cl, inline=True, fontsize=8, fmt='%d %%')\n"
            "\n"
            "legend_elements = [Patch(facecolor=c, label=l) for c, l in zip(couleurs, labels)]\n"
            "ax.legend(handles=legend_elements, title='Normale Pluviometrique', loc='lower right', fontsize=8)\n"
            "ax.set_xlim(x_min, x_max); ax.set_ylim(y_min, y_max)\n"
            "ax.set_title(titre_carte, fontsize=14, fontweight='bold')\n"
            "ax.grid(True, linestyle='--', alpha=0.2)\n"
            "plt.tight_layout()\n"
            "plt.savefig('output_isohyete.png', dpi=300, bbox_inches='tight')\n"
            "plt.close()\n"
        )

    def _skeleton_stations_density(self) -> str:
        return (
            "import pandas as pd\n"
            "import numpy as np\n"
            "import geopandas as gpd\n"
            "import matplotlib.pyplot as plt\n"
            "from matplotlib.colors import ListedColormap, BoundaryNorm\n"
            "from matplotlib.patches import Patch\n"
            "import psycopg2\n"
            "import os\n"
            "\n"
            "conn = psycopg2.connect(os.environ['DATABASE_URL'])\n"
            "query = \"\"\"[requete_sql]\"\"\"\n"
            "df = pd.read_sql(query, conn)\n"
            "conn.close()\n"
            "df.columns = df.columns.str.lower()\n"
            "\n"
            "# Chargement des couches géographiques depuis PostGIS\n"
            "import sqlalchemy\n"
            "engine = sqlalchemy.create_engine(os.environ['DATABASE_URL'])\n"
            "gdf_pays = gpd.read_postgis('SELECT geom FROM limite_pays_polygon', engine, geom_col='geom').to_crs('EPSG:32632')\n"
            "gdf_gouv = gpd.read_postgis('SELECT lib_fr, geom FROM gouvernorats', engine, geom_col='geom').to_crs('EPSG:32632')\n"
            "\n"
            "gdf_stations = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df['x'], df['y']), crs=\"EPSG:32632\")\n"
            "titre_carte = 'Reseau Pluviometrique — Implantation et Precipitations Annuelles (mm)'\n"
            "\n"
            "niveaux = [0, 100, 200, 300, 500, 700, 1000, 1500]\n"
            "labels  = ['<100 mm', '100-200', '200-300', '300-500', '500-700', '700-1000', '>1000 mm']\n"
            "couleurs = ['#d73027', '#fc8d59', '#fee090', '#e0f3f8', '#91bfdb', '#4575b4', '#313695']\n"
            "cmap = ListedColormap(couleurs)\n"
            "norm = BoundaryNorm(niveaux, cmap.N)\n"
            "\n"
            "fig, ax = plt.subplots(figsize=(9, 11))\n"
            "ax.set_aspect('equal')\n"
            "\n"
            "gdf_pays.plot(ax=ax, color='#f5f5f0', edgecolor='black', linewidth=1.5, zorder=1)\n"
            "gdf_gouv.boundary.plot(ax=ax, color='grey', linestyle='--', linewidth=0.6, zorder=2)\n"
            "\n"
            "sc = ax.scatter(df['lon'], df['lat'], c=df['total'], cmap=cmap, norm=norm, s=40, \n"
            "                edgecolor='black', linewidth=0.8, alpha=0.9, zorder=3, label='Stations')\n"
            "\n"
            "cbar = plt.colorbar(sc, ax=ax, orientation='vertical', pad=0.03, shrink=0.75, extend='max')\n"
            "cbar.set_label('Precipitations Annuelles Totales (mm)', fontsize=10, fontweight='bold')\n"
            "cbar.ax.tick_params(labelsize=8)\n"
            "\n"
            "bounds = gdf_pays.total_bounds\n"
            "margin = 15000\n"
            "ax.set_xlim(bounds[0] - margin, bounds[2] + margin)\n"
            "ax.set_ylim(bounds[1] - margin, bounds[3] + margin)\n"
            "ax.set_title(titre_carte, fontsize=13, fontweight='bold')\n"
            "ax.grid(True, linestyle='--', alpha=0.3)\n"
            "plt.tight_layout()\n"
            "plt.savefig('output_isohyete.png', dpi=300, bbox_inches='tight')\n"
            "plt.close()\n"
        )
