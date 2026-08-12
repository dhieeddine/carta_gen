import os
import matplotlib.pyplot as plt
import matplotlib.patches as patches

# Configuration de la figure
fig, ax = plt.subplots(figsize=(16, 22), dpi=300)
ax.set_xlim(0, 100)
ax.set_ylim(0, 140)
ax.axis('off')

# Style de couleur (Palette moderne sombre/bleue DGRE)
BG_COLOR = "#0f172a"
HEADER_BG = "#1e293b"
CARD_BG = "#1e293b"
CARD_BORDER = "#3b82f6"
TEXT_COLOR = "#f8fafc"
TEXT_MUTED = "#94a3b8"
ACCENT_GREEN = "#22c55e"
ACCENT_BLUE = "#38bdf8"
ACCENT_ORANGE = "#f97316"
ACCENT_PURPLE = "#a855f7"

fig.patch.set_facecolor(BG_COLOR)

# Titre Principal
ax.text(50, 134, "DIAGRAMME D'ACTIVITÉ GLOBAL — PLATAFORME CARTAGEN", 
        fontsize=18, fontweight='bold', ha='center', color=ACCENT_BLUE)
ax.text(50, 130, "Architecture Multi-Agents & RAG Hydrologique (DGRE)", 
        fontsize=12, fontstyle='italic', ha='center', color=TEXT_MUTED)

def draw_box(x, y, w, h, title, text="", color=CARD_BORDER, bg=CARD_BG, shape="rect"):
    if shape == "diamond":
        # Losange de décision
        diamond = patches.Polygon([[x+w/2, y], [x+w, y+h/2], [x+w/2, y+h], [x, y+h/2]],
                                  facecolor=bg, edgecolor=color, linewidth=2, zorder=3)
        ax.add_patch(diamond)
        ax.text(x+w/2, y+h/2, title, fontsize=9, fontweight='bold', ha='center', va='center', color=TEXT_COLOR, zorder=4)
    elif shape == "start":
        circle = patches.Circle((x+w/2, y+h/2), radius=w/2, facecolor=ACCENT_BLUE, edgecolor="white", linewidth=2, zorder=3)
        ax.add_patch(circle)
    elif shape == "end":
        circle1 = patches.Circle((x+w/2, y+h/2), radius=w/2, facecolor="none", edgecolor=ACCENT_GREEN, linewidth=2, zorder=3)
        circle2 = patches.Circle((x+w/2, y+h/2), radius=w/3, facecolor=ACCENT_GREEN, edgecolor="none", zorder=3)
        ax.add_patch(circle1)
        ax.add_patch(circle2)
    else:
        # Rectangle classique
        rect = patches.FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.5",
                                       facecolor=bg, edgecolor=color, linewidth=1.5, zorder=3)
        ax.add_patch(rect)
        if text:
            ax.text(x+w/2, y+h*0.65, title, fontsize=10, fontweight='bold', ha='center', va='center', color=ACCENT_BLUE, zorder=4)
            ax.text(x+w/2, y+h*0.3, text, fontsize=8, ha='center', va='center', color=TEXT_COLOR, zorder=4)
        else:
            ax.text(x+w/2, y+h/2, title, fontsize=10, fontweight='bold', ha='center', va='center', color=TEXT_COLOR, zorder=4)

def draw_arrow(x1, y1, x2, y2, label="", color=TEXT_MUTED):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle="->", color=color, lw=2, mutation_scale=15), zorder=2)
    if label:
        ax.text((x1+x2)/2 + 1, (y1+y2)/2, label, fontsize=8, fontweight='bold', color=ACCENT_ORANGE, zorder=4)

# 1. Point de départ
draw_box(47, 122, 6, 4, "", shape="start")
ax.text(50, 120, "Départ : Requête Utilisateur", fontsize=9, ha='center', color=TEXT_COLOR)

# 2. Réception & Extraction
draw_box(30, 110, 40, 6, "1. Réception & Extraction Entités (NER)", "Détection : Question, Année, Mois, Gouvernorat, Options RAG")
draw_arrow(50, 122, 50, 116)

# 3. Décision Type de Requête
draw_box(35, 98, 30, 7, "Demande Visuelle ?", shape="diamond")
draw_arrow(50, 110, 50, 105)

# Swimlanes / Conteneurs
# Branche RAG (Gauche)
rect_rag = patches.FancyBboxPatch((4, 30), 42, 63, boxstyle="round,pad=0.8", facecolor="#1e293b", edgecolor="#334155", lw=1, alpha=0.5, zorder=1)
ax.add_patch(rect_rag)
ax.text(25, 90, "BRANCHE 1 : RAG ANNUAIRE & IMAGES OFFICIELLES", fontsize=11, fontweight='bold', ha='center', color=ACCENT_GREEN)

# Branche SIG Dynamique (Droite)
rect_sig = patches.FancyBboxPatch((54, 30), 42, 63, boxstyle="round,pad=0.8", facecolor="#1e293b", edgecolor="#334155", lw=1, alpha=0.5, zorder=1)
ax.add_patch(rect_sig)
ax.text(75, 90, "BRANCHE 2 : GENERATION DYNAMIQUE SIG (MULTI-AGENTS)", fontsize=11, fontweight='bold', ha='center', color=ACCENT_ORANGE)

# --- BRANCHE 1 (RAG) ---
draw_arrow(35, 101.5, 25, 101.5, "Oui (Annuaire)")
draw_arrow(25, 101.5, 25, 84)

draw_box(10, 78, 30, 6, "Recherche Multi-Source RAG", "Passages Zvec (961 Chunks) + Chiffres Exacts PostgreSQL")
draw_box(10, 68, 30, 6, "Arbitrage Visuel LLM Provider", "Le LLM analyse le catalogue d'images d'annuaire")
draw_arrow(25, 78, 25, 74)

draw_box(12, 56, 26, 7, "Image Annuaire Validée ?", shape="diamond")
draw_arrow(25, 68, 25, 63)

draw_box(10, 44, 30, 6, "Récupération Image Officielle", "ex: carte_annuelle.png / carte_saison_auto.png", color=ACCENT_GREEN)
draw_arrow(25, 56, 25, 50, "Oui (Par LLM)")

# --- BRANCHE 2 (SIG DYNAMIQUE) ---
draw_arrow(65, 101.5, 75, 101.5, "Non / Sur-Mesure")
draw_arrow(75, 101.5, 75, 84)
draw_arrow(38, 59.5, 75, 59.5, "Non (Rejeté par LLM)")
draw_arrow(75, 59.5, 75, 84)

draw_box(60, 78, 30, 6, "SQLGeneratorAgent & DataAuditAgent", "Traduction SQL PostGIS + Validation des stations (>0)")
draw_box(60, 68, 30, 6, "Classification Intention LLM", "Le LLM classe l'intention (mono, analysis, multi_season...)")
draw_arrow(75, 78, 75, 74)

draw_box(60, 58, 30, 6, "Appel LLM Fine-Tuné (Colab)", "Génération du Script Python SIG complet")
draw_arrow(75, 68, 75, 64)

draw_box(60, 48, 30, 6, "Exécution SandboxManager", "Exécution isolée subprocess -> output_isohyete.png")
draw_arrow(75, 58, 75, 54)

draw_box(62, 36, 26, 7, "Code Retour == 0 ?", shape="diamond")
draw_arrow(75, 48, 75, 43)

draw_box(60, 24, 30, 6, "QualityVerificationAgent", "Injection Traceback + Prompt d'Auto-Correction", color=ACCENT_ORANGE)
draw_arrow(62, 39.5, 55, 39.5, "Non (Erreur)")
draw_arrow(55, 39.5, 55, 61)
draw_arrow(55, 61, 60, 61)

# --- FIN & SYNTHÈSE ---
draw_box(30, 16, 40, 6, "Synthèse Exécutive & Formattage", "Le LLM rédige un résumé concis 2-3 puces (sans lister les stations)")
draw_arrow(25, 44, 25, 19)
draw_arrow(25, 19, 30, 19)
draw_arrow(75, 36, 75, 19, "Oui (Succès)")
draw_arrow(75, 19, 70, 19)

draw_box(47, 5, 6, 4, "", shape="end")
draw_arrow(50, 16, 50, 9)
ax.text(50, 2, "Affichage Final UI CartaGen (Rendu, Code & Traces Agents)", fontsize=10, fontweight='bold', ha='center', color=ACCENT_GREEN)

# Sauvegarde de la figure
output_path = r"d:\Desktop\stage_dgre\carta_gen\diagramme_activite_cartagen.png"
plt.savefig(output_path, bbox_inches='tight', facecolor=BG_COLOR)
plt.close()
print(f"Diagramme graphique généré avec succès : {output_path}")
