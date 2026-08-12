# Rapport de Sélection et d'Audit des Stations Pluviométriques (DGRE)

Ce document présente l'audit détaillé des stations de la table `station_148` utilisées dans la plateforme **CartaGen** et le générateur d'annuaire pluviométrique de la DGRE.

---

## 📊 Synthèse Numérique

| Métrique | Valeur | Description |
| :--- | :--- | :--- |
| **Nombre total de stations répertoriées** | **148** | Enregistrements présents dans la table référentielle `station_148`. |
| **Stations actives & sélectionnées** | **131** | Stations possédant des données valides dans `pluies_148` pour la période observée. |
| **Stations non sélectionnées (exclues)** | **17** | Stations absentes des relevés de la période (inactives ou sans télémesures). |

$$148 \text{ (stations totales)} - 17 \text{ (sans données)} = \mathbf{131 \text{ stations valides utilisées}}$$

---

## 📋 Liste Détaillée des 17 Stations Non Sélectionnées

Ces 17 stations ne possèdent aucune mesure enregistrée dans la table `pluies_148` pour l'année observée (ex: 2020-2021). Afin de garantir la précision métier et de ne pas biaiser l'interpolation des cartes d'isohyètes (IDW / Thiessen), elles sont exclues automatiquement par l'agent d'audit de données (`DataAuditAgent`).

| N° | ID Station | Nom de la Station | Gouvernorat | Motif d'Exclusion |
| :---: | :--- | :--- | :--- | :--- |
| **1** | `1485676324` | **SILIANA II SM** | Siliana | Aucune observation dans `pluies_148` pour la période |
| **2** | `1487208343` | **DJEBEL MATLEG** | Sidi Bouzid | Aucune observation dans `pluies_148` pour la période |
| **3** | `1488098463` | **BIR SANIA** | Kébili | Aucune observation dans `pluies_148` pour la période |
| **4** | `1488740362` | **TAMEGHZA.GN** | Tozeur | Aucune observation dans `pluies_148` pour la période |
| **5** | `1489124352` | **BEN GUERDANE 1 SM** | Mednine | Aucune observation dans `pluies_148` pour la période |
| **6** | `1489125452` | **BENI KHEDECHE DELAGA** | Mednine | Aucune observation dans `pluies_148` pour la période |
| **7** | `1489179462` | **DEGACHE MUNICIPALITE** | Tozeur | Aucune observation dans `pluies_148` pour la période |
| **8** | `1489202652` | **DJERBA HOUMT SOUK SM** | Mednine | Aucune observation dans `pluies_148` pour la période |
| **9** | `1489257863` | **EL FAOUAR CRDA** | Kébili | Aucune observation dans `pluies_148` pour la période |
| **10** | `1489342862` | **HIZOUA** | Tozeur | Aucune observation dans `pluies_148` pour la période |
| **11** | `1489358563` | **KEBILI CRDA** | Kébili | Aucune observation dans `pluies_148` pour la période |
| **12** | `1489430152` | **MEDNINE PEPINIERE PF** | Mednine | Aucune observation dans `pluies_148` pour la période |
| **13** | `1489464262` | **NEFTA** | Tozeur | Aucune observation dans `pluies_148` pour la période |
| **14** | `1489688652` | **STE SIDI CHOMMAKH** | Mednine | Aucune observation dans `pluies_148` pour la période |
| **15** | `1489703563` | **SOUK LAHAD** | Kébili | Aucune observation dans `pluies_148` pour la période |
| **16** | `1489777162` | **TOZEUR CRDA** | Tozeur | Aucune observation dans `pluies_148` pour la période |
| **17** | `1489817652` | **ZARZIS VILLE PAVA** | Mednine | Aucune observation dans `pluies_148` pour la période |

---

## 🎯 Impact sur les Traitements SIG

1. **Cartographie des Isohyètes** : L'exclusion des stations à 0 mesure empêche de créer de faux "trous" ou artefacts de précipitation nulle sur les zones du Sud (Kébili, Tozeur, Mednine).
2. **Pondération de Thiessen** : Les Voronoi sont calculés exclusivement sur les 131 stations géographiquement actives.
