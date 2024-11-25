from psse_model_util.dataformat.classes import *
# from psse_model_util.common.classes import (AreaId, BusId, IdInt, IdStr, Impedance, Name, PowerFactor, Resistance,
#                                             Reactance, OwnerId, OwnerFraction, Rating, ReactivePower, ActivePower,
#                                             Status, Susceptance, Voltage, ZoneId)

FormatType = namedtuple('FormatType', ['category', 'column', 'dtype', 'prop_type'])

DTYPE_RAW_DATA = \
    {'AREA': {"I": IdInt, "ISW": int, "PDES": float, "PTOL": float, "ARNAME": Name},
     'BRANCH': {"I": BusId, "J": BusId, "CKT": IdStr, "R": Resistance, "X": Reactance, "B": Susceptance, "NAME": Name,
                "RATE1": Rating, "RATE2": Rating, "RATE3": Rating, "RATE4": Rating, "RATE5": Rating, "RATE6": Rating,
                "RATE7": Rating, "RATE8": Rating, "RATE9": Rating, "RATE10": Rating, "RATE11": Rating, "RATE12": Rating,
                "GI": float, "BI": float, "GJ": float, "BJ": float, "STAT": Status, "MET": int, "LEN": float,
                "O1": OwnerId, "F1": float, "O2": OwnerId, "F2": float, "O3": OwnerId, "F3": float, "O4": OwnerId,
                "F4": float},
     'BUS': {"I": BusId, "NAME": Name, "BASKV": Voltage, "IDE": int, "AREA": AreaId, "ZONE": ZoneId, "OWNER": int,
             "VM": Voltage,
             "VA": float, "NVHI": Voltage, "NVLO": Voltage, "EVHI": Voltage, "EVLO": Voltage},
     'FACTS DEVICE': {"NAME": Name, "I": BusId, "J": BusId, "MODE": int, "PDES": float, "QDES": float, "VSET": float,
                      "SHMX": float,
                      "TRMX": float, "VTMN": float, "VTMX": float, "VSMX": float, "IMX": float, "LINX": float,
                      "RMPCT": float,
                      "OWNER": OwnerId, "SET1": float, "SET2": float, "VSREF": int, "FCREG": int, "'MNAME'": Name,
                      "NREG": int},
     'FIXED SHUNT': {"I": BusId, "ID": str, "STATUS": Status, "GL": float, "BL": float},
     'GENERATOR': {"I": BusId, "ID": IdStr, "PG": float, "QG": float, "QT": float, "QB": float, "VS": float,
                   "IREG": int, "MBASE": float, "ZR": float, "ZX": float, "RT": float, "XT": float, "GTAP": float,
                   "STAT": Status, "RMPCT": float, "PT": float, "PB": float, "O1": OwnerId, "F1": OwnerFraction,
                   "O2": OwnerId, "F2": OwnerFraction, "O3": OwnerId, "F3": OwnerFraction, "O4": OwnerId,
                   "F4": OwnerFraction, "WMOD": int, "WPF": float, "NREG": str},
     'GNE': {},
     'HEADER': {"IC": int, "SBASE": float, "REV": int, "XFRRAT": int, "NXFRAT": int,
                "BASFRQ": float},
     'IMPEDANCE CORRECTION': [{"I": BusId, "T1": float, "Re(F1)": float, "Im(F1)": float, "T2": float, "Re(F2)": float,
                               "Im(F2)": float, "T3": float, "Re(F3)": float, "Im(F3)": float, "T4": float,
                               "Re(F4)": float,
                               "Im(F4)": float, "T5": float, "Re(F5)": float, "Im(F5)": float, "T6": float,
                               "Re(F6)": float,
                               "Im(F6)": float},
                              {"T7": float, "Re(F7)": float, "Im(F7)": float, "T8": float, "Re(F8)": float,
                               "Im(F8)": float,
                               "T9": float, "Re(F9)": float, "Im(F9)": float, "T10": float, "Re(F10)": float,
                               "Im(F10)": float,
                               "T11": float, "Re(F11)": float, "Im(F11)": float, "T12": float, "Re(F12)": float,
                               "Im(F12)": float}],
     'INDUCTION MACHINE': {"I": BusId, "'ID'": IdStr, "ST": int, "SC": int, "DC": int, "AREA": AreaId, "ZONE": ZoneId,
                           "OWNER": OwnerId, "TC": int, "BC": int, "MBASE": float, "RATEKV": float, "PC": int,
                           "PSET": float, "H": float, "A": float, "B": float, "D": float, "E": float, "RA": str,
                           "XA": str, "XM": str, "R1": str, "X1": str, "R2": str, "X2": str, "X3": str, "E1": str,
                           "SE1": str, "E2": str, "SE2": str, "IA1": str, "IA2": str, "XAMULT": str},
     'INTER-AREA TRANSFER': {"ARFROM": AreaId, "ARTO": AreaId, "TRID": str, "PTRAN": float},
     'LOAD': {"I": BusId, "ID": IdStr, "STAT": Status, "AREA": AreaId, "ZONE": ZoneId, "PL": float, "QL": float,
              "IP": float, "IQ": float, "YP": float, "YQ": float, "OWNER": OwnerId, "SCALE": int, "INTRPT": int,
              "DGENP": float, "DGENQ": float, "DGENF": int},
     'MULTI-SECTION LINE': {"I": BusId, "J": BusId, "'ID'": IdStr, "MET": int, "DUM1": int, "DUM2": int, "DUM3": int,
                            "DUM4": int, "DUM5": int, "DUM6": int, "DUM7": int, "DUM8": int, "DUM9": int},
     'MULTI-TERMINAL DC': [{"NAME": Name, "NCONV": int, "NDCBS": int, "NDCLN": int, "MDC": int, "VCONV": int,
                            "VCMOD": float, "VCONVN": int},
                           {"IB": int, "N": int, "ANGMX": float, "ANGMN": float, "RC": float, "XC": float,
                            "EBAS": float,
                            "TR": float, "TAP": float, "TPMX": float, "TPMN": float, "TSTP": float, "SETVL": float,
                            "DCPF": float,
                            "MARG": float, "CNVCOD": int},
                           {"IDC": int, "IB": int, "AREA": AreaId, "ZONE": ZoneId, "DCNAME": Name, "IDC2": int,
                            "RGRND": float, "OWNER": OwnerId},
                           {"IDC": int, "JDC": str, "DCCKT": str, "MET": int, "RDC": str, "LDC": str}],
     'OWNER': {'I': int, 'OWNAME': Name},
     'SUBSTATION': {},
     'SWITCHED SHUNT': {"I": BusId, "MODSW": int, "ADJM": int, "ST": int, "VSWHI": float, "VSWLO": float, "SWREG": int,
                        "RMPCT": float, "RMIDNT": str, "BINIT": float, "N1": int, "B1": float, "N2": int,
                        "B2": float, "N3": int, "B3": float, "N4": int, "B4": float, "N5": int, "B5": float,
                        "N6": int, "B6": float, "N7": int, "B7": float, "N8": int, "B8": float, "NREG": int},
     'SYSTEM SWITCHING DEVICE': {"I": BusId, "J": BusId, "CKT": IdStr, "X": (float, 'x'), "RATE1": Rating,
                                 "RATE2": Rating,
                                 "RATE3": Rating, "RATE4": Rating, "RATE5": Rating, "RATE6": Rating, "RATE7": Rating,
                                 "RATE8": Rating, "RATE9": Rating, "RATE10": Rating, "RATE11": Rating, "RATE12": Rating,
                                 "STAT": Status, "NSTAT": int, "MET": int, "STYPE": int, "NAME": Name},
     'TRANSFORMER': [
         {"I": BusId, "J": BusId, "K": BusId, "CKT": IdStr, "CW": int, "CZ": int, "CM": int, "MAG1": float,
          "MAG2": float, "NMETR": int, "NAME": Name, "STAT": Status, "O1": OwnerId, "F1": float, "O2": OwnerId,
          "F2": float, "O3": OwnerId, "F3": float, "O4": OwnerId, "F4": float, "VECGRP": str, "ZCOD": int},
         {"R1-2": Resistance, "X1-2": Reactance, "SBASE1-2": float, "R2-3": Resistance, "X2-3": Reactance,
          "SBASE2-3": float, "R3-1": Resistance, "X3-1": Reactance, "SBASE3-1": float, "VMSTAR": float,
          "ANSTAR": float},
         {"WINDV1": float, "NOMV1": Voltage, "ANG1": float, "RATE1-1": Rating, "RATE1-2": Rating,
          "RATE1-3": Rating, "RATE1-4": Rating, "RATE1-5": Rating, "RATE1-6": Rating, "RATE1-7": Rating,
          "RATE1-8": Rating, "RATE1-9": Rating, "RATE1-10": Rating, "RATE1-11": Rating, "RATE1-12": Rating,
          "COD1": int, "CONT1": int, "RMA1": float, "RMI1": float, "VMA1": float, "VMI1": float,
          "NTP1": int, "TAB1": int, "CR1": float, "CX1": float, "CNXA1": float, "NOD1": int},
         {"WINDV2": float, "NOMV2": Voltage, "ANG2": float, "RATE2-1": Rating, "RATE2-2": Rating,
          "RATE2-3": Rating, "RATE2-4": Rating, "RATE2-5": Rating, "RATE2-6": Rating, "RATE2-7": Rating,
          "RATE2-8": Rating, "RATE2-9": Rating, "RATE2-10": Rating, "RATE2-11": Rating, "RATE2-12": Rating,
          "COD2": int, "CONT2": int, "RMA2": float, "RMI2": float, "VMA2": float, "VMI2": float,
          "NTP2": int, "TAB2": int, "CR2": float, "CX2": float, "CNXA2": float, "NOD2": int},
         {"WINDV3": float, "NOMV3": Voltage, "ANG3": float, "RATE3-1": Rating, "RATE3-2": Rating,
          "RATE3-3": Rating, "RATE3-4": Rating, "RATE3-5": Rating, "RATE3-6": Rating, "RATE3-7": Rating,
          "RATE3-8": Rating, "RATE3-9": Rating, "RATE3-10": Rating, "RATE3-11": Rating, "RATE3-12": Rating,
          "COD3": int, "CONT3": int, "RMA3": float, "RMI3": float, "VMA3": float, "VMI3": float,
          "NTP3": int, "TAB3": int, "CR3": float, "CX3": float, "CNXA3": float, "NOD3": int}],
     'TWO-TERMINAL DC': [{"NAME": Name, "MDC": int, "RDC": float, "SETVL": float, "VSCHD": float, "VCMOD": float,
                          "RCOMP": float, "DELTI": float, "METER": str, "DCVMIN": float, "CCCITMX": int,
                          "CCCACC": float},
                         {"IPR": int, "NBR": int, "ANMXR": float, "ANMNR": float, "RCR": float, "XCR": float,
                          "EBASR": float, "TRR": float, "TAPR": float, "TMXR": float, "TMNR": float, "STPR": float,
                          "ICR": int, "IFR": int, "ITR": int, "IDR": str, "XCAPR": float, "NDR": int},
                         {"IPI": int, "NBI": int, "ANMXI": float, "ANMNI": float, "RCI": float, "XCI": float,
                          "EBASI": float, "TRI": float, "TAPI": float, "TMXI": float, "TMNI": float, "STPI": float,
                          "ICI": int, "IFI": int, "ITI": int, "IDI": str, "XCAPI": float, "NDI": int}],
     'VSC DC LINE': [
         {"NAME": Name, "MDC": int, "RDC": float, "O1": OwnerId, "F1": str, "O2": OwnerId, "F2": str, "O3": OwnerId,
          "F3": str, "O4": OwnerId, "F4": str},
         {"IBUS": int, "TYPE1": int, "MODE1": int, "DCSET1": float, "ACSET1": float, "ALOSS1": float,
          "BLOSS1": float, "MINLOSS1": float, "SMAX1": float, "IMAX1": str, "PWF1": float,
          "MAXQ1": float, "MINQ1": float, "VSREG1": int, "RMPCT1": float, "NREG1": int},
         {"JBUS": BusId, "TYPE2": int, "MODE2": int, "DCSET2": float, "ACSET2": float, "ALOSS2": float,
          "BLOSS2": float, "MINLOSS2": float, "SMAX2": float, "IMAX2": str, "PWF2": float,
          "MAXQ2": float, "MINQ2": float, "VSREG2": int, "RMPCT2": float, "NREG2": int}],
     'ZONE': {"I": IdInt, "ZONAME": Name}}

RAW_DATA = {k: list(v.keys()) if isinstance(v, dict) else [list(_.keys()) for _ in v]
            for k, v in DTYPE_RAW_DATA.items()}
# DTYPE_HEADERKEYS = DTYPE_RAW_DATA['HEADER']

MULTILINECOMPONENTS = ["TRANSFORMER", "TWO-TERMINAL DC", "VSC DC LINE", "IMPEDANCE CORRECTION", "MULTI-TERMINAL DC"]

DTYPE_SEQ_DATA = \
    {'GENERATOR': {"I": BusId, "ID": IdStr, "ZRPOS": float, "ZXPPDV": float,
                   "ZXPDV": float, "ZXSDV": float, "ZRNEG": float,
                   "ZXNEGDV": float, "ZR0": float, "ZX0DV": float, "CZG": int,
                   "ZRG": float, "ZXG": float, "REFDEG": float},
     'INDUCTION MACHINE': {"I": BusId, "ID": IdStr, "CZG": str, "GRDFLG": str,
                           "ILR2IR": str, "RTOX": str, "ZR0": str, "ZX0": str,
                           "ZRG": str, "ZXG": str, "ILR2IR_TRN": str,
                           "RTOX_TRN": str, "ILR2IR_NEG": str, "RTOX_NEG1": str},
     'LOAD': {"I": BusId, "ID": IdStr, "PNEG": float, "QNEG": float,
              "GRDFLG": float, "PZERO": float, "QZERO": float},
     'NON CONVENTIONAL SOURCE FAULT CONTRIBUTION': {"I": BusId, "ID": IdStr,
            "T1": float, "C1P": float, "C1Q": float,
            "T2": float, "C2P": float, "C2Q": float, "T3": float, "C3P": float,
            "C3Q": float, "T4": float, "C4P": float, "C4Q": float, "T5": float,
            "C5P": float, "C5Q": float, "T6": float, "C6P": float, "C6Q": float},
     'ZERO SEQ. FIXED SHUNT': {"I": BusId, "ID": IdStr, "GSZERO": float, "BSZERO": float},
     'ZERO SEQ. MUTUAL': {"I": BusId, "J": BusId, "ICKT1": str, "K": BusId, "L": BusId,
                          "'ICKT2'": str, "RM": str, "XM": str, "BIJ1": str,
                          "BIJ2": str, "BKL1": str, "BKL2": str},
     'ZERO SEQ. NON-TRANSFORMER BRANCH': {"I": BusId, "J": BusId, "ICKT": IdStr, "RLINZ": float, "XLINZ": float, "BCHZ": float,
                                         "GI": float, "BI": float, "GJ": float, "BJ": float, "IPR": float, "SCTYP": int},
     'ZERO SEQ. SWITCHED SHUNT': {"I": BusId, "BZ1": float, "BZ2": float, "BZ3": float, "BZ4": float, "BZ5": float,
                                  "BZ6": float, "BZ7": float, "BZ8": float},
     'ZERO SEQ. TRANSFORMER': [{"I": int, "J": int, "K": int, "ICKT": str, "CZ0": int, "CZG": int, "CC": int,
                                  "RG1": float, "XG1": float, "R01": float, "X01": float, "RG2": float, "XG2": float,
                                  "R02": float, "X02": float, "RNUTRL": float, "XNUTRL": float},
                               {"I": int, "J": int, "K": int, "ICKT": str, "CZ0": int, "CZG": int, "CC": int,
                                "RG1": float, "XG1": float, "R01": float, "X01": float, "RG2": float, "XG2": float,
                                "R02": float, "X02": float, "RG3": float, "XG3": float, "R03": float, "X03": float,
                                "RNUTRL": float, "XNUTRL": float}]}

SEQ_DATA = {k: list(v.keys()) if isinstance(v, dict) else [list(_.keys()) for _ in v]
            for k, v in DTYPE_SEQ_DATA.items()}

# To recreate *KEYS items below:
# for k, v in DTYPE_SEQ_DATA.items():
#     if isinstance(v, dict):
#         print(f"{k.replace(' ', '').replace('-', '').replace('.', '')}KEYS = list(DTYPE_SEQ_DATA['{k}'].keys())")
#     elif isinstance(v, list):
#         print(f"{k.replace(' ', '').replace('-', '').replace('.', '')}KEYS = [k for lst in DTYPE_SEQ_DATA['{k}'] for k in lst.keys()]")
#     else:
#         print("???", k)
GENERATORKEYS = list(DTYPE_SEQ_DATA['GENERATOR'].keys())
LOADKEYS = list(DTYPE_SEQ_DATA['LOAD'].keys())
ZEROSEQMUTUALKEYS = list(DTYPE_SEQ_DATA['ZERO SEQ. MUTUAL'].keys())
ZEROSEQNONTRANSFORMERBRANCHKEYS = list(DTYPE_SEQ_DATA['ZERO SEQ. NON-TRANSFORMER BRANCH'].keys())
ZEROSEQTRANSFORMERKEYS = [k for lst in DTYPE_SEQ_DATA['ZERO SEQ. TRANSFORMER'] for k in lst.keys()]
ZEROSEQSWITCHEDSHUNTKEYS = list(DTYPE_SEQ_DATA['ZERO SEQ. SWITCHED SHUNT'].keys())
ZEROSEQFIXEDSHUNTKEYS = list(DTYPE_SEQ_DATA['ZERO SEQ. FIXED SHUNT'].keys())
INDUCTIONMACHINEKEYS = list(DTYPE_SEQ_DATA['INDUCTION MACHINE'].keys())
NONCONVENTIONALSOURCEFAULTCONTRIBUTIONKEYS = list(DTYPE_SEQ_DATA['NON CONVENTIONAL SOURCE FAULT CONTRIBUTION'].keys())


def section_to_prop_name(section_name: str) -> str:
    """Convert a section name from a raw file to a Model property/attribute
    name like 'MULTI-TERMINAL DC' to 'multi_terminal_dc_df'
    or 'HEADER' to 'header'.
    """
    result = section_name.lower().strip().replace(' ', "_")
    result = result.replace('-', "_").replace(',', '')
    if "header" not in result and not result.endswith('_df'):
        result += '_df'
    return result


def raw_section_to_prop_name_map() -> dict[str, str]:
    """
    From DTYPE_RAW_DATA as an input, create a dict of
    {.raw file SECTION_NAME: Model attribute name}.
    :return: dict of {section name: Model attribute name}
    """
    return {section_name: section_to_prop_name(section_name)
            for section_name in DTYPE_RAW_DATA.keys()}


def raw_prop_to_section_name_map() -> dict[str, str]:
    return {v: k for k, v in raw_section_to_prop_name_map().items()}


RAW_SECTION_PROP_MAP = raw_section_to_prop_name_map()
RAW_PROP_SECTION_MAP = raw_prop_to_section_name_map()