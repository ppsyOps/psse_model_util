"""Data-format definitions for PSS/E models.

This subpackage holds the schema and domain types that drive parsing and
materialization:

* :mod:`~psse_model_util.dataformat.rawx_json_template` — the RAWX section
  schema (per-section ``fields``, ``data_type``, ``id_cols``, and ``bus_cols``).
* :mod:`~psse_model_util.dataformat.classes` — domain quantity types (voltage,
  reactance, etc.), dict/dataclass helpers, and the metadata-carrying
  ``ModelDF`` DataFrame subclass.
* :mod:`~psse_model_util.dataformat.inch_templates` — INCH-format templates.
"""
