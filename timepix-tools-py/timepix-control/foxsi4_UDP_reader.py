#UDP_Reader Updates::from rocket/2/13 
#3/16
## scaled flx rate from 100,000 -> 1,000
## deleted displays
# tested on bench - works

import pcapng
from pcapng import FileScanner 
import struct
import pandas as pd 
import os  
from datetime import datetime 
import numpy as np
from time import sleep
import glob


def rotate_point_on_rotated_matrix(x, y, matrix_size, rotation_degrees):
    rotation_degrees = rotation_degrees % 360
    num_rotations = rotation_degrees // 90
    for _ in range(num_rotations):
        x, y = matrix_size - y - 1, x 
    return x, y

def process_science_packet(sci_pkt):
    byte0 = struct.unpack('B', sci_pkt[42:43])[0]
    byte1 = struct.unpack('B', sci_pkt[43:44])[0]
    chip_number = (byte1 >> 6) & 0b11   
    packet_number = ((byte1 & 0b00111111) << 8) | byte0
    timer = struct.unpack('<I', sci_pkt[44:48])[0]

    # print("Chip Number:", chip_number)
    # print("Packet Number:", packet_number)
    # print("Time Elapsed: {} ns ".format(timer * 6.4))

    TimepixData = sci_pkt[48:]
    science_data = []

    if len(TimepixData) % 6 != 0:
        print("Something off about packet length....")
    else:
        print("Looks good... beginning to sort Science Packet Data")
        idx = 0
        while idx < len(TimepixData):
            chunk = TimepixData[idx:(idx + 6)]
            msb_4 = (struct.unpack('B', chunk[5:6])[0] >> 4) & 0b1111
            #print(chunk)
            if msb_4 == 0x0A:
                #print("Device in Pixel Frame Mode (1010)\n")
                idx += 6
                framedatachunk = chunk
                continue
            elif msb_4 == 0x0B:
                #print("Device in Data Driven Mode (1011)\n")
                idx += 6
                datadrivenchunk = chunk
                science_data.append(process_data_driven_chunk(datadrivenchunk,chip_number))
                continue

            elif msb_4 == 0x60:
                #print("0x60 recd :sequential number of the shutter per trigger sequence \n")
                idx += 6
                continue

            elif msb_4 == 0x58:
                #print("0x58 recd: Heart Beat\n") 
                idx += 6
                continue

            elif msb_4 == 0x50 or msb_4 == 0x51 or msb_4 == 0x52 or msb_4 == 0x53: 
                #print("0x50 recd: FPGA Time of the external trigger or software trigger\n") 
                idx += 6
                continue

            elif msb_4 == 0x44:
                #print("0x44 recd:  TPX3 clock in 25 ns counts // Wrap up 107.3742 seconds\n")
                idx += 6
                continue

            elif msb_4 == 0x46: 
                #print("0x46 recd: from tpx3- raise time of the shutter in TPX3 clock counts\n ")
                idx += 6
                continue

            elif msb_4 == 0x5D or msb_4 == 0x5E or msb_4 == 0x5F or msb_4 == 0x5C:
                #print("0x5D,5E,5F,5C: recd: Time of external trigger on another SMA input (not external shutter) FPGA clock\n  ")
                idx += 6
                continue

            elif msb_4 == 0x7: 
                #print("0x7 recd - end of read?")
                idx += 6
                continue

            elif msb_4 == 0x4: 
                #print("0x4 A 0x4 Command")
                idx += 6
                continue
            else:
                # print("Device Mode Unspecified or Unknown. Contuniung ...\n")
                # print("Unknown Command or Mode:{}".format(hex(msb_4)))
                # print("~~~~~~~unknown mode ~~~~~~~~~~")
                idx += 6
                continue
    return science_data


def process_service_packet(serv_pkt): #processes houskeeping data and saves in a npz file elsewhere 
    bytesback = serv_pkt
    #VREF is the HK ADC full-scale voltage
    VREF =2500
    #Current monitor scale factor
    ISCALE = 1000/357 #amps per volt
    hk_interval = 1
    val_array=[]
    #there are 36 values in all: 4 values read from each of 4 ASICs in bytes 4 to 35, and
    # 20 values starting at byte 36 read back from the ADCs, then 3 temperature values.  We'll display these
    for n in range(39):
        val_array.append(int(bytesback[2*n+4]) + 256*int(bytesback[2*n+5]))
        #print (hex(val_array[n]))
    #print(hex(val_array[20]),hex(val_array[21]))
    #drop the 3 LSBs
    temp1 = int(val_array[36]/8)
    if temp1 > 4095: temp1 = temp1 - 8192
    temp1 = temp1/16
    #drop the 3 LSBs
    temp2 = int(val_array[37]/8)
    if temp2 > 4095: temp2 = temp2 - 8192
    temp2 = temp2/16
    ##the temp from the FPGA XADC
    ftemp = val_array[38]
    ftemp = (((ftemp/65536)/0.00198421639) - 273.15)
    V18 = int(val_array[16]*VREF/4096)
    V33 = int(val_array[17]*VREF/4096 * 2)
    V25 = int(val_array[18]*VREF/4096 * 2)
    I0A = int(val_array[20]*VREF/4096 * ISCALE)
    I0D = int(val_array[21]*VREF/4096 * ISCALE)
    I1A = int(val_array[22]*VREF/4096 * ISCALE)
    I1D = int(val_array[23]*VREF/4096 * ISCALE)
    I2A = int(val_array[24]*VREF/4096 * ISCALE)
    I2D = int(val_array[25]*VREF/4096 * ISCALE)
    I3A = int(val_array[26]*VREF/4096 * ISCALE)
    I3D = int(val_array[27]*VREF/4096 * ISCALE)
    V0A = int(val_array[28]*VREF/4096)
    V0D = int(val_array[29]*VREF/4096)
    V1A = int(val_array[30]*VREF/4096)
    V1D = int(val_array[31]*VREF/4096)
    V2A = int(val_array[32]*VREF/4096)
    V2D = int(val_array[33]*VREF/4096)
    V3A = int(val_array[34]*VREF/4096)
    V3D = int(val_array[35]*VREF/4096)
    # print ('{:2.1f}\t'.format(temp1), end='')
    # print ('{:2.1f}\t'.format(temp2), end='')
    # print ('{:2.1f}\t'.format(ftemp), end='')
    # print ('{:2.1f}\t'.format(V33),end='')
    # print ('{:2.1f}\t'.format(V25),end='')
    # print ('{:2.1f}\t'.format(V18),end='')
    # print ('{:2.1f}\t'.format(V0A),end='')
    # print ('{:2.1f}\t'.format(V0D),end='')
    # print ('{:2.1f}\t'.format(V1A),end='')
    # print ('{:2.1f}\t'.format(V1D),end='')
    # print ('{:2.1f}\t'.format(V2A),end='')
    # print ('{:2.1f}\t'.format(V2D),end='')
    # print ('{:2.1f}\t'.format(V3A),end='')
    # print ('{:2.1f}\t'.format(V3D),end='')
    # print ('{:2.1f}\t'.format(I0A),end='')
    # print ('{:2.1f}\t'.format(I0D),end='')
    # print ('{:2.1f}\t'.format(I1A),end='')
    # print ('{:2.1f}\t'.format(I1D),end='')
    # print ('{:2.1f}\t'.format(I2A),end='')
    # print ('{:2.1f}\t'.format(I2D),end='')
    # print ('{:2.1f}\t'.format(I3A),end='')
    # print ('{:2.1f}\t'.format(I3D),end='') 
    data = {
    'temp1': temp1,
    'temp2': temp2,
    'ftemp': ftemp,
    'V33': V33,
    'V25': V25,
    'V18': V18,
    'V0A': V0A,
    'V0D': V0D,
    'V1A': V1A,
    'V1D': V1D,
    'V2A': V2A,
    'V2D': V2D,
    'V3A': V3A,
    'V3D': V3D,
    'I0A': I0A,
    'I0D': I0D,
    'I1A': I1A,
    'I1D': I1D,
    'I2A': I2A,
    'I2D': I2D,
    'I3A': I3A,
    'I3D': I3D,}
    print("making hk npz")
    output_filename = '/home/pi/uart_logs/hk.npz'
    np.savez(output_filename, **data)
    return 

def process_data_driven_chunk(datadrivenchunk,chip_number):
    byte0= struct.unpack('B', datadrivenchunk[0:1])[0] 
    byte1= struct.unpack('B', datadrivenchunk[1:2])[0] 
    byte2= struct.unpack('B', datadrivenchunk[2:3])[0] 
    byte3= struct.unpack('B', datadrivenchunk[3:4])[0] 
    byte4= struct.unpack('B', datadrivenchunk[4:5])[0] 
    byte5= struct.unpack('B', datadrivenchunk[5:6])[0] 

    ftoa = byte0 & 0b00001111
    tot = ((byte0 & 0b11110000) >> 4) | ((byte1 & 0b00111111) << 4)
    toa = ((byte0 & 0b00000011) << 12) | (byte2 << 4) | ((byte3 & 0b11110000) >> 4)
    # address = ((byte3 & 0b00001111) << 12) | (byte4 << 4) | ((byte5 & 0b11110000) >> 4)
    address = (byte3 & 0xF0) >> 4 | byte4 << 4 | (byte5 & 0xF) << 12
    mode = (byte5 & 0b11110000) >> 4
    eoc = (address >> 9) & 0x7F
    sp = (address >> 3) & 0x3F
    pix = address & 0x07
    xi = eoc * 2 + (pix // 4)
    yi = sp * 4 + (pix % 4)
                                    #TEST THAT THIS IS OK WITH IMAGE  
    if chip_number == 0:
        rot = 0
    elif chip_number == 1:
        rot = 180
    elif chip_number == 2:
        rot = 180
    elif chip_number == 3: 
        rot = 0
    x, y = rotate_point_on_rotated_matrix(xi, yi, 256, rot) 
    # print(f"Original Point: ({xi}, {yi})")
    # print(f"Rotated Point: ({x}, {y})")
    data = {"Chip ID": chip_number, "Matrix Index": (x, y), "ToA": toa, "ToT": tot, "FToA": ftoa, "Overflow": 0}
    return data  





def process_logfile(filename): 
    science_df = pd.DataFrame(columns=["Chip ID", "Matrix Index", "ToA", "ToT", "FToA", "Overflow"])
    service_packets = []
    start_timestamp = None
    end_timestamp = None

    with open(filename, 'rb') as fp:
        scanner = FileScanner(fp)
        sblock_counter = 0
        hkblock_counter = 0

        for i, block in enumerate(scanner):
            if isinstance(block, pcapng.blocks.EnhancedPacket):
                print(block.timestamp)
                timestamp = block.timestamp
                if start_timestamp is None or timestamp < start_timestamp:
                    start_timestamp = timestamp
                if end_timestamp is None or timestamp > end_timestamp:
                    end_timestamp = timestamp

                # Process the EnhancedPacket block
                pkt_data = block.packet_data
                #pkt_data = block.packet_data.binary_value
                #print(f"Processing EnhancedPacket {block_counter + 1}, Timestamp: {timestamp}")

                if block.packet_len == 9000:
                    #print('Type: Science Packet')
                    sci_pkt = pkt_data
                    science_df = pd.concat([science_df, pd.DataFrame(process_science_packet(sci_pkt))], ignore_index=True)
                    sblock_counter += 1

                elif block.packet_len == 168:
                    #maybe header in here?
                    #print('Type: Service Packet') 
                    serv_pkt = pkt_data
                    service_packets.append(serv_pkt)
                    process_service_packet(serv_pkt[42:])
                    hkblock_counter += 1 
                else: 
                    print("weird!!!~~~~~~~~")
                    #print(pkt_data)
            else:
                print('block without timestamp')


    print(sblock_counter,hkblock_counter)

    if start_timestamp is None or end_timestamp is None:
        print("Timestamp not found in Enhanced Packet blocks.")
        time_difference_seconds = 0
    else:
        start_time = datetime.utcfromtimestamp(start_timestamp)
        end_time = datetime.utcfromtimestamp(end_timestamp)
        time_difference_seconds = (end_time - start_time).total_seconds()
        #print()f"For this log file: ")
        # print(f"Start Time: {start_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        # print(f"End Time: {end_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        # print(f"Time Difference: {time_difference_seconds} seconds")
    return science_df, time_difference_seconds 

 
def calc_telemetry(df,time_difference): 
    meanToT = int(df['ToT'].mean()) 
    flxrate= int(len(df['ToT'])/time_difference)/1000
    #save to npz file 
    data = {
    'meanToT': meanToT,
    'flxrate': flxrate,
    }
    print("saving telemetry.npz")
    output_filename = '/home/pi/uart_logs/telemetry.npz'
    np.savez(output_filename, **data)
    return meanToT, flxrate



while True:
	sleep(1)
	files = glob.glob('/home/pi/udp_logs/*.pcap')
	files.sort()
	recentfile = files[-2]  ##max(files,key=os.path.getctime)
	res_dataframe, time_difference = process_logfile(recentfile) #time difference in seconds for a log file to be created
	try:
		calc_telemetry(res_dataframe, time_difference) #puts in npz file to be pulled from on the raspberry pi later  
	except:
		print('no hits to calc')
		print(len(res_dataframe))

