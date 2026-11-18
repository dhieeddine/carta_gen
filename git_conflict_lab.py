# -*- coding: utf-8 -*-
"""
git_conflict_lab.py
===================
Démonstrateur Interactif de Conflits Git & Résolution SCM (Sujet 10).
Crée un environnement temporaire isolé, simule deux développeurs modifiant le même fichier
en concurrence sur deux branches distinctes, provoque un conflit de fusion (3-way merge conflict),
décortique les marqueurs de conflits, puis effectue la résolution assistée.

Usage :
    python git_conflict_lab.py
"""

import os
import shutil
import subprocess
import tempfile
import sys


def run_cmd(cmd: list, cwd: str) -> str:
    res = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return res.stdout.strip() or res.stderr.strip()


def run_lab():
    print("=" * 75)
    print("🔬 DÉMONSTRATEUR DE CONFLIT DE CODE SOURCE GIT (SCM — SUJET 10)")
    print("=" * 75)

    temp_dir = tempfile.mkdtemp(prefix="git_scm_lab_")
    print(f"\n[1] Initialisation d'un dépôt Git isolé : {temp_dir}")

    try:
        run_cmd(["git", "init"], cwd=temp_dir)
        run_cmd(["git", "config", "user.name", "SCM Architect"], cwd=temp_dir)
        run_cmd(["git", "config", "user.email", "architect@cartagen.dgre.tn"], cwd=temp_dir)

        # Fichier initial
        config_path = os.path.join(temp_dir, "config.py")
        with open(config_path, "w", encoding="utf-8") as f:
            f.write(
                "# CartaGen Global Config\n"
                "DEFAULT_TIMEOUT = 30\n"
                "CACHE_STRATEGY = 'none'\n"
                "MAX_WORKERS = 4\n"
            )

        run_cmd(["git", "add", "config.py"], cwd=temp_dir)
        run_cmd(["git", "commit", "-m", "chore: configuration initiale commune"], cwd=temp_dir)
        print("  ✓ Commit initial créé sur la branche principale 'master/main'")

        # Branche Développeur A
        print("\n[2] Développeur A crée la branche 'feature/redis-cache' :")
        run_cmd(["git", "checkout", "-b", "feature/redis-cache"], cwd=temp_dir)
        with open(config_path, "w", encoding="utf-8") as f:
            f.write(
                "# CartaGen Global Config\n"
                "DEFAULT_TIMEOUT = 30\n"
                "CACHE_STRATEGY = 'redis_cluster_v2'  # Dev A: passage à Redis haute disponibilité\n"
                "MAX_WORKERS = 8\n"
            )
        run_cmd(["git", "commit", "-am", "feat(cache): intégration du cluster Redis par Dev A"], cwd=temp_dir)
        print("  ✓ Dev A a commité sa modification de CACHE_STRATEGY et MAX_WORKERS")

        # Branche Développeur B (partant du commit initial)
        print("\n[3] Développeur B travaille en parallèle sur 'feature/memory-cache' :")
        run_cmd(["git", "checkout", "master" if "master" in run_cmd(["git", "branch"], cwd=temp_dir) else "main"], cwd=temp_dir)
        run_cmd(["git", "checkout", "-b", "feature/memory-cache"], cwd=temp_dir)
        with open(config_path, "w", encoding="utf-8") as f:
            f.write(
                "# CartaGen Global Config\n"
                "DEFAULT_TIMEOUT = 45\n"
                "CACHE_STRATEGY = 'in_memory_lru'  # Dev B: cache local ultra-rapide\n"
                "MAX_WORKERS = 16\n"
            )
        run_cmd(["git", "commit", "-am", "feat(cache): mise en place LRU mémoire par Dev B"], cwd=temp_dir)
        print("  ✓ Dev B a commité sa modification concurrente sur les mêmes lignes !")

        # Tentative de Fusion (Merge)
        print("\n[4] Tentative de fusion de 'feature/redis-cache' dans 'feature/memory-cache' :")
        merge_output = run_cmd(["git", "merge", "feature/redis-cache"], cwd=temp_dir)
        print("  Résultat de git merge :")
        for line in merge_output.splitlines():
            print(f"    {line}")

        print("\n[5] Inspection des marqueurs de conflit générés par Git dans 'config.py' :")
        print("-" * 65)
        with open(config_path, "r", encoding="utf-8") as f:
            content = f.read()
            print(content)
        print("-" * 65)

        # Résolution Assistée (Arbitrage Architectural)
        print("\n[6] Résolution du conflit (Synthèse des deux besoins architecturaux) :")
        resolved_content = (
            "# CartaGen Global Config\n"
            "DEFAULT_TIMEOUT = 45  # Synthèse: allongement du timeout (Dev B)\n"
            "# Résolution de conflit SCM : stratégie hybride multiniveaux (Dev A + Dev B)\n"
            "CACHE_STRATEGY = 'hybrid_lru_then_redis'\n"
            "MAX_WORKERS = 16  # Performance maximale retenue\n"
        )
        with open(config_path, "w", encoding="utf-8") as f:
            f.write(resolved_content)

        run_cmd(["git", "add", "config.py"], cwd=temp_dir)
        run_cmd(["git", "commit", "-m", "merge: résolution du conflit de stratégie de cache (hybride LRU + Redis)"], cwd=temp_dir)
        print("  ✓ Fichier marqué comme résolu et commit de fusion finalisé !")

        print("\n[7] Visualisation de l'arbre Git après résolution (Git DAG) :")
        log_graph = run_cmd(["git", "log", "--graph", "--oneline", "--all"], cwd=temp_dir)
        for line in log_graph.splitlines():
            print(f"    {line}")

        print("\n" + "=" * 75)
        print("🎉 Démonstration SCM terminée avec succès ! Le conflit a été géré proprement.")
        print("=" * 75)

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    run_lab()

