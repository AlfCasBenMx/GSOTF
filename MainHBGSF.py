import os, fileinput, sys, shutil, glob, time, datetime, cv2, requests, json, warnings, threading, psutil, math



import StartSettings
import LiPER_NNP
import HandlingEvents as myEvent
import Send_HB as HB



time_LastPlate=time.time()
x_previous, y_previous=0,0

''' SET GLOBAL VARIABLES '''
StartSettings.startVar()
''' END SET GLOBAL VARIABLES '''



try:

    
t1= time.time()
t1log= time.time()
try:
  while True:

    dthb = time.time()-t1   
   
            
    if dthb >=  30.0:            
        t1 =time.time()
        myEvent.logSytem()
        try:
            HB.HBeat()
        except Exception as errorHb:
            myEvent.logException(errorHb)
    time.sleep(3)

except Exception as errorGral:
    #print(errorGral)