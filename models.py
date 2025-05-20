from dataclasses import dataclass, field
from typing import Optional

@dataclass
class RawSkuItem:
    """Represents the raw data extracted directly from the Gemini API."""
    sku_supplier: Optional[str] = None
    sku_invoice: Optional[str] = None
    sku_name: Optional[str] = None
    mrp: Optional[str] = None
    base_rate: Optional[str] = None
    base_discount_percent: Optional[str] = None
    qty_str: Optional[str] = None
    paid_qty: Optional[int] = None
    free_qty: Optional[int] = None
    batch_number: Optional[str] = None
    amount: Optional[int] = None

@dataclass
class ProcessedSkuItem:
    """Represents a processed SKU item with calculated metrics."""
    supplier: str
    sku: str # Invoice code
    sku_name: str # Human readable name
    mrp: float
    base_rate: float
    paid_qty: int
    free_qty: int
    qty_display_str: str
    eff_rate_display_column: Optional[float] = None
    eff_disc_display_column: Optional[float] = None
    comparison_eff_rate: Optional[float] = None
    calculated_rate_per_qty: Optional[float] = None
    batch_number: str = "N/A"