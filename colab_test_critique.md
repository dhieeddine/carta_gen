# 🧪 Batterie de Tests Critiques (Stress Tests) pour Colab

Pour identifier précisément les faiblesses actuelles de votre modèle (afin d'enrichir votre `dataset_mixed.jsonl` plus tard), copiez-collez cette grande cellule à la fin de votre Google Colab. 

Ce script va envoyer des requêtes "pièges" aux deux agents (SQL et SIG) et analyser automatiquement leur code pour voir s'ils tombent dans les pièges classiques.

```python
import json

print("🚀 DÉMARRAGE DE LA BATTERIE DE TESTS CRITIQUES...")

# ==========================================
# 1. TESTS DE L'AGENT SQL (Logique Métier)
# ==========================================
cas_sql = [
    ("Saison (Inconnu du dataset)", "Je veux les isohyètes de l'été 2022"),
    ("Plage de temps (Complexe)", "Précipitations cumulées entre 2020 et 2023"),
    ("Filtre Spatial", "Carte des pluies du mois de janvier 2021 uniquement pour le gouvernorat de Tunis")
]

print("\n📊 --- ÉVALUATION AGENT SQL ---")
for nom, requete in cas_sql:
    inputs = tokenizer.apply_chat_template([
        {"role": "system", "content": prompt_system_sql},
        {"role": "user", "content": requete}
    ], tokenize=True, add_generation_prompt=True, return_tensors="pt").to("cuda")
    
    out = model.generate(input_ids=inputs, max_new_tokens=512, use_cache=True, temperature=0.1)
    resultat = tokenizer.decode(out[0][inputs.shape[1]:], skip_special_tokens=True)
    
    print(f"\n🔹 TEST : {nom}")
    print(f"Requête : '{requete}'")
    try:
        data = json.loads(resultat)
        sql = data.get("sql_query", "")
        
        # Vérifications
        erreurs = []
        if "s.y IS NOT NULL" not in sql: erreurs.append("Oubli du filtre IS NOT NULL")
        if "GROUP BY s.id_station" not in sql and "GROUP BY p.id_station" in sql: erreurs.append("Erreur d'alias GROUP BY (p.id_station au lieu de s.id_station)")
        
        if erreurs:
            print(f"❌ ÉCHEC : {erreurs}")
        else:
            print(f"✅ SUCCÈS (JSON valide et logique SQL robuste)")
            
    except json.JSONDecodeError:
        print("❌ ÉCHEC CRITIQUE : Le modèle n'a pas retourné un JSON valide.")


# ==========================================
# 2. TESTS DE L'AGENT SIG (Syntaxe Numpy)
# ==========================================
print("\n🗺️ --- ÉVALUATION AGENT SIG ---")

requete_sig = "Génère une carte pour avril 2023"
sql_simule = "SELECT s.id_station, s.nom AS station, s.y, s.x, SUM(p.valeur_mm) AS pluie_avr_2023 FROM ann_pluies p JOIN ann_stations s ON p.id_station = s.id_station WHERE EXTRACT(MONTH FROM p.date_obs) = 4 AND EXTRACT(YEAR FROM p.date_obs) = 2023 AND s.y IS NOT NULL AND s.x IS NOT NULL GROUP BY s.id_station, s.nom, s.y, s.x;"

prompt_user_injecte = (
    "Tu disposes de la requête SQL d'extraction suivante :\n"
    f"```sql\n{sql_simule}\n```\n"
    "Les couches (limite_pays_polygon, gouvernorats, rgion_hydrographique) doivent être chargées depuis PostGIS avec gpd.read_postgis(). "
    "Utilise ce code de masquage ultra-rapide:\n"
    "geom_simplified = gdf_pays.geometry.unary_union.simplify(100, preserve_topology=True)\n"
    "mask_1d = contains(geom_simplified, grid_points[:, 0], grid_points[:, 1])\n\n"
    "Contraintes : Écris UNIQUEMENT du code Python complet. Termine par plt.savefig() et plt.close().\n"
    f"Requête utilisateur d'origine : {requete_sig}"
)

inputs_sig = tokenizer.apply_chat_template([
    {"role": "system", "content": prompt_system_sig},
    {"role": "user", "content": prompt_user_injecte}
], tokenize=True, add_generation_prompt=True, return_tensors="pt").to("cuda")

out_sig = model.generate(input_ids=inputs_sig, max_new_tokens=2048, use_cache=True, temperature=0.1)
code_python = tokenizer.decode(out_sig[0][inputs_sig.shape[1]:], skip_special_tokens=True)

print("\n🔹 TEST : Robustesse de la syntaxe Python (Interpolation IDW)")
erreurs_sig = []
if "np.meshgrid" not in code_python: erreurs_sig.append("Oubli de np.meshgrid pour la grille 2D.")
if "axis=1" not in code_python: erreurs_sig.append("Oubli de axis=1 dans les calculs numpy.sum().")
if "[indices]" not in code_python: erreurs_sig.append("Oubli du filtre [indices] pour l'IDW.")
if "subset=" in code_python and "masked_invalid" in code_python: erreurs_sig.append("Hallucination de subset='all' dans masked_invalid().")
if "plt.close()" not in code_python: erreurs_sig.append("Oubli de plt.close() -> Fuite de RAM.")
if "p.id_station" in code_python and "GROUP BY s.id_station" not in code_python: erreurs_sig.append("Mauvais alias SQL généré dans le Python.")

if erreurs_sig:
    print("❌ FAIBLESSES DÉTECTÉES (À corriger dans le futur Dataset) :")
    for e in erreurs_sig:
        print(f"  - {e}")
else:
    print("✅ CODE PYTHON PARFAIT ! Aucune hallucination détectée.")
```
