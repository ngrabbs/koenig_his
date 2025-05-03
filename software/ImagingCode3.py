### AUTOMATIC FILTER SWITCHING FOR DESIGNATED IMAGE BURST QUANTITY

# Camera Libraries
import os
import time
from picamera2 import Picamera2, Preview

# Servo Libraries
from gpiozero import AngularServo
from gpiozero.pins.pigpio import PiGPIOFactory

# Declare Variables, Switch Directory, and Start Smooth Servo Movement
count = 0
os.chdir('/home/cubesat/Desktop/Sample')
os.system("sudo pigpiod")
time.sleep(2)

# Initialize Servo Settings
factory = PiGPIOFactory()
servo = AngularServo(18, min_angle=0, max_angle=180, min_pulse_width=0.0005, max_pulse_width=0.0025, pin_factory=factory)

# Initialize Picam and Picam Settings
picam2 = Picamera2()
picam2.start_preview(Preview.QTGL)

controls = {"ExposureTime": 500, "AnalogueGain": 1.0, "ColourGains": (0.0,0.0), "Saturation": 0.0, "AeEnable": 0}

preview_config = picam2.create_preview_configuration(controls=controls)
capture_config = picam2.create_still_configuration(raw={}, display=None)
picam2.configure(preview_config)

picam2.start()
time.sleep(1)

# Acquire User Input

name = str(input('Name the Image(s):\n'))
pic_num = 1 + int(input('How many pictures?:\n'))
resp = str(input("Press Enter to take a picture:\n"))
picam2.switch_mode(capture_config)

# Image Loop (Option to Run Once or More Than Once)

while resp == '':

	angle = 0

	for i in range(1, 4):
		
		filt = '_760'
		if i == 2:
			filt = '_770'
		if i == 3:
			filt = '_780'
		pic_name = name + filt
		
		print('servo move\n')
		servo.angle = angle
		print('servo stop\n')
		time.sleep(0.5)
		
		for k in range(1,pic_num):
			print(f'pic {k}\n')
			picam2.capture_file(pic_name + f"_{k + count}.jpg")
			
		angle = angle + 45
		
	servo.angle = 0
	resp = input('Press Enter to Run Again, or n to End:\n')
	count = count + pic_num - 1

# Close Picamera and End Background Process (Return Servo to Original Position)

picam2.stop()
servo.angle = 0
time.sleep(1)
os.system("sudo killall pigpiod")

