#!/bin/bash

        # echo 'Startup saving data with TSHARK...'
        /usr/bin/dumpcap -i eth1 -f 'udp' -b  duration:1 -w /home/pi/udp_logs/foxsi_dumpcap.pcap -q &
        echo 'SHARK loaded...' >> /home/pi/tpx3_log.log
        echo $(date "+%Y-%m-%d %H:%M:%S") >> /home/pi/tpx3_log.log

	sleep 5
        /usr/bin/python3 /home/pi/foxsi4_UDP_reader.py >> /home/pi/tpx3_log.log&
        echo 'UDP code loaded...' >> /home/pi/tpx3_log.log
        echo $(date "+%Y-%m-%d %H:%M:%S") >> /home/pi/tpx3_log.log

        #echo 'Startup formatter code...'
        sleep 1
        /usr/bin/python3 /home/pi/FOXSI_TIMEPIX_formatter_jan121_flightpi.py &
        echo 'Formatter loaded...' >> /home/pi/tpx3_log.log
        echo $(date "+%Y-%m-%d %H:%M:%S") >> /home/pi/tpx3_log.log

