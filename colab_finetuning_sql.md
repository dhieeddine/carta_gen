# Fine-tuning du Modèle SQL/SIG pour CartaGen (Google Colab)

Ce document contient les cellules de code à copier-coller dans votre notebook Google Colab pour générer le jeu de données d'entraînement SQL (avec les nouveaux noms de colonnes `x` et `y`) et lancer le fine-tuning (LoRA) de votre modèle existant.

---

## Cellule 1 : Installation des dépendances et montage de Google Drive

```python
!pip install -q -U "unsloth[colab] @ git+https://github.com/unslothai/unsloth.git"
!pip install -q -U trl peft accelerate bitsandbytes datasets

from google.colab import drive
drive.mount('/content/drive')
```

---

## Cellule 2 : Importation des Datasets (Train & Eval) dans Google Drive

**⚠️ Action Manuelle Requise :**
Pour éviter de perdre vos fichiers à chaque fois que Colab redémarre, vous avez choisi de les stocker sur votre Google Drive.

Veuillez ouvrir votre **Google Drive** personnel, créer un dossier nommé **`Cartagen`** (à la racine), et y **importer (uploader)** les deux fichiers générés sur votre ordinateur (`d:\Desktop\stage_dgre\carta_gen\`) :
1. `dataset_train.jsonl`
2. `dataset_eval.jsonl`

Une fois les fichiers copiés sur Drive, passez à la cellule suivante.

---

## Cellule 3 : Chargement du Modèle et Préparation des Données (Unsloth)

Ici, nous allons charger le modèle (les poids LoRA existants si vous continuez l'entraînement, ou le modèle de base pour appliquer un nouveau LoRA).

```python
from unsloth import FastLanguageModel
import torch
from datasets import load_dataset

# Configuration
max_seq_length = 2048 # Adaptez selon votre VRAM
dtype = None # Auto-détection (Float16/Bfloat16)
load_in_4bit = True # 4bit pour économiser la VRAM

# --- OPTION A : Charger le modèle de base (Llama 3, Mistral, etc.) ---
# model_name = "unsloth/llama-3-8b-Instruct-bnb-4bit" 

# --- OPTION B : Charger vos poids pré-entraînés depuis Drive ---
model_name = "/content/drive/My Drive/CartaGen_LoRA" 

model, tokenizer = FastLanguageModel.from_pretrained(
    model_name = model_name,
    max_seq_length = max_seq_length,
    dtype = dtype,
    load_in_4bit = load_in_4bit,
)

# Configuration de LoRA
model = FastLanguageModel.get_peft_model(
    model,
    r = 16, 
    target_modules = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    lora_alpha = 16,
    lora_dropout = 0,
    bias = "none",
    use_gradient_checkpointing = "unsloth",
    random_state = 3407,
    use_rslora = False,
)

# Fonction de formatage ChatML pour l'entraînement
def format_chat_template(examples):
    formatted_texts = []
    for messages in examples["messages"]:
        text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=False)
        formatted_texts.append(text)
    return {"text": formatted_texts}

# Chargement des datasets d'entraînement (90%) et d'évaluation (10%) depuis Google Drive
dataset_train = load_dataset("json", data_files="/content/drive/My Drive/Cartagen/dataset_train.jsonl", split="train")
dataset_train = dataset_train.map(format_chat_template, batched=True)

dataset_eval = load_dataset("json", data_files="/content/drive/My Drive/Cartagen/dataset_eval.jsonl", split="train")
dataset_eval = dataset_eval.map(format_chat_template, batched=True)
```

---

## Cellule 4 : Lancement du Fine-Tuning

```python
from trl import SFTTrainer
from transformers import TrainingArguments
from unsloth import is_bfloat16_supported

trainer = SFTTrainer(
    model = model,
    tokenizer = tokenizer,
    train_dataset = dataset_train,
    eval_dataset = dataset_eval, # Le dataset de 10% pour évaluer l'overfitting
    dataset_text_field = "text",
    max_seq_length = max_seq_length,
    dataset_num_proc = 2,
    packing = False, 
    args = TrainingArguments(
        per_device_train_batch_size = 2,
        gradient_accumulation_steps = 4,
        warmup_steps = 5,
        max_steps = 150, 
        learning_rate = 2e-4,
        fp16 = not is_bfloat16_supported(),
        bf16 = is_bfloat16_supported(),
        logging_steps = 10,
        eval_strategy = "steps", # <-- CORRECTION : 'eval_strategy' remplace l'ancien 'evaluation_strategy'
        eval_steps = 10,               # Fréquence d'évaluation
        optim = "adamw_8bit",
        weight_decay = 0.01,
        lr_scheduler_type = "linear",
        seed = 3407,
        output_dir = "outputs",
        save_strategy = "no", # <-- CORRECTION : 'no' est la valeur valide pour désactiver la sauvegarde
    ),
)

trainer_stats = trainer.train()
```

---

## Cellule 5 : Sauvegarde des nouveaux poids fusionnés dans Google Drive

```python
save_path = "/content/drive/My Drive/CartaGen_LoRA_SQL_SIG"

# Sauvegarde des adaptateurs LoRA
model.save_pretrained(save_path)
tokenizer.save_pretrained(save_path)

print(f"Modèle sauvegardé avec succès dans {save_path}")

# (Optionnel) Si vous voulez fusionner les poids LoRA avec le modèle de base (Merge to 16bit)
# model.save_pretrained_merged(f"{save_path}_merged", tokenizer, save_method = "merged_16bit")
```

---

## Cellule 6 : Tester la génération SQL (Agent de Données)

Cette cellule utilise le prompt d'instruction SQL. Le modèle doit renvoyer uniquement un objet JSON contenant la requête SQL avec les colonnes `x` et `y`.

```python
FastLanguageModel.for_inference(model)

prompt_system_sql = (
    "Tu es un traducteur de langage naturel vers PostgreSQL/PostGIS expert pour les ressources en eau de la Tunisie (DGRE).\n"
    "Renvoie UNIQUEMENT un objet JSON valide avec exactement deux clés : 'sql_query' et 'target_col'. Sans explication.\n\n"
    "=== TABLES DISPONIBLES ===\n"
    "1. ann_stations : id_station, nom, gouvernorat, y, x, altitude, bassin.\n"
    "2. ann_pluies : id_station, gouvernorat, date_obs, valeur_mm.\n\n"
    "=== RÈGLE ABSOLUE ===\n"
    "- Pluies/isohyètes → TOUJOURS ann_pluies + ann_stations.\n"
    "- Inclure TOUJOURS : AND s.y IS NOT NULL AND s.x IS NOT NULL."
)

requete_sql = "Pluie d'avril 2023"

inputs = tokenizer.apply_chat_template([
    {"role": "system", "content": prompt_system_sql},
    {"role": "user", "content": requete_sql}
], tokenize=True, add_generation_prompt=True, return_tensors="pt").to("cuda")

outputs = model.generate(input_ids=inputs, max_new_tokens=512, use_cache=True, temperature=0.1)
print("=== RÉSULTAT TEST SQL ===")
print(tokenizer.decode(outputs[0][inputs.shape[1]:], skip_special_tokens=True))
```

---

## Cellule 7 : Tester la génération de code Python (Agent SIG)

Cette cellule reproduit l'injection du SQL dans le prompt de l'Agent SIG, exactement comme le fait votre application CartaGen. Le modèle doit générer un script Python complet utilisant `y` et `x`.

```python
prompt_system_sig = "Tu es un expert SIG Python/PostGIS pour la DGRE Tunisie. Génère du code Python exécutable, autonome et ultra-optimisé pour les cartes isohyètes."

requete_sig = "Carte des pluies en avril 2023"
sql_simule = "SELECT s.id_station, s.nom AS station, s.y, s.x, SUM(p.valeur_mm) AS pluie_avr_2023 FROM ann_pluies p JOIN ann_stations s ON p.id_station = s.id_station AND p.gouvernorat = s.gouvernorat WHERE EXTRACT(MONTH FROM p.date_obs) = 4 AND EXTRACT(YEAR FROM p.date_obs) = 2023 AND s.y IS NOT NULL AND s.x IS NOT NULL GROUP BY p.id_station, s.nom, s.y, s.x;"

prompt_user_injecte = (
    "Tu disposes de la requête SQL d'extraction suivante pour charger les données pluviométriques depuis PostgreSQL :\n"
    "```sql\n"
    f"{sql_simule}\n"
    "```\n"
    "Les couches géographiques (limite_pays_polygon, gouvernorats, rgion_hydrographique) doivent être chargées directement depuis la base de données PostGIS avec gpd.read_postgis(). Ne lis aucun fichier shapefile (.shp) sur le disque.\n\n"
    "Utilise ce code de masquage ultra-rapide:\n"
    "# OPTIMISATION : Simplification de la géométrie pour masquage instantané (0.1s)\n"
    "geom_simplified = gdf_pays.geometry.unary_union.simplify(100, preserve_topology=True)\n"
    "mask_1d = contains(geom_simplified, grid_points[:, 0], grid_points[:, 1])\n\n"
    "### Contraintes :\n"
    "- Écris UNIQUEMENT du code Python complet\n"
    "- Utilise plt.savefig('output_isohyete.png', dpi=300, bbox_inches='tight')\n"
    "- Utilise plt.close() à la fin\n\n"
    f"Requête utilisateur d'origine : {requete_sig}"
)

inputs_sig = tokenizer.apply_chat_template([
    {"role": "system", "content": prompt_system_sig},
    {"role": "user", "content": prompt_user_injecte}
], tokenize=True, add_generation_prompt=True, return_tensors="pt").to("cuda")

outputs_sig = model.generate(input_ids=inputs_sig, max_new_tokens=2048, use_cache=True, temperature=0.1)
print("=== RÉSULTAT TEST SIG (CODE PYTHON) ===")
print(tokenizer.decode(outputs_sig[0][inputs_sig.shape[1]:], skip_special_tokens=True))
```

---

## Cellule 8 : Le "Stress Test" (Généralisation sur un cas extrême)

Cette cellule vérifie si le modèle s'est contenté d'apprendre les dates par cœur (Overfitting) ou s'il a vraiment compris la logique spatio-temporelle. Nous allons lui demander une prédiction pour **l'année 2050** (qui n'existe absolument pas dans le jeu de données d'entraînement). 

```python
requete_extreme = "Je veux la carte des précipitations pour le mois de décembre 2050"

# Testons l'Agent SQL sur ce cas extrême
inputs_extreme = tokenizer.apply_chat_template([
    {"role": "system", "content": prompt_system_sql},
    {"role": "user", "content": requete_extreme}
], tokenize=True, add_generation_prompt=True, return_tensors="pt").to("cuda")

outputs_extreme = model.generate(input_ids=inputs_extreme, max_new_tokens=512, use_cache=True, temperature=0.1)

print("=== STRESS TEST SQL (Année 2050) ===")
resultat_extreme = tokenizer.decode(outputs_extreme[0][inputs_extreme.shape[1]:], skip_special_tokens=True)
print(resultat_extreme)

print("\n=== VÉRIFICATION DU RÉSULTAT ===")
if "2050" in resultat_extreme and "12" in resultat_extreme:
    print("✅ SUCCÈS : Le modèle a parfaitement généralisé ! Il a compris l'année 2050 et le mois 12.")
else:
    print("❌ ÉCHEC : Le modèle fait de l'overfitting. Il n'a pas su adapter la date.")
```
