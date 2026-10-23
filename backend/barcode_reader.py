"""Compatibility shim during the refactor — barcodes are integrations/imaging/barcode.py. Removed in its last step."""

from integrations.imaging.barcode import scan_image, scan_pil_image  # noqa: F401
