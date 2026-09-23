import os
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.enum.shapes import MSO_SHAPE

prs = Presentation()
prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)

# Color Palette
NAVY = RGBColor(15, 41, 66)       # #0F2942
WATER_BLUE = RGBColor(0, 119, 182) # #0077B6
ACCENT_BLUE = RGBColor(56, 189, 248) # #38BDF8
TEXT_DARK = RGBColor(30, 41, 59)   # #1E293B
MUTED = RGBColor(100, 116, 139)    # #64748B
BG_LIGHT = RGBColor(248, 250, 252) # #F8FAFC
CARD_BG = RGBColor(255, 255, 255)
ALERT_RED = RGBColor(220, 38, 38)
GREEN = RGBColor(16, 185, 129)

blank_layout = prs.slide_layouts[6]

def add_header(slide, title_text, category_text=""):
    # Header container
    header_box = slide.shapes.add_textbox(Inches(0.8), Inches(0.4), Inches(11.7), Inches(1.1))
    tf = header_box.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_top = tf.margin_right = tf.margin_bottom = 0
    
    if category_text:
        p_cat = tf.paragraphs[0]
        p_cat.text = category_text.upper()
        p_cat.font.size = Pt(11)
        p_cat.font.bold = True
        p_cat.font.color.rgb = WATER_BLUE
        p_title = tf.add_paragraph()
    else:
        p_title = tf.paragraphs[0]
        
    p_title.text = title_text
    p_title.font.size = Pt(26)
    p_title.font.bold = True
    p_title.font.color.rgb = NAVY

def add_bullet(tf, text, level=0, bold_words=None, font_size=15, color=TEXT_DARK):
    p = tf.add_paragraph()
    p.level = level
    p.space_after = Pt(8)
    p.font.size = Pt(font_size)
    p.font.color.rgb = color
    p.text = text
    if bold_words:
        p.font.bold = False

def set_slide_notes(slide, notes_text):
    notes_slide = slide.notes_slide
    tf = notes_slide.notes_text_frame
    tf.text = notes_text

# =========================================================================
# SLIDE 1: TITLE SLIDE
# =========================================================================
s1 = prs.slides.add_slide(blank_layout)
# Dark background banner
bg_shape = s1.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(13.333), Inches(7.5))
bg_shape.fill.solid()
bg_shape.fill.fore_color.rgb = NAVY
bg_shape.line.fill.background()

tb1 = s1.shapes.add_textbox(Inches(1.0), Inches(1.2), Inches(11.3), Inches(5.0))
tf1 = tb1.text_frame
tf1.word_wrap = True

p = tf1.paragraphs[0]
p.text = "NATIONAL ENGINEERING DIPLOMA DEFENSE | COMPUTER & GEOMATICS"
p.font.size = Pt(13)
p.font.bold = True
p.font.color.rgb = ACCENT_BLUE
p.space_after = Pt(20)

p2 = tf1.add_paragraph()
p2.text = "Rainfull Cartagen"
p2.font.size = Pt(44)
p2.font.bold = True
p2.font.color.rgb = RGBColor(255, 255, 255)
p2.space_after = Pt(12)

p3 = tf1.add_paragraph()
p3.text = "Engineering an Autonomous Multi-Agent Spatial AI Platform for National Hydrological Cartography and Yearbook Generation"
p3.font.size = Pt(20)
p3.font.color.rgb = RGBColor(203, 213, 225)
p3.space_after = Pt(40)

p4 = tf1.add_paragraph()
p4.text = "Author: Dhia Eddine BARHOUMI       |       Host Supervisor: Eng. Alaa Eddine JELASSI"
p4.font.size = Pt(16)
p4.font.bold = True
p4.font.color.rgb = RGBColor(255, 255, 255)
p4.space_after = Pt(8)

p5 = tf1.add_paragraph()
p5.text = "Direction Générale des Ressources en Eau (DGRE)   •   École Nationale d'Ingénieurs de Tunis (ENIT)"
p5.font.size = Pt(14)
p5.font.color.rgb = ACCENT_BLUE

set_slide_notes(s1, 
"Bonjour Monsieur le Président, chers membres du jury. Je suis particulièrement honoré de vous présenter aujourd'hui les résultats de mon projet de fin d'études d'ingénieur intitulé 'Rainfull Cartagen'. Ce projet a été réalisé au sein de la Direction Générale des Ressources en Eau (DGRE) sous l'encadrement de l'ingénieur Alaa Eddine JELASSI, et porte sur la conception et le déploiement d'une plateforme d'intelligence artificielle spatiale multi-agents pour automatiser intégralement la cartographie hydrologique nationale et la production de l'annuaire pluviométrique officiel.")

# =========================================================================
# SLIDE 2: CONTEXT
# =========================================================================
s2 = prs.slides.add_slide(blank_layout)
add_header(s2, "National Water Scarcity & The DGRE Mandate", "1. Institutional Background")

tb2 = s2.shapes.add_textbox(Inches(0.8), Inches(1.8), Inches(6.5), Inches(5.0))
tf2 = tb2.text_frame
tf2.word_wrap = True
add_bullet(tf2, "Tunisia's Hydro-Climatic Reality:")
add_bullet(tf2, "• Predominantly semi-arid Mediterranean bioclimatic zones with extreme rainfall variability.", 1)
add_bullet(tf2, "• Irrigated agriculture mobilizes ~80% of national water resources, creating acute vulnerability.", 1)
add_bullet(tf2, "The DGRE Mandate (Decree 2001-419):")
add_bullet(tf2, "• Sovereign technical authority under the Ministry of Agriculture (MARHP).", 1)
add_bullet(tf2, "• Plans, monitors, archives, and publishes national surface and groundwater records.", 1)
add_bullet(tf2, "The National Pluviometric Network:")
add_bullet(tf2, "• 148 certified reference stations across 24 governorates and 6 natural regions.", 1)
add_bullet(tf2, "• Mandated statutory publication: the official annual 'Annuaire Pluviométrique'.", 1)

if os.path.exists("figures/carte_reseau_148_stations.png"):
    s2.shapes.add_picture("figures/carte_reseau_148_stations.png", Inches(7.7), Inches(1.6), width=Inches(4.8))

set_slide_notes(s2,
"En Tunisie, l'eau est une ressource vitale sous tension extrême : 80% de notre dotation hydrique est absorbée par l'agriculture irriguée. La DGRE est l'institution souveraine qui surveille ce patrimoine grâce à un réseau de 148 stations pluviométriques de référence réparties sur les 24 gouvernorats. Sa mission cardinale est de produire chaque année l'Annuaire Pluviométrique officiel, qui sert de base au calcul du bilan hydrique national et aux décisions stratégiques sur les barrages.")

# =========================================================================
# SLIDE 3: PROBLEM STATEMENT
# =========================================================================
s3 = prs.slides.add_slide(blank_layout)
add_header(s3, "The Diagnostic: An 8-Month Manual Bottleneck", "2. Problem Statement")

tb3_left = s3.shapes.add_textbox(Inches(0.8), Inches(1.8), Inches(6.0), Inches(5.0))
tf3_left = tb3_left.text_frame
tf3_left.word_wrap = True
add_bullet(tf3_left, "Structural Bottlenecks Observed in Production:")
add_bullet(tf3_left, "• 8 Months Latency: Yearbook published almost a year after the hydrological cycle ends.", 1)
add_bullet(tf3_left, "• Extreme Data Fragmentation: 24 CRDAs transmitting decentralized, heterogeneous Access (.mdb) files and manual Excel sheets.", 1)
add_bullet(tf3_left, "• Zero Native Spatial Database: MS Access cannot calculate geodetic overlays or polygons; technicians export data manually to Surfer/ArcView.", 1)
add_bullet(tf3_left, "• Error Propagation: Manually updated gauges require recalculating entire spreadsheets and redrawing contour maps.", 1)

# Diagram box on right
card = s3.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(7.4), Inches(1.8), Inches(5.1), Inches(4.8))
card.fill.solid()
card.fill.fore_color.rgb = BG_LIGHT
card.line.color.rgb = WATER_BLUE

tb3_diag = s3.shapes.add_textbox(Inches(7.6), Inches(2.0), Inches(4.7), Inches(4.4))
tf3_diag = tb3_diag.text_frame
tf3_diag.word_wrap = True
p = tf3_diag.paragraphs[0]
p.text = "Legacy Workflow Failure Points:"
p.font.bold = True
p.font.size = Pt(16)
p.font.color.rgb = NAVY
p.space_after = Pt(10)
add_bullet(tf3_diag, "1. Daily manual gauge reading at 24 CRDAs", 0, font_size=13)
add_bullet(tf3_diag, "2. Fragmented Access & Excel local storage", 0, font_size=13)
add_bullet(tf3_diag, "3. Monthly transmission via email / USB", 0, font_size=13)
add_bullet(tf3_diag, "4. Manual concatenation in central Access DB", 0, font_size=13)
add_bullet(tf3_diag, "5. Excel formulas for Thiessen polygon weights", 0, font_size=13)
add_bullet(tf3_diag, "6. Manual contouring in desktop GIS", 0, font_size=13)
add_bullet(tf3_diag, "7. TOTAL DELAY: 7 TO 8 MONTHS", 0, font_size=15, color=ALERT_RED)

set_slide_notes(s3,
"Le diagnostic que j'ai mené lors de mon immersion à la DGRE a révélé un problème critique : l'élaboration de l'annuaire prenait entre 7 et 8 mois de travail manuel intensif ! Les données provenaient de 24 commissariats régionaux sous forme de fichiers Access et Excel hétérogènes. Comme Access ne gère pas les géométries, les techniciens devaient exporter manuellement les points vers Surfer ou ArcView, calculer les coefficients de Thiessen à la main, et assembler le document sous Word. Une seule erreur imposait de tout recalculer.")

# =========================================================================
# SLIDE 4: SOLUTION & OBJECTIVES
# =========================================================================
s4 = prs.slides.add_slide(blank_layout)
add_header(s4, "Rainfull Cartagen: Autonomous Spatial AI Platform", "3. Solution Architecture")

tb4 = s4.shapes.add_textbox(Inches(0.8), Inches(1.8), Inches(7.5), Inches(5.0))
tf4 = tb4.text_frame
tf4.word_wrap = True
add_bullet(tf4, "Core Engineering Pillars:")
add_bullet(tf4, "1. Unified Spatial Infrastructure: PostgreSQL 16 + PostGIS 3.4 in official UTM 32N (EPSG:32632).", 1)
add_bullet(tf4, "2. Hydrological Algorithms Engine: Vectorized Voronoi/Thiessen surface integration & IDW continuous interpolation.", 1)
add_bullet(tf4, "3. Deliberative Multi-Agent AI: Supervisor Pattern coordinating Text-to-SQL, Spatial GIS, and Quality Verification agents.", 1)
add_bullet(tf4, "4. Defensive AST Sandbox: Static analysis of Python syntax trees ensuring zero execution of dangerous calls.", 1)

# Metric card
mcard = s4.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(8.8), Inches(1.8), Inches(3.7), Inches(4.8))
mcard.fill.solid()
mcard.fill.fore_color.rgb = NAVY
mcard.line.fill.background()

mtb = s4.shapes.add_textbox(Inches(9.0), Inches(2.2), Inches(3.3), Inches(4.0))
mtf = mtb.text_frame
mtf.word_wrap = True
p = mtf.paragraphs[0]
p.alignment = PP_ALIGN.CENTER
p.text = "PRODUCTION SPEEDUP"
p.font.size = Pt(14)
p.font.bold = True
p.font.color.rgb = ACCENT_BLUE
p.space_after = Pt(14)

p2 = mtf.add_paragraph()
p2.alignment = PP_ALIGN.CENTER
p2.text = "-99.98%"
p2.font.size = Pt(44)
p2.font.bold = True
p2.font.color.rgb = RGBColor(255, 255, 255)
p2.space_after = Pt(14)

p3 = mtf.add_paragraph()
p3.alignment = PP_ALIGN.CENTER
p3.text = "From 8 Months to 118 Seconds\n\n• 100% Numerical Parity\n• 100+ Page Official PDF\n• Conversational Natural Language GIS"
p3.font.size = Pt(14)
p3.font.color.rgb = RGBColor(203, 213, 225)

set_slide_notes(s4,
"Pour résoudre ce goulot d'étranglement, j'ai conçu et développé Rainfull Cartagen. La plateforme repose sur quatre piliers : une base spatiale unifiée PostGIS en projection UTM 32N, un moteur mathématique pour Thiessen et l'IDW, un système multi-agents délibératif sous le patron Superviseur, et une sandbox de sécurité par analyseur AST. Le résultat est spectaculaire : nous passons de 8 mois à 118 secondes pour compiler l'annuaire complet avec une parité numérique absolue.")

# =========================================================================
# SLIDE 5: SPATIAL INFRASTRUCTURE
# =========================================================================
s5 = prs.slides.add_slide(blank_layout)
add_header(s5, "Spatial Infrastructure & Geodetic Rectification", "4. PostGIS & Geodesy")

tb5 = s5.shapes.add_textbox(Inches(0.8), Inches(1.8), Inches(6.5), Inches(5.0))
tf5 = tb5.text_frame
tf5.word_wrap = True
add_bullet(tf5, "PostgreSQL 16 + PostGIS 3.4 Spatial Schema:")
add_bullet(tf5, "• stations: 148 certified gauges with geometry geom Point(32632).", 1)
add_bullet(tf5, "• boundaries: 24 governorates & 6 natural regions as MultiPolygon(32632).", 1)
add_bullet(tf5, "• observations: Daily & monthly rainfall + 50-year normals (1959–2009).", 1)
add_bullet(tf5, "The Geodetic Rectification Challenge:")
add_bullet(tf5, "• Diagnostic: Regional files mixed WGS84 angular degrees and projected values.", 1)
add_bullet(tf5, "• Discovery: 17 stations had missing or inactive status in recent cycles.", 1)
add_bullet(tf5, "• Solution: Reprojected all layers to EPSG:32632 (UTM Zone 32N) preserving metric Euclidean area computation for Voronoi clipping.", 1)

if os.path.exists("figures/regions_naturelles_tunisie.png"):
    s5.shapes.add_picture("figures/regions_naturelles_tunisie.png", Inches(7.8), Inches(1.6), width=Inches(4.7))

set_slide_notes(s5,
"La première étape fondamentale a été de poser une infrastructure spatiale saine. J'ai unifié les données dans PostgreSQL 16 avec l'extension PostGIS. L'un de mes apports majeurs a été la rectification géodésique : les fichiers régionaux mélangeaient des coordonnées GPS en degrés décimaux et des projections anciennes. J'ai tout standardisé en UTM Zone 32N (EPSG:32632), ce qui est indispensable pour calculer avec exactitude les surfaces métriques des polygones de Voronoi.")

# =========================================================================
# SLIDE 6: MATHEMATICAL RIGOR (THIESSEN vs IDW)
# =========================================================================
s6 = prs.slides.add_slide(blank_layout)
add_header(s6, "Mathematical Rigor: Discrete vs. Continuous Integration", "5. Hydrological Algorithms")

tb6 = s6.shapes.add_textbox(Inches(0.8), Inches(1.8), Inches(6.5), Inches(5.0))
tf6 = tb6.text_frame
tf6.word_wrap = True
add_bullet(tf6, "1. Thiessen Polygons (Discrete Area Integration):")
add_bullet(tf6, "• Mandated by DGRE for official regional water balance tables.", 1)
add_bullet(tf6, "• Planar space decomposed into Voronoi polygons; station weight w_i = Area(V_i ∩ R) / Area(R).", 1)
add_bullet(tf6, "• Implemented via SciPy Voronoi + Shapely geometric clipping.", 1)
add_bullet(tf6, "2. Inverse Distance Weighting (Continuous Gradient):")
add_bullet(tf6, "• Mandated for plotting smooth isohyet contour lines across the nation.", 1)
add_bullet(tf6, "• Vectorized NumPy matrix computation with power exponent alpha = 2.0 and smoothing epsilon = 0.5m.", 1)

if os.path.exists("figures/comparaison_thiessen_idw.png"):
    s6.shapes.add_picture("figures/comparaison_thiessen_idw.png", Inches(7.6), Inches(1.6), width=Inches(5.0))

set_slide_notes(s6,
"Sur le plan méthodologique, la DGRE utilise deux approches complémentaires : la méthode des polygones de Thiessen pour les bilans régionaux officiels, où chaque station reçoit un poids proportionnel à sa zone d'influence Voronoi, et l'interpolation IDW vectorisée (puissance 2) pour tracer les lignes d'isohyètes continues. J'ai entièrement implémenté et vectorisé ces deux algorithmes en Python avec NumPy, SciPy et Shapely, éliminant tout calcul manuel.")

# =========================================================================
# SLIDE 7: MULTI-AGENT ARCHITECTURE
# =========================================================================
s7 = prs.slides.add_slide(blank_layout)
add_header(s7, "Deliberative Multi-Agent Architecture", "6. Artificial Intelligence")

tb7 = s7.shapes.add_textbox(Inches(0.8), Inches(1.8), Inches(6.5), Inches(5.0))
tf7 = tb7.text_frame
tf7.word_wrap = True
add_bullet(tf7, "The Supervisor Multi-Agent Pattern (LangGraph):")
add_bullet(tf7, "• Supervisor Router: Parses natural language intent into domain goals.", 1)
add_bullet(tf7, "• Text-to-SQL Agent: Generates optimized read-only PostGIS queries with spatial predicates.", 1)
add_bullet(tf7, "• GIS Python Agent: Synthesizes Matplotlib / GeoPandas isohyet maps.", 1)
add_bullet(tf7, "• Quality Verification Agent: Validates numerical coherence and boundary constraints.", 1)
add_bullet(tf7, "Closed-Loop Self-Correction:")
add_bullet(tf7, "• If SQL or script execution fails, error feedback is returned to the agent for dynamic self-healing (up to 3 iterations).", 1)

if os.path.exists("figures/diagramme_activite_multiagents.png"):
    s7.shapes.add_picture("figures/diagramme_activite_multiagents.png", Inches(7.7), Inches(1.6), width=Inches(4.9))

set_slide_notes(s7,
"Pour l'interaction avec le système, j'ai rejeté l'approche d'un prompt unique monolithique au profit d'une architecture multi-agents délibérative basée sur le patron Superviseur. L'agent superviseur reçoit la demande en langage naturel et délègue la tâche à des sous-agents spécialisés : l'agent SQL pour interroger PostGIS, l'agent Géomatique pour tracer les cartes, et l'agent Qualité qui vérifie la plausibilité physique des résultats et pilote une boucle d'auto-correction en cas d'erreur.")

# =========================================================================
# SLIDE 8: DEFENSIVE AST SANDBOX
# =========================================================================
s8 = prs.slides.add_slide(blank_layout)
add_header(s8, "Defensive Security: Abstract Syntax Tree (AST) Sandbox", "7. Code Sandboxing")

tb8 = s8.shapes.add_textbox(Inches(0.8), Inches(1.8), Inches(6.5), Inches(5.0))
tf8 = tb8.text_frame
tf8.word_wrap = True
add_bullet(tf8, "The Danger of Autonomous LLM Code Generation:")
add_bullet(tf8, "• LLMs can generate unauthorized file writes, subprocess forks, or SQL injection.", 1)
add_bullet(tf8, "Multi-Tiered Defensive AST Pipeline:")
add_bullet(tf8, "1. Static AST Node Traversal: Code is parsed into an abstract syntax tree prior to execution.", 1)
add_bullet(tf8, "2. Strict Module Whitelist: Only numpy, geopandas, matplotlib, pandas allowed.", 1)
add_bullet(tf8, "3. Blacklisted Symbols: Absolute block on eval, exec, open, os, sys, subprocess, and dunder methods (__subclasses__).", 1)
add_bullet(tf8, "4. Execution Isolation: Read-only DB connection, 5s timeout, 512MB RAM cap.", 1)

if os.path.exists("figures/pipeline_securite_sandbox.png"):
    s8.shapes.add_picture("figures/pipeline_securite_sandbox.png", Inches(7.6), Inches(1.6), width=Inches(5.0))

set_slide_notes(s8,
"Un défi majeur en ingénierie de l'IA est la sécurité : comment faire exécuter du code Python généré dynamiquement sans risquer de corrompre le serveur ? J'ai conçu un bac à sable défensif basé sur l'analyse statique d'arbre syntaxique abstrait (AST). Avant toute exécution, l'AST inspecte les nœuds syntaxiques : tout appel à 'eval', 'exec', 'open', 'subprocess' ou module non autorisé est intercepté et rejeté. Lors de nos tests d'intrusion, 100% des attaques ont été bloquées.")

# =========================================================================
# SLIDE 9: AI FINE-TUNING
# =========================================================================
s9 = prs.slides.add_slide(blank_layout)
add_header(s9, "Domain Adaptation: Qwen2.5-Coder LoRA Fine-Tuning", "8. Model Specialization")

tb9 = s9.shapes.add_textbox(Inches(0.8), Inches(1.8), Inches(6.5), Inches(5.0))
tf9 = tb9.text_frame
tf9.word_wrap = True
add_bullet(tf9, "Dataset Engineering & Distribution Rebalancing:")
add_bullet(tf9, "• Initial synthetic datasets over-indexed on basic SQL (65%) and neglected complex spatial joins (15%).", 1)
add_bullet(tf9, "• Curated 1,200 domain-specific instruction-response pairs covering:", 1)
add_bullet(tf9, "  - Statistical Aggregations (30%)", 2)
add_bullet(tf9, "  - Spatial Joins & Intersect Queries (25%)", 2)
add_bullet(tf9, "  - Deficit & Anomaly Calculations (25%)", 2)
add_bullet(tf9, "  - Cartographic Styling & Legends (20%)", 2)
add_bullet(tf9, "Parameter-Efficient Fine-Tuning (PEFT / LoRA):")
add_bullet(tf9, "• Adapted Qwen2.5-Coder with rank r=16, alpha=32 on attention projections.", 1)

if os.path.exists("figures/distribution_dataset_finetuning.png"):
    s9.shapes.add_picture("figures/distribution_dataset_finetuning.png", Inches(7.7), Inches(1.6), width=Inches(4.9))

set_slide_notes(s9,
"Pour que le modèle comprenne le jargon très spécifique de la DGRE, nous avons affiné le modèle Qwen2.5-Coder par LoRA. L'audit initial a montré que le dataset contenait trop de requêtes simples et pas assez de requêtes géospatiales. J'ai rééquilibré le corpus sur 1 200 paires d'instructions spécialisées (jointures spatiales, calculs d'anomalies, rendu cartographique), améliorant le taux de réussite au premier essai (Pass@1) à plus de 91%.")

# =========================================================================
# SLIDE 10: DEMO 1 (CONVERSATIONAL GIS)
# =========================================================================
s10 = prs.slides.add_slide(blank_layout)
add_header(s10, "Demonstration 1: Conversational Spatial GIS", "9. Live Demonstration")

# User Query Box
qbox = s10.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), Inches(1.8), Inches(5.6), Inches(1.4))
qbox.fill.solid()
qbox.fill.fore_color.rgb = BG_LIGHT
qbox.line.color.rgb = WATER_BLUE

qtb = s10.shapes.add_textbox(Inches(1.0), Inches(1.9), Inches(5.2), Inches(1.2))
qtf = qtb.text_frame
qtf.word_wrap = True
p = qtf.paragraphs[0]
p.text = "Natural Language User Prompt:"
p.font.bold = True
p.font.size = Pt(13)
p.font.color.rgb = WATER_BLUE
p2 = qtf.add_paragraph()
p2.text = "\"Identify all reference stations in the Medjerda basin with annual rainfall 20% below the 50-year normal in 2020.\""
p2.font.italic = True
p2.font.size = Pt(14)
p2.font.color.rgb = NAVY

# Generated SQL box
sbox = s10.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), Inches(3.4), Inches(5.6), Inches(3.4))
sbox.fill.solid()
sbox.fill.fore_color.rgb = NAVY
sbox.line.fill.background()

stb = s10.shapes.add_textbox(Inches(1.0), Inches(3.5), Inches(5.2), Inches(3.2))
stf = stb.text_frame
stf.word_wrap = True
p = stf.paragraphs[0]
p.text = "PostGIS SQL Synthesized in 0.8s:"
p.font.bold = True
p.font.size = Pt(13)
p.font.color.rgb = ACCENT_BLUE
p.space_after = Pt(8)

p2 = stf.add_paragraph()
p2.text = "SELECT s.nom, p.cumul, n.normale,\n       ROUND(((p.cumul - n.normale)\n              / n.normale * 100)::numeric, 1) AS deficit\nFROM stations s\nJOIN pluviometrie p ON s.code = p.code\nJOIN normales_50ans n ON s.code = n.code\nWHERE s.region = 'Nord' AND p.annee = 2020\n  AND ((p.cumul - n.normale)/n.normale) < -0.20;"
p2.font.size = Pt(11)
p2.font.color.rgb = RGBColor(255, 255, 255)

# Result table box on right
rtb = s10.shapes.add_textbox(Inches(6.8), Inches(1.8), Inches(5.8), Inches(5.0))
rtf = rtb.text_frame
rtf.word_wrap = True
p = rtf.paragraphs[0]
p.text = "Instant Synthesized Response (14 ms Query):"
p.font.bold = True
p.font.size = Pt(16)
p.font.color.rgb = NAVY
p.space_after = Pt(14)

add_bullet(rtf, "• Aïn Draham (Jendouba): 1120.5 mm  ➔  Deficit: -31.4%", 0, font_size=15, color=ALERT_RED)
add_bullet(rtf, "• Tabarka (Jendouba): 782.0 mm  ➔  Deficit: -24.8%", 0, font_size=15, color=ALERT_RED)
add_bullet(rtf, "• Béja Gare (Béja): 510.2 mm  ➔  Deficit: -22.1%", 0, font_size=15, color=ALERT_RED)
add_bullet(rtf, "Key Operational Value:")
add_bullet(rtf, "• Any agronomist or decision-maker can interrogate sovereign hydrological databases without submitting an IT ticket or knowing SQL syntax.", 1)

set_slide_notes(s10,
"Voici une démonstration concrète de l'interface en langage naturel. Un décideur ou agronome demande simplement les stations en déficit de plus de 20% par rapport à la normale cinquantenaire dans le Nord en 2020. L'agent superviseur détecte l'intention, l'agent SQL génère une requête PostGIS optimisée avec calcul de ratio, la base répond en 14 millisecondes, et le résultat est mis en forme en moins d'une seconde.")

# =========================================================================
# SLIDE 11: DEMO 2 (AUTOMATED CARTOGRAPHY)
# =========================================================================
s11 = prs.slides.add_slide(blank_layout)
add_header(s11, "Demonstration 2: Automated High-Resolution Cartography", "10. Cartographic Engine")

if os.path.exists("figures/carte_isohyetes_annuelle_2020.png"):
    s11.shapes.add_picture("figures/carte_isohyetes_annuelle_2020.png", Inches(0.8), Inches(1.6), width=Inches(5.6))

if os.path.exists("figures/cartes_saisonnieres_4panneaux.png"):
    s11.shapes.add_picture("figures/cartes_saisonnieres_4panneaux.png", Inches(6.8), Inches(1.6), width=Inches(5.8))

set_slide_notes(s11,
"En parallèle des requêtes tabulaires, le GIS Python Agent génère à la volée des cartes prêtes pour la publication. À gauche, la carte des isohyètes annuelles 2020 calculée par IDW avec découpage sur les frontières nationales. À droite, le tableau de bord en 4 panneaux saisonniers (automne, hiver, printemps, été). La génération d'une telle carte prenait une demi-journée sous Surfer/QGIS ; notre moteur l'exécute en 4.2 secondes.")

# =========================================================================
# SLIDE 12: DEMO 3 (COMPLETE YEARBOOK)
# =========================================================================
s12 = prs.slides.add_slide(blank_layout)
add_header(s12, "Demonstration 3: Automated Official Yearbook Generation", "11. Publication Engine")

tb12 = s12.shapes.add_textbox(Inches(0.8), Inches(1.8), Inches(6.5), Inches(5.0))
tf12 = tb12.text_frame
tf12.word_wrap = True
add_bullet(tf12, "Official Document Assembly Pipeline:")
add_bullet(tf12, "• Modular Jinja2 + LaTeX templates conforming to official DGRE visual standards.", 1)
add_bullet(tf12, "• 8 Statutory Statistical Tables Compiled Automatically:", 1)
add_bullet(tf12, "  - Tableau 1: General station catalog & coordinates", 2)
add_bullet(tf12, "  - Tableau 2 & 3: Monthly precipitation matrices", 2)
add_bullet(tf12, "  - Tableau 4: Surface-weighted regional means (Thiessen)", 2)
add_bullet(tf12, "  - Tableau 8: Rain-day frequencies (>1.0 mm threshold)", 2)
add_bullet(tf12, "• 22 Cartographic Plates Embedded Dynamically:", 1)
add_bullet(tf12, "  - 1 Annual, 12 Monthly, 4 Seasonal, 1 Normal, 1 Anomaly, 3 Regional", 2)
add_bullet(tf12, "• Total Execution Latency: 118 seconds for a 100+ page PDF.", 1, color=WATER_BLUE)

if os.path.exists("figures/carte_anomalie_normale_2020.png"):
    s12.shapes.add_picture("figures/carte_anomalie_normale_2020.png", Inches(7.7), Inches(1.6), width=Inches(4.8))

set_slide_notes(s12,
"Voici le couronnement de la plateforme : la génération automatisée de l'annuaire pluviométrique complet. Le moteur LaTeX assemble les 8 tableaux statistiques réglementaires et les 22 planches cartographiques en exactement 118 secondes. La carte d'anomalie affichée ici met en évidence le déficit sévère de 2020 dans le centre et le sud tunisien, directement exploitable pour les politiques de crise.")

# =========================================================================
# SLIDE 13: VALIDATION & PARITY
# =========================================================================
s13 = prs.slides.add_slide(blank_layout)
add_header(s13, "Empirical Validation & Numerical Parity", "12. Validation")

tb13 = s13.shapes.add_textbox(Inches(0.8), Inches(1.8), Inches(6.5), Inches(5.0))
tf13 = tb13.text_frame
tf13.word_wrap = True
add_bullet(tf13, "Rigorous Cross-Checking Against DGRE 2020 Archives:")
add_bullet(tf13, "• Tested against the historical published 2020 DGRE yearbook.", 1)
add_bullet(tf13, "• Absolute Parity: 0.00% numerical deviation on surface-weighted precipitation across all 6 natural zones.", 1, color=GREEN)
add_bullet(tf13, "Leave-One-Out Cross-Validation (LOOCV) of IDW:")
add_bullet(tf13, "• Correlation (R^2): 0.892 (Strong spatial consistency).", 1)
add_bullet(tf13, "• Mean Absolute Error (MAE): 18.4 mm on annual totals.", 1)
add_bullet(tf13, "• Percent Bias (PBIAS): +1.2% (Unbiased spatial estimator).", 1)

if os.path.exists("figures/comparatif_pluviometrique_regional.png"):
    s13.shapes.add_picture("figures/comparatif_pluviometrique_regional.png", Inches(7.7), Inches(1.6), width=Inches(4.9))

set_slide_notes(s13,
"En tant qu'ingénieur, la validation expérimentale était primordiale. Nous avons confronté les résultats générés par Rainfull Cartagen aux archives officielles publiées de 2020 : l'écart sur les moyennes pondérées par région est strictement de 0.00%. De plus, la validation croisée LOOCV sur l'IDW montre un R² de 0.89 et un biais de seulement 1.2%, confirmant la haute fidélité du modèle d'interpolation.")

# =========================================================================
# SLIDE 14: BENCHMARKS TABLE
# =========================================================================
s14 = prs.slides.add_slide(blank_layout)
add_header(s14, "Quantitative Engineering Benchmarks", "13. Performance Metrics")

# Benchmark table
rows, cols = 7, 4
left, top, width, height = Inches(0.8), Inches(1.8), Inches(11.7), Inches(4.5)
table_shape = s14.shapes.add_table(rows, cols, left, top, width, height)
tbl = table_shape.table

headers = ["Engineering Metric", "Legacy Manual Workflow", "Rainfull Cartagen", "Measured Gain"]
data = [
    ["Yearbook Compilation Cycle", "7–8 months (240 days)", "118 seconds", "-99.98%"],
    ["Natural Language Data Query", "2–4 days (IT ticket)", "0.85 seconds", "Instantaneous"],
    ["Isohyet Map Generation", "3–4 hours (Desktop GIS)", "4.2 seconds", "-99.96%"],
    ["AST Security Block Rate", "Unprotected", "100% Blocked", "Zero Breach"],
    ["Geodetic Spatial Standard", "Mixed formats / degrees", "EPSG:32632 (UTM 32N)", "Unified"],
    ["SQL Generation Accuracy", "Manual SQL writing", "91.4% (Pass@3: 98.2%)", "Robust"]
]

for c, h in enumerate(headers):
    cell = tbl.cell(0, c)
    cell.fill.solid()
    cell.fill.fore_color.rgb = NAVY
    p = cell.text_frame.paragraphs[0]
    p.text = h
    p.font.bold = True
    p.font.size = Pt(13)
    p.font.color.rgb = RGBColor(255, 255, 255)

for r, row_data in enumerate(data):
    for c, val in enumerate(row_data):
        cell = tbl.cell(r + 1, c)
        cell.fill.solid()
        cell.fill.fore_color.rgb = BG_LIGHT if r % 2 == 0 else CARD_BG
        p = cell.text_frame.paragraphs[0]
        p.text = val
        p.font.size = Pt(12)
        if c == 2 or c == 3:
            p.font.bold = True
            p.font.color.rgb = WATER_BLUE if c == 2 else GREEN

set_slide_notes(s14,
"Ce tableau synthétise le saut qualitatif et quantitatif opéré par Rainfull Cartagen. Nous passons de 240 jours à 118 secondes pour la production de l'annuaire, de 3 jours à moins d'une seconde pour interroger la base, avec un taux de sécurité AST de 100% et un déploiement entièrement conteneurisé sous Docker orchestrable en une seule commande.")

# =========================================================================
# SLIDE 15: PERSPECTIVES
# =========================================================================
s15 = prs.slides.add_slide(blank_layout)
add_header(s15, "Perspectives & National Scale-Up", "14. Future Horizons")

tb15 = s15.shapes.add_textbox(Inches(0.8), Inches(1.8), Inches(6.5), Inches(5.0))
tf15 = tb15.text_frame
tf15.word_wrap = True
add_bullet(tf15, "Short-Term Operational Horizons:")
add_bullet(tf15, "• IoT Direct Ingestion: Real-time telemetry ingestion from satellite/GSM rain gauges directly into PostGIS.", 1)
add_bullet(tf15, "• Interactive Web Dashboard: React / MapLibre client enabling interactive spatial slicing.", 1)
add_bullet(tf15, "Strategic Medium-Term AI Horizons:")
add_bullet(tf15, "• Coupled Flood Risk Modeling: Coupling Cartagen spatial rasters with hydraulic simulators (HEC-RAS).", 1)
add_bullet(tf15, "• National Drought Early-Warning: AI-driven seasonal forecasting supporting dam allocation policies.", 1)

if os.path.exists("figures/repartition_pluie_saisons.png"):
    s15.shapes.add_picture("figures/repartition_pluie_saisons.png", Inches(7.7), Inches(1.8), width=Inches(4.9))

set_slide_notes(s15,
"En termes de perspectives, la plateforme est prête pour deux évolutions majeures : à court terme, la connexion directe des pluviomètres télétransmis par GPRS/satellite pour une ingestion temps réel ; à moyen terme, le couplage avec des modèles hydrauliques de prévision des crues et des algorithmes d'alerte précoce à la sécheresse.")

# =========================================================================
# SLIDE 16: CONCLUSION
# =========================================================================
s16 = prs.slides.add_slide(blank_layout)
# Dark background banner
c_shape = s16.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(13.333), Inches(7.5))
c_shape.fill.solid()
c_shape.fill.fore_color.rgb = NAVY
c_shape.line.fill.background()

tb16 = s16.shapes.add_textbox(Inches(1.5), Inches(1.2), Inches(10.3), Inches(5.2))
tf16 = tb16.text_frame
tf16.word_wrap = True

p = tf16.paragraphs[0]
p.text = "CONCLUSION & CONTRIBUTIONS"
p.font.size = Pt(14)
p.font.bold = True
p.font.color.rgb = ACCENT_BLUE
p.space_after = Pt(20)

add_bullet(tf16, "1. Sovereign Spatial Infrastructure: Unification of 148 certified stations under PostGIS & UTM 32N.", 0, font_size=18, color=RGBColor(255, 255, 255))
add_bullet(tf16, "2. Radical Productivity Gain: 8-month manual struggle compressed to 118 seconds with 100% mathematical fidelity.", 0, font_size=18, color=RGBColor(255, 255, 255))
add_bullet(tf16, "3. Safe Autonomous AI: Multi-agent supervisor pattern shielded by an AST static sandbox.", 0, font_size=18, color=RGBColor(255, 255, 255))

p_end = tf16.add_paragraph()
p_end.space_before = Pt(30)
p_end.alignment = PP_ALIGN.CENTER
p_end.text = "Thank you for your attention!\nQuestions & Discussion"
p_end.font.size = Pt(28)
p_end.font.bold = True
p_end.font.color.rgb = ACCENT_BLUE

set_slide_notes(s16,
"Pour conclure, ce projet a permis de doter la DGRE d'une infrastructure spatiale souveraine, d'automatiser un processus historiquement long et complexe avec une fidélité mathématique totale, et de démontrer la viabilité d'agents IA autonomes hautement sécurisés. Je tiens à remercier chaleureusement mon encadrant à la DGRE M. Alaa Eddine JELASSI ainsi que l'ensemble du corps professoral de l'ENIT. Je me tiens à votre entière disposition pour vos questions.")

# Save presentation
output_path = "presentation_cartagen.pptx"
prs.save(output_path)
print(f"Presentation saved successfully to: {output_path}")
