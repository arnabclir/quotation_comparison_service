import pandas as pd
import re
from typing import List, Dict, Any, Optional
from models import ProcessedSkuItem # Import the data model

# --- SKU Comparison Logic (adapted from previous script) ---

def parse_quantity_string(qty_str: Optional[str]) -> tuple[int, int]:
    """Parses quantity string like '16+0', '15', '32+8' into (paid_qty, free_qty)."""
    if not qty_str: return 0, 0
    qty_str = str(qty_str).strip()
    match_plus = re.match(r'(\d+)\s*\+\s*(\d+)', qty_str)
    if match_plus:
        return int(match_plus.group(1)), int(match_plus.group(2))
    match_single = re.match(r'(\d+)', qty_str)
    if match_single:
        return int(match_single.group(1)), 0
    # Note: Streamlit warnings removed as this is a backend processing module
    return 0, 0 # Default if parsing fails

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
        qty_str = item.get("qty_str")
        paid_qty, free_qty = parse_quantity_string(qty_str)

        try:
            # Convert string inputs from Gemini to float, handle missing discount
            mrp_str = item.get("mrp")
            base_rate_str = item.get("base_rate")
            discount_str = item.get("base_discount_percent", "0").strip() # Default to "0" if missing

            mrp = float(mrp_str) if mrp_str else 0.0
            base_rate = float(base_rate_str) if base_rate_str else 0.0
            base_discount_percent = float(discount_str) if discount_str else 0.0

        except (ValueError, TypeError) as e:
            # Note: Streamlit warnings removed, consider logging or alternative error handling
            print(f"Data conversion error for SKU '{sku_name}' from supplier '{item.get('sku_supplier', 'N/A')}': {e}. Skipping item.")
            continue
            
        if paid_qty == 0 and free_qty == 0:
            continue

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
            qty_display_str=f"{paid_qty}+{free_qty}",
            eff_rate_display_column=eff_rate_disp,
            eff_disc_display_column=eff_disc_disp,
            comparison_eff_rate=comparison_rate,
            batch_number=item.get("batch_number", "N/A").strip(), # Include batch number
        ))
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
        for s_name in display_suppliers_order:
            if (s_name, "MRP") not in row_dict:
                for col_name in ["MRP", "Base Rate", "Eff. Rate", "Eff. Disc% ", "Qty", "SKU Code", "Batch Number"]: # Add Batch Number here too
                    row_dict[(s_name, col_name)] = "-"

        best_deal_text = "-"
        if offers_for_this_sku:
            # Sort by comparison_eff_rate, then paid_qty, then supplier unique count (desc)
            offers_for_this_sku.sort(key=lambda x: (
                x.comparison_eff_rate if x.comparison_eff_rate is not None else float('inf'),
                x.paid_qty,
                -supplier_unique_counts.get(x.supplier, 0)
            ))
            if offers_for_this_sku[0].comparison_eff_rate is not None and offers_for_this_sku[0].comparison_eff_rate != float('inf'):
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
            (supplier_name, "Qty"), (supplier_name, "SKU Code"), (supplier_name, "Batch Number") # Add Batch Number column tuple
        ])
    column_tuples.append(('Best Deal', ''))

    final_cols_index = pd.MultiIndex.from_tuples(column_tuples)
    df = df.reindex(columns=final_cols_index, fill_value="-")

    if not df.empty:
        df = df.set_index(('SKU Name', ''))
        df.index.name = "SKU Name"

    return df