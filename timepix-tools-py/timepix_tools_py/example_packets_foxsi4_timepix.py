# example_packets_foxsi4_timepix.py
# based on formatter_Scratch_pixelbuilder.py 
# and timepix_parser.py 

# this code serves to generate packets of data the
# same way they will be sent to the formatter and 
# read in the parser. 

#You should be able to just run as is 
#and see the output examples in terminal 

import numpy as np 
import random
from datetime import datetime

#for pixel data packet (not in use atm)
class Pixel:
    def __init__(self, x: int = 0, y: int = 0, toa: int = 0, tot: int = 0, chip: int = 0):
        self.x = x 									#u8 
        self.y = y 									#u8 
        self.toa = toa 								#u16
        self.tot = tot 								#u16
        self.chip = chip 							#2 bits (val = 0-3)

# for readrates packet 0x81
class ReadRatesPacket:
    def __init__(self, mean_tot: int = 0, flx_rate: int = 0):
        self.mean_tot = mean_tot  					# 2-byte integer (0-1022)
        self.flx_rate = flx_rate  					# 2-byte integer (four digits)

# for read all housekeeping packet 
# read all housekeeping 0x88
class ReadALLHKPacket:
    def __init__(self, board_t1: int = 0, board_t2: int = 0, asic_voltages: list = [0, 0, 0, 0],
                 asic_currents: list = [0, 0, 0, 0], fpga_values: list = [0, 0, 0], rpi_storage_fill: int = 0):
        self.board_t1 = board_t1            		# 3-digit integer
        self.board_t2 = board_t2            		# 3-digit integer
        self.asic_voltages = asic_voltages  		# List of 4 integers (each with a max of 5 digits)
        self.asic_currents = asic_currents  		# List of 4 integers (each with a max of 4 digits)
        self.fpga_values = fpga_values  			# List of 3 integers (each with a max of 4 digits)
        self.rpi_storage_fill = rpi_storage_fill    # 3-digit integer

# for read temp packets 0x89
class ReadTempPacket:
    def __init__(self, fpgat: int = 0, board_t1: int = 0, board_t2: int = 0):
        self.fpgat = fpgat  						# 3 digits
        self.board_t1 = board_t1  					# maximum 3 digits
        self.board_t2 = board_t2  					# maximum 3 digits

# for flags 
class FlagByte:
    def __init__(self):
        self.flags = 0         								# Initialize with all flags set to 0
    def raise_flag(self, flag_index):
        self.flags |= (1 << flag_index)         			# Set the bit at the specified index to 1
    def clear_flag(self, flag_index):         				# Set the bit at the specified index to 0
        self.flags &= ~(1 << flag_index)
    def is_flag_set(self, flag_index):				        # Check if the bit at the specified index is 1
        return bool(self.flags & (1 << flag_index))
    def get_flags(self):					        		# Return the entire byte representing flags
        return self.flags

# to create a packet of pixel data 
def create_packet(pixel: Pixel):
    packet = [0] * 6													# Define a 6 byte packet 
    packet[0] = pixel.toa & 0xFF 										# TOA is all 8 
    packet[1] = pixel.toa >> 8											# and the following 8 
    packet[2] = pixel.tot & 0xFF										# ToT is all 8 
    packet[3] = ((pixel.chip & 0x3) << 6) | ((pixel.tot >> 8) & 0x3F)	# Pixet Chip is 2 highest bits, Rest is ToT
    packet[4] = pixel.x 												# All 8
    packet[5] = pixel.y 												# All 8 
    return packet

# unpacket it 
def unpack_packet(packet):
    pixel = Pixel()
    pixel.toa = packet[0] | (packet[1] << 8)
    pixel.tot = packet[2] | ((packet[3] & 0x3F) << 8)
    pixel.chip = (packet[3] >> 6) & 0x3
    pixel.x = packet[4]
    pixel.y = packet[5]
    return pixel

def create_read_rates_packet(data: ReadRatesPacket):
    packet = [0] * 4  								# Define a 4-byte packet
    packet[0] = data.mean_tot & 0xFF
    packet[1] = (data.mean_tot >> 8) & 0xFF
    packet[2] = data.flx_rate & 0xFF
    packet[3] = (data.flx_rate >> 8) & 0xFF
    return packet

def unpack_read_rates_packet(packet):
    data = ReadRatesPacket()
    data.mean_tot = packet[0] | (packet[1] << 8)
    data.flx_rate = packet[2] | (packet[3] << 8)
    return data

def create_read_all_hk_packet(data: ReadALLHKPacket):
    packet = [0] * 27 # Define a 27-byte packet
    packet[0] = data.board_t1 % 256
    packet[1] = data.board_t1 // 256
    packet[2] = data.board_t2 % 256
    packet[3] = data.board_t2 // 256
    for i in range(4):    									# Packing ASIC voltages (5 digits each)
        packet[4 + i * 5] = data.asic_voltages[i] % 256
        packet[5 + i * 5] = data.asic_voltages[i] // 256
        packet[6 + i * 5] = data.asic_voltages[i] // 65536
    for i in range(4):    									# Packing ASIC currents (4 digits each)
    	packet[7 + i * 4] = data.asic_currents[i] % 256
    	packet[8 + i * 4] = data.asic_currents[i] // 256
    for i in range(3):										# Packing FPGA voltages (4 digits each)
        packet[9 + i * 4] = data.fpga_values[i] % 256
        packet[10 + i * 4] = data.fpga_values[i] // 256
    packet[11] = data.rpi_storage_fill % 256				# Packing RPI storage fill (3 digits)
    packet[12] = data.rpi_storage_fill // 256
    return packet


def unpack_read_all_hk_packet(packet):
    data = ReadALLHKPacket() #DEFINED IN EXAMPLE BELOW 
    data.board_t1 = packet[0] + (packet[1] << 8)
    data.board_t2 = packet[2] + (packet[3] << 8)
    for i in range(4):									    	# Unpacking ASIC voltages (5 digits each)
        data.asic_voltages[i] = packet[4 + i * 5] + (packet[5 + i * 5] << 8) + (packet[6 + i * 5] << 16)
    for i in range(4):											# Unpacking ASIC currents (4 digits each)
        data.asic_currents[i] = packet[7 + i * 4] + (packet[8 + i * 4] << 8)	
    for i in range(3):   										# Unpacking FPGA voltages (4 digits each)
        data.fpga_values[i] = packet[9 + i * 4] + (packet[10 + i * 4] << 8)
    data.rpi_storage_fill = packet[11] + (packet[12] << 8)      # Unpacking RPI storage fill (3 digits)   
    return data


def create_read_temp_packet(data: ReadTempPacket):
    packet = [0] * 9  # Define a 9-byte packet
    packet[0] = data.fpgat % 256 			    	# Packing FPGA T (3 digits)
    packet[1] = data.fpgat // 256
    packet[2] = data.board_t1 % 256 				# Packing Board T1 (3 digits)
    packet[3] = data.board_t1 // 256
    packet[4] = data.board_t2 % 256			    	# Packing Board T2 (3 digits)	
    packet[5] = data.board_t2 // 256
    return packet

def unpack_read_temp_packet(packet):
    data = ReadTempPacket()
    data.fpgat = packet[0] + (packet[1] << 8)     	# Unpacking FPGA T (3 digits)
    data.board_t1 = packet[2] + (packet[3] << 8)    # Unpacking Board T1 (3 digits)  
    data.board_t2 = packet[4] + (packet[5] << 8)    # Unpacking Board T2 (3 digits)
    return data

#########################################################
#### USAGE EXAMPLES START HERE ##########################
#########################################################
#########################################################
# Create and Unpack Example Packet ######################
print("Building pixel packet, values = ")
chip_number = 1
x_location = 1
y_location = 2
toa_value = 65
tot_value = 4
print("chip number:{} x:{} y:{} toa:{} tot:{}".format(chip_number,x_location,y_location,toa_value,tot_value))
pixel_packet=create_packet(Pixel(x=x_location, y=y_location, toa=toa_value, tot=tot_value, chip=chip_number))
print("pixel packet to be sent: {}".format(bytes(pixel_packet)))
print("Unpacking pixel packet...:")
original_pixel = unpack_packet(pixel_packet)
print("Unpacked:")
print("Received Chip Number:", original_pixel.chip)
print("Received X,Y:{},{}".format(original_pixel.x,original_pixel.y))
print("Received toa:",original_pixel.toa)
print("Received tot:",original_pixel.tot)
#print(original_pixel.__dict__)
#########################################################
print("")
print("")
#########################################################
# Create and Unpack Example Read Rates Packet ###########
print("Building read rates packet, values = ")
mean_tot = 50
flx_rate = 55
print("mean tot = {}, flux rate = {}".format(mean_tot,flx_rate))
read_rates_data = ReadRatesPacket(mean_tot=mean_tot, flx_rate=flx_rate)
read_rates_packet = create_read_rates_packet(read_rates_data)
print("read rates packet to be sent:",bytes(read_rates_packet))
print("Unpacking read rates packet...")
received_data = unpack_read_rates_packet(list(read_rates_packet))
print("Received MeanToT:", received_data.mean_tot)
print("Received FlxRate:", received_data.flx_rate)
#########################################################
print("")
print("")
#########################################################
# Example usage read all housekeeping 0x88 ##############
print("Building read all houskeeping packet, values = ")
board_t1 = 250
board_t2 = 300
asicv1 = 12345
asicv2 = 23456
asicv3 = 78910
asicv4 = 66166
asic_voltages = [asicv1,asicv2,asicv3,asicv4]
asicI1 = 2333
asicI2 = 1000
asicI3 = 1001
asicI4 = 2555
asic_currents = [asicI1,asicI2,asicI3,asicI4]
fpgaV = 5678
fpgaI = 6789
fpgat = 99
fpga_values = [fpgaV, fpgaI, fpgat]
rpi_storage_fill = 10
print("Board Temp 1 {}, Temp 2 {}".format(board_t1,board_t2))
print("Asic Voltages: \n 1,2,3,4:",asic_voltages)
print("Asic Currents: \n 1,2,3,4:",asic_currents)
print("FPGA Values: \n V: I: T:",fpga_values)
print("rpi storage fill: ",rpi_storage_fill)

read_all_hk_data = ReadALLHKPacket(
    board_t1=board_t1,
    board_t2=board_t2,
    asic_voltages=[asicv1, asicv2, asicv3, asicv4],
    asic_currents=[asicI1, asicI2, asicI3, asicI4],
    fpga_values=[fpgaI, fpgaT, fpgaT], #fpga voltage, fpga current, fpga temperature 
    rpi_storage_fill=rpi_storage_fill)
read_all_hk_packet = create_read_all_hk_packet(read_all_hk_data)
print("read all housekeeping packet to be sent:",bytes(read_all_hk_packet))
print("Unpacking read all housekeeping packet...")
received_data = unpack_read_all_hk_packet(list(read_all_hk_packet)) 
print("")
print("")
print("Received Board T1:", received_data.board_t1)
print("Received Board T2:", received_data.board_t2)
print("Received ASIC Voltages:", received_data.asic_voltages)
print("Received ASIC Currents:", received_data.asic_currents)
print("Received FPGA Voltages:", received_data.fpga_values)
print("Received RPI Storage Fill :", received_data.rpi_storage_fill)
#########################################################
print("")
print("")
#########################################################
#example usage read temp 0x89 ###########################
print("Building read temperature packet: values = ")
print("FPGA Temperature:", fpgat)
print("Board Temperature 1:", board_t1)
print("Board Temperature 2:", board_t2)
#fpgat = fpgat
#board_t1 = board_t1		#redundant
#board_t2 = board_t2		#defined in previous packet if using
read_temp_data = ReadTempPacket(fpgat=fpgat, board_t1=board_t1, board_t2=board_t2)
read_temp_packet = create_read_temp_packet(read_temp_data)
print("read all temperature packet to be sent:", bytes(read_temp_packet))
print("Unpacking read all temperature packet...")
unpacked_data = unpack_read_temp_packet(read_temp_packet)
print(f"Unpacked Data: FPGAT={unpacked_data.fpgat}, BoardT1={unpacked_data.board_t1}, BoardT2={unpacked_data.board_t2}")
#########################################################
print("")
print("")
#########################################################
### for using flagbyte (flags) tbd 0x8b/0xA4
print("Flag-Set Example:")
flag_number = 2
flag_byte = FlagByte()	# Create an instance of FlagByte
print("Raising flag: ",flag_number)
flag_byte.raise_flag(flag_number) 
print("Is flag {} set? {}".format(flag_number,flag_byte.is_flag_set(flag_number))) # check if flag is set

print("Clearing flag: ", flag_number)
flag_byte.clear_flag(flag_number) # ex clear the flag at index 2
print("Is flag {} set? {}".format(flag_number,flag_byte.is_flag_set(flag_number))) # check if flag is set
all_flags = flag_byte.get_flags() # Get the entire byte representing flags (sent with read flags command)
print("flags as binary: ")
print(bin(all_flags))


###From bin(all_flags) which is sent down as telemetry you can undo it by: 


def get_raised_flags(binary_flags):
    binary_flags = binary_flags[2:]  # Remove the '0b' prefix
    raised_flags = [i + 1 for i, bit in enumerate(reversed(binary_flags)) if bit == '1']
    return raised_flags

# Example usage:
all_flags = flag_byte.get_flags()
binary_flags = bin(all_flags)
raised_flags = get_raised_flags(binary_flags)

print("Flags as binary:", binary_flags)
print("Raised flags:", raised_flags)