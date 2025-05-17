import pandas as pd
import re
from typing import List, Dict, Any, Optional
from models import ProcessedSkuItem # Import the data model

# --- SKU Comparison Logic (adapted from previous script) ---

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

    for sku_name in target_sku_names:
        row_dict = {('SKU Name', ''): sku_name}
        offers_for_this_sku = []

        for item in all_processed_items:
            if item.sku_name == sku_name: # Compare by sku_name
                offers_for_this_sku.append(item)
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
            (supplier_name, "Qty"), (supplier_name, "SKU Code"), (supplier_name, "Batch Number"), # Add Batch Number column tuple
            (supplier_name, "Calc. Rate/Qty") # Add Calculated Rate/Qty column tuple
        ])
    column_tuples.append(('Best Deal', ''))

    final_cols_index = pd.MultiIndex.from_tuples(column_tuples)
    df = df.reindex(columns=final_cols_index, fill_value="-")

    if not df.empty:
        df = df.set_index(('SKU Name', ''))
        df.index.name = "SKU Name"

    return df