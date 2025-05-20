# Implementation Plan: Extract Amount and Calculate Rate Per Quantity

## Objective

Enhance the SKU Quotation Comparator application to extract the 'total price for the listed quantity' (referred to as 'amount') from the Gemini AI response, calculate a 'calculated_rate_per_qty' based on this amount and the total quantity (free + paid), display this new rate in the output comparison table, and use it as the primary metric for determining the best deal for each SKU.

## Plan

1.  **Update Data Models (`models.py`)**:
    *   Add an `amount: Optional[int] = None` field to the `RawSkuItem` dataclass to store the raw extracted amount as an integer.
    *   Add a `calculated_rate_per_qty: Optional[float] = None` field to the `ProcessedSkuItem` dataclass to store the calculated rate per quantity.

2.  **Modify Gemini Extraction (`gemini_service.py`)**:
    *   Update the prompt text within the `run_gemini_extraction` function to explicitly instruct Gemini to extract the "total price for the listed quantity" and label this extracted value as 'amount'.
    *   Modify the `response_schema` within the `generate_content_config` to include an 'amount' property with the type `genai.types.Type.INTEGER`.

3.  **Implement Calculation and Update Comparison Logic (`sku_processing.py`)**:
    *   In the function responsible for transforming `RawSkuItem` objects into `ProcessedSkuItem` objects, access the new `amount` field from the `RawSkuItem`.
    *   Calculate the total quantity for each item: `total_qty = paid_qty + free_qty`.
    *   Calculate the `calculated_rate_per_qty`:
        *   If `total_qty` is greater than 0, compute `calculated_rate_per_qty = amount / total_qty`.
        *   If `total_qty` is 0, set `calculated_rate_per_qty` to `None` to indicate that a rate cannot be calculated.
    *   Populate the `calculated_rate_per_qty` field in the corresponding `ProcessedSkuItem` object.
    *   Locate and modify the logic that determines the "best deal" for each unique SKU. This logic currently uses the `comparison_eff_rate`. Change this logic to use the `calculated_rate_per_qty` field instead. The best deal for a given SKU will be the `ProcessedSkuItem` with the minimum `calculated_rate_per_qty`. Ensure the logic correctly handles items where `calculated_rate_per_qty` is `None` (these should not be considered the best deal).
    *   Modify the function that constructs the final pandas DataFrame for the comparison table to include a new column displaying the 'calculated_rate_per_qty'.

4.  **Update UI Display (`ui_components.py` or `app.py`)**:
    *   Adjust the code that renders the comparison table (likely within `ui_components.py`) to include the newly added 'calculated_rate_per_qty' column.
    *   Apply appropriate formatting to the 'calculated_rate_per_qty' column for display (e.g., currency format, two decimal places).
    *   Update any conditional styling or highlighting applied to the comparison table to correctly identify and visually mark the "best deal" based on the minimum value in the 'calculated_rate_per_qty' column.

## Updated Data Flow

```mermaid
graph TD
    User -- Uploads PDFs --> App[app.py - Streamlit Orchestrator]
    App -- Calls --> GeminiService[gemini_service.py - Gemini API Interaction]
    GeminiService -- Returns Raw Data (incl. amount) --> App
    App -- Passes Raw Data --> SkuProcessing[sku_processing.py - Data Processing & Comparison]
    SkuProcessing -- Calculates calculated_rate_per_qty --> SkuProcessing
    SkuProcessing -- Determines Best Deal (using calculated_rate_per_qty) --> SkuProcessing
    SkuProcessing -- Returns Processed Data (incl. calculated_rate_per_qty) & SKUs --> App
    App -- Calls --> UIComponents[ui_components.py - UI Rendering Functions]
    UIComponents -- Renders UI & Handles Input --> User
    App -- Passes Data & Handlers --> UIComponents
    SkuProcessing -- Uses --> Models[models.py - Data Structures]
    GeminiService -- Uses --> Models