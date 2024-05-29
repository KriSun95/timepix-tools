#!/bin/bash

# Function to check if the FOXSI_TPX3X4_control.py script finishes within a certain time
check_script_timeout() {
    local script_pid=$1
    local timeout_sec=$2
    local count=0

    while ps -p $script_pid > /dev/null; do
        sleep 1
        ((count++))
        if [ $count -gt $timeout_sec ]; then
            return 1
        fi
    done
    return 0
}

# Continuously check MTU value of interface eth1
while true; do
    mtu=$(ip addr show eth1 | awk '/mtu/ {print $5}')
    # Get the IP address of eth1
    eth1_ip=$(ip addr show eth1 | grep -Po 'inet \K[\d.]+')

    # Check if the IP address matches the specified one
    if [[ "$mtu" -eq 9000 ]] && [[ "$eth1_ip" == "192.168.1.100" ]]; then
#	sleep 10
        echo "MTU value is already 9000"  > /home/pi/tpx3_log.log
        echo "The ip in eth1 is: "$eth1_ip  >> /home/pi/tpx3_log.log
        echo $(date "+%Y-%m-%d %H:%M:%S") >> /home/pi/tpx3_log.log
#        /usr/bin/python3 /home/pi/FOXSI_Python/chk_fpga_hk.py >>/home/pi/tpx3_log.log

#	sleep 10
        echo 'Startup Config TPX3X4...'
        echo $(date "+%Y-%m-%d %H:%M:%S") >> /home/pi/tpx3_log.log
	counter=0
        # Loop until FOXSI_TPX3X4_control.py finishes within 55 seconds
        while true; do
    	    # Run FOXSI_TPX3X4_control.py script
            /usr/bin/nice --20 /usr/bin/python3 /home/pi/FOXSI_Python/FOXSI_TP3X4_control.py >> /home/pi/tpx3_log.log &
            control_script_pid=$!
            if check_script_timeout $control_script_pid 55; then
                echo "Loop 1 FOXSI_TPX3X4_control.py script finished within 55 seconds."  >> /home/pi/tpx3_log.log
		break
            else
                echo "Loop 1 FOXSI_TPX3X4_control.py script did not finish within 55 seconds. Restarting..."  >> /home/pi/tpx3_log.log
                kill -9 $control_script_pid  # Kill the script
		((counter++))
            fi
    	    # Check if the counter is 3
    	    if [ $counter -eq 2 ]; then
        	echo "Loop 1 Counter reached 3. Exiting the loop." >> /home/pi/tpx3_log.log
        	break
    	    fi
        done
	sleep 1
	counter=0
        # Loop until FOXSI_TPX3X4_control.py finishes within 55 seconds
        echo $(date "+%Y-%m-%d %H:%M:%S") >> /home/pi/tpx3_log.log
        while true; do
    	    # Run FOXSI_TPX3X4_control.py script
            /usr/bin/nice --20 /usr/bin/python3 /home/pi/FOXSI_Python/FOXSI_TP3X4_control.py >> /home/pi/tpx3_log.log &
            control_script_pid=$!
            if check_script_timeout $control_script_pid 55; then
                echo "Loop 2 FOXSI_TPX3X4_control.py script finished within 55 seconds."  >> /home/pi/tpx3_log.log
		break
            else
                echo "Loop 2 FOXSI_TPX3X4_control.py script did not finish within 55 seconds. Restarting..."#  >> /home/pi/tpx3_log.log
                kill -9 $control_script_pid  # Kill the script
		((counter++))
            fi
    	    # Check if the counter is 3
    	    if [ $counter -eq 2 ]; then
        	echo "Loop 2 Counter reached 3. Exiting the loop." >> /home/pi/tpx3_log.log
        	break
    	    fi
        done
        echo 'Config TPX3X4 loaded...' >> /home/pi/tpx3_log.log
        echo $(date "+%Y-%m-%d %H:%M:%S") >> /home/pi/tpx3_log.log

#        sleep 1
#        # echo 'Startup saving data with TSHARK...'
#        /usr/bin/dumpcap -i eth1 -f 'udp' -b  duration:1 -w /home/pi/udp_logs/foxsi_dumpcap.pcap -q &
#        echo 'SHARK loaded...' >> /home/pi/tpx3_log.log
#        echo $(date "+%Y-%m-%d %H:%M:%S") >> /home/pi/tpx3_log.log

#	sleep 5
#        /usr/bin/python3 /home/pi/foxsi4_UDP_reader.py >> /home/pi/tpx3_log.log&
#        echo 'UDP code loaded...' >> /home/pi/tpx3_log.log
#        echo $(date "+%Y-%m-%d %H:%M:%S") >> /home/pi/tpx3_log.log

#        #echo 'Startup formatter code...'
#        sleep 1
#        /usr/bin/python3 /home/pi/FOXSI_TIMEPIX_formatter_jan121_flightpi.py &
#        echo 'Formatter loaded...' >> /home/pi/tpx3_log.log
#        echo $(date "+%Y-%m-%d %H:%M:%S") >> /home/pi/tpx3_log.log
        break
    else
        echo "MTU value is $mtu, still waiting to change 9000..."
        echo $(date "+%Y-%m-%d %H:%M:%S") >> /home/pi/tpx3_log.log
        sleep 2  # Wait for a few seconds before retrying
    fi
done

