# -*- coding: utf-8 -*-
"""
Script de génération et mise en page professionnelle du Journal de Stage ENIT
Fichier cible : journal_stage_français_mis_a_jour.docx
"""

import os
import docx
from docx import Document
from docx.shared import Inches, Pt, RGBColor, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml import parse_xml, OxmlElement
from docx.oxml.ns import nsdecls, qn

def set_cell_background(cell, fill_hex):
    """Applique une couleur d'arrière-plan à une cellule."""
    tcPr = cell._element.get_or_add_tcPr()
    shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{fill_hex}"/>')
    tcPr.append(shd)

def set_cell_margins(cell, top=100, bottom=100, left=150, right=150):
    """Définit les marges internes d'une cellule en dxa (1 pt = 20 dxa)."""
    tcPr = cell._element.get_or_add_tcPr()
    tcMar = parse_xml(
        f'<w:tcMar {nsdecls("w")}>'
        f'<w:top w:w="{top}" w:type="dxa"/>'
        f'<w:bottom w:w="{bottom}" w:type="dxa"/>'
        f'<w:left w:w="{left}" w:type="dxa"/>'
        f'<w:right w:w="{right}" w:type="dxa"/>'
        f'</w:tcMar>'
    )
    tcPr.append(tcMar)

def set_table_borders(table, color="B0BEC5", sz="4", val="single"):
    """Applique des bordures nettes et professionnelles au tableau."""
    tblPr = table._element.xpath('w:tblPr')
    if tblPr:
        borders = parse_xml(
            f'<w:tblBorders {nsdecls("w")}>'
            f'<w:top w:val="{val}" w:sz="{sz}" w:space="0" w:color="{color}"/>'
            f'<w:bottom w:val="{val}" w:sz="{sz}" w:space="0" w:color="{color}"/>'
            f'<w:left w:val="{val}" w:sz="{sz}" w:space="0" w:color="{color}"/>'
            f'<w:right w:val="{val}" w:sz="{sz}" w:space="0" w:color="{color}"/>'
            f'<w:insideH w:val="{val}" w:sz="{sz}" w:space="0" w:color="{color}"/>'
            f'<w:insideV w:val="{val}" w:sz="{sz}" w:space="0" w:color="{color}"/>'
            f'</w:tblBorders>'
        )
        tblPr[0].append(borders)

def add_header_footer(doc):
    """Ajoute en-tête et pied de page sur les sections."""
    for section in doc.sections:
        # En-tête
        header = section.header
        hp = header.paragraphs[0]
        hp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        hrun = hp.add_run("École Nationale d'Ingénieurs de Tunis (ENIT) | Journal de Stage Ingénieur")
        hrun.font.name = "Calibri"
        hrun.font.size = Pt(8.5)
        hrun.font.color.rgb = RGBColor(120, 144, 156)

        # Pied de page
        footer = section.footer
        fp = footer.paragraphs[0]
        fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        frun = fp.add_run("Élève-Ingénieur : Dhia Eddine BARHOUMI — DGRE (2026)")
        frun.font.name = "Calibri"
        frun.font.size = Pt(8.5)
        frun.font.color.rgb = RGBColor(120, 144, 156)

def add_page_number_badge(cell_or_doc, current_page, total_pages=12):
    """Ajoute un badge de numéro de page élégant en bas à droite."""
    p = cell_or_doc.add_paragraph() if hasattr(cell_or_doc, 'add_paragraph') else cell_or_doc.paragraphs[-1]
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after = Pt(0)
    run = p.add_run(f"Page {current_page} / {total_pages}")
    run.font.name = "Calibri"
    run.font.size = Pt(9.5)
    run.font.bold = True
    run.font.color.rgb = RGBColor(30, 58, 138)  # Bleu ENIT

def create_journal_document(output_path):
    doc = Document()

    # Configuration A4 Portrait
    section = doc.sections[0]
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(1.8)
    section.bottom_margin = Cm(1.8)
    section.left_margin = Cm(2.0)
    section.right_margin = Cm(2.0)

    # Styles globaux
    style_normal = doc.styles['Normal']
    style_normal.font.name = 'Calibri'
    style_normal.font.size = Pt(10)
    style_normal.font.color.rgb = RGBColor(33, 37, 41)

    # =========================================================================
    # PAGE 1 : COUVERTURE DU JOURNAL DE STAGE
    # =========================================================================
    p_inst = doc.add_paragraph()
    p_inst.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_inst.paragraph_format.space_before = Pt(0)
    p_inst.paragraph_format.space_after = Pt(3)
    r = p_inst.add_run("RÉPUBLIQUE TUNISIENNE\nMINISTÈRE DE L'ENSEIGNEMENT SUPÉRIEUR ET DE LA RECHERCHE SCIENTIFIQUE\nUNIVERSITÉ DE TUNIS EL MANAR")
    r.font.size = Pt(8.5)
    r.font.bold = True
    r.font.color.rgb = RGBColor(100, 116, 139)

    # Logo officiel ENIT
    if os.path.exists("enit.png"):
        p_logo = doc.add_paragraph()
        p_logo.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p_logo.paragraph_format.space_before = Pt(4)
        p_logo.paragraph_format.space_after = Pt(4)
        p_logo.add_run().add_picture("enit.png", width=Cm(2.5))

    p_enit = doc.add_paragraph()
    p_enit.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_enit.paragraph_format.space_before = Pt(2)
    p_enit.paragraph_format.space_after = Pt(10)
    r_enit = p_enit.add_run("ÉCOLE NATIONALE D'INGÉNIEURS DE TUNIS\n(E.N.I.T.)")
    r_enit.font.size = Pt(13)
    r_enit.font.bold = True
    r_enit.font.color.rgb = RGBColor(26, 54, 93)

    # Encadré Titre Principal
    p_title = doc.add_paragraph()
    p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_title.paragraph_format.space_before = Pt(6)
    p_title.paragraph_format.space_after = Pt(12)
    r_title = p_title.add_run("JOURNAL DE STAGE")
    r_title.font.size = Pt(22)
    r_title.font.bold = True
    r_title.font.color.rgb = RGBColor(15, 23, 42)

    # Tableau Informations Étudiant & Stage
    table_cov = doc.add_table(rows=7, cols=2)
    table_cov.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(table_cov, color="CBD5E1", sz="6")
    
    cov_data = [
        ("Élève - Ingénieur :", "Dhia Eddine BARHOUMI"),
        ("Département :", "Technologies de l'Information et de la Communication (TIC)"),
        ("Classe / Niveau :", "2ème Année Ingénieur (2 AINFO)"),
        ("Type de Stage :", "Stage Ingénieur (Obligatoire de fin de 2ème année)"),
        ("Organisme d'Accueil :", "Direction Générale des Ressources en Eau (DGRE)\nMinistère de l'Agriculture, des Ressources Hydrauliques et de la Pêche"),
        ("Lieu du Stage :", "Rue Saïda El Manoubia, Montfleury, 1008 Tunis"),
        ("Période du Stage :", "Du 15/06/2026 au 30/07/2026 (7 semaines)")
    ]

    col_widths = [Cm(5.5), Cm(11.5)]
    for row_idx, (label, val) in enumerate(cov_data):
        row = table_cov.rows[row_idx]
        cell_lbl, cell_val = row.cells[0], row.cells[1]
        
        cell_lbl.width, cell_val.width = col_widths[0], col_widths[1]
        set_cell_margins(cell_lbl, top=90, bottom=90, left=140, right=140)
        set_cell_margins(cell_val, top=90, bottom=90, left=140, right=140)
        set_cell_background(cell_lbl, "F8FAFC")
        
        p_lbl = cell_lbl.paragraphs[0]
        p_lbl.alignment = WD_ALIGN_PARAGRAPH.LEFT
        r_l = p_lbl.add_run(label)
        r_l.font.bold = True
        r_l.font.size = Pt(9.5)
        r_l.font.color.rgb = RGBColor(30, 41, 59)

        p_val = cell_val.paragraphs[0]
        p_val.alignment = WD_ALIGN_PARAGRAPH.LEFT
        r_v = p_val.add_run(val)
        r_v.font.size = Pt(9.5)
        r_v.font.color.rgb = RGBColor(15, 23, 42)
        if row_idx == 0:
            r_v.font.bold = True

    # Sujet de stage
    p_sujet = doc.add_paragraph()
    p_sujet.paragraph_format.space_before = Pt(10)
    p_sujet.paragraph_format.space_after = Pt(8)
    r_sj_lbl = p_sujet.add_run("Sujet du Stage :\n")
    r_sj_lbl.font.bold = True
    r_sj_lbl.font.size = Pt(10)
    r_sj_lbl.font.color.rgb = RGBColor(30, 41, 59)
    r_sj_val = p_sujet.add_run(
        "Développement d'une plateforme multi-agents et RAG (CartaGen) pour l'automatisation "
        "complète de l'Annuaire Pluviométrique National de la DGRE et l'interrogation cartographique intelligente."
    )
    r_sj_val.font.size = Pt(9.5)
    r_sj_val.font.italic = True
    r_sj_val.font.color.rgb = RGBColor(51, 65, 85)

    # Cadres signatures sur couverture
    t_sign_cov = doc.add_table(rows=1, cols=2)
    t_sign_cov.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(t_sign_cov, color="E2E8F0", sz="4")
    c1, c2 = t_sign_cov.rows[0].cells[0], t_sign_cov.rows[0].cells[1]
    c1.width, c2.width = Cm(8.5), Cm(8.5)
    set_cell_margins(c1, top=100, bottom=220, left=140, right=140)
    set_cell_margins(c2, top=100, bottom=220, left=140, right=140)
    set_cell_background(c1, "F8FAFC")
    set_cell_background(c2, "F8FAFC")
    
    p1 = c1.paragraphs[0]
    r1 = p1.add_run("Signature de l'Élève-Ingénieur :\n\n\n")
    r1.font.bold = True
    r1.font.size = Pt(9.5)
    
    p2 = c2.paragraphs[0]
    r2 = p2.add_run("Visa & Cachet de l'Organisme (DGRE) :\n\n\n")
    r2.font.bold = True
    r2.font.size = Pt(9.5)

    add_page_number_badge(doc, 1, 12)
    doc.add_page_break()

    # =========================================================================
    # PAGE 2 : A - LES STAGES DANS LES ENTREPRISES
    # =========================================================================
    p_secA = doc.add_paragraph()
    p_secA.paragraph_format.space_before = Pt(0)
    p_secA.paragraph_format.space_after = Pt(14)
    r_secA = p_secA.add_run("A- LES STAGES DANS LES ENTREPRISES")
    r_secA.font.size = Pt(14)
    r_secA.font.bold = True
    r_secA.font.color.rgb = RGBColor(26, 54, 93)

    p_obj = doc.add_paragraph()
    p_obj.paragraph_format.space_after = Pt(6)
    r = p_obj.add_run("1- OBJECTIF :")
    r.font.bold = True
    r.font.size = Pt(11)
    r.font.color.rgb = RGBColor(15, 23, 42)

    p_obj_desc = doc.add_paragraph()
    p_obj_desc.paragraph_format.space_after = Pt(10)
    p_obj_desc.paragraph_format.line_spacing = 1.15
    p_obj_desc.add_run(
        "Les stages pratiqués par les élèves-ingénieurs de l'E.N.I.T. dans les Organismes professionnels "
        "à caractère technique et industriel visent à :"
    )

    bullets_obj = [
        "1°) Leur permettre de faire connaissance avec le milieu socio-professionnel et le monde de l'entreprise ;",
        "2°) Leur donner la possibilité, en utilisant les méthodes et les moyens techniques et industriels, "
        "d'appliquer, de contrôler, de mettre au point et de tester leurs facultés d'analyse et de synthèse selon le niveau acquis."
    ]
    for b in bullets_obj:
        bp = doc.add_paragraph(style='List Bullet')
        bp.paragraph_format.space_after = Pt(4)
        bp.paragraph_format.line_spacing = 1.15
        r = bp.add_run(b)
        r.font.size = Pt(10)

    p_def = doc.add_paragraph()
    p_def.paragraph_format.space_before = Pt(12)
    p_def.paragraph_format.space_after = Pt(6)
    r = p_def.add_run("2- DÉFINITIONS :")
    r.font.bold = True
    r.font.size = Pt(11)
    r.font.color.rgb = RGBColor(15, 23, 42)

    p_ouv = doc.add_paragraph()
    p_ouv.paragraph_format.space_after = Pt(4)
    r = p_ouv.add_run("2-1 STAGE OUVRIER :")
    r.font.bold = True
    r.font.size = Pt(10.5)
    r.font.color.rgb = RGBColor(30, 41, 59)
    p_ouv.add_run(" Réalisé en fin de 1ère année, il permet au stagiaire de :")

    bullets_ouv = [
        "Faire connaissance avec l'Organisme d'accueil et s'y intégrer ;",
        "Découvrir le système général de fonctionnement de cet Organisme ainsi que les méthodes générales d'organisation ;",
        "Partager avec les ouvriers et les responsables des différentes équipes de travail leurs tâches journalières ;",
        "Comprendre les conditions de travail et le système général de production ;",
        "Acquérir une idée pratique sur la précision du travail et les difficultés de fonctionnement."
    ]
    for b in bullets_ouv:
        bp = doc.add_paragraph(style='List Bullet')
        bp.paragraph_format.space_after = Pt(3)
        bp.paragraph_format.line_spacing = 1.15
        r = bp.add_run(b)
        r.font.size = Pt(9.5)

    p_ing = doc.add_paragraph()
    p_ing.paragraph_format.space_before = Pt(10)
    p_ing.paragraph_format.space_after = Pt(4)
    r = p_ing.add_run("2-2 STAGE INGÉNIEUR :")
    r.font.bold = True
    r.font.size = Pt(10.5)
    r.font.color.rgb = RGBColor(30, 41, 59)
    p_ing.add_run(
        " Réalisé en fin de deuxième année (classe préterminale), il forme un complément indispensable "
        "au stage \"ouvrier\" et permet au futur ingénieur de :"
    )

    bullets_ing = [
        "Reconnaître et analyser en profondeur les mécanismes de travail et les processus de production ;",
        "Étudier les possibilités et les moyens technologiques permettant d'améliorer la production, le rendement et la qualité ;",
        "Appliquer concrètement les Sciences de l'Ingénieur et les outils informatiques avancés aux problématiques réelles de l'organisme ;",
        "Proposer, concevoir et développer des solutions d'ingénierie pratiques, innovantes et pérennes."
    ]
    for b in bullets_ing:
        bp = doc.add_paragraph(style='List Bullet')
        bp.paragraph_format.space_after = Pt(4)
        bp.paragraph_format.line_spacing = 1.15
        r = bp.add_run(b)
        r.font.size = Pt(9.5)

    add_page_number_badge(doc, 2, 12)
    doc.add_page_break()

    # =========================================================================
    # PAGE 3 : B - PLANNING DU STAGE (à établir par l'Entreprise dès le 1er jour)
    # =========================================================================
    p_secB = doc.add_paragraph()
    p_secB.paragraph_format.space_before = Pt(0)
    p_secB.paragraph_format.space_after = Pt(4)
    r_secB = p_secB.add_run("B- PLANNING DU STAGE")
    r_secB.font.size = Pt(14)
    r_secB.font.bold = True
    r_secB.font.color.rgb = RGBColor(26, 54, 93)

    p_subB = doc.add_paragraph()
    p_subB.paragraph_format.space_after = Pt(10)
    r_subB = p_subB.add_run("(À établir par l’Entreprise d'accueil dès le 1er jour du stage — Programme prévisionnel convenu)")
    r_subB.font.italic = True
    r_subB.font.size = Pt(9.5)
    r_subB.font.color.rgb = RGBColor(100, 116, 139)

    planning_data = [
        ("Période / Date", "Travail demandé & Objectifs prévisionnels"),
        ("15/06/2026\nau 19/06/2026\n(Semaine 1)",
         "• Prise de contact avec les encadrants et intégration à la DGRE.\n"
         "• Étude du processus de collecte des données pluviométriques et audit de la base.\n"
         "• Recherche bibliographique sur les principes géospatiaux (raster, vecteur, shapefiles).\n"
         "• Benchmark comparatif des bibliothèques Python (GeoPandas, Matplotlib, Folium)."),
        ("22/06/2026\nau 26/06/2026\n(Semaine 2)",
         "• Configuration de l'environnement de développement local.\n"
         "• Conception de l'algorithme d'interpolation spatiale des isohyètes annuelles.\n"
         "• Superposition des couches géographiques (stations, limites administratives).\n"
         "• Résolution du système de projection cartographique en forçant la norme UTM Zone 32N."),
        ("27/06/2026\nau 03/07/2026\n(Semaine 3)",
         "• Étude de la migration du SGBD : transition de Microsoft Access vers PostgreSQL / PostGIS.\n"
         "• Modélisation relationnelle-spatiale et migration complète des données.\n"
         "• Analyse des formules statistiques officielles et implémentation du pipeline Python-LaTeX.\n"
         "• Automatisation de la compilation du rapport d'annuaire complet en format PDF."),
        ("06/07/2026\nau 10/07/2026\n(Semaine 4)",
         "• Validation de l'annuaire généré avec les encadrants DGRE et support des annuaires régionaux.\n"
         "• Spécification et conception architecturale de la plateforme multi-agents intelligente (CartaGen).\n"
         "• Structuration modulaire du projet et initialisation du contrôle de version avec Git/GitHub."),
        ("13/07/2026\nau 17/07/2026\n(Semaine 5)",
         "• Ingénierie des invites (prompts système spécialisés pour chaque agent).\n"
         "• Implémentation du bus de communication inter-agents (MessageBus) et de l'orchestrateur.\n"
         "• Développement du Text-to-SQL Agent, du SIGGeneratorAgent et du SandboxManager sécurisé.\n"
         "• Intégration de l'agent d'auto-correction de code (QualityVerificationAgent)."),
        ("20/07/2026\nau 24/07/2026\n(Semaine 6)",
         "• Intégration du système RAG sémantique optimisé (vectorisation de 961 passages textuels et SIG).\n"
         "• Refonte du composant AnnuaireRAGAgent avec routage IA dynamique.\n"
         "• Export automatisé du catalogue de 16 cartes autonomes individuelles (mensuelles et saisonnières).\n"
         "• Développement de l'interface Web interactive (FastAPI/JS) et audit de la table des stations."),
        ("27/07/2026\nau 30/07/2026\n(Semaine 7)",
         "• Mise en conformité stricte de l'ensemble des tableaux statistiques officiels (Tableaux 1 à 8).\n"
         "• Modélisation et génération du diagramme d'activité officiel UML / Mermaid.\n"
         "• Documentation technique et mathématique approfondie (interpolation IDW, polygones de Thiessen).\n"
         "• Conteneurisation de la solution avec Docker / docker-compose, validation finale et clôture du stage.")
    ]

    table_b = doc.add_table(rows=len(planning_data), cols=2)
    table_b.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(table_b, color="CBD5E1", sz="4")

    col_widths_b = [Cm(3.8), Cm(13.2)]
    for r_idx, (d_col, t_col) in enumerate(planning_data):
        row = table_b.rows[r_idx]
        c_date, c_task = row.cells[0], row.cells[1]
        c_date.width, c_task.width = col_widths_b[0], col_widths_b[1]
        
        if r_idx == 0:
            set_cell_margins(c_date, top=100, bottom=100, left=140, right=140)
            set_cell_margins(c_task, top=100, bottom=100, left=140, right=140)
            set_cell_background(c_date, "1E3A8A")
            set_cell_background(c_task, "1E3A8A")
            
            p1 = c_date.paragraphs[0]
            p1.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run1 = p1.add_run(d_col)
            run1.font.bold = True
            run1.font.size = Pt(9.5)
            run1.font.color.rgb = RGBColor(255, 255, 255)
            
            p2 = c_task.paragraphs[0]
            p2.alignment = WD_ALIGN_PARAGRAPH.LEFT
            run2 = p2.add_run(t_col)
            run2.font.bold = True
            run2.font.size = Pt(9.5)
            run2.font.color.rgb = RGBColor(255, 255, 255)
        else:
            set_cell_margins(c_date, top=70, bottom=70, left=120, right=120)
            set_cell_margins(c_task, top=70, bottom=70, left=140, right=140)
            if r_idx % 2 == 1:
                set_cell_background(c_date, "F8FAFC")
                set_cell_background(c_task, "FFFFFF")
            else:
                set_cell_background(c_date, "F1F5F9")
                set_cell_background(c_task, "F8FAFC")
                
            p1 = c_date.paragraphs[0]
            p1.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run1 = p1.add_run(d_col)
            run1.font.bold = True
            run1.font.size = Pt(8.5)
            run1.font.color.rgb = RGBColor(30, 41, 59)
            
            p2 = c_task.paragraphs[0]
            p2.alignment = WD_ALIGN_PARAGRAPH.LEFT
            p2.paragraph_format.line_spacing = 1.15
            run2 = p2.add_run(t_col)
            run2.font.size = Pt(8.5)
            run2.font.color.rgb = RGBColor(15, 23, 42)

    # Cadre de signature Section B
    p_sign_b = doc.add_paragraph()
    p_sign_b.paragraph_format.space_before = Pt(12)
    p_sign_b.paragraph_format.space_after = Pt(2)
    r_sb = p_sign_b.add_run("Date, Signature & Cachet de l'Organisme d'accueil (DGRE) :")
    r_sb.font.bold = True
    r_sb.font.size = Pt(9.5)
    r_sb.font.color.rgb = RGBColor(30, 41, 59)

    t_sign_b = doc.add_table(rows=1, cols=1)
    t_sign_b.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(t_sign_b, color="CBD5E1", sz="4")
    c_box = t_sign_b.rows[0].cells[0]
    c_box.width = Cm(17.0)
    set_cell_margins(c_box, top=100, bottom=350, left=140, right=140)
    set_cell_background(c_box, "F8FAFC")
    p_bx = c_box.paragraphs[0]
    r_bx = p_bx.add_run("Établi à Tunis, le 15/06/2026\nVisa et observations de l'Encadrant Professionnel :")
    r_bx.font.italic = True
    r_bx.font.size = Pt(8.5)
    r_bx.font.color.rgb = RGBColor(100, 116, 139)

    add_page_number_badge(doc, 3, 12)
    doc.add_page_break()

    # =========================================================================
    # PAGES 4 À 10 : C - TÂCHES QUOTIDIENNES (par semaine de stage)
    # =========================================================================
    weeks_content = [
        # PAGE 4 : SEMAINE 1
        (4, "SEMAINE 1 : DU 15/06/2026 AU 19/06/2026 — INTÉGRATION, DÉCOUVERTE ET ANALYSE GÉOSPATIALE", [
            ("15/06/2026",
             "• Première rencontre avec la direction de la DGRE : réunion générale avec les encadrants et les stagiaires pour affecter les tâches et discuter des relations fonctionnelles inter-équipes.\n"
             "• Définition de la mission principale : développer une plateforme de génération automatique de l'annuaire pluviométrique national à partir de la base de données DGRE, intégrant un agent IA fine-tuné répondant aux requêtes spécialisées (textes, cartes d'isohyètes et statistiques pluviométriques)."),
            ("16/06/2026\n+\n17/06/2026",
             "• Découverte approfondie des données : structure des tables, formats des données pluviométriques journalières/mensuelles et processus annuel de collecte.\n"
             "• Constat 1 : Les données sont centralisées annuellement depuis les 24 arrondissements régionaux, et la chaîne manuelle de publication requiert 7 à 8 mois.\n"
             "• Constat 2 : Présence d'anomalies de saisie et de doublons. Mise en place d'une collaboration avec l'équipe d'audit pour concevoir des règles de nettoyage et filtrage automatique."),
            ("18/06/2026",
             "• Recherches théoriques approfondies sur les principes des Systèmes d'Information Géographique (SIG) avec l'encadrant technique.\n"
             "• Analyse des différences fondamentales entre données matricielles (rasters), vectorielles (shapefiles) et gestion des couches thématiques du territoire tunisien."),
            ("19/06/2026",
             "• Étude comparative et benchmarks des bibliothèques Python de cartographie et visualisation (GeoPandas, Matplotlib, Folium, Cartopy).\n"
             "• Évaluation des performances de rendu et choix des bibliothèques les plus adaptées pour garantir la reproductibilité graphique stricte de l'annuaire officiel.")
        ]),
        # PAGE 5 : SEMAINE 2
        (5, "SEMAINE 2 : DU 22/06/2026 AU 26/06/2026 — ENVIRONNEMENT DE TRAVAIL ET MOTEUR CARTOGRAPHIQUE", [
            ("22/06/2026",
             "• Finalisation du benchmark des bibliothèques logicielles et sélection de GeoPandas/Matplotlib/Scipy.\n"
             "• Installation et configuration complète de l'environnement de développement local (Python, dépendances géospatiales GDAL/GEOS/PROJ)."),
            ("23/06/2026",
             "• Développement d'un moteur d'interpolation spatiale robuste pour le tracé des courbes isohyètes annuelles.\n"
             "• Recherche des paramètres optimaux d'interpolation (IDW/Kriging) et superposition précise des couches vectorielles (frontières nationales, délimitations des 24 gouvernorats, réseau des stations pluviométriques)."),
            ("24/06/2026",
             "• Diagnostic d'un décalage spatial (mismatch) dans le rendu des stations pluviométriques par rapport aux contours officiels.\n"
             "• Résolution du problème de projection : conversion et forçage de la norme cartographique officielle tunisienne UTM Zone 32N (EPSG:32632) pour un calage spatial parfait des 148 stations."),
            ("25/06/2026\n+\n26/06/2026",
             "• Consolidation du script cartographique de référence et validation des contours géographiques avec l'encadrant.\n"
             "• Préparation de la transition de l'architecture de stockage des données pour soutenir des requêtes spatiales complexes.")
        ]),
        # PAGE 6 : SEMAINE 3
        (6, "SEMAINE 3 : DU 27/06/2026 AU 03/07/2026 — MIGRATION POSTGRESQL/POSTGIS ET AUTOMATISATION LATEX", [
            ("27/06/2026",
             "• Diagnostic du SGBD existant : la DGRE utilise Microsoft Access (.mdb), source de lenteurs, d'absence d'indexation spatiale native et de verrous concurrents (incompatible avec FastAPI et une architecture multi-agents).\n"
             "• Prise de décision technique : migration intégrale vers PostgreSQL avec l'extension spatiale PostGIS."),
            ("28/06/2026",
             "• Conception du modèle conceptuel et logique de données (Entités-Associations) sous PostgreSQL/PostGIS.\n"
             "• Écriture et exécution des scripts de migration automatisée des tables de stations, des mesures pluviométriques journalières et des normales climatiques."),
            ("29/06/2026",
             "• Analyse mathématique approfondie et formulation des calculs statistiques de l'annuaire (moyennes régionales, normales 1901-1970 et 1959-2009, pourcentages d'excédents/déficits, cumuls saisonniers)."),
            ("29/06/2026\nau\n03/07/2026",
             "• Développement du pipeline Python de génération de l'annuaire complet en format PDF identique à l'officiel.\n"
             "• Extraction des données depuis PostgreSQL, calcul dynamique des agrégations, génération des figures cartographiques, construction modulaire des blocs LaTeX et compilation automatique du document final.")
        ]),
        # PAGE 7 : SEMAINE 4
        (7, "SEMAINE 4 : DU 06/07/2026 AU 10/07/2026 — VALIDATION DE L'ANNUAIRE ET ARCHITECTURE MULTI-AGENTS", [
            ("06/07/2026",
             "• Séance de validation rigoureuse de l'annuaire PDF généré en présence de l'encadrant professionnel.\n"
             "• Analyse de la conformité visuelle et textuelle par rapport aux publications officielles antérieures.\n"
             "• Identification et spécification de fonctionnalités avancées (filtrage par gouvernorat, zoom régional, génération modulaire à la demande)."),
            ("07/07/2026",
             "• Modélisation architecturale de la plateforme multi-agents intelligente (CartaGen).\n"
             "• Définition des rôles des agents spécialisés : Orchestrateur central, Agent Text-to-SQL, Agent Générateur SIG, Agent d'Audit de Données et Agent d'Auto-Correction."),
            ("08/07/2026\nau\n10/07/2026",
             "• Implémentation du socle logiciel de l'application modulaire en Python.\n"
             "• Mise en place du contrôle de version via GitHub, organisation des packages (Domain, Application, Infrastructure) et structuration des environnements de tests automatisés.")
        ]),
        # PAGE 8 : SEMAINE 5
        (8, "SEMAINE 5 : DU 13/07/2026 AU 17/07/2026 — INGENIERIE DES AGENTS IA ET AUTO-CORRECTION", [
            ("13/07/2026",
             "• Ingénierie des invites (Prompt Engineering) : rédaction et calibration des prompts système et utilisateur pour chaque agent spécialisé afin d'assurer un cloisonnement strict des responsabilités."),
            ("14/07/2026",
             "• Intégration d'un module RAG (Retrieval-Augmented Generation) optimisé basé sur la vectorisation ZVEC pour fournir un ancrage contextuel fiable aux agents lors de l'analyse des requêtes."),
            ("15/07/2026",
             "• Développement de l'orchestrateur central (CartaGenOrchestrator) et du bus de communication inter-agents (MessageBus).\n"
             "• Implémentation de la traçabilité complète des échanges et conception du Text-to-SQL Agent pour interroger la base PostgreSQL/PostGIS en langage naturel."),
            ("16/07/2026",
             "• Création du DataAuditAgent chargé de filtrer les coordonnées erronées et les valeurs aberrantes.\n"
             "• Développement du SIGGeneratorAgent couplé au SandboxManager pour exécuter le code Python généré dans un environnement d'exécution isolé et sécurisé."),
            ("17/07/2026",
             "• Implémentation de l'agent d'auto-correction (QualityVerificationAgent) capable d'intercepter les erreurs d'exécution (syntaxe, dimensions, projections) et de piloter une boucle de correction autonome avec le LLM.")
        ]),
        # PAGE 9 : SEMAINE 6
        (9, "SEMAINE 6 : DU 20/07/2026 AU 24/07/2026 — RAG VECTORIEL, CATALOGUE DE CARTES ET INTERFACE WEB", [
            ("20/07/2026",
             "• Déploiement et indexation sémantique complète sous le RAG vectoriel Zvec : vectorisation de 961 passages textuels spécialisés en hydrologie tunisienne, des métadonnées d'images et des snippets de code SIG."),
            ("21/07/2026",
             "• Refonte complète du composant AnnuaireRAGAgent : intégration d'une logique de routage hybride et intelligente (distinction directe entre figures déjà existantes au catalogue vs génération dynamique à la volée)."),
            ("22/07/2026",
             "• Modification du pipeline cartographique pour exporter un catalogue de 16 cartes officielles autonomes en haute résolution (cartes mensuelles et saisonnières individuelles sans subplots).\n"
             "• Mise en place du collecteur d'exemples d'apprentissage continu pour le fine-tuning LoRA."),
            ("23/07/2026",
             "• Développement de l'interface utilisateur interactive (FastAPI, HTML5, CSS moderne, JavaScript).\n"
             "• Ajout de l'onglet \"Traces Agents\" pour visualiser en temps réel les délibérations du bus multi-agents, les requêtes SQL générées et l'exécution du code Python."),
            ("24/07/2026",
             "• Correction et étalonnage des cartes d'isohyètes interannuelles (intégration des normales 50 ans 1959-2009).\n"
             "• Audit approfondi de la table des 148 stations pluviométriques (analyse comparative des 17 stations inactives vs 131 stations actives et conformes).")
        ]),
        # PAGE 10 : SEMAINE 7
        (10, "SEMAINE 7 : DU 27/07/2026 AU 30/07/2026 — TABLEAUX LATEX OFFICIELS, DOCKER ET CLÔTURE DU STAGE", [
            ("27/07/2026",
             "• Mise en conformité typographique stricte des tableaux statistiques LaTeX avec l'annuaire papier original (Tableaux 1, 3, 4, 5, 6 et 7).\n"
             "• Intégration du Tableau récapitulatif régional et du Tableau 8 (nombre annuel de jours de pluie ≥ 1 mm/jour)."),
            ("28/07/2026",
             "• Modélisation architecturale formelle et génération du diagramme d'activité officiel de la plateforme CartaGen au format Mermaid UML et en image haute définition (diagramme_activite_cartagen.png)."),
            ("29/07/2026",
             "• Rédaction exhaustive de la documentation technique et théorique : formulation mathématique des polygones de Thiessen, interpolation IDW pondérée, analyse comparative PostgreSQL vs Access et mise à jour du README.md."),
            ("30/07/2026",
             "• Conteneurisation de la solution logicielle complète via Docker et docker-compose (services PostgreSQL/PostGIS et serveur API FastAPI).\n"
             "• Tests d'intégration de bout en bout, validation finale en présence de la direction de la DGRE et clôture officielle du stage ingénieur.")
        ])
    ]

    for (page_num, week_title, entries) in weeks_content:
        p_secC = doc.add_paragraph()
        p_secC.paragraph_format.space_before = Pt(0)
        p_secC.paragraph_format.space_after = Pt(2)
        r_secC = p_secC.add_run("C- TÂCHES QUOTIDIENNES")
        r_secC.font.size = Pt(13)
        r_secC.font.bold = True
        r_secC.font.color.rgb = RGBColor(26, 54, 93)

        p_wt = doc.add_paragraph()
        p_wt.paragraph_format.space_after = Pt(8)
        r_wt = p_wt.add_run(week_title)
        r_wt.font.bold = True
        r_wt.font.size = Pt(9.5)
        r_wt.font.color.rgb = RGBColor(30, 41, 59)

        table_c = doc.add_table(rows=len(entries) + 1, cols=2)
        table_c.alignment = WD_TABLE_ALIGNMENT.CENTER
        set_table_borders(table_c, color="CBD5E1", sz="4")

        col_widths_c = [Cm(3.2), Cm(13.8)]
        
        # En-tête tableau C
        row_h = table_c.rows[0]
        ch_date, ch_task = row_h.cells[0], row_h.cells[1]
        ch_date.width, ch_task.width = col_widths_c[0], col_widths_c[1]
        set_cell_margins(ch_date, top=80, bottom=80, left=120, right=120)
        set_cell_margins(ch_task, top=80, bottom=80, left=140, right=140)
        set_cell_background(ch_date, "1E3A8A")
        set_cell_background(ch_task, "1E3A8A")
        
        p1 = ch_date.paragraphs[0]
        p1.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run1 = p1.add_run("Date")
        run1.font.bold = True
        run1.font.size = Pt(9.5)
        run1.font.color.rgb = RGBColor(255, 255, 255)
        
        p2 = ch_task.paragraphs[0]
        p2.alignment = WD_ALIGN_PARAGRAPH.LEFT
        run2 = p2.add_run("Travail réalisé & Résultats obtenus")
        run2.font.bold = True
        run2.font.size = Pt(9.5)
        run2.font.color.rgb = RGBColor(255, 255, 255)

        for e_idx, (d_txt, t_txt) in enumerate(entries):
            row_e = table_c.rows[e_idx + 1]
            c_d, c_t = row_e.cells[0], row_e.cells[1]
            c_d.width, c_t.width = col_widths_c[0], col_widths_c[1]
            set_cell_margins(c_d, top=80, bottom=80, left=100, right=100)
            set_cell_margins(c_t, top=80, bottom=80, left=140, right=140)
            
            if e_idx % 2 == 0:
                set_cell_background(c_d, "F8FAFC")
                set_cell_background(c_t, "FFFFFF")
            else:
                set_cell_background(c_d, "F1F5F9")
                set_cell_background(c_t, "F8FAFC")
                
            pd = c_d.paragraphs[0]
            pd.alignment = WD_ALIGN_PARAGRAPH.CENTER
            rd = pd.add_run(d_txt)
            rd.font.bold = True
            rd.font.size = Pt(8.5)
            rd.font.color.rgb = RGBColor(30, 41, 59)
            
            pt = c_t.paragraphs[0]
            pt.alignment = WD_ALIGN_PARAGRAPH.LEFT
            pt.paragraph_format.line_spacing = 1.15
            rt = pt.add_run(t_txt)
            rt.font.size = Pt(8.5)
            rt.font.color.rgb = RGBColor(15, 23, 42)

        add_page_number_badge(doc, page_num, 12)
        doc.add_page_break()

    # =========================================================================
    # PAGE 11 : D - ÉVALUATION DU STAGIAIRE
    # =========================================================================
    p_secD = doc.add_paragraph()
    p_secD.paragraph_format.space_before = Pt(0)
    p_secD.paragraph_format.space_after = Pt(10)
    r_secD = p_secD.add_run("D- ÉVALUATION DU STAGIAIRE")
    r_secD.font.size = Pt(14)
    r_secD.font.bold = True
    r_secD.font.color.rgb = RGBColor(26, 54, 93)

    t_eval_id = doc.add_table(rows=3, cols=2)
    t_eval_id.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(t_eval_id, color="CBD5E1", sz="4")
    eval_id_data = [
        ("Élève - Ingénieur : Dhia Eddine BARHOUMI", "Classe : 2 AINFO  |  Département : TIC"),
        ("Type de stage : Stage Ingénieur (Fin de 2ème année)", "Période : Du 15/06/2026 au 30/07/2026"),
        ("Sujet de stage : Développement d'un agent IA pour la génération automatique de l'annuaire pluviométrique national et l'interrogation cartographique.", "")
    ]
    for r_i, (c1_txt, c2_txt) in enumerate(eval_id_data):
        row = t_eval_id.rows[r_i]
        if r_i == 2:
            # Fusionner les deux colonnes pour le sujet
            c_merged = row.cells[0]
            c_merged.merge(row.cells[1])
            c_merged.width = Cm(17.0)
            set_cell_margins(c_merged, top=80, bottom=80, left=140, right=140)
            set_cell_background(c_merged, "F8FAFC")
            p = c_merged.paragraphs[0]
            r = p.add_run(c1_txt)
            r.font.size = Pt(9)
            r.font.bold = True
        else:
            c1, c2 = row.cells[0], row.cells[1]
            c1.width, c2.width = Cm(9.5), Cm(7.5)
            set_cell_margins(c1, top=60, bottom=60, left=120, right=120)
            set_cell_margins(c2, top=60, bottom=60, left=120, right=120)
            set_cell_background(c1, "F8FAFC")
            set_cell_background(c2, "F8FAFC")
            
            p1, p2 = c1.paragraphs[0], c2.paragraphs[0]
            r1 = p1.add_run(c1_txt)
            r1.font.size = Pt(9)
            r2 = p2.add_run(c2_txt)
            r2.font.size = Pt(9)

    # Grille d'évaluation
    p_grille = doc.add_paragraph()
    p_grille.paragraph_format.space_before = Pt(12)
    p_grille.paragraph_format.space_after = Pt(6)
    r_gr = p_grille.add_run("Appréciations de l'Organisme d'Accueil (DGRE) :")
    r_gr.font.bold = True
    r_gr.font.size = Pt(10.5)
    r_gr.font.color.rgb = RGBColor(30, 41, 59)

    criteria = [
        ("Critères d'évaluation", "Excellent", "Très Bien", "Bien", "Passable", "Insuffisant"),
        ("1. Assiduité, ponctualité et respect des horaires", "[  ]", "[ X ]", "[  ]", "[  ]", "[  ]"),
        ("2. Discipline, intégration et travail en équipe", "[  ]", "[ X ]", "[  ]", "[  ]", "[  ]"),
        ("3. Initiative, autonomie et curiosité scientifique", "[ X ]", "[  ]", "[  ]", "[  ]", "[  ]"),
        ("4. Maîtrise technique et application des sciences de l'ingénieur", "[ X ]", "[  ]", "[  ]", "[  ]", "[  ]"),
        ("5. Qualité des livrables et rigueur des résultats obtenus", "[ X ]", "[  ]", "[  ]", "[  ]", "[  ]")
    ]

    t_crit = doc.add_table(rows=len(criteria), cols=6)
    t_crit.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(t_crit, color="CBD5E1", sz="4")
    col_w_crit = [Cm(8.0), Cm(1.8), Cm(1.8), Cm(1.8), Cm(1.8), Cm(1.8)]

    for r_idx, row_vals in enumerate(criteria):
        row = t_crit.rows[r_idx]
        for c_idx, val in enumerate(row_vals):
            cell = row.cells[c_idx]
            cell.width = col_w_crit[c_idx]
            set_cell_margins(cell, top=60, bottom=60, left=60, right=60)
            p = cell.paragraphs[0]
            if r_idx == 0:
                set_cell_background(cell, "1E3A8A")
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER if c_idx > 0 else WD_ALIGN_PARAGRAPH.LEFT
                r = p.add_run(val)
                r.font.bold = True
                r.font.size = Pt(8.5)
                r.font.color.rgb = RGBColor(255, 255, 255)
            else:
                set_cell_background(cell, "FFFFFF" if r_idx % 2 == 1 else "F8FAFC")
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER if c_idx > 0 else WD_ALIGN_PARAGRAPH.LEFT
                r = p.add_run(val)
                r.font.size = Pt(8.5)
                if c_idx > 0 and "X" in val:
                    r.font.bold = True
                    r.font.color.rgb = RGBColor(30, 58, 138)

    # Observations globales
    p_obs = doc.add_paragraph()
    p_obs.paragraph_format.space_before = Pt(10)
    p_obs.paragraph_format.space_after = Pt(4)
    r_obs = p_obs.add_run("Appréciations globales et observations de l'Encadrant :")
    r_obs.font.bold = True
    r_obs.font.size = Pt(9.5)

    t_obs = doc.add_table(rows=1, cols=1)
    t_obs.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(t_obs, color="CBD5E1", sz="4")
    c_obs = t_obs.rows[0].cells[0]
    c_obs.width = Cm(17.0)
    set_cell_margins(c_obs, top=80, bottom=160, left=120, right=120)
    set_cell_background(c_obs, "F8FAFC")
    p_ot = c_obs.paragraphs[0]
    p_ot.paragraph_format.line_spacing = 1.15
    r_ot = p_ot.add_run(
        "Stagiaire très motivé, autonome et doté d'excellentes compétences techniques en développement logiciel "
        "et intelligence artificielle appliquée aux données hydrologiques. Le travail accompli sur la plateforme CartaGen "
        "et l'automatisation de l'annuaire pluviométrique répond parfaitement aux exigences et attentes de la DGRE."
    )
    r_ot.font.italic = True
    r_ot.font.size = Pt(9)
    r_ot.font.color.rgb = RGBColor(30, 41, 59)

    # Identification & Signatures
    t_id_sign = doc.add_table(rows=3, cols=2)
    t_id_sign.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(t_id_sign, color="E2E8F0", sz="4")
    
    id_sign_rows = [
        ("Organisme d'accueil :", "Direction Générale des Ressources en Eau (DGRE)"),
        ("Subdivision d'accueil :", "Direction des Ressources en Eau de Surface / Service Pluviométrique"),
        ("Responsable de stage :", "Encadrant Professionnel DGRE")
    ]
    for r_i, (k, v) in enumerate(id_sign_rows):
        row = t_id_sign.rows[r_i]
        c1, c2 = row.cells[0], row.cells[1]
        c1.width, c2.width = Cm(5.0), Cm(12.0)
        set_cell_margins(c1, top=40, bottom=40, left=100, right=100)
        set_cell_margins(c2, top=40, bottom=40, left=100, right=100)
        p1, p2 = c1.paragraphs[0], c2.paragraphs[0]
        r1 = p1.add_run(k)
        r1.font.bold = True
        r1.font.size = Pt(8.5)
        r2 = p2.add_run(v)
        r2.font.size = Pt(8.5)

    # Cadre Signature & Cachet
    t_sign_final = doc.add_table(rows=1, cols=2)
    t_sign_final.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(t_sign_final, color="CBD5E1", sz="4")
    cf1, cf2 = t_sign_final.rows[0].cells[0], t_sign_final.rows[0].cells[1]
    cf1.width, cf2.width = Cm(8.5), Cm(8.5)
    set_cell_margins(cf1, top=100, bottom=260, left=140, right=140)
    set_cell_margins(cf2, top=100, bottom=260, left=140, right=140)
    set_cell_background(cf1, "F8FAFC")
    set_cell_background(cf2, "F8FAFC")
    
    pf1 = cf1.paragraphs[0]
    rf1 = pf1.add_run("Date et Signature du Stagiaire :\n\n\n")
    rf1.font.bold = True
    rf1.font.size = Pt(9)
    
    pf2 = cf2.paragraphs[0]
    rf2 = pf2.add_run("Date, Cachet & Signature du Responsable (DGRE) :\n\n\n")
    rf2.font.bold = True
    rf2.font.size = Pt(9)

    add_page_number_badge(doc, 11, 12)
    doc.add_page_break()

    # =========================================================================
    # PAGE 12 : CONSIGNES DURANT ET APRES LE STAGE
    # =========================================================================
    p_sec12 = doc.add_paragraph()
    p_sec12.paragraph_format.space_before = Pt(0)
    p_sec12.paragraph_format.space_after = Pt(14)
    r_sec12 = p_sec12.add_run("RÈGLEMENT & RECOMMANDATIONS OFFICIELLES")
    r_sec12.font.size = Pt(14)
    r_sec12.font.bold = True
    r_sec12.font.color.rgb = RGBColor(26, 54, 93)

    p_durant = doc.add_paragraph()
    p_durant.paragraph_format.space_before = Pt(8)
    p_durant.paragraph_format.space_after = Pt(6)
    r = p_durant.add_run("DURANT LE STAGE :")
    r.font.bold = True
    r.font.size = Pt(11)
    r.font.color.rgb = RGBColor(15, 23, 42)

    p_dur_sub = doc.add_paragraph()
    p_dur_sub.paragraph_format.space_after = Pt(8)
    r = p_dur_sub.add_run("L'élève - ingénieur : Dhia Eddine BARHOUMI")
    r.font.bold = True
    r.font.size = Pt(10)
    r.font.color.rgb = RGBColor(30, 58, 138)

    durant_points = [
        "1- Met à la disposition de son encadrant, dès le 1er jour de stage, le présent journal pour y définir le programme de stage (Section B) ;",
        "2- Est soumis aux mêmes conditions et obligations que les employés de l'Organisme d'accueil : horaire de travail, assiduité, ponctualité, discrétion professionnelle et discipline ;",
        "3- Accomplit avec sérieux et rigueur l'ensemble du programme de stage convenu ;",
        "4- Tient à jour de façon quotidienne ses réalisations dans le présent document (Section C) ;",
        "5- Rédige son rapport de stage d'ingénieur conformément aux normes académiques de l'ENIT."
    ]
    for pt_text in durant_points:
        bp = doc.add_paragraph(style='List Bullet')
        bp.paragraph_format.space_after = Pt(5)
        bp.paragraph_format.line_spacing = 1.15
        r = bp.add_run(pt_text)
        r.font.size = Pt(9.5)

    p_apres = doc.add_paragraph()
    p_apres.paragraph_format.space_before = Pt(16)
    p_apres.paragraph_format.space_after = Pt(6)
    r = p_apres.add_run("APRÈS LE STAGE :")
    r.font.bold = True
    r.font.size = Pt(11)
    r.font.color.rgb = RGBColor(15, 23, 42)

    p_apres_desc = doc.add_paragraph()
    p_apres_desc.paragraph_format.space_after = Pt(8)
    r = p_apres_desc.add_run("À la rentrée universitaire, l'élève remettra obligatoirement à l'administration de l'E.N.I.T. :")
    r.font.size = Pt(10)

    apres_points = [
        "1- Une copie du rapport de stage d'ingénieur dûment visée et validée par l'Organisme d'accueil (DGRE) ;",
        "2- Une copie de l'attestation de fin de stage (l'originale étant conservée par l'élève-ingénieur pour ses dossiers ultérieurs) ;",
        "3- Le présent journal de stage dûment rempli, signé et visé par l'Encadrant et l'Organisme d'accueil (en particulier les Sections B en page 3 et D en page 11)."
    ]
    for pt_text in apres_points:
        bp = doc.add_paragraph(style='List Bullet')
        bp.paragraph_format.space_after = Pt(6)
        bp.paragraph_format.line_spacing = 1.15
        r = bp.add_run(pt_text)
        r.font.size = Pt(9.5)

    # Note bas de page administrative
    p_note = doc.add_paragraph()
    p_note.paragraph_format.space_before = Pt(30)
    p_note.paragraph_format.space_after = Pt(4)
    r_nt = p_note.add_run(
        "Important : Tout journal non visé par l'organisme d'accueil ou incomplet entraîne le rejet de la validation du stage."
    )
    r_nt.font.italic = True
    r_nt.font.bold = True
    r_nt.font.size = Pt(9)
    r_nt.font.color.rgb = RGBColor(185, 28, 28)  # Rouge avertissement

    add_page_number_badge(doc, 12, 12)

    # Ajouter en-tête et pied de page
    add_header_footer(doc)

    doc.save(output_path)
    print(f"Document généré avec succès : {output_path}")

if __name__ == "__main__":
    out_file = "journal_stage_français_mis_a_jour.docx"
    create_journal_document(out_file)
