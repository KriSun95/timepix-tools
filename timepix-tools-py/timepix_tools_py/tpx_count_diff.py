#tpx_count_diff.py 
import pcapng
from pcapng import FileScanner 
import struct
import pandas as pd 
import os  
from datetime import datetime 
from time import sleep
import glob
import matplotlib.pyplot as plt
import numpy as np
import glob
# takes two sets of file(s) and compares the difference in count rate 
# this code was made to compute a prehv and hv count rate difference from pcap files
# for the foxsi-4 experiment to be used for GSE information at PFRR 

# 3/17
#Change for your system: 
dirt1 = "/home/savannahperezpiel/Desktop/pcap_test/hv_off" 
dirt2 = "/home/savannahperezpiel/Desktop/pcap_test/hv_on"
file_factor = 'All' # 5 ##'All' #can be 'All', or you can change to an integer
############################################################################
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

    TimepixData = sci_pkt[48:]
    science_data = []

    if len(TimepixData) % 6 != 0:
        print("Something off about packet length....")
    else:
        idx = 0
        while idx < int(len(TimepixData)):
        #while idx < 1000:  ## can change to this is files are too big, this will cut it down
            chunk = TimepixData[idx:(idx + 6)]
            msb_4 = (struct.unpack('B', chunk[5:6])[0] >> 4) & 0b1111
            if msb_4 == 0x0B:
                idx += 6
                datadrivenchunk = chunk
                science_data.append(process_data_driven_chunk(datadrivenchunk,chip_number))
                continue
            else:
            	idx += 6
            	continue
    return science_data

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
    if chip_number == 0:
        rot = 0
    elif chip_number == 1:
        rot = 180
    elif chip_number == 2:
        rot = 180
    elif chip_number == 3: 
        rot = 0
    x, y = rotate_point_on_rotated_matrix(xi, yi, 256, rot) 
    data = {"Chip ID": chip_number, "Matrix Index": (x, y), "ToA": toa, "ToT": tot, "FToA": ftoa, "Overflow": 0}
    return data     # Collect data in a dictionary for DataFrame, and return 



def process_logfile(filename): 
    
    science_df = pd.DataFrame(columns=["Chip ID", "Matrix Index", "ToA", "ToT", "FToA", "Overflow"])
    service_packets = []
    start_timestamp = None
    end_timestamp = None
    with open(filename, 'rb') as fp:
        scanner = FileScanner(fp)
        for i, block in enumerate(scanner):
            if isinstance(block, pcapng.blocks.EnhancedPacket):
                #print(block.timestamp)
                timestamp = block.timestamp
                if start_timestamp is None or timestamp < start_timestamp:
                    start_timestamp = timestamp
                if end_timestamp is None or timestamp > end_timestamp:
                    end_timestamp = timestamp
                pkt_data = block.packet_data

                if block.packet_len == 9000:
                    #print('Type: Science Packet')
                    sci_pkt = pkt_data
                    science_df = pd.concat([science_df, pd.DataFrame(process_science_packet(sci_pkt))], ignore_index=True)

    if start_timestamp is None or end_timestamp is None:
        print("Timestamp not found in Enhanced Packet blocks.")
        time_difference_seconds = 0
    else:
        start_time = datetime.utcfromtimestamp(start_timestamp)
        end_time = datetime.utcfromtimestamp(end_timestamp)
        time_difference_seconds = (end_time - start_time).total_seconds()
    return science_df, time_difference_seconds 


def process(hv_ons,hv_offs):
	hv_on_cnt = []
	hv_off_cnt = []
	for i in range(len(hv_ons)):
		res_hv_ons,td_ons = process_logfile(hv_ons[i])
		l_hv_ons = len(res_hv_ons)
		hv_on_cnt.append(l_hv_ons)
		del(res_hv_ons)
		res_hv_offs,td_offs = process_logfile(hv_offs[i])
		l_hv_offs = len(res_hv_offs)
		hv_off_cnt.append(l_hv_offs)
		del(res_hv_offs)
		#print("")
		## for a single file: 
		# print("hv on counts : {}".format(l_hv_ons))
		# print("hv_off_counts : {}".format(l_hv_offs))
		# print("hv_on - hv_off = {}".format(l_hv_ons - l_hv_offs))
	print("counts from hv on files: {}".format(sum(hv_on_cnt)))
	print("counts from hv off files: {}".format(sum(hv_off_cnt)))
	print("total difference from all files: {}".format(sum(hv_on_cnt) - sum(hv_off_cnt)))


# Make sure you have the same length of pcap files in each folder: 
hv_on_f, hv_off_f = glob.glob(dirt1+"/*.pcap"), glob.glob(dirt2+"/*.pcap")

if (len(hv_on_f) - len(hv_off_f)) > 0:
	min_length = min(len(hv_on_f), len(hv_off_f))
	print(f"hv_on has {len(hv_on_f)} files and hv_off has {len(hv_off_f)} files, we will trim to {min_length}")
	hv_on_f = hv_on_f[:min_length]
	hv_off_f = hv_off_f[:min_length]
else:
	print("same length for each set of pcaps")


# Calculate the difference in count-rates
if file_factor == 'All':
	print("all files used")
	process(hv_on_f,hv_off_f)
else: 
	file_factor = int(file_factor) #male file factor an integer number
	if file_factor > len(hv_off_f): 
		print("file factor larger than folder contents- all files used")
		process(hv_on_f,hv_off_f)
	print("{} files used".format(file_factor))
	process(hv_on_f[:file_factor],hv_off_f[:file_factor])


