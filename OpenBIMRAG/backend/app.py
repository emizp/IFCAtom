# backend/app.py
# File principale dell'applicazione backend Flask per IFC Analyzer AI.

import os
import uuid # Added for unique file IDs
import threading # Added for asynchronous processing
from flask import Flask, request, jsonify, send_from_directory, current_app # Added current_app
from werkzeug.utils import secure_filename
import pandas as pd
from concurrent.futures import ThreadPoolExecutor
import time # For creating unique file IDs if needed, and for thread pool operations
import networkx as nx # Added for graph generation
import matplotlib.pyplot as plt # Added for graph visualization

# Importa i moduli locali che abbiamo creato
import ifc_parser 
import data_visualizer # Importiamo il modulo per i grafici

# --- Configurazione Iniziale ---

# Crea l'istanza dell'applicazione Flask
# Configure static_folder to point to frontend/static for serving CSS, JS directly
# os.path.dirname(__file__) is the 'backend' directory
frontend_static_dir = os.path.join(os.path.dirname(__file__), '..', 'frontend', 'static')
app = Flask(__name__, static_folder=frontend_static_dir)

# Configura una cartella per salvare i file IFC caricati
UPLOAD_FOLDER = 'uploads' # Idealmente, questa dovrebbe essere in una sottocartella di 'backend'
# Se app.py è in backend/, UPLOAD_FOLDER sarà backend/uploads/
# Se app.py è nella root, UPLOAD_FOLDER sarà uploads/
# Per coerenza con la struttura, assumiamo che app.py sia in backend/
# e UPLOAD_FOLDER sia una sottocartella di backend/
if not os.path.isabs(UPLOAD_FOLDER): # Se non è un percorso assoluto
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), UPLOAD_FOLDER)

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Configura una cartella per cachare i DataFrame processati
CACHE_FOLDER = 'cache' # Sarà backend/cache/
if not os.path.isabs(CACHE_FOLDER):
    CACHE_FOLDER = os.path.join(os.path.dirname(__file__), CACHE_FOLDER)
if not os.path.exists(CACHE_FOLDER):
    os.makedirs(CACHE_FOLDER)
app.config['CACHE_FOLDER'] = CACHE_FOLDER

# Definisci le estensioni di file permesse (solo .ifc)
ALLOWED_EXTENSIONS = {'ifc'}

def allowed_file(filename):
    """Verifica se l'estensione del file è permessa."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Configura una cartella per i file statici (es. grafici generati)
STATIC_FOLDER = 'static' # Sarà backend/static/
if not os.path.isabs(STATIC_FOLDER):
    STATIC_FOLDER = os.path.join(os.path.dirname(__file__), STATIC_FOLDER)

PLOTS_SUBDIR = 'plots' # Sottocartella per i grafici
PLOTS_FOLDER = os.path.join(STATIC_FOLDER, PLOTS_SUBDIR) # Sarà backend/static/plots/
if not os.path.exists(PLOTS_FOLDER):
    os.makedirs(PLOTS_FOLDER)

GRAPHS_SUBDIR = 'graphs' # Sottocartella per i grafici di conoscenza
GRAPHS_FOLDER = os.path.join(STATIC_FOLDER, GRAPHS_SUBDIR) # Sarà backend/static/graphs/
if not os.path.exists(GRAPHS_FOLDER):
    os.makedirs(GRAPHS_FOLDER)

# Flask serve automaticamente i file dalla cartella 'static' se è al livello root dell'app.
# Se 'static' è dentro 'backend', potremmo dover configurare diversamente o servire manualmente.
# Per semplicità, Flask cerca 'static' relativo a dove l'app è inizializzata.
# Se app è in backend/, Flask cercherà backend/static.

# Struttura dati temporanea per tenere traccia dei file caricati e dei loro metadati
# In un'applicazione reale, useresti un database.
# La chiave sarà un ID univoco generato, il valore un dizionario con i dettagli.
uploaded_files_metadata = {} 

# Dictionary to store the status of parsing tasks
# Key: file_id, Value: {status: 'pending'/'processing'/'completed'/'failed', original_filename: '...', result: {'csv_path': ..., 'json_path': ...} or None, error: str or None}
parsing_status = {}

# Helper function to process a single file (load from cache or parse IFC)
# This will be run in a separate thread for each file.
def process_single_ifc_file(file_id, file_info, app_config):
    filepath = file_info.get("saved_path")
    filename = file_info.get("original_filename", "Unknown File") # Use original_filename for consistency
    df_properties = None
    cached_df_path = file_info.get("cached_df_path")

    if cached_df_path and os.path.exists(cached_df_path):
        try:
            df_properties = pd.read_pickle(cached_df_path)
            file_info["processed_data_df"] = df_properties
            print(f"Successfully loaded DataFrame from disk cache for file ID: {file_id}. Rows: {len(df_properties)}")
            return file_id, filename, df_properties
        except Exception as e:
            print(f"Error loading DataFrame from disk cache {cached_df_path} for file ID {file_id}: {e}. Will try other methods.")
            df_properties = None

    if df_properties is None:
        df_properties = file_info.get("processed_data_df")
        if df_properties is not None:
            print(f"Using existing in-memory DataFrame for file ID: {file_id}. Rows: {len(df_properties) if not df_properties.empty else 0}")
            return file_id, filename, df_properties

    if df_properties is None:
        print(f"DataFrame for file ID {file_id} not found in disk or memory cache. Loading from IFC...")
        if filepath and os.path.exists(filepath):
            try:
                # Corrected: extract_properties_from_ifc returns only the DataFrame
                parsed_df = ifc_parser.extract_properties_from_ifc(filepath)
                print(f"[Debug] For file ID {file_id}, parsed_df type: {type(parsed_df)}, Shape: {parsed_df.shape if hasattr(parsed_df, 'shape') else 'N/A'}")
                if parsed_df is not None:
                    df_properties = parsed_df
                    file_info["processed_data_df"] = df_properties
                    print(f"Successfully parsed IFC; loaded properties for file ID: {file_id}. Rows: {len(df_properties) if not df_properties.empty else 0}")
                    if not df_properties.empty:
                        new_cache_filename = f"{file_id.replace('-', '_')}_df.pkl" # Ensure filename is valid
                        new_cache_filepath = os.path.join(app_config['CACHE_FOLDER'], new_cache_filename)
                        try:
                            df_properties.to_pickle(new_cache_filepath)
                            file_info["cached_df_path"] = new_cache_filepath
                            print(f"Successfully cached newly parsed DataFrame to disk: {new_cache_filepath}")
                        except Exception as pickle_save_e:
                            print(f"Error saving newly parsed DataFrame to pickle cache for {file_id}: {pickle_save_e}")
                    else:
                        print(f"Parsed IFC for {file_id}, but it resulted in an empty DataFrame. Not caching to disk.")
                else:
                    print(f"Parsing IFC for {file_id} did not return a DataFrame (returned None).")
                    df_properties = pd.DataFrame() # Assign empty DataFrame to avoid errors later
            except Exception as parse_e:
                print(f"Error parsing IFC file {filepath} for file ID {file_id}: {parse_e}")
                current_app.logger.error(f"Exception during IFC parsing for {file_id} ({filepath}): {parse_e}", exc_info=True)
                df_properties = pd.DataFrame() # Assign empty DataFrame
        else:
            print(f"Original IFC file path not found for {file_id}: {filepath}")
            df_properties = pd.DataFrame() # Assign empty DataFrame
    
    return file_id, filename, df_properties


# --- Endpoint API ---

@app.route('/api/upload', methods=['POST'])
def upload_ifc_files():
    """
    Endpoint per caricare uno o più file IFC.
    Salva i file nella UPLOAD_FOLDER e estrae i metadati iniziali.
    """
    if 'ifcFiles' not in request.files:
        # Use English for API error responses
        return jsonify({"error": "No 'ifcFiles' part in the request"}), 400

    files = request.files.getlist('ifcFiles') # Gestisce caricamenti multipli
    
    uploaded_file_info = [] # Lista per restituire info sui file caricati con successo

    for file in files:
        if file.filename == '':
            # Salta i file senza nome (potrebbe accadere se il campo è vuoto)
            continue 
            
        if file and allowed_file(file.filename):
            # Rendi sicuro il nome del file per evitare problemi di sicurezza/percorso
            filename = secure_filename(file.filename)
            
            # Crea un percorso completo per salvare il file
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            
            try:
                # Salva il file sul server
                file.save(filepath)
                # Use English for server logs
                print(f"File saved: {filepath}")

                # Estrai i metadati usando la funzione dal nostro parser
                # ifc_parser è nella stessa cartella backend/
                # Estrai solo i metadati base usando la funzione dal nostro parser
                # ifc_parser è nella stessa cartella backend/
                fname, schema, software = ifc_parser.extract_ifc_metadata(filepath)

                if fname: # Se l'estrazione dei metadati base ha successo
                    file_id = str(uuid.uuid4()) # Genera un ID univoco
                    
                    # Store initial metadata and set parsing status to "pending"
                    parsing_status[file_id] = {
                        "status": "pending",
                        "original_filename": filename,
                        "schema": schema,
                        "software": software,
                        "saved_path": filepath, # Store path for the thread
                        "result": None,
                        "error": None
                    }

                    # Store basic info in uploaded_files_metadata as well, if needed for other parts of the app
                    # This part might be refactored later if all info moves to parsing_status
                    uploaded_files_metadata[file_id] = {
                        "original_filename": filename,
                        "saved_path": filepath,
                        "schema": schema,
                        "software": software,
                        "discipline": None, # Potrebbe essere popolato in seguito
                        "processed_data_df": None, # Questo è per la query ITO, non per il parsing iniziale
                        "cached_df_path": None
                    }

                    # Start a new thread for parsing this file
                    # The target function will update parsing_status
                    thread = threading.Thread(target=parse_ifc_file_async, args=(file_id, filepath, app.config['CACHE_FOLDER']))
                    thread.start()

                    # Add info to return to the frontend (ID and basic info for status polling)
                    uploaded_file_info.append({
                        "id": file_id,
                        "filename": filename,
                        "schema": schema,
                        "software": software,
                        "status": "processing" # Inform frontend that processing has started
                    })
                    print(f"File {filename} (ID: {file_id}) received. Asynchronous parsing started.")
                else:
                    # Se l'estrazione dei metadati base fallisce
                    print(f"Core metadata (fname, schema, software) not extracted for {filename}, file was saved but not processed further.")
                    # Considera se eliminare il file o gestirlo diversamente

            except Exception as e:
                 # Use English for server error logs
                print(f"Error during saving or metadata analysis for {filename}: {e}")
                # Potresti voler restituire un errore specifico per questo file
                
        elif file and not allowed_file(file.filename):
             # Use English for server warnings/logs
             print(f"File not allowed: {file.filename}")
             # Potresti voler informare l'utente specificamente per questo file

    if not uploaded_file_info:
         # Use English for API error responses
         return jsonify({"error": "No valid IFC files uploaded or processed"}), 400

    # Restituisce l'elenco dei file caricati con successo e i loro metadati base.
    # Il messaggio ora riflette che il caricamento è veloce e il processamento completo è differito.
    if not uploaded_file_info:
        message = "No valid IFC files were processed or initiated for parsing."
        return jsonify({"message": message, "files": []}), 400 # Bad request if no files are good
    
    message = f"{len(uploaded_file_info)} IFC file(s) received. Processing started in background."
    return jsonify({"message": message, 
                    "files": uploaded_file_info}), 202 # 202 Accepted, processing not complete


# @app.route('/api/run_ito_query', methods=['POST'])
# def run_ito_query():
#     """
#     Endpoint per eseguire una query ITO sui file selezionati.
#     Estrae proprietà, filtra per tipo entità (query) e genera un grafico per ogni file.
#     """
#     try:
#         data = request.get_json()
#         if not data:
#             return jsonify({"error": "Request body must be JSON"}), 400

#         query_string = data.get('query') # Es. "IfcWall", "IfcDoor" (può essere None o vuoto)
#         file_ids = data.get('file_ids') # Lista di ID dei file selezionati dal frontend

#         if not file_ids or not isinstance(file_ids, list):
#             return jsonify({"error": "Missing or invalid 'file_ids' list in request body"}), 400

#         print(f"Received ITO query: '{query_string}' for file IDs: {file_ids}")

#         all_data_frames = []
#         charts_data = [] # New list to store individual chart data
#         futures = []

#         # Use a ThreadPoolExecutor to process files concurrently
#         # The number of max_workers can be adjusted based on typical number of files and server resources
#         with ThreadPoolExecutor(max_workers=min(5, len(file_ids) if file_ids else 1)) as executor:
#             for file_id in file_ids:
#                 if file_id in uploaded_files_metadata:
#                     file_info = uploaded_files_metadata[file_id]
#                     # Pass app.config to the helper function for CACHE_FOLDER access
#                     futures.append(executor.submit(process_single_ifc_file, file_id, file_info, app.config))
#                 else:
#                     print(f"File ID {file_id} not found in uploaded_files_metadata. Skipping.")

#             for future in futures:
#                 try:
#                     processed_file_id, processed_filename, df_properties = future.result() # Timeout can be added here
#                     if df_properties is not None and not df_properties.empty:
#                         df_properties_copy = df_properties.copy()
#                         df_properties_copy['Source Model'] = processed_filename
#                         all_data_frames.append(df_properties_copy)

#                         # Generate chart for this specific file's data
#                         df_for_chart = df_properties.copy() # Start with a copy to ensure original df_properties is not altered
#                         # query_string is no longer used for initial chart filtering here
#                         # The chart will always be based on the full data for the file initially
                        
#                         if not df_for_chart.empty:
#                             _, chart_image_base64 = data_visualizer.plot_entity_counts(df_for_chart)
#                             if chart_image_base64:
#                                 charts_data.append({
#                                     "file_id": processed_file_id,
#                                     "filename": processed_filename,
#                                     "chart_base64": chart_image_base64,
#                                     "query_used_for_chart": "All Entities" # Always all entities for initial chart
#                                 })
#                             else:
#                                 print(f"Chart generation failed for {processed_filename} using query 'All Entities'")
#                         else:
#                             print(f"No data to generate chart for {processed_filename} (displaying all entities)")
#                     else:
#                         print(f"No properties DataFrame available or it's empty for file ID: {processed_file_id}. Skipping for table and chart.")
#                 except Exception as e:
#                     # Log the exception from the thread
#                     current_app.logger.error(f"Error processing a file in thread: {e}", exc_info=True)
#                     # Optionally, you could add a placeholder or error message for this file in the response

#         if not all_data_frames:
#             print("No dataframes were processed or all were empty after concurrent processing.")
#             return jsonify({
#                 "message": "No data found for the selected files or query after processing.", 
#                 "data": [], 
#                 "charts_data": []
#             }), 200

#         # Combina tutti i DataFrame in uno solo per la tabella dei risultati
#         df_combined = pd.concat(all_data_frames, ignore_index=True) if all_data_frames else pd.DataFrame()

#         # The initial query_string is no longer used for server-side table filtering.
#         # All data is returned, and filtering is handled by the client-side "Filter Results" section.
#         df_filtered_table = df_combined

#         # Converti il DataFrame filtrato in JSON per la risposta
#         # Sostituisci NaN con None (che diventa null in JSON) per una migliore compatibilità
#         data_for_frontend = df_filtered_table.fillna(value=pd.NA).to_dict(orient='records')
#         # Sostituisci pd.NA con None per la serializzazione JSON
#         data_for_frontend = [{k: (None if pd.isna(v) else v) for k, v in record.items()} for record in data_for_frontend]


#         message = f"Query processed for {len(file_ids)} file(s). All data returned for client-side filtering."
        
#         print(f"Returning {len(data_for_frontend)} records and {len(charts_data)} charts.")

#         return jsonify({
#             "message": message,
#             "data": data_for_frontend,
#             "charts_data": charts_data # Pass the list of chart data objects
#         }), 200

#     except Exception as e:
#         current_app.logger.error(f"Error during ITO query: {e}", exc_info=True)
#         # Use English for API error responses
#         return jsonify({"error": f"An unexpected error occurred: {str(e)}"}), 500


@app.route('/api/extract_data', methods=['POST'])
def extract_data():
    """Extracts data from selected processed IFC files and returns tabular results."""
    try:
        data = request.get_json()
        if not data or 'file_ids' not in data or not isinstance(data['file_ids'], list):
            return jsonify({"error": "Missing or invalid 'file_ids' list in request body"}), 400

        file_ids = data['file_ids']
        if not file_ids:
            return jsonify({"error": "'file_ids' list cannot be empty"}), 400

        all_data_frames = []
        processed_count = 0

        with ThreadPoolExecutor(max_workers=min(5, len(file_ids))) as executor:
            futures = []
            for file_id in file_ids:
                if file_id in parsing_status and parsing_status[file_id]['status'] == 'completed':
                    if file_id in uploaded_files_metadata:
                        file_info = uploaded_files_metadata[file_id]
                        futures.append(executor.submit(process_single_ifc_file, file_id, file_info, app.config))
                    else:
                        print(f"File ID {file_id} not found in uploaded_files_metadata. Skipping for data extraction.")
                else:
                    print(f"File ID {file_id} not completed or not found in parsing_status. Skipping for data extraction.")
            
            for future in futures:
                try:
                    processed_file_id, processed_filename, df_properties = future.result()
                    if df_properties is not None and not df_properties.empty:
                        df_properties_copy = df_properties.copy()
                        df_properties_copy['Source Model'] = processed_filename # Add source model column
                        all_data_frames.append(df_properties_copy)
                        processed_count += 1
                    else:
                        print(f"No DataFrame or empty DataFrame for file ID: {processed_file_id} after processing.")
                except Exception as e:
                    current_app.logger.error(f"Error processing file in thread for data extraction: {e}", exc_info=True)

        if not all_data_frames:
            return jsonify({"message": "No data extracted. Selected files might be empty or failed processing.", "data": []}), 200

        df_combined = pd.concat(all_data_frames, ignore_index=True)
        data_for_frontend = df_combined.fillna(value=pd.NA).to_dict(orient='records')
        data_for_frontend = [{k: (None if pd.isna(v) else v) for k, v in record.items()} for record in data_for_frontend]

        message = f"Data extracted from {processed_count} file(s). Total records: {len(data_for_frontend)}."
        return jsonify({"message": message, "data": data_for_frontend}), 200

    except Exception as e:
        current_app.logger.error(f"Error during data extraction: {e}", exc_info=True)
        return jsonify({"error": f"An unexpected error occurred during data extraction: {str(e)}"}), 500


@app.route('/api/generate_chart', methods=['POST'])
def generate_chart():
    """Generates charts for selected processed IFC files."""
    try:
        data = request.get_json()
        if not data or 'file_ids' not in data or not isinstance(data['file_ids'], list):
            return jsonify({"error": "Missing or invalid 'file_ids' list in request body"}), 400

        file_ids = data['file_ids']
        if not file_ids:
            return jsonify({"error": "'file_ids' list cannot be empty"}), 400

        charts_data = []
        processed_count = 0

        with ThreadPoolExecutor(max_workers=min(5, len(file_ids))) as executor:
            futures = []
            for file_id in file_ids:
                if file_id in parsing_status and parsing_status[file_id]['status'] == 'completed':
                    if file_id in uploaded_files_metadata:
                        file_info = uploaded_files_metadata[file_id]
                        futures.append(executor.submit(process_single_ifc_file, file_id, file_info, app.config))
                    else:
                        print(f"File ID {file_id} not found in uploaded_files_metadata. Skipping for chart generation.")
                else:
                    print(f"File ID {file_id} not completed or not found in parsing_status. Skipping for chart generation.")

            for future in futures:
                try:
                    processed_file_id, processed_filename, df_properties = future.result()
                    if df_properties is not None and not df_properties.empty:
                        # Generate chart for this specific file's data
                        _, chart_image_base64 = data_visualizer.plot_entity_counts(df_properties.copy())
                        if chart_image_base64:
                            charts_data.append({
                                "file_id": processed_file_id,
                                "filename": processed_filename,
                                "chart_base64": chart_image_base64
                            })
                            processed_count += 1
                        else:
                            print(f"Chart generation failed for {processed_filename}.")
                    else:
                        print(f"No DataFrame or empty DataFrame for file ID: {processed_file_id}. Cannot generate chart.")
                except Exception as e:
                    current_app.logger.error(f"Error processing file in thread for chart generation: {e}", exc_info=True)

        if not charts_data:
            return jsonify({"message": "No charts generated. Selected files might be empty or failed processing.", "charts": []}), 200
        
        message = f"{len(charts_data)} chart(s) generated successfully from {processed_count} file(s)."
        return jsonify({"message": message, "charts": charts_data}), 200

    except Exception as e:
        current_app.logger.error(f"Error during chart generation: {e}", exc_info=True)
        return jsonify({"error": f"An unexpected error occurred during chart generation: {str(e)}"}), 500


@app.route('/api/generate_graph', methods=['POST'])
def generate_graph():
    """Generates a knowledge graph for a single processed IFC file."""
    try:
        data = request.get_json()
        if not data or 'file_id' not in data or not isinstance(data['file_id'], str):
            return jsonify({"error": "Missing or invalid 'file_id' (string) in request body"}), 400

        file_id = data['file_id']
        if not file_id:
            return jsonify({"error": "'file_id' cannot be empty"}), 400

        if not (file_id in parsing_status and parsing_status[file_id]['status'] == 'completed' and file_id in uploaded_files_metadata):
            return jsonify({"error": f"File ID {file_id} not found, not processed, or metadata missing."}), 404

        file_info = uploaded_files_metadata[file_id]
        _, filename, df_properties = process_single_ifc_file(file_id, file_info, app.config)

        if df_properties is None or df_properties.empty:
            return jsonify({"error": f"No data available for file {filename} (ID: {file_id}) to generate graph."}), 400

        # Simple graph: IfcEntity -> PropertySet (if both columns exist)
        G = nx.DiGraph()
        if 'IfcEntity' in df_properties.columns and 'PropertySet' in df_properties.columns:
            for _, row in df_properties.iterrows():
                entity = row['IfcEntity']
                pset = row['PropertySet']
                if pd.notna(entity) and pd.notna(pset):
                    G.add_node(str(entity), type='IfcEntity')
                    G.add_node(str(pset), type='PropertySet')
                    G.add_edge(str(entity), str(pset))
        
        if not G.nodes:
            return jsonify({"message": f"No graph data (nodes/edges) could be generated for {filename}.", "graph_path": None}), 200

        plt.figure(figsize=(12, 12))
        pos = nx.spring_layout(G, k=0.15, iterations=20)
        nx.draw(G, pos, with_labels=True, node_size=500, node_color="skyblue", font_size=8, arrows=True)
        plt.title(f"Knowledge Graph for {filename}")
        
        graph_filename = f"graph_{file_id.replace('-', '_')}.png"
        graph_file_path = os.path.join(GRAPHS_FOLDER, graph_filename)
        plt.savefig(graph_file_path)
        plt.close() # Close the figure to free memory

        # Construct URL for the frontend
        # serve_generated_content serves from STATIC_FOLDER (backend/static)
        # So, path should be relative to STATIC_FOLDER
        relative_graph_path = os.path.join(GRAPHS_SUBDIR, graph_filename).replace('\\', '/')
        graph_url = f"/generated_content/{relative_graph_path}"

        return jsonify({"message": f"Graph generated successfully for {filename}.", "graph_path": graph_url}), 200

    except Exception as e:
        current_app.logger.error(f"Error during graph generation: {e}", exc_info=True)
        return jsonify({"error": f"An unexpected error occurred during graph generation: {str(e)}"}), 500


# --- Asynchronous Parsing Task --- 
def parse_ifc_file_async(file_id, ifc_file_path, output_dir):
    """
    Parses an IFC file asynchronously, updates status, and saves results.
    This function is run in a separate thread.
    """
    if file_id not in parsing_status:
        print(f"Error: file_id {file_id} not found in parsing_status for async task.")
        return

    parsing_status[file_id]['status'] = 'processing'
    print(f"Async parsing started for file_id: {file_id}, path: {ifc_file_path}")

    try:
        # Call the parser function from ifc_parser module
        # output_dir here is app.config['CACHE_FOLDER'] passed from the upload endpoint
        csv_path, json_path = ifc_parser.parse_ifc_to_files(ifc_file_path, output_dir, file_id)

        if csv_path and json_path:
            parsing_status[file_id]['status'] = 'completed'
            parsing_status[file_id]['result'] = {
                'csv_path': os.path.relpath(csv_path, os.path.dirname(__file__)), 
                'json_path': os.path.relpath(json_path, os.path.dirname(__file__)) 
            }
            parsing_status[file_id]['error'] = None
            print(f"Async parsing completed for file_id: {file_id}. CSV: {csv_path}, JSON: {json_path}")
        else:
            parsing_status[file_id]['status'] = 'failed'
            parsing_status[file_id]['error'] = 'Parsing completed but no output files were generated.'
            print(f"Async parsing failed for file_id: {file_id}. No output files.")

    except Exception as e:
        parsing_status[file_id]['status'] = 'failed'
        parsing_status[file_id]['error'] = str(e)
        print(f"Exception during async parsing for file_id {file_id}: {e}")


# --- Endpoint for Checking Parsing Status --- 
@app.route('/api/status/<file_id>', methods=['GET'])
def get_parsing_status(file_id):
    """
    Endpoint to check the parsing status of a file.
    """
    if file_id in parsing_status:
        status_info = parsing_status[file_id]
        return jsonify(status_info), 200
    else:
        return jsonify({"error": "File ID not found"}), 404

@app.route('/hello')
def hello():
    return "Hello, World!"

@app.route('/')
def serve_index():
    """Serves the main index.html file for the frontend."""
    # os.path.dirname(__file__) is /backend
    # os.path.join(os.path.dirname(__file__), '..', 'frontend') is /frontend
    frontend_dir = os.path.join(os.path.dirname(__file__), '..', 'frontend')
    return send_from_directory(frontend_dir, 'index.html')

# Note: Flask is already configured to serve static files from '../frontend/static'
# via the static_folder parameter in app = Flask(...).
# So, requests to /static/css/style.css will correctly serve frontend/static/css/style.css.
# No explicit @app.route('/static/...') for frontend static files is needed here.

# --- Serve Backend Generated Static Files ---
# This is for files generated by the backend, like plots or reports,
# that might be stored in backend/static/
# The existing STATIC_FOLDER variable (defined earlier in the script) points to backend/static/
@app.route('/generated_content/<path:filename>')
def serve_generated_content(filename):
    """Serves files from the backend's dedicated static content folder (backend/static)."""
    # STATIC_FOLDER is defined above as os.path.join(os.path.dirname(__file__), 'static')
    return send_from_directory(STATIC_FOLDER, filename)

# --- Main Execution ---
if __name__ == '__main__':
    # Avvia il server di sviluppo Flask
    # debug=True ricarica automaticamente il server quando modifichi il codice
    # e fornisce messaggi di errore più dettagliati nel browser.
    # Non usare debug=True in produzione!
    app.run(debug=True, host='0.0.0.0', port=5000) # Ascolta su tutte le interfacce sulla porta 5000

