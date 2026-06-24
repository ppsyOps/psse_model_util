"""Typed per-section schema metadata for network DataFrames.

Replaces the legacy ``df._metadata`` dict. Instances are held in
``Network._section_schemas`` keyed by section name, never on the DataFrame.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class SectionSchema:
    """Schema metadata for one network section.

    Attributes:
        id_cols: Columns forming the unique-equipment index.
        bus_cols: Columns holding bus numbers.
        data_type: Per-column dtype hints, ``{column_name: type}``.
    """

    id_cols: tuple[str, ...] = ()
    bus_cols: tuple[str, ...] = ()
    data_type: Mapping[str, type] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Coerce list/sequence inputs to tuples without breaking frozen-ness.
        object.__setattr__(self, "id_cols", tuple(self.id_cols))
        object.__setattr__(self, "bus_cols", tuple(self.bus_cols))
        object.__setattr__(self, "data_type", dict(self.data_type))

    @classmethod
    def from_template(cls, template: Mapping[str, Any], fields: Sequence[str]) -> "SectionSchema":
        """Build a schema from a ``rawx_json_template['network'][section]`` entry.

        ``data_type`` in the template is a list aligned to the template's fields;
        it is zipped against the *actual* ``fields`` of the parsed DataFrame
        (mirroring the legacy ``_create_dataframe`` behavior, including
        zip-truncation when lengths differ).
        """
        raw_dt = template.get("data_type", [])
        data_type = dict(raw_dt) if isinstance(raw_dt, dict) else dict(zip(fields, raw_dt))
        return cls(
            id_cols=tuple(template.get("id_cols", ())),
            bus_cols=tuple(template.get("bus_cols", ())),
            data_type=data_type,
        )
