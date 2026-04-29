from textwrap import dedent

"""
PowerGEM incremental change (INCH) files are used to modify the power system
model.  This module introduces the INCH_TEMPLATE constant to support creation
of the INCH files using this library (psse_model_util.Inch class).

INCH_TEMPLATE (dict) is a metadata dict of INCH action definitions/specifications.
It contains all metadata needed to creat the INCH file.  Actual data values are
not included and must be provided.  Use the INCH_TEMPLATE, data values and other
code to create INCH files.

command (str): the INCH file command recognized by PowerGEM TARA software.
inch_fields list[str]: valid INCH file field names
rawx_section (str): a valid section name in a RAWX file, such as 'bus',
                    'acline', 'generator', etc.
rawx_fields (list[str]): list of corresponding model.Model.network dataframe
                         field names
template (str): template section of INCH file.
                line 1: // comment
                line 2: #COMMAND [csv INCH field name list]
                line 3: csv value list
"""

INCH_TEMPLATE = {
    'ADD_BUS': {'command': '#ADD_BUS',
                'inch_fields': ['BusNum', 'BusName', 'BusNomVolt', 'BusType', 'AreaNum', 'ZoneNum', 'OwnerNum',
                                'BusVoltPU', 'BusAngle', 'VmaxNorm', 'VminNorm', 'VmaxCont', 'VminCont'],
                'rawx_section': 'bus',
                'rawx_fields': ['ibus', 'name', 'baskv', 'ide', 'area', 'zone', 'owner', 'vm', 'va',
                                'nvhi', 'nvlo', 'evhi', 'evlo'],  # If it breaks, try removing the last four parameters
                'template': dedent('''
                           //ADD NEW BUS DATA
                           #ADD_BUS [BusNum,BusName,BusNomVolt,BusType,AreaNum,ZoneNum,OwnerNum,BusVoltPU,BusAngle,VmaxNorm,VminNorm,VmaxCont,VminCont]
                           ibus,name,baskv,ide,area,zone,owner,vm,va,nvhi,nvlo,evhi,evlo
                           #END
                           ''').strip('\n\t')
                },

    'MODIFY_BUS': {'command': '#MODIFY_BUS',
        'inch_fields': ['BusNum', 'BusName', 'BusNomVolt', 'BusType', 'AreaNum', 'ZoneNum', 'OwnerNum', 'BusVoltPU',
                        'BusAngle', 'VmaxNorm', 'VminNorm', 'VmaxCont', 'VminCont'],
        'rawx_section': 'bus',
        'rawx_fields': ['ibus', 'name', 'baskv', 'ide', 'area', 'zone', 'owner', 'vm', 'va', 'nvhi', 'nvlo', 'evhi',
                        'evlo'],
        'template': dedent('''
                   //MODIFY BUS DATA
                   #MODIFY_BUS [BusNum,BusName,BusNomVolt,BusType,AreaNum,ZoneNum,OwnerNum,BusVoltPU,BusAngle,VmaxNorm,VminNorm,VmaxCont,VminCont]
                   ibus,'name        ',baskv,ide,area,zone,owner,vm,va,nvhi,nvlo,evhi,evlo
                   #END
                   ''').strip('\n\t')
    },

    'MODIFY_BUS_NUMBER': {'command': '#MODIFY_BUS',
        'inch_fields': ['BusNum', 'BusNumChn'],
        'rawx_section': 'bus',
        'rawx_fields': ['ibus', 'new ibus'],
        'template': dedent('''
                   //MODIFY ONLY BUS NUMBER
                   #MODIFY_BUS [BusNum,BusNumChn]
                   ibus,new ibus
                   #END
                   ''').strip('\n\t')
    },

    'DELETE_BUS': {'command': '#DELETE_BUS',
        'inch_fields': ['BusNum'],
        'rawx_section': 'bus',
        'rawx_fields': ['ibus'],
        'template': dedent('''
                   //DELETE BUS DATA
                   #DELETE_BUS [BusNum]
                   ibus
                   #END
                   ''').strip('\n\t')
    },

    'ADD_LOAD': {'command': '#ADD_LOAD',
        'inch_fields': ['BusNum', 'LoadID', 'Status', 'LoadArea', 'LoadZone', 'LoadOwner', 'ConfrmFlag', 'LoadP0',
                        'LoadQ0', 'LoadP1', 'LoadQ1', 'LoadP2', 'LoadQ2'],
        'rawx_section': 'load',
        'rawx_fields': ['ibus', 'loadid', 'stat', 'area', 'zone', 'owner', 'scale', 'pl', 'ql', 'ip', 'iq', 'yp', 'yq'],
        'template': dedent('''
                   //ADD NEW LOAD DATA
                   #ADD_LOAD [BusNum,LoadID,Status,LoadArea,LoadZone,LoadOwner,ConfrmFlag,LoadP0,LoadQ0,LoadP1,LoadQ1,LoadP2,LoadQ2]
                   ibus,loadid,stat,area,zone,owner,scale,pl,ql,ip,iq,yp,yq
                   #END
                   ''').strip('\n\t')

    },

    'MODIFY_LOAD': {'command': '#MODIFY_LOAD',
        'inch_fields': ['BusNum', 'LoadID', 'Status', 'LoadArea', 'LoadZone', 'LoadOwner', 'ConfrmFlag', 'LoadP0',
                        'LoadQ0', 'LoadP1', 'LoadQ1', 'LoadP2', 'LoadQ2'],
        'rawx_section': 'load',
        'rawx_fields': ['ibus', 'loadid', 'stat', 'area', 'zone', 'owner', 'scale', 'pl', 'ql', 'ip', 'iq', 'yp', 'yq'],
        'template': dedent('''
                   //MODIFY LOAD DATA
                   #MODIFY_LOAD [BusNum,LoadID,Status,LoadArea,LoadZone,LoadOwner,ConfrmFlag,LoadP0,LoadQ0,LoadP1,LoadQ1,LoadP2,LoadQ2]
                   ibus,loadid,stat,area,zone,owner,scale,pl,ql,ip,iq,yp,yq
                   #END
                   ''').strip('\n\t')

    },
    'MODIFY_LOAD_BUS_NUMBER': {'command': '#MODIFY_LOAD',
        'inch_fields': ['BusNum', 'LoadID', 'BusNumChn'],
        'rawx_section': 'load',
        'rawx_fields': ['ibus', 'loadid', 'new ibus'],
        'template': dedent('''
                   //MODIFY ONLY LOAD BUS NUMBER
                   #MODIFY_LOAD [BusNum,LoadID,BusNumChn]
                   ibus,loadid,new ibus
                   #END
                   ''').strip('\n\t')

    },
    'DELETE_LOAD': {'command': '#DELETE_LOAD',
        'inch_fields': ['BusNum', 'LoadID'],
        'rawx_section': 'load',
        'rawx_fields': ['ibus', 'loadid'],
        'template': dedent('''
                   //DELETE LOAD DATA
                   #DELETE_LOAD [BusNum, LoadID]
                   ibus,loadid
                   #END
                   ''').strip('\n\t')

    },
    'ADD_FXSHUNT': {'command': '#ADD_FXSHUNT',
        'inch_fields': ['BusNum', 'ShuntID', 'Status', 'ShuntMW', 'ShuntMVAr'],
        'rawx_section': 'fixshunt',
        'rawx_fields': ['ibus', 'shntid', 'stat', 'gl', 'bl'],
        'template': dedent('''
                   //ADD NEW FIXED SHUNT DATA
                   #ADD_FXSHUNT [BusNum,ShuntID,Status,ShuntMW,ShuntMVAr]
                   ibus,shntid,stat,gl,bl
                   #END
                   ''').strip('\n\t')

    },
    'MODIFY_FXSHUNT': {'command': '#MODIFY_FXSHUNT',
        'inch_fields': ['BusNum', 'ShuntID', 'Status', 'ShuntMW', 'ShuntMVAr'],
        'rawx_section': 'fixshunt',
        'rawx_fields': ['ibus', 'shntid', 'stat', 'gl', 'bl'],
        'template': dedent('''
                   //MODIFY FIXED SHUNT DATA
                   #MODIFY_FXSHUNT [BusNum,ShuntID,Status,ShuntMW,ShuntMVAr]
                   ibus,shntid,stat,gl,bl
                   #END
                   ''').strip('\n\t')


    },
    'MODIFY_FXSHUNT_BUS_NUMBER': {'command': '#MODIFY_FXSHUNT',
        'inch_fields': ['BusNum', 'ShuntID', 'BusNumChn'],
        'rawx_section': 'fixshunt',
        'rawx_fields': ['ibus', 'shntid', 'new ibus'],
        'template': dedent('''
                   //MODIFY ONLY FIXED SHUNT BUS NUMBER
                   #MODIFY_FXSHUNT [BusNum,ShuntID,BusNumChn]
                   ibus,shntid,new ibus
                   #END
                   ''').strip('\n\t')

    },
    'DELETE_FXSHUNT': {'command': '#DELETE_FXSHUNT',
        'inch_fields': ['BusNum', 'ShuntID'],
        'rawx_section': 'fixshunt',
        'rawx_fields': ['ibus', 'shntid'],
        'template': dedent('''
                   //DELETE FIXED SHUNT DATA
                   #DELETE_FXSHUNT [BusNum, ShuntID]
                   ibus,shntid
                   #END
                   ''').strip('\n\t')

    },
    'ADD_SWSHUNT': {'command': '#ADD_SWSHUNT',
        'inch_fields': ['BusNum', 'Mode', 'Status', 'BlockOrder', 'VMIN', 'VMAX', 'BShuntCur', 'CtlBs#', 'RemPcnt',
                        'NBank1', 'BankSize1', 'NBank2', 'BankSize2', 'NBank3', 'BankSize3', 'NBank4', 'BankSize4',
                        'NBank5', 'BankSize5', 'NBank6', 'BankSize6', 'NBank7', 'BankSize7', 'NBank8', 'BankSize8',
                        'NBank9', 'BankSize9', 'NBank10', 'BankSize10', 'NBank11', 'BankSize11', 'NBank12',
                        'BankSize12'],
        'rawx_section': 'swshunt',
        'rawx_fields': ['ibus', 'modsw', 'stat', 'adjm', 'vswlo', 'vswhi', 'binit', 'swreg', 'rmpct', 'n1', 'b1', 'n2',
                        'b2', 'n3', 'b3', 'n4', 'b4', 'n5', 'b5', 'n6', 'b6', 'n7', 'b7', 'n8', 'b8', 'n9', 'b9', 'n10',
                        'b10', 'n11', 'b11', 'n12', 'b12'],
        'template': dedent('''
                   //ADD NEW SWITCHED SHUNT DATA
                   #ADD_SWSHUNT [BusNum,Mode,Status,BlockOrder,VMIN,VMAX,BShuntCur,CtlBs#,RemPcnt,NBank1,BankSize1,NBank2,BankSize2,NBank3,BankSize3,NBank4,BankSize4,NBank5,BankSize5,NBank6,BankSize6,NBank7,BankSize7,NBank8,BankSize8,NBank9,BankSize9,NBank10,BankSize10,NBank11,BankSize11,NBank12,BankSize12]
                   ibus,modsw,stat,adjm,vswlo,vswhi,binit,swreg,rmpct,n1,b1,n2,b2,n3,b3,n4,b4,n5,b5,n6,b6,n7,b7,n8,b8,n9,b9,n10,b10,n11,b11,n12,b12
                   #END
                   ''').strip('\n\t')

    },
    'MODIFY_SWSHUNT': {'command': '#MODIFY_SWSHUNT',
        'inch_fields': ['BusNum', 'Mode', 'Status', 'BlockOrder', 'VMIN', 'VMAX', 'BShuntCur', 'CtlBs#', 'RemPcnt',
                        'NBank1', 'BankSize1', 'NBank2', 'BankSize2', 'NBank3', 'BankSize3', 'NBank4', 'BankSize4',
                        'NBank5', 'BankSize5', 'NBank6', 'BankSize6', 'NBank7', 'BankSize7', 'NBank8', 'BankSize8',
                        'NBank9', 'BankSize9', 'NBank10', 'BankSize10', 'NBank11', 'BankSize11', 'NBank12',
                        'BankSize12'],
        'rawx_section': 'swshunt',
        'rawx_fields': ['ibus', 'modsw', 'stat', 'adjm', 'vswlo', 'vswhi', 'binit', 'swreg', 'rmpct', 'n1', 'b1', 'n2',
                        'b2', 'n3', 'b3', 'n4', 'b4', 'n5', 'b5', 'n6', 'b6', 'n7', 'b7', 'n8', 'b8', 'n9', 'b9', 'n10',
                        'b10', 'n11', 'b11', 'n12', 'b12'],
        'template': dedent('''
                   //MODIFY SWITCHED SHUNT DATA
                   #MODIFY_SWSHUNT [BusNum,Mode,Status,BlockOrder,VMIN,VMAX,BShuntCur,CtlBs#,RemPcnt,NBank1,BankSize1,NBank2,BankSize2,NBank3,BankSize3,NBank4,BankSize4,NBank5,BankSize5,NBank6,BankSize6,NBank7,BankSize7,NBank8,BankSize8,NBank9,BankSize9,NBank10,BankSize10,NBank11,BankSize11,NBank12,BankSize12]
                   ibus,modsw,stat,adjm,vswlo,vswhi,binit,swreg,rmpct,n1,b1,n2,b2,n3,b3,n4,b4,n5,b5,n6,b6,n7,b7,n8,b8,n9,b9,n10,b10,n11,b11,n12,b12
                   #END
                   ''').strip('\n\t')

    },
    'MODIFY_SWSHUNT_BUS_NUMBER': {'command': '#MODIFY_SWSHUNT',
        'inch_fields': ['BusNum', 'ShuntID', 'BusNumChn'],
        'rawx_section': 'swshunt',
        'rawx_fields': ['ibus', 'shntid', 'new ibus'],
        'template': dedent('''
                   //MODIFY ONLY SWITCHED SHUNT BUS NUMBER
                   #MODIFY_SWSHUNT [BusNum,ShuntID,BusNumChn]
                   ibus,shntid,new ibus
                   #END
                   ''').strip('\n\t')

    },
    'DELETE_SWSHUNT': {'command': '#DELETE_SWSHUNT',
        'inch_fields': ['BusNum', 'ShuntID'],
        'rawx_section': 'swshunt',
        'rawx_fields': ['ibus', 'shntid'],
        'template': dedent('''
                   //DELETE SWITCHED SHUNT DATA
                   #DELETE_SWSHUNT [BusNum, ShuntID]
                   ibus,shntid
                   #END
                   ''').strip('\n\t')

    },
    'ADD_GEN': {'command': '#ADD_GEN',
        'inch_fields': ['BusNum', 'GenID', 'Status', 'GenMW', 'GenMVR', 'GenMWMin', 'GenMWMax', 'GenMVRMin',
                        'GenMVRMax', 'GenRMPCT', 'GenRegBusNum', 'VoltTarg', 'MBase', 'RSource', 'XSource', 'RTran',
                        'XTran', 'GenTap', 'Own1', 'Own1%', 'Own2', 'Own2%', 'Own3', 'Own3%', 'Own4', 'Own4%'],
        'rawx_section': 'generator',
        'rawx_fields': ['ibus', 'machid', 'stat', 'pg', 'qg', 'pb', 'pt', 'qb', 'qt', 'rmpct', 'ireg', 'vs', 'mbase',
                        'zr', 'zx', 'rt', 'xt', 'gtap', 'o1', 'f1', 'o2', 'f2', 'o3', 'f3', 'o4', 'f4'],
        'template': dedent('''
                   //ADD NEW GENERATOR DATA
                   #ADD_GEN [BusNum,GenID,Status,GenMW,GenMVR,GenMWMin,GenMWMax,GenMVRMin,GenMVRMax,GenRMPCT,GenRegBusNum,VoltTarg,MBase,RSource,XSource,RTran,XTran,GenTap,Own1,Own1%,Own2,Own2%,Own3,Own3%,Own4,Own4%]
                   ibus,machid,stat,pg,qg,pb,pt,qb,qt,rmpct,ireg,vs,mbase,zr,zx,rt,xt,gtap,o1,f1,o2,f2,o3,f3,o4,f4
                   #END
                   ''').strip('\n\t')

    },
    'MODIFY_GEN': {'command': '#MODIFY_GEN',
        'inch_fields': ['BusNum', 'GenID', 'Status', 'GenMW', 'GenMVR', 'GenMWMin', 'GenMWMax', 'GenMVRMin',
                        'GenMVRMax', 'GenRMPCT', 'GenRegBusNum', 'VoltTarg', 'MBase', 'RSource', 'XSource', 'RTran',
                        'XTran', 'GenTap', 'Own1', 'Own1%', 'Own2', 'Own2%', 'Own3', 'Own3%', 'Own4', 'Own4%'],
        'rawx_section': 'generator',
        'rawx_fields': ['ibus', 'machid', 'stat', 'pg', 'qg', 'pb', 'pt', 'qb', 'qt', 'rmpct', 'ireg', 'vs', 'mbase',
                        'zr', 'zx', 'rt', 'xt', 'gtap', 'o1', 'f1', 'o2', 'f2', 'o3', 'f3', 'o4', 'f4'],
        'template': dedent('''
                   //MODIFY GENERATOR DATA
                   #MODIFY_GEN [BusNum,GenID,Status,GenMW,GenMVR,GenMWMin,GenMWMax,GenMVRMin,GenMVRMax,GenRMPCT,GenRegBusNum,VoltTarg,MBase,RSource,XSource,RTran,XTran,GenTap,Own1,Own1%,Own2,Own2%,Own3,Own3%,Own4,Own4%]
                   ibus,machid,stat,pg,qg,pb,pt,qb,qt,rmpct,ireg,vs,mbase,zr,zx,rt,xt,gtap,o1,f1,o2,f2,o3,f3,o4,f4
                   #END
                   ''').strip('\n\t')

    },
    'MODIFY_GEN_BUS_NUMBER': {'command': '#MODIFY_GEN',
        'inch_fields': ['BusNum', 'GenID', 'BusNumChn'],
        'rawx_section': 'generator',
        'rawx_fields': ['ibus', 'machid', 'new ibus'],
        'template': dedent('''
                   //MODIFY ONLY GENERATOR BUS NUMBER
                   #MODIFY_GEN [BusNum,GenID,BusNumChn]
                   ibus,machid,new ibus
                   #END
                   ''').strip('\n\t')

    },
    'DELETE_GEN': {'command': '#DELETE_GEN',
        'inch_fields': ['BusNum', 'GenID'],
        'rawx_section': 'generator',
        'rawx_fields': ['ibus', 'machid'],
        'template': dedent('''
                   //DELETE GENERATOR DATA
                   #DELETE_GEN [BusNum, GenID]
                   ibus,machid
                   #END
                   ''').strip('\n\t')

    },
    'ADD_BRANCH': {'command': '#ADD_BRANCH',
        'inch_fields': ['BusNumFr', 'BusNumTo', 'CKT', 'Mt', 'Status', 'LineR', 'LineX', 'Charge', 'ShuntGFr',
                        'ShuntBFr', 'ShuntGTo', 'ShuntBTo', 'Rate1', 'Rate2', 'Rate3', 'Rate4', 'Rate5', 'Rate6',
                        'Rate7', 'Rate8', 'Rate9', 'Rate10', 'Rate11', 'Rate12', 'Length', 'BranchName', 'Own1',
                        'Own1%', 'Own2', 'Own2%', 'Own3', 'Own3%', 'Own4', 'Own4%'],
        'rawx_section': 'acline',
        'rawx_fields': ['ibus', 'jbus', 'ckt', 'method', 'stat', 'rpu', 'xpu', 'bpu', 'gi', 'bi', 'gj', 'bj', 'rate1',
                        'rate2', 'rate3', 'rate4', 'rate5', 'rate6', 'rate7', 'rate8', 'rate9', 'rate10', 'rate11',
                        'rate12', 'len', 'name', 'o1', 'f1', 'o2', 'f2', 'o3', 'f3', 'o4', 'f4'],
        'template': dedent('''
                   //ADD NEW BRANCH DATA
                   #ADD_BRANCH [BusNumFr,BusNumTo,CKT,Mt,Status,LineR,LineX,Charge,ShuntGFr,ShuntBFr,ShuntGTo,ShuntBTo,Rate1,Rate2,Rate3,Rate4,Rate5,Rate6,Rate7,Rate8,Rate9,Rate10,Rate11,Rate12,Length,BranchName,Own1,Own1%,Own2,Own2%,Own3,Own3%,Own4,Own4%]
                   ibus,jbus,ckt,method,stat,rpu,xpu,bpu,gi,bi,gj,bj,rate1,rate2,rate3,rate4,rate5,rate6,rate7,rate8,rate9,rate10,rate11,rate12,len,name,o1,f1,o2,f2,o3,f3,o4,f4
                   #END
                   ''').strip('\n\t')

    },
    'MODIFY_BRANCH': {'command': '#MODIFY_BRANCH',
        'inch_fields': ['BusNumFr', 'BusNumTo', 'CKT', 'Mt', 'Status', 'LineR', 'LineX', 'Charge', 'ShuntGFr',
                        'ShuntBFr', 'ShuntGTo', 'ShuntBTo', 'Rate1', 'Rate2', 'Rate3', 'Rate4', 'Rate5', 'Rate6',
                        'Rate7', 'Rate8', 'Rate9', 'Rate10', 'Rate11', 'Rate12', 'Length', 'BranchName', 'Own1',
                        'Own1%', 'Own2', 'Own2%', 'Own3', 'Own3%', 'Own4', 'Own4%'],
        'rawx_section': 'acline',
        'rawx_fields': ['ibus', 'jbus', 'ckt', 'method', 'stat', 'rpu', 'xpu', 'bpu', 'gi', 'bi', 'gj', 'bj', 'rate1',
                        'rate2', 'rate3', 'rate4', 'rate5', 'rate6', 'rate7', 'rate8', 'rate9', 'rate10', 'rate11',
                        'rate12', 'len', 'name', 'o1', 'f1', 'o2', 'f2', 'o3', 'f3', 'o4', 'f4'],
        'template': dedent('''
                   //MODIFY BRANCH DATA
                   #MODIFY_BRANCH [BusNumFr,BusNumTo,CKT,Mt,Status,LineR,LineX,Charge,ShuntGFr,ShuntBFr,ShuntGTo,ShuntBTo,Rate1,Rate2,Rate3,Rate4,Rate5,Rate6,Rate7,Rate8,Rate9,Rate10,Rate11,Rate12,Length,BranchName,Own1,Own1%,Own2,Own2%,Own3,Own3%,Own4,Own4%]
                   ibus,jbus,ckt,method,stat,rpu,xpu,bpu,gi,bi,gj,bj,rate1,rate2,rate3,rate4,rate5,rate6,rate7,rate8,rate9,rate10,rate11,rate12,len,name,o1,f1,o2,f2,o3,f3,o4,f4
                   #END
                   ''').strip('\n\t')

    },
    'DELETE_BRANCH': {'command': '#DELETE_BRANCH',
        'inch_fields': ['BusNumFr', 'BusNumTo', 'CKT'],
        'rawx_section': 'acline',
        'rawx_fields': ['ibus', 'jbus', 'ckt'],
        'template': dedent('''
                   //DELETE BRANCH DATA
                   #DELETE_BRANCH [BusNumFr, BusNumTo, CKT]
                   ibus,jbus,ckt
                   #END
                   ''').strip('\n\t')

    },
    'ADD_TRANSFORMER': {'command': '#ADD_TRANSFORMER',
        'inch_fields': ['W1Bus#', 'W2Bus#', 'W3Bus#', 'CKT', 'XfmrName', 'Status', 'CW', 'CZ', 'CM', 'MAG1', 'MAG2',
                        'MtBus', 'R1-2', 'X1-2', 'SBAS1', 'R2-3', 'X2-3', 'SBAS2', 'R3-1', 'X3-1', 'SBAS3', 'Own1',
                        'Own1%', 'Own2', 'Own2%', 'Own3', 'Own3%', 'Own4', 'Own4%', 'W1WINV', 'W1NOMV', 'W1ANG',
                        'W1Rate1', 'W1Rate2', 'W1Rate3', 'W1Rate4', 'W1Rate5', 'W1Rate6', 'W1Rate7', 'W1Rate8',
                        'W1Rate9', 'W1Rate10', 'W1Rate11', 'W1Rate12', 'W1AdjStatus', 'W1CtrlBus', 'W1RegulMax',
                        'W1RegulMin', 'W1TargetMax', 'W1TargetMin', 'W1NumTapPos', 'W1NTable', 'W1LDropR', 'W1LDropX',
                        'W2WINV', 'W2NOMV', 'W2ANG', 'W2Rate1', 'W2Rate2', 'W2Rate3', 'W2Rate4', 'W2Rate5', 'W2Rate6',
                        'W2Rate7', 'W2Rate8', 'W2Rate9', 'W2Rate10', 'W2Rate11', 'W2Rate12', 'W2AdjStatus', 'W2CtrlBus',
                        'W2RegulMax', 'W2RegulMin', 'W2TargetMax', 'W2TargetMin', 'W2NumTapPos', 'W2NTable', 'W2LDropR',
                        'W2LDropX', 'W3WINV', 'W3NOMV', 'W3ANG', 'W3Rate1', 'W3Rate2', 'W3Rate3', 'W3Rate4', 'W3Rate5',
                        'W3Rate6', 'W3Rate7', 'W3Rate8', 'W3Rate9', 'W3Rate10', 'W3Rate11', 'W3Rate12', 'W3AdjStatus',
                        'W3CtrlBus', 'W3RegulMax', 'W3RegulMin', 'W3TargetMax', 'W3TargetMin', 'W3NumTapPos',
                        'W3NTable', 'W3LDropR', 'W3LDropX'],
        'rawx_section': 'transformer',
        'rawx_fields': ['ibus', 'jbus', 'kbus', 'ckt', 'name', 'stat', 'cw', 'cz', 'cm', 'mag1', 'mag2', 'nmet', 'r1-2',
                        'x1-2', 'sbase1_2', 'r2-3', 'x2-3', 'sbase2_3', 'r3-1', 'x3-1', 'sbase3_1', 'o1', 'f1', 'o2',
                        'f2', 'o3', 'f3', 'o4', 'f4', 'windv1', 'nomv1', 'ang1', 'wdg1rate1', 'wdg1rate3', 'wdg1rate4',
                        'wdg1rate5', 'wdg1rate6', 'wdg1rate7', 'wdg1rate8', 'wdg1rate9', 'wdg1rate10', 'wdg1rate11',
                        'wdg1rate12', 'cod1', 'cont1', 'rma1', 'rmi1', 'vma1', 'vmi1', 'ntp1', 'tab1', 'cr1', 'cx1',
                        'windv2', 'nomv2', 'ang2', 'wdg2rate1', 'wdg2rate3', 'wdg2rate4', 'wdg2rate5', 'wdg2rate6',
                        'wdg2rate7', 'wdg2rate8', 'wdg2rate9', 'wdg2rate10', 'wdg2rate11', 'wdg2rate12', 'cod2',
                        'cont2', 'rma2', 'rmi2', 'vma2', 'vmi2', 'ntp2', 'tab2', 'cr2', 'cx2', 'windv3', 'nomv3',
                        'ang3', 'wdg3rate1', 'wdg3rate3', 'wdg3rate4', 'wdg3rate5', 'wdg3rate6', 'wdg3rate7',
                        'wdg3rate8', 'wdg3rate9', 'wdg3rate10', 'wdg3rate11', 'wdg3rate12', 'cod3', 'cont3', 'rma3',
                        'rmi3', 'vma3', 'vmi3', 'ntp3', 'tab3', 'cr3', 'cx3'],
        'template': dedent('''
                   //ADD NEW TRANSFORMER DATA
                   #ADD_TRANSFORMER [W1Bus#,W2Bus#,W3Bus#,CKT ,XfmrName,Status,CW,CZ,CM,MAG1,MAG2,MtBus,R1-2,X1-2,SBAS1,R2-3,X2-3,SBAS2,R3-1,X3-1,SBAS3,Own1,Own1%,Own2,Own2%,Own3,Own3%,Own4,Own4%,W1WINV,W1NOMV,W1ANG,W1Rate1,W1Rate2,W1Rate3,W1Rate4,W1Rate5,W1Rate6,W1Rate7,W1Rate8,W1Rate9,W1Rate10,W1Rate11,W1Rate12,W1AdjStatus,W1CtrlBus,W1RegulMax,W1RegulMin,W1TargetMax,W1TargetMin,W1NumTapPos,W1NTable,W1LDropR,W1LDropX,W2WINV,W2NOMV,W2ANG,W2Rate1,W2Rate2,W2Rate3,W2Rate4,W2Rate5,W2Rate6,W2Rate7,W2Rate8,W2Rate9,W2Rate10,W2Rate11,W2Rate12,W2AdjStatus,W2CtrlBus,W2RegulMax,W2RegulMin,W2TargetMax,W2TargetMin,W2NumTapPos,W2NTable,W2LDropR,W2LDropX,W3WINV,W3NOMV,W3ANG,W3Rate1,W3Rate2,W3Rate3,W3Rate4,W3Rate5,W3Rate6,W3Rate7,W3Rate8,W3Rate9,W3Rate10,W3Rate11,W3Rate12,W3AdjStatus,W3CtrlBus,W3RegulMax,W3RegulMin,W3TargetMax,W3TargetMin,W3NumTapPos,W3NTable,W3LDropR,W3LDropX]
                   ibus,jbus,kbus,ckt,'name',stat,cw,cz,cm,mag1,mag2,nmet,r1-2,x1-2,sbase1_2,r2-3,x2-3,sbase2_3,r3-1,x3-1,sbase3_1,o1,f1,o2,f2,o3,f3,o4,f4,windv1,nomv1,ang1,wdg1rate1,wdg1rate3,wdg1rate4,wdg1rate5,wdg1rate6,wdg1rate7,wdg1rate8,wdg1rate9,wdg1rate10,wdg1rate11,wdg1rate12,cod1,cont1,rma1,rmi1,vma1,vmi1,ntp1,tab1,cr1,cx1,windv2,nomv2,ang2,wdg2rate1,wdg2rate3,wdg2rate4,wdg2rate5,wdg2rate6,wdg2rate7,wdg2rate8,wdg2rate9,wdg2rate10,wdg2rate11,wdg2rate12,cod2,cont2,rma2,rmi2,vma2,vmi2,ntp2,tab2,cr2,cx2,windv3,nomv3,ang3,wdg3rate1,wdg3rate3,wdg3rate4,wdg3rate5,wdg3rate6,wdg3rate7,wdg3rate8,wdg3rate9,wdg3rate10,wdg3rate11,wdg3rate12,cod3,cont3,rma3,rmi3,vma3,vmi3,ntp3,tab3,cr3,cx3
                   #END
                   ''').strip('\n\t')

    },

    'MODIFY_TRANSFORMER': {'command': '#MODIFY_TRANSFORMER',
        'inch_fields': ['W1Bus#', 'W2Bus#', 'W3Bus#', 'CKT', 'XfmrName', 'Status', 'CW', 'CZ', 'CM', 'MAG1', 'MAG2',
                        'MtBus', 'R1-2', 'X1-2', 'SBAS1', 'R2-3', 'X2-3', 'SBAS2', 'R3-1', 'X3-1', 'SBAS3', 'Own1',
                        'Own1%', 'Own2', 'Own2%', 'Own3', 'Own3%', 'Own4', 'Own4%', 'W1WINV', 'W1NOMV', 'W1ANG',
                        'W1Rate1', 'W1Rate2', 'W1Rate3', 'W1Rate4', 'W1Rate5', 'W1Rate6', 'W1Rate7', 'W1Rate8',
                        'W1Rate9', 'W1Rate10', 'W1Rate11', 'W1Rate12', 'W1AdjStatus', 'W1CtrlBus', 'W1RegulMax',
                        'W1RegulMin', 'W1TargetMax', 'W1TargetMin', 'W1NumTapPos', 'W1NTable', 'W1LDropR', 'W1LDropX',
                        'W2WINV', 'W2NOMV', 'W2ANG', 'W2Rate1', 'W2Rate2', 'W2Rate3', 'W2Rate4', 'W2Rate5', 'W2Rate6',
                        'W2Rate7', 'W2Rate8', 'W2Rate9', 'W2Rate10', 'W2Rate11', 'W2Rate12', 'W2AdjStatus', 'W2CtrlBus',
                        'W2RegulMax', 'W2RegulMin', 'W2TargetMax', 'W2TargetMin', 'W2NumTapPos', 'W2NTable', 'W2LDropR',
                        'W2LDropX', 'W3WINV', 'W3NOMV', 'W3ANG', 'W3Rate1', 'W3Rate2', 'W3Rate3', 'W3Rate4', 'W3Rate5',
                        'W3Rate6', 'W3Rate7', 'W3Rate8', 'W3Rate9', 'W3Rate10', 'W3Rate11', 'W3Rate12', 'W3AdjStatus',
                        'W3CtrlBus', 'W3RegulMax', 'W3RegulMin', 'W3TargetMax', 'W3TargetMin', 'W3NumTapPos',
                        'W3NTable', 'W3LDropR', 'W3LDropX'],
        'rawx_section': 'transformer',
        'rawx_fields': ['ibus', 'jbus', 'kbus', 'ckt', 'name', 'stat', 'cw', 'cz', 'cm', 'mag1', 'mag2', 'nmet', 'r1-2',
                        'x1-2', 'sbase1_2', 'r2-3', 'x2-3', 'sbase2_3', 'r3-1', 'x3-1', 'sbase3_1', 'o1', 'f1', 'o2',
                        'f2', 'o3', 'f3', 'o4', 'f4', 'windv1', 'nomv1', 'ang1', 'wdg1rate1', 'wdg1rate3', 'wdg1rate4',
                        'wdg1rate5', 'wdg1rate6', 'wdg1rate7', 'wdg1rate8', 'wdg1rate9', 'wdg1rate10', 'wdg1rate11',
                        'wdg1rate12', 'cod1', 'cont1', 'rma1', 'rmi1', 'vma1', 'vmi1', 'ntp1', 'tab1', 'cr1', 'cx1',
                        'windv2', 'nomv2', 'ang2', 'wdg2rate1', 'wdg2rate3', 'wdg2rate4', 'wdg2rate5', 'wdg2rate6',
                        'wdg2rate7', 'wdg2rate8', 'wdg2rate9', 'wdg2rate10', 'wdg2rate11', 'wdg2rate12', 'cod2',
                        'cont2', 'rma2', 'rmi2', 'vma2', 'vmi2', 'ntp2', 'tab2', 'cr2', 'cx2', 'windv3', 'nomv3',
                        'ang3', 'wdg3rate1', 'wdg3rate3', 'wdg3rate4', 'wdg3rate5', 'wdg3rate6', 'wdg3rate7',
                        'wdg3rate8', 'wdg3rate9', 'wdg3rate10', 'wdg3rate11', 'wdg3rate12', 'cod3', 'cont3', 'rma3',
                        'rmi3', 'vma3', 'vmi3', 'ntp3', 'tab3', 'cr3', 'cx3'],
        'template': dedent('''
                   //MODIFY TRANSFORMER DATA
                   #MODIFY_TRANSFORMER [W1Bus#,W2Bus#,W3Bus#,CKT ,XfmrName,Status,CW,CZ,CM,MAG1,MAG2,MtBus,R1-2,X1-2,SBAS1,R2-3,X2-3,SBAS2,R3-1,X3-1,SBAS3,Own1,Own1%,Own2,Own2%,Own3,Own3%,Own4,Own4%,W1WINV,W1NOMV,W1ANG,W1Rate1,W1Rate2,W1Rate3,W1Rate4,W1Rate5,W1Rate6,W1Rate7,W1Rate8,W1Rate9,W1Rate10,W1Rate11,W1Rate12,W1AdjStatus,W1CtrlBus,W1RegulMax,W1RegulMin,W1TargetMax,W1TargetMin,W1NumTapPos,W1NTable,W1LDropR,W1LDropX,W2WINV,W2NOMV,W2ANG,W2Rate1,W2Rate2,W2Rate3,W2Rate4,W2Rate5,W2Rate6,W2Rate7,W2Rate8,W2Rate9,W2Rate10,W2Rate11,W2Rate12,W2AdjStatus,W2CtrlBus,W2RegulMax,W2RegulMin,W2TargetMax,W2TargetMin,W2NumTapPos,W2NTable,W2LDropR,W2LDropX,W3WINV,W3NOMV,W3ANG,W3Rate1,W3Rate2,W3Rate3,W3Rate4,W3Rate5,W3Rate6,W3Rate7,W3Rate8,W3Rate9,W3Rate10,W3Rate11,W3Rate12,W3AdjStatus,W3CtrlBus,W3RegulMax,W3RegulMin,W3TargetMax,W3TargetMin,W3NumTapPos,W3NTable,W3LDropR,W3LDropX]
                   ibus,jbus,kbus,ckt,'name',stat,cw,cz,cm,mag1,mag2,nmet,r1-2,x1-2,sbase1_2,r2-3,x2-3,sbase2_3,r3-1,x3-1,sbase3_1,o1,f1,o2,f2,o3,f3,o4,f4,windv1,nomv1,ang1,wdg1rate1,wdg1rate3,wdg1rate4,wdg1rate5,wdg1rate6,wdg1rate7,wdg1rate8,wdg1rate9,wdg1rate10,wdg1rate11,wdg1rate12,cod1,cont1,rma1,rmi1,vma1,vmi1,ntp1,tab1,cr1,cx1,windv2,nomv2,ang2,wdg2rate1,wdg2rate3,wdg2rate4,wdg2rate5,wdg2rate6,wdg2rate7,wdg2rate8,wdg2rate9,wdg2rate10,wdg2rate11,wdg2rate12,cod2,cont2,rma2,rmi2,vma2,vmi2,ntp2,tab2,cr2,cx2,windv3,nomv3,ang3,wdg3rate1,wdg3rate3,wdg3rate4,wdg3rate5,wdg3rate6,wdg3rate7,wdg3rate8,wdg3rate9,wdg3rate10,wdg3rate11,wdg3rate12,cod3,cont3,rma3,rmi3,vma3,vmi3,ntp3,tab3,cr3,cx3
                   #END
                   ''').strip('\n\t')

    },

    'DELETE_TRANSFORMER': {'command': '#DELETE_TRANSFORMER',
        'inch_fields': ['W1Bus#', 'W2Bus#', 'W3Bus#', 'CKT'],
        'rawx_section': 'transformer',
        'rawx_fields': ['ibus', 'jbus', 'kbus', 'ckt'],
        'template': dedent('''
                   //DELETE TRANSFORMER DATA
                   #DELETE_TRANSFORMER [W1Bus#, W2Bus#, W3Bus#, CKT]
                   ibus,jbus,kbus,ckt
                   #END
                   ''').strip('\n\t')

    },

    'ADD_AREA': {'command': '#ADD_AREA',
        'inch_fields': ['AreaNum', 'AreaName', 'DesInter', 'SlackBusNum'],
        'rawx_section': 'area',
        'rawx_fields': ['iarea', 'arname', 'pdes', 'isw'],
        'template': dedent('''
                   //ADD AREA DATA
                   #ADD_AREA [AreaNum,AreaName,DesInter,SlackBusNum]
                   iarea,arname,pdes,isw
                   #END
                   ''').strip('\n\t')

    },

    'MODIFY_AREA': {'command': '#MODIFY_AREA',
        'inch_fields': ['AreaNum', 'AreaName', 'DesInter', 'SlackBusNum'],
        'rawx_section': 'area',
        'rawx_fields': ['iarea', 'arname', 'pdes', 'isw'],
        'template': dedent('''
                   //MODIFY AREA DATA
                   #MODIFY_AREA [AreaNum,AreaName,DesInter,SlackBusNum]
                   iarea,arname,pdes,isw
                   #END
                   ''').strip('\n\t')

    },

    'MODIFY_AREA_NUMBER': {'command': '#MODIFY_AREA',
        'inch_fields': ['AreaNum', 'AreaNumChn'],
        'rawx_section': 'area',
        'rawx_fields': ['iarea', 'new iarea'],
        'template': dedent('''
                   //MODIFY ONLY AREA NUMBER
                   #MODIFY_AREA [AreaNum,AreaNumChn]
                   iarea,new iarea
                   #END
                   ''').strip('\n\t')

    },

    'DELETE_AREA': {'command': '#DELETE_AREA',
        'inch_fields': ['AreaNum'],
        'rawx_section': 'area',
        'rawx_fields': ['iarea'],
        'template': dedent('''
                   //DELETE AREA DATA
                   #DELETE_AREA [AreaNum]
                   iarea
                   #END
                   ''').strip('\n\t')

    },

    'ADD_ZONE': {'command': '#ADD_ZONE',
        'inch_fields': ['ZoneNum', 'ZoneName'],
        'rawx_section': 'zone',
        'rawx_fields': ['izone', 'zoname'],
        'template': dedent('''
                   //ADD ZONE DATA
                   #ADD_ZONE [ZoneNum,ZoneName]
                   izone,zoname
                   #END
                   ''').strip('\n\t')

    },

    'MODIFY_ZONE': {'command': '#MODIFY_ZONE',
        'inch_fields': ['ZoneNum', 'ZoneName'],
        'rawx_section': 'zone',
        'rawx_fields': ['izone', 'zoname'],
        'template': dedent('''
                   //MODIFY ZONE DATA
                   #MODIFY_ZONE [ZoneNum,ZoneName]
                   izone,zoname
                   #END
                   ''').strip('\n\t')

    },

    'MODIFY_ZONE_NUMBER': {'command': '#MODIFY_ZONE',
        'inch_fields': ['ZoneNum', 'ZoneNumChn'],
        'rawx_section': 'zone',
        'rawx_fields': ['izone', 'new izone'],
        'template': dedent('''
                   //MODIFY ONLY ZONE NUMBER
                   #MODIFY_ZONE [ZoneNum,ZoneNumChn]
                   izone,new izone
                   #END
                   ''').strip('\n\t')

    },

    'DELETE_ZONE': {'command': '#DELETE_ZONE',
        'inch_fields': ['ZoneNum'],
        'rawx_section': 'zone',
        'rawx_fields': ['izone'],
        'template': dedent('''
                   //DELETE ZONE DATA
                   #DELETE_ZONE [ZoneNum]
                   izone
                   #END
                   ''').strip('\n\t')
    }
}
