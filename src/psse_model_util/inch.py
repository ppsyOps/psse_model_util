"""Work in progress — not yet functional.

INCH/IDEV export support for PowerGEM TARA. This module is intended to translate
a :class:`~psse_model_util.compare.ModelComparison` into INCH (incremental
change) file records that TARA can apply to a base case. Roadmap phase 3.2.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from psse_model_util.compare import ModelComparison


@dataclass
class InchRecord:
    """A single INCH file record describing one change to a PSS/E model.

    Holds the INCH command, its field/value lists, and the corresponding RAWX
    section/field names so a model change can be rendered as INCH file text.

    Args:
        title: Optional descriptive title for this INCH record.
        command: The INCH file command recognized by PowerGEM TARA software.
        inch_fields: Valid INCH file field names.
        rawx_section: A valid RAWX section name, such as ``'bus'``, ``'acline'``,
            ``'generator'``, etc.
        rawx_fields: Corresponding ``model.Model.network`` DataFrame field names.
        template: Template section of the INCH file. Line 1 is a ``//`` comment,
            line 2 is ``#COMMAND`` followed by the CSV INCH field-name list, and
            line 3 is the CSV value list.
        values: CSV value list to include in ``inch_text``.
        inch_text: The rendered INCH file contents.
    """

    # Optional descriptive title for this INCH record.
    title: str = ''
    # command (str): the INCH file command recognized by PowerGEM TARA software.
    command: str = ''
    # inch_fields list[str]: valid INCH file field names
    inch_fields: List[str] = field(default_factory=list)
    # rawx_section (str): a valid section name in a RAWX file, such as 'bus',
    #                     'acline', 'generator', etc.
    rawx_section: str = ''
    # rawx_fields (list[str]): list of corresponding model.Model.network dataframe
    #                          field names
    rawx_fields: List[str] = field(default_factory=list)
    # template (str): template section of INCH file.
    #                 line 1: // comment
    #                 line 2: #COMMAND [csv INCH field name list]
    #                 line 3: csv value list
    # values (list): csv value list
    # inch_text (str): the INCH file contents
    template: str = ''
    # list of values to include in inch_text
    values: List[str] = field(default_factory=list)
    # actual text to include in the INCH file.
    inch_text: str = ''

    # TODO: replace inch_text with self._inch_text and creating
    #    and inch_text property that automatically populates _inch_text.


class Inch(object):
    """Builds an INCH/IDEV change set from a model comparison.

    Accumulates :class:`InchRecord` entries derived from a
    :class:`~psse_model_util.compare.ModelComparison` and renders them as an
    INCH file for PowerGEM TARA.

    Args:
        comparison: The model comparison whose differences drive the INCH
            records. May be ``None`` when records are added manually.
    """

    def __init__(self, comparison: ModelComparison = None):
        self.comparison: ModelComparison = comparison
        _records: list[InchRecord] = []

    def add_record(self, record: InchRecord):
        """Append an INCH record to this change set.

        Args:
            record: The INCH record to add.
        """
        assert isinstance(record, InchRecord)
        self._records += [record]

    def del_record(self, loc: int):
        """Remove an INCH record from this change set.

        Args:
            loc: Position of the record to remove.
        """
        assert isinstance(loc, int)
        self._records.remove(loc)

    def add_bus(self, bus_id: int, direction: str = '2to1'):
        """Add an INCH record that creates a bus from the comparison.

        Args:
            bus_id: Model (RAW file) bus number.
            direction: Model comparison direction. One of ``'2to1'`` or
                ``'1to2'``.
        """
        # TODO: write code for add_bus
        assert isinstance(self.comparison, ModelComparison) and self.comparison is not None
        df = self.comparison.network_df_comparison['bus']
        _ = df[df['bus_id'] == bus_id].to_dict('records')[0]
        ...

    def modify_bus(self, bus_id):
        """Add an INCH record that modifies an existing bus.

        Args:
            bus_id: Model (RAW file) bus number to modify.
        """
        # TODO: write code
        assert isinstance(self.comparison, ModelComparison) and self.comparison is not None
        ...

    def modify_bus_number(self, bus_id):
        """Add an INCH record that renumbers an existing bus.

        Args:
            bus_id: Model (RAW file) bus number to renumber.
        """
        # TODO: write code
        assert isinstance(self.comparison, ModelComparison) and self.comparison is not None
        ...

    def del_bus(self, bus_id):
        """Add an INCH record that deletes an existing bus.

        Args:
            bus_id: Model (RAW file) bus number to delete.
        """
        # TODO: write code
        assert isinstance(self.comparison, ModelComparison) and self.comparison is not None
        ...

    def to_inch(self, filepath: Path | str) -> tuple[Path, str]:
        """Write the INCH records to a file.

        Args:
            filepath: Where to write the INCH file.

        Returns:
            A tuple of the filepath written and the file content.
        """
        # TODO: write the inch records to a file.
        ...

