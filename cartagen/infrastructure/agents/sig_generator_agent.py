# -*- coding: utf-8 -*-

import os
import time
import json
import requests
from typing import Dict, Any
from cartagen.infrastructure.database.postgres_connection import PostgresConnectionManager

class SIGGeneratorAgent:
    """Agent chargé de générer le code Python géospatiale robuste en s'appuyant sur des APIs Cloud ou VisCoder2-7B local."""

    def __init__(self, hf_token: str, db_manager: PostgresConnectionManager):
        self.hf_token = hf_token
        self.db_manager = db_manager
        
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
        
        self.model_name = "TIGER-Lab/VisCoder2-7B"
        self.tokenizer = None
        self.model = None
        
        # Identification des caractéristiques des tables
        self.gouv_col = "lib_fr"  # Colonne nom français dans la table gouvernorats
        self.reg_col  = "lib_fr"  # Colonne nom français dans la table rgion_hydrographique

    def initialize_model(self):
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

    def detect_prompt_type(self, prompt: str) -> str:
        """Détecte le type d'isohyète demandé pour aiguiller vers le bon squelette."""
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

    def generate_code(self, prompt: str, sql_query: str, vector_context: Dict[str, Any] = None) -> str:
        """Génère le code Python complet en associant le prompt, la requête SQL et le squelette."""
        self.initialize_model()

        ptype = self.detect_prompt_type(prompt)
        skeleton = self._get_skeleton(ptype)

        # RAG Vector Context Formatting
        rag_context = ""
        if vector_context:
            rag_context += "\n### Contexte de recherche sémantique (Zvec Vector DB) :\n"
            if "stations" in vector_context and vector_context["stations"]:
                rag_context += "- Stations similaires trouvées dans la base de données :\n"
                for station in vector_context["stations"]:
                    rag_context += f"  * Nom: {station['nom']} (ID: {station['id_station']}) [Score de similarité: {station['score']:.4f}]\n"
            if "schemas" in vector_context and vector_context["schemas"]:
                rag_context += "- Tables de données et schémas pertinents :\n"
                for schema in vector_context["schemas"]:
                    rag_context += f"  * Table: {schema['table_name']} -> {schema['description']} [Score: {schema['score']:.4f}]\n"

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

{rag_context}
"""
            constraints = (
                "### Contraintes de programmation (IMPÉRATIVES) :\n"
                "- Écris UNIQUEMENT du code Python complet et exécutable, sans explications.\n"
                "- Le code doit être autonome (tous les imports inclus).\n"
                "- Charge TOUTES les couches géographiques depuis la base de données PostGIS avec gpd.read_postgis(). Ne lis pas de fichiers shapefiles sur le disque.\n"
                "- Utilise la fonction d'extraction SQL fournie pour remplir le DataFrame.\n"
                "- Reprojette toutes les couches géographiques vers EPSG:32632 dès le chargement.\n"
                "- Effectue l'IDW et le masquage en 1D. Reshape en 2D uniquement pour contourf.\n"
                "- N'utilise JAMAIS Point() de shapely. Utilise gpd.points_from_xy() à la place.\n"
                "- Applique np.ma.masked_invalid(z_2d) après le reshape.\n"
                "- Trace les limites des gouvernorats avec gdf_gouv_all.boundary.plot(ax=ax, ...) uniquement.\n"
                "- Ne fais jamais d'appel à boundary.plot() sur un GeoDataFrame de points (comme les stations).\n"
                "- Si tu utilises une colorbar avec des niveaux discrets, assure-toi que le nombre de labels correspond exactement au nombre de ticks/niveaux ou utilise ax.legend() avec des Patches.\n"
                "- Sauvegarde la figure en utilisant plt.savefig('output_isohyete.png', dpi=300, bbox_inches='tight').\n"
                "- Utilise plt.close() à la fin.\n\n"
            )

        # Aiguillage selon le provider choisi (on passe un prompt épuré sans balises ChatML)
        if self.llm_provider in ["groq", "openai", "ollama", "openrouter"]:
            api_prompt = (
                f"{context}\n\n"
                f"### Instruction :\n{prompt}\n\n"
                + constraints
                + "### SQUELETTE DE CODE À SUIVRE OBLIGATOIREMENT :\n"
                "```python\n"
                + skeleton
                + "\n```"
            )
            if self.llm_provider == "groq":
                return self._call_groq_api(api_prompt)
            elif self.llm_provider == "openai":
                return self._call_openai_api(api_prompt)
            elif self.llm_provider == "ollama":
                return self._call_ollama_api(api_prompt)
            elif self.llm_provider == "openrouter":
                return self._call_openrouter_api(api_prompt)

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
        return self._clean_code(raw_output)

    def generate_correction(self, code: str, error: str) -> str:
        """Génère un code corrigé à partir d'un code ayant échoué et de son exception."""
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
        
        hint_block = "\n".join(hints) if hints else ""

        task = f"""Le code généré a échoué avec l'erreur :
---
{error}
---
Code d'origine :
```python
{code}
```
{hint_block}

Corrige le code et retourne UNIQUEMENT le code corrigé, complet et autonome, sans explications.
"""

        # Aiguillage pour correction via API Cloud
        if self.llm_provider in ["groq", "openai", "ollama", "openrouter"]:
            if self.llm_provider == "groq":
                return self._call_groq_api(task)
            elif self.llm_provider == "openai":
                return self._call_openai_api(task)
            elif self.llm_provider == "ollama":
                return self._call_ollama_api(task)
            elif self.llm_provider == "openrouter":
                return self._call_openrouter_api(task)

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
        """Appelle Ollama localement."""
        url = f"{self.ollama_url}/api/generate"
        payload = {
            "model": self.ollama_model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.1
            }
        }
        res = requests.post(url, json=payload, timeout=45)
        res.raise_for_status()
        return self._clean_code(res.json()["response"])

    def _clean_code(self, text: str) -> str:
        if "```python" in text:
            return text.split("```python")[1].split("```")[0].strip()
        if "```" in text:
            return text.split("```")[1].strip()
        return text.strip()

    # Définition des squelettes d'injection (Mono, Single Gouv, etc.)
    def _skeleton_mono(self) -> str:
        return (
            "import pandas as pd\n"
            "import numpy as np\n"
            "import geopandas as gpd\n"
            "import matplotlib.pyplot as plt\n"
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
            "\n"
            "target_col = '[colonne_cible]'\n"
            "titre_carte = '[titre_carte]'\n"
            "\n"
            "# 3. Nettoyage des données\n"
            "df = df.dropna(subset=[target_col])\n"
            "df = df.reset_index(drop=True)\n"
            "if df.empty:\n"
            "    raise ValueError(f\"Aucune donn\u00e9e disponible pour la colonne '{target_col}'\")\n"
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
            "fig, ax = plt.subplots(figsize=(9, 11))\n"
            "ax.set_aspect('equal')\n"
            "gdf_pays.boundary.plot(ax=ax, color='black', linewidth=1.5)\n"
            "gdf_gouv.boundary.plot(ax=ax, color='grey', linestyle='--', linewidth=0.8)\n"
            "ax.contourf(x_mesh, y_mesh, z_2d, levels=niveaux, cmap=cmap, norm=norm, alpha=0.7, extend='max')\n"
            "cl = ax.contour(x_mesh, y_mesh, z_2d, levels=niveaux, colors='black', linewidths=0.6)\n"
            "ax.clabel(cl, inline=True, fontsize=8, fmt='%d mm')\n"
            "legend_elements = [Patch(facecolor=c, label=l) for c, l in zip(couleurs, labels)]\n"
            "ax.legend(handles=legend_elements, title='Précipitations', loc='lower right', fontsize=9)\n"
            "ax.set_xlim(bounds[0] - margin, bounds[2] + margin)\n"
            "ax.set_ylim(bounds[1] - margin, bounds[3] + margin)\n"
            "ax.set_title(titre_carte, fontsize=13, fontweight='bold')\n"
            "ax.grid(True, linestyle='--', alpha=0.3)\n"
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
            "# TODO : Écrire le traitement pandas pour filtrer les colonnes nécessaires selon le prompt\n"
            "# TODO : Générer l'histogramme, courbe ou diagramme demandé\n"
            "# TODO : Sauvegarder la figure avec : plt.savefig('output_isohyete.png', dpi=300, bbox_inches='tight')\n"
            "# TODO : Sauvegarder le tableau de données si pertinent avec : df_result.to_html('output_table.html', index=False, classes='analysis-table')\n"
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
            "df = df.dropna(subset=[target_col])\n"
            "df = df.reset_index(drop=True)\n"
            "if df.empty:\n"
            "    raise ValueError(f\"Aucune donnée disponible pour la colonne '{target_col}'\")\n"
            "\n"
            "# 5. Filtrage spatial des stations dans le gouvernorat\n"
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
            "gdf_gouv_all.boundary.plot(ax=ax, color='lightgrey', linestyle='--', linewidth=0.6)\n"
            "gdf_pays.boundary.plot(ax=ax, color='black', linewidth=1.5)\n"
            "gdf_cible.boundary.plot(ax=ax, color='black', linewidth=2.0)\n"
            "\n"
            "if not np.all(np.isnan(z_2d)):\n"
            "    ax.contourf(x_mesh, y_mesh, z_2d, levels=niveaux, cmap=cmap, norm=norm, alpha=0.75, extend='max')\n"
            "    cl = ax.contour(x_mesh, y_mesh, z_2d, levels=niveaux, colors='black', linewidths=0.7)\n"
            "    ax.clabel(cl, inline=True, fontsize=8, fmt='%d mm')\n"
            "\n"
            "ax.scatter(df_stations_cible['x'], df_stations_cible['y'], s=25, color='red', edgecolor='black', zorder=5, label='Stations')\n"
            "legend_elements = [Patch(facecolor=c, label=l) for c, l in zip(couleurs, labels)]\n"
            "ax.legend(handles=legend_elements, title='Précipitations', loc='lower right', fontsize=8)\n"
            "ax.set_xlim(x_min, x_max); ax.set_ylim(y_min, y_max)\n"
            "ax.set_title(titre_carte, fontsize=14, fontweight='bold')\n"
            "ax.grid(True, linestyle='--', alpha=0.3)\n"
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
