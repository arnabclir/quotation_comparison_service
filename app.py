import streamlit as st
import pandas as pd
import os
import re
import json
from google import genai
from google.genai import types
from io import BytesIO

# --- Gemini API Key Configuration ---
# Ensure your GEMINI_API_KEY is set as an environment variable
# For Streamlit Cloud, set it in the secrets.
if "GEMINI_API_KEY" in st.secrets:
    os.environ["GEMINI_API_KEY"] = st.secrets["GEMINI_API_KEY"]

# --- Gemini Data Extraction Function ---
def run_gemini_extraction(uploaded_files):
    """
    Uploads files to Gemini, sends them for processing, and returns structured SKU data.
    """
    if not uploaded_files:
        return None

    import base64
    import os
    from google import genai
    from google.genai import types
    import json
    from io import BytesIO
    import tempfile
    import shutil

    client = genai.Client(
        api_key=os.environ.get("GEMINI_API_KEY"),
    )

    gemini_files = []
    file_uris_for_prompt = []
    temp_files = []
    try:
        with st.spinner(f"Uploading {len(uploaded_files)} files to Gemini..."):
            for uploaded_file in uploaded_files:
                # Save uploaded file to a temporary file
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                    tmp.write(uploaded_file.getvalue())
                    temp_files.append(tmp.name)
                # Upload file using file path (latest Gemini API)
                gf = client.files.upload(file=tmp.name)
                gemini_files.append(gf)
                file_uris_for_prompt.append(
                    types.Part.from_uri(file_uri=gf.uri, mime_type=gf.mime_type)
                )
                st.write(f"Uploaded {uploaded_file.name} to Gemini.")

        # Prepare prompt parts
        prompt_parts = [
            *file_uris_for_prompt,
            types.Part.from_text(text="""These are PDF quotation files received by a company.
                                 \nInstructions:\n
                                 1. For each distinct product item listed in these documents, extract the following details.\n
                                 2. The 'sku_supplier' should be the name of the company providing the quotation (e.g., NARSINGH PHARMA, MEDIVISION, S. D. M. AGENCY).\n
                                 3. Extract the product name as 'sku_name' (e.g., PARACETAMOL 500MG TAB). \n
                                 If there are product names across the quotations with similar product names, they should be given a common sku_name and used in the output\
                                 Ex: (i) "GLUCONORM G 1" and "GLUCONORM G1" are the same product \n
                                     (ii) "JANUMET 50/500" and "JANUMET 50/500 TAB" are the same product\n
                                     (iii) "JUST TEAR E/D" and "JUST TEAR LUBRICANT E/D" are the same product\n
                                     (iv) "SEROFLO 250 R/C", "SEROFLO 250 ROTA" and "SEROFLO 250 ROTACAP" are the same product\n
                                     (v) "ATORVA 20MG TAB" and "ATORVA-20" are the same product\n
                                 etc.\n
                                 4. Ensure all numeric fields like MRP, Base Rate, and Discount are extracted as strings, exactly as they appear.\n
                                 5. Quantity ('qty_str') should be extracted as it appears (e.g., \"10+1\", \"20\").\n6. If a product appears in multiple documents, create a separate entry for each instance.\n
                                 Extract the data in the specified JSON schema including 'sku_name'."""),
        ]

        generate_content_config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=genai.types.Schema(
                type=genai.types.Type.OBJECT,
                properties={
                    "sku_data": genai.types.Schema(
                        type=genai.types.Type.ARRAY,
                        items=genai.types.Schema(
                            type=genai.types.Type.OBJECT,
                            properties={
                                "sku_supplier": genai.types.Schema(type=genai.types.Type.STRING),
                                "sku_invoice": genai.types.Schema(type=genai.types.Type.STRING),
                                "sku_name": genai.types.Schema(type=genai.types.Type.STRING),
                                "mrp": genai.types.Schema(type=genai.types.Type.STRING),
                                "base_rate": genai.types.Schema(type=genai.types.Type.STRING),
                                "base_discount_percent": genai.types.Schema(type=genai.types.Type.STRING),
                                "qty_str": genai.types.Schema(type=genai.types.Type.STRING),
                            },
                        ),
                    ),
                },
            ),
        )

        st.write("Sending request to Gemini for data extraction...")
        with st.spinner("Gemini is processing the documents... This may take a moment."):
            response_text = ""
            for chunk in client.models.generate_content_stream(
                model="gemini-2.0-flash",
                contents=[types.Content(role="user", parts=prompt_parts)],
                config=generate_content_config,
            ):
                response_text += chunk.text

        # Try to parse the JSON output
        try:
            json_data = json.loads(response_text)
            return json_data.get("sku_data", [])
        except json.JSONDecodeError as e:
            st.error(f"Error decoding JSON response from Gemini: {e}")
            st.text_area("Gemini Raw Response", response_text, height=200)
            return None
        except Exception as e:
            st.error(f"An unexpected error occurred while processing Gemini response: {e}")
            st.text_area("Gemini Raw Response", response_text, height=200)
            return None
    except Exception as e:
        st.error(f"An error occurred during Gemini processing: {e}")
        return None
    finally:
        # Clean up temp files
        for f in temp_files:
            try:
                os.remove(f)
            except Exception:
                pass


# --- SKU Comparison Logic (adapted from previous script) ---

def parse_quantity_string(qty_str):
    """Parses quantity string like '16+0', '15', '32+8' into (paid_qty, free_qty)."""
    if not qty_str: return 0, 0
    qty_str = str(qty_str).strip()
    match_plus = re.match(r'(\d+)\s*\+\s*(\d+)', qty_str)
    if match_plus:
        return int(match_plus.group(1)), int(match_plus.group(2))
    match_single = re.match(r'(\d+)', qty_str)
    if match_single:
        return int(match_single.group(1)), 0
    # st.warning(f"Could not parse quantity string: '{qty_str}', assuming 0 paid, 0 free.")
    return 0, 0 # Default if parsing fails

def calculate_item_metrics(base_rate, base_discount_percent, paid_qty, free_qty):
    if None in [base_rate, paid_qty, free_qty] or base_rate < 0: # base_discount_percent can be None (0%)
        return None, None, None
    
    base_discount_percent = base_discount_percent if base_discount_percent is not None else 0.0

    eff_rate_display = base_rate * (1 - base_discount_percent / 100.0)
    eff_disc_display = base_discount_percent

    if (paid_qty + free_qty) == 0:
        comparison_rate = float('inf') if paid_qty > 0 else 0.0
    else:
        total_cost_for_paid_items = paid_qty * eff_rate_display
        comparison_rate = total_cost_for_paid_items / (paid_qty + free_qty)
    
    return round(eff_rate_display, 2), round(eff_disc_display, 2), round(comparison_rate, 2)

def preprocess_data(raw_data_list):
    processed_items = []
    if not raw_data_list:
        return []
        
    for item in raw_data_list:
        sku_name = item.get("sku_name", "UNKNOWN_SKU_NAME").strip()
        sku_as_extracted = item.get("sku_invoice", "UNKNOWN_SKU").strip()
        paid_qty, free_qty = parse_quantity_string(item.get("qty_str"))

        try:
            # Convert string inputs from Gemini to float, handle missing discount
            mrp = float(item["mrp"]) if item.get("mrp") else 0.0
            base_rate = float(item["base_rate"]) if item.get("base_rate") else 0.0
            
            # Handle base_discount_percent: if missing or empty, treat as 0%
            discount_str = item.get("base_discount_percent", "0").strip()
            base_discount_percent = float(discount_str) if discount_str else 0.0

        except (ValueError, TypeError) as e:
            st.warning(f"Data conversion error for SKU '{sku_name}' from supplier '{item.get('sku_supplier', 'N/A')}': {e}. Skipping item.")
            continue
            
        if paid_qty == 0 and free_qty == 0:
            continue

        eff_rate_disp, eff_disc_disp, comparison_rate = calculate_item_metrics(
            base_rate, base_discount_percent, paid_qty, free_qty
        )

        processed_items.append({
            "supplier": item.get("sku_supplier", "UNKNOWN_SUPPLIER").strip(),
            "sku": sku_as_extracted, # Invoice code
            "sku_name": sku_name,    # Human readable name
            "mrp": mrp,
            "base_rate": base_rate,
            "paid_qty": paid_qty,
            "free_qty": free_qty,
            "qty_display_str": f"{paid_qty}+{free_qty}",
            "eff_rate_display_column": eff_rate_disp,
            "eff_disc_display_column": eff_disc_disp,
            "comparison_eff_rate": comparison_rate,
        })
    return processed_items

def get_supplier_unique_sku_counts(all_processed_items):
    supplier_skus = {}
    for item in all_processed_items:
        supplier = item["supplier"]
        sku = item["sku"] # Using raw SKU
        if supplier not in supplier_skus:
            supplier_skus[supplier] = set()
        supplier_skus[supplier].add(sku)
    return {supplier: len(skus) for supplier, skus in supplier_skus.items()}

def generate_comparison_table(target_sku_names, all_processed_items, display_suppliers_order):
    output_data_rows = []
    supplier_unique_counts = get_supplier_unique_sku_counts(all_processed_items)

    for sku_name in target_sku_names:
        row_dict = {('SKU Name', ''): sku_name}
        offers_for_this_sku = []

        for item in all_processed_items:
            if item["sku_name"] == sku_name: # Compare by sku_name
                offers_for_this_sku.append(item)
                if item["supplier"] in display_suppliers_order:
                    supplier_name = item["supplier"]
                    row_dict[(supplier_name, "MRP")] = f"{item['mrp']:.2f}" if item['mrp'] is not None else "-"
                    row_dict[(supplier_name, "Base Rate")] = f"{item['base_rate']:.2f}" if item['base_rate'] is not None else "-"
                    row_dict[(supplier_name, "Eff. Rate")] = f"{item['eff_rate_display_column']:.2f}" if item['eff_rate_display_column'] is not None else "-"
                    row_dict[(supplier_name, "Eff. Disc% ")] = f"{item['eff_disc_display_column']:.2f}" if item['eff_disc_display_column'] is not None else "-"
                    row_dict[(supplier_name, "Qty")] = item["qty_display_str"]
                    row_dict[(supplier_name, "SKU Code")] = item["sku"]
        for s_name in display_suppliers_order:
            if (s_name, "MRP") not in row_dict:
                for col_name in ["MRP", "Base Rate", "Eff. Rate", "Eff. Disc% ", "Qty", "SKU Code"]:
                    row_dict[(s_name, col_name)] = "-"

        best_deal_text = "-"
        if offers_for_this_sku:
            offers_for_this_sku.sort(key=lambda x: (
                x["comparison_eff_rate"] if x["comparison_eff_rate"] is not None else float('inf'),
                x["paid_qty"],
                -supplier_unique_counts.get(x["supplier"], 0)
            ))
            if offers_for_this_sku[0]["comparison_eff_rate"] is not None and offers_for_this_sku[0]["comparison_eff_rate"] != float('inf'):
                best_offer = offers_for_this_sku[0]
                best_deal_text = f"{best_offer['supplier']} ({best_offer['qty_display_str']})"
        row_dict[('Best Deal', '')] = best_deal_text
        output_data_rows.append(row_dict)

    if not output_data_rows:
        return pd.DataFrame()

    df = pd.DataFrame(output_data_rows)
    
    column_tuples = [('SKU Name', '')]
    for supplier_name in display_suppliers_order:
        column_tuples.extend([
            (supplier_name, "MRP"), (supplier_name, "Base Rate"),
            (supplier_name, "Eff. Rate"), (supplier_name, "Eff. Disc% "),
            (supplier_name, "Qty"), (supplier_name, "SKU Code")
        ])
    column_tuples.append(('Best Deal', ''))
    
    final_cols_index = pd.MultiIndex.from_tuples(column_tuples)
    df = df.reindex(columns=final_cols_index, fill_value="-")
    
    if not df.empty:
        df = df.set_index(('SKU Name', ''))
        df.index.name = "SKU Name"

    return df

# --- Streamlit App UI ---
st.set_page_config(layout="wide")
st.title("📄 SKU Quotation Comparator using Gemini AI ✨")

# Initialize session state
if 'extracted_data' not in st.session_state:
    st.session_state.extracted_data = None
if 'all_skus_from_pdfs' not in st.session_state:
    st.session_state.all_skus_from_pdfs = []
if 'selected_skus_for_comparison' not in st.session_state:
    st.session_state.selected_skus_for_comparison = []
if 'comparison_df' not in st.session_state:
    st.session_state.comparison_df = pd.DataFrame()

# --- Sidebar for File Upload and Controls ---
with st.sidebar:
    st.header("Upload Quotation PDFs")
    uploaded_files = st.file_uploader(
        "Choose PDF files", type="pdf", accept_multiple_files=True,
        help="Upload one or more PDF quotation files."
    )

    if uploaded_files:
        if st.button("1. Extract Data with Gemini", key="extract_button", type="primary"):
            st.session_state.extracted_data = None # Reset previous
            st.session_state.all_skus_from_pdfs = []
            st.session_state.selected_skus_for_comparison = []
            st.session_state.comparison_df = pd.DataFrame()

            extracted_json_data = run_gemini_extraction(uploaded_files)
            if extracted_json_data:
                st.session_state.extracted_data = extracted_json_data
                st.success(f"Successfully extracted data for {len(extracted_json_data)} items from Gemini!")
                
                # Populate unique SKU names for selection
                all_items = preprocess_data(st.session_state.extracted_data) # Preprocess to get clean SKUs and suppliers
                if all_items:
                    unique_sku_names = sorted(list(set(item['sku_name'] for item in all_items)))
                    st.session_state.all_skus_from_pdfs = unique_sku_names
                    # Preselect all SKUs after extraction
                    st.session_state.selected_skus_for_comparison = unique_sku_names.copy()
                else:
                    st.warning("No processable items found after initial parsing of Gemini data.")
            else:
                st.error("Failed to extract data using Gemini or no data returned.")
    else:
        st.info("Upload PDF files to begin.")

    if st.session_state.all_skus_from_pdfs:
        st.header("Select SKUs for Comparison")
        st.session_state.selected_skus_for_comparison = st.multiselect(
            "Choose SKUs to compare:",
            options=st.session_state.all_skus_from_pdfs,
            default=st.session_state.selected_skus_for_comparison, # Persist selection
            help="Select the SKUs you want to see in the comparison table. (SKU names only)"
        )

        if st.session_state.selected_skus_for_comparison:
            if st.button("2. Generate Comparison Table", key="compare_button"):
                if st.session_state.extracted_data:
                    processed_items = preprocess_data(st.session_state.extracted_data)
                    if processed_items:
                        # Determine dynamic supplier order for columns
                        unique_suppliers = sorted(list(set(item['supplier'] for item in processed_items)))
                        if not unique_suppliers:
                             st.warning("No suppliers found in the processed data.")
                             st.session_state.comparison_df = pd.DataFrame()
                        else:
                            st.session_state.comparison_df = generate_comparison_table(
                                st.session_state.selected_skus_for_comparison,
                                processed_items,
                                unique_suppliers # Dynamic supplier order
                            )
                            if st.session_state.comparison_df.empty:
                                st.warning("No data to display for the selected SKUs.")
                            else:
                                st.success("Comparison table generated!")
                    else:
                        st.error("No data available after preprocessing. Cannot generate comparison.")
                        st.session_state.comparison_df = pd.DataFrame()
                else:
                    st.error("No extracted data found. Please extract data first.")
                    st.session_state.comparison_df = pd.DataFrame()


# --- Main Area for Displaying Results ---
if st.session_state.extracted_data and not st.session_state.all_skus_from_pdfs and not uploaded_files:
    # This can happen if extraction was attempted but yielded no processable SKUs
    st.warning("Data was extracted by Gemini, but no SKUs could be identified for selection. Please check the raw data below or try with different/clearer PDFs.")


if not st.session_state.comparison_df.empty:
    st.subheader("SKU Comparison Table")
    st.dataframe(st.session_state.comparison_df, use_container_width=True)
    # Download as CSV button
    csv_buffer = BytesIO()
    st.session_state.comparison_df.to_csv(csv_buffer)
    csv_buffer.seek(0)
    st.download_button(
        label="Download Comparison as CSV",
        data=csv_buffer,
        file_name="sku_comparison_report.csv",
        mime="text/csv"
    )
    st.markdown("""
    **Calculation Notes:**
    *   **Effective Rate (for Best Deal Logic)** = (Paid Qty × (Base Rate × (1 - Supplier Base Discount%))) ÷ (Paid Qty + Free Qty)
    *   **Displayed 'Eff. Rate' Column** = Base Rate × (1 - Supplier Base Discount%)
    *   **Displayed 'Eff. Disc%' Column** = Supplier Base Discount%
    *   **Best Deal determined by:** 1) Lowest effective rate (for Best Deal logic), 2) Lower paid quantity requirement if rates equal, 3) Supplier with more unique products (across all extracted items) if both prior conditions are equal.
    *   All rates and MRP are typically shown to 2 decimal places.
    *   The 'Best Deal' column indicates the supplier and quantity scheme for the most favorable offer.
    """)
elif st.session_state.selected_skus_for_comparison and not st.session_state.extracted_data:
    st.warning("Please upload files and click 'Extract Data with Gemini' first.")


# Optional: Display Raw Extracted Data for debugging
if st.session_state.extracted_data:
    with st.expander("View Raw Extracted JSON Data from Gemini"):
        st.json(st.session_state.extracted_data)

st.markdown("---")
st.caption("Ensure your `GEMINI_API_KEY` environment variable is set for Gemini functionality.")