#Timepix3X4 KCU105 Control Program
#v01: first releaase
#v04: got 12 packets instead of 8 for 'RP'
#v05: Added whichASIC in RM and some other commands
#     Removed data reception from RM
#v06: Added DAC scan file write, change filenames
#v07: Made RM work Oct 29, 2021
#v08: Implemented WMF, write matrix fast command
#v09: Made separate RA, RF commands
#v10: Changed WMF to send 64 3k packets instead of 32 6k ones
#        Changed SETALL to use WMF
#        Turned off shutter during RM
#v11: Added support for new frame-based data readout
#v12: Added support for the settable max_UDP interval
#v13: Fixed PH command, only works with MB software after v45.  7/17/23
#v14: 8/23/23:     global shutter_mode


import time
import datetime
import socket
import string
import sys
import random
import os
import numpy as np
from quadpix3_cfg import quadpixXml

#Set this to 1 to stop program from binding to Science port (so that we can run the science acq in another window
# Commands expecting a response won't work with this set
no_science_bind = 0

#The 128-bit token-select field, used in the ReadPixelMatrixSequential cpmmand
token_select = 0x40000000000000000000000000000000
#token_select = 0x40123456789abcdef0123456789abcde


#Why the double backslashes here??
configfilename = "/home/pi/FOXSI_Python/config/tp3x4_config.txt"
logdata = 0
logfilename = "/home/pi/FOXSI_Python/data/tp3x4_writelog.csv"
phscan_filename = "/home/pi/FOXSI_Python/data/tp3x4_phscan.csv"
dacscan_filename = "/home/pi/FOXSI_Python/data/tp3x4_dacscan.csv"

#This is to print a bunch of stuff
debug_print = 0

#This is to print the 48b packets when doing a RP
RP_debug_print = 0

#Send to broadcast address
#KCU105_IP_PORT = "192.168.3.255"
#KC705 expects commands on this port
KCU105_CMD_PORT= 60002

MY_SCI_PORT = 60001

num_resp_per_packet = 1492
bytes_in_science_payload = 6*num_resp_per_packet + 6

#Settings for the phase scan routine
#These are for 80 and 160MHz clocks
first_setting_loclock = -250
step_size_loclock = 10
num_steps_loclock = 50
#These are for 320MHz
first_setting_hiclock = -125
step_size_hiclock = 5
num_steps_hiclock = 60


#Store these values of local registers that get written together
DAC0 = 0x200  #ExtDAC to TP3 chip
DAC1 = 0x200  #VCM for LVDS receivers
testpoints = 1

#Set to 1 for ext trigger
global shutter_mode
shutter_mode = 0
#This global variable will be set to 1 when send_shutter_ram is called to do a soft trigger
#soft_trigger = 0

#Arrays to store the commanded values for DACs
commanded_DAC_vals = []
for n in range(18): commanded_DAC_vals.append(-1)

#Array to store Chip IDs in srting format
#ChipID_AST = []

#Named variables to store the readable commanded peripheral register values
TP_period = -1
TP_Pulsenumber =-1
OutBlockConfig = -1
PLLConfig = -1
GeneralConfig = -1
SLVSConfig = -1
PPulsePattern = -1
MaskBit = -1
TestBit = -1
#Read the local reg values from config file into this array
local_regs = [0] * 32


#Store the 6-bit PCR value for comparison with readback value- set this in the send_matrix routine
PCR_val = -1

#run this under Python 3.x
if (sys.version_info < (3,0)):
	print("Must run under python 3.x")
	quit()

#------------------------------------------------------------
#  FOXSI control software additions
#------------------------------------------------------------

#----------------------------------
def Set_All_FOXSI():
    #--------
    print("Resetting ASICs")
    cmd_payload = bytearray(196)
    cmd_payload[0] = 0x81
############################################ Problemo
    sendit(cmd_payload)
    print('loaded payload')
    time.sleep(1)
    #Write the local registers
    #Get the local reg values from config file
    try:
        fhand = open(configfilename)
    except Exception as e:
        print (e)
        #continue
    send_tp3_params(0,fhand, 0)
    fhand.close()
    #--------
    print("Writing Local Registers")
    send_local_regs()
    for n in range(4):
        print("Writing Peripherals Chip " + (str(n)))
        try:
            fhand = open(configfilename)
        except Exception as e:
            print (e)
            #continue
        send_tp3_params(n,fhand, 1)
        fhand.close()
        time.sleep(.1)
    #--------
    print("Writing Shutter RAM")
    try:
        fhand = open(configfilename)
    except Exception as e:
        print (e)
        #continue
    send_shutter_RAM(fhand)
    fhand.close()
    time.sleep(0.1)
    
    #--------
    #Now we need to do a phset for each chip
    #Get the clock freq from the config file
    try:
        fhand = open(configfilename)
    except Exception as e:
        print (e)
        #continue
    #get the data clock setting
    send_tp3_params(0, fhand, 0)
    #Only implemented for 320, 160, and 80 MHz
    #print ("OutBlockConfig = ", hex(OutBlockConfig))
    clock_code = (OutBlockConfig>>13) & 0x7
    if clock_code == 3: clock_freq = 80
    elif clock_code == 2: clock_freq = 160
    elif clock_code == 1: clock_freq = 320
    else:
        print("clock code not allowed")
        return
    print ("clock Freq = ", clock_freq)
    first_setting = first_setting_loclock
    step_size = step_size_loclock
    num_steps = num_steps_loclock
    if (clock_freq == 320):
        first_setting = first_setting_hiclock
        step_size = step_size_hiclock
        num_steps = num_steps_hiclock
    if first_setting < 0: first_setting += 65536      
    bytes_in_phase_scan_payload = num_steps * 16 + 14
    for n in range(4):
        print("Adjusting phase, chip  " + (str(n)))
        phset(n, first_setting, step_size, num_steps)
        time.sleep(.2)

#----------------------------------
def Set_Science_Mode(mode):
    if mode == 'SD':  # science mode DATA DRIVEN
        cmd_payload = bytearray(196)
        cmd_payload[0] = 0xe0
        cmd_payload[4] = 0x01
        sendit(cmd_payload)
    elif mode == 'SF':  # science mode FRAMEs
        cmd_payload = bytearray(196)
        cmd_payload[0] = 0xe0
        cmd_payload[4] = 0x02
        temp = token_select
        for n in range(16):
            this_byte = temp>>120
            print(this_byte)
            cmd_payload[8+n] = this_byte
            temp = (temp<<8) & 0xffffffffffffffffffffffffffffffff
        sendit(cmd_payload)
    elif mode == 'C':  # command mode
        cmd_payload = bytearray(196)
        cmd_payload[0] = 0xe0
        cmd_payload[4] = 0x00
        sendit(cmd_payload)

#----------------------------------
def Open_Shutter_Forever():
    global shutter_mode
    open_list = 256*[0]
    wait_list = 256*[0]
    shutter_mode = 8  # open shutter forever
    cmd_payload = bytearray(2052)
    cmd_payload[0] = 0x50
    cmd_payload[2] = shutter_mode
    print("Seting shutter into mode = ", shutter_mode)
    for i in range(256):
        cmd_payload[4+8*i] = wait_list[i]>>24
        cmd_payload[5+8*i] = (wait_list[i]>>16) & 0xff
        cmd_payload[6+8*i] = (wait_list[i]>>8) & 0xff
        cmd_payload[7+8*i] = wait_list[i] & 0xff
        cmd_payload[8+8*i] = open_list[i]>>24
        cmd_payload[9+8*i] = (open_list[i]>>16) & 0xff
        cmd_payload[10+8*i] = (open_list[i]>>8) & 0xff
        cmd_payload[11+8*i] = open_list[i] & 0xff
    sendit(cmd_payload)
    #-------------------
    #issue software trigger now which will open the shutter
    cmd_payload = bytearray(196)
    for n in range(len(cmd_payload)): cmd_payload[n]=0
    cmd_payload[0] = 0x51
    cmd_payload[2] = shutter_mode
    print("shutter_mode= ", shutter_mode)
    sendit(cmd_payload)

#----------------------------------
def set_DACs_Matrix_from_XML(config_filename, ChipIDs):
    # make sure the chipIDs are already read into the variable (by calling Read Periphery function) !!!
    if(len(ChipID_AST) < 4):
        print("Did not read ChipID information yet, need to do it before calling this function")
        return
    
    Config = quadpixXml()
    Config.load(config_filename)
    
    for n in range(4):  # 4 chips here
        # setup DACs for each chip
        chip_id_to_restore = ChipIDs[n]  # Replace with the actual chip_id you want to restore
        b_layout, b_settings, system_dacs, system_info = Config.tpx3_restore_chip_config(config_filename, chip_id_to_restore)
        system_dacs = np.delete(system_dacs[0],5)  #remove the combined THL value
        # Print restored DACs
        print('')
        print('Restored DACs = ', system_dacs)
        #sending DAC values here, one by one, 18 of them
        for i in range(len(system_dacs)):
            val = system_dacs[i]
            send_periph_reg(n, 2, (val<<5) + i + 1)

    # Extract binary pixel configurations and print the first 10 elements
    # make 4 buffers for 4 chips Cfg, all with 6 bits per pixel as sent to single chip
    pixCfg = []
    buff_4_bytes = bytearray(4)
    for n in range(4):  # 4 chips here
        pixCfg.append(bytearray(49152))  # 192 bytes per colum, 256 columns
        xml_config = Config.get_binary_pix_cfg(ChipIDs[n])  # read binary Cfg matrix from the XML file
        
        # print("First 10 PixCfg:")
        # for idx in range(10):
        #     print(f'Mask = {xml_config[idx].mask_bit}, Test Bit = {xml_config[idx].test_bit}, THL Adj = {xml_config[idx].thl_adj}')

        idx1 = 0  # index for the 6-bit config array
        for x in range(0,256,1):  # 256 coulmns per chip, stepping by 1 column
            for y in range(255,-1,-4):  # 256 rows per chip, stepping by 4 of them to form 3 bytes (24 bits = 4 pixels data), max y is first
                for i in range(4):  # 4 pixels here to be packed into 3 bytes
                    idx2 = (y-i)*256 + x # index for the pixel (col,row)
                    buff_4_bytes[i] = ((((xml_config[idx2].mask_bit)) & 0x01)                   | # mask bit
                                       ((reverse_bits(xml_config[idx2].thl_adj,8)) & 0xF0) >>3  | # THL bits
                                       ((xml_config[idx2].test_bit)&0x01)<<5)                     # test bit
        
                byte0 = (buff_4_bytes[0] & 0x3F)<<2 | (buff_4_bytes[1] & 0x30)>>4
                byte1 = (buff_4_bytes[1] & 0x0F)<<4 | (buff_4_bytes[2] & 0x3C)>>2
                byte2 = (buff_4_bytes[2] & 0x03)<<6 | (buff_4_bytes[3] & 0x3F)<<0
                pixCfg[n][idx1+0] = byte0
                pixCfg[n][idx1+1] = byte1
                pixCfg[n][idx1+2] = byte2
                idx1 = idx1 + 3
    # print("Chip1 10 bytes")                
    # for idx in range(192,202):
    #     print(f' idx={idx}, Byte = {pixCfg[0][idx]}')                
    # print("Chip2 10 bytes")                
    # for idx in range(10):
    #     print(f' idx={idx}, Byte = {pixCfg[1][idx]}')                
    # print("Chip3 10 bytes")                
    # for idx in range(10):
    #     print(f' idx={idx}, Byte = {pixCfg[2][idx]}')                
    # print("Chip4 10 bytes")                
    # for idx in range(10):
    #     print(f' idx={idx}, Byte = {pixCfg[3][idx]}')                

    # form the array for Rick's command: 
    # sending 64 packets out. Each packet consists of 4 columns data for 4 chips (192 bytes per column, 16 of those per packet)
    # sequence such that chip0:col0 - chip1:col0 - chip2:col0 - chip3:col0 - chip0:col1 - chip1:col1, etc. 
    payload = bytearray(3076)
    for start_col in range(0,256,4):   # 256 coulmns per chip, stepping by 4 column, 4 chipsx 4 coolumns are sent at once
        for n in range(len(payload)): payload[n]=0
        payload[0] = 0x21              # command to send pixels to matrix in fast way
        payload[1] = start_col;        # first column number in that packet (starts with this for each 4 chips)
        for i in range(4):             # 4 columns per one sending
            for n in range(4):         # 4 chips here
                arr_ind = 4 + 192*n + i*4*192
                chip_cfg_ind = (start_col + i) * 192
                payload[ arr_ind : (arr_ind + 192)] = pixCfg[n][chip_cfg_ind : (chip_cfg_ind + 192)] 

        print("column N ", start_col, "\r",end='')
        sendit(payload)
        time.sleep(.001)

    #Reset the readout logic- need to do this before any readback
    time.sleep(.5)
    cmd_payload = bytearray(196)
    cmd_payload[0] = 0x80
    sendit(cmd_payload)
    time.sleep(1)

#------------------------------------------------------------
# END of FOXSI 
#------------------------------------------------------------


#----------------------------------------------------------------------------
def flush_rx_buf():
    dumpcount = 0    
    #How big is the UDP buffer?  This is just guesswork
    while (dumpcount<64):
        try:
            print (dumpcount)
            dumpbytes = sock.recvfrom(9000)
            dumpcount +=1
        except:
            break
    return
    
#----------------------------------------------------------------------------
def flush_sci_buf():
    #set a short timeout; when it times out. we're done
    sci_sock.settimeout(0.1)

    dumpcount = 0    
    #How big is the UDP buffer?  This is just guesswork
    while (dumpcount<16):
        try:
            print (dumpcount)
            dumpbytes = sci_sock.recvfrom(9000)
            dumpcount +=1
        except:
            break
    return
    
#----------------------------------------------------------------------------
def sendit(payload):
    sock.sendto(bytes(payload), (KCU105_IP_ADDR, KCU105_CMD_PORT))
    time.sleep(.005)
    if debug_print: print (payload)
    
#----------------------------------------------------------------------------
def send_periph_reg(chip, header, val):
    if val<0: val = 0
    if val>0xffff: val = 0xffff
    cmd_payload = bytearray(196)
    for n in range(len(cmd_payload)): cmd_payload[n]=0
    cmd_payload[0] = 0x10
    cmd_payload[2] = chip 
    cmd_payload[4] = header
    cmd_payload[8] = val>>8
    cmd_payload[9] = val & 0xff
    sendit(cmd_payload)

#----------------------------------------------------------------------------
def send_local_regs():
    cmd_payload = bytearray(196)
    for n in range(len(cmd_payload)): cmd_payload[n]=0
    cmd_payload[0] = 0x40
    for n in range(32):
        cmd_payload[2*n+4] = local_regs[n] & 0xff
        cmd_payload[2*n+5] = local_regs[n] >> 8
        #print(n, cmd_payload[2*n+4], cmd_payload[2*n+5])
    sendit(cmd_payload)
    
#----------------------------------------------------------------------------
def send_tp3_params(chip, fhand, send_data):
    #don't understand why this is needed:
    global TP_period
    global TP_Pulsenumber
    global OutBlockConfig
    global PLLConfig
    global GeneralConfig
    global SLVSConfig
    global PPulsePattern
    global local_regs

    for line in fhand:
        if debug_print == 1:print (line)
        if line.startswith("*"): continue
        #strip off the comment
        strippedline = line.split('*')[0]
        #Split the tag field from the cs value field
        fields = strippedline.split("=")
        if len(fields) !=2: continue
        tag = fields[0].strip()
        val = int(fields[1],0)
        if (tag =="FE_DAC0"): local_regs[0] = val
        if (tag =="FE_DAC1"): local_regs[1] = val
        if (tag =="FE_DAC2"): local_regs[2] = val
        if (tag =="FE_DAC3"): local_regs[3] = val
        if (tag =="U25_REG1"): local_regs[4] = val
        if (tag =="U25_REG4"): local_regs[5] = val
        if (tag =="U25_REG5"): local_regs[6] = val
        if (tag =="U25_REG6"): local_regs[7] = val
        if (tag =="U25_REG7"): local_regs[8] = val
        if (tag =="U26_REG1"): local_regs[9] = val
        if (tag =="U26_REG4"): local_regs[10] = val
        if (tag =="U26_REG5"): local_regs[11] = val
        if (tag =="U26_REG6"): local_regs[12] = val
        if (tag =="U26_REG7"): local_regs[13] = val
        if (tag =="PLL_MON_SEL"): local_regs[14] = val
        if (tag =="FAKE_RATE_0"): local_regs[15] = val
        if (tag =="FAKE_RATE_1"): local_regs[16] = val
        if (tag =="FAKE_RATE_2"): local_regs[17] = val
        if (tag =="FAKE_RATE_3"): local_regs[18] = val
        if (tag =="MAX_UDP_INT"): local_regs[19] = val
        #print(val)
        if (tag == "SENSDACSEL"):
            if (send_data):send_periph_reg(chip, 0x0,val)
        if (tag == "EXTDACSEL"):
            if (send_data):send_periph_reg(chip, 0x1,val)
        if (tag == "TPPERIOD"):
            TP_period = val
            if (send_data):send_periph_reg(chip, 0xc,val)
        if (tag == "TPNUMBER"):
            TP_Pulsenumber = val
            if (send_data):send_periph_reg(chip, 0xd,val)
        if (tag == "OUTBLKCONFIG"):
            OutBlockConfig = val
            if (send_data):send_periph_reg(chip, 0x10,val)
        if (tag == "PLLCONFIGREG"):
            PLLConfig = val
            if (send_data):send_periph_reg(chip, 0x20,val)
        if (tag == "PIXMODE"):
            pixmode = val
        if (tag == "GRAYCOUNT"):
            graycount = val
        if (tag == "TPENABLE"):
            tpenable = val
        if (tag == "FASTLO"):
            fastlo = val
        if (tag == "TESTPULSEIN"):
            testpulsein = val
        if (tag == "TPEXTINT"):
            tpextint = val
        
        if (tag == "SLVSCONFIGREG"):
            SLVSConfig = val
            if (send_data):send_periph_reg(chip, 0x34,val)
        if (tag == "POWPULSEPAT"):
            PPulsePattern = val
            if (send_data):send_periph_reg(chip, 0x3c,val)
        if (tag == "SETTIMELOW"):
            if (send_data):send_periph_reg(chip, 0x41,val)
        if (tag == "SETTIMEMID"):
            if (send_data):send_periph_reg(chip, 0x42,val)
        if (tag == "SETTIMEHIGH"):
            if (send_data):send_periph_reg(chip, 0x43,val)       
        #find tags of the form "DACVAL_xx"
        if tag.startswith("DACVAL"):
            fields = tag.split("_")
            whichdac = int(fields[1])
            if whichdac>18: whichdac=18
            if val>0x1ff: val = 0x1ff  #9-bit DACs
            commanded_DAC_vals[whichdac-1] = val
            if (send_data):send_periph_reg(chip, 2,(val<<5) + whichdac)
    GeneralConfig = 1 #LSB is polarity, 1 is for electrons
    GeneralConfig |= (pixmode<<1) | (graycount<<3) | (tpenable<<5) | (fastlo<<6) | (testpulsein<<9) | (tpextint<<10)
    if (send_data):
        send_periph_reg(chip, 0x30,GeneralConfig)
        cmd_payload = bytearray(196)
        for n in range(len(cmd_payload)): cmd_payload[n]=0
        cmd_payload[0] = 0x82
        #sendit(cmd_payload)
        
#----------------------------------------------------------------------------
def send_CTPR(chip, fhand):
    for line in fhand:
        if debug_print == 1:print (line)
        if line.startswith("*"): continue
        #strip off the comment
        strippedline = line.split('*')[0]
        #Split the tag field from the cs value field
        fields = strippedline.split("=")
        if len(fields) !=2: continue
        tag = fields[0].strip()
        if (tag == "TESTPIXCOL"):
            val = int(fields[1],0)
            #We can choose one column only.  Set a single 1 in the proper bit position
            # of the 256-bit CTPR
            whichbyte = int(val/8)
            whichbit = val % 8
            print(val, whichbyte,whichbit)
            cmd_payload = bytearray(196)
            for n in range(len(cmd_payload)): cmd_payload[n]=0
            if (TestBit): cmd_payload[0] = 0x31
            else: cmd_payload[0] = 0x30
            cmd_payload[2] = chip
            cmd_payload[4 +whichbyte] = 0x80>>whichbit
            sendit(cmd_payload)

#----------------------------------------------------------------------------
def send_shutter_RAM(fhand):
    global shutter_mode
    open_list = 256*[0]
    wait_list = 256*[0]
    for line in fhand:
        if debug_print == 1:print (line)
        if line.startswith("*"): continue
        #strip off the comment
        strippedline = line.split('*')[0]
        #Split the tag field from the cs value field
        fields = strippedline.split("=")
        if len(fields) !=2: continue
        tag = fields[0].strip()
        val = int(fields[1],0)
        if tag =="SHUTTERMODE":
            shutter_mode = val #& ~0x2  #Don't permit permanent setting of the soft_trigger bit
        #if soft_trigger == 1: shutter_mode = 2
        if tag.startswith("WAIT"):
            fields = tag.split("_")
            index = int(fields[1])
            #print("W", index, val)
            wait_list[index] = val
        if tag.startswith("OPEN"):
            fields = tag.split("_")
            index = int(fields[1])
            open_list[index] = val
    #print(wait_list)
    cmd_payload = bytearray(2052)
    cmd_payload[0] = 0x50
    cmd_payload[2] = shutter_mode
    #print(shutter_mode)
    for i in range(256):
        cmd_payload[4+8*i] = wait_list[i]>>24
        cmd_payload[5+8*i] = (wait_list[i]>>16) & 0xff
        cmd_payload[6+8*i] = (wait_list[i]>>8) & 0xff
        cmd_payload[7+8*i] = wait_list[i] & 0xff
        cmd_payload[8+8*i] = open_list[i]>>24
        cmd_payload[9+8*i] = (open_list[i]>>16) & 0xff
        cmd_payload[10+8*i] = (open_list[i]>>8) & 0xff
        cmd_payload[11+8*i] = open_list[i] & 0xff
    sendit(cmd_payload)
        
#----------------------------------------------------------------------------
def reverse_bits(data_in, width):
    data_out = 0
    for ii in range(width):
        data_out = data_out << 1
        if (data_in & 1): data_out = data_out | 1
        data_in = data_in >> 1
    return data_out
    
#----------------------------------------------------------------------------
def send_matrix(chip, fhand, send_data):
    global PCR_val
    global GeneralConfig
    testbitcol = 0
    testbitrow = 0
    pixthresh = 0
    for line in fhand:
        if debug_print == 1:print (line)
        if line.startswith("*"): continue
        #strip off the comment
        strippedline = line.split('*')[0]
        #Split the tag field from the cs value field
        fields = strippedline.split("=")
        if len(fields) !=2: continue
        tag = fields[0].strip()
        val = int(fields[1],0)
        if (tag == "TESTPIXCOL"): testbitcol = val
        if (tag == "TESTPIXROW"): testbitrow = val
        if (tag == "PIXTHRESH"): pixthresh = val
        if (tag == "GENCONFIGREG"):GeneralConfig = val
        if (tag == "MASKBIT"): MaskBit = val
        if (tag == "TESTBIT"): TestBit = val
    #We need to figure out which test_bit to set in the 1536-bit stream for
    #  the given column
    #Since the bottom pixel is defined as 0, but the PCR of pixel 255 is sent out first,
    # need to reverse the row number
    #testbitrow_rev = 255- testbitrow
    #The bytes go out in the reverse order: the first byte in the packet is PCR[1535:1528], so
    # need to reverse the order
    whichbyte = 191 - int((testbitrow * 6 + 5)/8)
    whichbit = (testbitrow * 6 + 5) % 8
    bitmask = 1<<whichbit
    #print(hex(whichbyte),hex(bitmask))
    if pixthresh > 15: pixthresh = 15
    if pixthresh < 0 : pixthresh = 0
    #There's a 6-bit field repeated 256 times to make a 192B array
    #A three-byte pattern is repeated 64 times
    #The field (PCR, pixel control reg) is:
    #  [5]: test bit, 1 to enable
    #  [4:1] pixel threshold, bit-reversed
    #  [0]: mask bit; set these all to 1
    pixthresh_rev = reverse_bits(pixthresh,4)
    if MaskBit == 1: PCR_val = pixthresh_rev<<1 | 1
    else: PCR_val = pixthresh_rev<<1 
    if TestBit: PCR_val |= 0x20
    #print("PCR val = ", hex(PCR_val))
    #byte2 = ((pixthresh_rev<<3) | (pixthresh_rev>>3)) & 0xff
    #byte1 = ((pixthresh_rev<<5) | (pixthresh_rev>>1)) & 0xff
    #byte0 = ((pixthresh_rev<<7) | (pixthresh_rev<<1)) & 0xff
    byte2 = ((PCR_val<<2) | (PCR_val>>4)) & 0xff
    byte1 = ((PCR_val<<4) | (PCR_val>>2)) & 0xff
    byte0 = ((PCR_val<<6) | (PCR_val<<0)) & 0xff
    #print(hex(byte0),hex(byte1),hex(byte2))
    #print(pixthresh,pixthresh_rev,byte2,byte1,byte0)
    #We'll send 256 "set_pixel_matrix" packets
    if send_data:
        cmd_payload = bytearray(196)
        for column in range(256):
        #for column in range(2,3):
            for n in range(len(cmd_payload)): cmd_payload[n]=0
            cmd_payload[0] = 0x20
            cmd_payload[1] = column
            cmd_payload[2] = chip
            
            for i in range(64):
                cmd_payload[4+3*i] = byte2
                cmd_payload[5+3*i] = byte1
                cmd_payload[6+3*i] = byte0
            if column == testbitcol:
                #The 192 bytes of PCR data are offset by 4 in the cmd_payload array
                #We want to set the MSbit (test) of the 6-bit PCR for that pixel
                if (TestBit == 0): cmd_payload[whichbyte+4] = cmd_payload[whichbyte+4] | bitmask
                else:cmd_payload[whichbyte+4] = cmd_payload[whichbyte+4] & ~bitmask
                #print(hex(whichbyte),hex(cmd_payload[whichbyte+4]))
            print("Column ", column, "\r",end='')
            sendit(cmd_payload)
        print("Done Write Matrix")

#----------------------------------------------------------------------------
def send_matrix_fast(fhand, send_data):
    global PCR_val
    global GeneralConfig
    testbitcol = 0
    testbitrow = 0
    pixthresh = 0
    for line in fhand:
        if debug_print == 1:print (line)
        if line.startswith("*"): continue
        #strip off the comment
        strippedline = line.split('*')[0]
        #Split the tag field from the cs value field
        fields = strippedline.split("=")
        if len(fields) !=2: continue
        tag = fields[0].strip()
        val = int(fields[1],0)
        if (tag == "TESTPIXCOL"): testbitcol = val
        if (tag == "TESTPIXROW"): testbitrow = val
        if (tag == "PIXTHRESH"): pixthresh = val
        if (tag == "GENCONFIGREG"):GeneralConfig = val
        if (tag == "MASKBIT"): MaskBit = val
        if (tag == "TESTBIT"): TestBit = val
    #We need to figure out which test_bit to set in the 1536-bit stream for
    #  the given column
    #Since the bottom pixel is defined as 0, but the PCR of pixel 255 is sent out first,
    # need to reverse the row number
    #testbitrow_rev = 255- testbitrow
    #The bytes go out in the reverse order: the first byte in the packet is PCR[1535:1528], so
    # need to reverse the order
    whichbyte = 191 - int((testbitrow * 6 + 5)/8)
    whichbit = (testbitrow * 6 + 5) % 8
    bitmask = 1<<whichbit
    #print(hex(whichbyte),hex(bitmask))
    if pixthresh > 15: pixthresh = 15
    if pixthresh < 0 : pixthresh = 0
    #There's a 6-bit field repeated 256 times to make a 192B array
    #A three-byte pattern is repeated 64 times
    #The field (PCR, pixel control reg) is:
    #  [5]: test bit, 1 to enable
    #  [4:1] pixel threshold, bit-reversed
    #  [0]: mask bit; set these all to 1
    pixthresh_rev = reverse_bits(pixthresh,4)
    if MaskBit == 1: PCR_val = pixthresh_rev<<1 | 1
    else: PCR_val = pixthresh_rev<<1 
    if TestBit: PCR_val |= 0x20
    #print("PCR val = ", hex(PCR_val))
    #byte2 = ((pixthresh_rev<<3) | (pixthresh_rev>>3)) & 0xff
    #byte1 = ((pixthresh_rev<<5) | (pixthresh_rev>>1)) & 0xff
    #byte0 = ((pixthresh_rev<<7) | (pixthresh_rev<<1)) & 0xff
    byte2 = ((PCR_val<<2) | (PCR_val>>4)) & 0xff
    byte1 = ((PCR_val<<4) | (PCR_val>>2)) & 0xff
    byte0 = ((PCR_val<<6) | (PCR_val<<0)) & 0xff
    #print(hex(byte0),hex(byte1),hex(byte2))
    #print(pixthresh,pixthresh_rev,byte2,byte1,byte0)
    #We'll send 64 "set_16_mx_cols" packets
    if send_data:
        cmd_payload = bytearray(3076)
        for packet in range(64):
            for n in range(len(cmd_payload)): cmd_payload[n]=0
            cmd_payload[0] = 0x21
            cmd_payload[1] = 4*packet
            for col in range(4):
                column = 4*packet + col
                for chip in range(4):
                    for i in range(64):
                        cmd_payload[4+3*i + 192*(4*col + chip)] = byte2
                        cmd_payload[5+3*i + 192*(4*col + chip)] = byte1
                        cmd_payload[6+3*i + 192*(4*col + chip)] = byte0
                    if column == testbitcol:
                        #The 192 bytes of PCR data are offset by 4 in the cmd_payload array
                        #We want to set the MSbit (test) of the 6-bit PCR for that pixel
                        if (TestBit == 0): cmd_payload[whichbyte+4 + 192*(4*col + chip)] = cmd_payload[whichbyte+4 + 192*(4*col + chip)] | bitmask
                        else:cmd_payload[whichbyte+4 + 192*(4*col + chip)] = cmd_payload[whichbyte+4 + 192*(4*col + chip)] & ~bitmask
                        #print(hex(whichbyte),hex(cmd_payload[whichbyte+4]))
            print("packet ", packet, "\r",end='')
            sendit(cmd_payload)
            #time.sleep(0.1)
        print("Done Write Matrix")


#----------------------------------------------------------------------------
#transform the 16b address returned by the ASIC to a 2-element list: col, row
def pixadd_2_colrow(pixadd):
    pix = pixadd & 0x7
    superpix = (pixadd>>3) & 0x3f
    eoc = pixadd >> 9
    retval = []
    retval.append(2*eoc + int(pix/4))
    retval.append(superpix*4 + pix%4)
    return retval

#----------------------------------------------------------------------------
def phset(chip, first_setting, step_size, num_steps):
    bytes_in_phase_scan_payload = num_steps * 16 + 14
    cmd_payload = bytearray(196)
    for n in range(len(cmd_payload)): cmd_payload[n]=0
    cmd_payload[0] = 0xb0
    cmd_payload[2] = chip
    cmd_payload[4] = first_setting & 0xff   
    cmd_payload[5] = first_setting >> 8
    cmd_payload[6] = step_size & 0xff   
    cmd_payload[7] = step_size >> 8
    cmd_payload[8] = num_steps & 0xff   
    cmd_payload[9] = num_steps >> 8
    
    flush_rx_buf()
    sendit(cmd_payload)
    time.sleep(1)
    numpackets = 0     
    while(numpackets<5):
        try:
            OK = 1
            reply = sock.recvfrom(1024)
            #print(len(reply[0]))
            numpackets +=1
        except:
            print ("no reply")
            OK=0
        if (OK & (len(reply[0]) == bytes_in_phase_scan_payload)):
            fhand_log = open(phscan_filename, 'w')
            print ("Bytes Received = " + str(len(reply[0])), end='')
            bytesback = reply[0]
            respnum = (bytesback[1]<<8) + bytesback[0]
            print(" response packet # " + str(respnum) + " " + hex(respnum))
            first_phase_setting = bytesback[4] + 256*bytesback[5]
            if first_phase_setting > 32767: first_phase_setting = first_phase_setting - 65536
            step_size = bytesback[6]
            num_steps = bytesback[8]
            print(first_phase_setting, step_size, num_steps)
            fhand_log.write(str(first_phase_setting) + ',' + str(step_size) + ',' + str(num_steps) + '\n')
            for step in range(num_steps):
                fhand_log.write(str(first_phase_setting + step_size * step) + ',')
                for chan in range(8):
                    fhand_log.write(str(bytesback[10 + 16*step + 2*chan] + 256*bytesback[11 + 16*step + 2*chan]) + ',')
                fhand_log.write('\n')
            set_phase = bytesback[12 + 16*step + 2*chan] + 256*bytesback[13 + 16*step + 2*chan]
            if set_phase > 32767: set_phase = set_phase - 65536
            print("Final phase setting " + str(set_phase))
            fhand_log.write("Final phase setting " + str(set_phase))
            fhand_log.close()
            break
    

#----------------------------------------------------------------------------
def read_periphery():
    #When reading back the peripheral registers, must turn off the shutter, else ASIC will be spewing out data during the readback
    cmd_payload = bytearray(1028)
    cmd_payload[0] = 0x50
    cmd_payload[2] = 0
    cmd_payload[4] = 0
    cmd_payload[5] =0
    sendit(cmd_payload)
    time.sleep(0.1)
    #And dump the data ib the fifos
    cmd_payload = bytearray(196)
    cmd_payload[0] = 0x82
    sendit(cmd_payload)

    #Get the parameters from the config file, so we can compare with the read-back values
    try:
        fhand = open(configfilename)
    except Exception as e:
        print (e)
#        continue

    send_tp3_params(0, fhand, 0)
    fhand.close()
    #Sending a packet with command_byte = 0xf0 causes the KC705 to send a series of commands to the ASIC
    # requesting register values
    cmd_payload = bytearray(196)
    cmd_payload[0] = 0xf0
    #Need to flush out old science data first
    flush_sci_buf()
    #set timeout longer so we don't time out
    sci_sock.settimeout(0.5)
    sendit(cmd_payload)
    #Wait for at least eight packets, two from each core
    time.sleep(.6)
    #We'll store the relevaant responses here
    responses = []
    for n in range(4):
        one_chip_resp = []
        responses.append(one_chip_resp)
    #Get 8 UDP packets
    numpackets = 0
    reg_addresses ={0x03, 0x09, 0x0a, 0x0e, 0x11, 0x21, 0x31, 0x35, 0x3d, 0x71}
    while (numpackets < 12):
        try:
            OK = 1
            reply = sci_sock.recvfrom(bytes_in_science_payload)
        except:
            print ("no reply")
            OK=0
        if (OK & (len(reply[0]) == bytes_in_science_payload)):
            #print(reply)
            print ("Bytes Received = " + str(len(reply[0])), end='')
            bytesback = reply[0]
            respnum = ((bytesback[1]<<8) + bytesback[0]) & 0x3fff
            which_chip = (bytesback[1])>>6
            print(" response packet # " + str(respnum) + " " + hex(respnum) + " from chip " + str(which_chip))
            #There are 18 DAC values and 14 peripheral register values read back.  Each value consists of 12 bytes, 96 bits, including
            # headers, padding, chip ID, etc.  Form a list ("readback") of 32 12B lists "ASIC_resp"
            for n in range (num_resp_per_packet):
                resp = 0
                #for m in range(7,1,-1):
                for m in range(11,5,-1):
                    resp = resp<<8
                    resp = resp | (bytesback[6*n + m])
                #print(hex(resp))
                if resp == 0xffffffffffff: break
                if ((resp >>40)in reg_addresses): responses[which_chip].append(resp)
            numpackets = numpackets + 1
    if RP_debug_print:
        for val in responses: print(hex(val))

    #Array to store Chip IDs in srting format
    ChipID_AST = []
        
    for which_chip in range(4):   
        #Now make a list of all the DAC values and other peripheral registers
        #The DACaddresses are 1 to 18, but we'll store them in 0 to 17
        DACvals = 18*[-1]
        ChipID = -1
        TP_Config_readback = -1
        OutBlock_Config_readback = -1
        PLL_Config_readback = -1
        Gen_Config_readback = -1
        SLVS_Config_readback = -1
        PPulse_Config_readback = -1
        for respval in responses[which_chip]:
            if (respval & 0xff0000000000) == 0x030000000000:
                #This is a DAC value- there are 18, from 0x01 to 0x12
                DAC_addr = respval & 0x1f
                if DAC_addr not in range(1,19): 
                    print("DAC address out of range ", DAC_addr)
                else: DACvals[DAC_addr-1] = (respval>>5) & 0x1ff
            elif (respval & 0xff0000000000) == 0x090000000000: ChipID = respval & 0xffffffff
            elif (respval & 0xff0000000000) == 0x0e0000000000: TP_Config_readback = respval & 0x00fffffff
            elif (respval & 0xff0000000000) == 0x110000000000: OutBlock_Config_readback = respval & 0xffff
            elif (respval & 0xff0000000000) == 0x210000000000: PLL_Config_readback = respval & 0x3fff
            elif (respval & 0xff0000000000) == 0x310000000000: Gen_Config_readback = respval & 0xffff
            elif (respval & 0xff0000000000) == 0x350000000000: SLVS_Config_readback = respval & 0x1f
            elif (respval & 0xff0000000000) == 0x3d0000000000: PPulse_Config_readback = respval & 0xff
            
        print("")
        chip_ID_AST_str = chr(0x40 + (ChipID & 0xF)) + str((ChipID >> 4) & 0xF).zfill(2) + "-W" + str((ChipID >> 8) & 0xFFF).zfill(3)
        print(chip_ID_AST_str)
        ChipID_AST.append(chip_ID_AST_str)
        print("Chip ", which_chip, " ChipID", hex(ChipID), " ---", chip_ID_AST_str)
    
        data_bad = 0
        for n in range(18):
            if DACvals[n] != commanded_DAC_vals[n]:
                print("Bad DAC readback ", n, DACvals[n], commanded_DAC_vals[n])
                data_bad = 1
        if data_bad == 0: print("DAC  values MATCH those in config file")
        #Get the other peripheral reg values and check them.
        
        data_bad = 0
        if ((TP_period<<16) | TP_Pulsenumber)  != TP_Config_readback:
            data_bad = 1
            print ("TP_Config_readback no match ", end='')
            print("configfile value ", hex(((TP_period<<16) | TP_Pulsenumber)), ", readback value ", hex(TP_Config_readback))
        if (OutBlockConfig != OutBlock_Config_readback):
            data_bad = 1
            print ("OutBlock_Config_readback no match ", end='')
            print("configfile value ", hex(OutBlockConfig), ", readback value ", hex(OutBlock_Config_readback))
        if (PLLConfig != PLL_Config_readback):
            data_bad = 1
            print ("PLL_Config_readback no match ", end='')
            print("configfile value ", hex(PLLConfig), ", readback value ", hex(PLL_Config_readback))
        if (GeneralConfig != Gen_Config_readback):
            data_bad = 1
            print ("Gen_Config_readback no match ",end='')
            print("configfile value ", hex(GeneralConfig), ", readback value ", hex(Gen_Config_readback))
        if (SLVSConfig != SLVS_Config_readback):
            data_bad = 1
            print ("SLVS_Config_readback no match ")
            print("configfile value ", hex(SLVSConfig), ", readback value ", hex(SLVS_Config_readback))
        if (PPulsePattern != PPulse_Config_readback):
            data_bad = 1
            print ("PPulse_Config_readback no match ")
            print("configfile value ", hex(PPulsePattern), ", readback value ", hex(PPulse_Config_readback))
        if (data_bad == 0): print("Peripheral register vals MATCH those in config file")    
    
    time.sleep(.1)   
    #restore the shutter settings
    #time.sleep(3)
    try:
        fhand = open(configfilename)
    except Exception as e:
        print (e)
#        continue
    send_shutter_RAM(fhand)
    fhand.close()
    return ChipID_AST


##########################################################    
##########################################################    
##########################################################    


print ("Timepix3 Four-Chip Control")
#inp = input("subnet address x: 192.168,x.255 (1)")
#if inp == "": inp = "1"
inp = "1"
KCU105_IP_ADDR = "192.168." + inp + ".255"

try :
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) # UDP0
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST,1) # TEST
    print ("Socket Created")
except socket.error as msg :
    print ('Failed to create socket. Error Code : ' + str(msg[0]) + ' Message ' + msg[1])
    sys.exit()    
sock.settimeout(0.1)

if(no_science_bind == 0):
    try :
        sci_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) # UDP
        sci_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST,1) # TEST
        print ("Socket Created")
    except socket.error as msg :
        print ('Failed to create socket. Error Code : ' + str(msg[0]) + ' Message ' + msg[1])
        sys.exit()    
    sci_sock.settimeout(0.5)


#Need to "bind" socket to MY_UDP_PORT since the KCU105 will respond to this port.  So host will send from MY_UDP_PORT, 
# and therefore know to expect a response from MY_UDP_PORT
#Or, use "0" and allow OS to choose a port.  Works only if server (KCU105) will learn the response
# port from the command port
try:
    sock.bind(("", 59999))
    #sock.bind(("", 0))
except socket.error as msg:
    print ('Bind failed. Error Code : ' + str(msg[0]) + ' Message ' + msg[1])
    sys.exit()
     
print ('Socket bind complete')

if(no_science_bind == 0):
    try:
        sci_sock.bind(("", 60001))
        #sock.bind(("", 0))
    except socket.error as msg:
        print ('Bind failed. Error Code : ' + str(msg[0]) + ' Message ' + msg[1])
        sys.exit()

#***************************FOXSI4***********************
Set_All_FOXSI()
ChipID_AST = read_periphery()
print('==========================================================================')
ChipID_AST = read_periphery()
print('==========================================================================')
print(ChipID_AST)
print('==========================================================================')

set_DACs_Matrix_from_XML("/home/pi/FOXSI_Python/FOXSI4_Matrix_DACs_Config.xml", ChipID_AST)
Set_Science_Mode("SD")
Open_Shutter_Forever()

#***************************END OF FOXSI4***********************

"""
while True:
    inp = input('''Enter
    "SETALL" to do a complete setup,
    "WL" to write all local register (DACs, temp sensors, fake, PLL_Mon select) from config.txt,
    "WR" to write one ASIC periphery register,
    "TH" to set the threshold,
    "RT" to ramp the threshold,
    "WP" to write all periphery registers,
    "RP" to read back ASIC periph data,
    "CT" to set column test pulse register (CTPR)
    "RA" to hard-reset the ASICs,
    "RF" to reset the data FIFOs (DON"T DO THIS RIGHT AFTER AN RA; ASICs NEED TO BE SET UP BEFORE RF (do WP first),
    "RS" to send reset_sequential command to ASIC,
    "WM" to write entire pixel matrix,
    "WMF" to write entire pixel matrix quickly,
    "RM" to read the entire pixel matrix,
    "WS" to set up the shutter RAM,
    "ST" to issue a soft trigger,
    "SCAN" to do a DAC scan and report back the data
    "PH" to manually adjust the receive clock phase,
    "PHSET" to automatically tune the receive clock phase,
    "SD" to switch to science mode, data driven,
    "SF" to switch to science mode, frame based,
    "C" to switch to command mode,
    "F"
    or "q" to quit\n\r''')
    
    if inp == 'q':
        quit()
    elif inp == "SETALL":
        print("Resetting ASICs")
        cmd_payload = bytearray(196)
        cmd_payload[0] = 0x81
        sendit(cmd_payload)
        time.sleep(1)
        #Write the local registers
        #Get the local reg values from config file
        try:
            fhand = open(configfilename)
        except Exception as e:
            print (e)
            continue
        send_tp3_params(0,fhand, 0)
        fhand.close()
        #
        print("Writing Local Registers")
        send_local_regs()
        for n in range(4):
            print("Writing Peripherals Chip " + (str(n)))
            try:
                fhand = open(configfilename)
            except Exception as e:
                print (e)
                continue
            send_tp3_params(n,fhand, 1)
            fhand.close()
            time.sleep(.1)
            
            # print("Writing Matrix Chip " + (str(n)))
            # try:
                # fhand = open(configfilename)
            # except Exception as e:
                # print (e)
                # continue
            # send_matrix(n, fhand, 1)
            # fhand.close()
            # time.sleep(1)
            
        print("Writing Shutter RAM")
        try:
            fhand = open(configfilename)
        except Exception as e:
            print (e)
            continue
        send_shutter_RAM(fhand)
        fhand.close()

        print("Writing Matrix, all chips")
        try:
            fhand = open(configfilename)
        except Exception as e:
            print (e)
            continue
        send_matrix_fast(fhand, 1)
        fhand.close()
        time.sleep(1)
        #Reset the readout logic- need to do this before any readback
        cmd_payload = bytearray(196)
        cmd_payload[0] = 0x80
        sendit(cmd_payload)
        
        time.sleep(1)
        #Now we need to do a phset for each chip
        #Get the clock freq from the config file
        try:
            fhand = open(configfilename)
        except Exception as e:
            print (e)
            continue
        #get the data clock setting
        send_tp3_params(0, fhand, 0)
        #Only implemented for 320, 160, and 80 MHz
        #print ("OutBlockConfig = ", hex(OutBlockConfig))
        clock_code = (OutBlockConfig>>13) & 0x7
        if clock_code == 3: clock_freq = 80
        elif clock_code == 2: clock_freq = 160
        elif clock_code == 1: clock_freq = 320
        else:
            print("clock code not allowed")
            break
        print ("clock Freq = ", clock_freq)
        first_setting = first_setting_loclock
        step_size = step_size_loclock
        num_steps = num_steps_loclock
        if (clock_freq == 320):
            first_setting = first_setting_hiclock
            step_size = step_size_hiclock
            num_steps = num_steps_hiclock
        if first_setting < 0: first_setting += 65536      
        bytes_in_phase_scan_payload = num_steps * 16 + 14
        for n in range(4):
            print("Adjusting phase, chip  " + (str(n)))
            phset(n, first_setting, step_size, num_steps)
            time.sleep(.2)
        
    elif inp == 'WL':
        #Get the local reg values from config file
        try:
            fhand = open(configfilename)
        except Exception as e:
            print (e)
            continue
        send_tp3_params(0,fhand, 0)
        fhand.close()
        #
        send_local_regs()
    elif inp == 'WR':
        inp1 = input("Input chip, reg_address and value, in decimal or 0x__ hex")
        vals = inp1.split(',')
        send_periph_reg(int(vals[0],0), int(vals[1],0),int(vals[2],0))
    elif inp == 'TH':
        inp1 = input("Enter chip, coarse (4b) and fine(9b) values\n")
        vals = inp1.split(',')
        chip = int(vals[0])
        coarse = int(vals[1])
        fine = int(vals[2])
        send_periph_reg(chip, 2,(fine<<5) + 6)
        time.sleep(.1)
        send_periph_reg(chip, 2,(coarse<<5) + 7)
        time.sleep(.2)
        
    elif inp == 'RT':
        if logdata == 1:
            fhand_log = open(logfilename, 'w')
        inp1 = input("which chip (0-3)?")
        chip = int(inp1)
        inp1 = input("Enter firstval, lastval, and step, 13b quantities\n")
        vals = inp1.split(',')
        firstval = int(vals[0])
        lastval = int(vals[1])
        step = int(vals[2])
        for val in range(firstval, lastval, step):
            fine = val & 0x1ff
            coarse = (val>>9) & 0xf
            print("Coarse ", coarse, "Fine ", fine)
            if logdata == 1:
                fhand_log.write((time.ctime().split(" ")[3] + "  Writing Threshold " + hex(coarse) + " " + hex(fine) + '\n\r'))
            send_periph_reg(chip, 2,(fine<<5) + 6)
            time.sleep(.1)
            send_periph_reg(chip, 2,(coarse<<5) + 7)
            time.sleep(.5)
        if logdata == 1: fhand_log.close()

        
    elif inp == "CT":
        inp1 = input("which chip (0-3)?")
        chip = int(inp1)
        try:
            fhand = open(configfilename)
        except Exception as e:
            print (e)
            continue
        send_CTPR(chip, fhand)
        fhand.close()
        
    elif inp == 'WP':
        inp1 = input("which chip (0-3), CR for all?")
        if (inp1 == ""):
            for n in range(4):
                try:
                    fhand = open(configfilename)
                except Exception as e:
                    print (e)
                    continue
                send_tp3_params(n,fhand, 1)
                fhand.close()
                time.sleep(0.1)
        else:
            try:
                fhand = open(configfilename)
            except Exception as e:
                print (e)
                continue
            send_tp3_params(int(inp1),fhand, 1)
            
            fhand.close()
    elif inp == 'WM':
        inp1 = input("which chip (0-3)?")
        chip = int(inp1)
        try:
            fhand = open(configfilename)
        except Exception as e:
            print (e)
            continue
        send_matrix(chip, fhand, 1)
        fhand.close()
        #Reset the readout logic- need to do this before any readback
        cmd_payload = bytearray(196)
        cmd_payload[0] = 0x80
        sendit(cmd_payload)
    elif inp == 'WMF':
        try:
            fhand = open(configfilename)
        except Exception as e:
            print (e)
            continue
        send_matrix_fast(fhand, 1)
        fhand.close()
        #Reset the readout logic- need to do this before any readback
        cmd_payload = bytearray(196)
        cmd_payload[0] = 0x80
        sendit(cmd_payload)
    elif inp == 'RA':
        cmd_payload = bytearray(196)
        cmd_payload[0] = 0x81
        sendit(cmd_payload)
    elif inp == 'RF':
        cmd_payload = bytearray(196)
        cmd_payload[0] = 0x82
        sendit(cmd_payload)
    elif inp == 'RS':
        cmd_payload = bytearray(196)
        cmd_payload[0] = 0x80
        sendit(cmd_payload)
    elif inp == 'SD':
        cmd_payload = bytearray(196)
        cmd_payload[0] = 0xe0
        cmd_payload[4] = 0x01
        sendit(cmd_payload)
    elif inp == 'SF':
        cmd_payload = bytearray(196)
        cmd_payload[0] = 0xe0
        cmd_payload[4] = 0x02
        temp = token_select
        for n in range(16):
            this_byte = temp>>120
            print(this_byte)
            cmd_payload[8+n] = this_byte
            temp = (temp<<8) & 0xffffffffffffffffffffffffffffffff
        sendit(cmd_payload)
    elif inp == 'C':
        cmd_payload = bytearray(196)
        cmd_payload[0] = 0xe0
        cmd_payload[4] = 0x00
        sendit(cmd_payload)
        
        
    elif inp == 'WS':
      #for n in range(20):
        #print(n)
        try:
            fhand = open(configfilename)
        except Exception as e:
            print (e)
            continue
        send_shutter_RAM(fhand)
        fhand.close()
        #time.sleep(3)
    elif inp == 'ST':
        cmd_payload = bytearray(196)
        for n in range(len(cmd_payload)): cmd_payload[n]=0
        cmd_payload[0] = 0x51
        cmd_payload[2] = shutter_mode
        print("shutter_mode= ", shutter_mode)
        sendit(cmd_payload)
        # soft_trigger = 1
        # try:
            # fhand = open(configfilename)
        # except Exception as e:
            # print (e)
            # continue
        # send_shutter_RAM(fhand)
        # fhand.close()
        # soft_trigger = 0
        # try:
            # fhand = open(configfilename)
        # except Exception as e:
            # print (e)
            # continue
        # send_shutter_RAM(fhand)
        # fhand.close()
        
    elif inp == 'RP':
        read_periphery()

    elif inp == 'RM':
        #When reading back the matrix, must turn off the shutter, else ASIC will be spewing out data during the readback
        cmd_payload = bytearray(1028)
        cmd_payload[0] = 0x50
        cmd_payload[2] = 0
        cmd_payload[4] = 0
        cmd_payload[5] =0
        sendit(cmd_payload)
        time.sleep(0.1)
        #And dump the data ib the fifos
        cmd_payload = bytearray(196)
        cmd_payload[0] = 0x82
        sendit(cmd_payload)

        inp1 = input("which chip (0-3)?")
        chip = int(inp1)
        #Get the PCR value and the GENCONFIGREG
        try:
            fhand = open(configfilename)
        except Exception as e:
            print (e)
            continue
        send_matrix(chip, fhand, 0)
        fhand.close()
        PCR_val_rev = reverse_bits(PCR_val,6)
        #Reset the readout logic- need to do this before any readback
        cmd_payload = bytearray(196)
        cmd_payload[0] = 0x80
        sendit(cmd_payload)
        time.sleep(.05)
        #Also, turn off the test pulser, to get rid of the "TP_finished" responses
        send_periph_reg(chip, 0x30, GeneralConfig & ~0x20)

        #print(PCR_val_rev)
        num_good_PCRs = 0
        num_px_mx_read = 0
        packet_count = 0
        #The science packets contain 1492 responses of 6B each.  Each column request causes the ASIC to transmit 256 responses, 
        #  so 1536B.  So it takes 6 column requests to fill up one UDP packet.  We'll request 6 columns, then process two UDP packets
        #  then repeat til we have them all
        #Need to flush out old science data first
        flush_sci_buf()
        #Loop through an extra time, but don't send out the commands the last time
        for loopcount in range(44):         
            for n in range(6):
                if loopcount<43:
                    column = loopcount*6+n
                    if (loopcount == 42) & (n == 4): break
                    print("Column ", column, "\r",end='')
                    cmd_payload = bytearray(196)
                    cmd_payload[0] = 0x60
                    cmd_payload[1] = column
                    cmd_payload[2] = chip
                    sendit(cmd_payload)
                    time.sleep(.002)
            #print(loopcount)
            #This is kludgy but it works
            if loopcount == 43: time.sleep(0.5)
            for sci_pkt_count in range(3):
                try:
                    OK = 1
                    reply = sci_sock.recvfrom(bytes_in_science_payload)
                except:
                    print ("no reply")
                    OK=0
                if OK:
                    numbytes = len(reply[0])
                    if numbytes == bytes_in_science_payload:
                        #print ("Bytes Received = " + str(numbytes))
                        bytesback = reply[0]
                        #We only want science packets from the selected chip
                        if ((bytesback[1]>>6) != chip):
                            sci_pkt_count -= 1
                        else:
                            serno = (((bytesback[1]<<8) + bytesback[0]) & 0x3fff)
                            print("Sci Pkt Serno = ", hex(serno))
                            numresp = int((numbytes-2)/6)
                            for n in range (numresp):
                                resp = 0
                                for m in range(11,5,-1):
                                    resp = resp<<8
                                    resp = resp | (bytesback[6*n + m])
                                #print(n, hex(resp))
                                if (resp & 0xf00000000000) == 0x900000000000:
                                    num_px_mx_read += 1
                                    #it's a pixel matrix value
                                    if ((resp>>14) & 0x3f) != PCR_val:
                                        pixadd = (resp>>28) &0xffff
                                        this_PCR = (resp>>14) & 0x3f
                                        print("PCR mismatch: Global PCR = ", hex(PCR_val), " this one = ",hex(this_PCR),end='')
                                        a = pixadd_2_colrow(pixadd)
                                        print("  Column ", a[0], " Row ", a[1])
                                    else: num_good_PCRs+=1
                                #else: print(hex(resp))
        
        print("# Good PCR Compares= ", num_good_PCRs)
        print("Pixel matrix values read = ", num_px_mx_read)
        #restore the GENCONFIGREG
        send_periph_reg(chip, 0x30, GeneralConfig)
        #restore the shutter settings
        #time.sleep(3)
        try:
            fhand = open(configfilename)
        except Exception as e:
            print (e)
            continue
        send_shutter_RAM(fhand)
        fhand.close()

    elif inp == 'SCAN':
        fhand_log = open(dacscan_filename, 'w')

        inp1 = input("Which Chip (0-3)")
        chip = int(inp1)
        inp = input("Which DAC (1-18) (1)")
        if inp=="": inp = '1'
        whichDAC = int(inp)
        DACmax = 255
        if (whichDAC == 2): DACmax = 15
        if (whichDAC == 7): DACmax = 15
        if (whichDAC == 9): DACmax = 15
        if (whichDAC == 11): DACmax = 15
        if (whichDAC == 6): DACmax = 511
        if (whichDAC == 16): DACmax = 511
        fhand_log.write("DAC Scan for ASIC " + str(chip) + " DAC " + str(whichDAC) + " \n")

        cmd_payload = bytearray(196)
        for n in range(len(cmd_payload)): cmd_payload[n]=0
        cmd_payload[0] = 0x90
        cmd_payload[1] = whichDAC
        cmd_payload[2] = chip
        sendit(cmd_payload)
        time.sleep(1)
        numpackets = 0     
        while(numpackets<5):
            try:
                OK = 1
                reply = sock.recvfrom(1030)
                #print(len(reply[0]))
                numpackets +=1
            except:
                print ("no reply")
                OK=0
            if (OK):
                print ("Bytes Received = " + str(len(reply[0])))
                bytesback = reply[0]
                for n in range(DACmax):
                    val = (bytesback[2*n+2] & 0xff) + (bytesback[2*n+3] << 8)
                    print(n, val)
                    fhand_log.write(str(n) + "," + str(val) + '\n')
                break
        fhand_log.close()

    elif inp == 'PH':
        inp1 = input("which chip (0-3)?")
        chip = int(inp1)
        inp = input("# Steps, -32768 to +32767")
        steps = int(inp)
        cmd_payload = bytearray(196)
        for n in range(len(cmd_payload)): cmd_payload[n]=0
        cmd_payload[0] = 0xa0
        if steps<0: steps = steps + 65536    
        cmd_payload[2] = chip
        cmd_payload[4] = steps & 0xff
        cmd_payload[5] = steps >> 8
        sendit(cmd_payload)
        
    elif inp == 'PHSET':
        #Get the clock freq from the config file
        try:
            fhand = open(configfilename)
        except Exception as e:
            print (e)
            continue
        #get the data clock setting
        send_tp3_params(0, fhand, 0)
        #Only implemented for 320, 160, and 80 MHz
        #print ("OutBlockConfig = ", hex(OutBlockConfig))
        clock_code = (OutBlockConfig>>13) & 0x7
        if clock_code == 3: clock_freq = 80
        elif clock_code == 2: clock_freq = 160
        elif clock_code == 1: clock_freq = 320
        else:
            print("clock code not allowed")
            break
        print ("clock Freq = ", clock_freq)
        first_setting = first_setting_loclock
        step_size = step_size_loclock
        num_steps = num_steps_loclock
        if (clock_freq == 320):
            first_setting = first_setting_hiclock
            step_size = step_size_hiclock
            num_steps = num_steps_hiclock
        if first_setting < 0: first_setting += 65536
        
        inp1 = input("which chip (0-3)?")
        chip = int(inp1)
        phset(chip, first_setting, step_size, num_steps)

    elif inp == 'X':
        cmd_payload = bytearray(5900)
        for n in range(len(cmd_payload)): cmd_payload[n]=0
        sendit(cmd_payload)
        
    elif inp == 'F':
        Set_All_FOXSI()
        ChipID_AST = read_periphery()
        set_DACs_Matrix_from_XML("FOXSI4_Matrix_DACs_Config.xml", ChipID_AST)
        Set_Science_Mode("SD")
        Open_Shutter_Forever()

"""
