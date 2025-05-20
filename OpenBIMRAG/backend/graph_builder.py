# backend/graph_builder.py
# Modulo per costruire un grafo di conoscenza da un file IFC usando networkx.

import ifcopenshell
import networkx as nx
import time # Per misurare il tempo di costruzione

def build_graph_from_ifc(ifc_file_path):
    """
    Costruisce un grafo NetworkX (orientato) da un file IFC.

    In questa versione:
    - Nodi: Entità IfcProduct (elementi, spazi, ecc.), identificati dal loro GlobalId.
            Attributi del nodo includono: ifc_type, name (se presente), ifc_id (ID numerico).
    - Archi: Rappresentano relazioni IFC:
        - IfcRelContainedInSpatialStructure: Elemento -> contenuto_in -> Struttura Spaziale
        - IfcRelAggregates: Parte -> aggregato_a -> Intero
        - IfcRelConnects: Elemento1 -> connesso_a -> Elemento2 (bidirezionale se non specificato)
        - IfcRelVoidsElement: Apertura (es. IfcOpeningElement) -> svuota -> Elemento (es. IfcWall)
        - IfcRelFillsElement: Elemento (es. IfcDoor, IfcWindow) -> riempie -> Apertura (IfcOpeningElement)

    Args:
        ifc_file_path (str): Il percorso del file IFC.

    Returns:
        networkx.DiGraph: Il grafo costruito, oppure None se il file non può essere aperto.
        float: Tempo impiegato per costruire il grafo in secondi.
    """
    start_time = time.time()
    try:
        ifc_model = ifcopenshell.open(ifc_file_path)
        print(f"Successfully opened IFC file for graph building: {ifc_file_path}")
    except Exception as e:
        print(f"Error opening IFC file '{ifc_file_path}' for graph building: {e}")
        return None, 0.0

    G = nx.DiGraph() # Grafo Orientato
    
    # --- 1. Aggiungere Nodi ---
    # Usiamo IfcObjectDefinition come base più generale che include IfcProduct, IfcActor, IfcGroup, ecc.
    # IfcProduct è comunque una scelta comune per gli elementi principali.
    # Per ora, ci concentriamo su IfcProduct per coerenza con l'esempio precedente.
    definitions = ifc_model.by_type("IfcProduct") 
    print(f"Found {len(definitions)} IfcProduct instances to process as potential nodes.")

    for item in definitions:
        try:
            global_id = item.GlobalId
            if not global_id: # Alcune entità potrebbero non avere un GlobalId
                print(f"Warning: Skipping entity ID {item.id()} of type {item.is_a()} due to missing GlobalId.")
                continue
            
            node_id = global_id # Usiamo GlobalId come ID univoco del nodo
            
            G.add_node(
                node_id, 
                ifc_type=item.is_a(), 
                name=getattr(item, 'Name', None),
                description=getattr(item, 'Description', None),
                ifc_id=item.id() 
            )
        except AttributeError as e:
            print(f"Warning: Skipping entity ID {item.id()} of type {item.is_a()} due to attribute error: {e}")
            continue
            
    print(f"Added {G.number_of_nodes()} nodes to the graph.")

    # --- 2. Aggiungere Archi (Relazioni) ---
    
    # Funzione helper per aggiungere archi verificando l'esistenza dei nodi
    def add_relationship_edge(source_entity, target_entity, rel_instance, default_label="related_to"):
        try:
            if not (hasattr(source_entity, 'GlobalId') and hasattr(target_entity, 'GlobalId')):
                return False # Salta se manca GlobalId
                
            source_id = source_entity.GlobalId
            target_id = target_entity.GlobalId

            if G.has_node(source_id) and G.has_node(target_id):
                G.add_edge(
                    source_id, 
                    target_id, 
                    relation_type=rel_instance.is_a(), 
                    relation_name=getattr(rel_instance, 'Name', default_label),
                    ifc_rel_id=rel_instance.id()
                )
                return True
            # else:
                # print(f"Warning: Nodes for relation ID {rel_instance.id()} not found in graph. Source: {source_id}, Target: {target_id}")
        except AttributeError as e:
            print(f"Warning: Skipping relation ID {rel_instance.id()} of type {rel_instance.is_a()} due to missing attribute: {e}")
        return False

    edges_added_count = 0

    # IfcRelContainedInSpatialStructure: Elemento -> contenuto_in -> Struttura Spaziale
    for rel in ifc_model.by_type("IfcRelContainedInSpatialStructure"):
        relating_structure = rel.RelatingStructure
        for element in rel.RelatedElements:
            if add_relationship_edge(element, relating_structure, rel, "is_contained_in"):
                edges_added_count +=1
    
    # IfcRelAggregates: Parte -> aggregato_a -> Intero
    for rel in ifc_model.by_type("IfcRelAggregates"):
        relating_object = rel.RelatingObject # L'intero
        for part in rel.RelatedObjects: # Le parti
            if add_relationship_edge(part, relating_object, rel, "is_part_of"):
                edges_added_count += 1

    # IfcRelConnects (generico, potrebbe necessitare di specializzazione per tipo di connessione)
    # La direzione qui può essere meno definita, potremmo renderlo non orientato o aggiungere due archi.
    # Per ora, creiamo un arco da RelatingElement a RelatedElement.
    for rel in ifc_model.by_type("IfcRelConnects"):
        # Questa relazione è più complessa, es. IfcRelConnectsElements, IfcRelConnectsPorts, etc.
        # Consideriamo IfcRelConnectsElements per connessioni tra elementi strutturali/architettonici
        if hasattr(rel, 'RelatingElement') and hasattr(rel, 'RelatedElement'):
            if add_relationship_edge(rel.RelatingElement, rel.RelatedElement, rel, "connects_to"):
                 edges_added_count += 1
            # Potremmo voler aggiungere anche l'arco inverso per alcune connessioni
            # if add_relationship_edge(rel.RelatedElement, rel.RelatingElement, rel, "connected_by"):
            # edges_added_count += 1


    # IfcRelVoidsElement: Apertura (IfcOpeningElement) -> svuota -> Elemento (es. IfcWall)
    for rel in ifc_model.by_type("IfcRelVoidsElement"):
        opening = rel.RelatedOpeningElement # L'apertura
        element_voided = rel.RelatingBuildingElement # L'elemento che viene svuotato
        if add_relationship_edge(opening, element_voided, rel, "voids_in_element"):
            edges_added_count += 1

    # IfcRelFillsElement: Elemento (es. IfcDoor, IfcWindow) -> riempie -> Apertura (IfcOpeningElement)
    for rel in ifc_model.by_type("IfcRelFillsElement"):
        filling_element = rel.RelatedBuildingElement # L'elemento che riempie (porta/finestra)
        opening_filled = rel.RelatingOpeningElement # L'apertura che viene riempita
        if add_relationship_edge(filling_element, opening_filled, rel, "fills_opening"):
            edges_added_count += 1
            
    # TODO: Considerare altre relazioni come:
    # - IfcRelDefinesByProperties (collegare i PropertySet come nodi, o aggiungere proprietà come attributi degli archi/nodi)
    # - IfcRelAssignsToGroup
    # - IfcRelSpaceBoundary

    end_time = time.time()
    build_duration = end_time - start_time
    print(f"Added {edges_added_count} relationship edges.")
    print(f"Graph built in {build_duration:.2f} seconds. Total nodes: {G.number_of_nodes()}, Total edges: {G.number_of_edges()}")

    return G, build_duration

# --- Esempio di utilizzo (per testare il modulo se eseguito direttamente) ---
if __name__ == "__main__":
    # Sostituire 'None' con un percorso valido a un file .ifc per testare
    test_ifc_file = None 
    
    if test_ifc_file:
        print(f"Building graph for: {test_ifc_file}...")
        graph, duration = build_graph_from_ifc(test_ifc_file)
        
        if graph:
            print(f"\n--- Graph Info ---")
            print(f"Graph built successfully in {duration:.2f} seconds.")
            print(f"Number of nodes: {graph.number_of_nodes()}")
            print(f"Number of edges: {graph.number_of_edges()}")

            if graph.number_of_nodes() > 0:
                print("\n--- Sample Nodes (first 5) ---")
                node_count = 0
                for node_id, data in graph.nodes(data=True):
                    print(f"Node: {node_id}, Type: {data.get('ifc_type')}, Name: {data.get('name')}")
                    node_count += 1
                    if node_count >= 5:
                        break
            
            if graph.number_of_edges() > 0:
                print("\n--- Sample Edges (first 5) ---")
                edge_count = 0
                for u, v, data in graph.edges(data=True):
                    print(f"Edge: ({u}) --[{data.get('relation_name', data.get('relation_type'))}]--> ({v})")
                    edge_count += 1
                    if edge_count >= 5:
                        break
        else:
            print("\nFailed to build graph.")
    else:
        print("Test IFC file path not specified. Modify 'test_ifc_file' in the code to run tests.")

