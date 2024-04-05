#!/usr/bin/env python3
# Note:  I need to run this from the main SDR-TRX directory or it doesn't work.
# Figure this out.

import socket
import time
import lib.WSJTXClass as WSJTXClass
import serial
import yaml
import struct
import datetime
import os

#Import weakmon to use encoders
import sys
import os


# sys.path.append(os.path.expandvars('$WEAKMON'))
# print(os.path.expandvars('$WEAKMON'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
#sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))

print(sys.path)
from ft8 import FT8Send
from ft4 import FT4Send

#Read configuration file
configs_file = open('transceiver_config.yml', 'r')
configs = yaml.load(configs_file, Loader=yaml.BaseLoader)

#Serial port for arduino
serial_port = configs['serial_port']
baudrate    = configs['baudrate']
try:
    puerto = serial.Serial(serial_port, baudrate, timeout=0.5)
except serial.serialutil.SerialException:
    print("\nCould not connect to serial port: " + serial_port + "\n")
    exit(1)

#Global variables
callsign = configs['callsign']
grid = configs['grid']
current_msg = ''
rx_callsign = ''
mode = 'FT8'
tx_freq = 1200

#Connection for WSJT-X
UDP_IP = "127.0.0.1"
UDP_PORT = 2237
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind((UDP_IP, UDP_PORT))

#FT8 encoder
ft8_encoder = FT8Send()
ft4_encoder = FT4Send()

def encode_ft8(msg):
    try:
        a77 = ft8_encoder.pack(msg, 1)
        # print(a77)
        # print("Type (a77): ", type(a77))
    except Exception as e:
        print("FT8 encoder error, check message 1!")
        print(f"Exception type: {type(e).__name__}")
        print(f"Exception message: {str(e)}")
    try:
        symbols = ft8_encoder.make_symbols(a77)
    except Exception as e:
        print("FT8 encoder error, check message 2!")
        print(f"Exception type: {type(e).__name__}")
        print(f"Exception message: {str(e)}")
        symbols = None
        time.sleep(3)
    return symbols

def encode_ft4(msg):
    try:
        a77 = ft4_encoder.pack(msg, 1)
    except Exception as e:
        print("FT4 encoder error, check message 1!")
        print(f"Exception type: {type(e).__name__}")
        print(f"Exception message: {str(e)}")
        symbols = None
        time.sleep(3)
    try:
        symbols = ft4_encoder.make_symbols(a77)
        print("Symbols: ", symbols)
        print('len(symbols)', len(symbols))
    except Exception as e:
        print("FT4 encoder error, check message!")
        print(f"Exception type: {type(e).__name__}")
        print(f"Exception message: {str(e)}")
        symbols = None
        time.sleep(3)
    return symbols

def load_symbols(symbols):
    print("Load symbols into transmitter..")
    puerto.write(b'm')
    count = 0
    for symbol in symbols:
        puerto.write(struct.pack('>B', symbol))
        count += 1
        #Wait to avoid Arduino serial buffer overflow
        if count % 50 == 0:
            time.sleep(0.05)
    puerto.write(b'\0')
    time.sleep(0.05)
    resp = puerto.read(1)
    if resp == b'm':
        print("Load OK")
    else:
        print(resp)
       

def change_freq(new_freq):
    global tx_freq
    print ("Change TX frequency to:", new_freq)
    puerto.write(b'o')
    for kk in range(2):
        puerto.write(struct.pack('>B', (new_freq >> 8*kk) & 0xFF))
    time.sleep(0.05)
    resp = puerto.read(1)        
    if resp == b'o':
        print("New freq set to: {0}".format(new_freq))
        tx_freq = new_freq
        

# def set_mode(new_mode):
#     global mode
#     if mode != new_mode:
#         puerto.write(b's')
#         time.sleep(3)
#         resp = puerto.read(512) 
#         print("resp = ", resp)       
#         if resp == b's':
#             mode = new_mode
#             print("Switched to: {0}".format(new_mode))

def set_mode(new_mode):
    global mode
    if new_mode == 'FT8':
        puerto.write(b'e')
        time.sleep(.05)
        resp = puerto.read(1) 
        print("resp = ", resp)       
        if resp == b'e':
            mode = new_mode
            print("Switched to: {0}".format(new_mode))  
            return True
    elif new_mode == 'FT4':
        puerto.write(b'f')
        time.sleep(0.05)
        resp = puerto.read(1) 
        print("resp = ", resp)       
        if resp == b'f':
            mode = new_mode
            print("Switched to: {0}".format(new_mode))
            return True
    else:
        return False

def new_msg(msg):
    global current_msg
    global mode
    if msg != current_msg:
        print("Message: {0}".format(msg))
        print(msg)
        print('len(msg)',len(msg))
        if 'FT8' in mode:
            symbols = encode_ft8(msg)
        else:
            print('Encoding FT4')
            symbols = encode_ft4(msg)            
        if symbols.any():
            #symbols = [kk for kk in range(79)]
            load_symbols(symbols)
            current_msg = msg
        else:
            return
    else:
        time.sleep(0.005)

def transmit():
    if False:#not current_msg:
        print("No previous message!")
        time.sleep(1)
    else:
        print("TX!")
        puerto.write(b't')                

def check_time_window(utc_time):
    time_window = 15 if 'FT8' in mode else 7
    print("Time window: ", time_window )
    rm = utc_time.second % time_window
    if rm > 1 and rm < time_window-1:
        return False
    else:
        return True

#Check transmitter is initialized
print("\n\nWait for transmitter ready...")
while True:
    time.sleep(1)    
    puerto.write(b'r')
    time.sleep(0.05)
    x = puerto.read()
    if x == b'r':
        print("Transmitter ready!")
        break

        
try:
    while True:

        fileContent, addr = sock.recvfrom(1024)
        NewPacket = WSJTXClass.WSJTX_Packet(fileContent, 0)
        NewPacket.Decode()

        if NewPacket.PacketType == 1:
            StatusPacket = WSJTXClass.WSJTX_Status(fileContent, NewPacket.index)
            StatusPacket.Decode()

            #Check TX frequency and update transceiver
            new_freq = StatusPacket.TxDF
            new_mode = StatusPacket.TxMode.strip()
            print('new_mode', new_mode)
            
            if new_freq != tx_freq:
                change_freq(new_freq)

            if new_mode != mode:
                print("Mode before: {0}".format(mode))
                if not set_mode(new_mode):
                    print("Invalid mode: {0}".format(new_mode))
                print("New mode after: {0}".format(mode))

            #Check if TX is enabled
            if StatusPacket.Transmitting == 1:
                #Check time, avoid transmitting out of the time slot
                utc_time = datetime.datetime.utcnow()
                tx_now = check_time_window(utc_time)                
                if tx_now:
                    puerto.write(b'p')
                message = StatusPacket.TxMessage
                message = message.replace('<', '')
                message = message.replace('>', '')                
                new_msg(message.strip())
                
                if tx_now:
                    transmit()
                print( "Time: {0}:{1}:{2}".format(utc_time.hour, utc_time.minute, utc_time.second))


finally:
    sock.close()
