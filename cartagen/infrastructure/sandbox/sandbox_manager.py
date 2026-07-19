# -*- coding: utf-8 -*-

import os
import sys
import uuid
import time
import shutil
import subprocess
from io import StringIO
from typing import Dict, Any, Optional
from cartagen.domain.models.map_request import ExecutionResult

class SandboxManager:
    """Gère l'exécution sécurisée et isolée du code Python de rendu géospatiale."""

    def __init__(self, workspace_root: str, database_url: str):
        self.workspace_root = workspace_root
        self.database_url = database_url
        self.sandbox_dir = os.path.join(workspace_root, "sandbox_runs")
        os.makedirs(self.sandbox_dir, exist_ok=True)

    def execute(self, code: str, shapefiles_dir: str) -> ExecutionResult:
        """
        Exécute le code Python dans un répertoire temporaire isolé.
        Copie les shapefiles d'intérêt et injecte la connexion PostgreSQL.
        """
        run_id = str(uuid.uuid4())
        run_dir = os.path.join(self.sandbox_dir, run_id)
        os.makedirs(run_dir, exist_ok=True)

        # 1. Copier les Shapefiles de référence dans le dossier d'exécution
        # Pour que le script puisse s'exécuter localement sans chemins absolus complexes
        if os.path.exists(shapefiles_dir):
            for file in os.listdir(shapefiles_dir):
                if file.endswith(('.shp', '.dbf', '.shx', '.prj', '.xlsx')):
                    shutil.copy(
                        os.path.join(shapefiles_dir, file),
                        os.path.join(run_dir, file)
                    )

        # 2. Écrire le code généré dans un script exécutable
        script_path = os.path.join(run_dir, "run_map.py")
        # S'assurer que le script produit l'image 'output_isohyete.png'
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(code)

        # 3. Préparer l'environnement d'exécution (injection DATABASE_URL)
        env = os.environ.copy()
        env["DATABASE_URL"] = self.database_url
        env["MPLBACKEND"] = "Agg"  # Backend non-interactif Matplotlib indispensable

        # Détecter et utiliser le binaire Python du venv local s'il existe
        python_exe = sys.executable
        venv_dir = os.path.join(self.workspace_root, "venv")
        if os.path.exists(venv_dir):
            if os.name == "nt":
                venv_python = os.path.join(venv_dir, "Scripts", "python.exe")
            else:
                venv_python = os.path.join(venv_dir, "bin", "python")
            if os.path.exists(venv_python):
                python_exe = venv_python

        t0 = time.time()
        stdout, stderr = "", ""
        success = False
        error_msg = None
        output_image_path = None
        output_table_html = None

        try:
            # Exécution isolée du sous-processus avec un Timeout de 60 secondes
            process = subprocess.run(
                [python_exe, "run_map.py"],
                cwd=run_dir,
                env=env,
                capture_output=True,
                text=True,
                timeout=60
            )
            stdout = process.stdout
            stderr = process.stderr
            
            if process.returncode == 0:
                expected_image = os.path.join(run_dir, "output_isohyete.png")
                expected_table = os.path.join(run_dir, "output_table.html")
                
                has_image = os.path.exists(expected_image)
                has_table = os.path.exists(expected_table)
                
                if has_image or has_table:
                    success = True
                    if has_image:
                        # Déplacer l'image finale vers un chemin persistant
                        persisted_image = os.path.join(self.sandbox_dir, f"map_{run_id}.png")
                        shutil.move(expected_image, persisted_image)
                        output_image_path = persisted_image
                        
                    if has_table:
                        with open(expected_table, "r", encoding="utf-8") as f_tbl:
                            output_table_html = f_tbl.read()
                    
                    # Sauvegarder également le code source généré final de façon persistante
                    persisted_code_path = os.path.join(self.sandbox_dir, f"map_{run_id}.py")
                    with open(persisted_code_path, "w", encoding="utf-8") as f_code:
                        f_code.write(code)
                else:
                    error_msg = "Le script a terminé avec succès (code 0) mais n'a produit ni image 'output_isohyete.png' ni tableau 'output_table.html'."
            else:
                error_msg = f"Erreur d'exécution (Code {process.returncode}) : {stderr}"
                # Sauvegarder le code en cas d'échec pour le debug local
                persisted_code_path = os.path.join(self.sandbox_dir, f"map_{run_id}_failed.py")
                with open(persisted_code_path, "w", encoding="utf-8") as f_code:
                    f_code.write(code)

        except subprocess.TimeoutExpired as e:
            error_msg = f"Timeout d'exécution dépassé (60s). Le script a été stoppé."
            stdout = e.stdout or ""
            stderr = e.stderr or ""
        except Exception as e:
            error_msg = f"Exception système lors du lancement : {str(e)}"
        finally:
            elapsed = time.time() - t0
            # Nettoyage optionnel du répertoire de travail temporaire
            try:
                # Conserver uniquement le script pour debug, ou tout supprimer
                shutil.rmtree(run_dir, ignore_errors=True)
            except:
                pass

        return ExecutionResult(
            success=success,
            stdout=stdout,
            stderr=stderr,
            output_image_path=output_image_path,
            error_message=error_msg,
            execution_time=elapsed,
            output_table_html=output_table_html
        )
