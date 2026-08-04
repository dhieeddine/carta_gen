#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Script de génération de l'annuaire pluviométrique 2021-2022.
Version corrigée :
- Tous les mois apparaissent dans les tableaux (détection améliorée)
- Police ultra-compacte (\tiny) pour les tables
- Marges minimales, colonnes serrées
- Figures des isohyètes redimensionnées pour tenir dans la page
- Correction des noms d'images FEV, MAR, AVR
- Compilation avec lualatex en priorité
"""

import os
import sys
import pandas as pd
import numpy as np
import subprocess
import shutil
import glob
from datetime import datetime

# ------------------------- Configuration -------------------------
YASRA_PATH = "yasra.xlsx"
TABLEAUX_JOURNAUX = "tableaux_pluviometriques_2021-2022.xlsx"
OUTPUT_TEX = "annuaire_2021_2022.tex"
OUTPUT_PDF = "annuaire_2021_2022.pdf"
LOGO_PATH = "logo_dgre.png"
IMG_DIR = "."

# ------------------------- 1. Chargement des données mensuelles (yasra) -------------------------
def load_yasra(path):
    df = pd.read_excel(path)
    print("Colonnes dans yasra.xlsx :", df.columns.tolist())

    # On détecte les colonnes mois telles qu'elles sont (elles sont déjà en majuscules)
    mois_connus = ['SEPT', 'OCTO', 'NOVE', 'DECE', 'JANV', 'FEV', 'MAR', 'AVR', 'MAI', 'JUIN', 'JUIL', 'AOUT']
    mois_cols = [c for c in df.columns if c.upper() in mois_connus]

    # Si certains mois manquent, on essaie avec les abréviations alternatives
    if len(mois_cols) < 12:
        # Essayer avec des noms comme 'SEP', 'OCT', etc.
        alt_map = {
            'SEP': 'SEPT', 'OCT': 'OCTO', 'NOV': 'NOVE', 'DEC': 'DECE',
            'JAN': 'JANV', 'FEV': 'FEV', 'MAR': 'MAR', 'AVR': 'AVR',
            'MAI': 'MAI', 'JUN': 'JUIN', 'JUL': 'JUIL', 'AOU': 'AOUT'
        }
        for col in df.columns:
            col_upper = col.upper()
            if col_upper in alt_map and alt_map[col_upper] not in [c.upper() for c in mois_cols]:
                mois_cols.append(col)

    # Tri dans l'ordre chronologique
    ordre = ['SEPT','OCTO','NOVE','DECE','JANV','FEV','MAR','AVR','MAI','JUIN','JUIL','AOUT']
    mois_cols = [c for c in ordre if c in [m.upper() for m in mois_cols]]

    total_col = None
    for col in df.columns:
        if col.upper() in ['TOTAL', 'TOT', 'TOTAL ANNUEL']:
            total_col = col
            break
    if total_col is None:
        total_col = 'TOTAL'

    region_col = None
    for col in df.columns:
        if 'region' in col.lower() or 'gouv' in col.lower() or 'gouvernorat' in col.lower():
            region_col = col
            break

    print(f"Colonnes mois : {mois_cols}")
    print(f"Colonne total : {total_col}")
    print(f"Colonne région : {region_col}")
    return df, mois_cols, total_col, region_col

df, mois_cols, total_col, region_col = load_yasra(YASRA_PATH)

# ------------------------- 2. Calcul des statistiques -------------------------
def compute_stats(df, mois_cols, total_col, region_col):
    moyenne_mensuelle = df[mois_cols].mean()
    saisons = {
        'Automne': df[mois_cols[:3]].sum(axis=1).mean(),
        'Hiver': df[mois_cols[3:6]].sum(axis=1).mean(),
        'Printemps': df[mois_cols[6:9]].sum(axis=1).mean(),
        'Été': df[mois_cols[9:12]].sum(axis=1).mean()
    }
    total_national = df[total_col].mean()
    deficit = 100 * (1 - total_national / 232)

    if region_col and region_col in df.columns:
        regions = df.groupby(region_col)[total_col].mean().index
        region_data = {}
        for r in regions:
            sub = df[df[region_col] == r]
            region_data[r] = {
                'total': sub[total_col].mean(),
                'auto': sub[mois_cols[:3]].sum(axis=1).mean(),
                'hiver': sub[mois_cols[3:6]].sum(axis=1).mean(),
                'print': sub[mois_cols[6:9]].sum(axis=1).mean(),
                'ete': sub[mois_cols[9:12]].sum(axis=1).mean()
            }
    else:
        region_data = None

    return {
        'moyenne_mensuelle': moyenne_mensuelle,
        'saisons': saisons,
        'total_national': total_national,
        'deficit': deficit,
        'region_data': region_data
    }

stats = compute_stats(df, mois_cols, total_col, region_col)

# ------------------------- 3. Recherche des images isohyètes (corrigé) -------------------------
def find_images():
    images = {}
    # Dictionnaire de correspondance : nom de colonne (dans yasra) -> nom de fichier image
    col_to_file = {
        'SEPT': 'isohyete_SEP.png',
        'OCTO': 'isohyete_OCT.png',
        'NOVE': 'isohyete_NOV.png',
        'DECE': 'isohyete_DEC.png',
        'JANV': 'isohyete_JAN.png',
        'FEV': 'isohyete_FEV.png',    # colonne 'FEV' -> isohyete_FEV.png
        'MAR': 'isohyete_MAR.png',    # colonne 'MAR' -> isohyete_MAR.png
        'AVR': 'isohyete_AVR.png',    # colonne 'AVR' -> isohyete_AVR.png
        'MAI': 'isohyete_MAI.png',
        'JUIN': 'isohyete_JUN.png',
        'JUIL': 'isohyete_JUL.png',
        'AOUT': 'isohyete_AOU.png'
    }

    for col in mois_cols:
        col_upper = col.upper()
        if col_upper in col_to_file:
            file_name = col_to_file[col_upper]
            if os.path.exists(file_name):
                images[col] = file_name
                print(f"✅ Image trouvée pour {col} : {file_name}")
                continue
        # Fallback : chercher avec des variantes
        variants = [col, col.lower(), col.upper(), col.capitalize()]
        for v in variants:
            for ext in ['.png', '.PNG', '.jpg', '.JPG']:
                fname = f"isohyete_{v}{ext}"
                if os.path.exists(fname):
                    images[col] = fname
                    print(f"✅ Image trouvée pour {col} : {fname}")
                    break
            if col in images:
                break
        if col not in images:
            print(f"⚠️ Image manquante pour {col}")

    # Images annuelle et saisonnière
    for f in ['isohyete_annuelle.png', 'carte_isohyetes.png', 'isohyetes_annuelles.png']:
        if os.path.exists(f):
            images['annuelle'] = f
            print(f"✅ Image annuelle : {f}")
            break
    for f in ['carte_isohyetes_saisons.png', 'isohyetes_saisons.png']:
        if os.path.exists(f):
            images['saisons'] = f
            print(f"✅ Image saisonnière : {f}")
            break

    return images

images = find_images()
print("Images finales :", list(images.keys()))

# ------------------------- 4. Génération des tableaux journaliers (tous les mois, ultra-compacts) -------------------------
def generer_tableaux_journaliers(excel_path):
    if not os.path.exists(excel_path):
        return "Aucun fichier de tableaux journaliers trouvé."

    xl = pd.ExcelFile(excel_path)
    all_tables_latex = []

    # Ordre des mois dans l'ordre chronologique (pour l'affichage)
    ordre_mois = ['Sep','Oct','Nov','Dec','Jan','Fév','Mar','Avr','Mai','Juin','Juil','Août']

    for sheet_name in xl.sheet_names:
        df_sheet = pd.read_excel(excel_path, sheet_name=sheet_name, header=0)
        cols = df_sheet.columns.tolist()

        if 'Jour' not in cols:
            continue

        # On prend toutes les colonnes qui ne sont pas 'Jour' et qui ne contiennent pas 'Total' (ni 'TOTAL')
        # On garde aussi les colonnes qui sont dans la liste ordre_mois (ou leurs abréviations)
        mois_cols_present = []
        for col in cols:
            if col == 'Jour':
                continue
            if 'Total' in col or 'TOTAL' in col:
                continue
            # Si la colonne est vide (NaN), on l'ignore
            if pd.isna(col):
                continue
            # On ajoute si elle correspond à un mois (vérification avec les mots-clés)
            col_lower = col.lower().replace('é','e').replace('è','e').replace('ê','e').replace('à','a').replace('â','a').replace('ô','o')
            mois_keywords = ['sep','sept','oct','nov','dec','dece','jan','janv','fev','fevr','mar','avr','avri','mai','juin','juil','aout','aou']
            if any(k in col_lower for k in mois_keywords):
                mois_cols_present.append(col)
            # Sinon, on garde quand même (fallback)
            else:
                mois_cols_present.append(col)

        # Trier les colonnes selon l'ordre chronologique
        mois_cols_present.sort(key=lambda x: ordre_mois.index(x) if x in ordre_mois else 999)

        if not mois_cols_present:
            print(f"⚠️ Aucune colonne mois détectée dans la feuille {sheet_name}")
            continue

        # On n'utilise pas de colonne Total (pour gagner de la place)
        total_col = None

        nb_cols = 1 + len(mois_cols_present)
        caption = f"Station {sheet_name}"
        label = f"tab:{sheet_name.replace(' ', '_')}"

        table_code = "\\begin{longtable}{|c|" + "c" * len(mois_cols_present) + "|}\n"
        table_code += f"\\caption{{{caption}}}\\label{{{label}}}\\\\\n"
        table_code += "\\hline\n"
        table_code += "Jour & " + " & ".join(mois_cols_present) + " \\\\\n"
        table_code += "\\hline\n"
        table_code += "\\endfirsthead\n"
        table_code += "\\multicolumn{" + str(nb_cols) + "}{c}{{\\bfseries Suite}} \\\\\n"
        table_code += "\\hline\n"
        table_code += "Jour & " + " & ".join(mois_cols_present) + " \\\\\n"
        table_code += "\\hline\n"
        table_code += "\\endhead\n"
        table_code += "\\hline\n"
        table_code += "\\multicolumn{" + str(nb_cols) + "}{r}{{Suite sur la page suivante}} \\\\\n"
        table_code += "\\endfoot\n"
        table_code += "\\hline\n"
        table_code += "\\endlastfoot\n"

        for idx, row in df_sheet.iterrows():
            jour = row['Jour']
            if pd.isna(jour):
                continue

            if isinstance(jour, str):
                if 'Total' in jour or 'Nb jours' in jour or 'Max' in jour:
                    line = "\\hline\n\\textbf{" + jour + "} & "
                    for m in mois_cols_present:
                        val = row[m]
                        if pd.isna(val):
                            line += " & "
                        else:
                            line += f"{val:.1f} & "
                    line = line.rstrip(' & ') + " \\\\\n"
                    table_code += line
                    continue
                else:
                    line = f"{jour} & "
            else:
                line = f"{int(jour)} & "

            for m in mois_cols_present:
                val = row[m]
                if pd.isna(val):
                    line += " & "
                elif val == 0:
                    line += "." + " & "
                else:
                    line += f"{val:.1f} & "
            line = line.rstrip(' & ') + " \\\\\n"
            table_code += line

        table_code += "\\end{longtable}\n"
        all_tables_latex.append(table_code)

    # Regrouper deux par page avec une police très petite
    final_code = ""
    for i in range(0, len(all_tables_latex), 2):
        final_code += "\\begin{minipage}[t]{0.48\\textwidth}\n"
        final_code += "\\raggedright\n"
        final_code += "\\tiny\n"  # police la plus petite
        final_code += "\\setlength{\\tabcolsep}{1pt}\n"
        final_code += all_tables_latex[i]
        final_code += "\\end{minipage}\n"
        if i + 1 < len(all_tables_latex):
            final_code += "\\hfill\n"
            final_code += "\\begin{minipage}[t]{0.48\\textwidth}\n"
            final_code += "\\raggedright\n"
            final_code += "\\tiny\n"
            final_code += "\\setlength{\\tabcolsep}{1pt}\n"
            final_code += all_tables_latex[i+1]
            final_code += "\\end{minipage}\n"
        final_code += "\\newpage\n"

    return final_code

tableaux_journaux_latex = generer_tableaux_journaliers(TABLEAUX_JOURNAUX)

# ------------------------- 5. Génération du LaTeX final (avec figures redimensionnées) -------------------------
def escape_latex(s):
    return s.replace('%', '\\%').replace('_', '\\_').replace('&', '\\&').replace('#', '\\#')

def generate_latex(stats, images, region_col, tableaux_journaux_latex):
    # Tableau mensuel national
    mois_labels = [m[:3].upper() for m in stats['moyenne_mensuelle'].index]
    mois_values = stats['moyenne_mensuelle'].values
    table_mois = "\\begin{tabular}{l r}\n\\toprule\nMois & Pluie (mm) \\\\ \\midrule\n"
    for m, v in zip(mois_labels, mois_values):
        table_mois += f"{m} & {v:.1f} \\\\\n"
    table_mois += "\\bottomrule\n\\end{tabular}"

    # Tableau saisonnier
    table_saisons = "\\begin{tabular}{l r}\n\\toprule\nSaison & Pluie (mm) \\\\ \\midrule\n"
    for s, v in stats['saisons'].items():
        table_saisons += f"{s} & {v:.1f} \\\\\n"
    table_saisons += "\\bottomrule\n\\end{tabular}"

    # Tableau par région
    table_regions = ""
    if stats['region_data'] is not None:
        table_regions = "\\begin{tabular}{l r r r r r}\n\\toprule\nRégion & Total & Automne & Hiver & Printemps & Été \\\\ \\midrule\n"
        for r, data in stats['region_data'].items():
            table_regions += f"{escape_latex(r)} & {data['total']:.1f} & {data['auto']:.1f} & {data['hiver']:.1f} & {data['print']:.1f} & {data['ete']:.1f} \\\\\n"
        table_regions += "\\bottomrule\n\\end{tabular}"
    else:
        table_regions = "Les données régionales ne sont pas disponibles."

    # Construction des figures mensuelles (groupées par 3 pour gagner de la place, avec largeur réduite)
    monthly_figures = ""
    mois_ordre = ['SEPT','OCTO','NOVE','DECE','JANV','FEV','MAR','AVR','MAI','JUIN','JUIL','AOUT']
    avail = [c for c in mois_ordre if c in images]
    if avail:
        for i in range(0, len(avail), 3):
            group = avail[i:i+3]
            monthly_figures += "\\begin{figure}[htbp]\n\\centering\n"
            for j, col in enumerate(group):
                img = images[col]
                # Réduire la largeur de la minipage pour que l'image ne déborde pas
                width = "0.7\\textwidth" if len(group) == 1 else "0.32\\textwidth"
                monthly_figures += f"\\begin{{minipage}}{{{width}}}\n\\centering\n\\includegraphics[width=0.9\\linewidth]{{{img}}}\n\\caption{{Isohyètes de {col[:3].lower()} 2021}}\n\\end{{minipage}}"
                if j < len(group)-1:
                    monthly_figures += "\\hfill\n"
            monthly_figures += "\\end{figure}\n\\clearpage\n"
    else:
        monthly_figures = "\\noindent Aucune carte mensuelle disponible.\n"

    annual_fig = ""
    if 'annuelle' in images:
        annual_fig = f"\\begin{{figure}}[htbp]\n\\centering\n\\includegraphics[width=0.85\\textwidth]{{{images['annuelle']}}}\n\\caption{{Carte des isohyètes annuelles 2021-2022}}\n\\end{{figure}}\n\\clearpage\n"
    else:
        annual_fig = "\\noindent Carte annuelle non disponible.\n\\clearpage\n"

    season_fig = ""
    if 'saisons' in images:
        season_fig = f"\\begin{{figure}}[htbp]\n\\centering\n\\includegraphics[width=0.85\\textwidth]{{{images['saisons']}}}\n\\caption{{Cartes des isohyètes saisonnières}}\n\\end{{figure}}\n\\clearpage\n"
    else:
        season_fig = "\\noindent Carte saisonnière non disponible.\n\\clearpage\n"

    # Textes avant-propos et présentation (inchangés)
    avant_propos = r"""
\section*{Avant-propos}
L'annuaire pluviométrique de la Tunisie de l'année 2021-2022 est une synthèse des observations pluviométriques relevées sur l'ensemble du réseau pluviométrique national au cours de l'année hydrologique 2021-2022 qui démarre le 1er septembre 2021 et s'achève le 31 août 2022.

Il est le fruit d'une collaboration permanente entre les établissements régionaux représentés par les arrondissements des ressources en eau (A/RE) des Commissariats Régionaux au Développement Agricole (CRDA) et la Direction Générale des Ressources en Eau (DGRE). Dans chaque gouvernorat, il existe un CRDA au sein duquel toutes les directions techniques centrales au niveau du ministère sont représentées par des arrondissements. La Direction Générale des Ressources en Eau est représentée à l'échelle régionale par 24 arrondissements des ressources en eau. Parmi leurs nombreux types de tâches, on peut citer :

\begin{itemize}
\item Gérer le réseau de pluviomètres implantés dans les différents gouvernorats et s'assurer de leur bon état de fonctionnement.
\item Recueillir les observations et accompagner des observateurs pluviométriques pour tenir des registres de précipitations.
\item Créer les fichiers informatisés et éditer des catalogues pluviométriques régionaux.
\end{itemize}

Et la Direction des Eaux de Surface par l'intermédiaire de la sous-direction d'Hydrologie Analytique et des Bases de Données :

\begin{itemize}
\item Assurer la levée, la collecte, l'informatisation et la mise en forme de ces données ;
\item Préparer, éditer et diffuser l'annuaire pluviométrique national ;
\item Veiller à la mise à jour et la sauvegarde de la banque des données pluviométriques, composante principale de la base nationale de données sur les ressources en eau ;
\item Accorder une assistance technique permanente aux arrondissements régionaux pour la bonne gestion du réseau pluviométrique.
\end{itemize}
"""

    presentation = r"""
\section*{Présentation de l'annuaire}

La première partie de cette publication présente une analyse de la pluviosité en Tunisie durant l'année 2021-2022. Cette analyse a été faite à l'échelle des gouvernorats et des régions naturelles. Chaque région naturelle regroupe un certain nombre de gouvernorats selon la répartition suivante :

\begin{itemize}
\item Nord Ouest : Jendouba, Béja, Kef et Siliana;
\item Nord Est : Tunis, Ariana, Ben Arous, Manouba, Nabeul, Zaghouan et Bizerte;
\item Centre Ouest : Kairouan, Kasserine et Sidi Bouzid;
\item Centre Est : Sousse, Monastir, Mahdia et Sfax;
\item Sud Ouest : Gafsa, Tozeur et Kebili;
\item Sud Est : Gabès, Tataouine et Mednine.
\end{itemize}

Sur un total de 728 stations de mesure des précipitations observées en 2021-2022, 148 stations ont été sélectionnées (3 à 7 stations par gouvernorat), pour décrire la situation pluviométrique à l'échelle du pays.

La deuxième partie comprend les relevés pluviométriques quotidiens. Ces relevés sont présentés sous forme de tableau annuel par station et regroupés par bassin et par ordre numérique et alphabétique. Les données pluviométriques ont été saisies et traitées à l'aide du logiciel de gestion des données pluviométriques « HYDRACCES », développé au Laboratoire d'Hydrologie de l'Institut d'Études du Développement (IRD).

Quant à la critique des données, elle se fait la première fois lors de la réception du bulletin pluviométrique. Ce niveau de critique consiste à comparer les relevés des postes voisins. Les critiques incluent la comparaison des lectures des stations voisines et l'exclusion de toute observation qui semble sortir de l'ordinaire. La deuxième critique a été formulée lors de la préparation du catalogue en comparant les bulletins avec leurs copies et avec les pages de référence pour documenter les éventuelles corrections. Les valeurs qui paraissent correctes ou acceptables seront fidèlement reproduites comme sur le message d'observation, des corrections sont également apportées sur les relevés décalés d'un jour car parfois les observateurs jugent marquer les quantités observées à 7 heures du matin le même jour que la veille selon les instructions établies.
"""

    # Page de garde
    logo_latex = ""
    if os.path.exists(LOGO_PATH):
        logo_latex = f"\\includegraphics[width=3cm]{{{LOGO_PATH}}}\\\\"
    page_garde = r"""
\begin{titlepage}
\centering
""" + logo_latex + r"""
\vspace{1cm}
{\LARGE \textbf{REPUBLIQUE TUNISIENNE} \\
MINISTERE DE L'AGRICULTURE \\
DES RESSOURCES HYDRAULIQUES ET DE LA PECHE}

\vspace{1cm}
{\Large Année : 2021-2022}

\vspace{2cm}
{\Huge \textbf{ANNUAIRE PLUVIOMETRIQUE} \\
\textbf{DE LA TUNISIE}}

\vspace{3cm}
{\Large PUBLICATION DE LA DIRECTION GENERALE DES RESSOURCES EN EAU \\
43, Rue la MANOUBIA -1008- TUNIS \\
Tél : (216) 71 560 000 / +216 71 391 851 \\
Fax : (216) 71 391 549}

\vfill
{\large Généré le """ + datetime.now().strftime('%d/%m/%Y') + r"""}

\end{titlepage}
"""

    # Préambule avec marges réduites
    preambule = r"""
\documentclass[a4paper,12pt]{article}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{lmodern}
\usepackage[french]{babel}
\usepackage{geometry}
\geometry{left=1.2cm,right=1.2cm,top=1.5cm,bottom=1.5cm}
\usepackage{graphicx}
\usepackage{array,booktabs}
\usepackage{multirow}
\usepackage{subcaption}
\usepackage{longtable}
\usepackage{hyperref}
\usepackage{colortbl}
\hypersetup{
    pdfauthor={DGRE},
    pdftitle={Annuaire Pluviométrique 2021-2022},
}
\renewcommand{\arraystretch}{0.7}
\setlength{\arrayrulewidth}{0.2pt}
\setlength{\tabcolsep}{1pt}
\setcounter{secnumdepth}{0}

\begin{document}
"""

    content = page_garde + r"""
\tableofcontents
\newpage
\listoffigures
\newpage
\listoftables
\newpage
""" + avant_propos + presentation + r"""

\section{Aperçu sommaire de la pluviosité de l'année 2021-2022}

Le total pluviométrique de l'année hydrologique 2021-2022 pour l'ensemble du pays est déficitaire. À l'échelle des grandes régions naturelles, le déficit varie entre 16\% au Nord Ouest et 68\% au Sud Ouest.

\begin{itemize}
\item Au Nord Ouest, on a enregistré des pluies (par gouvernorat) variant entre 323 mm au gouvernorat du Kef et 670 mm au gouvernorat de Jendouba ; au niveau de ces deux gouvernorats nous avons relevé respectivement un déficit qui varie entre 19\% et 21\% par rapport à la moyenne pluviométrique par gouvernorat ;
\item Au Nord Est on a enregistré des pluies (par gouvernorat) variant entre 248 mm au gouvernorat de Tunis et 547 mm au gouvernorat de Bizerte ; représentant respectivement un déficit qui varie entre 14\% au gouvernorat de Bizerte et 45\% au gouvernorat de Tunis par rapport à la moyenne pluviométrique par gouvernorat ;
\item Au Centre Ouest, on a enregistré des pluies (moyenne par gouvernorat) variant entre 123 mm à Sidi Bouzid et 204 mm au gouvernorat de Kairouan, représentant respectivement des déficits de 43\% au gouvernorat de Sidi Bouzid et de 36\% au gouvernorat de Kairouan par rapport à la moyenne pluviométrique par gouvernorat ;
\item Au Centre Est, on a enregistré 96 mm de pluie à Sfax et 180 mm à Sousse, représentant respectivement un déficit variant entre 39\% au gouvernorat de Mahdia et 56\% au gouvernorat de Sfax comparé à la moyenne pluviométrique par gouvernorat ;
\item Au Sud Ouest, on a enregistré des pluies (moyenne par gouvernorat) variant entre 36 mm à Kebili et 67 mm à Gafsa avec des déficits variant entre 51\% au gouvernorat de Tozeur et 60\% au gouvernorat de Kebili comparés à la moyenne pluviométrique par gouvernorat ;
\item Au Sud Est du pays, on a enregistré des pluies de 30 mm à Tataouine et 98 mm à Gabes avec des déficits qui varient entre 41\% au gouvernorat de Gabes et 71\% au gouvernorat de Tataouine par rapport à la moyenne pluviométrique par gouvernorat.
\end{itemize}

Comparée à la moyenne interannuelle, la répartition régionale de la pluviométrie pour l'année 2021-2022 se présente comme suit :

""" + table_regions + r"""

\subsection{Pluies mensuelles}

La distribution mensuelle des pluies du pays, synthétisée dans le tableau suivant, montre que le mois de Mars est excédentaire avec 25\%. Pour le reste de l'année, les déficits varient entre 10\% au mois d'Octobre et 91\% au mois de Juin.

""" + table_mois + r"""

\subsection{Pluies saisonnières}

À l'échelle saisonnière, la répartition des pluies par région naturelle se présente comme suit :

\begin{itemize}
\item L'automne a contribué de 30,5\% au total pluviométrique de l'année sur l'ensemble du pays. Sa contribution à l'échelle régionale varie entre 12\% au Centre Ouest et 46\% au Sud Est;
\item L'hiver a présenté 29,5\% du total pluviométrique sur l'ensemble du pays, sa contribution à l'échelle régionale varie entre 8\% au Sud Ouest et 40\% au Nord Ouest;
\item La saison du printemps a contribué de 36\% du total pluviométrique annuel, sa contribution régionale varie de 24\% au Nord Est à 59\% au Centre Ouest;
\item La saison estivale a contribué de 4\% au total pluviométrique de l'année 2021-2022, sa contribution à l'échelle régionale varie de 0\% au Sud Est à 11\% au Centre Ouest.
\end{itemize}

""" + table_saisons + r"""

\clearpage

\section{Cartes d'isohyètes}

""" + annual_fig + season_fig + monthly_figures + r"""

\section{Tableaux pluviométriques journaliers}

Les tableaux ci-dessous présentent les relevés quotidiens pour chaque station du gouvernorat de Béja (données extraites de la base Access). Un point « . » indique un jour sec, une case vide correspond à une absence de relevé. Les lignes « Total mensuel », « Nb jours > 0 mm » et « Max journalier » sont des récapitulatifs.

""" + tableaux_journaux_latex + r"""

\section{Liste des stations pluviométriques}

La liste exhaustive des 728 stations, avec leurs coordonnées et altitudes, est consultable dans l'annuaire papier complet. Une extraction est présentée en annexe numérique.

\end{document}
"""

    with open(OUTPUT_TEX, "w", encoding="utf-8") as f:
        f.write(preambule + content)
    print(f"✅ Fichier LaTeX généré : {OUTPUT_TEX}")
    return OUTPUT_TEX

tex_path = generate_latex(stats, images, region_col, tableaux_journaux_latex)

# ------------------------- 6. Compilation LaTeX avec lualatex en priorité -------------------------
def compile_latex(tex_file):
    for engine in ['lualatex', 'xelatex', 'pdflatex']:
        eng_path = shutil.which(engine)
        if eng_path:
            print(f"Compilation avec {engine}...")
            success = True
            for _ in range(2):
                cmd = [eng_path, '-interaction=nonstopmode', '-synctex=1', tex_file]
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode != 0:
                    success = False
                    break
            if success:
                base = os.path.splitext(tex_file)[0]
                if os.path.exists(f"{base}.pdf"):
                    shutil.move(f"{base}.pdf", OUTPUT_PDF)
                    print(f"✅ PDF généré avec {engine} : {OUTPUT_PDF}")
                    return True
        else:
            print(f"{engine} non trouvé.")
    return False

if compile_latex(tex_path):
    for ext in ['.aux', '.log', '.out', '.toc', '.synctex.gz', '.lof', '.lot']:
        f = tex_path.replace('.tex', ext)
        if os.path.exists(f):
            os.remove(f)
else:
    print("\n❌ Tous les moteurs LaTeX ont échoué.")
    print(f"Le fichier LaTeX est disponible : {tex_path}")
    print("Compilez manuellement avec :")
    print(f"  lualatex {tex_path}")
    print("  lualatex {tex_path}  # deux fois")



