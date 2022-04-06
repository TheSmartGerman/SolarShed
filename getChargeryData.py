#!/usr/bin/env python3

# getChargeryData.py
# Description: open RS232 serial port and read Chargery BMS data.
# Output data in a format to be consumed by nodeexporter/prometheus/grafana
# in folder /ramdisk
# v0.4b 5-16-20 Joe Elliott joe@inetd.com
# Protocol at http://chargery.com/uploadFiles/bms24_additional_protocol%20V1.22.pdf

# updated by TheSmartGerman
# protocal v1.26
# Protocol at https://www.chargery.com/uploadFiles/BMS24T,16T,8T%20Additional%20Protocol%20Info%20V1.26.pdf
# Main unit update to V4.05, the version must fit with protocol V1.26 

# Protocol Versions (according to the protocol documentation)
# V1.22 Add SOC send out
# V1.24 Add Wh user setup and also Wh & Ah send out
# V1.25 Add cell impedance measurement and also mΩ /current that measure impedance send out
# V1.26 Add Discharge End voltage of cell, and charge, discharge status send out

# 1. This communication protocol is used for BMS8T, BMS16T and BMS24T
# 2. The BMS only send out data, it DOESN’T receive any data
# 3. When using an external device to read the BMS, please correct communication protocol after main unit is updated
# 4. The GND of RS232 port of BMS cannot connect to cell 1- or battery negative which is in monitoring.


# Data length: From The packet header to check sum(include check sum)


import serial
import sys, os, io
import time
import binascii
from argparse import ArgumentParser

modeList= ["Discharge", "Charge", "Storage"]
chargeList=["Release", "Protection"]
gotCellData = False;
gotSysData  = False;
gotCellImpedance = False;
debug=False;
cellCount = 8
protocolVersion = ["V126"] # 122, 124, 125     

def bin2hex(str1):
        bytes_str = bytes(str1)
        return binascii.hexlify(bytes_str)

def get_voltage_value(byte1, byte2):
        return float((float(byte1 * 256) + float(byte2)) / 1000)

def get_current_value(byte1, byte2):
        return float((float(byte1 * 256) + float(byte2)) / 10)

# It is instant current when measure cell impedance	
def get_current1_value(byte1, byte2):
	return float((float(byte1) + float(byte2 * 256)) / 10)  

def get_temp_value(byte1, byte2):
        return float((float(byte1 * 256) + float(byte2)) / 10)

def get_impedance_value(byte1, byte2):
	# return float(float(byte1) + float(byte2  * 256 ) / 10) # according to datasheet
        return float((float(byte1) + float(byte2  * 256 )) / 10) # proof by recalc

# wh and ah are the same formula		
def get_capacity_value(hexLine):
        byte1 = int(hexLine[0:2],16)
        byte2 = int(hexLine[2:4],16)
        byte3 = int(hexLine[4:6],16)
        byte4 = int(hexLine[6:8],16)
        return float((float(byte1) + float(byte2 * 256) + (byte3 * 256 * 256) + (byte4 * 256 * 256 * 256))/1000)

# Checksum calculation: Sum all packet bytes and calc the sum mod 256
def getCheckSum(hexLine):
        chk_sum = 0

        # https://stackoverflow.com/questions/29699927/bytearray-sum-in-python
        # CHECKSUM have to be calcultate without the chechskum byte :P
        for i in range(0,len(hexLine)-3,2):
                chk_sum += int(hexLine[i:i+2],16)

        # MOD by 256 and retun hex value without formating: get rid of '0x'       
        return(format(chk_sum % 256, '02x')) 

def getValidData(hexLine, strLen, minLen):
        decStrLen = len(hexLine)        # length of hex String: 2 Chars = 1 Byte
        dataLen = hexLine[6:8]          # data length         

        if (decStrLen < strLen) or (decStrLen < minLen):
                if (debug): print("Truncated cell block - len:", len(hexLine), "Expected:", strLen)
                return(True)
        else:
                if (debug): print("hexLine len", len(hexLine))

        # check if length is correct
        if (int(dataLen,16) !=  (decStrLen/2)):
                if (debug): print("Missmatch of datalength! Expected: ", int(dataLen,16), " Received: ", (decStrLen/2))
                return(True)
        else:
                if (debug): print("dataLen:", int(dataLen, 16), "bytes")

        # check for valid data
        chksum = hexLine[decStrLen-2:decStrLen] # extract Checksum
        calc_sum = getCheckSum(hexLine)

        if (debug):
                print("Checksum:", chksum, "Calc Checksum: ", calc_sum)

        if (chksum != calc_sum):
                if(debug): print("Checksume missmatch - corupt data")
                return(True)        

# Command 56
# Report cells voltage (main control board)
def getCellData(fileObj, hexLine, strLen):
        minLen = 44     # minimal bytes for the 8s inc header (each byte is 2 chars)
        dataStart = 8   # cell voltage data starts at byte 9 in 2 byte chunks (hi-lo)
        cellNum = 1
        aggVolts = 0    # total voltage of the battery
        global gotCellData

        if (debug): print("getCellData: called - ", hexLine)

        if (debug):
                header  = hexLine[0:4]          # header
                command = hexLine[4:6]          # command
                print("header:", header)
                print("command:", command)                

        if (getValidData(hexLine, strLen, minLen)): return(True)

        for cell in range(dataStart, dataStart + cellCount * 4, 4):    # 2 charaters for one byte, every cell value: 2 byte.
                cellVolts = get_voltage_value(int(hexLine[cell:cell+2], 16), int(hexLine[cell+2:cell+4], 16))
                if (debug): print("Cell ", cellNum, ":", cellVolts, "v")
                # format the data for node_exporter to read into prometheus
                #valName  = "mode={}{}".format("CellNum", cellNum)
                valName  = "mode=\"CellNum" + str(cellNum) + "\""
                valName = "{" + valName + "}"
                dataStr  = f"BMS_A{valName} {cellVolts}"
                print(dataStr, file=fileObj)

                aggVolts += cellVolts
                cellNum += 1
      
        if (protocolVersion in ['V126','V125']):
                # Add Discharge End voltage of cell, and charge, discharge status send out
                # 4 Bytes = 1 byte: 4 chars
                # From cell+4 to cell+12 WH
                # from cell+12 to cell+20 AH
                # is there a smater solution to call this function ? \(°J°)/
                capacity_wh = get_capacity_value(hexLine[cell+4:cell+12])
                valName  = "mode=\"capacity_wh\""
                valName = "{" + valName + "}"
                dataStr  = f"BMS_A{valName} {capacity_wh}"
                print(dataStr, file=fileObj)

                # 4 Bytes = 1 Byte: 2 chars
                capacity_ah = get_capacity_value(hexLine[cell+12:cell+20])	
                valName  = "mode=\"capacity_ah\""
                valName = "{" + valName + "}"
                dataStr  = f"BMS_A{valName} {capacity_ah}"
                print(dataStr, file=fileObj)	

                if(debug):
                        print("Battery AH:", capacity_ah)
                        print("Battery WH:", capacity_wh)

        elif (protocolVersion in ['V122']):
                soc = int(hexLine[cell], 16)
                if(debug): print("SOC2", soc)

                valName  = "mode=\"SOC2\""
                valName = "{" + valName + "}"
                dataStr  = f"BMS_A{valName} {soc}"
                print(dataStr, file=fileObj)
        else:
                print("Unknow BMS Protocol")
                
        aggVolts = "{:4.2f}".format(aggVolts)
        valName  = "mode=\"aggVolts\""
        valName  = "{" + valName + "}"
        dataStr  = f"BMS_A{valName} {aggVolts}"
        print(dataStr, file=fileObj)
        
        if (debug):
                #print("Checksum:", asdf , "Calc Checksum: ", getCheckSum(hexLine))
                print("Battery voltage:", aggVolts, "v")

        gotCellData = True;
        return(False)

# Command 57
# Report measure value (main control board)
# the data length is always 13 
def getSysData(fileObj, hexLine, strLen):    
        minLen = 30     # minimal bytes inc header (each byte is 2 chars)
        global gotSysData

        if (debug): print("getSysData: called - ", hexLine)

                # first 3 fields for debug only)
        header     = hexLine[0:4]       # header
        command    = hexLine[4:6]       # command

        if (getValidData(hexLine, strLen, minLen)): return(True)        

        ## grap first block of Data
        maxEndVolt_hi = hexLine[8:10]      # Charge End voltage of cell
        maxEndVolt_lo = hexLine[10:12]     # Charge End voltage of cell
        mode       = hexLine[12:14]     # Current mode
        amps_hi    = hexLine[14:16]     # Current amps
        amps_lo    = hexLine[16:18]     # Current amps
        temp1_hi   = hexLine[18:20]     # Temp 1
        temp1_lo   = hexLine[20:22]     # Temp 1
        temp2_hi   = hexLine[22:24]     # Temp 2
        temp2_lo   = hexLine[24:26]     # Temp 2
        soc        = hexLine[26:28]     # SOC

        ## calculate real values
        maxEndVolts = get_voltage_value(int(maxEndVolt_hi, 16), int(maxEndVolt_lo, 16))
        currentFlow = get_current_value(int(amps_hi, 16), int(amps_lo, 16))
        modeName = modeList[int(mode, 16)]
        modeInt = int(mode, 16)
        temp1 = get_temp_value(int(temp1_hi, 16), int(temp1_lo, 16))
        temp2 = get_temp_value(int(temp2_hi, 16), int(temp2_lo, 16))
        socInt = int(soc, 16)

        ## output if debug
        if (debug):
                print("End voltage of cell:",  maxEndVolts, "v")
                print("mode:", modeInt, modeName)
                print("Temp 1:", temp1, "c")
                print("Temp 2:", temp2, "c")
                print("SOC:", socInt, "%") 

        ## output to file
        #print("mode:", mode)
        if (int(mode) == 0):
                currentFlow = currentFlow * -1 # flow is in or out of the battery?
                #print("currentFlow:", currentFlow)

        valName  = "mode=\"current\""
        valName  = "{" + valName + "}"
        dataStr  = f"BMS_A{valName} {currentFlow}"
        print(dataStr, file=fileObj)

        valName  = "mode=\"maxEndVolts\""
        valName  = "{" + valName + "}"
        dataStr  = f"BMS_A{valName} {maxEndVolts}"
        print(dataStr, file=fileObj)

        valName  = "mode=\"modeInt\", myStr=\""
        valName  = valName + modeName + "\""
        valName  = "{" + valName + "}"
        dataStr  = f"BMS_A{valName} {modeInt}"
        print(dataStr, file=fileObj)

        valName  = "mode=\"temp1\""
        valName  = "{" + valName + "}"
        dataStr  = f"BMS_A{valName} {temp1}"
        print(dataStr, file=fileObj)

        valName  = "mode=\"temp2\""
        valName  = "{" + valName + "}"
        dataStr  = f"BMS_A{valName} {temp2}"
        print(dataStr, file=fileObj)

        valName  = "mode=\"SOC\""
        valName  = "{" + valName + "}"
        dataStr  = f"BMS_A{valName} {socInt}"
        print(dataStr, file=fileObj)   

        ## grap block of Data
        if(protocolVersion=="V126"):
                minEndVolt_hi = hexLine[28:30]  # Discharge End Voltage of cell
                minEndVolt_lo = hexLine[30:32]  # Discharge End Voltage of cell
                chgProtectionStatus = hexLine[32:34]    # 1: Over Charge Protection (P) / 0: Over Charge Release (R)
                dsgProtectionStatus = hexLine[34:36]    # 1: Over Discharge Protection (P) / o: Over Discharge Release (R)
                chksum = hexLine[36:38] # Checksum

                if(debug): 
                        print ("chgStatus hex:", chgProtectionStatus)
                        print ("dsgStatus hex:", dsgProtectionStatus)

                minEndVolts = get_voltage_value(int(minEndVolt_hi, 16), int(minEndVolt_lo, 16))
                chgProtectionInt = int(chgProtectionStatus,16)
                dsgProtectionInt = int(dsgProtectionStatus,16)
                chgProtectionName = chargeList[int(chgProtectionStatus,16)]
                dsgProtectionName = chargeList[int(dsgProtectionStatus,16)]
             
                valName  = "mode=\"minEndVolts\""
                valName  = "{" + valName + "}"
                dataStr  = f"BMS_A{valName} {minEndVolts}"
                print(dataStr, file=fileObj)

                valName  = "mode=\"chgProtectionInt\", myStr=\""
                valName  = valName + chgProtectionName + "\""
                valName  = "{" + valName + "}"
                dataStr  = f"BMS_A{valName} {chgProtectionInt}"
                print(dataStr, file=fileObj)

                valName  = "mode=\"dsgProtectionInt\", myStr=\""
                valName  = valName + dsgProtectionName + "\""
                valName  = "{" + valName + "}"
                dataStr  = f"BMS_A{valName} {dsgProtectionInt}"
                print(dataStr, file=fileObj)

                ## output if debug
                if (debug):
                        print("min end voltage of cell:", minEndVolts, "v")
                        print("Charge Protectoin Status", chgProtectionName)
                        print("Discharge Protection Status", dsgProtectionName)
                              
        gotSysData = True;
        return(False)

# Command 58
# Report cells impedance (main control board)
# updates only on mode change 
def getCellImpedance(fileObj, hexLine, strLen):
        dataStart = 8   # cell impedance data starts at byte 9 in 2 byte chunks (hi-lo)
        # for BMS8T, 16T, and 24T, the data length depends on cell counts, each cell impedance is 2 bytes
        # header + command + dataLen + mode + current + 2 * count of cells + checksum 
        minLen = 8 + 2 + 4 + cellCount * 4 + 2
        cellNum = 1
        aggImpedance = 0    # total impedance of the battery
        
        global gotCellImpedance

        if (debug): print("getCellImpedance: called - ", hexLine)

        header  = hexLine[0:4]          # header
        command = hexLine[4:6]          # command
        
        if (debug):
                print("header:", header)
                print("command:", command)

        # My 16T BMS should have a Datalength of 40 Bytes but it sends out 59. Something wrong here?
        # if (getValidData(hexLine, strLen, minLen)): return(True)  

        amp1_mode = hexLine[8:10]	# currentMode1
        amp1_hi = hexLine[10:12]	# instant current1
        amp1_lo = hexLine[12:14]        # instant current1       

        # get current flow while impedance measure
        Current1ModeInt = int(amp1_mode,16)
        Current1ModeName = modeList[int(amp1_mode,16)]

        # get current while impedance measure
        current1 = get_current1_value(int(amp1_hi,16),int(amp1_lo,16))

        if(debug):
                print("currentMode1", Current1ModeName)
                print("current1", current1)

        valName  = "mode=\"currentMode1\", myStr=\""
        valName  = valName + Current1ModeName + "\""
        valName  = "{" + valName + "}"
        dataStr  = f"BMS_A_imp{valName} {Current1ModeInt}"
        print(dataStr, file=fileObj)

        valName  = "mode=\"current1\""
        valName  = "{" + valName + "}"
        dataStr  = f"BMS_A_imp{valName} {current1}"
        print(dataStr, file=fileObj)       

        for cell in range(dataStart, dataStart + cellCount * 4, 4):  
                cellImpedance = get_impedance_value(int(hexLine[cell:cell+2], 16), int(hexLine[cell+2:cell+4], 16))
                if (debug): print("Cell ", cellNum, ":", cellImpedance, "mOhm")
                valName  = "mode=\"CellNumImp" + str(cellNum) + "\""
                valName = "{" + valName + "}"
                dataStr  = f"BMS_A_imp{valName} {cellImpedance}"
                print(dataStr, file=fileObj)

                aggImpedance += cellImpedance
                cellNum += 1

        if(debug):
                print("Batterypack Impedance: ", "{:4.2f}".format(aggImpedance))

        aggImpedance = "{:4.2f}".format(aggImpedance)
        valName  = "mode=\"aggImpedance\""
        valName  = "{" + valName + "}"
        dataStr  = f"BMS_A_imp{valName} {aggImpedance}"
        print(dataStr, file=fileObj)

        gotCellImpedance = True;
        return(False)

################ main ##################

parser = ArgumentParser(description='Get BMS Data')

parser.add_argument(
        "-p",
        "--port",
        type=str,
        help="Specifies the device communications port (/dev/ttyUSB0 [default], /dev/hidraw0, COM3, ...)",
        default="/dev/ttyUSB0",
)

parser.add_argument(
        "-D",
        "--debug",
        help="Enable Debug and above (i.e. all) messages",
        action="store_true",
        #type=int,
        #default="1",
)

parser.add_argument(
        "-P",
        "--protocol",
        type=str,
        help="Specifies the device command and response protocol, (default: V122)",
        default="V122",
        choices=[
                "V121",
                "V122",
                "V124",
                "V125",
                "V126",
        ],
)

parser.add_argument(
        "-c",
        "--cells",
        type=int,
        help="Specifies the number of cells (1-24)",
        default="8",
)

args = parser.parse_args()

if args.debug:
        debug = True
        print("Debug: enabled")

if args.port:
        devName = args.port
else:
        devName='/dev/ttyUSB0'

if args.protocol:
        protocolVersion = args.protocol

if args.cells:
        cellCount = args.cells     

# id id type len data                          checksum
# 24 24 57   0F  10 68 02 00 00 FF 21 FF 21 00 68
# 24 24 56   16  00 0A 00 0A 00 09 00 0B 00 0D 00 11 00 01 00 15 00 10
# len includes id & type

# data is written to the serial port every second or less, waiting too long results in garbled lines.
# Read fast and often to get the best results. System and Cell data is written at different frequencies.

try:
        ser = serial.Serial(devName, 115200, bytesize=8, parity='N', stopbits=1, timeout=0.1)
        if (debug): print("Opened:", ser.name)
except OSError as err:
        print("Failed to open port: ", devName)
        exit()

while (ser.is_open):
        #myBin = ser.read()     # read 1 byte
        myBin  = ser.read(256)  # read up to 15 bytes
        #myBin = ser.readline(255)      # read a '\n' terminated line??
        myPid  = os.getpid()    # for temp file buffering

        hexLine = bin2hex(myBin)
        hexLine = hexLine.decode('utf-8')       # remove leading b in Python3
        dataLen = len(hexLine)

        if (gotSysData or gotCellData or gotCellImpedance):
                if (debug): print("Skip new tmp file")
        else:
                if (debug): print("Opened new tmp file /ramdisk/BMS_A_sys.prom.tmp")
                file_object = open('/ramdisk/BMS_A_sys.prom.tmp', mode='w')
                if (debug): print("Opened new tmp file /ramdisk/BMS_A_imp.prom.tmp")
                file_object_imp = open('/ramdisk/BMS_A_imp.prom.tmp', mode='w')

        if (debug): print("Read ", len(hexLine), "bytes: ", hexLine, " gotSysData: ", gotSysData, " gotCellData: ", gotCellData, " gotCellImpedance ", gotCellImpedance)

        if (dataLen > 14):
                byteA = hexLine[0:2]    # header
                byteB = hexLine[2:4]    # header
                byteC = hexLine[4:6]    # packet type 56 | 57 | 58
                byteD = hexLine[6:8]    # packet len

                if (byteA == "24" and byteB == "24"):

                        # SysData very second
                        # CellData very 2 seconds
                        # Impedance Data: on change between charge & discharge -> Flush with sys/cell data (every 2 seconds)

                        # every 2 seconds a dataset should be completed
                        if (gotSysData and gotCellData):
                                # We have a complete set, before we overwrite, copy the temp file to its final dest
                                if (debug): print("BINGO!!! - complete set - copying file to /ramdisk/BMS_A_sys.prom")
                                file_object.flush()
                                file_object.close()                                     

                                outLine = os.system('/bin/mv /ramdisk/BMS_A_sys.prom.tmp /ramdisk/BMS_A_sys.prom')
                                if (debug):    
                                        print("\n")
                                        outLine = os.system('/bin/cat /ramdisk/BMS_A_sys.prom')
                                        
                                #if (debug): sys.exit()
                                # open new temp file as we have data to write
                                file_object = open('/ramdisk/BMS_A_sys.prom.tmp', mode='w')
                                if (debug): print("Opened new tmp file /ramdisk/BMS_A_sys.prom.tmp")
                                gotSysData  = False;    # start all over again
                                gotCellData = False;

                        if(gotCellImpedance):
                                # We have a Impedance data copy the temp file to its final dest
                                if (debug): print("BINGO!!! - copying file to /ramdisk/BMS_A_imp.prom")
                                file_object_imp.flush()
                                file_object_imp.close()                                 

                                # outLine = os.system('/bin/cp /ramdisk/BMS_A_imp.prom.tmp /home/pi/BMS_A_imp.txt')
                                outLine = os.system('/bin/mv /ramdisk/BMS_A_imp.prom.tmp /ramdisk/BMS_A_imp.prom')
                                if (debug):    
                                        print("\n")
                                        outLine = os.system('/bin/cat /ramdisk/BMS_A_imp.prom')
                                
                                # open new temp file as we have data to write
                                file_object_imp = open('/ramdisk/BMS_A_imp.prom.tmp', mode='w')
                                if (debug): print("Opened new tmp file /ramdisk/BMS_A_imp.prom.tmp")
                                gotCellImpedance = False;

                        if (byteC == "56"):
                                if (debug): print("Found Cell block", byteA, byteB, byteC, hexLine)
                                if (not gotCellData):
                                        getCellData(file_object, hexLine, int(byteD, 16))
                        elif (byteC == "57"):
                                if (debug): print("Found System block", byteA, byteB, byteC, hexLine)
                                if (not gotSysData):
                                        getSysData(file_object, hexLine, int(byteD, 16))
                        elif (byteC == "58"):
                                if (debug): print("Found Impedance block", byteA, byteB, byteC, hexLine)
                                # collect impedance data
                                # if (debug == 2): 
                                # file_object_debug = open('/home/pi/raw_imp.txt', mode='a')
                                # print(hexLine, file=file_object_debug)
                                # file_object_debug.flush()
                                # file_object_debug.close() 
                                        
                                if (not gotCellImpedance):
                                        getCellImpedance(file_object_imp, hexLine, int(byteD, 16))                
                        else:
                                if (debug): print("Found Unexpected command block", byteA, byteB, byteC, hexLine)
                else:
                        if (debug): print("Found Unexpected header block", byteA, byteB, byteC, hexLine)
        else:
                if (debug): print("Read Empty line", len(hexLine), "bytes: ", hexLine)

ser.close()

# End.