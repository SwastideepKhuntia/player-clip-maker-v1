/**
 * Player Clip Maker Pro Studio — Full Controller
 * Supporting 4-Slot Multi-Half Ingestion, Live WhoScored Scraping, Dynamic Team/Player Mapping,
 * Grouped Event Checkboxes, and Premiere Pro Timeline Studio.
 */

(function () {
    "use strict";

    // Dynamic API Base Configuration for Production / Vercel
    const API_BASE = (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1" || window.location.protocol === "file:")
        ? "" 
        : "https://player-clip-maker-v1-1.onrender.com";

    function apiUrl(endpoint) {
        if (!endpoint) return "";
        if (endpoint.startsWith("http://") || endpoint.startsWith("https://")) return endpoint;
        if (!endpoint.startsWith("/")) endpoint = "/" + endpoint;
        return `${API_BASE}${endpoint}`;
    }

    // View Navigation Tabs
    const tabNavGenerator = document.getElementById("tab-nav-generator");
    const tabNavStudio = document.getElementById("tab-nav-studio");
    const generatorView = document.getElementById("generator-view");
    const studioView = document.getElementById("studio-view");

    // 4-Slot Video Ingestion Elements
    const slot1hZone = document.getElementById("slot-1h-zone");
    const slot2hZone = document.getElementById("slot-2h-zone");
    const slotEtZone = document.getElementById("slot-et-zone");
    const slotFullZone = document.getElementById("slot-full-zone");

    const video1hInput = document.getElementById("video-1h-input");
    const video2hInput = document.getElementById("video-2h-input");
    const videoEtInput = document.getElementById("video-et-input");
    const videoFullInput = document.getElementById("video-full-input");

    const video1hFilename = document.getElementById("video-1h-filename");
    const video2hFilename = document.getElementById("video-2h-filename");
    const videoEtFilename = document.getElementById("video-et-filename");
    const videoFullFilename = document.getElementById("video-full-filename");

    const slot1hStatus = document.getElementById("slot-1h-status");
    const slot2hStatus = document.getElementById("slot-2h-status");
    const slotEtStatus = document.getElementById("slot-et-status");
    const slotFullStatus = document.getElementById("slot-full-status");

    // CSV & API Ingestion
    const csvDropZone = document.getElementById("csv-drop-zone");
    const csvInput = document.getElementById("csv-input");
    const csvFileName = document.getElementById("csv-file-name");

    const whoscoredUrlInput = document.getElementById("whoscored-url-input");
    const whoscoredScrapeBtn = document.getElementById("whoscored-scrape-btn");
    const scoreswayUrlInput = document.getElementById("scoresway-url-input");
    const scoreswayScrapeBn = document.getElementById("scoresway-scrape-btn");
    const uploadBtn = document.getElementById("upload-btn");

    // State Variables (hoisted before any callbacks)
    let currentMatchTeams = ["Chelsea", "Brighton"];
    let currentMatchPlayers = [];
    let currentTeamPlayersMap = {};

    const uploadedNames = {
        video_1h: null,
        video_2h: null,
        video_et1: null,
        video: null,
        csv: null
    };

    const files = {
        video_1h: null,
        video_2h: null,
        video_et1: null,
        video: null,
        csv: null
    };

    // Kairo Settings & Team Radios
    const kairoMatchTitle = document.getElementById("kairo-match-title");
    const kairoRadioTeamA = document.getElementById("kairo-radio-team-a");
    const kairoRadioTeamB = document.getElementById("kairo-radio-team-b");
    const kairoTeamAName = document.getElementById("kairo-team-a-name");
    const kairoTeamBName = document.getElementById("kairo-team-b-name");
    const kairoPlayerSelect = document.getElementById("kairo-player-select");
    const kairoSelectAllEvents = document.getElementById("kairo-select-all-events");
    const kairoEventsStatusText = document.getElementById("kairo-events-status-text");

    const playerNameInput = document.getElementById("player-name-input");
    const teamNameInput = document.getElementById("team-name-input");
    const playerDatalist = document.getElementById("player-datalist");
    const teamDatalist = document.getElementById("team-datalist");

    const fhKickoffInput = document.getElementById("fh-kickoff-input");
    const shKickoffInput = document.getElementById("sh-kickoff-input");
    const halvesInclude = document.getElementById("halves-include");

    const preBufferInput = document.getElementById("pre-buffer-input");
    const postBufferInput = document.getElementById("post-buffer-input");
    const mergeGapInput = document.getElementById("merge-gap-input");
    const topXInput = document.getElementById("top-x-input");
    const minScoreInput = document.getElementById("min-score-input");
    const minScoreValue = document.getElementById("min-score-value");
    const minXtInput = document.getElementById("min-xt-input");

    const musicSelect = document.getElementById("music-select");
    const muteOriginalInput = document.getElementById("mute-original-input");

    const outputFolderInput = document.getElementById("output-folder-input");
    const browseDirBtn = document.getElementById("browse-dir-btn");
    const outputFilenameInput = document.getElementById("output-filename-input");
    const saveIndividualInput = document.getElementById("save-individual-input");
    const generateBtn = document.getElementById("generate-btn");

    const statusContainer = document.getElementById("status-container");
    const statusText = document.getElementById("status-text");
    const progressFill = document.getElementById("progress-fill");

    const resultSection = document.getElementById("result-section");
    const resultVideo = document.getElementById("result-video");
    const savedPathLabel = document.getElementById("saved-path-label");
    const downloadLink = document.getElementById("download-link");
    const sendToStudioBtn = document.getElementById("send-to-studio-btn");

    // Studio Elements
    const kairoStudioVideo = document.getElementById("kairo-studio-video");
    const kairoStudioBackBtn = document.getElementById("kairo-studio-back-btn");
    const editorClipsList = document.getElementById("editor-clips-list");
    const prevClipBtn = document.getElementById("prev-clip-btn");
    const nextClipBtn = document.getElementById("next-clip-btn");
    const currentClipLabel = document.getElementById("current-clip-label");
    const finalizeRenderBtn = document.getElementById("finalize-render-btn");

    let studioClips = [];
    let activeClipIndex = 0;

    // Toast Notification Utility
    function toast(msg, type = "info") {
        const container = document.getElementById("toast-container");
        if (!container) return;
        const div = document.createElement("div");
        div.className = `toast toast--${type}`;
        div.textContent = msg;
        container.appendChild(div);
        setTimeout(() => div.classList.add("show"), 10);
        setTimeout(() => {
            div.classList.remove("show");
            setTimeout(() => div.remove(), 300);
        }, 4000);
    }

    // View Switching
    if (tabNavGenerator && tabNavStudio) {
        tabNavGenerator.addEventListener("click", () => {
            tabNavGenerator.classList.add("nav-tab-btn--active");
            tabNavStudio.classList.remove("nav-tab-btn--active");
            generatorView.style.display = "flex";
            studioView.style.display = "none";
        });

        tabNavStudio.addEventListener("click", () => {
            tabNavStudio.classList.add("nav-tab-btn--active");
            tabNavGenerator.classList.remove("nav-tab-btn--active");
            generatorView.style.display = "none";
            studioView.style.display = "flex";

            // If filtered clips exist from current session or storage, load them immediately
            const storedClips = window.latestFilteredClips || JSON.parse(sessionStorage.getItem("latest_filtered_clips") || "[]");
            const storedVid = window.latestSourceVideoName || sessionStorage.getItem("latest_source_video_name") || "";
            const storedUrl = window.latestSourceVideoUrl || sessionStorage.getItem("latest_source_video_url") || "";

            if (storedClips && storedClips.length > 0) {
                initStudioData(storedClips, storedVid, storedUrl);
            }
        });
    }

    if (kairoStudioBackBtn) {
        kairoStudioBackBtn.addEventListener("click", () => {
            tabNavGenerator.click();
        });
    }

    // 4-Slot Drop Setup
    function setupSlot(zone, input, nameEl, statusEl, key) {
        if (!zone || !input) return;
        zone.addEventListener("click", () => input.click());

        input.addEventListener("change", () => {
            if (input.files.length > 0) {
                files[key] = input.files[0];
                nameEl.textContent = files[key].name;
                statusEl.textContent = "Ready";
                statusEl.classList.add("slot-status--ready");
                zone.classList.add("drop-zone-slot--active");
                checkUploadReady();
            }
        });

        zone.addEventListener("dragover", (e) => {
            e.preventDefault();
            zone.classList.add("drop-zone-slot--active");
        });

        zone.addEventListener("dragleave", () => {
            if (!files[key]) zone.classList.remove("drop-zone-slot--active");
        });

        zone.addEventListener("drop", (e) => {
            e.preventDefault();
            if (e.dataTransfer.files.length > 0) {
                files[key] = e.dataTransfer.files[0];
                nameEl.textContent = files[key].name;
                statusEl.textContent = "Ready";
                statusEl.classList.add("slot-status--ready");
                zone.classList.add("drop-zone-slot--active");
                checkUploadReady();
            }
        });
    }

    setupSlot(slot1hZone, video1hInput, video1hFilename, slot1hStatus, "video_1h");
    setupSlot(slot2hZone, video2hInput, video2hFilename, slot2hStatus, "video_2h");
    setupSlot(slotEtZone, videoEtInput, videoEtFilename, slotEtStatus, "video_et1");
    setupSlot(slotFullZone, videoFullInput, videoFullFilename, slotFullStatus, "video");

    // CSV Drop Setup
    if (csvDropZone && csvInput) {
        csvDropZone.addEventListener("click", () => csvInput.click());
        csvInput.addEventListener("change", () => {
            if (csvInput.files.length > 0) {
                files.csv = csvInput.files[0];
                csvFileName.textContent = files.csv.name;
                csvDropZone.classList.add("drop-zone--has-file");
                checkUploadReady();
            }
        });

        csvDropZone.addEventListener("dragover", (e) => {
            e.preventDefault();
            csvDropZone.classList.add("drop-zone--dragover");
        });

        csvDropZone.addEventListener("dragleave", () => {
            csvDropZone.classList.remove("drop-zone--dragover");
        });

        csvDropZone.addEventListener("drop", (e) => {
            e.preventDefault();
            csvDropZone.classList.remove("drop-zone--dragover");
            if (e.dataTransfer.files.length > 0) {
                files.csv = e.dataTransfer.files[0];
                csvFileName.textContent = files.csv.name;
                csvDropZone.classList.add("drop-zone--has-file");
                checkUploadReady();
            }
        });
    }

    function checkUploadReady() {
        const hasVideo = files.video_1h || files.video_2h || files.video_et1 || files.video;
        const hasCsv = files.csv || uploadedNames.csv;
        if (uploadBtn) {
            uploadBtn.disabled = !(hasVideo || hasCsv);
        }
    }

    // Min Score Slider
    if (minScoreInput && minScoreValue) {
        minScoreInput.addEventListener("input", () => {
            minScoreValue.textContent = minScoreInput.value;
        });
    }

    // Accordions
    document.querySelectorAll(".kairo-category-item .kairo-cat-header").forEach(header => {
        header.addEventListener("click", () => {
            const item = header.closest(".kairo-category-item");
            if (item) item.classList.toggle("open");
        });
    });

    // Category Master Checkboxes
    document.querySelectorAll(".kairo-cat-master-cb").forEach(masterCb => {
        masterCb.addEventListener("change", (e) => {
            e.stopPropagation();
            const parent = masterCb.closest(".kairo-category-item");
            if (!parent) return;
            const subCbs = parent.querySelectorAll(".action-cb");
            subCbs.forEach(cb => cb.checked = masterCb.checked);
            updateKairoEventsSummary();
        });
    });

    // Individual Action Checkboxes
    document.querySelectorAll(".kairo-category-item .action-cb").forEach(cb => {
        cb.addEventListener("change", () => {
            const parent = cb.closest(".kairo-category-item");
            if (parent) {
                const subCbs = parent.querySelectorAll(".action-cb");
                const masterCb = parent.querySelector(".kairo-cat-master-cb");
                const allChecked = Array.from(subCbs).every(c => c.checked);
                const someChecked = Array.from(subCbs).some(c => c.checked);
                if (masterCb) {
                    masterCb.checked = allChecked;
                    masterCb.indeterminate = !allChecked && someChecked;
                }
            }
            updateKairoEventsSummary();
        });
    });

    // Select All Events Checkbox
    if (kairoSelectAllEvents) {
        kairoSelectAllEvents.addEventListener("change", () => {
            const checked = kairoSelectAllEvents.checked;
            document.querySelectorAll(".kairo-category-item .action-cb").forEach(cb => cb.checked = checked);
            document.querySelectorAll(".kairo-cat-master-cb").forEach(cb => {
                cb.checked = checked;
                cb.indeterminate = false;
            });
            updateKairoEventsSummary();
        });
    }

    function updateKairoEventsSummary() {
        const allActionCbs = document.querySelectorAll(".kairo-category-item .action-cb");
        const checkedActionCbs = Array.from(allActionCbs).filter(cb => cb.checked);
        const total = allActionCbs.length;
        const count = checkedActionCbs.length;

        if (kairoEventsStatusText) {
            if (count === 0) {
                kairoEventsStatusText.textContent = "No events selected";
            } else if (count === total) {
                kairoEventsStatusText.textContent = "All events selected";
            } else {
                kairoEventsStatusText.textContent = `${count} event${count > 1 ? 's' : ''} selected`;
            }
        }

        if (kairoSelectAllEvents) {
            kairoSelectAllEvents.checked = (count === total && total > 0);
            kairoSelectAllEvents.indeterminate = (count > 0 && count < total);
        }
    }

    // Team Radio & Dynamic Player Selection
    document.querySelectorAll('input[name="kairo_team_choice"]').forEach(radio => {
        radio.addEventListener("change", () => {
            renderKairoPlayerOptions();
            syncSelectedTeamAndPlayer();
        });
    });

    if (kairoPlayerSelect) {
        kairoPlayerSelect.addEventListener("change", () => {
            syncSelectedTeamAndPlayer();
        });
    }

    function renderKairoPlayerOptions() {
        if (!kairoPlayerSelect) return;
        const selectedRadio = document.querySelector('input[name="kairo_team_choice"]:checked');
        const radioVal = selectedRadio ? selectedRadio.value : "both";

        let playersToShow = currentMatchPlayers || [];

        if (radioVal === "team_a" && currentMatchTeams.length > 0) {
            const teamA = currentMatchTeams[0];
            const matchingKey = Object.keys(currentTeamPlayersMap).find(k => k.trim().toLowerCase() === teamA.trim().toLowerCase());
            if (matchingKey && currentTeamPlayersMap[matchingKey]) {
                playersToShow = currentTeamPlayersMap[matchingKey];
            }
        } else if (radioVal === "team_b" && currentMatchTeams.length > 1) {
            const teamB = currentMatchTeams[1];
            const matchingKey = Object.keys(currentTeamPlayersMap).find(k => k.trim().toLowerCase() === teamB.trim().toLowerCase());
            if (matchingKey && currentTeamPlayersMap[matchingKey]) {
                playersToShow = currentTeamPlayersMap[matchingKey];
            }
        }

        const prev = kairoPlayerSelect.value;
        kairoPlayerSelect.innerHTML = '<option value="">All players on team</option>';

        playersToShow.forEach(p => {
            const opt = document.createElement("option");
            opt.value = p;
            opt.textContent = p;
            kairoPlayerSelect.appendChild(opt);
        });

        if (prev && Array.from(kairoPlayerSelect.options).some(o => o.value === prev)) {
            kairoPlayerSelect.value = prev;
        }
    }

    function syncSelectedTeamAndPlayer() {
        const selectedRadio = document.querySelector('input[name="kairo_team_choice"]:checked');
        const radioVal = selectedRadio ? selectedRadio.value : "both";
        let targetTeam = "";

        if (radioVal === "team_a" && currentMatchTeams.length > 0) {
            targetTeam = currentMatchTeams[0];
        } else if (radioVal === "team_b" && currentMatchTeams.length > 1) {
            targetTeam = currentMatchTeams[1];
        }

        const targetPlayer = kairoPlayerSelect ? kairoPlayerSelect.value.trim() : "";
        if (teamNameInput) teamNameInput.value = targetTeam;
        if (playerNameInput) playerNameInput.value = targetPlayer;
    }

    // WhoScored Live Match Scraper
    if (whoscoredScrapeBtn) {
        whoscoredScrapeBtn.addEventListener("click", async () => {
            const urlVal = whoscoredUrlInput ? whoscoredUrlInput.value.trim() : "";
            if (!urlVal) {
                toast("Please enter a WhoScored URL or Match ID.", "error");
                return;
            }

            whoscoredScrapeBtn.disabled = true;
            whoscoredScrapeBtn.textContent = "Scraping...";
            toast("Scraping live match data from WhoScored...", "info");

            const form = new FormData();
            form.append("url_or_id", urlVal);

            try {
                const res = await fetch(apiUrl("/api/scrape_whoscored"), { method: "POST", body: form });
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || "Scraping failed");

                uploadedNames.csv = data.csv_filename;
                csvFileName.textContent = `⚡ ${data.csv_filename} (${data.total_events} events)`;
                csvDropZone.classList.add("drop-zone--has-file");

                if (data.teams && data.teams.length > 0) {
                    currentMatchTeams = data.teams;
                    currentMatchPlayers = data.players || [];
                    currentTeamPlayersMap = data.team_players || {};

                    if (kairoMatchTitle) {
                        kairoMatchTitle.textContent = currentMatchTeams.length >= 2 
                            ? `${currentMatchTeams[0]} vs ${currentMatchTeams[1]}` 
                            : `${currentMatchTeams[0]} Match`;
                    }
                    if (kairoTeamAName && currentMatchTeams.length >= 1) {
                        kairoTeamAName.textContent = currentMatchTeams[0];
                    }
                    if (kairoTeamBName && currentMatchTeams.length >= 2) {
                        kairoTeamBName.textContent = currentMatchTeams[1];
                    }

                    renderKairoPlayerOptions();
                    syncSelectedTeamAndPlayer();
                }

                toast(`✓ WhoScored Scrape Complete! Found ${data.total_events} events (${data.teams.join(' vs ')}).`, "success");
                checkUploadReady();
            } catch (err) {
                console.error("WhoScored Scrape Error:", err);
                toast(err.message, "error");
            } finally {
                whoscoredScrapeBtn.disabled = false;
                whoscoredScrapeBtn.textContent = "⚡ Scrape Events";
            }
        });
    }

    // Scoresway Scrape Button
    if (scoreswayScrapeBn) {
        scoreswayScrapeBn.addEventListener("click", async () => {
            const urlVal = scoreswayUrlInput ? scoreswayUrlInput.value.trim() : "";
            if (!urlVal) {
                toast("Please enter a Scoresway URL or Match ID.", "error");
                return;
            }

            scoreswayScrapeBn.disabled = true;
            scoreswayScrapeBn.textContent = "Scraping...";
            toast("Scraping live match data from Scoresway...", "info");

            const form = new FormData();
            form.append("url_or_id", urlVal);

            try {
                const res = await fetch(apiUrl("/api/scrape_scoresway"), { method: "POST", body: form });
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || "Scraping failed");

                uploadedNames.csv = data.csv_filename;
                csvFileName.textContent = `⚡ ${data.csv_filename} (${data.total_events} events)`;
                csvDropZone.classList.add("drop-zone--has-file");

                if (data.teams && data.teams.length > 0) {
                    currentMatchTeams = data.teams;
                    currentMatchPlayers = data.players || [];
                    currentTeamPlayersMap = data.team_players || {};

                    if (kairoMatchTitle) {
                        kairoMatchTitle.textContent = currentMatchTeams.length >= 2
                            ? `${currentMatchTeams[0]} vs ${currentMatchTeams[1]}`
                            : `${currentMatchTeams[0]} Match`;
                    }
                    if (kairoTeamAName && currentMatchTeams.length >= 1) {
                        kairoTeamAName.textContent = currentMatchTeams[0];
                    }
                    if (kairoTeamBName && currentMatchTeams.length >= 2) {
                        kairoTeamBName.textContent = currentMatchTeams[1];
                    }

                    renderKairoPlayerOptions();
                    syncSelectedTeamAndPlayer();
                }

                toast(`✓ Scoresway Scrape Complete! Found ${data.total_events} events (${data.teams.join(' vs ')}).`, "success");
                checkUploadReady();
            } catch (err) {
                console.error("Scoresway Scrape Error:", err);
                toast(err.message, "error");
            } finally {
                scoreswayScrapeBn.disabled = false;
                scoreswayScrapeBn.textContent = "⚡ Scrape Events";
            }
        });
    }

    // Upload & Sync Button
    if (uploadBtn) {
        uploadBtn.addEventListener("click", async () => {
            const form = new FormData();
            if (files.video_1h) form.append("video_1h", files.video_1h);
            if (files.video_2h) form.append("video_2h", files.video_2h);
            if (files.video_et1) form.append("video_et1", files.video_et1);
            if (files.video) form.append("video", files.video);
            if (files.csv) form.append("csv", files.csv);

            uploadBtn.disabled = true;
            uploadBtn.textContent = "Uploading...";

            try {
                const res = await fetch(apiUrl("/api/upload"), { method: "POST", body: form });
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || "Upload failed");

                if (data.video_1h) uploadedNames.video_1h = data.video_1h;
                if (data.video_2h) uploadedNames.video_2h = data.video_2h;
                if (data.video_et1) uploadedNames.video_et1 = data.video_et1;
                if (data.video) uploadedNames.video = data.video;
                if (data.csv) uploadedNames.csv = data.csv;

                toast("✓ Match videos & data synchronized!", "success");
                uploadBtn.textContent = "✓ Uploaded & Synced";
            } catch (err) {
                toast(err.message, "error");
                uploadBtn.disabled = false;
                uploadBtn.textContent = "Upload & Sync Match Files";
            }
        });
    }

    // Load Music Files
    async function loadMusic() {
        if (!musicSelect) return;
        try {
            const res = await fetch(apiUrl("/api/music"));
            const data = await res.json();
            if (data.songs && data.songs.length > 0) {
                musicSelect.innerHTML = '<option value="">No Music</option>';
                data.songs.forEach(song => {
                    const opt = document.createElement("option");
                    opt.value = song;
                    opt.textContent = song;
                    musicSelect.appendChild(opt);
                });
            }
        } catch (err) {
            console.error("Could not load music list:", err);
        }
    }
    loadMusic();

    // Browse Output Directory
    if (browseDirBtn) {
        browseDirBtn.addEventListener("click", async () => {
            try {
                const res = await fetch(apiUrl("/api/browse_folder"));
                const data = await res.json();
                if (data.folder) {
                    outputFolderInput.value = data.folder;
                    toast(`Selected folder: ${data.folder}`, "info");
                }
            } catch (err) {
                console.error("Browse Folder Error:", err);
            }
        });
    }

    // Generate Highlights Pipeline
    if (generateBtn) {
        generateBtn.addEventListener("click", async () => {
            const selectedActions = [];
            document.querySelectorAll(".kairo-category-item .action-cb:checked").forEach(cb => {
                selectedActions.push(cb.value);
            });

            syncSelectedTeamAndPlayer();

            const selectedPlayer = kairoPlayerSelect ? kairoPlayerSelect.value.trim() : (playerNameInput ? playerNameInput.value.trim() : "");
            const selectedRadio = document.querySelector('input[name="kairo_team_choice"]:checked');
            const radioVal = selectedRadio ? selectedRadio.value : "both";
            let selectedTeam = "";
            if (radioVal === "team_a" && currentMatchTeams.length > 0) selectedTeam = currentMatchTeams[0];
            else if (radioVal === "team_b" && currentMatchTeams.length > 1) selectedTeam = currentMatchTeams[1];

            const form = new FormData();
            form.append("video_filename", uploadedNames.video || "");
            form.append("video_1h_filename", uploadedNames.video_1h || "");
            form.append("video_2h_filename", uploadedNames.video_2h || "");
            form.append("video_et1_filename", uploadedNames.video_et1 || "");
            form.append("csv_filename", uploadedNames.csv || "");
            form.append("player_name", selectedPlayer);
            form.append("team_name", selectedTeam);
            form.append("action_types", selectedActions.length > 0 ? selectedActions.join(",") : "all");

            function parseTime(t) {
                if (!t) return 0;
                const parts = t.trim().split(":");
                if (parts.length === 3) return (+parts[0])*3600 + (+parts[1])*60 + (+parts[2]);
                if (parts.length === 2) return (+parts[0])*60 + (+parts[1]);
                return parseFloat(t) || 0;
            }

            form.append("fh_kickoff", parseTime(fhKickoffInput ? fhKickoffInput.value : "03:33"));
            form.append("sh_kickoff", parseTime(shKickoffInput ? shKickoffInput.value : "1:00:20"));
            form.append("halves_include", halvesInclude ? halvesInclude.value : "both");
            form.append("pre_buffer", parseFloat(preBufferInput.value) || 3);
            form.append("post_buffer", parseFloat(postBufferInput.value) || 8);
            form.append("merge_gap", parseFloat(mergeGapInput.value) || 6);
            form.append("top_x", parseInt(topXInput.value) || 0);
            form.append("min_score", parseInt(minScoreInput.value) || 1);
            form.append("min_xt", parseFloat(minXtInput.value) || 0.0);
            form.append("music_file", musicSelect ? musicSelect.value : "");
            form.append("mute_original", muteOriginalInput ? muteOriginalInput.checked : false);
            form.append("output_folder", outputFolderInput ? outputFolderInput.value : "");
            form.append("output_filename", outputFilenameInput ? outputFilenameInput.value : "Highlights.mp4");
            form.append("save_individual", saveIndividualInput ? saveIndividualInput.checked : false);

            generateBtn.disabled = true;
            generateBtn.innerHTML = '<span class="spinner"></span> Generating...';

            if (statusContainer) {
                statusContainer.style.display = "block";
                statusText.textContent = "Processing match clips with FFmpeg...";
                progressFill.style.width = "40%";
            }

            try {
                const res = await fetch(apiUrl("/api/generate"), {
                    method: "POST",
                    body: form
                });
                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || "Generation failed");

                // Background pipeline started — start polling /api/status
                let pollInterval = setInterval(async () => {
                    try {
                        const statusRes = await fetch(apiUrl("/api/status"));
                        const statusData = await statusRes.json();

                        if (statusData.state === "processing") {
                            if (statusText) statusText.textContent = statusData.message || "Extracting clips...";
                            if (progressFill && statusData.total > 0) {
                                const percent = Math.min(95, Math.round((statusData.progress / statusData.total) * 100));
                                progressFill.style.width = `${percent}%`;
                            }
                        } else if (statusData.state === "done") {
                            clearInterval(pollInterval);
                            generateBtn.disabled = false;
                            generateBtn.innerHTML = `
                                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polygon points="5 3 19 12 5 21 5 3"/></svg>
                                GENERATE HIGHLIGHTS
                            `;
                            if (progressFill) progressFill.style.width = "100%";
                            if (statusText) statusText.textContent = `✓ Done! Created ${statusData.progress || 0} clips.`;

                            const videoUrl = apiUrl(`/api/download/${statusData.output_file}`);

                            // Show preview video
                            if (resultSection && statusData.output_file) {
                                resultSection.style.display = "block";
                                resultVideo.src = videoUrl;
                                resultVideo.load();
                                savedPathLabel.textContent = statusData.actual_path || statusData.output_file;
                                downloadLink.href = videoUrl;
                                downloadLink.download = statusData.output_file;
                                resultSection.scrollIntoView({ behavior: "smooth" });
                            }

                            // Store this exact filtered_clips array in memory and sessionStorage
                            if (statusData.clips_preview && statusData.clips_preview.length > 0) {
                                window.latestFilteredClips = statusData.clips_preview;
                                window.latestSourceVideoName = statusData.video_filename;
                                window.latestSourceVideoUrl = statusData.source_video_url;

                                try {
                                    sessionStorage.setItem("latest_filtered_clips", JSON.stringify(statusData.clips_preview));
                                    sessionStorage.setItem("latest_source_video_name", statusData.video_filename || "");
                                    sessionStorage.setItem("latest_source_video_url", statusData.source_video_url || "");
                                } catch (e) {}

                                initStudioData(statusData.clips_preview, statusData.video_filename, statusData.source_video_url);
                            }

                            toast("🎉 Highlights generated successfully!", "success");
                        } else if (statusData.state === "error") {
                            clearInterval(pollInterval);
                            generateBtn.disabled = false;
                            generateBtn.innerHTML = `
                                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polygon points="5 3 19 12 5 21 5 3"/></svg>
                                GENERATE HIGHLIGHTS
                            `;
                            if (statusText) statusText.textContent = `❌ ${statusData.message || "Generation error"}`;
                            toast(statusData.message || "Generation error", "error");
                        }
                    } catch (pollErr) {
                        console.error("Polling error:", pollErr);
                    }
                }, 1000);

            } catch (err) {
                console.error("Generate Error:", err);
                toast(err.message, "error");
                if (statusText) statusText.textContent = `❌ Error: ${err.message}`;
                generateBtn.disabled = false;
                generateBtn.innerHTML = `
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polygon points="5 3 19 12 5 21 5 3"/></svg>
                    GENERATE HIGHLIGHTS
                `;
            }
        });
    }

    // =========================================================================
    // KAIRO CLIP STUDIO CONTROLLER (ORIGINAL FULL-MATCH VIDEO & REALTIME TRIMMING)
    // =========================================================================
    const ksPrevClipBtn = document.getElementById("ks-prev-clip-btn");
    const ksNextClipBtn = document.getElementById("ks-next-clip-btn");
    const ksClipBadge = document.getElementById("ks-clip-badge");
    const ksClipTimecode = document.getElementById("ks-clip-timecode");
    const ksActionTagsContainer = document.getElementById("ks-action-tags-container");
    const ksOverviewTrack = document.getElementById("ks-overview-track");
    const ksOverviewPlayhead = document.getElementById("ks-overview-playhead");
    const ksTrimmerTrack = document.getElementById("ks-trimmer-track");
    const ksTrimSelection = document.getElementById("ks-trim-selection");
    const ksHandleLeft = document.getElementById("ks-handle-left");
    const ksHandleRight = document.getElementById("ks-handle-right");
    const ksMatchSubtitle = document.getElementById("ks-match-subtitle");
    const ksTimelineSummary = document.getElementById("ks-timeline-summary");

    const ksResetAllBtn = document.getElementById("ks-reset-all-btn");
    const ksSaveChangesBtn = document.getElementById("ks-save-changes-btn");
    const ksExportZipBtn = document.getElementById("ks-export-zip-btn");
    const ksExportReelBtn = document.getElementById("ks-export-reel-btn");
    const ksResetClipBtn = document.getElementById("ks-reset-clip-btn");
    const ksDeleteClipBtn = document.getElementById("ks-delete-clip-btn");
    const ksDownloadClipBtn = document.getElementById("ks-download-clip-btn");

    let originalStudioClips = [];
    let currentSourceVideoName = "";
    let currentSourceVideoUrl = "";
    let matchTotalDuration = 99 * 60 + 4; // default ~99m 4s

    function formatTimecode(sec) {
        const m = Math.floor(sec / 60);
        const s = Math.floor(sec % 60);
        return `${m}:${s < 10 ? '0' : ''}${s}`;
    }

    function initStudioData(clips, videoFilename, videoSrcUrl) {
        if (!clips || clips.length === 0) return;
        
        currentSourceVideoName = videoFilename || uploadedNames.video || uploadedNames.video_1h || "";
        currentSourceVideoUrl = videoSrcUrl ? apiUrl(videoSrcUrl) : (currentSourceVideoName ? apiUrl(`/api/videos/${currentSourceVideoName}`) : "");
        studioClips = JSON.parse(JSON.stringify(clips));
        originalStudioClips = JSON.parse(JSON.stringify(clips));
        activeClipIndex = 0;

        // Set match subtitle
        if (ksMatchSubtitle && currentMatchTeams.length >= 2) {
            ksMatchSubtitle.textContent = `${currentMatchTeams[0]} vs ${currentMatchTeams[1]}`;
        }

        // Determine the initial video source from the first clip's metadata if available
        const firstClip = studioClips[0];
        const initialVideoUrl = (firstClip && firstClip.source_video_url) ? 
            apiUrl(firstClip.source_video_url) : 
            (currentSourceVideoUrl || (currentSourceVideoName ? apiUrl(`/api/videos/${currentSourceVideoName}`) : ""));

        // Load correct source video into Clip Studio player
        if (kairoStudioVideo && initialVideoUrl) {
            if (!kairoStudioVideo.src.endsWith(initialVideoUrl)) {
                kairoStudioVideo.src = initialVideoUrl;
                kairoStudioVideo.load();
            }
        }

        renderStudioClipsList();
        selectStudioClip(0);
    }

    // Video duration detection
    if (kairoStudioVideo) {
        kairoStudioVideo.addEventListener("loadedmetadata", () => {
            if (kairoStudioVideo.duration && !isNaN(kairoStudioVideo.duration) && kairoStudioVideo.duration > 10) {
                matchTotalDuration = kairoStudioVideo.duration;
            }
            renderStudioClipsList();
        });

        // Loop / pause synchronization: keep playback inside active clip bounds
        kairoStudioVideo.addEventListener("timeupdate", () => {
            const curTime = kairoStudioVideo.currentTime;
            
            // Update playhead on overview track
            if (ksOverviewPlayhead) {
                const pct = Math.max(0, Math.min(100, (curTime / matchTotalDuration) * 100));
                ksOverviewPlayhead.style.left = `${pct}%`;
            }

            // Enforce active clip boundary
            if (studioClips && studioClips[activeClipIndex]) {
                const clip = studioClips[activeClipIndex];
                if (curTime >= clip.end_sec) {
                    kairoStudioVideo.currentTime = clip.start_sec;
                    kairoStudioVideo.pause();
                }
            }
        });
    }

    function renderStudioClipsList() {
        if (!studioClips || studioClips.length === 0) return;

        if (ksTimelineSummary) {
            ksTimelineSummary.textContent = `${studioClips.length} clips · match ${formatTimecode(matchTotalDuration)}`;
        }

        // Render overview track markers
        if (ksOverviewTrack) {
            ksOverviewTrack.querySelectorAll(".ks-overview-block").forEach(b => b.remove());

            studioClips.forEach((c, idx) => {
                const block = document.createElement("div");
                block.className = `ks-overview-block ${idx === activeClipIndex ? 'ks-overview-block--active' : ''}`;
                const startPct = Math.max(0, Math.min(100, (c.start_sec / matchTotalDuration) * 100));
                const durPct = Math.max(0.4, ((c.end_sec - c.start_sec) / matchTotalDuration) * 100);
                block.style.left = `${startPct}%`;
                block.style.width = `${durPct}%`;
                block.title = `Clip ${idx + 1}: ${c.event || 'Action'} (${formatTimecode(c.start_sec)} - ${formatTimecode(c.end_sec)})`;
                block.addEventListener("click", (e) => {
                    e.stopPropagation();
                    selectStudioClip(idx);
                });
                ksOverviewTrack.appendChild(block);
            });
        }

        updateActiveClipUI();
        updateTrimmerTrackUI();
    }

    function selectStudioClip(index) {
        if (index < 0 || index >= studioClips.length) return;
        activeClipIndex = index;

        if (ksOverviewTrack) {
            const blocks = ksOverviewTrack.querySelectorAll(".ks-overview-block");
            blocks.forEach((b, i) => {
                if (i === activeClipIndex) b.classList.add("ks-overview-block--active");
                else b.classList.remove("ks-overview-block--active");
            });
        }

        updateActiveClipUI();
        updateTrimmerTrackUI();

        // Seek video player to clip start timestamp with dynamic source video swapping
        const clip = studioClips[activeClipIndex];
        if (kairoStudioVideo && clip) {
            const clipVideoUrl = clip.source_video_url ? apiUrl(clip.source_video_url) : 
                (clip.source_video ? apiUrl(`/api/videos/${clip.source_video}`) : currentSourceVideoUrl);

            if (clipVideoUrl && !kairoStudioVideo.src.endsWith(clipVideoUrl)) {
                kairoStudioVideo.src = clipVideoUrl;
                kairoStudioVideo.load();
                kairoStudioVideo.addEventListener("loadedmetadata", function onMeta() {
                    kairoStudioVideo.removeEventListener("loadedmetadata", onMeta);
                    kairoStudioVideo.currentTime = clip.start_sec || 0;
                    kairoStudioVideo.play().catch(() => {});
                });
            } else {
                kairoStudioVideo.currentTime = clip.start_sec || 0;
                kairoStudioVideo.play().catch(() => {});
            }
        }
    }

    function updateActiveClipUI() {
        if (!studioClips || studioClips.length === 0) return;
        const clip = studioClips[activeClipIndex];
        if (!clip) return;

        const clipNum = String(activeClipIndex + 1).padStart(2, '0');
        const startStr = formatTimecode(clip.start_sec || 0);
        const endStr = formatTimecode(clip.end_sec || 0);

        if (ksClipBadge) {
            ksClipBadge.innerHTML = `Clip ${clipNum} <span class="ks-clip-time">${startStr} – ${endStr}</span>`;
        }

        // Render Action Tags
        if (ksActionTagsContainer) {
            ksActionTagsContainer.innerHTML = "";
            const tags = clip.tags && clip.tags.length > 0 ? clip.tags : [clip.event || "Action"];
            tags.forEach(t => {
                const tagEl = document.createElement("span");
                tagEl.className = "ks-tag";
                tagEl.textContent = t;
                ksActionTagsContainer.appendChild(tagEl);
            });
        }
    }

    function updateTrimmerTrackUI() {
        if (!studioClips || studioClips.length === 0 || !ksTrimSelection) return;
        const clip = studioClips[activeClipIndex];
        if (!clip) return;

        // Task 2: Zoomed Precision Trimming Window (e.g. +/- 20s context around the clip)
        const clipDur = Math.max(1.0, clip.end_sec - clip.start_sec);
        const padding = Math.max(15, clipDur * 1.2);
        const zoomStart = Math.max(0, clip.start_sec - padding);
        const zoomEnd = Math.min(matchTotalDuration, clip.end_sec + padding);
        const zoomWindowDur = Math.max(5.0, zoomEnd - zoomStart);

        // Map clip boundaries into the zoomed window
        const startPct = Math.max(0, Math.min(100, ((clip.start_sec - zoomStart) / zoomWindowDur) * 100));
        const endPct = Math.max(startPct + 1.0, Math.min(100, ((clip.end_sec - zoomStart) / zoomWindowDur) * 100));
        const durPct = endPct - startPct;

        ksTrimSelection.style.left = `${startPct}%`;
        ksTrimSelection.style.width = `${durPct}%`;
    }

    // Task 2: Precision Zoom-Aware Draggable Edge Trimming
    let isDraggingHandle = null; // 'left' or 'right'

    function handleTrimmingDrag(e) {
        if (!isDraggingHandle || !ksTrimmerTrack || !studioClips || !studioClips[activeClipIndex]) return;
        const rect = ksTrimmerTrack.getBoundingClientRect();
        const clientX = e.touches ? e.touches[0].clientX : e.clientX;
        
        const clip = studioClips[activeClipIndex];
        const clipDur = Math.max(1.0, clip.end_sec - clip.start_sec);
        const padding = Math.max(15, clipDur * 1.2);
        const zoomStart = Math.max(0, clip.start_sec - padding);
        const zoomEnd = Math.min(matchTotalDuration, clip.end_sec + padding);
        const zoomWindowDur = Math.max(5.0, zoomEnd - zoomStart);

        // Exact timestamp in zoomed timeline window
        const clickRatio = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
        const targetSec = zoomStart + (clickRatio * zoomWindowDur);

        if (isDraggingHandle === "left") {
            // Drag Left handle backward or forward with 0.1s precision
            const minAllowed = 0;
            const maxAllowed = clip.end_sec - 0.5;
            const clampedSec = Math.round(Math.max(minAllowed, Math.min(maxAllowed, targetSec)) * 10) / 10;
            
            clip.start_sec = clampedSec;
            if (kairoStudioVideo) {
                kairoStudioVideo.currentTime = clampedSec;
            }
        } else if (isDraggingHandle === "right") {
            // Drag Right handle backward or forward with 0.1s precision
            const minAllowed = clip.start_sec + 0.5;
            const maxAllowed = matchTotalDuration;
            const clampedSec = Math.round(Math.max(minAllowed, Math.min(maxAllowed, targetSec)) * 10) / 10;
            
            clip.end_sec = clampedSec;
            if (kairoStudioVideo) {
                kairoStudioVideo.currentTime = clampedSec;
            }
        }

        updateActiveClipUI();
        updateTrimmerTrackUI();
    }

    function stopTrimmingDrag() {
        if (isDraggingHandle) {
            isDraggingHandle = null;
            document.removeEventListener("mousemove", handleTrimmingDrag);
            document.removeEventListener("mouseup", stopTrimmingDrag);
            document.removeEventListener("touchmove", handleTrimmingDrag);
            document.removeEventListener("touchend", stopTrimmingDrag);
            renderStudioClipsList();
        }
    }

    if (ksHandleLeft) {
        ksHandleLeft.addEventListener("mousedown", (e) => {
            e.preventDefault();
            e.stopPropagation();
            isDraggingHandle = "left";
            document.addEventListener("mousemove", handleTrimmingDrag);
            document.addEventListener("mouseup", stopTrimmingDrag);
        });
        ksHandleLeft.addEventListener("touchstart", (e) => {
            e.stopPropagation();
            isDraggingHandle = "left";
            document.addEventListener("touchmove", handleTrimmingDrag);
            document.addEventListener("touchend", stopTrimmingDrag);
        });
    }

    if (ksHandleRight) {
        ksHandleRight.addEventListener("mousedown", (e) => {
            e.preventDefault();
            e.stopPropagation();
            isDraggingHandle = "right";
            document.addEventListener("mousemove", handleTrimmingDrag);
            document.addEventListener("mouseup", stopTrimmingDrag);
        });
        ksHandleRight.addEventListener("touchstart", (e) => {
            e.stopPropagation();
            isDraggingHandle = "right";
            document.addEventListener("touchmove", handleTrimmingDrag);
            document.addEventListener("touchend", stopTrimmingDrag);
        });
    }

    // Quick Seek Controls (-8s, -1s, +1s, +8s)
    const ksSeekBack8 = document.getElementById("ks-seek-back-8");
    const ksSeekBack1 = document.getElementById("ks-seek-back-1");
    const ksSeekFwd1 = document.getElementById("ks-seek-fwd-1");
    const ksSeekFwd8 = document.getElementById("ks-seek-fwd-8");

    function seekStudioVideo(offsetSec) {
        if (!kairoStudioVideo) return;
        const maxTime = kairoStudioVideo.duration || matchTotalDuration;
        const targetTime = Math.max(0, Math.min(maxTime, kairoStudioVideo.currentTime + offsetSec));
        kairoStudioVideo.currentTime = targetTime;
        
        if (ksOverviewPlayhead) {
            const pct = Math.max(0, Math.min(100, (targetTime / matchTotalDuration) * 100));
            ksOverviewPlayhead.style.left = `${pct}%`;
        }

        // If seeking beyond current clip bounds, dynamically adjust the active clip boundary
        if (studioClips && studioClips[activeClipIndex]) {
            const clip = studioClips[activeClipIndex];
            if (targetTime < clip.start_sec) {
                clip.start_sec = Math.round(targetTime * 10) / 10;
            } else if (targetTime > clip.end_sec) {
                clip.end_sec = Math.round(targetTime * 10) / 10;
            }
            updateActiveClipUI();
            updateTrimmerTrackUI();
            renderStudioClipsList();
        }
    }

    if (ksSeekBack8) ksSeekBack8.addEventListener("click", () => seekStudioVideo(-8));
    if (ksSeekBack1) ksSeekBack1.addEventListener("click", () => seekStudioVideo(-1));
    if (ksSeekFwd1) ksSeekFwd1.addEventListener("click", () => seekStudioVideo(1));
    if (ksSeekFwd8) ksSeekFwd8.addEventListener("click", () => seekStudioVideo(8));

    // Clip Navigation Buttons
    if (ksPrevClipBtn) {
        ksPrevClipBtn.addEventListener("click", () => {
            if (activeClipIndex > 0) selectStudioClip(activeClipIndex - 1);
        });
    }

    if (ksNextClipBtn) {
        ksNextClipBtn.addEventListener("click", () => {
            if (activeClipIndex < studioClips.length - 1) selectStudioClip(activeClipIndex + 1);
        });
    }

    // Clip Modification Actions
    if (ksResetClipBtn) {
        ksResetClipBtn.addEventListener("click", () => {
            if (originalStudioClips[activeClipIndex] && studioClips[activeClipIndex]) {
                studioClips[activeClipIndex].start_sec = originalStudioClips[activeClipIndex].start_sec;
                studioClips[activeClipIndex].end_sec = originalStudioClips[activeClipIndex].end_sec;
                selectStudioClip(activeClipIndex);
                toast(`Reset Clip ${activeClipIndex + 1} to original bounds.`, "info");
            }
        });
    }

    if (ksDeleteClipBtn) {
        ksDeleteClipBtn.addEventListener("click", () => {
            if (studioClips.length <= 1) {
                toast("Cannot delete the only clip in timeline.", "error");
                return;
            }
            studioClips.splice(activeClipIndex, 1);
            if (originalStudioClips[activeClipIndex]) originalStudioClips.splice(activeClipIndex, 1);
            if (activeClipIndex >= studioClips.length) activeClipIndex = studioClips.length - 1;
            renderStudioClipsList();
            selectStudioClip(activeClipIndex);
            toast("Clip deleted from timeline.", "info");
        });
    }

    if (ksResetAllBtn) {
        ksResetAllBtn.addEventListener("click", () => {
            studioClips = JSON.parse(JSON.stringify(originalStudioClips));
            renderStudioClipsList();
            selectStudioClip(0);
            toast("Reset all timeline clips to original intervals.", "info");
        });
    }

    // Task 1: Fix State Reversion and Player Reset on 'Save changes'
    if (ksSaveChangesBtn) {
        ksSaveChangesBtn.addEventListener("click", () => {
            if (!studioClips || studioClips.length === 0) {
                toast("No clips in timeline to save.", "error");
                return;
            }

            // Persist the mutated state into memory and sessionStorage
            window.latestFilteredClips = JSON.parse(JSON.stringify(studioClips));
            originalStudioClips = JSON.parse(JSON.stringify(studioClips));

            try {
                sessionStorage.setItem("latest_filtered_clips", JSON.stringify(studioClips));
            } catch (e) {}

            // Keep video player state untouched (do not reset currentTime or src)
            toast(`✓ Saved changes for ${studioClips.length} clips!`, "success");
        });
    }

    // Task 3: Route the Mutated State to the Export Function
    async function triggerCustomExport(saveIndividual = false) {
        // Strictly pull the active, mutated clips array from state or sessionStorage
        const activeClips = (studioClips && studioClips.length > 0) ? 
            studioClips : 
            (window.latestFilteredClips || JSON.parse(sessionStorage.getItem("latest_filtered_clips") || "[]"));

        if (!activeClips || activeClips.length === 0) {
            toast("No clips in timeline to export.", "error");
            return;
        }

        const videoFile = currentSourceVideoName || uploadedNames.video || uploadedNames.video_1h || "";
        if (!videoFile) {
            toast("Source match video not found.", "error");
            return;
        }

        const payload = {
            video_filename: videoFile,
            player_name: playerNameInput ? playerNameInput.value.trim() : "Custom_Edit",
            save_individual: saveIndividual,
            output_folder: outputFolderInput ? outputFolderInput.value : "",
            music_file: musicSelect ? musicSelect.value : "",
            mute_original: muteOriginalInput ? muteOriginalInput.checked : false,
            clips: activeClips.map(c => ({
                clip_start: c.start_sec,
                clip_end: c.end_sec,
                source_video: c.source_video || ""
            }))
        };

        toast(saveIndividual ? "Exporting individual clips ZIP..." : "Compiling timeline reel with FFmpeg...", "info");

        try {
            const res = await fetch(apiUrl("/api/render_custom"), {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || "Export failed");

            // Return to generator to monitor render progress
            tabNavGenerator.click();
            if (statusContainer) {
                statusContainer.style.display = "block";
                statusText.textContent = "Compiling customized clips with FFmpeg...";
                progressFill.style.width = "50%";
            }

            // Poll /api/status until completion
            let poll = setInterval(async () => {
                try {
                    const sRes = await fetch(apiUrl("/api/status"));
                    const sData = await sRes.json();
                    if (sData.state === "processing") {
                        if (statusText) statusText.textContent = sData.message || "Rendering...";
                        if (progressFill && sData.total > 0) {
                            progressFill.style.width = `${Math.round((sData.progress / sData.total) * 100)}%`;
                        }
                    } else if (sData.state === "done") {
                        clearInterval(poll);
                        if (progressFill) progressFill.style.width = "100%";
                        if (statusText) statusText.textContent = "✓ Export complete!";
                        if (resultSection && sData.output_file) {
                            resultSection.style.display = "block";
                            resultVideo.src = apiUrl(`/api/download/${sData.output_file}`);
                            resultVideo.load();
                            savedPathLabel.textContent = sData.actual_path || sData.output_file;
                            downloadLink.href = apiUrl(`/api/download/${sData.output_file}`);
                            downloadLink.download = sData.output_file;
                            resultSection.scrollIntoView({ behavior: "smooth" });
                        }
                        toast("🎉 Highlights rendered and saved successfully!", "success");
                    } else if (sData.state === "error") {
                        clearInterval(poll);
                        if (statusText) statusText.textContent = `❌ ${sData.message}`;
                        toast(sData.message, "error");
                    }
                } catch (e) {
                    console.error("Custom export poll error:", e);
                }
            }, 1000);

        } catch (err) {
            console.error("Export error:", err);
            toast(err.message, "error");
        }
    }

    if (ksExportReelBtn) {
        ksExportReelBtn.addEventListener("click", () => triggerCustomExport(false));
    }

    if (ksExportZipBtn) {
        ksExportZipBtn.addEventListener("click", () => triggerCustomExport(true));
    }

    if (sendToStudioBtn) {
        sendToStudioBtn.addEventListener("click", () => {
            const clipsToLoad = window.latestFilteredClips || 
                                (studioClips && studioClips.length > 0 ? studioClips : null) || 
                                JSON.parse(sessionStorage.getItem("latest_filtered_clips") || "[]");
            const vidName = window.latestSourceVideoName || currentSourceVideoName || sessionStorage.getItem("latest_source_video_name") || "";
            const vidUrl = window.latestSourceVideoUrl || currentSourceVideoUrl || sessionStorage.getItem("latest_source_video_url") || "";

            tabNavStudio.click();
            if (clipsToLoad && clipsToLoad.length > 0) {
                initStudioData(clipsToLoad, vidName, vidUrl);
            }
        });
    }

    // In generator pipeline completion, pass raw clips and source video
    window.setStudioInitialState = function(clips, videoFilename, sourceUrl) {
        initStudioData(clips, videoFilename, sourceUrl);
    };

})();
