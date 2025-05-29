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

from pydantic import BaseModel, Field
from typing import List

class SkuNameMapping(BaseModel):
    """Represents a mapping from an original SKU name to its normalized form."""
    original_sku_name: str = Field(description="The original SKU name extracted from the document")
    normalized_sku_name: str = Field(description='''The canonical or deduplicated form of the SKU name  
                                  Ex: (i) "GLUCONORM G 1" and "GLUCONORM G1" are the same product \n
                                      (ii) "JANUMET 50/500" and "JANUMET 50/500 TAB" are the same product\n
                                      (iii) "JUST TEAR E/D" and "JUST TEAR LUBRICANT E/D" are the same product\n
                                      (iv) "SEROFLO 250 R/C", "SEROFLO 250 ROTA" and "SEROFLO 250 ROTACAP" are the same product\n
                                      (v) "ATORVA 20MG TAB" and "ATORVA-20" are the same product\n''')

class BatchSkuNameNormalization(BaseModel):
    """Represents a batch of SKU name normalizations, mapping multiple original names to their canonical forms."""
    mappings: List[SkuNameMapping] = Field(description="List of SKU name normalizations")
