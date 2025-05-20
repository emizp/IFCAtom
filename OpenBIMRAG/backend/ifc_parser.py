# backend/ifc_parser.py
# Module for parsing IFC files, extracting metadata (including software with a simplified method) and properties.

import ifcopenshell
import pandas as pd
import os
import json # Added for JSON operations

def extract_ifc_metadata(ifc_file_path):
    """
    Opens an IFC file and extracts key metadata: file name, schema, software (simplified method).

    Args:
        ifc_file_path (str): The path to the IFC file.

    Returns:
        tuple: (file_name, ifc_schema, authoring_software) or (None, None, None) in case of error.
    """
    try:
        ifc_model = ifcopenshell.open(ifc_file_path)
    except Exception as e:
        # Use English for error/log messages that might end up in server logs
        print(f"Error opening IFC file '{ifc_file_path}' for metadata extraction: {e}")
        return None, None, None

    file_name = ifc_model.header.file_name.name if ifc_model.header.file_name else "Unknown"
    ifc_schema = ifc_model.schema if ifc_model.schema else "Unknown"
    
    # Extraction of authoring software (simplified method based on ID #1)
    authoring_software = "Unknown"
    try:
        # Direct attempt with ID #1 as per Colab example
        entity_1 = ifc_model.by_id(1)
        # Verify that the entity exists and has a 'Name' attribute that is a string
        if entity_1 and hasattr(entity_1, 'Name') and isinstance(entity_1.Name, str):
            authoring_software = entity_1.Name 
        else:
             # Use English for warning/log messages
             print(f"Warning: Could not determine software from ID #1 for '{ifc_file_path}'. Entity #1 does not exist or lacks a valid 'Name' attribute.")

    except Exception as e_soft:
        # Handles generic errors during access to ID #1
        # Use English for warning/log messages
        print(f"Warning: Error accessing ID #1 to determine software in '{ifc_file_path}': {e_soft}")
        
    return file_name, ifc_schema, authoring_software


def extract_properties_from_ifc(ifc_file_path):
    """
    Opens an IFC file, extracts element properties, and returns them as a Pandas DataFrame.
    The DataFrame will include a 'FileName' column derived from the IFC header.

    Args:
        ifc_file_path (str): The path to the IFC file to process.

    Returns:
        pandas.DataFrame: A DataFrame containing the extracted data including 'FileName'.
                          Returns an empty DataFrame if the file cannot be opened or no data is found.
    """
    try:
        ifc_model = ifcopenshell.open(ifc_file_path)
    except Exception as e:
        # Use English for error/log messages
        print(f"Error opening IFC file '{ifc_file_path}' for property extraction: {e}")
        return pd.DataFrame()

    file_name_header = "Unknown"
    try:
        if ifc_model.header and ifc_model.header.file_name:
            file_name_header = ifc_model.header.file_name.name
    except Exception as e_header:
        print(f"Warning: Could not extract file_name from header for {ifc_file_path}: {e_header}")
        # Continue even if header filename extraction fails, properties might still be extractable.

    extracted_data_list = []
    instances = ifc_model.by_type("IfcElement") # Extracts from all IfcElement

    for inst in instances:
        entity_type = inst.is_a()
        instance_name = inst.Name if hasattr(inst, 'Name') else None
        global_id = inst.GlobalId if hasattr(inst, 'GlobalId') else None

        if hasattr(inst, "IsDefinedBy"):
            for rel in inst.IsDefinedBy:
                if rel.is_a("IfcRelDefinesByProperties"):
                    prop_definition = rel.RelatingPropertyDefinition
                    if prop_definition.is_a("IfcPropertySet"):
                        pset_name = prop_definition.Name if hasattr(prop_definition, 'Name') else "Unknown"
                        
                        if hasattr(prop_definition, "HasProperties"):
                            for prop in prop_definition.HasProperties:
                                prop_name = prop.Name if hasattr(prop, 'Name') else "Unknown"
                                prop_value = None
                                
                                if hasattr(prop, "NominalValue") and prop.NominalValue is not None:
                                    prop_value = getattr(prop.NominalValue, "wrappedValue", None)
                                    # If wrappedValue is another IFC entity (e.g., IfcLabel), extract its value
                                    if hasattr(prop_value, "wrappedValue"):
                                         prop_value = getattr(prop_value, "wrappedValue", prop_value)

                                extracted_data_list.append({
                                    "IFC_Entity": entity_type,
                                    "IFC_Name": instance_name,
                                    "IFC_GlobalId": global_id,
                                    "PropertySet": pset_name,
                                    "PropertyName": prop_name,
                                    "PropertyValue": prop_value
                                })
    
    df = pd.DataFrame(extracted_data_list)

    if not df.empty:
        # Add the file name from header to all rows of the DataFrame
        df.insert(0, "FileName", file_name_header) 
        # Reorder columns for consistency
        df = df[
            ["FileName", "IFC_Entity", "IFC_Name", "IFC_GlobalId",
             "PropertySet", "PropertyName", "PropertyValue"]
        ]
    
    return df

def parse_ifc_to_files(ifc_file_path, output_dir, file_id):
    """
    Parses an IFC file, extracts properties, and saves them to CSV and JSON files.

    Args:
        ifc_file_path (str): Path to the IFC file.
        output_dir (str): Directory to save the output CSV and JSON files.
        file_id (str): A unique identifier for the file, used for naming output files.

    Returns:
        tuple: (csv_file_path, json_file_path) or (None, None) if parsing fails or no data.
    """
    print(f"Starting parsing for IFC file: {ifc_file_path} with file_id: {file_id}")
    df_properties = extract_properties_from_ifc(ifc_file_path)

    if df_properties.empty:
        print(f"No properties extracted from {ifc_file_path}. Output files will not be generated for file_id: {file_id}.")
        return None, None

    # Ensure output directory exists
    if not os.path.exists(output_dir):
        try:
            os.makedirs(output_dir)
            print(f"Created output directory: {output_dir}")
        except Exception as e_mkdir:
            print(f"Error creating output directory {output_dir}: {e_mkdir}. Cannot save files for file_id: {file_id}.")
            return None, None

    # Use file_id for unique, clean filenames (without original extension)
    base_filename = file_id 
    csv_filename = f"{base_filename}.csv"
    json_filename = f"{base_filename}.json"

    csv_file_path = os.path.join(output_dir, csv_filename)
    json_file_path = os.path.join(output_dir, json_filename)

    try:
        # Save to CSV
        df_properties.to_csv(csv_file_path, index=False, encoding='utf-8')
        print(f"Successfully saved CSV to {csv_file_path}")

        # Save to JSON (structured semantic data - for now, records from DataFrame)
        json_data_records = df_properties.to_dict(orient='records')
        # Replace pd.NA or NaN with None for JSON compatibility
        json_data_cleaned = []
        for record in json_data_records:
            cleaned_record = {}
            for k, v in record.items():
                if pd.isna(v):
                    cleaned_record[k] = None
                else:
                    cleaned_record[k] = v
            json_data_cleaned.append(cleaned_record)
        
        with open(json_file_path, 'w', encoding='utf-8') as f_json:
            json.dump(json_data_cleaned, f_json, indent=4, ensure_ascii=False)
        print(f"Successfully saved JSON to {json_file_path}")
        
        return csv_file_path, json_file_path

    except Exception as e_save:
        print(f"Error saving output files for file_id {file_id} (IFC: {ifc_file_path}): {e_save}")
        # Clean up partially created files if an error occurs during saving
        if os.path.exists(csv_file_path):
            try:
                os.remove(csv_file_path)
                print(f"Cleaned up partial CSV: {csv_file_path}")
            except Exception as e_del_csv:
                print(f"Error deleting partial CSV {csv_file_path}: {e_del_csv}")
        if os.path.exists(json_file_path):
            try:
                os.remove(json_file_path)
                print(f"Cleaned up partial JSON: {json_file_path}")
            except Exception as e_del_json:
                print(f"Error deleting partial JSON {json_file_path}: {e_del_json}")
        return None, None


# --- Example of usage (for testing the module if executed directly) ---
if __name__ == "__main__":
    # Replace 'None' with a valid path to an .ifc file to test
    # Example: test_ifc_file_path = "path/to/your/test_file.ifc"
    test_ifc_file_path = None 
    test_output_directory = "temp_ifc_parser_outputs"
    # Define a sample file_id for testing
    test_file_identifier = "test_ifc_file_123"

    if test_ifc_file_path and os.path.exists(test_ifc_file_path):
        print(f"--- Testing IFC Parser Module with File: {test_ifc_file_path} ---")
        
        # Test metadata extraction
        print("\n--- Testing Metadata Extraction ---")
        fname_meta, schema_meta, software_meta = extract_ifc_metadata(test_ifc_file_path)
        if fname_meta:
             print(f"File Name (from header): {fname_meta}")
             print(f"IFC Schema: {schema_meta}")
             print(f"Authoring Software: {software_meta}")
        else:
             print("Could not extract metadata.")

        # Test property extraction (DataFrame only)
        print("\n--- Testing Property Extraction (to DataFrame) ---")
        data_df = extract_properties_from_ifc(test_ifc_file_path)
        
        if not data_df.empty:
            print(f"Successfully extracted properties to DataFrame.")
            print(f"DataFrame Head:\n{data_df.head()}")
            print(f"Total properties extracted: {len(data_df)}")
            print("\nUnique Entity Counts in DataFrame:")
            print(data_df['IFC_Entity'].value_counts())

            # Test parsing to CSV and JSON files
            print(f"\n--- Testing Parsing to CSV and JSON Files (Output Dir: {test_output_directory}) ---")
            
            # Create the test output directory if it doesn't exist
            if not os.path.exists(test_output_directory):
                os.makedirs(test_output_directory)
                print(f"Created test output directory: {test_output_directory}")
            
            csv_p, json_p = parse_ifc_to_files(test_ifc_file_path, test_output_directory, test_file_identifier)
            if csv_p and json_p:
                print(f"Successfully created CSV: {os.path.abspath(csv_p)}")
                print(f"Successfully created JSON: {os.path.abspath(json_p)}")
                # Note: For a real test suite, you might want to verify contents and then clean up these files/directory.
            else:
                print("Failed to create CSV/JSON files during test.")
        else:
            print(f"\nNo property data extracted from {test_ifc_file_path}. Cannot test file generation fully.")
    else:
        if test_ifc_file_path: # Only print if a path was given but not found
            print(f"Test IFC file path not found: {test_ifc_file_path}. Modify 'test_ifc_file_path' in the code to run tests.")
        else:
            print("Test IFC file path is not specified. Please provide a valid .ifc file path to run tests.")
