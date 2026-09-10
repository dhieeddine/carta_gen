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
        if self.provider_manager is None:
            try:
                from cartagen.infrastructure.providers.provider_manager import ProviderManager
                self.provider_manager = ProviderManager(os.getcwd())
            except Exception:
                self.provider_manager = None

        self.llm_provider = os.getenv("LLM_PROVIDER", "openrouter").lower()
        self.last_system_prompt = ""
        self.last_user_prompt = ""
        self.last_response = ""
        self.last_correction_system_prompt = ""
        self.last_correction_user_prompt = ""
        self.last_correction_response = ""

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
                    "- region_naturelle (si l'utilisateur demande la carte des régions naturelles, la délimitation Nord/Centre/Sud, les 6 régions)\n"
                    "- mono (pour toute carte d'isohyètes standard pays ou région)\n\n"
                    "Ne réponds rien d'autre que ce mot unique."
                )
                res = self.provider_manager.call_llm_api(
                    provider_id=self.llm_provider,
                    prompt=f"Classification d'intention pour : '{prompt}'",
                    system_prompt=system_prompt
                ).strip().lower()
                
                # Extraire le premier mot clé valide
                valid_types = ["analysis", "multi_season", "compare_gouv", "single_gouv", "region_hydro", "difference", "anomalie", "stations_density", "region_naturelle", "mono"]
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
        if any(k in low for k in ["région naturelle", "region naturelle", "régions naturelles", "regions naturelles",
                "delimitation", "délimitation", "6 régions", "6 regions",
                "nord ouest", "nord est", "centre ouest", "centre est", "sud ouest", "sud est"]):
            return "region_naturelle"
        return "mono"

    def _get_skeleton(self, ptype: str) -> str:
        """Retourne le squelette de code Python associé au type de prompt.
        
        Charge le squelette depuis les fichiers .py.template du dossier skeletons/.
        """
        from cartagen.infrastructure.agents.skeletons.skeleton_loader import load_skeleton
        # multi_season utilise le squelette mono (pas de template dédié)
        skeleton_name = "mono" if ptype == "multi_season" else ptype
        try:
            return load_skeleton(skeleton_name)
        except FileNotFoundError:
            return load_skeleton("mono")

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

        # Types déterministes : exécution directe du squelette sans appel LLM
        DETERMINISTIC_TYPES = {"region_naturelle"}
        if ptype in DETERMINISTIC_TYPES:
            print(f"[SIG Agent] Type déterministe '{ptype}' : exécution directe du squelette (bypass LLM)")
            self.last_system_prompt = f"Squelette déterministe ({ptype})"
            self.last_user_prompt = prompt
            self.last_response = skeleton
            return skeleton

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
            if not self.provider_manager:
                raise RuntimeError("ProviderManager non configuré pour l'appel LLM de SIGGeneratorAgent.")

            raw = self.provider_manager.call_llm_api(self.llm_provider, api_prompt)
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
            if not self.provider_manager:
                raise RuntimeError("ProviderManager non configuré pour l'appel LLM de SIGGeneratorAgent.")

            raw = self.provider_manager.call_llm_api(self.llm_provider, task)
            self.last_response = raw
            return self._clean_code(raw)

        # Mode local correction

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

    # Les squelettes de code SIG (mono, analysis, single_gouv, compare_gouv,
    # region_hydro, difference, anomalie, stations_density, region_naturelle)
    # sont désormais chargés depuis les fichiers .py.template du dossier :
    # cartagen/infrastructure/agents/skeletons/
