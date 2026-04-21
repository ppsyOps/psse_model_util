"""
The rawx_json_template.rawx_json_template is to provides a standardized structure and metadata for parsing and
organizing PSSE v35 RAWX (JSON) file data. It serves several important functions in the Model class:

1. Data Structure Definition:
   It defines the expected structure of the RAWX data, including all sections (like 'network', 'harmonics',
   'timeseries', etc.) and subsections (like 'fields', 'data', etc.) and their respective fields.

2. Metadata Provision:
   For each section and subsection, it provides crucial metadata.  While 'fields' and 'data' dict entries are expected
    in the raw files, other fields ('data_type', 'bus_cols' and 'id_cols') provide important metadata.
   - 'fields': The expected column names for each DataFrame (for PSS/e v35 RAWX files).
   - 'data_type': The expected data types for each field
           Used in the _create_dataframe method of the Network class (which is part of Model).
           It specifies the data types for each column in a DataFrame.
           When creating a DataFrame, these data types are used to convert the raw data to the correct types.
           If 'data_type' is provided as a list or tuple, it's converted to a dictionary where the keys are field names
           and values are the corresponding data types.

   - 'bus_cols': Columns that contain bus information
            Used in multiple methods, including filter_by_area and section_with_bus in the Network class.
            Identifies which columns in a DataFrame contain bus information.
            In filter_by_area, it's used to determine which columns to check when filtering data based on specified
            areas.
            In section_with_bus, it's used to know which columns should be joined with the bus DataFrame to add bus
            information.

   - 'id_cols': Columns that should be used as identifiers or index
            Used in the _create_dataframe method of the Network class.
            Specifies which columns should be used as the index for the DataFrame.
            If 'id_cols' is provided in the metadata, the method attempts to set these columns as the index of the
            DataFrame.

   - Usage:
        In the _create_dataframe method:
            The method checks if these metadata fields exist in the rawx_json_template for the current section.
            If they exist, they're added to the DataFrame's metadata.
            The 'data_type' is used to convert column data types.
            The 'id_cols' is used to set the DataFrame's index.

        In other methods like filter_by_area and section_with_bus:
            The methods check the DataFrame's metadata for 'bus_cols'.
            If present, 'bus_cols' is used to identify which columns contain bus information for filtering or joining
            operations.

        This approach allows for flexible and dynamic handling of different sections in the RAWX data, with each section
        potentially having different column structures, data types, and indexing requirements. CopyRetryClaude can make
        mistakes. Please double-check responses.

3. Default Values:
   It can provide default values or empty structures for sections that might be missing in some RAWX files, ensuring
   consistency across different files.

4. Data Validation:
   By defining the expected structure and data types, it allows for validation of incoming data against a known, correct
   format.

5. Flexibility and Extensibility:
   Having a template makes it easier to extend or modify the parser to handle new versions of the RAWX format or
    additional data fields.

6. Performance Optimization:
   By predetermining the structure and data types, it allows for more efficient parsing and DataFrame creation, as the
   code doesn't need to infer these details from the data itself.

7. Consistency in Processing:
   It ensures that all RAWX files are processed in a consistent manner, regardless of minor variations in the input
   data.

In the Model class, this template is used extensively in the _create_dataframe method to structure the incoming JSON
data into appropriate pandas DataFrames with the correct metadata. It guides the entire process of transforming the raw
JSON data into a structured, queryable model representation.
"""
from psse_model_util.dataformat.classes import *

# from psse_model_util.common.classes import (AreaId, BusId, IdInt, IdStr, Impedance, Name, PowerFactor, Resistance,
#                                             Reactance, OwnerId, OwnerFraction, Rating, ReactivePower, ActivePower,
#                                             Status, Susceptance, Voltage, ZoneId, SwShID)


rawx_json_template = \
    {
        "general": {},
        "network": {
            "caseid": {
                "fields": ["ic", "sbase", "rev", "xfrrat", "nxfrat", "basfrq", "title1", "title2"],
                "data": [],
                "data_type": [int, float, int, int, int, float, str, str]
            },
            "general": {
                "fields": ["thrshz", "pqbrak", "blowup", "maxisollvls", "camaxreptsln", "chkdupcntlbl"],
                "data": [],
                "data_type": [float, float, float, int, int, int]
            },
            "gauss": {
                "fields": ["itmx", "accp", "accq", "accm", "tol"],
                "data": [],
                "data_type": [int, float, float, float, float]
            },
            "newton": {
                "fields": ["itmxn", "accn", "toln", "vctolq", "vctolv", "dvlim", "ndvfct"],
                "data": [],
                "data_type": [int, float, float, float, float, float, float]
            },
            "adjust": {
                "fields": ["adjthr", "acctap", "taplim", "swvbnd", "mxtpss", "mxswim"],
                "data": [],
                "data_type": [float, float, float, float, int, int],
            },
            "tysl": {
                "fields": ["itmxty", "accty", "tolty"],
                "data": [],
                "data_type": [int, float, float],
            },
            "solver": {
                "fields": ["method", "actaps", "areain", "phshft", "dctaps", "swshnt", "flatst", "varlim", "nondiv"],
                "data": [],
                "data_type": [str, int, int, int, int, int, int, int, int],
            },
            "rating": {
                "fields": ["irate", "name", "desc"],
                "data": [],
                "data_type": [int, str, str],
            },
            "bus": {
                "fields": ["ibus", "name", "baskv", "ide", "area", "zone", "owner", "vm", "va", "nvhi", "nvlo", "evhi",
                           "evlo"],
                "data": [],
                "data_type": [BusId, Name, Voltage, int, AreaId, ZoneId, int, Voltage, float, Voltage, Voltage, Voltage,
                              Voltage],
                "bus_cols": ["ibus"],
                "id_cols": ["ibus"],
            },
            "load": {
                "fields": ["ibus", "loadid", "stat", "area", "zone", "pl", "ql", "ip", "iq", "yp", "yq", "owner",
                           "scale", "intrpt", "dgenp", "dgenq", "dgenm", "loadtype"],
                "data": [],
                "data_type": [BusId, IdStr, Status, AreaId, ZoneId, float, float, float, float, float, float, OwnerId,
                              int, int, float, float, int, str],
                "bus_cols": ["ibus"],
                "id_cols": ["ibus", "loadid"],
            },
            "fixshunt": {
                "fields": ["ibus", "shntid", "stat", "gl", "bl"],
                "data": [],
                "data_type": [BusId, str, Status, float, float],
                "bus_cols": ["ibus"],
                "id_cols": ["ibus", "shntid"],
            },
            "generator": {
                "fields": ["ibus", "machid", "pg", "qg", "qt", "qb", "vs", "ireg", "nreg", "mbase", "zr", "zx", "rt",
                           "xt", "gtap", "stat", "rmpct", "pt", "pb", "baslod", "o1", "f1", "o2", "f2", "o3", "f3",
                           "o4", "f4", "wmod", "wpf"],
                "data": [],
                "data_type": [BusId, IdStr, float, float, float, float, float, int, str, float, float, float, float,
                              float, float, Status, float, float, float, int, OwnerId, OwnerFraction, OwnerId,
                              OwnerFraction, OwnerId, OwnerFraction, OwnerId, OwnerFraction, int, float],
                "bus_cols": ["ibus"],
                "id_cols": ["ibus", "machid"],
            },
            "acline": {
                "fields": ["ibus", "jbus", "ckt", "rpu", "xpu", "bpu", "name", "rate1", "rate2", "rate3", "rate4",
                           "rate5", "rate6", "rate7", "rate8", "rate9", "rate10", "rate11", "rate12", "gi", "bi", "gj",
                           "bj", "stat", "met", "len", "o1", "f1", "o2", "f2", "o3", "f3", "o4", "f4"],
                "data": [],
                "data_type": [BusId, BusId, IdStr, Resistance, Reactance, Susceptance, Name, Rating, Rating, Rating,
                              Rating, Rating, Rating, Rating, Rating, Rating, Rating, Rating, Rating, float, float,
                              float, float, Status, int, float, OwnerId, float, OwnerId, float, OwnerId, float, OwnerId,
                              float],
                "bus_cols": ["ibus", "jbus"],
                "id_cols": ["ibus", "jbus", "ckt"],
            },
            "sysswd": {
                "fields": ["ibus", "jbus", "ckt", "xpu", "rate1", "rate2", "rate3", "rate4", "rate5", "rate6", "rate7",
                           "rate8", "rate9", "rate10", "rate11", "rate12", "stat", "nstat", "met", "stype", "name"],
                "data": [],
                "data_type": [BusId, BusId, IdStr, float, Rating, Rating, Rating, Rating, Rating, Rating, Rating,
                              Rating, Rating, Rating, Rating, Rating, Status, int, int, int, Name],
                "bus_cols": ["ibus", "jbus"],
                "id_cols": ["ibus", "jbus", "ckt"],
            },
            "transformer": {
                "fields": ["ibus", "jbus", "kbus", "ckt", "cw", "cz", "cm", "mag1", "mag2", "nmet", "name", "stat",
                           "o1", "f1", "o2", "f2", "o3", "f3", "o4", "f4", "vecgrp", "zcod", "r1_2", "x1_2", "sbase1_2",
                           "r2_3", "x2_3", "sbase2_3", "r3_1", "x3_1", "sbase3_1", "vmstar", "anstar", "windv1",
                           "nomv1", "ang1", "wdg1rate1", "wdg1rate2", "wdg1rate3", "wdg1rate4", "wdg1rate5",
                           "wdg1rate6", "wdg1rate7", "wdg1rate8", "wdg1rate9", "wdg1rate10", "wdg1rate11", "wdg1rate12",
                           "cod1", "cont1", "node1", "rma1", "rmi1", "vma1", "vmi1", "ntp1", "tab1", "cr1", "cx1",
                           "cnxa1", "windv2", "nomv2", "ang2", "wdg2rate1", "wdg2rate2", "wdg2rate3", "wdg2rate4",
                           "wdg2rate5", "wdg2rate6", "wdg2rate7", "wdg2rate8", "wdg2rate9", "wdg2rate10", "wdg2rate11",
                           "wdg2rate12", "cod2", "cont2", "node2", "rma2", "rmi2", "vma2", "vmi2", "ntp2", "tab2",
                           "cr2", "cx2", "cnxa2", "windv3", "nomv3", "ang3", "wdg3rate1", "wdg3rate2", "wdg3rate3",
                           "wdg3rate4", "wdg3rate5", "wdg3rate6", "wdg3rate7", "wdg3rate8", "wdg3rate9", "wdg3rate10",
                           "wdg3rate11", "wdg3rate12", "cod3", "cont3", "node3", "rma3", "rmi3", "vma3", "vmi3", "ntp3",
                           "tab3", "cr3", "cx3", "cnxa3"],
                "data": [],
                "data_type": [BusId, BusId, BusId, IdStr, int, int, int, float, float, int, Name, Status, OwnerId,
                              float, OwnerId, float, OwnerId, float, OwnerId, float, str, int, Resistance, Reactance,
                              float, Resistance, Reactance, float, Resistance, Reactance, float, float, float, float,
                              Voltage, float, Rating, Rating, Rating, Rating, Rating, Rating, Rating, Rating, Rating,
                              Rating, Rating, Rating, int, int, int, float, float, float, float, int, int, float, float,
                              float, float, Voltage, float, Rating, Rating, Rating, Rating, Rating, Rating, Rating,
                              Rating, Rating, Rating, Rating, Rating, int, int, int, float, float, float, float, int,
                              int, float, float, float, float, Voltage, float, Rating, Rating, Rating, Rating, Rating,
                              Rating, Rating, Rating, Rating, Rating, Rating, Rating, int, int, int, float, float,
                              float, float, int, int, float, float, float],
                "bus_cols": ["ibus", "jbus", "kbus"],
                "id_cols": ["ibus", "jbus", "kbus", "ckt"],
            },
            "area": {
                "fields": ["iarea", "isw", "pdes", "ptol", "arname"],
                "data": [],
                "data_type": [IdInt, int, float, float, Name],
                "id_cols": ["iarea"],
            },
            "twotermdc": {
                "fields": ["name", "mdc", "rdc", "setvl", "vschd", "vcmod", "rcomp", "delti", "met", "dcvmin",
                           "cccitmx", "cccacc", "ipr", "nbr", "anmxr", "anmnr", "rcr", "xcr", "ebasr", "trr", "tapr",
                           "tmxr", "tmnr", "stpr", "icr", "ndr", "ifr", "itr", "idr", "xcapr", "ipi", "nbi", "anmxi",
                           "anmni", "rci", "xci", "ebasi", "tri", "tapi", "tmxi", "tmni", "stpi", "ici", "ndi", "ifi",
                           "iti", "idi", "xcapi"],
                "data": [],
                "data_type": [Name, int, float, float, float, float, float, float, str, float, int, float, int, int,
                              float, float, float, float, float, float, float, float, float, float, int, int, int, int,
                              str, float, int, int, float, float, float, float, float, float, float, float, float,
                              float, int, int, int, int, str, float],
                "bus_cols": ["ipi", "ipr"],
                "id_cols": ["name"],
            },
            "vscdc": {
                "fields": ["name", "mdc", "rdc", "o1", "f1", "o2", "f2", "o3", "f3", "o4", "f4", "ibus1", "type1",
                           "mode1",
                           "dcset1", "acset1", "aloss1", "bloss1", "minloss1", "smax1", "imax1", "pwf1", "maxq1",
                           "minq1", "vsreg1",
                           "nreg1", "rmpct1", "ibus2", "type2", "mode2", "dcset2", "acset2", "aloss2", "bloss2",
                           "minloss2", "smax2",
                           "imax2", "pwf2", "maxq2", "minq2", "vsreg2", "nreg2", "rmpct2"],
                "data": [],
                "data_type": [Name, int, float, OwnerId, str, OwnerId, str, OwnerId, str, OwnerId, str, int, int, int,
                              float, float, float, float, float, float, str, float, float, float, int, int, float,
                              BusId, int, int, float, float, float, float, float, float, str, float, float, float, int,
                              int, float],
                "bus_cols": ["ibus1"],
                "id_cols": ["name"],
            },
            "impcor": {
                "fields": ["itable", "tap", "refact", "imfact"],
                "data": [],
                "data_type": [int, float, float, float],
                "id_cols": ["itable"],
            },
            "ntermdc": {
                "fields": ["name", "nconv", "ndcbs", "ndcln", "mdc", "vconv", "vcmod", "vconvn"],
                "data": [],
                "data_type": [IdStr, int, int, int, int, int, float, int],
                "id_cols": ["name"],
            },
            "ntermdcconv": {
                "fields": ["name", "ib", "nbrdg", "angmx", "angmn", "rc", "xc", "ebas", "tr", "tap", "tpmx", "tpmn",
                           "tstp",
                           "setvl", "dcpf", "marg", "cnvcod"],
                "data": [],
                "data_type": [Name, BusId, int, float, float, float, float, float, float, float, float, float, float,
                              float, float, float, int],
                "bus_cols": ["ib"],
                "id_cols": ["name", "ib"],
            },
            "ntermdcbus": {
                "fields": ["name", "idc", "ib", "area", "zone", "dcname", "idc2", "rgrnd", "owner"],
                "data": [],
                "data_type": [Name, int, BusId, AreaId, ZoneId, Name, int, float, OwnerId],
                "bus_cols": ["ib"],
                "id_cols": ["name", "idc"],
            },
            "ntermdclink": {
                "fields": ["name", "idc", "jdc", "dcckt", "met", "rdc", "ldc"],
                "data": [],
                "data_type": [Name, int, str, str, int, str, str],
                "id_cols": ["name"],
            },
            "msline": {
                "fields": ["ibus", "jbus", "mslid", "met", "dum1", "dum2", "dum3", "dum4", "dum5", "dum6", "dum7",
                           "dum8", "dum9"],
                "data": [],
                "data_type": [BusId, BusId, IdStr, int, int, int, int, int, int, int, int, int, int],
                "bus_cols": ["ibus", "jbus"],
                "id_cols": ["ibus", "jbus", "mslid"],
            },
            "zone": {
                "fields": ["izone", "zoname"],
                "data": [],
                "data_type": [IdInt, Name],
                "id_cols": ["izone"],
            },
            "iatrans": {
                "fields": ["arfrom", "arto", "trid", "ptran"],
                "data": [],
                "data_type": [AreaId, AreaId, str, float],
                "id_cols": ["arfrom", "arto", "trid"],
            },
            "owner": {
                "fields": ["iowner", "owname"],
                "data": [],
                "id_cols": ["iowner"],
            },
            "facts": {
                "fields": ["name", "ibus", "jbus", "mode", "pdes", "qdes", "vset", "shmx", "trmx", "vtmn", "vtmx",
                           "vsmx", "imx", "linx", "rmpct", "owner", "set1", "set2", "vsref", "fcreg", "nreg", "mname"],
                "data": [],
                "bus_cols": ["ibus", "jbus"],
                "id_cols": ["name"],
            },
            "swshunt": {
                "fields": ["ibus", "shntid", "modsw", "adjm", "stat", "vswhi", "vswlo", "swreg", "nreg", "rmpct",
                           "rmidnt", "binit", "s1", "n1", "b1", "s2", "n2", "b2", "s3", "n3", "b3", "s4", "n4", "b4",
                           "s5", "n5", "b5", "s6", "n6", "b6", "s7", "n7", "b7", "s8", "n8", "b8"],
                "data": [],
                "bus_cols": ["ibus"],
                "id_cols": ["ibus", "shntid"],
            },
            "gne": {
                "fields": ["name", "model", "nterm", "bus1", "bus2", "nreal", "nintg", "nchar", "stat", "owner", "nmet",
                           "real1", "real2", "real3", "real4", "real5", "real6", "real7", "real8", "real9", "real10",
                           "intg1", "intg2", "intg3", "intg4", "intg5", "intg6", "intg7", "intg8", "intg9", "intg10",
                           "char1", "char2", "char3", "char4", "char5", "char6", "char7", "char8", "char9", "char10"],
                "data": [],
                "bus_cols": ["bus1", "bus2"],
                "id_cols": ["name"],
            },
            "indmach": {
                "fields": ["ibus", "imid", "stat", "sc", "dc", "area", "zone", "owner", "tc", "bc", "mbase", "ratekv",
                           "pcode", "pset", "hconst", "aconst", "bconst", "dconst", "econst", "ra", "xa", "xm", "r1",
                           "x1", "r2", "x2", "x3", "e1", "se1", "e2", "se2", "ia1", "ia2", "xamult"],
                "data": [],
                "bus_cols": ["ibus"],
                "id_cols": ["ibus", "imid"],
            },
            "sub": {
                "fields": ["isub", "name", "lati", "long", "srg"],
                "data": [],
                "id_cols": ["isub"],
            },
            "subnode": {
                "fields": ["isub", "inode", "name", "ibus", "stat", "vm", "va"],
                "data": [],
                "bus_cols": ["ibus"],
                "id_cols": ["isub", "inode", "ibus"],
            },
            "subswd": {
                "fields": ["isub", "inode", "jnode", "swdid", "name", "type", "stat", "nstat", "xpu", "rate1", "rate2",
                           "rate3"],
                "data": [],
                "id_cols": ["isub", "inode", "jnode", "swdid"],
            },
            "subterm": {
                "fields": ["isub", "inode", "type", "eqid", "ibus", "jbus", "kbus"],
                "data": [],
                "bus_cols": ["ibus", "jbus", "kbus"],
                "id_cols": ["isub", "inode", "type", "eqid", "ibus", "jbus", "kbus"],
            }
        },
        "timeseries": {},
        "harmonics": {
            "impchr": {
                "fields": ["name"],
                "data": []
            },
            "impchrpts": {
                "fields": ["name", "hn", "rn_r0", "ln_l0", "cn_c0"],
                "data": []
            },
            "vltsrc": {
                "fields": ["name", "angoptn"],
                "data": []
            },
            "vltsrcpts": {
                "fields": ["name", "hn", "vn/v0", "angn"],
                "data": []
            },
            "cursrc": {
                "fields": ["name", "curtyp", "angoptn"],
                "data": []
            },
            "cursrcpts": {
                "fields": ["name", "hn", "in_i0", "angn"],
                "data": []
            },
            "load": {
                "fields": ["ibus", "id", "hstate", "htype", "hquality", "hireg", "hpk", "zharm", "vharm", "iharm"],
                "data": []
            },
            "generator": {
                "fields": ["ibus", "id", "hstate", "htype", "hquality", "zharm", "vharm", "iharm"],
                "data": []
            },
            "ntbranch": {
                "fields": ["ibus", "jbus", "ckt", "hstate", "htype", "hquality", "zharm"],
                "data": []
            },
            "trbranch": {
                "fields": ["ibus", "jbus", "kbus", "ckt", "hstate", "htype", "hquality", "zharm", "iharm"],
                "data": [
                    [101, 151, 0, "T1", 1, 4, 1.000000, "", ""],
                    [102, 151, 0, "T2", 1, 5, 1.000000, "", ""],
                    [152, 153, 0, "T3", 1, 6, 1.000000, "", ""],
                    [152, 3021, 0, "T4", 1, 6, 1.000000, "", ""],
                    [152, 3022, 0, "T5", 1, 5, 1.000000, "", ""],
                    [154, 9154, 0, "W1", 1, 4, 1.000000, "", ""],
                    [201, 211, 0, "T6", 1, 3, 1.000000, "", ""],
                    [202, 203, 0, "T7", 1, 2, 1.000000, "", "ISRC_TRN1"],
                    [204, 205, 0, "T8", 1, 1, 1.000000, "", ""],
                    [204, 9204, 0, "W2", 1, 0, 1.000000, "", ""],
                    [205, 206, 0, "T9", 1, 1, 1.000000, "", ""],
                    [3002, 93002, 0, "W3", 1, 2, 1.000000, "", "ISRC_TRN2"],
                    [3004, 3005, 0, "10", 1, 3, 1.000000, "", ""],
                    [3008, 3018, 0, "11", 1, 4, 1.000000, "", ""],
                    [205, 215, 208, "3", 1, 0, 1.000000, "", ""],
                    [209, 217, 218, "4", 1, 1, 1.000000, "", ""],
                    [3001, 3002, 3011, "1", 1, 2, 1.000000, "", ""],
                    [3008, 3012, 3010, "2", 1, 3, 1.000000, "", "ISRC_TRN2"]
                ]
            },
            "2tdc": {
                "fields": ["name", "acbus", "hstate", "vharm", "iharm"],
                "data": []
            },
            "vscdc": {
                "fields": ["name", "acbus", "hstate", "vharm", "iharm"],
                "data": []
            },
            "mtdc": {
                "fields": ["name", "acbus", "hstate", "vharm", "iharm"],
                "data": []
            },
            "facts": {
                "fields": ["name", "sendbus", "termbus", "hstate", "htype", "hquality", "zharm", "vharm", "iharm"],
                "data": []
            },
            "indmach": {
                "fields": ["ibus", "id", "hstate", "htype", "hquality", "zharm", "vharm", "iharm"],
                "data": []
            },
            "Passive Filter": {
                "fields": ["ibus", "id", "hstate", "czy", "cfg", "rg", "xb1", "xb2"],
                "data": []
            }
        }
    }
