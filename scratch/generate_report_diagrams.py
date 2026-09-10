import os
import matplotlib.pyplot as plt
import numpy as np
from scipy.spatial import Voronoi, voronoi_plot_2d

figures_dir = r"d:\Desktop\stage_dgre\carta_gen\figures"
os.makedirs(figures_dir, exist_ok=True)

# -------------------------------------------------------------
# 1. Comparaison Thiessen (Voronoi) vs IDW Interpolation
# -------------------------------------------------------------
plt.figure(figsize=(14, 6), dpi=300)

# Station positions and values
np.random.seed(42)
n_pts = 16
x = np.random.uniform(10, 90, n_pts)
y = np.random.uniform(10, 90, n_pts)
values = np.random.uniform(150, 750, n_pts)

# Left: Thiessen Polygons
ax1 = plt.subplot(1, 2, 1)
vor = Voronoi(np.column_stack([x, y]))
voronoi_plot_2d(vor, ax=ax1, show_vertices=False, line_colors='#1e3d59', line_width=1.5, line_alpha=0.8)

# Color points by value
scatter1 = ax1.scatter(x, y, c=values, cmap='Blues', s=120, edgecolors='black', zorder=5)
for i in range(n_pts):
    ax1.annotate(f"S{i+1}\n({int(values[i])}mm)", (x[i]+1.5, y[i]-1.5), fontsize=8, weight='bold', color='#111')

ax1.set_title("(A) Méthode des Polygones de Thiessen (Voronoi)\nIntégration surfacique discrète (Aires d'influence $w_i$)", fontsize=11, fontweight='bold', pad=12)
ax1.set_xlim(0, 100)
ax1.set_ylim(0, 100)
ax1.set_xlabel("Coordonnée X (Est)", fontsize=10)
ax1.set_ylabel("Coordonnée Y (Nord)", fontsize=10)
ax1.grid(True, linestyle='--', alpha=0.3)
plt.colorbar(scatter1, ax=ax1, label='Hauteur pluviométrique observée (mm)', fraction=0.046, pad=0.04)

# Right: IDW Interpolation
ax2 = plt.subplot(1, 2, 2)
grid_x, grid_y = np.mgrid[0:100:200j, 0:100:200j]

# Compute IDW
grid_val = np.zeros_like(grid_x)
for i in range(grid_x.shape[0]):
    for j in range(grid_x.shape[1]):
        gx = grid_x[i, j]
        gy = grid_y[i, j]
        dists = np.sqrt((x - gx)**2 + (y - gy)**2)
        dists = np.maximum(dists, 0.5)
        weights = 1.0 / (dists ** 2)
        grid_val[i, j] = np.sum(weights * values) / np.sum(weights)

contour = ax2.contourf(grid_x, grid_y, grid_val, levels=15, cmap='YlGnBu')
ax2.scatter(x, y, c='red', s=60, edgecolors='black', label='Stations Pluviométriques', zorder=5)
cs = ax2.contour(grid_x, grid_y, grid_val, levels=8, colors='navy', alpha=0.5, linewidths=0.8)
ax2.clabel(cs, inline=True, fontsize=8, fmt='%1.0f mm')

ax2.set_title("(B) Méthode d'Interpolation IDW ($1/d^2$)\nChamp continu spatialisé et courbes isohyètes", fontsize=11, fontweight='bold', pad=12)
ax2.set_xlim(0, 100)
ax2.set_ylim(0, 100)
ax2.set_xlabel("Coordonnée X (Est)", fontsize=10)
ax2.set_ylabel("Coordonnée Y (Nord)", fontsize=10)
ax2.legend(loc='upper right', fontsize=8)
ax2.grid(True, linestyle='--', alpha=0.3)
plt.colorbar(contour, ax=ax2, label='Pluviométrie interpolée (mm)', fraction=0.046, pad=0.04)

plt.tight_layout()
plt.savefig(os.path.join(figures_dir, "comparaison_thiessen_idw.png"), dpi=300, bbox_inches='tight')
plt.close()
print("Saved comparaison_thiessen_idw.png")

# -------------------------------------------------------------
# 2. Distribution Dataset Fine-Tuning Avant vs Après
# -------------------------------------------------------------
plt.figure(figsize=(10, 5), dpi=300)

metrics = ['Total Exemples', 'Requêtes Saisonnières', 'Contexte RAG Zvec', 'Gouvernorats sans données']
before = [975, 0, 0, 4]
after = [1302, 108, 504, 0]

x_pos = np.arange(len(metrics))
width = 0.35

fig, ax = plt.subplots(figsize=(11, 5.5), dpi=300)
rects1 = ax.bar(x_pos - width/2, before, width, label='Dataset Initial (Brut)', color='#e05353', edgecolor='black')
rects2 = ax.bar(x_pos + width/2, after, width, label='Dataset Rééquilibré (Corrigé)', color='#2e8b57', edgecolor='black')

ax.set_ylabel('Nombre d\'exemples / Entités', fontsize=11, fontweight='bold')
ax.set_title('Amélioration Qualitative et Quantitative du Dataset de Fine-Tuning LoRA\n(dataset_mixed_clean.jsonl)', fontsize=12, fontweight='bold', pad=15)
ax.set_xticks(x_pos)
ax.set_xticklabels(metrics, fontsize=10, fontweight='bold')
ax.legend(fontsize=10)
ax.grid(axis='y', linestyle='--', alpha=0.5)

def autolabel(rects):
    for rect in rects:
        height = rect.get_height()
        ax.annotate(f'{height}',
                    xy=(rect.get_x() + rect.get_width() / 2, height),
                    xytext=(0, 3),
                    textcoords="offset points",
                    ha='center', va='bottom', fontsize=9, fontweight='bold')

autolabel(rects1)
autolabel(rects2)

plt.tight_layout()
plt.savefig(os.path.join(figures_dir, "distribution_dataset_finetuning.png"), dpi=300, bbox_inches='tight')
plt.close()
print("Saved distribution_dataset_finetuning.png")

# -------------------------------------------------------------
# 3. Sécurité Sandbox AST Pipeline
# -------------------------------------------------------------
fig, ax = plt.subplots(figsize=(12, 4.5), dpi=300)
ax.axis('off')

boxes = [
    {"text": "1. Code Python\nGénéré par l'Agent SIG", "color": "#e8f4f8", "edge": "#17a2b8", "x": 0.08, "w": 0.16},
    {"text": "2. Inspecteur AST\n(Analyse Statique Syntaxique)\nVérifie ast.Import, ast.Call", "color": "#fff3cd", "edge": "#ffc107", "x": 0.32, "w": 0.20},
    {"text": "3. Filtrage Règles Sécurité\nBloque subprocess, eval,\nshutil, socket, os.system", "color": "#f8d7da", "edge": "#dc3545", "x": 0.60, "w": 0.18},
    {"text": "4. Sandbox Isolé\nSubprocess avec Timeout,\nCWD dédié & Capture stderr", "color": "#d4edda", "edge": "#28a745", "x": 0.86, "w": 0.18}
]

for b in boxes:
    rect = plt.Rectangle((b["x"] - b["w"]/2, 0.25), b["w"], 0.5, facecolor=b["color"], edgecolor=b["edge"], linewidth=2, transform=ax.transAxes, zorder=2)
    ax.add_patch(rect)
    ax.text(b["x"], 0.5, b["text"], ha='center', va='center', fontsize=9.5, fontweight='bold', transform=ax.transAxes, zorder=3)

# Draw arrows
arrows = [(0.17, 0.21), (0.43, 0.50), (0.70, 0.76)]
for start_x, end_x in arrows:
    ax.annotate('', xy=(end_x, 0.5), xytext=(start_x, 0.5),
                xycoords='axes fraction', textcoords='axes fraction',
                arrowprops=dict(arrowstyle="->", lw=2.5, color='#2c3e50'))

# Feedback loop
ax.annotate('Si rejet de sécurité ou erreur stderr\nBoucle de correction LLM (max 3 itérations)',
            xy=(0.08, 0.24), xytext=(0.60, 0.1),
            xycoords='axes fraction', textcoords='axes fraction',
            ha='center', va='center', fontsize=8.5, fontstyle='italic', color='#c0392b',
            arrowprops=dict(arrowstyle="->", connectionstyle="arc3,rad=-0.25", lw=1.8, color='#c0392b', linestyle='--'))

ax.set_title("Architecture de Sécurité Défensive à Double Niveau pour l'Exécution du Code Cartographique", fontsize=11, fontweight='bold', pad=15)
plt.tight_layout()
plt.savefig(os.path.join(figures_dir, "pipeline_securite_sandbox.png"), dpi=300, bbox_inches='tight')
plt.close()
print("Saved pipeline_securite_sandbox.png")
