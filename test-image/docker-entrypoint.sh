#!/bin/bash

set -x

echo "command: \"$@\""


check_file() {
	file_to_check="/opt/f"
	interval=5  # Time interval in seconds

	while true; do
		if [ -f "$file_to_check" ]; then
			echo "File exists. Exiting..."
			exit 0
		fi
		sleep "$interval"
	done
}


#sleep 10
#sh -c "$@"
#sleep infinity # <---




check_file



#exec $@ # <---

#while [ ! -f "/ok" ]; do
#	sleep 1
#done

#sleep infinity


