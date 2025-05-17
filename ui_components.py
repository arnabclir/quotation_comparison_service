import streamlit as st
import pandas as pd
import sys # Import sys for executable path
import logging # Import logging
from io import BytesIO
from typing import List, Callable, Any, Optional, Dict # Import Dict
from streamlit.runtime.uploaded_file_manager import UploadedFile # Correct import path

# Configure logging (can be done once in app.py, but adding here for module-specific info)
# logging.basicConfig(level=logging.ERROR, format='%(asctime)s - %(levelname)s - %(message)s') # Avoid re-configuring if already done in app.py

logging.debug("--- ui_components.py execution started ---")
logging.debug(f"Python executable in ui_components: {sys.executable}")
logging.debug(f"Streamlit version in ui_components: {st.__version__}")
logging.debug(f"Type of st object in ui_components: {type(st)}")
logging.debug(f"Attributes in st (ui_components): {dir(st)}")

# Function to apply styling (can be here or in sku_processing, keeping here for UI context)
def highlight_best_deal(row):
    """Applies styling to highlight the best deal row."""
    logging.debug(f"highlight_best_deal: Processing row with index {row.name}")
    logging.debug(f"highlight_best_deal: Row data: {row.to_dict()}")
    logging.debug(f"Row index (columns): {list(row.index)}")

    # Assuming 'Best Deal' is the column indicating the best offer supplier name
    # The column name is a tuple ('Best Deal', '')
    styles = [''] * len(row)
    best_deal_supplier = row.get(('Best Deal', ''), "-") # Use .get() for safety

    logging.debug(f"highlight_best_deal: Best deal supplier: {best_deal_supplier}")

    if best_deal_supplier != "-":
        try:
            # Find the indices of all columns belonging to the best deal supplier
            supplier_col_indices = [
                i for i, col_tuple in enumerate(row.index)
                if isinstance(col_tuple, tuple) and col_tuple[0] == best_deal_supplier
            ]
            logging.debug(f"highlight_best_deal: Supplier column indices for {best_deal_supplier}: {supplier_col_indices}")

            # Apply green background to all cells in those columns for the current row
            for i in supplier_col_indices:
                styles[i] = 'background-color: #e0ffe0' # Light green
                logging.debug(f"highlight_best_deal: Applied style to column index {i}")

        except Exception as e:
            # Log or handle potential errors in identifying columns
            logging.error(f"highlight_best_deal: Error applying styling: {e}")

    logging.debug(f"highlight_best_deal: Generated styles: {styles}")
    return styles

def render_file_uploader(uploaded_files: Optional[List[UploadedFile]], extract_handler: Callable[[List[UploadedFile]], None]):
    """Renders the file uploader and extract button in the sidebar."""
    st.header("Upload Quotation PDFs")
    new_uploaded_files = st.file_uploader(
        "Choose PDF files", type="pdf", accept_multiple_files=True,
        help="Upload one or more PDF quotation files."
    )

    if new_uploaded_files:
        # Check if new files were uploaded compared to the current state
        # This is a simple check, could be improved
        if not uploaded_files or any(nf.name not in [f.name for f in uploaded_files] for nf in new_uploaded_files) or len(new_uploaded_files) != len(uploaded_files):
             # If new files are uploaded, trigger extraction automatically or show button
             # For now, let's keep the button click explicit as in original logic
             pass # Keep the new_uploaded_files for the button check below

        if st.button("1. Extract Data with Gemini", key="extract_button", type="primary"):
             if new_uploaded_files:
                 extract_handler(new_uploaded_files)
             else:
                 st.info("Please upload files before extracting.")
    else:
        st.info("Upload PDF files to begin.")

    return new_uploaded_files # Return the potentially new uploaded files

def render_sku_selector(all_skus: List[str], selected_skus: List[str], select_handler: Callable[[List[str]], None]) -> List[str]:
    """Renders the SKU selection multiselect in the sidebar."""
    st.header("Select SKUs for Comparison")
    new_selected_skus = st.multiselect(
        "Choose SKUs to compare:",
        options=all_skus,
        default=selected_skus, # Persist selection
        help="Select the SKUs you want to see in the comparison table. (SKU names only)"
    )
    # Call handler if selection changed - Streamlit handles state, so just return
    # select_handler(new_selected_skus) # Handler might not be needed here due to session state
    return new_selected_skus


def render_comparison_button(compare_handler: Callable[[], None]):
     """Renders the Generate Comparison Table button."""
     if st.button("2. Generate Comparison Table", key="compare_button"):
         compare_handler()


def render_comparison_table(df: pd.DataFrame):
    """Displays the comparison table and download button."""
    if not df.empty:
        st.subheader("SKU Comparison Table")
        # Apply styling to the dataframe directly
        styled_df = df.style.apply(highlight_best_deal, axis=1)
        st.dataframe(styled_df, use_container_width=True)

        # Download as CSV button (use the original dataframe without styling)
        csv_buffer = BytesIO()
        df.to_csv(csv_buffer)
        csv_buffer.seek(0)
        st.download_button(
            label="Download Comparison as CSV",
            data=csv_buffer,
            file_name="sku_comparison_report.csv",
            mime="text/csv"
        )

def render_notes():
    """Displays the calculation notes."""
    st.markdown("""
    **Calculation Notes:**
    *   **Effective Rate (for Best Deal Logic)** = (Paid Qty × (Base Rate × (1 - Supplier Base Discount%))) ÷ (Paid Qty + Free Qty)
    *   **Displayed 'Eff. Rate' Column** = Base Rate × (1 - Supplier Base Discount%)
    *   **Displayed 'Eff. Disc%' Column** = Supplier Base Discount%
    *   **Best Deal determined by:** 1) Lowest effective rate (for Best Deal logic), 2) Lower paid quantity requirement if rates equal, 3) Supplier with more unique products (across all extracted items) if both prior conditions are equal.
    *   All rates and MRP are typically shown to 2 decimal places.
    *   The 'Best Deal' column indicates the supplier and quantity scheme for the most favorable offer.
    """)

def render_raw_data_expander(raw_data: Optional[List[Dict[str, Any]]]):
    """Displays the raw extracted JSON data in an expander."""
    if raw_data:
        with st.expander("View Raw Extracted JSON Data from Gemini"):
            st.json(raw_data)

def render_footer():
    """Displays the application footer."""
    st.markdown("---")
    st.caption("Ensure your `GEMINI_API_KEY` environment variable is set for Gemini functionality.")