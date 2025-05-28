import streamlit as st
import pandas as pd
import os
import sys # Import sys to get executable path
import logging # Import logging

# Configure logging
logging.basicConfig(level=logging.ERROR, format='%(asctime)s - %(levelname)s - %(message)s')

logging.debug("--- app.py execution started ---")
logging.debug(f"Python executable: {sys.executable}")
logging.debug(f"Streamlit version: {st.__version__}")
logging.debug(f"Type of st object: {type(st)}")
logging.debug(f"Attributes in st: {dir(st)}")

# Removed unused imports: re, json, google.genai, google.genai.types, io.BytesIO, base64, tempfile, shutil

# Import functions and classes from new modules
from gemini_service import run_gemini_extraction
from sku_processing import preprocess_data, generate_comparison_table, normalize_sku_names # Added normalize_sku_names
from ui_components import (
    render_file_uploader,
    render_sku_selector,
    render_comparison_button,
    render_comparison_table,
    render_notes,
    render_raw_data_expander,
    render_footer,
)
from models import ProcessedSkuItem # Import ProcessedSkuItem for type hinting if needed, or just for clarity
import instructor
from openai import OpenAI # For instructor client

# --- Initialize Chutes AI Instructor Client ---
# Attempt to get API key from Streamlit secrets, then environment variable
CHUTES_API_KEY = st.secrets.get("CHUTES_API_KEY", os.environ.get("CHUTES_API_KEY"))
chutes_instructor_client = None
if CHUTES_API_KEY:
    try:
        chutes_instructor_client = instructor.from_openai(
            OpenAI(
                base_url="https://llm.chutes.ai/v1/",
                api_key=CHUTES_API_KEY,
                timeout=30.0, # Added timeout
            )
        )
        logging.info("Chutes AI Instructor client initialized successfully.")
    except Exception as e:
        logging.error(f"Failed to initialize Chutes AI Instructor client: {e}")
        # chutes_instructor_client will remain None, app can proceed without normalization if client is None
else:
    logging.warning("CHUTES_API_KEY not found in Streamlit secrets or environment variables. SKU normalization will be skipped.")


# --- Streamlit App UI ---
st.set_page_config(layout="wide")
st.title("📄 SKU Quotation Comparator using Gemini AI ✨")

# Initialize session state
if 'extracted_data' not in st.session_state:
    st.session_state.extracted_data = None # Raw data from Gemini (list of dicts)
if 'processed_items' not in st.session_state:
    st.session_state.processed_items = [] # List of ProcessedSkuItem objects
if 'all_sku_names' not in st.session_state:
    st.session_state.all_sku_names = [] # List of unique sku_name strings
if 'selected_sku_names' not in st.session_state:
    st.session_state.selected_sku_names = [] # List of selected sku_name strings
if 'comparison_df' not in st.session_state:
    st.session_state.comparison_df = pd.DataFrame()

# --- Handlers for UI component interactions ---

def handle_extract_data(uploaded_files):
    """Handles the data extraction process when the button is clicked."""
    st.session_state.extracted_data = None # Reset previous
    st.session_state.processed_items = []
    st.session_state.all_sku_names = []
    st.session_state.selected_sku_names = []
    st.session_state.comparison_df = pd.DataFrame()

    all_extracted_data = []
    batch_size = 3
    num_files = len(uploaded_files)

    if num_files == 0:
        st.warning("No files uploaded.")
        return

    st.info(f"Processing {num_files} files in batches of {batch_size}...")

    for i in range(0, num_files, batch_size):
        batch_files = uploaded_files[i : i + batch_size]
        batch_number = (i // batch_size) + 1
        st.write(f"Processing batch {batch_number} with {len(batch_files)} files...")

        extracted_json_data = run_gemini_extraction(batch_files)

        if extracted_json_data:
            all_extracted_data.extend(extracted_json_data)
            st.success(f"Successfully extracted data for {len(extracted_json_data)} items from batch {batch_number}.")
        else:
            st.warning(f"No data extracted from batch {batch_number}.")

    if all_extracted_data:
        st.session_state.extracted_data = all_extracted_data
        st.success(f"Successfully extracted data for a total of {len(all_extracted_data)} items from all files!")

        # Preprocess and populate unique SKU names for selection
        processed_items = preprocess_data(st.session_state.extracted_data)
        if processed_items:
            st.session_state.processed_items = processed_items
            
            # --- SKU Name Normalization Step ---
            if chutes_instructor_client and st.session_state.processed_items:
                current_sku_names = sorted(list(set(item.sku_name for item in st.session_state.processed_items)))
                if current_sku_names:
                    st.write("Normalizing SKU names via Chutes AI...") # User feedback
                    try:
                        normalized_name_map = normalize_sku_names(current_sku_names, chutes_instructor_client)

                        if normalized_name_map:
                            updated_items_count = 0
                            for item in st.session_state.processed_items:
                                original_name = item.sku_name
                                normalized_name = normalized_name_map.get(original_name, original_name)
                                if original_name != normalized_name:
                                    item.sku_name = normalized_name
                                    updated_items_count +=1
                            if updated_items_count > 0:
                                st.success(f"SKU names normalized. {updated_items_count} items updated.")
                            else:
                                st.info("SKU name normalization complete. No names were changed by the LLM.")
                        else:
                            st.warning("SKU name normalization did not return any mappings. Using original names.")
                    except Exception as e:
                        st.error(f"Error during SKU name normalization: {e}. Proceeding with original names.")
                        logging.error(f"SKU Normalization Exception: {e}", exc_info=True)
                else:
                    logging.info("No SKU names found in processed items to normalize.")
            elif not chutes_instructor_client:
                st.warning("Chutes AI client not initialized (CHUTES_API_KEY missing?). Skipping SKU name normalization.")
            # --- End SKU Name Normalization ---

            # Update all_sku_names and selected_sku_names with the new (potentially normalized) names
            unique_sku_names = sorted(list(set(item.sku_name for item in st.session_state.processed_items)))
            st.session_state.all_sku_names = unique_sku_names
            # Preselect all SKUs after extraction/normalization
            st.session_state.selected_sku_names = unique_sku_names.copy() # Ensure this is a copy
        else:
            st.warning("No processable items found after initial parsing of Gemini data.")
    else:
        st.error("Failed to extract data using Gemini or no data returned from any batch.")

def handle_generate_comparison():
    """Handles the comparison table generation when the button is clicked."""
    if st.session_state.extracted_data:
        # Use the already processed items from session state
        processed_items = st.session_state.processed_items
        selected_sku_names = st.session_state.selected_sku_names

        if processed_items and selected_sku_names:
            # Determine dynamic supplier order for columns based on all processed items
            unique_suppliers = sorted(list(set(item.supplier for item in processed_items)))
            if not unique_suppliers:
                 st.warning("No suppliers found in the processed data.")
                 st.session_state.comparison_df = pd.DataFrame()
            else:
                st.session_state.comparison_df = generate_comparison_table(
                    selected_sku_names,
                    processed_items,
                    unique_suppliers # Dynamic supplier order
                )
                if st.session_state.comparison_df.empty:
                    st.warning("No data to display for the selected SKUs.")
                else:
                    st.success("Comparison table generated!")
        elif not processed_items:
             st.error("No data available after preprocessing. Cannot generate comparison.")
             st.session_state.comparison_df = pd.DataFrame()
        elif not selected_sku_names:
             st.warning("No SKUs selected for comparison.")
             st.session_state.comparison_df = pd.DataFrame()
    else:
        st.error("No extracted data found. Please extract data first.")
        st.session_state.comparison_df = pd.DataFrame()


# --- Sidebar ---
with st.sidebar:
    # Render file uploader and handle extraction
    uploaded_files = render_file_uploader(st.session_state.get('uploaded_files'), handle_extract_data)
    # Store uploaded files in session state if needed for re-runs, though Streamlit handles this
    # st.session_state.uploaded_files = uploaded_files # Optional: Streamlit's file_uploader handles state

    # Render SKU selector if data is available
    if st.session_state.all_sku_names:
        st.session_state.selected_sku_names = render_sku_selector(
            st.session_state.all_sku_names,
            st.session_state.selected_sku_names,
            lambda skus: st.session_state.update(selected_sku_names=skus) # Update session state on selection change
        )

        # Render comparison button if SKUs are selected
        if st.session_state.selected_sku_names:
            render_comparison_button(handle_generate_comparison)


# --- Main Area ---

# Display warnings if extraction yielded no processable SKUs
if st.session_state.extracted_data is not None and not st.session_state.all_sku_names and not uploaded_files:
     st.warning("Data was extracted by Gemini, but no SKUs could be identified for selection. Please check the raw data below or try with different/clearer PDFs.")

# Render the comparison table if available
render_comparison_table(st.session_state.comparison_df)

# Display notes
render_notes()

# Display raw data expander
render_raw_data_expander(st.session_state.extracted_data)

# Display footer
render_footer()