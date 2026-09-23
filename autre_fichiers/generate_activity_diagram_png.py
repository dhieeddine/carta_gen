import os
import matplotlib.pyplot as plt
import matplotlib.patches as patches

# Configuration de la figure
fig, ax = plt.subplots(figsize=(16, 22), dpi=300)
ax.set_xlim(0, 100)
ax.set_ylim(0, 140)
ax.axis('off')

# Style de couleur (Palette moderne claire / DGRE Eau & Territoire)
BG_COLOR = "#f8fafc"       # Slate 50 très clair
CARD_BG = "#ffffff"        # Blanc pur pour les cartes
CARD_BORDER = "#94a3b8"    # Slate 400 pour des contours nets
TEXT_COLOR = "#0f172a"     # Slate 900 très lisible
TEXT_MUTED = "#475569"     # Slate 600
ACCENT_BLUE = "#0284c7"    # Sky 600 / Bleu DGRE moderne
ACCENT_GREEN = "#15803d"   # Vert émeraude 700
ACCENT_ORANGE = "#c2410c"  # Orange foncé 700 pour visibilité sur fond clair
ACCENT_PURPLE = "#7e22ce"  # Violet 700
BORDER_DIAMOND = "#2563eb" # Bleu royal pour décisions

fig.patch.set_facecolor(BG_COLOR)

# Titre Principal
ax.text(50, 134, "DIAGRAMME D'ACTIVITÉ GLOBAL — PLATEFORME CARTAGEN", 
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
        circle = patches.Circle((x+w/2, y+h/2), radius=w/2, facecolor=ACCENT_BLUE, edgecolor="#0369a1", linewidth=2.5, zorder=3)
        ax.add_patch(circle)
    elif shape == "end":
        circle1 = patches.Circle((x+w/2, y+h/2), radius=w/2, facecolor="white", edgecolor=ACCENT_GREEN, linewidth=2.5, zorder=3)
        circle2 = patches.Circle((x+w/2, y+h/2), radius=w/3, facecolor=ACCENT_GREEN, edgecolor="none", zorder=4)
        ax.add_patch(circle1)
        ax.add_patch(circle2)
    else:
        # Rectangle classique
        rect = patches.FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.5",
                                       facecolor=bg, edgecolor=color, linewidth=1.8, zorder=3)
        ax.add_patch(rect)
        if text:
            ax.text(x+w/2, y+h*0.65, title, fontsize=10, fontweight='bold', ha='center', va='center', color=ACCENT_BLUE, zorder=4)
            ax.text(x+w/2, y+h*0.3, text, fontsize=8, ha='center', va='center', color=TEXT_COLOR, zorder=4)
        else:
            ax.text(x+w/2, y+h/2, title, fontsize=10, fontweight='bold', ha='center', va='center', color=TEXT_COLOR, zorder=4)

def draw_arrow(x1, y1, x2, y2, label="", color="#475569", label_pos="auto", label_color=ACCENT_ORANGE):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle="->", color=color, lw=2, mutation_scale=15), zorder=2)
    if label:
        if label_pos == "above" or (label_pos == "auto" and abs(y1 - y2) < 2):
            ax.text((x1+x2)/2, (y1+y2)/2 + 1.2, label, fontsize=8, fontweight='bold', 
                    ha='center', va='bottom', color=label_color, zorder=5,
                    bbox=dict(boxstyle="round,pad=0.2", facecolor=BG_COLOR, edgecolor="none", alpha=0.9))
        elif label_pos == "below":
            ax.text((x1+x2)/2, (y1+y2)/2 - 1.2, label, fontsize=8, fontweight='bold', 
                    ha='center', va='top', color=label_color, zorder=5,
                    bbox=dict(boxstyle="round,pad=0.2", facecolor=BG_COLOR, edgecolor="none", alpha=0.9))
        elif label_pos == "left":
            ax.text((x1+x2)/2 - 1.2, (y1+y2)/2, label, fontsize=8, fontweight='bold', 
                    ha='right', va='center', color=label_color, zorder=5,
                    bbox=dict(boxstyle="round,pad=0.2", facecolor=BG_COLOR, edgecolor="none", alpha=0.9))
        else:
            # right or auto vertical
            ax.text((x1+x2)/2 + 1.2, (y1+y2)/2, label, fontsize=8, fontweight='bold', 
                    ha='left', va='center', color=label_color, zorder=5,
                    bbox=dict(boxstyle="round,pad=0.2", facecolor=BG_COLOR, edgecolor="none", alpha=0.9))

# 1. Point de départ
draw_box(47, 122, 6, 4, "", shape="start")
ax.text(50, 120, "Départ : Requête Utilisateur", fontsize=9, fontweight='bold', ha='center', color=TEXT_COLOR)

# 2. Réception & Extraction
draw_box(30, 110, 40, 6, "1. Réception & Extraction Entités (NER)", "Détection : Question, Année, Mois, Gouvernorat, Options RAG")
draw_arrow(50, 122, 50, 116)

# 3. Décision Type de Requête
draw_box(35, 98, 30, 7, "Demande Visuelle ?", shape="diamond", color=BORDER_DIAMOND)
draw_arrow(50, 110, 50, 105)

# Swimlanes / Conteneurs
# Branche RAG (Gauche)
rect_rag = patches.FancyBboxPatch((4, 30), 42, 63, boxstyle="round,pad=0.8", facecolor="#ecfdf5", edgecolor="#a7f3d0", lw=1.5, alpha=0.85, zorder=1)
ax.add_patch(rect_rag)
ax.text(25, 90, "BRANCHE 1 : RAG ANNUAIRE & IMAGES OFFICIELLES", fontsize=11, fontweight='bold', ha='center', color=ACCENT_GREEN)

# Branche SIG Dynamique (Droite)
rect_sig = patches.FancyBboxPatch((54, 30), 42, 63, boxstyle="round,pad=0.8", facecolor="#fff7ed", edgecolor="#fed7aa", lw=1.5, alpha=0.85, zorder=1)
ax.add_patch(rect_sig)
ax.text(75, 90, "BRANCHE 2 : GÉNÉRATION DYNAMIQUE SIG (MULTI-AGENTS)", fontsize=11, fontweight='bold', ha='center', color=ACCENT_ORANGE)

# --- BRANCHE 1 (RAG) ---
draw_arrow(35, 101.5, 25, 101.5, label="Oui (Annuaire)", label_pos="above")
draw_arrow(25, 101.5, 25, 84)

draw_box(10, 78, 30, 6, "Recherche Multi-Source RAG", "Passages Zvec (961 Chunks) + Chiffres Exacts PostgreSQL")
draw_box(10, 68, 30, 6, "Arbitrage Visuel LLM Provider", "Le LLM analyse le catalogue d'images d'annuaire")
draw_arrow(25, 78, 25, 74)

draw_box(12, 56, 26, 7, "Image Annuaire Validée ?", shape="diamond", color=BORDER_DIAMOND)
draw_arrow(25, 68, 25, 63)

draw_box(10, 44, 30, 6, "Récupération Image Officielle", "ex: carte_annuelle.png / carte_saison_auto.png", color=ACCENT_GREEN)
draw_arrow(25, 56, 25, 50, label="Oui (Par LLM)", label_pos="right", label_color=ACCENT_GREEN)

# --- BRANCHE 2 (SIG DYNAMIQUE) ---
draw_arrow(65, 101.5, 75, 101.5, label="Non / Sur-Mesure", label_pos="above")
draw_arrow(75, 101.5, 75, 84)

# Connexion Rejet LLM vers Branche 2 (contourne proprement par le couloir central)
draw_arrow(38, 59.5, 50, 59.5, label="Non (Rejeté)", label_pos="above")
draw_arrow(50, 59.5, 50, 84)
draw_arrow(50, 84, 60, 84)

draw_box(60, 78, 30, 6, "SQLGeneratorAgent & DataAuditAgent", "Traduction SQL PostGIS + Validation des stations (>0)")
draw_box(60, 68, 30, 6, "Classification Intention LLM", "Le LLM classe l'intention (mono, analysis, multi_season...)")
draw_arrow(75, 78, 75, 74)

draw_box(60, 58, 30, 6, "Appel LLM Fine-Tuné (Colab)", "Génération du Script Python SIG complet")
draw_arrow(75, 68, 75, 64)

draw_box(60, 48, 30, 6, "Exécution SandboxManager", "Exécution isolée subprocess -> output_isohyete.png")
draw_arrow(75, 58, 75, 54)

draw_box(62, 36, 26, 7, "Code Retour == 0 ?", shape="diamond", color=BORDER_DIAMOND)
draw_arrow(75, 48, 75, 43)

# Cas Erreur -> QualityVerificationAgent puis Retry
draw_box(60, 24, 30, 6, "QualityVerificationAgent", "Injection Traceback + Prompt d'Auto-Correction", color=ACCENT_ORANGE)
draw_arrow(75, 36, 75, 30, label="Non (Erreur)", label_pos="right")
draw_arrow(60, 27, 55, 27)
draw_arrow(55, 27, 55, 61, label="Boucle Auto-Correction", label_pos="left")
draw_arrow(55, 61, 60, 61)

# Cas Succès -> Sortie latérale directe vers synthèse
draw_arrow(88, 39.5, 92, 39.5, label="Oui (Succès)", label_pos="above", label_color=ACCENT_GREEN)
draw_arrow(92, 39.5, 92, 19)
draw_arrow(92, 19, 70, 19)

# --- FIN & SYNTHÈSE ---
draw_box(30, 16, 40, 6, "Synthèse Exécutive & Formattage", "Le LLM rédige un résumé concis 2-3 puces (sans lister les stations)")
draw_arrow(25, 44, 25, 19)
draw_arrow(25, 19, 30, 19)

draw_box(47, 5, 6, 4, "", shape="end")
draw_arrow(50, 16, 50, 9)
ax.text(50, 2, "Affichage Final UI CartaGen (Rendu, Code & Traces Agents)", fontsize=10, fontweight='bold', ha='center', color=ACCENT_GREEN)

# Sauvegarde de la figure
output_dir = os.path.dirname(os.path.abspath(__file__))
output_path = os.path.join(output_dir, "diagramme_activite_cartagen.png")
plt.savefig(output_path, bbox_inches='tight', facecolor=BG_COLOR)
plt.close()
print(f"Diagramme graphique généré avec succès : {output_path}")

