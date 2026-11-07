// ============================================================
// LOGIQUE APPLICATIVE FRONTEND — CARTAGEN (DGRE TUNISIE)
// ============================================================

// 1. Fonctions globales de Journalisation et Statut (Robustes & Universelles)
function addLog(message, type = "system") {
    console.log(`[CartaGen ${type.toUpperCase()}]`, message);
    const consoleLogs = document.getElementById("consoleLogs");
    if (!consoleLogs) return;
    const time = new Date().toLocaleTimeString();
    const line = document.createElement("div");
    line.className = `log-line ${type}`;
    line.innerHTML = `<span style="color: var(--text-muted)">[${time}]</span> ${message}`;
    consoleLogs.appendChild(line);
    consoleLogs.scrollTop = consoleLogs.scrollHeight;
}

function setStatus(status, text) {
    const statusIndicator = document.getElementById("statusIndicator");
    if (!statusIndicator) return;
    statusIndicator.className = `indicator ${status}`;
    statusIndicator.textContent = text;
}

// 2. Gestion de la Navigation par Onglets (Actifs & Cliquables)
function initTabs() {
    const tabBtns = document.querySelectorAll(".tab-btn");
    const tabContents = document.querySelectorAll(".tab-content");

    tabBtns.forEach(btn => {
        btn.addEventListener("click", (e) => {
            e.preventDefault();
            const tabId = btn.getAttribute("data-tab");
            if (!tabId) return;

            // Retirer l'état actif de tous les onglets
            tabBtns.forEach(b => b.classList.remove("active"));
            tabContents.forEach(c => c.classList.remove("active"));

            // Activer l'onglet cliqué et son contenu correspondant
            btn.classList.add("active");
            const targetContent = document.getElementById(tabId);
            if (targetContent) {
                targetContent.classList.add("active");
            }

            // Déclencheur spécifique pour le chargement .env
            if (tabId === "env-config" && typeof loadEnvConfig === "function") {
                loadEnvConfig();
            }
        });
    });
}

// 3. Gestion du Presse-papiers (Code Python et Tableau de Données)
function initClipboard() {
    function copyTextToClipboard(text, btnElement) {
        if (!text || !btnElement) return;
        navigator.clipboard.writeText(text).then(() => {
            const originalHTML = btnElement.innerHTML;
            btnElement.innerHTML = '<i class="fa-solid fa-check"></i> Copié !';
            btnElement.style.backgroundColor = "var(--success)";
            setTimeout(() => {
                btnElement.innerHTML = originalHTML;
                btnElement.style.backgroundColor = "";
            }, 2000);
        }).catch(err => {
            console.error("Erreur de copie presse-papiers:", err);
        });
    }

    const copyCodeBtn = document.getElementById("copyCodeBtn");
    const pythonCodeDisplay = document.getElementById("pythonCodeDisplay");
    if (copyCodeBtn && pythonCodeDisplay) {
        copyCodeBtn.addEventListener("click", (e) => {
            e.preventDefault();
            copyTextToClipboard(pythonCodeDisplay.textContent, copyCodeBtn);
        });
    }

    const copyTableBtn = document.getElementById("copyTableBtn");
    const tableDataDisplay = document.getElementById("tableDataDisplay");
    if (copyTableBtn && tableDataDisplay) {
        copyTableBtn.addEventListener("click", (e) => {
            e.preventDefault();
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
}


// ============================================================
// GESTION DU MODULE ANNUAIRE (BIMODAL PDF & WORD DOCX)
// ============================================================

function resetYearbookUI() {
    const generateYearbookBtn = document.getElementById("generateYearbookBtn");
    const yearbookSpinner = generateYearbookBtn ? generateYearbookBtn.querySelector(".yearbook-spinner") : null;
    if (generateYearbookBtn) generateYearbookBtn.disabled = false;
    if (yearbookSpinner) yearbookSpinner.classList.add("hidden");
}

function pollYearbookStatus(taskId, year, gouvText, requestedFormat) {
    const isUserDocx = (requestedFormat || "").toLowerCase() === "docx";
    const interval = setInterval(async () => {
        try {
            const response = await fetch(`/api/v1/maps/status/${taskId}`);
            if (!response.ok) throw new Error(`HTTP ${response.status}`);

            const data = await response.json();

            if (data.status === "completed") {
                clearInterval(interval);
                resetYearbookUI();
                setStatus("success", "Succès");

                // Un document n'est DOCX que si le backend a reellement confirme le format docx
                const hasRealDocx = (data.format === "docx") && (data.docx_url || (data.file_url && data.file_url.endsWith(".docx")));
                const isFinalDocx = hasRealDocx || (data.file_url && data.file_url.endsWith(".docx"));
                const formatLabel = isFinalDocx ? "Word (.docx)" : "PDF (.pdf)";

                if (yearbookResultTitle) {
                    yearbookResultTitle.textContent = `${gouvText} — ${year}-${year + 1}`;
                }

                if (yearbookResultDesc) {
                    if (isUserDocx && !isFinalDocx) {
                        yearbookResultDesc.textContent = `La version Word n'a pu être finalisée, la version PDF complète est prête au téléchargement ci-dessous.`;
                    } else {
                        yearbookResultDesc.textContent = `Le document a été généré avec succès en format ${formatLabel}.`;
                    }
                }

                if (yearbookResultIcon) {
                    if (isFinalDocx) {
                        yearbookResultIcon.className = "fa-solid fa-file-word pdf-large-icon";
                        yearbookResultIcon.style.color = "#2b579a";
                    } else {
                        yearbookResultIcon.className = "fa-solid fa-file-pdf pdf-large-icon";
                        yearbookResultIcon.style.color = "#e74c3c";
                    }
                }

                // Liens de telechargement
                const primaryUrl = isFinalDocx ? (data.docx_url || data.file_url) : (data.pdf_url || data.file_url);

                if (downloadYearbookLink && primaryUrl) {
                    downloadYearbookLink.href = primaryUrl;
                    downloadYearbookLink.setAttribute("download", `Annuaire_${gouvText}_${year}_${year+1}.${isFinalDocx ? "docx" : "pdf"}`);
                }

                if (downloadYearbookText) {
                    downloadYearbookText.textContent = isFinalDocx ? "Télécharger l'Annuaire (.docx)" : "Télécharger l'Annuaire (.pdf)";
                }

                if (downloadYearbookPdfLink) {
                    if (isFinalDocx && data.pdf_url) {
                        downloadYearbookPdfLink.href = data.pdf_url;
                        downloadYearbookPdfLink.classList.remove("hidden");
                    } else {
                        downloadYearbookPdfLink.classList.add("hidden");
                    }
                }

                if (yearbookResultBox) {
                    yearbookResultBox.classList.remove("hidden");
                }
            } else if (data.status === "failed") {
                clearInterval(interval);
                resetYearbookUI();
                setStatus("failed", "Échec");
                addLog(`❌ La génération de l'annuaire a échoué.`, "failed");

                const yearbookErrorText = document.getElementById("yearbookErrorText");
                const yearbookErrorLogs = document.getElementById("yearbookErrorLogs");
                const yearbookErrorBox = document.getElementById("yearbookErrorBox");

                if (yearbookErrorText) {
                    yearbookErrorText.textContent = "Une erreur est survenue lors de la génération ou conversion.";
                }
                if (yearbookErrorLogs) {
                    yearbookErrorLogs.textContent = data.error || "Aucune log d'erreur disponible.";
                }
                if (yearbookErrorBox) {
                    yearbookErrorBox.classList.remove("hidden");
                }
            }
        } catch (err) {
            console.error("[Yearbook Polling Error]", err);
        }
    }, 2000);
}

function initYearbook() {
    const generateYearbookBtn = document.getElementById("generateYearbookBtn");
    if (!generateYearbookBtn) return;

    async function handleGenerate(e) {
        if (e) {
            e.preventDefault();
            e.stopPropagation();
        }

        const yearbookYear = document.getElementById("yearbookYear");
        const yearbookGouv = document.getElementById("yearbookGouv");
        const yearbookFormat = document.getElementById("yearbookFormat");
        const yearbookSpinner = generateYearbookBtn.querySelector(".yearbook-spinner");
        const yearbookResultBox = document.getElementById("yearbookResultBox");
        const yearbookErrorBox = document.getElementById("yearbookErrorBox");

        const year = yearbookYear ? parseInt(yearbookYear.value) : 2021;
        const gouv = yearbookGouv ? yearbookGouv.value : "national";
        const gouvText = (yearbookGouv && yearbookGouv.selectedIndex >= 0) ? yearbookGouv.options[yearbookGouv.selectedIndex].text : "National";
        
        const format = (yearbookFormat && yearbookFormat.value) ? yearbookFormat.value.toLowerCase().trim() : "docx";
        const formatLabel = format === "docx" ? "Word (.docx)" : "PDF (.pdf)";

        if (!year || year < 2015 || year > 2024) {
            addLog("⚠️ Année invalide (doit être entre 2015 et 2024).", "failed");
            alert("Veuillez choisir une année valide entre 2015 et 2024.");
            return;
        }

        generateYearbookBtn.disabled = true;
        if (yearbookSpinner) yearbookSpinner.classList.remove("hidden");
        if (yearbookResultBox) yearbookResultBox.classList.add("hidden");
        if (yearbookErrorBox) yearbookErrorBox.classList.add("hidden");

        addLog(`⏳ Démarrage de la génération de l'annuaire (${formatLabel}) - ${gouvText} (${year}-${year + 1})`);
        setStatus("running", `Génération Annuaire (${formatLabel})`);

        try {
            console.log("[Yearbook] Envoi de la requête avec payload:", { year, gouv, format });
            const response = await fetch("/api/v1/yearbook/generate", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ year: year, gouv: gouv, format: format })
            });

            if (!response.ok) throw new Error(`HTTP ${response.status}`);

            const data = await response.json();
            const taskId = data.request_id;
            addLog(`✅ Tâche d'annuaire acceptée. ID: ${taskId}`);

            pollYearbookStatus(taskId, year, gouvText, format);
        } catch (error) {
            addLog(`❌ Échec d'envoi de la demande d'annuaire : ${error.message}`, "failed");
            resetYearbookUI();
            setStatus("failed", "Échec");

            if (yearbookErrorBox) {
                const logsEl = document.getElementById("yearbookErrorLogs");
                if (logsEl) logsEl.textContent = error.message;
                yearbookErrorBox.classList.remove("hidden");
            }
        }
    }

    // generateYearbookBtn.onclick = handleGenerate; // Removed to prevent double-triggering
    generateYearbookBtn.addEventListener("click", handleGenerate);
}


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

// LOGIQUE D'INGESTION DES SHAPEFILES SPATIAUX
    // ============================================================
    const ingestShapefilesBtn = document.getElementById("ingestShapefilesBtn");
    const shapefilesSpinner = document.getElementById("shapefilesSpinner");
    const shapefilesResultBox = document.getElementById("shapefilesResultBox");
    const shapefilesResultMsg = document.getElementById("shapefilesResultMsg");

    if (ingestShapefilesBtn) {
        ingestShapefilesBtn.addEventListener("click", async () => {
            const btnText = ingestShapefilesBtn.querySelector(".btn-text");
            const originalText = btnText.textContent;
            
            btnText.textContent = "Vérification et Ingestion...";
            ingestShapefilesBtn.disabled = true;
            shapefilesSpinner.classList.remove("hidden");
            shapefilesResultBox.classList.add("hidden");

            addLog("🗺️ Démarrage de l'importation/vérification des bases spatiales (Shapefiles)...", "system");

            try {
                const res = await fetch("/api/v1/data/ingest-shapefiles", {
                    method: "POST"
                });

                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || "Erreur d'importation des shapefiles.");

                if (shapefilesResultMsg) {
                    shapefilesResultMsg.innerHTML = data.message;
                }
                shapefilesResultBox.classList.remove("hidden");
                
                if (data.all_existed) {
                    addLog("✅ Les bases spatiales existent déjà. Aucune action supplémentaire requise.", "success");
                } else if (data.success) {
                    addLog("✅ Bases spatiales importées avec succès dans PostgreSQL (PostGIS).", "success");
                } else {
                    addLog("⚠️ L'importation s'est terminée avec des erreurs partielles. Vérifiez le rapport.", "failed");
                }
                
            } catch (err) {
                addLog(`❌ Erreur d'importation des Shapefiles : ${err.message}`, "error");
                if (shapefilesResultMsg) {
                    shapefilesResultMsg.innerHTML = `Erreur : ${err.message}`;
                    shapefilesResultBox.classList.remove("hidden");
                }
            } finally {
                btnText.textContent = originalText;
                ingestShapefilesBtn.disabled = false;
                shapefilesSpinner.classList.add("hidden");
            }
        });
    }

    // ============================================================

// CHAT ANNUAIRE RAG
    // ============================================================
    const chatMessages = document.getElementById("chatMessages");
    const chatQuestionInput = document.getElementById("chatQuestionInput");
    const sendChatBtn = document.getElementById("sendChatBtn");
    const chatSpinner = document.getElementById("chatSpinner");

    function resolveImageUrl(url) {
        if (!url) return "";
        if (url.startsWith("http://") || url.startsWith("https://") || url.startsWith("/")) {
            return url;
        }
        return `/api/v1/maps/image/${url}`;
    }

    function displayMapResult(imageUrl) {
        if (!imageUrl) return;
        const safeUrl = resolveImageUrl(imageUrl);
        const mapPlaceholder = document.getElementById("mapPlaceholder");
        const mapImage = document.getElementById("mapImage");
        const downloadBtn = document.getElementById("downloadBtn");

        if (mapPlaceholder) {
            mapPlaceholder.classList.add("hidden");
            mapPlaceholder.style.display = "none";
        }
        if (mapImage) {
            mapImage.src = safeUrl;
            mapImage.classList.remove("hidden");
            mapImage.style.display = "block";
        }
        if (downloadBtn) {
            downloadBtn.href = safeUrl;
            downloadBtn.classList.remove("hidden");
        }

        // Basculer sur l'onglet Rendu (visualisation)
        const renduBtn = document.querySelector('.tab-btn[data-tab="visualisation"]');
        if (renduBtn) {
            renduBtn.click();
        }
    }

    function renderSimpleMarkdown(rawText) {
        if (!rawText) return "";
        let text = rawText;

        // 1. Process markdown table if present
        const tableRegex = /(\|[^\n]+\|\r?\n\|[-: |]+\|\r?\n(?:\|[^\n]+\|\r?\n?)+)/g;
        text = text.replace(tableRegex, (match) => {
            const lines = match.trim().split(/\r?\n/).filter(l => l.trim().startsWith("|"));
            if (lines.length < 2) return match;
            const parseRow = (rowStr) => {
                return rowStr.split("|")
                    .slice(1, -1)
                    .map(c => c.trim());
            };
            const headerCells = parseRow(lines[0]);
            let html = '<div style="overflow-x:auto; margin:10px 0;"><table class="data-table" style="font-size:0.8rem; width:100%; border-collapse:collapse; min-width:auto; border-radius:6px; overflow:hidden;"><thead><tr>';
            headerCells.forEach(h => {
                html += `<th style="padding:6px 10px; background:#1e3a5f; color:#fff; border:1px solid rgba(255,255,255,0.1); text-align:left;">${h}</th>`;
            });
            html += '</tr></thead><tbody>';
            for (let i = 2; i < lines.length; i++) {
                const cells = parseRow(lines[i]);
                html += '<tr style="border-bottom:1px solid rgba(255,255,255,0.06);">';
                cells.forEach(c => {
                    html += `<td style="padding:5px 10px; border:1px solid rgba(255,255,255,0.05);">${c}</td>`;
                });
                html += '</tr>';
            }
            html += '</tbody></table></div>';
            return html;
        });

        // 2. Bold and italic
        text = text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
        text = text.replace(/\*(.*?)\*/g, '<em>$1</em>');

        // 3. Newlines outside tables
        const parts = text.split(/(<div style="overflow-x:auto[\s\S]*?<\/div>)/g);
        for (let i = 0; i < parts.length; i++) {
            if (!parts[i].startsWith('<div style="overflow-x:auto')) {
                parts[i] = parts[i].replace(/\n/g, '<br>');
            }
        }
        return parts.join('');
    }

    function appendChatMessage(role, text, sources, images, save = true) {
        if (!chatMessages) return;
        const wrapper = document.createElement("div");
        wrapper.style.cssText = `display:flex; flex-direction:column; gap:4px; align-items:${role === 'user' ? 'flex-end' : 'flex-start'}; margin-bottom:12px;`;

        const bubble = document.createElement("div");
        bubble.style.cssText = `
            max-width:92%; padding:12px 16px; border-radius:14px; line-height:1.6; font-size:0.9rem;
            background:${role === 'user'
                ? 'linear-gradient(135deg,rgba(52,152,219,0.7),rgba(41,128,185,0.7))'
                : 'rgba(255,255,255,0.07)'};
            color:#fff; border:1px solid rgba(255,255,255,0.1);
            border-bottom-right-radius:${role === 'user' ? '4px' : '14px'};
            border-bottom-left-radius:${role === 'user' ? '14px' : '4px'};
            ${role === 'user' ? 'white-space:pre-wrap;' : ''}
        `;
        if (role === 'assistant') {
            bubble.innerHTML = renderSimpleMarkdown(text);
        } else {
            bubble.textContent = text;
        }
        wrapper.appendChild(bubble);

        if (images && images.length > 0 && role === 'assistant') {
            images.forEach(imgUrl => {
                const safeUrl = resolveImageUrl(imgUrl);
                const img = document.createElement("img");
                img.src = safeUrl;
                img.style.cssText = "max-width:100%; max-height:300px; border-radius:8px; margin-top:8px; border:1px solid rgba(255,255,255,0.15); cursor:pointer; object-fit:contain;";
                img.title = "Cliquer pour afficher dans l'onglet Rendu";
                img.addEventListener("click", () => displayMapResult(safeUrl));
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

        if (save) {
            try {
                let history = JSON.parse(localStorage.getItem('cartagenChatHistory') || '[]');
                history.push({role, text, sources, images});
                localStorage.setItem('cartagenChatHistory', JSON.stringify(history));
            } catch (e) {
                console.error("Error saving chat history", e);
            }
        }
    }

    function renderAgentTraces(traces) {
        if (!workflowAgentsDisplay || !traces) return;

        const escapeHTML = (str) => {
            if (!str) return "";
            return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
        };
        
        let html = "";
        const agentTraces = traces || {};
        const busTraces = agentTraces.message_bus || [];

        // Rendu du Bus de Communication Inter-Agents
        if (busTraces && busTraces.length > 0) {
            html += `
            <div style="background: #111b27; border: 1px solid var(--border-color); border-radius: var(--radius-md); padding: 15px; margin-bottom: 20px;">
                <h4 style="margin: 0 0 12px 0; color: #38bdf8; font-size: 14px; display: flex; align-items: center; gap: 8px;">
                    <i class="fa-solid fa-network-wired"></i> Bus de Communication Inter-Agents (En Direct)
                </h4>
                <div style="display: flex; flex-direction: column; gap: 8px; max-height: 250px; overflow-y: auto;">`;
            
            busTraces.forEach(msg => {
                const statusColor = msg.status === 'SUCCESS' ? '#27ae60' : (msg.status === 'WARNING' ? '#f39c12' : (msg.status === 'ERROR' ? '#e74c3c' : '#3498db'));
                html += `
                <div style="display: flex; align-items: center; justify-content: space-between; background: #182635; padding: 8px 12px; border-radius: 6px; font-size: 12px; border-left: 4px solid ${statusColor};">
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <span style="font-weight: bold; color: #fff;">[${msg.sender} ➔ ${msg.receiver}]</span>
                        <span style="color: var(--text-muted);">${escapeHTML(msg.description)}</span>
                    </div>
                    <span style="font-size: 10px; padding: 2px 6px; border-radius: 4px; background: ${statusColor}22; color: ${statusColor}; font-weight: bold;">${msg.action}</span>
                </div>`;
            });

            html += `</div></div>`;
        }

        const agents = [
            { id: "annuaire_rag_agent", name: "Annuaire RAG Agent (Zvec + SQL + LLM)", icon: "fa-book-open-reader", color: "#f1c40f" },
            { id: "sql_agent", name: "SQL Generator Agent (PostgreSQL)", icon: "fa-database", color: "#3498db" },
            { id: "data_audit_agent", name: "Data Audit & Validation Agent", icon: "fa-clipboard-check", color: "#2ecc71" },
            { id: "sig_agent", name: "SIG & Chart Python Agent (GeoPandas)", icon: "fa-map-location-dot", color: "#9b59b6" }
        ];
        
        agents.forEach(agent => {
            const trace = agentTraces[agent.id];
            if (trace && (trace.system_prompt || trace.user_prompt || trace.response || trace.message)) {
                html += `
                <div class="agent-trace-card" style="border: 1px solid var(--border-color); border-radius: var(--radius-md); background: #111b27; overflow: hidden; margin-bottom: 15px; box-shadow: 0 4px 6px rgba(0,0,0,0.15);">
                    <div class="agent-trace-header" style="background: #182635; padding: 12px 15px; display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid var(--border-color);">
                        <div style="display: flex; align-items: center; gap: 10px;">
                            <i class="fa-solid ${agent.icon}" style="color: ${agent.color}; font-size: 16px;"></i>
                            <span style="font-weight: bold; color: var(--text-primary); font-size: 14px;">${agent.name}</span>
                        </div>
                        <span style="font-size: 11px; background: ${agent.color}22; color: ${agent.color}; padding: 2px 8px; border-radius: 20px; font-weight: bold; border: 1px solid ${agent.color}44;">Actif</span>
                    </div>
                    
                    <div class="agent-trace-body" style="padding: 15px; display: flex; flex-direction: column; gap: 12px;">
                        ${trace.message ? `
                        <div>
                            <div style="font-weight: bold; font-size: 11px; color: #2ecc71; margin-bottom: 5px; text-transform: uppercase;">
                                <i class="fa-solid fa-square-check"></i> Rapport d'Audit des Données
                            </div>
                            <div style="background: #090e15; padding: 10px; border-radius: var(--radius-sm); font-size: 12px; color: #e2e8f0; border: 1px solid #2ecc7144;">
                                ${escapeHTML(trace.message)}
                            </div>
                        </div>` : ''}
                        
                        ${trace.system_prompt ? `
                        <div>
                            <div style="font-weight: bold; font-size: 11px; color: var(--text-muted); margin-bottom: 5px; display: flex; align-items: center; gap: 5px; text-transform: uppercase;">
                                <i class="fa-solid fa-gears"></i> Prompt Système (Rôle et Règles)
                            </div>
                            <pre style="background: #090e15; padding: 10px; border-radius: var(--radius-sm); max-height: 120px; overflow-y: auto; margin: 0; font-size: 11.5px; border: 1px solid #182635; color: #9ca3af; white-space: pre-wrap;"><code style="font-family: monospace;">${escapeHTML(trace.system_prompt)}</code></pre>
                        </div>` : ''}
                        
                        ${trace.user_prompt ? `
                        <div>
                            <div style="font-weight: bold; font-size: 11px; color: var(--text-muted); margin-bottom: 5px; display: flex; align-items: center; gap: 5px; text-transform: uppercase;">
                                <i class="fa-solid fa-user-gear"></i> Prompt Utilisateur / Instructions
                            </div>
                            <pre style="background: #090e15; padding: 10px; border-radius: var(--radius-sm); max-height: 150px; overflow-y: auto; margin: 0; font-size: 11.5px; border: 1px solid #182635; color: #9ca3af; white-space: pre-wrap;"><code style="font-family: monospace;">${escapeHTML(trace.user_prompt)}</code></pre>
                        </div>` : ''}
                        
                        ${trace.response ? `
                        <div>
                            <div style="font-weight: bold; font-size: 11px; color: var(--text-primary); margin-bottom: 5px; display: flex; align-items: center; gap: 5px; text-transform: uppercase;">
                                <i class="fa-solid fa-reply-all" style="color: var(--primary-color);"></i> Réponse / Output de l'Agent
                            </div>
                            <pre style="background: #060a0f; padding: 12px; border-radius: var(--radius-sm); max-height: 250px; overflow-y: auto; margin: 0; font-size: 11.5px; border: 1px solid #3b82f622; color: #e2e8f0; white-space: pre-wrap;"><code style="font-family: monospace; color: #38bdf8;">${escapeHTML(trace.response)}</code></pre>
                        </div>` : ''}
                    </div>
                </div>`;
            }
        });
        
        if (html) {
            workflowAgentsDisplay.innerHTML = html;
        }
    }

    // Mode RAG par défaut : ACTIVÉ
    let isRagEnabled = true;
    const toggleRagBtn = document.getElementById("toggleRagBtn");
    const indexSpinner = document.getElementById("indexSpinner");
    const indexStatusMsg = document.getElementById("indexStatusMsg");

    if (toggleRagBtn) {
        toggleRagBtn.onclick = async function(e) {
            if (e) e.preventDefault();
            isRagEnabled = !isRagEnabled;
            const ragToggleText = document.getElementById("ragToggleText");

            if (isRagEnabled) {
                toggleRagBtn.style.background = "#27ae60";
                if (ragToggleText) ragToggleText.textContent = "RAG : ACTIVÉ";
                toggleRagBtn.setAttribute("data-enabled", "true");
                
                // Exécution automatique de l'indexation lors de l'activation
                if (indexSpinner) indexSpinner.classList.remove("hidden");
                if (indexStatusMsg) {
                    indexStatusMsg.textContent = "⏳ Indexation vectorielle auto en cours...";
                    indexStatusMsg.style.color = "#f1c40f";
                }
                
                try {
                    const res = await fetch("/api/v1/annuaire/index", { method: "POST" });
                    const data = await res.json();
                    if (indexStatusMsg) {
                        indexStatusMsg.textContent = "✅ RAG activé & Données indexées.";
                        indexStatusMsg.style.color = "#2ecc71";
                    }
                    console.log("🧠 Mode RAG activé et indexation lancée.");
                } catch (err) {
                    if (indexStatusMsg) {
                        indexStatusMsg.textContent = "⚠️ Indexation auto : " + err.message;
                    }
                } finally {
                    if (indexSpinner) indexSpinner.classList.add("hidden");
                }
            } else {
                toggleRagBtn.style.background = "#e74c3c";
                if (ragToggleText) ragToggleText.textContent = "RAG : DÉSACTIVÉ";
                toggleRagBtn.setAttribute("data-enabled", "false");
                if (indexStatusMsg) {
                    indexStatusMsg.textContent = "⚡ Mode Pure LLM actif (Sans RAG).";
                    indexStatusMsg.style.color = "#95a5a6";
                }
                console.log("⚡ Mode RAG désactivé : Exécution Pure LLM Direct");
            }
        };
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
        if (workflowAgentsDisplay) {
            workflowAgentsDisplay.innerHTML = `
            <div class="placeholder-view" id="workflowPlaceholder" style="text-align: center; padding: 40px 20px; color: var(--text-muted);">
                <i class="fa-solid fa-sync fa-spin" style="font-size: 40px; margin-bottom: 15px; color: var(--primary-color);"></i>
                <p style="margin: 0; font-size: 14px;">Analyse en cours... Les traces de l'agent RAG vont s'afficher d'un instant à l'autre.</p>
            </div>`;
        }
        const typingEl = document.createElement("div");
        typingEl.id = "typingIndicator";
        typingEl.style.cssText = "color:rgba(255,255,255,0.4); font-size:0.85rem; padding:8px;";
        typingEl.innerHTML = '<i class="fa-solid fa-ellipsis fa-beat"></i> L\'agent analyse les données...';
        if (chatMessages) {
            chatMessages.appendChild(typingEl);
            chatMessages.scrollTop = chatMessages.scrollHeight;
        }

        try {
            const res = await fetch("/api/v1/annuaire/chat", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ question, llm_provider: llmProvider, use_rag: isRagEnabled })
            });
            const initData = await res.json();
            if (!res.ok) throw new Error(initData.detail || "Échec d'initialisation de la tâche.");

            const taskId = initData.request_id;
            
            // Polling en direct pour mettre à jour les Traces Agents et le Chat
            let chatPolling = setInterval(async () => {
                try {
                    const statusRes = await fetch(`/api/v1/maps/status/${taskId}`);
                    if (!statusRes.ok) return;
                    
                    const data = await statusRes.json();
                    
                    // Rendu des traces des agents en temps réel
                    if (data.agent_traces) {
                        renderAgentTraces(data.agent_traces);
                    }
                    
                    if (data.status === "completed") {
                        clearInterval(chatPolling);
                        if (typingEl) typingEl.remove();
                        appendChatMessage("assistant", data.answer || "Aucune réponse générée.", data.sources || [], data.images || []);
                        addLog(`💬 Réponse annuaire générée (${data.nb_passages || 0} passages).`, "success");

                        const pythonDisplay = document.getElementById("pythonCodeDisplay");
                        if (pythonDisplay && (data.code || data.answer)) {
                            pythonDisplay.textContent = data.code || data.answer;
                        }

                        if (data.table_html) {
                            const tableDataDisplay = document.getElementById("tableDataDisplay");
                            const copyTableBtn = document.getElementById("copyTableBtn");
                            if (tableDataDisplay) tableDataDisplay.innerHTML = data.table_html;
                            if (copyTableBtn) copyTableBtn.classList.remove("hidden");
                            const wantsTable = /tableau|table|liste|données|donnees|relevé|releve|classement/i.test(question);
                            const tableBtn = document.querySelector('.tab-btn[data-tab="tableau-donnees"]');
                            if (tableBtn && wantsTable && (!data.images || data.images.length === 0)) {
                                tableBtn.click();
                            }
                        }

                        if (data.images && data.images.length > 0) {
                            displayMapResult(data.images[0]);
                        }

                        if (chatSpinner) chatSpinner.classList.add("hidden");
                        if (sendChatBtn) sendChatBtn.disabled = false;
                    } else if (data.status === "failed") {
                        clearInterval(chatPolling);
                        if (typingEl) typingEl.remove();
                        appendChatMessage("assistant", "❌ Erreur : " + (data.error || "Échec d'exécution du workflow."), []);
                        if (chatSpinner) chatSpinner.classList.add("hidden");
                        if (sendChatBtn) sendChatBtn.disabled = false;
                    }
                } catch (e) {
                    console.error("Erreur polling chat :", e);
                }
            }, 1000);
            
        } catch (err) {
            if (typingEl) typingEl.remove();
            appendChatMessage("assistant", "❌ Erreur réseau : " + err.message, []);
            if (chatSpinner) chatSpinner.classList.add("hidden");
            if (sendChatBtn) sendChatBtn.disabled = false;
        }
    }

    const chatBtn = document.getElementById("sendChatBtn");
    const chatInput = document.getElementById("chatQuestionInput");

    if (chatBtn) {
        chatBtn.onclick = function(e) {
            if (e) e.preventDefault();
            sendChatQuestion();
        };
    }
    if (chatInput) {
        chatInput.onkeydown = function(e) {
            if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                sendChatQuestion();
            }
        };
    }

    // Bouton Nouvelle Session / Effacer le chat
    const clearChatBtn = document.getElementById("clearChatBtn");
    if (clearChatBtn) {
        clearChatBtn.onclick = function() {
            if (confirm("Démarrer une nouvelle session de chat et effacer les messages actuels ?")) {
                localStorage.removeItem('cartagenChatHistory');
                if (chatMessages) {
                    chatMessages.innerHTML = `
                        <div class="chat-msg-system" style="
                            color:rgba(255,255,255,0.5); font-size:0.8rem; text-align:center;
                            padding:8px; border-radius:6px;">
                            <i class="fa-solid fa-info-circle"></i>
                            Nouvelle session démarrée. Posez votre question pluviométrique ci-dessous.
                        </div>
                    `;
                }
                addLog("🧹 Session de chat réinitialisée.", "info");
            }
        };
    }

    // Gestion de la session serveur : Efface automatiquement l'historique lors du redémarrage de "python run_app.py"
    async function initChatSession() {
        try {
            const res = await fetch('/api/v1/session/info');
            if (res.ok) {
                const data = await res.json();
                const currentBootId = data.boot_id;
                const savedBootId = localStorage.getItem('cartagenServerBootId');

                // Si le serveur a redémarré (nouvel identifiant de boot différent), effacer les anciens messages
                if (savedBootId && savedBootId !== currentBootId) {
                    console.log("[CartaGen] Redémarrage du serveur détecté -> Démarrage d'une nouvelle session de chat.");
                    localStorage.removeItem('cartagenChatHistory');
                }
                localStorage.setItem('cartagenServerBootId', currentBootId);
            }
        } catch (e) {
            console.warn("Impossible de vérifier l'ID de session serveur :", e);
        }

        // Charger l'historique seulement s'il appartient à cette session active
        try {
            let history = JSON.parse(localStorage.getItem('cartagenChatHistory') || '[]');
            if (history.length > 0 && chatMessages) {
                const systemMsg = chatMessages.querySelector(".chat-msg-system");
                if (systemMsg) systemMsg.remove();
                let lastImage = null;
                history.forEach(msg => {
                    appendChatMessage(msg.role, msg.text, msg.sources, msg.images, false);
                    if (msg.images && msg.images.length > 0) {
                        lastImage = msg.images[0];
                    }
                });
                if (lastImage) {
                    displayMapResult(lastImage);
                }
            }
        } catch (e) {
            console.error("Erreur lors du chargement de l'historique du chat :", e);
        }
    }

    initChatSession();

    // ============================================================

// GESTION DE LA CONFIGURATION DES VARIABLES .ENV
    // ============================================================
    const envStatusAlert = document.getElementById("envStatusAlert");
    const modeFormBtn = document.getElementById("modeFormBtn");
    const modeRawBtn = document.getElementById("modeRawBtn");
    const envFormView = document.getElementById("envFormView");
    const envRawView = document.getElementById("envRawView");
    const envRawTextarea = document.getElementById("envRawTextarea");
    const saveEnvBtn = document.getElementById("saveEnvBtn");
    const reloadEnvBtn = document.getElementById("reloadEnvBtn");
    const testDbBtn = document.getElementById("testDbBtn");
    const testLlmBtn = document.getElementById("testLlmBtn");
    const envTempSlider = document.getElementById("env_TEMPERATURE");
    const tempValueDisplay = document.getElementById("tempValueDisplay");

    function showEnvAlert(message, type = "success", duration = 6000) {
        if (!envStatusAlert) return;
        envStatusAlert.className = `env-alert ${type}`;
        const icon = type === "success" ? "fa-circle-check" : (type === "error" ? "fa-circle-exclamation" : "fa-triangle-exclamation");
        envStatusAlert.innerHTML = `<i class="fa-solid ${icon}"></i> <span>${message}</span>`;
        envStatusAlert.classList.remove("hidden");
        if (duration > 0) {
            setTimeout(() => {
                envStatusAlert.classList.add("hidden");
            }, duration);
        }
    }

    if (envTempSlider && tempValueDisplay) {
        envTempSlider.addEventListener("input", () => {
            tempValueDisplay.textContent = envTempSlider.value;
        });
    }

    // Bascule entre Formulaire et Éditeur Brut
    if (modeFormBtn && modeRawBtn && envFormView && envRawView) {
        modeFormBtn.addEventListener("click", () => {
            modeFormBtn.classList.add("active");
            modeRawBtn.classList.remove("active");
            envFormView.classList.add("active");
            envRawView.classList.remove("active");
        });
        modeRawBtn.addEventListener("click", () => {
            modeRawBtn.classList.add("active");
            modeFormBtn.classList.remove("active");
            envRawView.classList.add("active");
            envFormView.classList.remove("active");
        });
    }

    // Bascule visibilité mot de passe
    document.querySelectorAll(".toggle-pwd-btn").forEach(btn => {
        btn.addEventListener("click", () => {
            const input = btn.parentElement.querySelector("input");
            const icon = btn.querySelector("i");
            if (input.type === "password") {
                input.type = "text";
                icon.className = "fa-solid fa-eye-slash";
            } else {
                input.type = "password";
                icon.className = "fa-solid fa-eye";
            }
        });
    });

    // Charger les variables depuis l'API
    async function loadEnvConfig() {
        try {
            const res = await fetch("/api/v1/config/env");
            if (!res.ok) throw new Error("Impossible de lire la configuration .env");
            const data = await res.json();
            const vars = data.variables || {};

            // Remplissage des champs du formulaire
            const mapFields = [
                "LLM_PROVIDER", "TEMPERATURE", "MAX_TOKENS",
                "OPENROUTER_API_KEY", "OPENROUTER_MODEL",
                "GROQ_API_KEY", "GROQ_MODEL",
                "OPENAI_API_KEY", "OPENAI_MODEL",
                "HF_TOKEN", "OLLAMA_COLAB_URL", "OLLAMA_MODEL", "COLAB_MODEL",
                "DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD", "DATABASE_URL",
                "CACHE_TTL", "REDIS_HOST", "REDIS_PORT"
            ];

            mapFields.forEach(field => {
                const el = document.getElementById(`env_${field}`);
                if (el && vars[field] !== undefined) {
                    el.value = vars[field];
                    if (field === "TEMPERATURE" && tempValueDisplay) {
                        tempValueDisplay.textContent = vars[field];
                    }
                }
            });

            // Checkbox Cache
            const cacheCheckbox = document.getElementById("env_CACHE_ENABLED");
            if (cacheCheckbox && vars["CACHE_ENABLED"] !== undefined) {
                cacheCheckbox.checked = String(vars["CACHE_ENABLED"]).toLowerCase() === "true";
            }

            // Éditeur brut
            if (envRawTextarea) {
                envRawTextarea.value = data.raw || "";
            }
        } catch (err) {
            console.error("Erreur chargement .env :", err);
            showEnvAlert(`Erreur de chargement des paramètres : ${err.message}`, "error");
        }
    }

    // Sauvegarder les modifications
    async function saveEnvConfig() {
        if (!saveEnvBtn) return;
        const originalHtml = saveEnvBtn.innerHTML;
        saveEnvBtn.disabled = true;
        saveEnvBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Enregistrement...';

        try {
            const isRawMode = envRawView && envRawView.classList.contains("active");
            let payload = {};

            if (isRawMode) {
                payload = { raw: envRawTextarea ? envRawTextarea.value : "" };
            } else {
                const variables = {};
                const textFields = [
                    "LLM_PROVIDER", "TEMPERATURE", "MAX_TOKENS",
                    "OPENROUTER_API_KEY", "OPENROUTER_MODEL",
                    "GROQ_API_KEY", "GROQ_MODEL",
                    "OPENAI_API_KEY", "OPENAI_MODEL",
                    "HF_TOKEN", "OLLAMA_COLAB_URL", "OLLAMA_MODEL", "COLAB_MODEL",
                    "DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD", "DATABASE_URL",
                    "CACHE_TTL", "REDIS_HOST", "REDIS_PORT"
                ];

                textFields.forEach(field => {
                    const el = document.getElementById(`env_${field}`);
                    if (el) variables[field] = el.value.trim();
                });

                const cacheCheckbox = document.getElementById("env_CACHE_ENABLED");
                if (cacheCheckbox) {
                    variables["CACHE_ENABLED"] = cacheCheckbox.checked ? "true" : "false";
                }

                // Si les champs individuels de BDD sont modifiés, reconstruire DATABASE_URL
                if (variables["DB_USER"] && variables["DB_PASSWORD"] && variables["DB_HOST"] && variables["DB_PORT"] && variables["DB_NAME"]) {
                    const autoUrl = `postgresql://${variables["DB_USER"]}:${variables["DB_PASSWORD"]}@${variables["DB_HOST"]}:${variables["DB_PORT"]}/${variables["DB_NAME"]}`;
                    if (!variables["DATABASE_URL"] || variables["DATABASE_URL"].includes("@")) {
                        variables["DATABASE_URL"] = autoUrl;
                        const dbUrlEl = document.getElementById("env_DATABASE_URL");
                        if (dbUrlEl) dbUrlEl.value = autoUrl;
                    }
                }

                payload = { variables };
            }

            const res = await fetch("/api/v1/config/env", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });

            const result = await res.json();
            if (!res.ok) throw new Error(result.detail || "Échec de sauvegarde.");

            showEnvAlert("✅ Fichier .env enregistré et environnement applicatif rechargé avec succès !", "success");
            if (result.raw && envRawTextarea) {
                envRawTextarea.value = result.raw;
            }
        } catch (err) {
            console.error("Erreur sauvegarde .env :", err);
            showEnvAlert(`❌ Erreur lors de la sauvegarde : ${err.message}`, "error");
        } finally {
            saveEnvBtn.disabled = false;
            saveEnvBtn.innerHTML = originalHtml;
        }
    }

    // Tester la connexion PostgreSQL
    async function testDbConnection() {
        if (!testDbBtn) return;
        const originalHtml = testDbBtn.innerHTML;
        testDbBtn.disabled = true;
        testDbBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Test BDD...';

        try {
            const dbUrlEl = document.getElementById("env_DATABASE_URL");
            const dbUrl = dbUrlEl ? dbUrlEl.value.trim() : "";
            const res = await fetch("/api/v1/config/test-db", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ database_url: dbUrl })
            });
            const data = await res.json();
            if (data.success) {
                showEnvAlert(`✅ Connexion PostgreSQL réussie ! (${data.version}, ${data.tables_count} tables, latence: ${data.latency_ms}ms)`, "success", 8000);
            } else {
                showEnvAlert(`❌ Échec de connexion PostgreSQL : ${data.error}`, "error", 10000);
            }
        } catch (err) {
            showEnvAlert(`❌ Erreur requête test BDD : ${err.message}`, "error");
        } finally {
            testDbBtn.disabled = false;
            testDbBtn.innerHTML = originalHtml;
        }
    }

    // Tester le Provider LLM
    async function testLlmProvider() {
        if (!testLlmBtn) return;
        const originalHtml = testLlmBtn.innerHTML;
        testLlmBtn.disabled = true;
        testLlmBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Test LLM...';

        try {
            const providerEl = document.getElementById("env_LLM_PROVIDER");
            const provider = providerEl ? providerEl.value : "";
            const res = await fetch("/api/v1/config/test-llm", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ provider, prompt: "Reponds uniquement par le mot: OK" })
            });
            const data = await res.json();
            if (data.success) {
                showEnvAlert(`✅ Provider '${data.provider}' opérationnel ! Réponse : "${data.response}" (${data.latency_ms}ms)`, "success", 8000);
            } else {
                showEnvAlert(`❌ Provider '${data.provider}' indisponible : ${data.error}`, "error", 10000);
            }
        } catch (err) {
            showEnvAlert(`❌ Erreur requête test LLM : ${err.message}`, "error");
        } finally {
            testLlmBtn.disabled = false;
            testLlmBtn.innerHTML = originalHtml;
        }
    }

    if (saveEnvBtn) saveEnvBtn.addEventListener("click", saveEnvConfig);
    if (reloadEnvBtn) reloadEnvBtn.addEventListener("click", loadEnvConfig);
    if (testDbBtn) testDbBtn.addEventListener("click", testDbConnection);
    if (testLlmBtn) testLlmBtn.addEventListener("click", testLlmProvider);

    // Déclenchement automatique du chargement quand on clique sur l'onglet
    const envTabBtn = document.querySelector('.tab-btn[data-tab="env-config"]');
    if (envTabBtn) {
        envTabBtn.addEventListener("click", () => {
            loadEnvConfig();
        });
    }

    // Chargement initial
    loadEnvConfig();


// ============================================================
// INITIALISATION GLOBALE DE L'APPLICATION
// ============================================================
function initApp() {
    initTabs();
    initClipboard();
    initYearbook();
    
    // Charger dynamiquement les providers LLM au démarrage
    if (typeof loadDynamicProviders === "function") {
        loadDynamicProviders();
    }
    
    // Charger la configuration d'environnement .env au démarrage
    if (typeof loadEnvConfig === "function") {
        loadEnvConfig();
    }
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initApp);
} else {
    initApp();
}
