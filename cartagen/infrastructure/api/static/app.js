// ============================================================
// LOGIQUE APPLICATIVE FRONTEND — CARTAGEN
// ============================================================

document.addEventListener("DOMContentLoaded", () => {
    // Éléments du DOM
    const promptInput = document.getElementById("promptInput");
    const generateBtn = document.getElementById("generateBtn");
    const spinner = generateBtn ? generateBtn.querySelector(".spinner") : null;
    const btnIcon = generateBtn ? generateBtn.querySelector(".btn-icon") : null;
    const btnText = generateBtn ? generateBtn.querySelector(".btn-text") : null;
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
        if (!consoleLogs) return; // sidebar removed
        const time = new Date().toLocaleTimeString();
        const line = document.createElement("div");
        line.className = `log-line ${type}`;
        line.innerHTML = `<span style="color: var(--text-muted)">[${time}]</span> ${message}`;
        consoleLogs.appendChild(line);
        consoleLogs.scrollTop = consoleLogs.scrollHeight;
    }

    function setStatus(status, text) {
        if (!statusIndicator) return; // sidebar removed
        statusIndicator.className = `indicator ${status}`;
        statusIndicator.textContent = text;
    }

    if (window.location.protocol === 'file:') {
        addLog("⚠️ ATTENTION : Vous avez ouvert la page en fichier local (file://). Pour exécuter les requêtes IA et générer les annuaires, lancez 'python run_app.py' et ouvrez http://localhost:8000", "error");
    }

    // ============================================================
    // SUGGESTIONS RAPIDES
    // ============================================================
    // Suggestions rapides (sidebar supprimée — guard null)
    suggestChips.forEach(chip => {
        chip.addEventListener("click", () => {
            if (promptInput) { promptInput.value = chip.textContent; promptInput.focus(); }
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

    if (copyCodeBtn) {
        copyCodeBtn.addEventListener("click", () => {
            copyTextToClipboard(pythonCodeDisplay.textContent, copyCodeBtn);
        });
    }

    if (copySqlBtn) {
        copySqlBtn.addEventListener("click", () => {
            copyTextToClipboard(sqlQueryDisplay.textContent, copySqlBtn);
        });
    }

    if (copyTableBtn) {
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
    }

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
        if (generateBtn) generateBtn.disabled = true;
        if (promptInput) promptInput.disabled = true;
        if (spinner) spinner.classList.remove("hidden");
        if (btnIcon) btnIcon.classList.add("hidden");
        if (btnText) btnText.textContent = "Analyse en cours...";

        const providerSelect = document.getElementById("llmProviderSelect");
        const selectedProvider = providerSelect ? providerSelect.value : "openrouter";

        // Nettoyage console et onglets
        if (consoleLogs) consoleLogs.innerHTML = "";
        addLog(`🔮 Requête soumise : "${prompt}" (Modèle/Provider: ${selectedProvider})`);
        setStatus("running", "Initialisation");

        // Fermer un ancien polling
        if (pollingInterval) clearInterval(pollingInterval);

        try {
            const response = await fetch("/api/v1/maps/generate", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    prompt: prompt,
                    llm_provider: selectedProvider
                })
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
        if (generateBtn) generateBtn.disabled = false;
        if (promptInput) promptInput.disabled = false;
        if (spinner) spinner.classList.add("hidden");
        if (btnIcon) btnIcon.classList.remove("hidden");
        if (btnText) btnText.textContent = "Générer la Carte";
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

    if (generateBtn) generateBtn.addEventListener("click", submitPrompt);

    if (promptInput) {
        promptInput.addEventListener("keydown", (e) => {
            if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submitPrompt();
            }
        });
    }

    // ============================================================
    // GESTION DU MODULE ANNUAIRE
    // ============================================================
    const generateYearbookBtn = document.getElementById("generateYearbookBtn");
    const yearbookYear = document.getElementById("yearbookYear");
    const yearbookGouv = document.getElementById("yearbookGouv");
    const yearbookResultBox = document.getElementById("yearbookResultBox");
    const yearbookResultTitle = document.getElementById("yearbookResultTitle");
    const downloadYearbookLink = document.getElementById("downloadYearbookLink");
    const yearbookErrorBox = document.getElementById("yearbookErrorBox");
    const yearbookErrorText = document.getElementById("yearbookErrorText");
    const yearbookErrorLogs = document.getElementById("yearbookErrorLogs");
    const yearbookSpinner = generateYearbookBtn ? generateYearbookBtn.querySelector(".yearbook-spinner") : null;

    if (generateYearbookBtn) {
        generateYearbookBtn.addEventListener("click", async () => {
        const year = parseInt(yearbookYear.value);
        const gouv = yearbookGouv.value;
        const gouvText = yearbookGouv.options[yearbookGouv.selectedIndex].text;

        if (!year || year < 2015 || year > 2024) {
            addLog("⚠️ Année invalide (doit être entre 2015 et 2024).", "failed");
            return;
        }

        // Bloquer l'interface de l'annuaire
        generateYearbookBtn.disabled = true;
        yearbookSpinner.classList.remove("hidden");
        yearbookResultBox.classList.add("hidden");
        yearbookErrorBox.classList.add("hidden");

        addLog(`📂 Démarrage de la génération de l'annuaire - ${gouvText} (${year}-${year + 1})`);
        setStatus("running", "Génération Annuaire");

        try {
            const response = await fetch("/api/v1/yearbook/generate", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ year: year, gouv: gouv })
            });

            if (!response.ok) throw new Error(`HTTP ${response.status}`);

            const data = await response.json();
            const taskId = data.request_id;
            addLog(`✅ Tâche d'annuaire acceptée. ID: ${taskId}`);

            // Lancer le polling pour l'annuaire
            pollYearbookStatus(taskId, year, gouvText);
        } catch (error) {
            addLog(`❌ Échec d'envoi de la demande d'annuaire : ${error.message}`, "failed");
            resetYearbookUI();
            setStatus("failed", "Échec");
        }
    });
}

    function resetYearbookUI() {
        generateYearbookBtn.disabled = false;
        yearbookSpinner.classList.add("hidden");
    }

    function pollYearbookStatus(taskId, year, gouvText) {
        const interval = setInterval(async () => {
            try {
                const response = await fetch(`/api/v1/maps/status/${taskId}`);
                if (!response.ok) throw new Error(`HTTP ${response.status}`);

                const data = await response.json();

                if (data.status === "completed") {
                    clearInterval(interval);
                    resetYearbookUI();
                    setStatus("success", "Succès");
                    addLog(`🎉 Annuaire généré avec succès en PDF !`, "success");

                    yearbookResultTitle.textContent = `Annuaire ${gouvText} — ${year}-${year + 1}`;
                    downloadYearbookLink.href = data.pdf_url;
                    yearbookResultBox.classList.remove("hidden");
                } else if (data.status === "failed") {
                    clearInterval(interval);
                    resetYearbookUI();
                    setStatus("failed", "Échec");
                    addLog(`❌ La génération de l'annuaire a échoué.`, "failed");

                    yearbookErrorText.textContent = "Une erreur est survenue lors de l'extraction des données ou de la compilation LaTeX.";
                    yearbookErrorLogs.textContent = data.error || "Aucune log d'erreur disponible.";
                    yearbookErrorBox.classList.remove("hidden");
                }
            } catch (err) {
                console.error("Erreur de polling annuaire:", err);
            }
        }, 2000);
    }

    // ============================================================
    // GESTION DYNAMIQUE DES PROVIDERS LLM (API, COLAB, KAGGLE, LOCAL)
    // ============================================================
    const llmProviderSelect = document.getElementById("llmProviderSelect");
    const providerModal = document.getElementById("providerModal");
    const openAddProviderModalBtn = document.getElementById("openAddProviderModalBtn");
    const closeProviderModalBtn = document.getElementById("closeProviderModalBtn");
    const cancelProviderBtn = document.getElementById("cancelProviderBtn");
    const addProviderForm = document.getElementById("addProviderForm");

    async function loadDynamicProviders(selectedIdToKeep = null) {
        try {
            const res = await fetch("/api/v1/providers");
            if (!res.ok) return;
            const data = await res.json();

            if (data.providers && data.providers.length > 0 && llmProviderSelect) {
                llmProviderSelect.innerHTML = "";
                data.providers.forEach(p => {
                    const opt = document.createElement("option");
                    opt.value = p.id;
                    let typeBadge = (p.exec_type || "API").toUpperCase();
                    opt.textContent = `${p.name} [${typeBadge} | ${p.model}]`;
                    if (selectedIdToKeep ? p.id === selectedIdToKeep : p.is_default) {
                        opt.selected = true;
                    }
                    llmProviderSelect.appendChild(opt);
                });
            }
        } catch (err) {
            console.warn("Impossible de charger les providers dynamiques:", err);
        }
    }

    // Charger les providers dès le démarrage de la page
    loadDynamicProviders();

    if (openAddProviderModalBtn) {
        openAddProviderModalBtn.addEventListener("click", (e) => {
            e.preventDefault();
            e.stopPropagation();
            if (providerModal) {
                providerModal.classList.remove("hidden");
            }
        });
    }

    function closeProviderModal() {
        if (providerModal) {
            providerModal.classList.add("hidden");
        }
    }

    if (closeProviderModalBtn) closeProviderModalBtn.addEventListener("click", closeProviderModal);
    if (cancelProviderBtn) cancelProviderBtn.addEventListener("click", closeProviderModal);
    if (providerModal) {
        providerModal.addEventListener("click", (e) => {
            if (e.target === providerModal) closeProviderModal();
        });
    }

    if (addProviderForm) {
        addProviderForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            const name = document.getElementById("provName").value.trim();
            const exec_type = document.getElementById("provExecType").value;
            const endpoint_url = document.getElementById("provEndpoint").value.trim();
            const model = document.getElementById("provModel").value.trim();
            const api_key = document.getElementById("provApiKey").value.trim();

            try {
                const res = await fetch("/api/v1/providers/add", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ name, exec_type, endpoint_url, model, api_key })
                });

                if (!res.ok) throw new Error(`Erreur ${res.status}`);
                const data = await res.json();

                addLog(`✨ Nouveau Provider configuré : "${data.provider.name}" (${data.provider.exec_type})`, "success");
                closeProviderModal();
                addProviderForm.reset();

                // Recharger le select et sélectionner le nouveau provider
                await loadDynamicProviders(data.provider.id);
            } catch (err) {
                alert("Erreur lors de l'enregistrement du provider: " + err.message);
            }
        });
    }

    // ============================================================
    // LOGIQUE D'INGESTION DES FICHIERS MDB
    // ============================================================
    const ingestMdbForm = document.getElementById("ingestMdbForm");
    const ingestResultBox = document.getElementById("ingestResultBox");
    const ingestResultMsg = document.getElementById("ingestResultMsg");
    const ingestMdbBtn = document.getElementById("ingestMdbBtn");

    if (ingestMdbForm) {
        ingestMdbForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            const fileInput = document.getElementById("ingestFile");
            if (!fileInput.files.length) return;

            const file = fileInput.files[0];
            const formData = new FormData();
            formData.append("file", file);

            const btnText = ingestMdbBtn.querySelector(".btn-text");
            const originalText = btnText.textContent;
            btnText.textContent = "Ingestion & Détection en cours...";
            ingestMdbBtn.disabled = true;
            ingestResultBox.classList.add("hidden");

            addLog(`📤 Transmission du fichier Access "${file.name}" (détection automatique du gouvernorat)...`, "system");

            try {
                const res = await fetch("/api/v1/data/ingest-mdb", {
                    method: "POST",
                    body: formData
                });

                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || "Erreur d'ingestion.");

                const reportEl = document.getElementById("ingestReportDetails");
                const nbLignes = data.nb_pluies || 0;
                const gouvNom = data.gouvernorat || "Inconnu";

                if (reportEl) {
                    reportEl.innerHTML = `
                        <div style="display:flex; flex-direction:column; gap:10px;">
                            <div style="font-size:1.05rem; padding-bottom:8px; border-bottom:1px solid rgba(255,255,255,0.1);">
                                📍 <strong>Gouvernorat :</strong> <span style="color:#3498db; font-size:1.1rem; font-weight:700;">${gouvNom}</span>
                                &nbsp;&nbsp;|&nbsp;&nbsp;
                                📊 <strong>Lignes ajoutées :</strong> <span style="color:#2ecc71; font-size:1.1rem; font-weight:700;">${nbLignes.toLocaleString('fr-FR')} lignes</span>
                            </div>
                            <div style="display:grid; grid-template-columns: 1fr 1fr; gap: 8px;">
                                <div>📄 <strong>Fichier source :</strong> ${data.fichier || file.name}</div>
                                <div>🏢 <strong>Stations impactées :</strong> ${data.nb_stations || 0} station(s)</div>
                                <div>📅 <strong>Période observée :</strong> du ${data.date_min || 'N/A'} au ${data.date_max || 'N/A'}</div>
                                <div>🗃️ <strong>Table cible PostgreSQL :</strong> <code>ann_pluies</code></div>
                            </div>
                        </div>
                    `;
                }

                ingestResultMsg.textContent = `Gouvernorat : ${gouvNom} — ${nbLignes.toLocaleString('fr-FR')} lignes de la table 'pluies' ajoutées avec succès.`;
                ingestResultBox.classList.remove("hidden");
                addLog(`✅ Union réussie pour ${gouvNom} : ${nbLignes.toLocaleString('fr-FR')} lignes de relevés ajoutées à 'ann_pluies'.`, "success");
                ingestMdbForm.reset();
            } catch (err) {
                addLog(`❌ Erreur d'ingestion MDB : ${err.message}`, "error");
                alert(`Erreur d'ingestion : ${err.message}`);
            } finally {
                btnText.textContent = originalText;
                ingestMdbBtn.disabled = false;
            }
        });
    }

    // ============================================================
    // CHAT ANNUAIRE RAG
    // ============================================================
    const indexAnnuaireBtn = document.getElementById("indexAnnuaireBtn");
    const indexStatusMsg = document.getElementById("indexStatusMsg");
    const indexSpinner = document.getElementById("indexSpinner");
    const chatMessages = document.getElementById("chatMessages");
    const chatQuestionInput = document.getElementById("chatQuestionInput");
    const sendChatBtn = document.getElementById("sendChatBtn");
    const chatSpinner = document.getElementById("chatSpinner");

    function appendChatMessage(role, text, sources, images) {
        if (!chatMessages) return;
        const wrapper = document.createElement("div");
        wrapper.style.cssText = `display:flex; flex-direction:column; gap:4px; align-items:${role === 'user' ? 'flex-end' : 'flex-start'}; margin-bottom:12px;`;

        const bubble = document.createElement("div");
        bubble.style.cssText = `
            max-width:85%; padding:12px 16px; border-radius:14px; line-height:1.6; font-size:0.9rem;
            background:${role === 'user'
                ? 'linear-gradient(135deg,rgba(52,152,219,0.7),rgba(41,128,185,0.7))'
                : 'rgba(255,255,255,0.07)'};
            color:#fff; border:1px solid rgba(255,255,255,0.1);
            border-bottom-right-radius:${role === 'user' ? '4px' : '14px'};
            border-bottom-left-radius:${role === 'user' ? '14px' : '4px'};
            white-space:pre-wrap;
        `;
        bubble.textContent = text;
        wrapper.appendChild(bubble);

        if (images && images.length > 0 && role === 'assistant') {
            images.forEach(imgUrl => {
                const img = document.createElement("img");
                img.src = imgUrl;
                img.style.cssText = "max-width:100%; max-height:300px; border-radius:8px; margin-top:8px; border:1px solid rgba(255,255,255,0.15); cursor:pointer; object-fit:contain;";
                img.title = "Cliquer pour ouvrir en grand";
                img.addEventListener("click", () => window.open(imgUrl, '_blank'));
                wrapper.appendChild(img);
            });
        }

        if (sources && sources.length > 0 && role === 'assistant') {
            const srcDiv = document.createElement("div");
            srcDiv.style.cssText = "font-size:0.73rem; color:rgba(255,255,255,0.4); padding-left:4px;";
            srcDiv.textContent = "📚 Sources : " + sources.join(", ");
            wrapper.appendChild(srcDiv);
        }

        // Remove the system welcome message on first real message
        const systemMsg = chatMessages.querySelector(".chat-msg-system");
        if (systemMsg) systemMsg.remove();

        chatMessages.appendChild(wrapper);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    function appendTypingIndicator() {
        if (!chatMessages) return null;
        const div = document.createElement("div");
        div.id = "typingIndicator";
        div.style.cssText = "color:rgba(255,255,255,0.4); font-size:0.85rem; padding:8px;";
        div.innerHTML = '<i class="fa-solid fa-ellipsis fa-beat"></i> L\'agent analyse les données...';
        chatMessages.appendChild(div);
        chatMessages.scrollTop = chatMessages.scrollHeight;
        return div;
    }

    if (indexAnnuaireBtn) {
        indexAnnuaireBtn.addEventListener("click", async () => {
            const originalText = indexAnnuaireBtn.querySelector(".btn-text").textContent;
            indexAnnuaireBtn.querySelector(".btn-text").textContent = "Indexation...";
            if (indexSpinner) indexSpinner.classList.remove("hidden");
            indexAnnuaireBtn.disabled = true;
            if (indexStatusMsg) indexStatusMsg.textContent = "⏳ Indexation en cours (peut prendre 1-2 minutes)...";

            try {
                const res = await fetch("/api/v1/annuaire/index", { method: "POST" });
                const data = await res.json();
                if (indexStatusMsg) {
                    indexStatusMsg.textContent = "✅ " + (data.message || "Indexation démarrée en arrière-plan.");
                    indexStatusMsg.style.color = "#2ecc71";
                }
                addLog("✅ Indexation des données annuaire lancée.", "success");
            } catch (err) {
                if (indexStatusMsg) {
                    indexStatusMsg.textContent = "❌ Erreur : " + err.message;
                    indexStatusMsg.style.color = "#e74c3c";
                }
            } finally {
                indexAnnuaireBtn.querySelector(".btn-text").textContent = originalText;
                if (indexSpinner) indexSpinner.classList.add("hidden");
                indexAnnuaireBtn.disabled = false;
            }
        });
    }

    async function sendChatQuestion() {
        const question = chatQuestionInput ? chatQuestionInput.value.trim() : "";
        if (!question) return;

        appendChatMessage("user", question);
        chatQuestionInput.value = "";

        const llmProvider = document.getElementById("llmProviderSelect")
            ? document.getElementById("llmProviderSelect").value
            : null;

        if (chatSpinner) chatSpinner.classList.remove("hidden");
        if (sendChatBtn) sendChatBtn.disabled = true;
        const typingEl = appendTypingIndicator();

        try {
            const res = await fetch("/api/v1/annuaire/chat", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ question, llm_provider: llmProvider })
            });
            const data = await res.json();
            if (typingEl) typingEl.remove();

            if (!res.ok) {
                appendChatMessage("assistant", "❌ Erreur : " + (data.detail || "Réponse invalide."), []);
            } else {
                appendChatMessage("assistant", data.answer || "Aucune réponse générée.", data.sources || [], data.images || []);
                addLog(`💬 Réponse annuaire générée (${data.nb_passages || 0} passages).`, "success");

                // Projection automatique du tableau HTML sur l'onglet Tableau
                if (data.table_html) {
                    if (tableDataDisplay) tableDataDisplay.innerHTML = data.table_html;
                    if (copyTableBtn) copyTableBtn.classList.remove("hidden");
                    // Toujours basculer sur l'onglet Tableau (index 1) si un tableau est disponible et pas d'image
                    const tableBtn = document.querySelector('.tab-btn[data-tab="tableau-donnees"]');
                    if (tableBtn && (!data.images || data.images.length === 0)) {
                        tableBtn.click();
                    }
                }

                // Projection automatique de l'image/carte sur l'onglet Rendu
                if (data.images && data.images.length > 0) {
                    const firstImage = data.images[0];
                    if (mapPlaceholder) mapPlaceholder.classList.add("hidden");
                    if (mapImage) {
                        mapImage.src = firstImage;
                        mapImage.classList.remove("hidden");
                    }
                    if (downloadBtn) {
                        downloadBtn.href = firstImage;
                        downloadBtn.classList.remove("hidden");
                    }
                    // Basculer automatiquement sur l'onglet Rendu (index 0)
                    if (tabBtns && tabBtns.length > 0) {
                        tabBtns[0].click();
                    }
                }
            }
        } catch (err) {
            if (typingEl) typingEl.remove();
            appendChatMessage("assistant", "❌ Erreur réseau : " + err.message, []);
        } finally {
            if (chatSpinner) chatSpinner.classList.add("hidden");
            if (sendChatBtn) sendChatBtn.disabled = false;
        }
    }

    if (sendChatBtn) {
        sendChatBtn.addEventListener("click", sendChatQuestion);
    }
    if (chatQuestionInput) {
        chatQuestionInput.addEventListener("keydown", (e) => {
            if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                sendChatQuestion();
            }
        });
    }
});
