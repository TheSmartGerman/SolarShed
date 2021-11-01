#!/bin/bash

#This script assumes you already have the mpp-solar python program running correctly and node_exporter, Prometheus and Grafana working.
# See my other documents for information on that.
# All this simple script does is convert the output for mpp-solar into a .prom file in the /ramdisk folder, so node_-exporter can read it and load into
# the Prometheus database. You can then graph the values in real--time with Grafana.

# mpp-solar parsing script for 1 x 5048 MGX MPP Solar all--in--one devices
# Original:
# Joe Elliott
# v0.4b Nov 2020
# Modified
# Benedikt Geiger
# Oct 2021

# create CPU & LoadAvg with # while :; do :; done
# create DISK load with # find /usr -exec grep joe {} \;
# create Network load with # ping -f 8.8.8.8 

# For any trouble running the script: file Encoding UTF-8 without BOM, only LF (not CRLF) - make the file excecutable 'chmod -x'

debug=0
unitName="MPP5048MGX"
dataFileP1="MPP5048MGX"
dataDir="/ramdisk/"

while : ; do
        # Collect the raw data from inverter.
        # Use double buffering to avoid race conditions.

        # sudo mpp-solar -p /dev/hidraw0 --getstatus - also possible

        # request Device Rating Information 
        # RATED Information not current - apply first, otherwise you will not get actual data
        # `mpp-solar -p /dev/hidraw0 -c QPIRI > ${dataDir}${dataFileP1}.$$`       
        
        #request Device General Status Parameter
        `mpp-solar -p /dev/hidraw0 -c QPIGS >> ${dataDir}${dataFileP1}.$$`      

        # request serial number
        `mpp-solar -p /dev/hidraw0 -c QID >> ${dataDir}${dataFileP1}.$$`        

        # move tmp file to txt file
        `mv ${dataDir}${dataFileP1}.$$ ${dataDir}${dataFileP1}.txt`       

        for mppDev in $dataFileP1
        do
                # Inverter power values
                gridVolts=`cat ${dataDir}${mppDev}.txt | \grep ac_input_voltage | cut -f2 | sed 's/ //g'`
                gridHz=`cat  ${dataDir}${mppDev}.txt | \grep ac_input_frequency | cut -f2 | sed 's/ //g'`  
                acOutVolt=`cat  ${dataDir}${mppDev}.txt | \grep ac_output_voltage | cut -f2 | sed 's/ //g'`  
                acOutHz=`cat  ${dataDir}${mppDev}.txt | \grep ac_output_frequency | cut -f2 | sed 's/ //g'`  

                acWatts=`cat   ${dataDir}${mppDev}.txt | \grep ac_output_active_power | cut -f2 | sed 's/ //g'`
                acLoadPC=`cat  ${dataDir}${mppDev}.txt | \grep ac_output_load   | cut -f2 | sed 's/ //g'`
              
                pvVolts=`cat   ${dataDir}${mppDev}.txt | \grep pv_input_voltage | cut -f2 | sed 's/ //g'`
                pvAmps=`cat    ${dataDir}${mppDev}.txt | \grep pv_input_current_for_battery  | cut -f2 | sed 's/ //g'`
                pvWatts=`cat   ${dataDir}${mppDev}.txt | \grep pv_input_power  | cut -f2 | sed 's/ //g'`
                batVolts=`cat  ${dataDir}${mppDev}.txt | \grep -w battery_voltage | cut -f2 | sed 's/ //g'` #also is_battery_voltage_to_steady_while_charging and battery_voltage_from_scc
                batCap=`cat    ${dataDir}${mppDev}.txt | \grep battery_capacity | cut -f2 | sed 's/ //g'`

                heatSinkTemp=`cat  ${dataDir}${mppDev}.txt | \grep inverter_heat_sink_temperature   | cut -f2 | sed 's/ //g'`

                # We need to calculate this value
                #pvWatts=$(echo "scale=2; $pvVolts*$pvAmps" | bc)

                # Inverter status values (binary)
                #sccOK=`cat         ${dataDir}${mppDev}.txt | \grep is_scc_ok                | cut -f2 | sed 's/ //g'`
                sccCharging=`cat   ${dataDir}${mppDev}.txt | \grep is_scc_charging_on          | cut -f2 | sed 's/ //g'`
                acCharging=`cat    ${dataDir}${mppDev}.txt | \grep is_ac_charging_on           | cut -f2 | sed 's/ //g'`
                # acLost=`cat        ${dataDir}${mppDev}.txt | \grep is_line_lost             | cut -f2 | sed 's/ //g'`
                acLoadOn=`cat      ${dataDir}${mppDev}.txt | \grep is_load_on               | cut -f2 | sed 's/ //g'`
                #batOverV=`cat      ${dataDir}${mppDev}.txt | \grep is_battery_over_voltage  | cut -f2 | sed 's/ //g'`
                #batUnderV=`cat     ${dataDir}${mppDev}.txt | \grep is_battery_under_voltage | cut -f2 | sed 's/ //g'`
                confChange=`cat    ${dataDir}${mppDev}.txt | \grep is_configuration_changed | cut -f2 | sed 's/ //g'`

                # Inverter Status  values (strings)
                serNum=`cat        ${dataDir}${mppDev}.txt | \grep serial_number            | cut -f2 | sed 's/ //g'`
                #workMode=`cat      ${dataDir}${mppDev}.txt | \grep work_mode                | cut -f2 | sed 's/ //g'`
                #srcMode=`cat       ${dataDir}${mppDev}.txt | \grep charger_source_priority  | cut -f2 | sed 's/ //g'`
                #faultCode=`cat     ${dataDir}${mppDev}.txt | \grep fault_code               | cut -f2 | sed 's/ //g'`

                # create the prom file. first value should truncate file. others append!
                printf "$mppDev{mode=\"gridVolts\"} $gridVolts\n" >  ${dataDir}${dataFileP1}.prom.$$ 
                printf "$mppDev{mode=\"batVolts\"}  $batVolts\n"  >> ${dataDir}${dataFileP1}.prom.$$ 
                printf "$mppDev{mode=\"pvVolts\"}   $pvVolts\n"   >> ${dataDir}${dataFileP1}.prom.$$ 
                printf "$mppDev{mode=\"pvAmps\"}    $pvAmps\n"    >> ${dataDir}${dataFileP1}.prom.$$ 
                printf "$mppDev{mode=\"batCap\"}    $batCap\n"    >> ${dataDir}${dataFileP1}.prom.$$ 
                printf "$mppDev{mode=\"pvWatts\"}   $pvWatts\n"   >> ${dataDir}${dataFileP1}.prom.$$ 
                printf "$mppDev{mode=\"acWatts\"}   $acWatts\n"   >> ${dataDir}${dataFileP1}.prom.$$ 
                printf "$mppDev{mode=\"acLoadPC\"}  $acLoadPC\n"  >> ${dataDir}${dataFileP1}.prom.$$
                printf "$mppDev{mode=\"gridHz\"}    $gridHz\n"    >> ${dataDir}${dataFileP1}.prom.$$
                printf "$mppDev{mode=\"acOutVolt\"} $acOutVolt\n" >> ${dataDir}${dataFileP1}.prom.$$
                printf "$mppDev{mode=\"acOutHz\"}    $acOutHz\n"  >> ${dataDir}${dataFileP1}.prom.$$
                printf "$mppDev{mode=\"heatSinkTemp\"}  $heatSinkTemp\n"  >> ${dataDir}${dataFileP1}.prom.$$ 

                #printf "$mppDev{mode=\"sccOK\"} $sccOK\n"             >> ${dataDir}$mppDev.prom.$$ 
                printf "$mppDev{mode=\"sccCharging\"} $sccCharging\n" >> ${dataDir}${dataFileP1}.prom.$$ 
                printf "$mppDev{mode=\"acCharging\"} $acCharging\n"   >> ${dataDir}${dataFileP1}.prom.$$ 
                #printf "$mppDev{mode=\"acLost\"} $acLost\n"           >> ${dataDir}$mppDev.prom.$$ 
                printf "$mppDev{mode=\"acLoadOn\"} $acLoadOn\n"       >> ${dataDir}${dataFileP1}.prom.$$ 
                #printf "$mppDev{mode=\"batOverV\"} $batOverV\n"       >> ${dataDir}$mppDev.prom.$$ 
                #printf "$mppDev{mode=\"batUnderV\"} $batUnderV\n"     >> ${dataDir}$mppDev.prom.$$ 
                printf "$mppDev{mode=\"confChange\"} $confChange\n"   >> ${dataDir}${dataFileP1}.prom.$$ 

                printf "$mppDev{mode=\"serNum\"} $serNum\n"                     >> ${dataDir}${dataFileP1}.prom.$$ 
                #printf "$mppDev{mode=\"workMode\",  myStr=\"$workMode\"}  0\n"  >> ${dataDir}$mppDev.prom.$$ 
                #printf "$mppDev{mode=\"srcMode\",   myStr=\"$srcMode\"}   0\n"  >> ${dataDir}${dataFileP1}.prom.$$ 
                #printf "$mppDev{mode=\"faultCode\", myStr=\"$faultCode\"} 0\n"  >> ${dataDir}$mppDev.prom.$$ 

                if (( $debug )) ; then
                        printf "handled file:${dataDir}$mppDev batVolts:$batVolts pvVolts:$pvVolts batCap:$batCap gridVolts:$gridVolts pvAmps:$pvAmps pvWatts:$pvWatts acWatts:$acWatts acLoadPC:$acLoadPC\n"
                fi
        done

        `mv ${dataDir}${dataFileP1}.prom.$$ ${dataDir}${dataFileP1}.prom`

        sleep 4
done
