sudo journalctl -u NetworkManager.service | grep 'DHCPOFFER' | awk '{ print $7}' | sort | uniq
