# Documentation des Algorithmes et Formules Mathématiques — CartaGen (DGRE)

Ce document détaille l'ensemble des formules mathématiques, algorithmes spatiaux et traitements statistiques implémentés dans la plateforme **CartaGen** et le générateur d'annuaires pluviométriques de la Direction Générale des Ressources en Eau (DGRE).

---

## 📐 1. Algorithmes Spatiaux et Cartographiques

### A. Interpolation Spatiale IDW (Inverse Distance Weighting)
L'interpolation spatiale des cumuls de pluie pour la génération des cartes d'isohyètes utilise la méthode **IDW à puissance 2**, optimisée par un arbre KD-Tree tridimensionnel (`scipy.spatial.cKDTree`).

#### Formule Mathématique :
Pour évaluer la pluviométrie $Z(x, y)$ en un point de la grille à partir de $k$ stations les plus proches ($k=10$) :

$$Z(x, y) = \frac{\sum_{i=1}^{k} w_i \cdot Z_i}{\sum_{i=1}^{k} w_i}$$

Où le poids $w_i$ de chaque station est inversement proportionnel au carré de la distance euclidienne $d_i$ :

$$w_i = \frac{1}{\max(d_i, \epsilon)^2} \quad \text{avec } \epsilon = 10^{-10}$$

---

### B. Polygones de Thiessen (Diagramme de Voronoi) & Pondération
Pour calculer les cumuls moyens régionaux et nationaux représentatifs sans biais d'uniformité :

#### Formule du Poids Surfacique ($W_i$) :

$$W_i = \frac{\text{Surface}(P_i \cap Z)}{S_Z} \quad \text{avec } \sum_{i=1}^{N} W_i = 1$$

#### Formule de la Moyenne Spatialement Pondérée ($\bar{P}$) :

$$\bar{P} = \sum_{i=1}^{N} (P_i \times W_i)$$

Où $P_i$ est la pluie à la station $i$, et $P_i \cap Z$ est l'intersection géométrique du polygone de Voronoi avec la frontière administrative PostGIS en projection UTM Zone 32N (EPSG:32632).

---

## 📊 2. Traitements Statistiques et Pluviométriques

### A. Cumul Pluviométrique Annuel Hydrologique
L'année hydrologique s'étend du 1er Septembre de l'année $A$ au 31 Août de l'année $A+1$.

#### Formule de Découpage de l'Année Hydrologique :

$$\text{HydroYear}(\text{date}) = \begin{cases} \text{Year}(\text{date}) & \text{si Month}(\text{date}) \ge 9 \\ \text{Year}(\text{date}) - 1 & \text{si Month}(\text{date}) < 9 \end{cases}$$

---

### B. Moyennes et Normales Interannuelles (20 ans Glissants)
Pour chaque station $i$, la moyenne historique normale $N_i$ est calculée sur une période glissante de 20 ans jusqu'à l'année d'observation $A$ :

$$N_i = \frac{1}{M} \sum_{y = A-20}^{A} P_{i, y} \quad (M \ge 3 \text{ ans valides})$$

---

### C. Calculs des Écarts et des Ratios Pourcentages

#### Écart Absolu (en mm) :

$$\Delta P = P_{\text{observé}} - N_{\text{historique}}$$

#### Ratio par rapport à la Normale (en %) :

$$\text{Rapport (\%)} = \left( \frac{P_{\text{observé}}}{N_{\text{historique}}} \right) \times 100$$

#### Écart Relatif / Déficit ou Excédent (en %) :

$$\text{Écart (\%)} = \left( \frac{P_{\text{observé}}}{N_{\text{historique}}} - 1 \right) \times 100$$

- Si $\text{Écart (\%)} \ge 0$ : Excédent de $\text{Écart (\%)}$.
- Si $\text{Écart (\%)} < 0$ : Déficit de $|\text{Écart (\%)}|$.

---

## 🗓️ 3. Répartition Saisonnière et Mensuelle

### A. Distribution Saisonnière (Poids Relatifs)
Chaque année hydrologique est divisée en 4 saisons :
- **Automne** : Septembre, Octobre, Novembre
- **Hiver** : Décembre, Janvier, Février
- **Printemps** : Mars, Avril, Mai
- **Été** : Juin, Juillet, Août

#### Contribution Relative d'une Saison $S$ au Total Annuel :

$$\text{Contrib}_S (\%) = \left( \frac{P_{\text{Saison } S}}{P_{\text{Annuel Total}}} \right) \times 100$$

---

### B. Classification par Classe de Pluviométrie (Tableau 6)
Pour chaque mois $m$, le ratio $\text{Rapp}_m = \left( \frac{P_m}{N_m} \right) \times 100$ détermine la classe d'abondance :

| Ratio ($\text{Rapp}_m$) | Classe Pluviométrique | Code Couleur |
| :--- | :--- | :---: |
| $\text{Rapp}_m < 50\%$ | Pluie inférieure à 50% de la moyenne | **Rouge** (`clsred`) |
| $50\% \le \text{Rapp}_m < 75\%$ | Pluie comprise entre 50% et 75% | **Orange** (`clsorange`) |
| $75\% \le \text{Rapp}_m < 100\%$ | Pluie comprise entre 75% et 100% | **Jaune** (`clsyellow`) |
| $\text{Rapp}_m \ge 100\%$ | Pluie supérieure à 100% de la moyenne | **Vert** (`clsgreen`) |

---

## ⚙️ 4. Validation des Données (Filtres `DataAuditAgent`)

Pour éliminer les erreurs de saisie et les anomalies géographiques avant tout calcul :
1. **Élimination des Doublons Journaliers** : Conservation d'une seule observation par `(id_station, date_obs::date)`.
2. **Filtrage des Coordonnées Aberrantes** : Exclusion des stations dont les coordonnées géographiques en UTM Zone 32N sont en dehors du domaine tunisien (ex: $Y < 3.8 \times 10^6$ pour les gouvernorats du Nord).
3. **Audit de Présence** : Les stations ne possédant aucune mesure sur la période ($N_{\text{obs}} = 0$) sont exclues du calcul des poids de Thiessen.
