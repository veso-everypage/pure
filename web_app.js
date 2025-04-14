// web_app.js - Client-side logic for EveryPage Pure interface

document.addEventListener('DOMContentLoaded', () => {
    const apiKeyInput = document.getElementById('api-key-input');
    const uploadForm = document.getElementById('upload-form');
    const fileInput = document.getElementById('file-input'); // Still the actual input
    const fileNameDisplay = document.getElementById('file-name-display'); // Span to show name
    const submitButton = document.getElementById('submit-button');
    const uploadStatusDiv = document.getElementById('upload-status');
    const jobQueueContainer = document.getElementById('job-queue-container'); // Updated ID
    const jobDetailsContainer = document.getElementById('job-details-container');
    const jobDetailsContentDiv = document.getElementById('job-details-content'); // New content div
    const downloadButtonsDiv = document.getElementById('download-buttons'); // New buttons div
    const downloadJsonButton = document.getElementById('download-json-button');
    const downloadCsvButton = document.getElementById('download-csv-button');
    const refreshQueueButton = document.getElementById('refresh-queue-button');
    const saveApiKeyButton = document.getElementById('save-api-key-button');
    const apiKeyStatusDiv = document.getElementById('api-key-status');
    const apiKeyHintSpan = document.getElementById('api-key-hint');
    // New prompt input elements
    const taskInput = document.getElementById('task-input');
    const outputStructureInput = document.getElementById('output-structure-input');
    const outputStructureGroup = document.getElementById('output-structure-group');
    const outputFormatRadios = document.querySelectorAll('input[name="output_format"]');
    const templateSelect = document.getElementById('prompt-template-select');
    const metaToggle = document.getElementById('meta-toggle'); // Meta intelligence toggle
    const userPromptInput = document.getElementById('user-prompt-input'); // Hidden input stores constructed prompt

    const API_BASE_URL = ''; // Assuming API is served from the same origin
    const API_KEY_STORAGE_KEY = 'everypage_pure_api_key';

    let selectedJobId = null;
    let queuePollingInterval = null;
    let detailsPollingInterval = null;
    let currentJobDataForDownload = null; // Store full data for download buttons

    // --- API Key Management ---

    function getApiKey() {
        // Prioritize saved key, but allow fallback to input field value *if needed* by an action
        // Best practice is to click "Save Key" first.
        // Always prioritize saved key from session storage
        const storedKey = sessionStorage.getItem(API_KEY_STORAGE_KEY);
        return storedKey || apiKeyInput.value.trim(); // Fallback to input only if not stored
    }

    function updateApiKeyHint() {
        const key = getApiKey();
        if (key && key.length >= 4) {
            apiKeyHintSpan.textContent = `(Using key ending '...${key.slice(-4)}')`;
        } else if (key) {
             apiKeyHintSpan.textContent = `(Using key: ${key})`; // Show short keys fully
        }
         else {
            apiKeyHintSpan.textContent = '(No API Key detected)';
        }
    }

    function saveApiKey(showStatus = false) {
        const key = apiKeyInput.value.trim();
        apiKeyStatusDiv.textContent = ''; // Clear previous text content only
        apiKeyInput.style.border = '1px solid #ccc';

        if (key) {
            sessionStorage.setItem(API_KEY_STORAGE_KEY, key);
            console.log('API Key saved to session storage.');
            if (showStatus) {
                 // Use innerHTML to preserve the hint span
                apiKeyStatusDiv.innerHTML = 'API Key saved for this session. <span id="api-key-hint" style="margin-left: 10px; color: #555;"></span>';
                apiKeyStatusDiv.style.color = 'green';
            }
        } else {
            sessionStorage.removeItem(API_KEY_STORAGE_KEY);
            console.log('API Key removed from session storage.');
            if (showStatus) {
                apiKeyStatusDiv.innerHTML = 'API Key cleared. <span id="api-key-hint" style="margin-left: 10px; color: #555;"></span>';
                apiKeyStatusDiv.style.color = 'orange';
            }
            sessionStorage.removeItem(API_KEY_STORAGE_KEY);
            console.log('API Key removed from session storage.');
        }
        updateApiKeyHint(); // Update hint after save/clear
    }

    // Load API key from session storage on load
    const storedKey = sessionStorage.getItem(API_KEY_STORAGE_KEY);
    if (storedKey) {
        apiKeyInput.value = storedKey;
    }

    // Add listener for the new Save button
    saveApiKeyButton.addEventListener('click', () => saveApiKey(true));

    // Optional: Clear status message text content only if user starts typing again
    apiKeyInput.addEventListener('input', () => {
         // Find the text node within apiKeyStatusDiv, if any, and clear it
         Array.from(apiKeyStatusDiv.childNodes).forEach(node => {
             if (node.nodeType === Node.TEXT_NODE) {
                 node.textContent = '';
             }
         });
         // Don't clear the hint span here
    });

    // --- API Helper ---
async function fetchWithApiKey(url, options = {}, statusElement = uploadStatusDiv) {
    const apiKey = getApiKey(); // Get the key *at the time of the fetch*
    updateApiKeyHint(); // Ensure hint is up-to-date when fetch starts
    apiKeyInput.style.border = '1px solid #ccc';


        if (!apiKey) {
            statusElement.innerHTML = '<p class="error-message">API Key is required. Please enter it above and click "Save Key".</p>';
            apiKeyInput.style.border = '1px solid red';
            return null; // Indicate failure
        }

        const headers = {
            ...(options.headers || {}),
            'x-api-key': apiKey, // Send API key in header
        };

        // Don't set Content-Type for FormData, browser does it correctly with boundary
        if (!(options.body instanceof FormData)) {
             headers['Content-Type'] = 'application/json';
        }
        // Accept JSON responses
        headers['Accept'] = 'application/json';


        try {
            const response = await fetch(`${API_BASE_URL}${url}`, { ...options, headers });

            if (!response.ok) {
                let errorDetail = `HTTP error ${response.status}: ${response.statusText}`;
                try {
                    const errorJson = await response.json();
                    errorDetail = errorJson.detail || JSON.stringify(errorJson);
                } catch (e) {
                    // Ignore if response is not JSON
                }
                throw new Error(errorDetail);
            }

             // Handle cases where response might be empty (e.g., 202 Accepted)
             const contentType = response.headers.get("content-type");
             if (contentType && contentType.indexOf("application/json") !== -1) {
                 return await response.json();
             } else {
                 // Return status for non-json responses or empty body
                 return { status: response.status, ok: response.ok };
             }

        } catch (error) {
            console.error('API Fetch Error:', error);
            // Display error appropriately depending on context (upload, queue, details)
            throw error; // Re-throw for specific handling
        }
    }

    // --- Rendering Functions ---

    function renderJobQueue(jobs) {
        if (!jobs || jobs.length === 0) {
            jobQueueDiv.innerHTML = '<p>No recent jobs found.</p>';
            return;
        }

        jobQueueContainer.innerHTML = ''; // Clear previous content
        jobs.forEach(job => {
            const jobItem = document.createElement('div');
            jobItem.classList.add('job-item', `status-${job.status}`);
            jobItem.dataset.jobId = job.job_id; // Store job ID for click handling
            jobItem.innerHTML = `
                <strong>Job ID:</strong> ${job.job_id.substring(0, 8)}... <br>
                <strong>File:</strong> ${job.document_name} <br>
                <strong>Status:</strong> ${job.status} (${job.progress.toFixed(1)}%) <br>
                <strong>Created:</strong> ${new Date(job.created_at).toLocaleString()}
            `;
            // Add title attribute for full ID on hover
            jobItem.title = `Job ID: ${job.job_id}`; // Add tooltip for full ID
            jobItem.addEventListener('click', () => {
                selectJob(job.job_id);
            });
            jobQueueContainer.appendChild(jobItem);
        });
    }

    function renderJobDetails(job) {
        if (!job) {
            jobDetailsContentDiv.innerHTML = '<p class="placeholder">Job details not available.</p>'; // Render placeholder in content div
            downloadButtonsDiv.style.display = 'none'; // Ensure buttons hidden
            return;
        }

        let resultsHtml = ''; // Start with empty results HTML
        let showDownloads = false; // Flag to control button visibility

        if (job.status === 'completed' && job.results) {
            currentJobDataForDownload = job; // Store for download buttons
            showDownloads = true; // Set flag to show downloads

            resultsHtml = `<h4>Processing Summary:</h4>
                           <pre>${JSON.stringify(job.results.processing_summary, null, 2)}</pre>
                           <h4>Page Transcriptions:</h4>`;

            if (job.results.pages && job.results.pages.length > 0) {
                 job.results.pages.forEach(page => {
                     resultsHtml += `<div class="page-result">`;
                     resultsHtml += `<div class="page-header">Page ${page.page_number} <span class="page-status status-${page.status.replace('error_', 'error').replace('mock_', 'mock')}">${page.status}</span></div>`; // Basic status styling
                     resultsHtml += `<div class="page-content open">`; // Keep content open by default
                     // Display whatever data object was returned successfully
                     if (page.status === 'success' && page.data) {
                         // Check if data is a string (plain text result) or object (JSON result)
                         if (typeof page.data === 'string') {
                            resultsHtml += `<h5>Result (Text):</h5><pre>${escapeHtml(page.data)}</pre>`;
                         } else if (typeof page.data === 'object') {
                            // Display the raw JSON object returned by the AI based on user prompt
                            resultsHtml += `<h5>Result (JSON):</h5><pre>${escapeHtml(JSON.stringify(page.data, null, 2))}</pre>`;
                         } else {
                             resultsHtml += `<p>Received unexpected data type.</p>`;
                         }
                     } else if (page.error_message) {
                         resultsHtml += `<p class="error-message">Error: ${escapeHtml(page.error_message)}</p>`;
                         if (page.raw_response) {
                            resultsHtml += `<h6>Raw Response Snippet:</h6><pre>${escapeHtml(page.raw_response)}</pre>`;
                         }
                     } else {
                         resultsHtml += `<p>No transcription data or error message available.</p>`;
                     }
                     resultsHtml += `</div></div>`; // Close page-content and page-result
                 });
            } else {
                 resultsHtml += `<p>No page results found.</p>`;
            }

        } else if (job.status === 'error') { // Simplified condition
             currentJobDataForDownload = null; // Cannot download error state
             showDownloads = false; // Ensure downloads are hidden
             if (job.errors) {
                 resultsHtml = `<h4>Errors:</h4>`;
                 job.errors.forEach(err => {
                      resultsHtml += `<p class="error-message"><strong>${err.code}:</strong> ${escapeHtml(err.message)}</p>`;
                      if(err.context) {
                         resultsHtml += `<pre>${JSON.stringify(err.context, null, 2)}</pre>`;
                      }
                 });
             } else {
                 resultsHtml = `<p class="error-message">An unknown error occurred.</p>`;
             }
        } else { // Still processing or other state
             currentJobDataForDownload = null;
             showDownloads = false; // Ensure downloads are hidden
             resultsHtml = `<p>Processing... (${job.progress.toFixed(1)}%)</p>`;
        }

       // Add title attribute for full ID on hover
       // Render the details *only* into the content div
       jobDetailsContentDiv.innerHTML = `
            <h3>Details for Job: ${job.job_id.substring(0, 13)}...</h3>
            <p><strong>File:</strong> ${job.document_name}</p>
            <p><strong>Status:</strong> <span class="status-${job.status}">${job.status}</span></p>
            <p><strong>Progress:</strong> ${job.progress.toFixed(1)}%</p>
            <p><strong>Created:</strong> ${new Date(job.created_at).toLocaleString()}</p>
            <p><strong>Updated:</strong> ${job.updated_at ? new Date(job.updated_at).toLocaleString() : 'N/A'}</p>
            <p><strong>Completed:</strong> ${job.completed_at ? new Date(job.completed_at).toLocaleString() : 'N/A'}</p>
            <hr>
            ${resultsHtml}
        `;

        // Set visibility of download buttons AFTER rendering content
        if (downloadButtonsDiv) {
            downloadButtonsDiv.style.display = showDownloads ? 'block' : 'none';
        }

        // Set title for the main container
        jobDetailsContainer.title = `Details for Job ID: ${job.job_id}`;

         // If the job is still processing, poll for updates
         if (job.status !== 'completed' && job.status !== 'error') {
             startDetailsPolling(job.job_id);
         } else {
              stopDetailsPolling(); // Stop polling if job is finished
         }
    }

    // --- Data Fetching Functions ---

    async function fetchJobQueue() {
        console.log('Fetching job queue...');
        try {
            const jobs = await fetchWithApiKey('/jobs/active?limit=20'); // Fetch recent 20 jobs
            if (jobs) {
                renderJobQueue(jobs);
            }
        } catch (error) {
            jobQueueContainer.innerHTML = `<p class="error-message">Failed to load job queue: ${error.message}</p>`;
        }
    }

    async function fetchJobDetails(jobId) {
        console.log(`Fetching details for job ${jobId}...`);
        stopDetailsPolling(); // Stop previous polling if any
        jobDetailsContentDiv.innerHTML = `<p>Loading details for job ${jobId}...</p>`;
        downloadButtonsDiv.style.display = 'none'; // Hide buttons while loading
        try {
            const job = await fetchWithApiKey(`/jobs/${jobId}`);
            if (job) {
                renderJobDetails(job);
            }
        } catch (error) {
            jobDetailsContentDiv.innerHTML = `<p class="error-message">Failed to load job details for ${jobId}: ${error.message}</p>`;
            downloadButtonsDiv.style.display = 'none'; // Hide buttons on error
        }
    }

    // --- Polling Functions ---

    function startQueuePolling(interval = 10000) { // Poll every 10 seconds
        stopQueuePolling(); // Clear existing interval if any
        console.log('Starting queue polling...');
        fetchJobQueue(); // Fetch immediately
        queuePollingInterval = setInterval(fetchJobQueue, interval);
    }

    function stopQueuePolling() {
        if (queuePollingInterval) {
            console.log('Stopping queue polling.');
            clearInterval(queuePollingInterval);
            queuePollingInterval = null;
        }
    }

     function startDetailsPolling(jobId, interval = 3000) { // Poll every 3 seconds for active job
         stopDetailsPolling(); // Clear existing interval
         if (!jobId) return;
         console.log(`Starting details polling for job ${jobId}...`);
         detailsPollingInterval = setInterval(() => fetchJobDetails(jobId), interval);
     }

     function stopDetailsPolling() {
         if (detailsPollingInterval) {
             console.log('Stopping details polling.');
             clearInterval(detailsPollingInterval);
             detailsPollingInterval = null;
         }
     }

    // --- Structured Prompt Handling ---

    function constructPrompt() {
        // Ensure elements exist before accessing value
        const task = taskInput ? taskInput.value.trim() : '';
        const outputFormatRadio = document.querySelector('input[name="output_format"]:checked');
        const outputFormat = outputFormatRadio ? outputFormatRadio.value : 'json'; // Default to json
        const structure = outputStructureInput ? outputStructureInput.value.trim() : '';

        // Basic prompt template structure
        let prompt = `<document_analysis>\n`;
        prompt += `  <system>\n    You are an advanced document analysis AI. Analyze the provided image for page {page_number}.\n  </system>\n`;
        prompt += `  <input>\n    <image_data>Page {page_number}</image_data>\n`;
        // Use placeholder if task is empty? Or enforce input? For now, use empty if needed.
        prompt += `    <task>${escapeHtml(task)}</task>\n`;
        prompt += `  </input>\n`;
        prompt += `  <output_format>\n`;
        prompt += `    <format>${outputFormat === 'json' ? 'JSON' : 'Plain Text'}</format>\n`;
        // Only include structure if JSON is selected AND structure field has content
        if (outputFormat === 'json' && structure) {
            // Basic validation/cleaning for structure example? For now, just escape.
            prompt += `    <structure>\n${escapeHtml(structure)}\n    </structure>\n`;
        }
        prompt += `    <constraints>\n`;
        if (outputFormat === 'json') {
            prompt += `      <constraint>Return ONLY valid JSON, starting with '{{' and ending with '}}'.</constraint>\n`;
            prompt += `      <constraint>Do not include any text, explanations, or markdown formatting before or after the JSON object.</constraint>\n`;
             if (structure) {
                 prompt += `      <constraint>The JSON structure MUST follow the example provided in the <structure> tag.</constraint>\n`;
             }
        } else {
             prompt += `      <constraint>Return only the processed text as plain text, without any JSON formatting or explanations.</constraint>\n`;
        }
        prompt += `    </constraints>\n`;
        prompt += `  </output_format>\n`;
        prompt += `</document_analysis>`;

        if (userPromptInput) {
            userPromptInput.value = prompt; // Store the constructed prompt
            // console.log("Constructed Prompt:", prompt); // For debugging
        } else {
             console.error("Hidden user prompt input not found!");
        }
    }

    function toggleOutputStructureInput() {
        const outputFormatRadio = document.querySelector('input[name="output_format"]:checked');
        const selectedFormat = outputFormatRadio ? outputFormatRadio.value : 'json';

        if (outputStructureGroup) {
            outputStructureGroup.style.display = (selectedFormat === 'json') ? 'block' : 'none';
        }
        constructPrompt(); // Reconstruct prompt when format changes
    }

    // Add listeners for prompt construction (check if elements exist first)
    if (taskInput) taskInput.addEventListener('input', constructPrompt);
    if (outputStructureInput) outputStructureInput.addEventListener('input', constructPrompt);
    outputFormatRadios.forEach(radio => radio.addEventListener('change', toggleOutputStructureInput));

    // Initial setup
    // --- Prompt Templates ---
    const promptTemplates = {
        "transcribe": {
            task: "Accurately transcribe all text content visible on page {page_number}. Preserve formatting like line breaks where appropriate.",
            format: "json",
            structure: `{\n  "transcription": "..."\n}`
        },
        "summarize": {
            task: "Provide a concise summary of the main points on page {page_number}.",
            format: "json",
            structure: `{\n  "summary": "...",\n  "key_points": ["...", "..."]\n}`
        },
        "translate_es": {
            task: "Accurately translate all text content visible on page {page_number} to Spanish.",
            format: "json",
            structure: `{\n  "original_language": "detected language",\n  "spanish_translation": "..."\n}`
        },
         "translate_zh": {
            task: "Accurately translate all text content visible on page {page_number} to Chinese (Simplified).",
            format: "json",
            structure: `{\n  "original_language": "detected language",\n  "chinese_translation": "..."\n}`
        },
         "qa": {
            task: "Analyze the document on page {page_number} and answer the following question: [Your Question Here]",
            format: "json",
            structure: `{\n  "question": "[Your Question Here]",\n  "answer": "..." \n}`
        },
        // Add more templates as needed
    };

    function loadTemplate() {
        const selectedValue = templateSelect.value;
        const template = promptTemplates[selectedValue];

        if (template) {
            taskInput.value = template.task;
            outputStructureInput.value = template.structure || ''; // Use empty string if no structure defined
            // Select the correct radio button
            document.querySelector(`input[name="output_format"][value="${template.format}"]`).checked = true;
        } else if (selectedValue === "") {
            // "-- Select --" chosen, maybe clear fields or leave as is for custom? Let's clear.
            taskInput.value = '';
            outputStructureInput.value = '';
            document.querySelector(`input[name="output_format"][value="json"]`).checked = true; // Default back to JSON
        }
        // If "custom" is selected, do nothing, leave fields as they are for user editing

        toggleOutputStructureInput(); // Update visibility and reconstruct prompt
    }

    // Add listener for template selection
    if (templateSelect) templateSelect.addEventListener('change', loadTemplate);


    // --- File Input Handling ---
    if (fileInput && fileNameDisplay) {
        fileInput.addEventListener('change', () => {
            if (fileInput.files.length > 0) {
                fileNameDisplay.textContent = fileInput.files[0].name;
                submitButton.disabled = false; // Enable submit button
            } else {
                fileNameDisplay.textContent = 'No file selected.';
                submitButton.disabled = true; // Disable submit button
            }
        });
    } else {
         console.error("File input or display element not found.");
    }


    // Initial setup
    toggleOutputStructureInput(); // Set initial visibility and construct initial prompt

    // --- Event Handlers ---

    uploadForm.addEventListener('submit', async (event) => {
        event.preventDefault(); // Prevent default form submission
        uploadStatusDiv.innerHTML = '<p>Uploading...</p>';
        submitButton.disabled = true;

        const file = fileInput.files[0];
        if (!file) {
            uploadStatusDiv.innerHTML = '<p class="error-message">Please select a file.</p>';
            submitButton.disabled = false;
            return;
        }

        const formData = new FormData();
        formData.append('file', file);
        // Construct the final prompt one last time to ensure it's up-to-date
        constructPrompt();
        // Ensure hidden input exists before trying to append
        if (userPromptInput) {
            formData.append('user_prompt', userPromptInput.value);
        } else {
             uploadStatusDiv.innerHTML = '<p class="error-message">Error: Prompt input element not found.</p>';
             submitButton.disabled = false;
             return; // Prevent submission
        }
        // Add selected output format
        const selectedFormatRadio = document.querySelector('input[name="output_format"]:checked');
        formData.append('output_format', selectedFormatRadio ? selectedFormatRadio.value : 'json');
        // Add meta intelligence toggle state (send "true" or "false" as string)
        formData.append('use_meta_intelligence', metaToggle ? metaToggle.checked.toString() : "false");

        try {
            const result = await fetchWithApiKey('/scan', {
                method: 'POST',
                body: formData,
            });

            if (result && result.job_id) {
                uploadStatusDiv.innerHTML = `<p>Upload successful! Job ID: ${result.job_id}. Processing started.</p>`;
                fileInput.value = ''; // Clear file input
                // Refresh queue and select the new job
                await fetchJobQueue();
                selectJob(result.job_id);
                 startQueuePolling(); // Ensure queue polling is active
            } else if (result && !result.ok) {
                 // Handle non-OK status from fetch helper if JSON wasn't returned
                 uploadStatusDiv.innerHTML = `<p class="error-message">Upload failed. Status: ${result.status}</p>`;
            }
             else {
                 // Should not happen if fetchWithApiKey throws on error
                 uploadStatusDiv.innerHTML = '<p class="error-message">Upload failed. Unknown error.</p>';
             }
        } catch (error) {
            uploadStatusDiv.innerHTML = `<p class="error-message">Upload failed: ${error.message}</p>`;
        } finally {
            submitButton.disabled = false;
        }
    });

    refreshQueueButton.addEventListener('click', () => {
         // Use the correct container ID
         jobQueueContainer.innerHTML = '<p>Refreshing queue...</p>';
         fetchJobQueue();
    });

    function selectJob(jobId) {
         // Scroll the right column to the top when a job is selected
         if (jobDetailsContainer.parentElement) {
             jobDetailsContainer.parentElement.scrollTop = 0;
         }
         console.log(`Selecting job ${jobId}`);
         selectedJobId = jobId;
         // Highlight selected job in the queue (optional)
         document.querySelectorAll('.job-item').forEach(item => {
             item.style.fontWeight = item.dataset.jobId === jobId ? 'bold' : 'normal';
             item.style.backgroundColor = item.dataset.jobId === jobId ? '#e0e0ff' : '#fff'; // Or use classes
         });
         fetchJobDetails(jobId);
    }

    // --- Download Functions ---

    function triggerDownload(blob, filename) {
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.style.display = 'none';
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        a.remove();
    }

    function downloadJson() {
        if (!currentJobDataForDownload || !currentJobDataForDownload.results) {
            alert("No completed job data available to download.");
            return;
        }
        const jobData = currentJobDataForDownload; // Use the stored full job data
        const jsonData = JSON.stringify(jobData.results, null, 2); // Pretty print
        const blob = new Blob([jsonData], { type: 'application/json' });
        const filename = `${jobData.job_id}_results.json`;
        triggerDownload(blob, filename);
    }

    function downloadCsv() {
        if (!currentJobDataForDownload || !currentJobDataForDownload.results || !currentJobDataForDownload.results.pages) {
            alert("No completed page data available to download as CSV.");
            return;
        }
        const jobData = currentJobDataForDownload;
        const pages = jobData.results.pages;

        // Basic CSV conversion: assumes page data is a flat JSON object
        // More complex prompts might require more sophisticated CSV logic
        let csvContent = "page_number,status,error_message";
        let headersSet = false;
        const pageDataRows = [];

        pages.forEach(page => {
            const baseRow = [page.page_number, page.status, `"${(page.error_message || '').replace(/"/g, '""')}"`];
            if (page.data && typeof page.data === 'object') {
                if (!headersSet) {
                    Object.keys(page.data).forEach(key => csvContent += `,${key}`);
                    csvContent += "\n";
                    headersSet = true;
                }
                const dataValues = Object.keys(page.data).map(key => {
                    const value = page.data[key];
                    // Basic handling for arrays/objects in cells - just stringify
                    const formattedValue = (typeof value === 'object' && value !== null)
                                           ? JSON.stringify(value).replace(/"/g, '""')
                                           : (value || '').toString().replace(/"/g, '""');
                    return `"${formattedValue}"`;
                });
                pageDataRows.push(baseRow.concat(dataValues).join(','));
            } else if (page.data && typeof page.data === 'string') {
                 if (!headersSet) {
                    csvContent += ",result_text\n"; // Header for plain text result
                    headersSet = true;
                 }
                 pageDataRows.push(baseRow.concat([`"${page.data.replace(/"/g, '""')}"`]).join(','));
            }
             else {
                 if (!headersSet) { csvContent += "\n"; headersSet = true; } // Ensure header row ends if no data
                 pageDataRows.push(baseRow.join(',')); // Add row with no data fields
            }
        });

        csvContent += pageDataRows.join('\n');

        const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
        const filename = `${jobData.job_id}_results.csv`;
        triggerDownload(blob, filename);
    }

    // Attach download listeners
    downloadJsonButton.addEventListener('click', downloadJson);
    downloadCsvButton.addEventListener('click', downloadCsv);


   // Helper to escape HTML for display in <pre> tags
   function escapeHtml(unsafe) {
       if (unsafe === null || typeof unsafe === 'undefined') return '';
       return unsafe
            .toString()
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
     }

    // --- Initial Load ---
    updateApiKeyHint(); // Show initial hint on load
    startQueuePolling(); // Start polling the queue on page load

});