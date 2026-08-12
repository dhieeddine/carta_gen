# Explication de la Méthode des Polygones de Thiessen (Voronoi) dans CartaGen

Ce document explique le principe théorique, la mise en œuvre algorithmique et l'utilisation de la **méthode des polygones de Thiessen** dans le système **CartaGen** de la Direction Générale des Ressources en Eau (DGRE).

---

## 🎯 1. Pourquoi la Méthode de Thiessen ?

En hydrologie et en météorologie, les pluviomètres fournissent des mesures ponctuelles de précipitation en un point précis (ex: station météo).
Cependant, pour évaluer la quantité d'eau totale tombée sur un bassin versant, un gouvernorat ou l'ensemble du territoire national, une **moyenne arithmétique simple est biaisée** car :
1. Les stations météo ne sont pas réparties de manière parfaitement uniforme sur le territoire.
2. Une région avec une forte densité de stations influencerait trop le résultat si toutes les stations avaient le même poids.

La **méthode des polygones de Thiessen (ou Voronoi)** résout ce problème en attribuant à chaque station une **surface d'influence géométrique (pondération spatiale)**.

---

## 📐 2. Principe Mathématique et Algorithmique

### A. Découpage du Territoire en Polygones de Voronoi
Pour chaque station pluviométrique $i$ localisée en $(x_i, y_i)$ :
1. On trace les médiatrices des segments reliant la station $i$ à toutes les stations voisines.
2. L'intersection de ces médiatrices forme un **polygone $P_i$** autour de la station.
3. **Propriété fondamentale** : Tout point situé à l'intérieur du polygone $P_i$ est plus proche de la station $i$ que de n'importe quelle autre station du réseau.

### B. Découpage et Intersection avec les Frontières Administratives
Dans CartaGen, chaque polygone de Thiessen $P_i$ est découpé (`intersection`) par les frontières officielles PostGIS :
- **À l'échelle nationale** : Découpage par la limite du pays (`limite_pays_polygon`).
- **À l'échelle régionale** : Découpage par les frontières naturelles (Nord-Ouest, Nord-Est, Centre-Ouest, Centre-Est, Sud-Ouest, Sud-Est).

### C. Calcul du Poids Rélatif ($W_i$)
Pour chaque station $i$, son poids relatif $W_i$ sur une zone $Z$ de surface totale $S_Z$ est calculé par :

$$W_i = \frac{\text{Surface}(P_i \cap Z)}{S_Z}$$

Avec la contrainte de normalisation :

$$\sum_{i=1}^{N} W_i = 1 \quad (100\%)$$

---

## 💻 3. Implémentation dans CartaGen (`generer_annuaire_database.py`)

La fonction `get_thiessen_weights()` prend en charge le calcul automatique des polygones et des poids :

```python
# 1. Construction des points géométriques en UTM Zone 32N (EPSG:32632)
df_st['geom'] = df_st.apply(lambda r: Point(r['lon'], r['lat']), axis=1)
gdf_st = gpd.GeoDataFrame(df_st, geometry='geom', crs="EPSG:32632")

# 2. Génération du diagramme de Voronoi
mp = MultiPoint(gdf_st['geom'].tolist())
vor = voronoi_diagram(mp, envelope=boundary.envelope.buffer(100000))

# 3. Intersections géométriques avec le territoire national et régional
gdf_thiessen['geometry'] = gdf_thiessen['geometry'].intersection(boundary)

# 4. Calcul des poids surfaciques (Poids = Surface du polygone / Surface totale)
tot_nat_area = boundary.area
gdf_thiessen['weight_nat'] = gdf_thiessen['geometry'].area / tot_nat_area
```

---

## 📊 4. Calcul de la Pluviométrie Moyenne Pondérée

Lors du calcul de la hauteur de pluie moyenne $\bar{P}$ sur une région ou sur toute la Tunisie :

$$\bar{P} = \sum_{i=1}^{N} (P_i \times W_i)$$

Où :
- $P_i$ : Hauteur d'eau mesurée à la station $i$ (en mm).
- $W_i$ : Poids surfacique de Thiessen de la station $i$.

La fonction `compute_weighted_avg()` applique cette formule :

```python
def compute_weighted_avg(df_vals, value_col, weights_dict):
    df_w = df_vals[['id_station', value_col]].copy()
    df_w['weight'] = df_w['id_station'].map(weights_dict)
    df_w = df_w.dropna(subset=['weight'])
    
    tot_w = df_w['weight'].sum()
    if tot_w > 0:
        df_w['weight_norm'] = df_w['weight'] / tot_w
        return (df_w[value_col] * df_w['weight_norm']).sum()
    return 0.0
```

---

## 🟢 5. Avantages Métier pour la DGRE

1. **Représentativité Physique Exacte** : Les zones désertiques du Sud ou les zones montagneuses du Nord-Ouest sont pondérées selon leur vraie étendue géographique, évitant de sur-représenter les zones urbaines denses en capteurs.
2. **Robustesse face aux Stations Inactives** : Si des stations sont exclues (ex: 17 stations inactives), les polygones des stations actives voisines s'agrandissent automatiquement pour rééquilibrer la somme des poids à 100%.
