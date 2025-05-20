# backend/data_visualizer.py
# Questo modulo contiene funzioni per creare visualizzazioni (grafici)
# basate sui dati estratti dai file IFC.

import pandas as pd
import matplotlib
matplotlib.use('Agg') # Set a non-interactive backend BEFORE importing pyplot
import matplotlib.pyplot as plt
import seaborn as sns
import os # Per gestire i percorsi dei file
import io # Per salvare l'immagine in memoria
import base64 # Per codificare l'immagine per il frontend

# Imposta uno stile gradevole per i grafici Seaborn
sns.set_theme(style="whitegrid")

def plot_entity_counts(data_df, output_dir="static/plots"):
    """
    Crea un grafico a barre del conteggio delle diverse entità IFC presenti nel DataFrame.
    Il grafico viene salvato sia come file PNG su disco (opzionale) sia restituito come stringa Base64.

    Args:
        data_df (pd.DataFrame): DataFrame contenente i dati estratti dall'IFC,
                                deve avere almeno la colonna 'IFC_Entity'.
        output_dir (str): La directory (percorso assoluto) dove salvare il grafico generato su disco.
                          Viene usata se si vuole un file fisico.

    Returns:
        tuple: (plot_filepath_relative, plot_base64_string)
               - plot_filepath_relative (str): Il percorso relativo del file dell'immagine del grafico
                                               (es. "plots/nomefile.png"), utile per URL nel frontend.
                                               None se il salvataggio su disco fallisce o non è previsto.
               - plot_base64_string (str): L'immagine del grafico codificata in base64
                                           (es. "data:image/png;base64,..."), pronta per essere
                                           incorporata direttamente in HTML. None se errore.
    """
    if data_df is None or data_df.empty or 'IFC_Entity' not in data_df.columns:
        print("Error: DataFrame is empty or 'IFC_Entity' column is missing for plot_entity_counts.")
        return None, None

    # Calcola il conteggio per ogni tipo di entità
    entity_counts = data_df['IFC_Entity'].value_counts()

    # Crea la figura e gli assi per il grafico
    fig, ax = plt.subplots(figsize=(12, 7)) # Dimensioni del grafico (larghezza, altezza in pollici)
    
    # Crea il grafico a barre usando Seaborn
    sns.barplot(x=entity_counts.index, y=entity_counts.values, ax=ax, palette="viridis")
    
    # Impostazioni del grafico
    ax.set_xlabel("IFC Entity Type", fontsize=12)
    ax.set_ylabel("Count", fontsize=12)
    ax.set_title("Distribution of IFC Entities", fontsize=14, weight='bold')
    
    # Ruota le etichette sull'asse x per una migliore leggibilità
    ax.set_xticklabels(ax.get_xticklabels(), rotation=75, ha='right', fontsize=10)
    ax.tick_params(axis='y', labelsize=10)
    
    fig.tight_layout() # Aggiusta il layout per evitare sovrapposizioni

    # --- Salvare il grafico ---
    
    # 1. Salvare come immagine in memoria (per la stringa Base64)
    img_buffer = io.BytesIO()
    try:
        fig.savefig(img_buffer, format='png', bbox_inches='tight')
        img_buffer.seek(0)
        img_base64_data = base64.b64encode(img_buffer.read()).decode('utf-8')
        plot_base64_string = f"data:image/png;base64,{img_base64_data}"
    except Exception as e_mem:
        print(f"Error saving plot to memory buffer: {e_mem}")
        plot_base64_string = None
    finally:
        img_buffer.close()
    
    # 2. (Opzionale ma consigliato per il debug o se serve un file) Salvare come file su disco
    plot_filepath_relative = None
    if output_dir: # Solo se una directory di output è specificata
        try:
            # Assicurati che la directory di output esista
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)
            
            # Crea un nome file univoco (es. basato sul timestamp) per evitare sovrascritture
            plot_filename_disk = f"entity_counts_{pd.Timestamp.now().strftime('%Y%m%d%H%M%S%f')}.png"
            plot_filepath_absolute_disk = os.path.join(output_dir, plot_filename_disk)
            
            fig.savefig(plot_filepath_absolute_disk, format='png', bbox_inches='tight')
            print(f"Plot saved to disk: {plot_filepath_absolute_disk}")
            
            # Il percorso restituito per l'URL nel frontend sarà relativo alla directory 'static'
            # Assumendo che output_dir sia qualcosa come 'backend/static/plots'
            # e PLOTS_SUBDIR sia 'plots'
            # Questo dipende da come Flask è configurato per servire file statici
            base_static_dir_name = os.path.basename(os.path.dirname(output_dir)) # es. 'static'
            plot_subdir_name = os.path.basename(output_dir) # es. 'plots'
            if base_static_dir_name == 'static': # Verifica comune
                 plot_filepath_relative = f"{plot_subdir_name}/{plot_filename_disk}" # es. "plots/entity_counts_....png"
            else: # Fallback se la struttura non è come atteso
                 plot_filepath_relative = plot_filename_disk


        except Exception as e_disk:
            print(f"Error saving plot to disk at {output_dir}: {e_disk}")
            # plot_filepath_relative rimane None

    plt.close(fig) # Chiudi la figura per liberare memoria

    return plot_filepath_relative, plot_base64_string


# --- Esempio di utilizzo (per testare il modulo se eseguito direttamente) ---
if __name__ == "__main__":
    # Crea un DataFrame di esempio simile a quello che potrebbe arrivare da ifc_parser
    sample_data = {
        'FileName': ['test.ifc'] * 15,
        'IFC_Entity': ['IfcWallStandardCase'] * 5 + ['IfcDoor'] * 3 + ['IfcSlab'] * 4 + ['IfcWindow'] * 2 + ['IfcBeam'],
        'IFC_Name': [f'Wall_{i}' for i in range(5)] + [f'Door_{i}' for i in range(3)] + [f'Slab_{i}' for i in range(4)] + [f'Window_{i}' for i in range(2)] + ['Beam_1'],
        'IFC_GlobalId': [f'gid_w{i}' for i in range(5)] + [f'gid_d{i}' for i in range(3)] + [f'gid_s{i}' for i in range(4)] + [f'gid_wi{i}' for i in range(2)] + ['gid_b1'],
        'PropertySet': ['Pset_WallCommon'] * 5 + ['Pset_DoorCommon'] * 3 + ['Pset_SlabCommon'] * 4 + ['Pset_WindowCommon'] * 2 + ['Pset_BeamCommon'],
        'PropertyName': ['LoadBearing'] * 5 + ['FireRating'] * 3 + ['Thickness'] * 4 + ['OverallHeight'] * 2 + ['Span'],
        'PropertyValue': [True, True, False, True, False] + ['60'] * 3 + [200] * 4 + [1200] * 2 + [6000]
    }
    test_df = pd.DataFrame(sample_data)

    print("--- Creating example plot ---")
    # Specifica una directory di output per il test (verrà creata se non esiste)
    # Questo percorso è relativo a dove esegui lo script.
    # Per l'app Flask, `output_dir` sarà un percorso assoluto come `backend/static/plots`
    test_output_dir_for_script = "temp_generated_plots" 
    
    # Chiama la funzione per generare il grafico
    plot_path_rel, plot_b64 = plot_entity_counts(test_df, output_dir=test_output_dir_for_script)

    if plot_b64: # Controlla se la stringa base64 è stata generata
        print(f"\nPlot generated successfully!")
        if plot_path_rel:
            print(f"Relative path (for URL if served from static): {plot_path_rel}")
            # Per testare l'apertura, costruisci il percorso assoluto
            # full_plot_path_disk = os.path.abspath(os.path.join(test_output_dir_for_script, os.path.basename(plot_path_rel)))
            # print(f"Full disk path for testing: {full_plot_path_disk}")
        print(f"Base64 data (first 100 chars): {plot_b64[:100]}...")
    else:
        print("\nError during plot generation.")

