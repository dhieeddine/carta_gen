// ============================================================
// LOGIQUE APPLICATIVE FRONTEND — CARTAGEN
// ============================================================

document.addEventListener("DOMContentLoaded", () => {
    // Éléments du DOM
    const promptInput = document.getElementById("promptInput");
    const generateBtn = document.getElementById("generateBtn");
    const spinner = generateBtn.querySelector(".spinner");
    const btnIcon = generateBtn.querySelector(".btn-icon");
    const btnText = generateBtn.querySelector(".btn-text");
    const suggestChips = document.querySelectorAll(".suggest-chip");
    
    const consoleLogs = document.getElementById("consoleLogs");
    const statusIndicator = document.getElementById("statusIndicator");
    
    const tabBtns = document.querySelectorAll(".tab-btn");
    const tabContents = document.querySelectorAll(".tab-content");
    
    const mapPlaceholder = document.getElementById("mapPlaceholder");
    const mapImage = document.getElementById("mapImage");
    const downloadBtn = document.getElementById("downloadBtn");
    
    const pythonCodeDisplay = document.getElementById("pythonCodeDisplay");
    const sqlQueryDisplay = document.getElementById("sqlQueryDisplay");
    
    const copyCodeBtn = document.getElementById("copyCodeBtn");
    const copySqlBtn = document.getElementById("copySqlBtn");
    
    const historyGrid = document.getElementById("historyGrid");
    
    const tableDataDisplay = document.getElementById("tableDataDisplay");
    const copyTableBtn = document.getElementById("copyTableBtn");

    // Données de session locales
    let activeTaskId = null;
    let pollingInterval = null;
    const history = [];

    // ============================================================
    // GESTION DES ONGLETS
    // ============================================================
    tabBtns.forEach(btn => {
        btn.addEventListener("click", () => {
            tabBtns.forEach(b => b.classList.remove("active"));
            tabContents.forEach(c => c.classList.remove("active"));
            
            btn.classList.add("active");
            const tabId = btn.getAttribute("data-tab");
            document.getElementById(tabId).classList.add("active");
        });
    });

    // ============================================================
    // UTILS : AJOUT DE LOGS ET GESTION STATUTS
    // ============================================================
    function addLog(message, type = "system") {
        const time = new Date().toLocaleTimeString();
        const line = document.createElement("div");
        line.className = `log-line ${type}`;
        line.innerHTML = `<span style="color: var(--text-muted)">[${time}]</span> ${message}`;
        consoleLogs.appendChild(line);
        consoleLogs.scrollTop = consoleLogs.scrollHeight;
    }

    function setStatus(status, text) {
        statusIndicator.className = `indicator ${status}`;
        statusIndicator.textContent = text;
    }

    // ============================================================
    // SUGGESTIONS RAPIDES
    // ============================================================
    suggestChips.forEach(chip => {
        chip.addEventListener("click", () => {
            promptInput.value = chip.textContent;
            promptInput.focus();
        });
    });

    // ============================================================
    // PRESSE-PAPIERS
    // ============================================================
    function copyTextToClipboard(text, btnElement) {
        navigator.clipboard.writeText(text).then(() => {
            const originalHTML = btnElement.innerHTML;
            btnElement.innerHTML = '<i class="fa-solid fa-check"></i> Copié !';
            btnElement.style.backgroundColor = "var(--success)";
            setTimeout(() => {
                btnElement.innerHTML = originalHTML;
                btnElement.style.backgroundColor = "";
            }, 2000);
        });
    }

    copyCodeBtn.addEventListener("click", () => {
        copyTextToClipboard(pythonCodeDisplay.textContent, copyCodeBtn);
    });

    copySqlBtn.addEventListener("click", () => {
        copyTextToClipboard(sqlQueryDisplay.textContent, copySqlBtn);
    });

    copyTableBtn.addEventListener("click", () => {
        const table = tableDataDisplay.querySelector("table");
        if (!table) return;
        
        let csv = [];
        const rows = table.querySelectorAll("tr");
        for (let i = 0; i < rows.length; i++) {
            const row = [], cols = rows[i].querySelectorAll("td, th");
            for (let j = 0; j < cols.length; j++) {
                let text = cols[j].innerText.replace(/"/g, '""');
                row.push('"' + text + '"');
            }
            csv.push(row.join(";"));
        }
        copyTextToClipboard(csv.join("\n"), copyTableBtn);
    });

    // ============================================================
    // GESTION DES REQUÊTES ASYNCHRONES (POLLING)
    // ============================================================
    async function submitPrompt() {
        const prompt = promptInput.value.trim();
        if (!prompt) {
            addLog("⚠️ Veuillez saisir une consigne avant de valider.", "failed");
            return;
        }

        // Désactiver l'interface
        generateBtn.disabled = true;
        promptInput.disabled = true;
        spinner.classList.remove("hidden");
        btnIcon.classList.add("hidden");
        btnText.textContent = "Analyse en cours...";

        // Nettoyage console et onglets
        consoleLogs.innerHTML = "";
        addLog(`🔮 Requête soumise : "${prompt}"`);
        setStatus("running", "Initialisation");

        // Fermer un ancien polling
        if (pollingInterval) clearInterval(pollingInterval);

        try {
            const response = await fetch("/api/v1/maps/generate", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ prompt: prompt })
            });

            if (!response.ok) throw new Error(`HTTP ${response.status}`);

            const data = await response.json();
            activeTaskId = data.request_id;
            addLog(`✅ Requête acceptée par l'API. ID de tâche : ${activeTaskId}`);
            addLog(`🤖 Lancement de la chaîne d'agents...`, "running");

            // Lancer le polling de statut
            startPolling(activeTaskId, prompt);
        } catch (error) {
            addLog(`❌ Impossible de soumettre la requête : ${error.message}`, "failed");
            resetUI();
            setStatus("failed", "Échec");
        }
    }

    function startPolling(taskId, prompt) {
        let elapsed = 0;
        let lastLoggedStatus = "";

        pollingInterval = setInterval(async () => {
            elapsed += 1.5;
            try {
                const response = await fetch(`/api/v1/maps/status/${taskId}`);
                if (!response.ok) throw new Error(`HTTP ${response.status}`);
                
                const data = await response.json();
                
                // Logging intelligent
                if (data.status === "processing" && lastLoggedStatus !== "processing") {
                    addLog("📊 [SQL Agent] Extraction des données de PostgreSQL en cours...", "running");
                    addLog("🤖 [SIG Agent] Écriture et mise en forme du code spatial (VisCoder)...", "running");
                    lastLoggedStatus = "processing";
                    setStatus("running", "Calculs");
                }

                if (data.status === "completed") {
                    clearInterval(pollingInterval);
                    setStatus("success", "Succès");
                    addLog(`🎉 Succès global en ${data.execution_time.toFixed(2)} secondes !`, "success");
                    addLog("🎨 [Quality Agent] Le code s'est exécuté sans erreur dans la Sandbox.");
                    addLog("🗺️ Carte générée et prête pour l'affichage.");
                    
                    // Rendu de la carte
                    displayMapResults(data);
                    
                    // Ajouter à l'historique de session
                    addToHistory(taskId, prompt, data.image_url);
                    resetUI();
                } else if (data.status === "failed") {
                    clearInterval(pollingInterval);
                    setStatus("failed", "Échec");
                    addLog(`❌ Échec de génération des agents : ${data.error}`, "failed");
                    
                    // Affichage du code défectueux dans l'onglet Python
                    if (data.code) {
                        pythonCodeDisplay.textContent = data.code;
                        addLog("📜 Le code ayant échoué a été injecté dans l'onglet Code Python pour analyse.");
                    }
                    resetUI();
                }
            } catch (error) {
                addLog(`⚠️ Erreur lors du polling : ${error.message}`, "failed");
            }
        }, 1500);
    }

    function resetUI() {
        generateBtn.disabled = false;
        promptInput.disabled = false;
        spinner.classList.add("hidden");
        btnIcon.classList.remove("hidden");
        btnText.textContent = "Générer la Carte";
    }

    // Rendu graphique des onglets
    function displayMapResults(data) {
        // Rendu de l'image
        if (data.image_url) {
            mapPlaceholder.classList.add("hidden");
            mapImage.src = data.image_url;
            mapImage.classList.remove("hidden");
            downloadBtn.href = data.image_url;
            downloadBtn.classList.remove("hidden");
        } else {
            mapImage.classList.add("hidden");
            downloadBtn.classList.add("hidden");
            mapPlaceholder.classList.remove("hidden");
        }

        // Rendu du tableau
        if (data.table_html) {
            tableDataDisplay.innerHTML = data.table_html;
            copyTableBtn.classList.remove("hidden");
        } else {
            tableDataDisplay.innerHTML = `
                <div class="placeholder-view" id="tablePlaceholder">
                    <i class="fa-solid fa-table placeholder-icon"></i>
                    <h2>Aucune donnée disponible</h2>
                    <p>Saisissez une consigne demandant un tableau ou une analyse statistique.</p>
                </div>`;
            copyTableBtn.classList.add("hidden");
        }

        // Code Python
        pythonCodeDisplay.textContent = data.code;

        // Requête SQL
        sqlQueryDisplay.textContent = data.sql || "-- Aucune requête SQL requise.";
        
        // Basculer automatiquement sur l'onglet de la carte ou du tableau
        if (data.table_html && !data.image_url) {
            // Basculer vers l'onglet Tableau (index 1)
            tabBtns[1].click();
        } else {
            // Basculer vers l'onglet Rendu (index 0)
            tabBtns[0].click();
        }
    }

    // ============================================================
    // GESTION DE L'HISTORIQUE DE SESSION
    // ============================================================
    function addToHistory(id, prompt, imageUrl) {
        // Éviter les doublons
        if (history.some(item => item.id === id)) return;

        const date = new Date().toLocaleTimeString();
        history.unshift({ id, prompt, imageUrl, date });
        updateHistoryUI();
    }

    function updateHistoryUI() {
        if (history.length === 0) {
            historyGrid.innerHTML = `
                <div class="empty-history">
                    <i class="fa-solid fa-folder-open"></i>
                    <p>Aucun historique disponible pour le moment.</p>
                </div>`;
            return;
        }

        historyGrid.innerHTML = "";
        history.forEach(item => {
            const card = document.createElement("div");
            card.className = "history-card";
            card.innerHTML = `
                <div class="history-card-header">
                    <span>${item.date}</span>
                    <i class="fa-solid fa-chevron-right" style="color: var(--accent-color)"></i>
                </div>
                <div class="history-prompt">${item.prompt}</div>
                <div class="history-footer">
                    <span>ID: ${item.id.substring(0, 8)}...</span>
                </div>
            `;
            
            // Recharger la carte de l'historique sur un clic
            card.addEventListener("click", async () => {
                addLog(`🔄 Chargement de l'historique : "${item.prompt}"`);
                try {
                    const response = await fetch(`/api/v1/maps/status/${item.id}`);
                    if (response.ok) {
                        const data = await response.json();
                        displayMapResults(data);
                        addLog("✅ Carte historique chargée.");
                    } else {
                        addLog("❌ Impossible de recharger la carte historique.", "failed");
                    }
                } catch (err) {
                    addLog(`❌ Erreur : ${err.message}`, "failed");
                }
            });
            
            historyGrid.appendChild(card);
        });
    }

    // Déclencheur du bouton Générer
    generateBtn.addEventListener("click", submitPrompt);
    
    // Déclencheur de la touche Entrée (sans Shift)
    promptInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            submitPrompt();
        }
    });
});
