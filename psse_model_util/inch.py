"""
docstring for inch.py
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from psse_model_util.compare import ModelComparison
from psse_model_util.dataformat.inch_templates import INCH_TEMPLATE


@dataclass
class InchRecord:
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
    def __init__(self, comparison: ModelComparison = None):
        """
        docstring for Inch
        """
        self.comparison: ModelComparison = comparison
        _records: list[InchRecord] = []

    def add_record(self, record: InchRecord):
        assert isinstance(record, InchRecord)
        self._records += [record]

    def del_record(self, loc: int):
        assert isinstance(loc, int)
        self._records.remove(loc)

    def add_bus(self, bus_id: int, direction: str = '2to1'):
        """

        :param bus_id: Model (RAW file) bus number
        :param direction: Model comparison direction
                          Default: '2to1'
                          Options: '2to1' or '1to2'
        :return:
        """
        # TODO: write code for add_bus
        assert isinstance(self.comparison, ModelComparison) and self.comparison is not None
        df = self.comparison.network_df_comparison['bus']
        bus = df[df['bus_id'] == bus_id].to_dict('records')[0]
        ...

    def modify_bus(self, bus_id):
        # TODO: write code
        assert isinstance(self.comparison, ModelComparison) and self.comparison is not None
        ...

    def modify_bus_number(self, bus_id):
        # TODO: write code
        assert isinstance(self.comparison, ModelComparison) and self.comparison is not None
        ...

    def del_bus(self, bus_id):
        # TODO: write code
        assert isinstance(self.comparison, ModelComparison) and self.comparison is not None
        ...

    def to_inch(self, filepath: Path | str) -> tuple[Path, str]:
        """
        Write the inch records to a file
        :param filepath: Path | str where to write the INCH file.
        :return: tuple[Path, str] of the filepath written and the file content.
        """
        # TODO: write the inch records to a file.
        ...

