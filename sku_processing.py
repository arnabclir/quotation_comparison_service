import pandas as pd
import re
from typing import List, Dict, Any, Optional
from models import ProcessedSkuItem, SkuNameMapping, BatchSkuNameNormalization # Import the data model
import instructor
import openai # openai is a dependency of instructor
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def calculate_item_metrics(base_rate: Optional[float], base_discount_percent: Optional[float], paid_qty: int, free_qty: int) -> tuple[Optional[float], Optional[float], Optional[float]]:
    """Calculates effective rate, effective discount, and comparison rate."""
    if base_rate is None or base_rate < 0 or paid_qty is None or free_qty is None:
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

def preprocess_data(raw_data_list: List[Dict[str, Any]]) -> List[ProcessedSkuItem]:
    """
    Processes raw data extracted from Gemini into a list of ProcessedSkuItem objects.
    Handles data conversion and basic validation.
    """
    processed_items = []
    if not raw_data_list:
        return []
        
    for item in raw_data_list:
        # Use .get() with default values for robustness
        sku_name = item.get("sku_name", "UNKNOWN_SKU_NAME").strip()
        sku_as_extracted = item.get("sku_invoice", "UNKNOWN_SKU").strip()

        # Get paid_qty and free_qty directly from raw data, with error handling and logging
        paid_qty = item.get("paid_qty")
        free_qty = item.get("free_qty")

        if paid_qty is None or free_qty is None:
             logging.warning(f"Missing paid_qty or free_qty for SKU '{sku_name}' from supplier '{item.get('sku_supplier', 'N/A')}'. Skipping item.")
             continue

        try:
            paid_qty = int(paid_qty)
            free_qty = int(free_qty)
        except (ValueError, TypeError) as e:
            logging.warning(f"Invalid paid_qty or free_qty (not integers) for SKU '{sku_name}' from supplier '{item.get('sku_supplier', 'N/A')}': {e}. Skipping item.")
            continue

        try:
            # Convert string inputs from Gemini to float, handle missing discount
            mrp_str = item.get("mrp")
            base_rate_str = item.get("base_rate")
            discount_str = item.get("base_discount_percent", "0").strip() # Default to "0" if missing

            mrp = float(mrp_str) if mrp_str else 0.0
            base_rate = float(base_rate_str) if base_rate_str else 0.0
            base_discount_percent = float(discount_str) if discount_str else 0.0

        except (ValueError, TypeError) as e:
            logging.warning(f"Data conversion error for SKU '{sku_name}' from supplier '{item.get('sku_supplier', 'N/A')}': {e}. Skipping item.")
            continue

        if paid_qty == 0 and free_qty == 0:
            logging.info(f"Skipping item for SKU '{sku_name}' from supplier '{item.get('sku_supplier', 'N/A')}' as both paid_qty and free_qty are zero.")
            continue

        # Get amount and calculate calculated_rate_per_qty
        amount = item.get("amount")
        calculated_rate_per_qty = None
        total_qty = paid_qty + free_qty

        if amount is not None and total_qty > 0:
            try:
                calculated_rate_per_qty = float(amount) / total_qty
            except (ValueError, TypeError) as e:
                logging.warning(f"Invalid amount or quantity for rate calculation for SKU '{sku_name}' from supplier '{item.get('sku_supplier', 'N/A')}': {e}")
                calculated_rate_per_qty = None # Ensure it's None on error

        # Calculate existing metrics (Eff. Rate, Eff. Disc, Comparison Eff. Rate)
        eff_rate_disp, eff_disc_disp, comparison_rate = calculate_item_metrics(
            base_rate, base_discount_percent, paid_qty, free_qty
        )

        processed_items.append(ProcessedSkuItem(
            supplier=item.get("sku_supplier", "UNKNOWN_SUPPLIER").strip(),
            sku=sku_as_extracted, # Invoice code
            sku_name=sku_name,    # Human readable name
            mrp=mrp,
            base_rate=base_rate,
            paid_qty=paid_qty,
            free_qty=free_qty,
            qty_display_str=f"{paid_qty}+{free_qty}", # Keep display string format
            eff_rate_display_column=eff_rate_disp,
            eff_disc_display_column=eff_disc_disp,
            comparison_eff_rate=comparison_rate, # Keep for now, will remove later
            calculated_rate_per_qty=calculated_rate_per_qty, # Add the new calculated rate
            batch_number=item.get("batch_number", "N/A").strip(), # Include batch number
        ))
    logging.info(f"Successfully processed {len(processed_items)} SKU items.")
    return processed_items

def get_supplier_unique_sku_counts(all_processed_items: List[ProcessedSkuItem]) -> Dict[str, int]:
    """Calculates the number of unique SKUs per supplier based on raw SKU code."""
    supplier_skus = {}
    for item in all_processed_items:
        supplier = item.supplier
        sku = item.sku # Using raw SKU
        if supplier not in supplier_skus:
            supplier_skus[supplier] = set()
        supplier_skus[supplier].add(sku)
    return {supplier: len(skus) for supplier, skus in supplier_skus.items()}

def generate_comparison_table(target_sku_names: List[str], all_processed_items: List[ProcessedSkuItem], display_suppliers_order: List[str]) -> pd.DataFrame:
    """Generates a pandas DataFrame for the SKU comparison table."""
    output_data_rows = []
    supplier_unique_counts = get_supplier_unique_sku_counts(all_processed_items)

    for sku_name in target_sku_names: # sku_name is now the normalized name
        row_dict = {('SKU Name', ''): sku_name}
        offers_for_this_sku = []
        original_sku_codes_for_this_normalized_name = set() # Use a set to store unique original codes

        for item in all_processed_items:
            if item.sku_name == sku_name: # item.sku_name is already normalized
                offers_for_this_sku.append(item)
                if item.sku: # Ensure item.sku is not None or empty before adding
                    original_sku_codes_for_this_normalized_name.add(item.sku) # item.sku is the original invoice code
                if item.supplier in display_suppliers_order:
                    supplier_name = item.supplier
                    row_dict[(supplier_name, "MRP")] = f"{item.mrp:.2f}" if item.mrp is not None else "-"
                    row_dict[(supplier_name, "Base Rate")] = f"{item.base_rate:.2f}" if item.base_rate is not None else "-"
                    row_dict[(supplier_name, "Eff. Rate")] = f"{item.eff_rate_display_column:.2f}" if item.eff_rate_display_column is not None else "-"
                    row_dict[(supplier_name, "Eff. Disc% ")] = f"{item.eff_disc_display_column:.2f} %" if item.eff_disc_display_column is not None else "-" # Format with %
                    row_dict[(supplier_name, "Qty")] = item.qty_display_str
                    row_dict[(supplier_name, "SKU Code")] = item.sku
                    row_dict[(supplier_name, "Batch Number")] = item.batch_number # Add Batch Number
                    row_dict[(supplier_name, "Calc. Rate/Qty")] = f"{item.calculated_rate_per_qty:.2f}" if item.calculated_rate_per_qty is not None else "-" # Add Calculated Rate/Qty
        for s_name in display_suppliers_order:
            if (s_name, "MRP") not in row_dict:
                for col_name in ["MRP", "Base Rate", "Eff. Rate", "Eff. Disc% ", "Qty", "SKU Code", "Batch Number", "Calc. Rate/Qty"]: # Add Calculated Rate/Qty here too
                    row_dict[(s_name, col_name)] = "-"

        best_deal_text = "-"
        if offers_for_this_sku:
            # Sort by calculated_rate_per_qty (ascending), then paid_qty (ascending), then supplier unique count (desc)
            # Treat None calculated_rate_per_qty as the worst (highest value)
            offers_for_this_sku.sort(key=lambda x: (
                x.calculated_rate_per_qty if x.calculated_rate_per_qty is not None else float('inf'),
                x.paid_qty,
                -supplier_unique_counts.get(x.supplier, 0)
            ))
            # Check if the best offer has a valid calculated_rate_per_qty
            if offers_for_this_sku[0].calculated_rate_per_qty is not None:
                best_offer = offers_for_this_sku[0]
                best_deal_text = f"{best_offer.supplier}" # Update Best Deal text to only show supplier
        
        # After processing all items for this sku_name:
        row_dict[('Original SKUs', '')] = ", ".join(sorted(list(original_sku_codes_for_this_normalized_name)))

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
            (supplier_name, "Qty"), (supplier_name, "SKU Code"), (supplier_name, "Batch Number"), 
            (supplier_name, "Calc. Rate/Qty") 
        ])
    column_tuples.append(('Original SKUs', '')) # Add the new column header
    column_tuples.append(('Best Deal', ''))

    final_cols_index = pd.MultiIndex.from_tuples(column_tuples)
    df = df.reindex(columns=final_cols_index, fill_value="-")

    if not df.empty:
        df = df.set_index(('SKU Name', ''))
        df.index.name = "SKU Name"

    return df

def normalize_sku_names(sku_names: List[str], client: instructor.Instructor) -> Dict[str, str]:
    """
    Normalizes a list of SKU names using an LLM call via the instructor library.

    Args:
        sku_names: A list of original SKU names.
        client: An initialized instructor client (e.g., from OpenAI, Gemini, or another provider).
                The client should be pre-configured with the desired model.

    Returns:
        A dictionary mapping original SKU names to their normalized forms.
        Returns a dictionary mapping original names to themselves if normalization fails or sku_names is empty.
    """
    if not sku_names:
        logging.info("normalize_sku_names: Received empty list of SKU names.")
        return {}

    # Process unique SKU names to avoid redundant calls and simplify LLM's task
    unique_sku_names = sorted(list(set(sku_names)))
    
    prompt = f"""
    You are an expert in pharmaceutical and FMCG product catalog management.
    Your task is to normalize a list of SKU names. This means identifying SKUs
    that refer to the same product despite minor variations in naming, dosage,
    packaging, or brand names, and mapping them to a single, canonical/normalized name.

    Consider the following aspects for normalization:
    - Dosage information (e.g., "10mg", "500 MG", "0.5ML")
    - Packaging type (e.g., "TAB", "TABLET", "CAP", "CAPSULE", "SYRUP", "INJ", "VIAL", "AMP")
    - Brand variations vs. generic names (e.g., "Crocin" vs "Paracetamol", "PAN 40" vs "Pantoprazole 40mg")
    - Minor spelling differences or abbreviations (e.g., "Vit" vs "Vitamin")
    - Order of words (e.g., "XYZ 10ML SYP" vs "SYP XYZ 10ML")
    - Include strength/volume even if the unit (mg/ml) is part of the name. E.g., "Test Syrup 100ml" -> "Test Syrup 100ml"

    The goal is to group similar items under a consistent name.
    For the normalized name, choose the most common, most complete, or a widely recognized generic/medical name.
    If an item has multiple variations (e.g. "BrandX 10mg Tab" and "BrandX 10mg Tablet"), normalize them to one form (e.g. "BrandX 10mg Tablet").
    If a generic name is appropriate and covers multiple brands, use that. E.g. "Pan 40mg Tab" and "Pantosec 40mg Tab" could both map to "Pantoprazole 40mg Tablet".
    Ensure that the casing and spacing are consistent in the normalized output. For example, "PAN 40MG TAB" and "PAN 40 Mg Tablet" should map to a single form like "PANTOPRAZOLE 40MG TABLET".

    Example Input List:
    [
        "PAN 40MG TAB",
        "PAN 40 MG TABLET",
        "PANTOSEC 40MG",
        "CALPOL 500MG",
        "CALPOL 500 TAB",
        "CROCIN ADVANCE TAB",
        "PARACETAMOL 500MG TAB",
        "Azithromycin 250",
        "AZITHRAL 250 TAB",
        "AMOXYCLAV 625MG TAB",
        "MOXIKIND CV 625"
    ]

    Desired Output Mappings (map original SKU name to normalized SKU name):
    - "PAN 40MG TAB" -> "PANTOPRAZOLE 40MG TABLET"
    - "PAN 40 MG TABLET" -> "PANTOPRAZOLE 40MG TABLET"
    - "PANTOSEC 40MG" -> "PANTOPRAZOLE 40MG TABLET"
    - "CALPOL 500MG" -> "CALPOL 500MG TABLET"
    - "CALPOL 500 TAB" -> "CALPOL 500MG TABLET"
    - "CROCIN ADVANCE TAB" -> "PARACETAMOL 500MG TABLET"
    - "PARACETAMOL 500MG TAB" -> "PARACETAMOL 500MG TABLET"
    - "Azithromycin 250" -> "AZITHROMYCIN 250MG TABLET" 
    - "AZITHRAL 250 TAB" -> "AZITHROMYCIN 250MG TABLET"
    - "AMOXYCLAV 625MG TAB" -> "AMOXICILLIN-CLAVULANATE 625MG TABLET"
    - "MOXIKIND CV 625" -> "AMOXICILLIN-CLAVULANATE 625MG TABLET"

    Please process the following list of SKU names and return the normalization mappings.
    Ensure every original SKU name provided in the input list below has a corresponding mapping in your output.
    Input SKU List:
    {unique_sku_names}
    """

    try:
        logging.info(f"normalize_sku_names: Sending {len(unique_sku_names)} unique SKU names for normalization (original list had {len(sku_names)} items).")
        
        response: BatchSkuNameNormalization = client.chat.completions.create(
            model = "qwen/qwen3-235b-a22b-07-25",
            messages=[{"role": "user", "content": prompt}],
            response_model=BatchSkuNameNormalization,
            # The 'model' parameter is typically set during client initialization or if the client is multi-model.
            # e.g., model="gemini-1.5-flash-latest" or specific OpenAI/Qwen model name.
        )

        # Process the response, which contains mappings for unique_sku_names
        temp_normalized_map = {}
        if response and response.mappings:
            for mapping in response.mappings:
                # Ensure the original name from the mapping is one we sent
                if mapping.original_sku_name in unique_sku_names:
                    temp_normalized_map[mapping.original_sku_name] = mapping.normalized_sku_name
            logging.info(f"normalize_sku_names: Received {len(temp_normalized_map)} valid mappings from LLM for {len(unique_sku_names)} unique SKUs.")
        else:
            logging.warning("normalize_sku_names: Normalization API call returned no mappings or an empty/invalid response.")

        # Create the final map that maps all original SKU names (including duplicates)
        # to their normalized form. If a unique SKU wasn't in the LLM response,
        # or if normalization failed, it defaults to its original name.
        final_sku_map = {}
        for original_name in sku_names:
            # Get the normalized name for its unique form, or default to original_name itself
            # if its unique form wasn't mapped or if the unique form is the original_name.
            normalized_name = temp_normalized_map.get(original_name, original_name)
            final_sku_map[original_name] = normalized_name
        
        logging.info(f"normalize_sku_names: Final map contains {len(final_sku_map)} items, mapping all original SKUs.")
        return final_sku_map

    except Exception as e:
        logging.error(f"normalize_sku_names: Error during SKU name normalization: {e}", exc_info=True)
        # In case of any error, return a dict mapping all original names to themselves
        return {name: name for name in sku_names}