"""Contingency File Processing and Network Model Validation Module.

This module provides utilities for processing power system contingency definitions,
validating network components against a PSS/E RAW file model, and generating
area-specific contingency files with quality separation.

Key Functionality:
1. Network model initialization from PSS/E RAW files
2. Contingency validation (component existence checks)
3. Voltage-level filtering with keyword exceptions
4. Area-based file generation with good/bad contingency separation

Input/Output:
- Input:
  - Directory of .con contingency definition files
  - PSS/E RAW network file
- Output:
  - Consolidated CSV files of processed contingencies
  - Area-specific .con files with validation metadata
  - Detailed reports of invalid contingencies

Example Usage:
    >>> from psse_model_util.util.contingency_util import create_area_con_files
    >>> create_area_con_files(
            raw_file="network.raw",
            input_folder="contingencies",
            output_folder="output"
        )
    Processing 42 contingencies...
    Generated 5 area files in 'output'
"""

print('Loading code (contingency_util.py)...')
print('    Starting imports...')
# Standard library imports
import os  # noqa: E402
import re  # noqa: E402
import shutil  # noqa: E402
import warnings  # noqa: E402
from collections import namedtuple  # noqa: E402
from itertools import chain, permutations  # noqa: E402

# from datetime import datetime as dtdt
from pathlib import Path  # noqa: E402

# Third-party imports
import pandas as pd  # noqa: E402

from psse_model_util import Model  # noqa: E402

# Local imports
from psse_model_util.common.logging_config import get_log_file_path, setup_logger  # noqa: E402

print('    Starting logger...')
logger = setup_logger("contingency_util")

logger.debug('    Loading functions...')

# Default file system paths for contingency processing
BASE_FOLDER: str = r'K:\panc\contingencies'
DEFAULT_INPUT_FOLDER: str = BASE_FOLDER + r'\input'  # Place all input files here, including exactly one raw file.
DEFAULT_OUTPUT_FOLDER: str = BASE_FOLDER + r'\test_output'

# Voltage filtering parameters (kV thresholds)
# Contingencies with components outside this range are filtered out
# unless they contain keywords from KV_EXCEPTIONS
KV_FILTER: tuple[int, int] = 138, 160  # (min_kv, max_kv)

# Component type keywords that bypass voltage filtering
# Contingencies containing these strings are always processed
# regardless of voltage levels (preserves critical load/generation contingencies)
KV_EXCEPTIONS: tuple[str, str] = 'MACHINE', 'LOAD'

# Folder containing files from which to read contingencies
CONTINGENCY_DEFINITIONS_FOLDER: str = r'K:\panc\contingencies\contingencies'

# Regex pattern for extracting bus numbers from contingency definitions
# Matches: 'BUS' followed by exactly 6 digits
BUS_REGEX_PATTERN: str = r'\s*BUS\s*\d{6,6}'
# Regex patterns for parsing contingency definitions
BRANCH_PATTERN: str = r'FROM\s+BUS\s+(\d+)\s+TO\s+BUS\s+(\d+)\s+CKT\s+[\"\']?(\w+)[\"\']?'
TRANSFORMER_PATTERN: str = r'\s+BUS\s+(\d+)\s+TO\s+BUS\s+(\d+)\s+TO\s+BUS\s+(\d+)\s+CKT\s+[\"\']?(\w+)[\"\']?'
GEN_PATTERN: str = r'\s+MACHINE\s+([\w\s]+?)\s+FROM\s+BUS\s+(\d+)'
LOAD_PATTERN: str = r'\s+LOAD\s+([\w\s]+?)\s+FROM\s+BUS\s+(\d+)'
CONTINGENCY_DEFINITION_PATTERN: str = r'CONTINGENCY.*?END'
REPEATED_CONTINGENCY_COMMENT_PATTERN: str = r'\n//.*REPEATED'

# File processing limits
MAX_INPUT_FILES: int = 50  # Maximum contingency files to process

# Define named tuple for return type
ContingencyInfo = namedtuple(
    "ContingencyInfo",
    [
        "contingency_definition",
        "unique_areas",
        "bus_numbers",
        "lowest_voltage",
        "highest_voltage",
        "undefined_buses",
        "branches",
        "undefined_branches",
        "generators",
        "undefined_generators",
        "loads",
        "undefined_loads",
        "transformers",
        "undefined_transformers",
    ],
)


def get_default_raw_file_path(filepath: str | Path = DEFAULT_INPUT_FOLDER) -> Path:
    """Resolve or discover the newest PSS/E RAW file in specified directory.

    Args:
        filepath: Path to file or directory containing .raw files.

    Returns:
        Path to resolved RAW file.

    Raises:
        FileNotFoundError: When:
            - Specified path doesn't exist
            - Directory contains no .raw files
            - File path points to non-existent file
        ValueError: When:
            - Provided file doesn't have .raw extension
            - Path is neither file nor directory

    Examples:
        Direct file path:
        >>> get_default_raw_file_path("data/network.raw")
        PosixPath('data/network.raw')

        Directory search (finds newest):
        >>> get_default_raw_file_path("raw_files/")
        PosixPath('raw_files/2024_summer_peak.raw')
    """
    path = Path(filepath) if not isinstance(filepath, Path) else filepath

    if not path.exists():
        raise FileNotFoundError(f"Path does not exist: {path}")

    if path.is_file():
        if not path.suffix.lower() == ".raw":
            raise ValueError(f"Path '{path}' is not a '.raw' file.")
        return path

    if path.is_dir():
        raw_files = list(path.glob("*.raw"))
        if not raw_files:
            raise FileNotFoundError(f"No '.raw' files found in directory: {path}")
        return max(raw_files, key=lambda f: f.stat().st_mtime)

    raise FileNotFoundError(f"Path is neither a file nor a directory: {path}")


def _get_contingency_info(
    bus_definitions: pd.DataFrame,
    contingency: str,
    branch_set: set[tuple[int, int, str]],
    generator_set: set[tuple[int, str]],
    load_set: set[tuple[int, str]],
    transformer_set: set[tuple[int, int, int, str]]
) -> ContingencyInfo:
    """Parse and validate individual contingency definition.

    Extracts component references from contingency text and validates
    their existence against the network model datasets.

    Processing Steps:
        1. Extract bus numbers using regex patterns (BUS######)
        2. Identify affected electrical areas from bus data
        3. Parse branch, generator, load, and transformer references
        4. Cross-reference components against model datasets
        5. Calculate voltage characteristics for filtering decisions
        6. Compile validation results into structured format

    Args:
        bus_definitions: Bus DataFrame with voltage and area data.
            Required columns: ['baskv', 'arname']
            Index must be 'ibus' (bus numbers)
        contingency: Raw contingency definition text block containing
            PSS/E contingency syntax (CONTINGENCY...END format)
        branch_set: Valid AC line identifiers as (ibus, jbus, circuit_id).
            Includes bidirectional entries for comprehensive validation.
        generator_set: Valid generator identifiers as (ibus, machine_id).
        load_set: Valid load identifiers as (ibus, load_id).
        transformer_set: Valid transformer identifiers as
            (ibus, jbus, kbus, circuit_id).

    Returns:
        ContingencyInfo: Named tuple containing:
            - contingency_definition: Original contingency text
            - unique_areas: Sorted list of affected area names
            - bus_numbers: Sorted tuple of referenced bus numbers
            - lowest_voltage: Minimum component voltage (kV)
            - highest_voltage: Maximum component voltage (kV)
            - undefined_buses: Buses not found in network model
            - branches: Parsed branch references from contingency
            - undefined_branches: Branches not found in model
            - generators: Parsed generator references
            - undefined_generators: Generators not found in model
            - loads: Parsed load references
            - undefined_loads: Loads not found in model
            - transformers: Currently returns empty tuple (not implemented)
            - undefined_transformers: Currently returns empty tuple

    Notes:
        - Returns empty ContingencyInfo if no bus numbers found
        - Voltage filtering based on bus base voltages (baskv column)
        - Component validation uses exact string matching
        - Missing components indicate potential data quality issues
        - Transformer parsing is not fully implemented in current version
    """
    # Extract bus numbers using regex pattern matching
    # Format: 'BUS######' where # represents digits
    bus_numbers = [int(num) for num in
                   re.findall(r'\bBUS\s+(\d+)', contingency, re.IGNORECASE)]
    bus_numbers = tuple(sorted(set(bus_numbers)))  # Remove duplicates and sort

    if not bus_numbers:
        return ContingencyInfo(contingency_definition=contingency,
                               unique_areas=tuple(),
                               bus_numbers=tuple(),
                               lowest_voltage=0.0,
                               highest_voltage=0.0,
                               undefined_buses=tuple(),
                               branches=tuple(),
                               undefined_branches=tuple(),
                               generators=tuple(),
                               undefined_generators=tuple(),
                               loads=tuple(),
                               undefined_loads=tuple(),
                               transformers=tuple(),
                               undefined_transformers=tuple(),
                               )

    # bus_definitions.columns = ['name', 'baskv', 'ide', 'area', 'zone', 'owner', 'vm', 'va', 'nvhi', 'nvlo', 'evhi', 'evlo', 'arname']
    # bus_definitions.index.name='ibus'
    # Filter relevant buses
    relevant_buses: pd.DataFrame = bus_definitions[bus_definitions.index.isin(bus_numbers)]

    # Get unique areas
    unique_areas: pd.DataFrame = relevant_buses['arname'].dropna().unique().tolist()

    # Get highest voltage
    voltages = relevant_buses['baskv'].dropna()
    lowest_voltage = voltages.min() if not voltages.empty else 0.0
    highest_voltage = voltages.max() if not voltages.empty else 0.0

    # Find all bus_numbers that are not in bus_definitions.
    undefined_buses = tuple(sorted(set(bus_numbers) - set(bus_definitions.index)))

    branch_matches = re.findall(BRANCH_PATTERN, contingency, re.IGNORECASE)
    branches = tuple([[int(ibus), int(jbus), ckt.strip('"\'').strip()] for ibus, jbus, ckt in branch_matches])

    # Check for undefined branches
    undefined_branches = []
    for branch in branches:
        ib, jb, ckt = branch
        branch_tuple = (ib, jb, str(ckt))
        if branch_tuple not in branch_set:
            undefined_branches.append(branch)
    undefined_branches = tuple(undefined_branches)

    transformers = []
    for m in re.findall(TRANSFORMER_PATTERN, contingency, re.IGNORECASE):
        ibus, jbus, kbus, ckt = m
        transformers.append((int(ibus), int(jbus), int(kbus), str(ckt).strip()))
    transformers = tuple(transformers)

    # Check for undefined branches
    undefined_transformers = []
    for transformer in transformers:
        ibus, jbus, kbus, ckt = transformer
        transformer_tuple = (ibus, jbus, kbus, str(ckt))
        if transformer_tuple not in transformer_set:
            undefined_transformers.append(transformer_tuple)
    undefined_transformers = tuple(undefined_transformers)

    # Extract generators
    gen_matches = re.findall(GEN_PATTERN, contingency, re.IGNORECASE)
    generators = tuple([[int(bus), str(machid).strip()] for machid, bus in gen_matches])

    # Check undefined generators
    undefined_generators = [
        gen for gen in generators
        if (gen[0], gen[1]) not in generator_set
    ]
    undefined_generators = tuple(undefined_generators)

    # Extract loads
    load_matches = re.findall(LOAD_PATTERN, contingency, re.IGNORECASE)
    loads = tuple([[int(bus), str(loadid).strip()] for loadid, bus in load_matches])

    # Check undefined loads
    undefined_loads = [
        load for load in loads
        if (load[0], load[1]) not in load_set
    ]
    undefined_loads = tuple(undefined_loads)

    # Update return statement
    return ContingencyInfo(
        contingency_definition=contingency,
        unique_areas=sorted(unique_areas),
        bus_numbers=bus_numbers,
        lowest_voltage=lowest_voltage,
        highest_voltage=highest_voltage,
        undefined_buses=undefined_buses,
        branches=branches,
        undefined_branches=undefined_branches,
        generators=generators,
        undefined_generators=undefined_generators,
        loads=loads,
        undefined_loads=undefined_loads,
        transformers=[],
        undefined_transformers=[],
    )


def _read_contingency_definition_file(model: Model,
                                       bus_definitions: pd.DataFrame,
                                       con_file_path: str | Path,
                                       branch_set: set[tuple[int, int, str]],
                                       generator_set: set[tuple[int, str]],
                                       load_set: set[tuple[int, str]],
                                       transformer_set: set[tuple[int, int, int, str]],
                                       mode: str = 'r') -> pd.DataFrame:
    """Parse individual contingency file into structured validation data.

    Args:
        model: Initialized network model for component validation
        bus_definitions: Bus data with voltage and area information
        con_file_path: Path to contingency definition file
        branch_set: Valid line identifiers for existence checks
        generator_set: Valid generator identifiers
        load_set: Valid load identifiers
        transformer_set: Valid transformer identifiers
        mode: File open mode (default: read-only)

    Returns:
        DataFrame containing parsed contingency data with validation metadata.

    Raises:
        UnicodeDecodeError: For files with incompatible text encoding
    """
    with open(con_file_path, mode=mode) as f:
        content = f.read()

    # Extract contingency blocks
    contingencies = re.findall(CONTINGENCY_DEFINITION_PATTERN, content, flags=re.DOTALL)

    # Generate contingency info using list comprehension
    contingency_info = [
        _get_contingency_info(bus_definitions, cont,
                              branch_set, generator_set, load_set, transformer_set)
        for cont in contingencies
    ]

    # Convert to DataFrame with proper typing
    contingency_df = pd.DataFrame(contingency_info).convert_dtypes()

    return contingency_df


def _read_contingency_definition_files(
    model: Model | str | dict | Path,
    bus_definitions: pd.DataFrame,
    branch_set,
    generator_set,
    load_set,
    transformer_set,
    contingency_definitions_folder: str | Path = CONTINGENCY_DEFINITIONS_FOLDER,
    max_input_files: int = MAX_INPUT_FILES,
) -> pd.DataFrame:
    """Batch process contingency files into unified validation dataset.

    Args:
        model: Network model for component validation
        bus_definitions: Preprocessed bus data with area associations
        branch_set: Valid line identifiers for existence checks
        generator_set: Valid generator identifiers
        load_set: Valid load identifiers
        transformer_set: Valid transformer identifiers
        contingency_definitions_folder: Directory containing .con files
        max_input_files: Maximum number of files to process

    Returns:
        Consolidated DataFrame of all processed contingencies with validation data.

    Raises:
        FileNotFoundError: If input directory does not exist
    """
    # Read bus definitions
    if not isinstance(model, Model):
        model = Model(model)

    # Get list of contingency files from contingency_definitions_folder
    contingency_definition_file_names = [
        os.path.join(contingency_definitions_folder, f)
        for f in os.listdir(contingency_definitions_folder)
        if os.path.isfile(os.path.join(contingency_definitions_folder, f))
    ]

    if len(contingency_definition_file_names) > max_input_files:
        warnings.warn(f'{len(contingency_definition_file_names)} found but only '
                      f'{max_input_files} will be processed.  To process more '
                      f'files, please update max_input_files.')

    #
    contingency_definitions = pd.DataFrame()
    i, row_count = 1, len(contingency_definition_file_names)
    for file_name in contingency_definition_file_names[:max_input_files]:
        # print(dtdt.now())
        logger.info(f"Getting contingency definitions ({i} of {row_count}): {file_name}")
        df = _read_contingency_definition_file(model=model,
                                                bus_definitions=bus_definitions,
                                                con_file_path=file_name,
                                                branch_set=branch_set,
                                                generator_set=generator_set,
                                                load_set=load_set,
                                                transformer_set=transformer_set,
                                                )
        df['source_file_name'] = file_name
        contingency_definitions = pd.concat(
            [contingency_definitions, df],
            ignore_index=True
        )
        i += 1

    return contingency_definitions


def create_area_con_files(raw_file: str | Path | None = None,
                          input_folder: str | Path = DEFAULT_INPUT_FOLDER,
                          output_folder: str | Path = DEFAULT_OUTPUT_FOLDER,
                          kv_filter: tuple[int, int] = KV_FILTER,
                          kv_exceptions: tuple[str, ...] = KV_EXCEPTIONS,
                          max_input_files: int = MAX_INPUT_FILES,
                          delete_old_output: bool = True
                          ) -> Path:
    """Execute contingency processing pipeline and generate area-specific files.

    This function implements a comprehensive pipeline for processing power system
    contingency definitions, including validation, filtering, and area-specific
    file generation.

    Processing Pipeline:
        1. Load and validate PSS/E RAW network model
        2. Parse contingency definition files (.con format)
        3. Validate component existence against network model
        4. Apply voltage-level filtering with keyword exceptions
        5. Generate area-specific output files with quality separation
        6. Export validation metadata and summary reports

    Args:
        raw_file: Path to PSS/E RAW network file. If None, automatically
            discovers the newest .raw file in input_folder by modification time.
        input_folder: Directory containing .con contingency definition files.
            All .con files in this directory will be processed.
        output_folder: Target directory for generated files. Directory will be
            created if it doesn't exist. If delete_old_output is True, existing
            contents will be removed.
        kv_filter: Voltage range filter as (min_kv, max_kv). Contingencies
            where all components fall outside this range are excluded.
        kv_exceptions: Component type keywords that bypass voltage filtering.
            Contingencies containing these keywords are always included.
        max_input_files: Maximum number of input files to process. Used for
            testing and performance management with large datasets.
        delete_old_output: Whether to clear output directory before processing.
            Recommended for clean runs to avoid stale data.

    Returns:
        Path to the output directory containing generated files.

    Raises:
        FileNotFoundError: When:
            - RAW file doesn't exist at specified path
            - Input directory doesn't exist or is empty
            - No .con files found in input directory
        ValueError: When:
            - Voltage filter parameters are invalid (min >= max)
            - RAW file cannot be parsed by PSS/E model
            - Network model lacks required data sections
        PermissionError: When:
            - Unable to write to output directory
            - Cannot delete existing output files (if delete_old_output=True)
        ModelError: When:
            - PSS/E model initialization fails
            - Network data is corrupted or incomplete

    Generated Files:
        - {area_name}.con: Valid contingencies for each area
        - {area_name}_bad.con: Invalid contingencies with error metadata
        - all_input_contingencies.csv: Complete input dataset
        - kv_removed_input_contingencies.csv: Voltage-filtered contingencies
        - duplicate_contingencies.log: Duplicate detection report
        - raw_*.csv: Network model reference data

    Examples:
        Basic usage:
        >>> output_dir = create_area_con_files(
        ...     raw_file="network.raw",
        ...     input_folder="contingencies/",
        ...     output_folder="output/"
        ... )

        Custom voltage filtering:
        >>> output_dir = create_area_con_files(
        ...     raw_file="model.raw",
        ...     kv_filter=(100, 500),
        ...     kv_exceptions=("GENERATOR", "CRITICAL_LOAD")
        ... )

    Notes:
        - Invalid contingencies include detailed validation metadata
        - Voltage filtering applies component-wise, not system-wide
        - Bidirectional validation ensures transmission line connectivity
        - Duplicate contingencies are automatically detected and logged
        - Progress is logged to both console and log files
    """

    if not raw_file:
        raw_file = get_default_raw_file_path(input_folder)

    logger.info('\n\n' + '*' * 80)
    logger.info('\nStarting create_area_con_files():\n')
    logger.info(f'Folders:\n   input contingency definitions folder: {input_folder}')
    logger.info(f'   output folder: {output_folder}')
    logger.info('\nFilters:')
    logger.info(f"  Lowest kV in contingency must be >= {kv_filter[0]} kV")
    logger.info(f"  Highest kV in contingency must be >= {kv_filter[-1]} kV")
    logger.info(f"  Do not apply kV filter to contingencies containing: {kv_exceptions}")
    # print(dtdt.now())
    logger.info('\n\n' + '*' * 80)

    # Prep the output_folder
    output_folder = output_folder if isinstance(output_folder, Path) else Path(output_folder)
    if delete_old_output and output_folder.exists():
        logger.info(f'Deleting old data from: {output_folder}')
        shutil.rmtree(output_folder)
    output_folder.mkdir(parents=True, exist_ok=True)

    # Read bus definitions
    model = Model(file_path_or_json=raw_file, force_recalculate=True)

    # Prepare bus_definitions
    bus_definitions: pd.DataFrame = model.network.bus.copy()
    bus_definitions['arname'] = model.network.area['arname'].reindex(bus_definitions['area']).values

    # Build branch_set ONCE
    branch_set = set()
    for idx in model.network.acline.index:
        ib, jb, ckt = idx
        ckt_str = str(ckt).strip()
        branch_set.add((ib, jb, ckt_str))
        branch_set.add((jb, ib, ckt_str))  # Reverse direction

    # Build transformer_set
    transformer_set = set()
    for idx in model.network.transformer.index:
        ibus, jbus, kbus, ckt = idx
        ckt_str = str(ckt).strip()
        # Add all permutations of i/j/k bus + ckt to the set.
        combos = [tuple(list(_) + [ckt]) for _ in list(permutations([ibus, jbus, kbus]))]
        for combo in combos:
            branch_set.add(combo)

    # Create generator lookup set
    generator_set = set()
    for idx in model.network.generator.index:
        ibus, machid = idx
        generator_set.add((ibus, str(machid).strip()))

    # Create load lookup set
    load_set = set()
    for idx in model.network.load.index:
        ibus, loadid = idx
        load_set.add((ibus, str(loadid).strip()))

    # Read and process all contingency files
    logger.info('\n\n' + '*' * 80)
    # print(dtdt.now())
    logger.info('Reading contingency definition input files...')
    all_contingencies = _read_contingency_definition_files(
        model=model,
        bus_definitions=bus_definitions,
        contingency_definitions_folder=input_folder,
        max_input_files=max_input_files,
        branch_set=branch_set,
        generator_set=generator_set,
        load_set=load_set,
        transformer_set=transformer_set,
    )

    # Save all input contingencies to disk.
    # print(dtdt.now())
    output_folder.mkdir(parents=True, exist_ok=True)
    fp = os.path.join(output_folder, 'all_input_contingencies.csv')
    logger.info(f'Saving all input contingency definitions to {fp} ...')
    all_contingencies.to_csv(fp, index=False)

    # Remove contingency definitions that indicate "REPEATED" in a comment.
    pattern = re.compile(REPEATED_CONTINGENCY_COMMENT_PATTERN, re.IGNORECASE)
    mask = ~all_contingencies['contingency_definition'].str.contains(pattern)
    all_contingencies = all_contingencies[mask].reset_index(drop=True)

    # Identify duplicates based on the 'contingency_definition' column
    duplicates = all_contingencies[all_contingencies.duplicated(subset=['contingency_definition'], keep=False)]
    # Save duplicates to a log file
    log_path = os.path.join(output_folder, 'duplicate_contingencies.log')
    with open(log_path, 'w') as log_file:
        if not duplicates.empty:
            log_file.write("Duplicate contingency definitions found and removed:\n\n")
            for idx, row in duplicates.iterrows():
                log_file.write(f"Source File: {row['source_file_name']}\n")
                log_file.write(f"Contingency Definition:\n{row['contingency_definition']}\n")
                log_file.write("-" * 80 + "\n")
        else:
            log_file.write("No duplicate contingency definitions found.\n")

    all_contingencies.drop_duplicates(subset=['contingency_definition'], keep='first', inplace=True)

    # Contingencies not filtered due to kV level:
    contingencies = all_contingencies[
        ((all_contingencies['lowest_voltage'] >= kv_filter[0]) &
         (all_contingencies['highest_voltage'] >= kv_filter[-1])
        ) |
        (all_contingencies['contingency_definition'].str.contains('|'.join(kv_exceptions), na=False))
        ]

    # Save contingencies filtered out due to kV level to disk.
    # print(dtdt.now())
    fp = os.path.join(output_folder, 'kv_removed_input_contingencies.csv')
    logger.info(f'Saving contingency definitions removed due to kV filter to {fp} ...')

    # Find rows in all_contingencies not present in contingencies using merge
    removed_contingencies = all_contingencies[~all_contingencies.index.isin(contingencies.index)]
    removed_contingencies.to_csv(fp, index=False)

    # print(dtdt.now())
    logger.info('Removing "bad" contingencies (equipment not found in raw file)...')
    # Split into good/bad contingencies based on undefined buses
    good_contingencies = contingencies[
        (contingencies["undefined_buses"].apply(len) == 0) &
        (contingencies["undefined_branches"].apply(len) == 0) &
        (contingencies["undefined_generators"].apply(len) == 0) &
        (contingencies["undefined_loads"].apply(len) == 0) &
        (contingencies["undefined_transformers"].apply(len) == 0)
        ]

    bad_contingencies = contingencies[
        (contingencies["undefined_buses"].apply(len) > 0) |
        (contingencies["undefined_branches"].apply(len) > 0) |
        (contingencies["undefined_generators"].apply(len) > 0) |
        (contingencies["undefined_loads"].apply(len) > 0) |
        (contingencies["undefined_transformers"].apply(len) > 0)
        ]

    # Get unique areas from all contingencies
    areas = set(chain.from_iterable(contingencies['unique_areas']))

    # Create area-specific contingency files
    logger.info('\n\n' + '*' * 80 + '\n\n')
    # print(dtdt.now())
    logger.info('\n!!! Write .con files...')
    logger.info('!' * 80 + '\n')
    i, row_count = 1, len(areas)
    for area in areas:
        # Filter good contingencies affecting this area
        good_area_mask = good_contingencies['unique_areas'].apply(lambda x: area in x)
        good_df = good_contingencies[good_area_mask]
        good_content = '\n\n'.join(good_df['contingency_definition'])
        # Write good contingencies to disk
        good_path = os.path.join(output_folder, f"{area}.con")
        with open(good_path, 'w') as f:
            logger.info(f'Writing GOOD .con file ({i} of {row_count}): "{good_path}"...')
            f.write(good_content)


        # Filter bad contingencies affecting this area
        bad_area_mask = bad_contingencies['unique_areas'].apply(lambda x: area in x)
        bad_df = bad_contingencies[bad_area_mask]
        if not bad_df.empty:
            def format_bad_row(row):
                return (
                    f"{row['contingency_definition'].rstrip()}\n"
                    f"UNDEFINED_BUSES: {row['undefined_buses']}\n"
                    f"UNDEFINED_BRANCHES: {row['undefined_branches']}\n"
                    f"SOURCE_FILE: {row['source_file_name']}\n"
                )

            bad_content = "\n\n".join(bad_df.apply(format_bad_row, axis=1))            # Write bad contingencies to disk
            bad_path = os.path.join(output_folder, f"{area}_bad.con")
            with open(bad_path, 'w') as f:
                logger.info(f'        BAD .con file: "{bad_path}"...')
                f.write(bad_content)

        i += 1

    logger.info('\n\n' + '*' * 80)
    # print(dtdt.now())
    logger.info(f'!!! Finished writing .con files for each area to \n   {output_folder}')
    logger.info('*' * 80 + '\n')

    # Save some of the raw file model data to csv files for easy refrence.
    output_folder = output_folder if isinstance(output_folder, Path) else Path(output_folder)
    folder = Path(args.output_folder)
    # Add bus info to other model data.
    model.network.append_bus_info_to_dfs()
    # Export raw file bus data.
    logger.info('Saving raw file bus data to disk...')
    model.network.bus.to_csv(folder / 'raw_bus.csv', index=True)
    # Export raw file branch data.
    logger.info('Saving raw file branch data to disk...')
    model.network.acline.to_csv(folder / 'raw_acline.csv', index=True)
    # Export raw file generator data.
    logger.info('Saving raw file generator data to disk...')
    model.network.generator.to_csv(folder / 'raw_generator.csv', index=True)
    # Export raw file load data.
    logger.info('Saving raw file load data to disk...')
    model.network.load.to_csv(folder / 'raw_load.csv', index=True)
    # Export raw file transformer data.
    logger.info('Saving raw file transformer data to disk...')
    model.network.transformer.to_csv(folder / 'raw_transformer.csv', index=True)

    return output_folder

logger.debug('    Finished loading code (cotingency_util.py).')


if __name__ == '__main__':
    logger.debug("Starting arg parsing...")

    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="""
        Create area-specific contingency definition files from PSS/E RAW
        model and input contingency files.

        This script processes power system contingency definitions by:
        1. Loading network model from RAW file
        2. Validating contingency components
        3. Applying voltage-level filtering
        4. Generating area-specific output files
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
        Examples:
          %(prog)s -r network.raw -i contingencies/ -o output/
          %(prog)s --raw-file model.raw --low-kv 100 --high-kv 500
        """
    )
    parser.add_argument(
        '-r', '--raw-file',
        type=str,
        metavar='PATH_TO_RAW_FILE',
        default='',
        help='Path to PSS/E RAW input file. If directory provided, '
             'newest .raw file will be used. (default: newest raw file in '
             'input-folder.')
    parser.add_argument(
        '-i', '--input-folder',
        type=str,
        default='',
        help=f'Folder containing contingency definition templates (default '
             f'{DEFAULT_INPUT_FOLDER})')
    parser.add_argument(
        '-o', '--output-folder',
        type=str,
        default='',
        help='Output directory for generated contingency files (.con) and '
             f'informational output (.csv and .log). (default '
             f'{DEFAULT_OUTPUT_FOLDER}).')
    parser.add_argument(
        '-n', '--low-kv',
        type=int,
        default=KV_FILTER[0],
        help=f'Lowest kV in contingency def must be greater than (default {KV_FILTER[0]})')
    parser.add_argument(
        '-g', '--high-kv',
        type=int,
        default=KV_FILTER[-1],
        help=f'Highest kV in contingency def must be greater than (default {KV_FILTER[-1]})')

    # Initialize dict of commandline arguments, args.
    args = parser.parse_args()
    pause: bool = True if len(sys.argv) == 1 else False

    if not args.input_folder:
        args.input_folder = args.input_folder.strip() or DEFAULT_INPUT_FOLDER
        args.input_folder = (input(f"Input contingency definitions folder ({args.input_folder}): ").strip()
                             or args.input_folder.strip())
    if not args.raw_file:
        args.raw_file = args.raw_file.strip() or args.input_folder
        args.raw_file = (input(f"Path to PSS/E RAW input file ({args.raw_file}): ").strip()
                         or args.input_folder.strip())
        args.raw_file = get_default_raw_file_path(args.raw_file)
    if not args.output_folder:
        args.output_folder = args.output_folder.strip() or DEFAULT_OUTPUT_FOLDER
        args.output_folder = (input(f"Output directory for generated contingency files ({args.output_folder}): ").strip()
                              or args.output_folder.strip())

    # Print configuration
    logger.info(f"\n{' Configuration ':-^40}")
    logger.info(f"  Raw File: {args.raw_file}")
    logger.info(f"  Input Folder: {args.input_folder}")
    logger.info(f"  Output Folder: {args.output_folder}")
    logger.info(f"  Lowest kV in contingency must be >= {args.low_kv} kV")
    logger.info(f"  Highest kV in contingency must be >= {args.high_kv} kV")
    logger.info(f"  Do not apply kV filter to contingencies containing: {KV_EXCEPTIONS}")
    logger.info(f"  Max # input con files to process: {MAX_INPUT_FILES}")
    logger.info(f"  Delete old output files: {True}\n\n")
    if pause:
        input(" Press [Enter] to continue... ")

    create_area_con_files(
        raw_file=args.raw_file,
        input_folder=args.input_folder,
        output_folder=args.output_folder,
        kv_filter=(int(args.low_kv), int(args.high_kv)),
        kv_exceptions=KV_EXCEPTIONS,
        max_input_files=MAX_INPUT_FILES,
        delete_old_output=True
    )

    print(f"\n{' Configuration ':-^40}"
          f"\n  Raw File: {args.raw_file}"
          f"\n  Input Folder: {args.input_folder}"
          f"\n  Output Folder: {args.output_folder}"
          f"\n  Lowest kV in contingency must be >= {args.low_kv} kV"
          f"\n  Highest kV in contingency must be >= {args.high_kv} kV"
          f"\n  Do not apply kV filter to contingencies containing: {KV_EXCEPTIONS}"
          f"\n  Max # input con files to process: {MAX_INPUT_FILES}"
          f"\n  Delete old output files: {True}\n\n"
          f"\n\nLog file: {get_log_file_path(logger)}")
