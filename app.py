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
from sku_processing import preprocess_data, generate_comparison_table
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

    extracted_json_data = run_gemini_extraction(uploaded_files)
    if extracted_json_data:
        st.session_state.extracted_data = extracted_json_data
        st.success(f"Successfully extracted data for {len(extracted_json_data)} items from Gemini!")

        # Preprocess and populate unique SKU names for selection
        processed_items = preprocess_data(st.session_state.extracted_data)
        if processed_items:
            st.session_state.processed_items = processed_items
            unique_sku_names = sorted(list(set(item.sku_name for item in processed_items)))
            st.session_state.all_sku_names = unique_sku_names
            # Preselect all SKUs after extraction
            st.session_state.selected_sku_names = unique_sku_names.copy()
        else:
            st.warning("No processable items found after initial parsing of Gemini data.")
    else:
        st.error("Failed to extract data using Gemini or no data returned.")

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