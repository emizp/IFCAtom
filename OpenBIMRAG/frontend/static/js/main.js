// frontend/static/js/main.js
document.addEventListener('DOMContentLoaded', () => {
    const ifcFileInput = document.getElementById('ifcFileInput');
    const uploadButton = document.getElementById('uploadButton');
    const uploadStatus = document.getElementById('upload-status');
    const fileList = document.getElementById('fileList');
    // const runQueryButton = document.getElementById('runQueryButton'); // Old button, replaced
    const extractDataButton = document.getElementById('extractDataButton');
    const generateChartButton = document.getElementById('generateChartButton');
    const generateGraphButton = document.getElementById('generateGraphButton');
    const queryStatus = document.getElementById('query-status');
    const resultsTableBody = document.querySelector('#resultsTable tbody');
    const resultsTableHead = document.querySelector('#resultsTable thead');
    const entityChart = document.getElementById('entityChart');
    const filterIfcEntityInput = document.getElementById('filterIfcEntity');
    const filterPropertySetInput = document.getElementById('filterPropertySet');
    const filterPropertyNameInput = document.getElementById('filterPropertyName');
    const applyFiltersButton = document.getElementById('applyFiltersButton');
    const clearFiltersButton = document.getElementById('clearFiltersButton');

    // New DOM Elements for file management and chart navigation
    const selectAllFilesButton = document.getElementById('selectAllFilesButton');
    const deselectAllFilesButton = document.getElementById('deselectAllFilesButton');
    const prevChartButton = document.getElementById('prevChartButton');
    const nextChartButton = document.getElementById('nextChartButton');
    const currentChartInfo = document.getElementById('currentChartInfo');
    const chartNavigation = document.getElementById('chart-navigation');
    const noChartMessage = document.getElementById('noChartMessage');
    const graphResultsArea = document.getElementById('graph-results-area'); // For displaying graph

    let uploadedFiles = []; // Store info about uploaded files: { id, filename, schema, software, category, selected, status, result_paths }
    let fullDataset = []; // Store the full dataset from the ITO query
    let currentChartsData = []; // Stores { file_id, filename, chart_base64 }
    let currentChartIndex = 0;
    let pollingIntervals = {}; // Store interval IDs for polling: { fileId: intervalId }

    const CATEGORIES = ['N/A', 'ARC', 'STR', 'MEP'];

    // --- File Upload Logic ---
    uploadButton.addEventListener('click', async () => {
        if (ifcFileInput.files.length === 0) {
            uploadStatus.textContent = 'Please select one or more IFC files.';
            uploadStatus.style.color = 'red';
            return;
        }

        const formData = new FormData();
        for (const file of ifcFileInput.files) {
            formData.append('ifcFiles', file);
        }

        uploadStatus.textContent = 'Uploading...';
        uploadStatus.style.color = 'orange';

        try {
            const response = await fetch('/api/upload', {
                method: 'POST',
                body: formData,
            });

            const result = await response.json();

            if (response.ok) {
                uploadStatus.textContent = result.message; // e.g., "X IFC file(s) received. Processing started in background."
                uploadStatus.style.color = 'blue'; // Indicate processing has started
                
                const newFilesData = result.files; // Files array from backend {id, filename, schema, software, status}

                newFilesData.forEach(fileData => {
                    // Check if file already exists (e.g., from a previous partial upload in the same session)
                    const existingFileIndex = uploadedFiles.findIndex(f => f.id === fileData.id);
                    if (existingFileIndex === -1) {
                        uploadedFiles.push({
                            ...fileData, // id, filename, schema, software, status (should be 'processing')
                            category: 'N/A', // Default category
                            selected: true,   // Default to selected
                            result_paths: null // Will be populated when 'completed'
                        });
                    } else {
                        // Update status if it was already there (though backend should give new IDs for new uploads)
                        uploadedFiles[existingFileIndex].status = fileData.status;
                    }

                    // Start polling for this file if its status is 'processing'
                    if (fileData.status === 'processing') {
                        pollFileStatus(fileData.id);
                    }
                });
                renderFileList();
            } else {
                uploadStatus.textContent = `Error: ${result.error || 'Upload failed'}`;
                uploadStatus.style.color = 'red';
            }
        } catch (error) {
            uploadStatus.textContent = `Network error: ${error.message}`;
            uploadStatus.style.color = 'red';
            console.error('Upload error:', error);
        }
    });

    function renderFileList() {
        fileList.innerHTML = ''; // Clear existing list
        if (uploadedFiles.length === 0) {
            const li = document.createElement('li');
            li.textContent = 'No files uploaded yet.';
            fileList.appendChild(li);
            return;
        }
        uploadedFiles.forEach((file, index) => {
            const li = document.createElement('li');
            li.style.display = 'flex';
            li.style.alignItems = 'center';
            li.style.marginBottom = '5px';

            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.classList.add('file-checkbox');
            checkbox.dataset.fileId = file.id;
            checkbox.checked = file.selected;
            checkbox.addEventListener('change', () => {
                uploadedFiles[index].selected = checkbox.checked;
            });

            const fileInfoSpan = document.createElement('span');
            // Display file status dynamically
            let statusText = file.status ? `Status: ${file.status}` : '';
            if (file.status === 'failed' && file.error) {
                statusText += ` (Error: ${file.error})`;
            }
            fileInfoSpan.textContent = ` ${file.filename} (Schema: ${file.schema || 'N/A'}, Software: ${file.software || 'N/A'}) - ${statusText} - Category: `;
            fileInfoSpan.style.marginLeft = '5px';
            fileInfoSpan.id = `status-span-${file.id}`; // ID to update status text

            const categorySelect = document.createElement('select');
            categorySelect.dataset.fileId = file.id;
            CATEGORIES.forEach(cat => {
                const option = document.createElement('option');
                option.value = cat;
                option.textContent = cat;
                if (cat === file.category) {
                    option.selected = true;
                }
                categorySelect.appendChild(option);
            });
            categorySelect.addEventListener('change', (e) => {
                uploadedFiles[index].category = e.target.value;
            });
            categorySelect.style.marginLeft = '5px';

            li.appendChild(checkbox);
            li.appendChild(fileInfoSpan);
            li.appendChild(categorySelect);

            // Add download links if completed
            if (file.status === 'completed' && file.result_paths) {
                const csvLink = document.createElement('a');
                csvLink.href = `/generated_content/${file.result_paths.csv_path.replace(/^cache\\/, '')}`;
                csvLink.textContent = 'Download CSV';
                csvLink.target = '_blank';
                csvLink.style.marginLeft = '10px';
                li.appendChild(csvLink);

                const jsonLink = document.createElement('a');
                jsonLink.href = `/generated_content/${file.result_paths.json_path.replace(/^cache\\/, '')}`;
                jsonLink.textContent = 'Download JSON';
                jsonLink.target = '_blank';
                jsonLink.style.marginLeft = '5px';
                li.appendChild(jsonLink);
            }
            fileList.appendChild(li);
        });
    }

    // --- File Status Polling --- 
    function pollFileStatus(fileId) {
        if (pollingIntervals[fileId]) {
            clearInterval(pollingIntervals[fileId]); // Clear existing interval if any
        }

        pollingIntervals[fileId] = setInterval(async () => {
            try {
                const response = await fetch(`/api/status/${fileId}`);
                if (!response.ok) {
                    console.error(`Error fetching status for ${fileId}: ${response.status}`);
                    // Optionally stop polling on certain errors (e.g., 404)
                    if (response.status === 404) {
                        clearInterval(pollingIntervals[fileId]);
                        delete pollingIntervals[fileId];
                        updateFileListItem(fileId, { status: 'error', error: 'File ID not found on server.' });
                    }
                    return;
                }
                const statusData = await response.json();
                
                // Update the file's status in the uploadedFiles array
                const fileIndex = uploadedFiles.findIndex(f => f.id === fileId);
                if (fileIndex !== -1) {
                    uploadedFiles[fileIndex].status = statusData.status;
                    uploadedFiles[fileIndex].error = statusData.error; // Store error message
                    if (statusData.status === 'completed') {
                        uploadedFiles[fileIndex].result_paths = statusData.result; // Store {csv_path, json_path}
                        uploadedFiles[fileIndex].schema = statusData.schema || uploadedFiles[fileIndex].schema; // Update schema if provided
                        uploadedFiles[fileIndex].software = statusData.software || uploadedFiles[fileIndex].software; // Update software if provided
                    }

                    // Update the specific list item in the UI
                    updateFileListItem(fileId, uploadedFiles[fileIndex]);

                    // If processing is complete or failed, stop polling for this file
                    if (statusData.status === 'completed' || statusData.status === 'failed') {
                        clearInterval(pollingIntervals[fileId]);
                        delete pollingIntervals[fileId];
                    }
                }
            } catch (error) {
                console.error(`Polling error for ${fileId}:`, error);
                // Optionally stop polling on network errors too
                // clearInterval(pollingIntervals[fileId]);
                // delete pollingIntervals[fileId];
                // updateFileListItem(fileId, { status: 'error', error: 'Network error during polling.' });
            }
        }, 5000); // Poll every 5 seconds
    }

    function updateFileListItem(fileId, fileData) {
        const statusSpan = document.getElementById(`status-span-${fileId}`);
        const listItem = statusSpan ? statusSpan.closest('li') : null;

        if (statusSpan) {
            let statusText = fileData.status ? `Status: ${fileData.status}` : '';
            if (fileData.status === 'failed' && fileData.error) {
                statusText += ` (Error: ${fileData.error})`;
            }
            statusSpan.textContent = ` ${fileData.filename} (Schema: ${fileData.schema || 'N/A'}, Software: ${fileData.software || 'N/A'}) - ${statusText} - Category: `;
        }

        if (listItem && fileData.status === 'completed' && fileData.result_paths) {
            // Remove existing download links to prevent duplication if this function is called multiple times
            listItem.querySelectorAll('a.download-link').forEach(link => link.remove());

            const csvLink = document.createElement('a');
            csvLink.href = `/generated_content/${fileData.result_paths.csv_path.replace(/^cache\\/, '')}`;
            csvLink.textContent = 'Download CSV';
            csvLink.target = '_blank';
            csvLink.style.marginLeft = '10px';
            csvLink.classList.add('download-link');
            listItem.appendChild(csvLink);

            const jsonLink = document.createElement('a');
            jsonLink.href = `/generated_content/${fileData.result_paths.json_path.replace(/^cache\\/, '')}`;
            jsonLink.textContent = 'Download JSON';
            jsonLink.target = '_blank';
            jsonLink.style.marginLeft = '5px';
            jsonLink.classList.add('download-link');
            listItem.appendChild(jsonLink);
        }
    }


    // --- ITO Query and Data Extraction Logic ---
    extractDataButton.addEventListener('click', async () => {
        const selectedFiles = uploadedFiles.filter(file => file.selected && file.status === 'completed');
        if (selectedFiles.length === 0) {
            queryStatus.textContent = 'Please select at least one processed (completed) file to extract data.';
            queryStatus.style.color = 'red';
            return;
        }

        const fileIds = selectedFiles.map(file => file.id);
        queryStatus.textContent = 'Extracting data...';
        queryStatus.style.color = 'orange';

        try {
            const response = await fetch('/api/extract_data', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ file_ids: fileIds }),
            });

            const result = await response.json();

            if (response.ok) {
                queryStatus.textContent = 'Data extracted successfully!';
                queryStatus.style.color = 'green';
                fullDataset = result.data; // Assuming result.data is an array of objects
                displayResults(fullDataset);
                // Clear previous chart and graph
                entityChart.style.display = 'none';
                noChartMessage.style.display = 'block';
                chartNavigation.style.display = 'none';
                currentChartsData = [];
                graphResultsArea.innerHTML = 'Select a single processed file and click "Generate Graph".';
            } else {
                queryStatus.textContent = `Error: ${result.error || 'Failed to extract data'}`;
                queryStatus.style.color = 'red';
            }
        } catch (error) {
            queryStatus.textContent = `Network error: ${error.message}`;
            queryStatus.style.color = 'red';
            console.error('Data extraction error:', error);
        }
    });

    // --- Chart Generation Logic ---
    generateChartButton.addEventListener('click', async () => {
        const selectedFiles = uploadedFiles.filter(file => file.selected && file.status === 'completed');
        if (selectedFiles.length === 0) {
            queryStatus.textContent = 'Please select at least one processed (completed) file to generate charts.';
            queryStatus.style.color = 'red';
            return;
        }

        const fileIds = selectedFiles.map(file => file.id);
        queryStatus.textContent = 'Generating chart(s)...';
        queryStatus.style.color = 'orange';
        entityChart.style.display = 'none';
        noChartMessage.style.display = 'block';
        chartNavigation.style.display = 'none';

        try {
            const response = await fetch('/api/generate_chart', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ file_ids: fileIds }),
            });

            const result = await response.json();

            if (response.ok) {
                queryStatus.textContent = 'Chart(s) generated successfully!';
                queryStatus.style.color = 'green';
                currentChartsData = result.charts; // Expecting an array of {file_id, filename, chart_base64}
                currentChartIndex = 0;
                displayCurrentChart();
            } else {
                queryStatus.textContent = `Error generating chart(s): ${result.error || 'Failed'}`;
                queryStatus.style.color = 'red';
                noChartMessage.textContent = result.error || 'Failed to generate chart(s).';
                noChartMessage.style.display = 'block';
            }
        } catch (error) {
            queryStatus.textContent = `Network error during chart generation: ${error.message}`;
            queryStatus.style.color = 'red';
            noChartMessage.textContent = 'Network error during chart generation.';
            noChartMessage.style.display = 'block';
            console.error('Chart generation error:', error);
        }
    });

    // --- Graph Generation Logic ---
    generateGraphButton.addEventListener('click', async () => {
        const selectedFiles = uploadedFiles.filter(file => file.selected && file.status === 'completed');
        if (selectedFiles.length !== 1) {
            queryStatus.textContent = 'Please select exactly one processed (completed) file to generate a graph.';
            queryStatus.style.color = 'red';
            graphResultsArea.innerHTML = 'Please select exactly one processed (completed) file to generate a graph.';
            return;
        }

        const fileId = selectedFiles[0].id;
        queryStatus.textContent = 'Generating graph...';
        queryStatus.style.color = 'orange';
        graphResultsArea.innerHTML = 'Generating graph...';

        try {
            const response = await fetch('/api/generate_graph', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ file_id: fileId }),
            });

            const result = await response.json();

            if (response.ok) {
                queryStatus.textContent = 'Graph generated successfully!';
                queryStatus.style.color = 'green';
                if (result.graph_path) {
                    graphResultsArea.innerHTML = `<img src="${result.graph_path}" alt="Knowledge Graph" style="max-width: 100%; height: auto;"/>`;
                } else if (result.message) {
                     graphResultsArea.innerHTML = result.message;
                } else {
                    graphResultsArea.innerHTML = 'Graph generated, but no visual provided.';
                }
            } else {
                queryStatus.textContent = `Error generating graph: ${result.error || 'Failed'}`;
                queryStatus.style.color = 'red';
                graphResultsArea.innerHTML = `Error: ${result.error || 'Failed to generate graph.'}`;
            }
        } catch (error) {
            queryStatus.textContent = `Network error during graph generation: ${error.message}`;
            queryStatus.style.color = 'red';
            graphResultsArea.innerHTML = 'Network error during graph generation.';
            console.error('Graph generation error:', error);
        }
    });


    // --- Display Logic for ITO Query Results ---
    function displayResults(data) {
        resultsTableHead.innerHTML = '';
        resultsTableBody.innerHTML = '';

        if (!data || data.length === 0) {
            const row = resultsTableBody.insertRow();
            const cell = row.insertCell();
            cell.colSpan = 1; // Default, will be updated if headers exist
            cell.textContent = 'No data found for this query.';
            return;
        }

        // Create table headers
        const headers = Object.keys(data[0]);
        const headerRow = resultsTableHead.insertRow();
        headers.forEach(headerText => {
            const th = document.createElement('th');
            th.textContent = headerText;
            headerRow.appendChild(th);
        });
        if (resultsTableBody.rows.length > 0 && resultsTableBody.rows[0].cells.length === 1) {
             resultsTableBody.rows[0].cells[0].colSpan = headers.length;
        }

        // Populate table rows
        data.forEach(item => {
            const row = resultsTableBody.insertRow();
            headers.forEach(header => {
                const cell = row.insertCell();
                cell.textContent = item[header] !== null && item[header] !== undefined ? item[header] : '';
            });
        });
    }

    // --- Chart Display and Navigation ---
    function displayCurrentChart() {
        if (currentChartsData.length > 0 && currentChartsData[currentChartIndex]) {
            const chartData = currentChartsData[currentChartIndex];
            entityChart.src = chartData.chart_base64;
            entityChart.alt = `IFC Entity Distribution Chart for ${chartData.filename}`;
            entityChart.style.display = 'block';
            noChartMessage.style.display = 'none';
            chartNavigation.style.display = 'flex'; // Show navigation
            currentChartInfo.textContent = `Chart ${currentChartIndex + 1} of ${currentChartsData.length}: ${chartData.filename}`;
            prevChartButton.disabled = currentChartIndex === 0;
            nextChartButton.disabled = currentChartIndex === currentChartsData.length - 1;
        } else {
            entityChart.style.display = 'none';
            noChartMessage.textContent = 'No chart to display. Generate charts first.';
            noChartMessage.style.display = 'block';
            chartNavigation.style.display = 'none';
        }
    }

    prevChartButton.addEventListener('click', () => {
        if (currentChartIndex > 0) {
            currentChartIndex--;
            displayCurrentChart();
        }
    });

    nextChartButton.addEventListener('click', () => {
        if (currentChartIndex < currentChartsData.length - 1) {
            currentChartIndex++;
            displayCurrentChart();
        }
    });

    // --- File Selection Management ---
    selectAllFilesButton.addEventListener('click', () => {
        uploadedFiles.forEach(file => file.selected = true);
        renderFileList();
    });

    deselectAllFilesButton.addEventListener('click', () => {
        uploadedFiles.forEach(file => file.selected = false);
        renderFileList();
    });
});