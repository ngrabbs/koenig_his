nmcli con delete basenet 
nmcli con add type wifi ifname wlan0 mode ap con-name satnet ssid satnet autoconnect true
#nmcli con modify satnet 802-11-wireless.band bg
#nmcli con modify satnet 802-11-wireless.channel 3
nmcli con modify satnet ipv4.method shared ipv4.address 192.168.4.1/24
#nmcli con modify satnet ipv6.method disabled
nmcli con modify satnet wifi-sec.key-mgmt wpa-psk
nmcli con modify satnet wifi-sec.psk "cubesat1"
nmcli con up satnet

