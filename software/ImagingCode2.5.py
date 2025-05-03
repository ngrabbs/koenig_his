### MANUAL FILTER SWITCHING FOR DESIGNATED IMAGE BURST QUANTITY

import os
import time
from picamera2 import Picamera2, Preview

## INITIALIZING VARIOUS SETTINGS
# Declare Variables
count = 0
tally = 0
resp2 = ''
os.chdir('/home/cubesat/Desktop/030125')

# Initialize Picam and Picam Settings
picam2 = Picamera2()
picam2.start_preview(Preview.QTGL)

controls = {"ExposureTime": 1000, "AnalogueGain": 1.0, "ColourGains": (0.0,0.0), "Saturation": 0.0, "AeEnable": 0}

preview_config = picam2.create_preview_configuration(controls=controls)
capture_config = picam2.create_still_configuration(raw={}, display=None)
picam2.configure(preview_config)

picam2.start()

## IMAGING PROCESS
# Acquire User Input

pic_num = 1 + int(input('How many pictures?:\n'))
resp = str(input("Press Enter to take a picture(s):\n"))
picam2.switch_mode(capture_config)

# Image Loop (Option to Run Once or More Than Once)
while resp2 == '':
	
	if resp == 'n':
		break
	
	while resp == '':

		for i in range(1, pic_num):
			picam2.capture_file(f"INITIAL_IMAGE{i + count}.jpg")

		resp = input('Press Enter to Run Again, or n to End:\n')
		count = count + pic_num - 1

	# Name Picture Set (Only if Pictures Were Taken)

	if count != 0:
		if tally == 0:
			name = str(input('Name the Image(s):\n'))
		tally += 1
		filt = '_' + str(input('What filter was used?:\n'))
		for j in range(1, count + 1):
			os.renames(f'INITIAL_IMAGE{j}.jpg', name + filt + f'_{j}.jpg')

	count = 0
	resp2 = str(input('SWITCH FILTERS, then press Enter to take picture(s)\nOR\nPress n to end testing\n'))
	if resp2 == '':
		resp = ''

# Close Picamera

picam2.stop()
