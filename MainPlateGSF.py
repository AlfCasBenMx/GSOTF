import os, fileinput, sys, shutil, glob, time, datetime
import cv2, requests, json, warnings, threading, psutil, math

# from matplotlib import image
import numpy as np
from datetime import datetime
from datetime import date
from azure.cognitiveservices.vision.computervision import ComputerVisionClient
from azure.cognitiveservices.vision.computervision.models import OperationStatusCodes
from msrest.authentication import CognitiveServicesCredentials
from PIL import Image 
from object_detection.utils import label_map_util
from object_detection.utils import visualization_utils as viz_utils
import tensorflow as tf
# import matplotlib.pyplot as plt
from picamera2 import Picamera2, Preview
from libcamera import controls

import StartSettings
import LiPER_NNP
import HandlingEvents as myEvent
import Send_HB as HB
import ResetControl
import SendNotifications
import ResetControl 

## Revisar que la ruta sea la misma de la carpeta.
def constrainPoint(num, minimum=1, maximum=255):
  """Limits input 'num' between minimum and maximum values.
  Default minimum value is 1 and maximum value is 255."""
  return max(min(num, maximum), minimum)
import shutil

def copy_files_with_space_check(source, destination):
    try:
        shutil.copy(source, destination)
        return True
    except Exception as e:
        #print(f"Error al copiar el archivo {source}: {e}")
        return False






offset=5
scoreTresh=45
clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))

os.chdir(r'/home/pi/Desktop/GDF')
FolderWithPlate='SavedPlates/'
FolderTemp='TempImages/'
FolderSavedTemp='TempSavedImages/'
FolderRegionPlate='PlateRegionImage/'
FolderOCRError='ErrorOCR/'
if not os.path.exists(FolderWithPlate):
        os.makedirs(FolderWithPlate)
if not os.path.exists(FolderTemp):
        os.makedirs(FolderTemp)        
if not os.path.exists(FolderSavedTemp):
        os.makedirs(FolderSavedTemp)   
if not os.path.exists(FolderRegionPlate):
        os.makedirs(FolderRegionPlate) 
if not os.path.exists(FolderOCRError):
        os.makedirs(FolderOCRError) 

time_LastPlate=time.time()
x_previous, y_previous=0,0

''' SET GLOBAL VARIABLES '''
StartSettings.startVar()
''' END SET GLOBAL VARIABLES '''

Counter_StaticPlate=0
x_current = 0
y_current = 0
'''
START AND SETING CANERA
'''
try:
  #print('Iniciando camara')
  widthcamera, heightcamera = 3200, 2592
  picam2 = Picamera2()
  preview_config = picam2.create_preview_configuration(main={"size": (widthcamera, heightcamera)})
  picam2.configure(preview_config)
  picam2.start()
  picam2.set_controls({"AfMode": controls.AfModeEnum.Continuous})
  time.sleep(2)
  print('Camara iniciada')
except Exception as ErrorCamera:

  SendNotifications.sendErrorAlert('Error al iniciar camara', 'Validar que el modulo de camara este conectado correctamente. Revise los parametros de resolución y configuración de manejo de camaras')
  ResetControl.ValidateReset(4, 'No se logro iniciar la camara correctamente') 

'''
END - START AND SETING CANERA
'''

'''
LOAD MODEL
'''
PATH_TO_SAVE_MODEL = r'saved_model'
label_map_pbtxt_fname = r'label_map.pbtxt'
category_index = label_map_util.create_category_index_from_labelmap(label_map_pbtxt_fname)
print('Iniciando modelo')
detect_fn = tf.saved_model.load(PATH_TO_SAVE_MODEL)
'''
END - LOAD MODEL
'''




# HB.HBeat()
myEvent.logSytem()
    
t1= time.time()
t1log= time.time()
myFlag = True
try:
  while myFlag:

    dt = time.time()-t1
    tminutes = int(dt / 60)
    
    dtlog=time.time()-t1log
    tminuteslog = int(dtlog / 60)
    myseconds= dt%30
#     if tminuteslog >=  5.0:
#         myEvent.logSytem()
#         if(myEvent.flagi ):
#             t1log= time.time()
            
    if tminutes >=  2.0:            
        t1 =time.time()
        myEvent.logSytem()
        # try:
        #     HB.HBeat()
        # except Exception as errorHb:
        #     pass
#             myEvent.logException(errorHb)
        try:          
            for entry in os.scandir(FolderTemp):
                if entry.path.endswith('.jpg'):
                    os.remove(entry)
                    
            time.sleep(0.5)
            for entry in os.scandir(FolderRegionPlate):
                if entry.path.endswith('.jpg'):
                    os.remove(entry)
        except:
            myEvent.logException('Eliminacion imagenes previas')


    '''
    TAKE  AND SAVE PHOTO
    '''
   
    myTimeStamp= date.today().strftime("%y%m%d")+time.strftime("%H%M%S")
    mycurrentTIme= time.time()
    my_FullImage = FolderTemp+myTimeStamp+'.jpg'  
    picam2.capture_file(my_FullImage)

    '''
    Copy temp image for  timeline
    '''
    # La convertimos a array
        
    image_np = cv2.imread(my_FullImage)
    W=np.shape(image_np)[1]
    H=np.shape(image_np)[0]
    '''
    END - TAKE AND SAVE PHOTO
    '''

    '''
    FIND PLATES IN IMAGE
    '''
    # La convertimos a tensor y la agregamos una dimensión para que pueda leerla nuestro modelo
    input_tensor = tf.convert_to_tensor(image_np)
    input_tensor = input_tensor[tf.newaxis, ...]
    # Realizamos la detección del objeto
    detections = detect_fn(input_tensor)    
    # Analizamos cuántas detecciones se obtuvieron
    num_detections = int(detections.pop('num_detections'))    
    detections = {key: value[0, :num_detections].numpy() for key, value in detections.items()}
    detections['num_detections'] = num_detections
    detections['detection_classes'] = detections['detection_classes'].astype(np.int64)
    '''
    END - FIND PLATES IN IMAGE
    '''

    '''
    OBTAINING REGIONS WITH PLATES
    '''
    image_np_with_detections = image_np.copy() 
        # Utilizamos la libreria de obejct detection para visualizar le bounding box y la clasificación
    viz_utils.visualize_boxes_and_labels_on_image_array(
      image_np_with_detections,
      detections['detection_boxes'],
      detections['detection_classes'],
      detections['detection_scores'],
      category_index,
      max_boxes_to_draw=200, 
      min_score_thresh=scoreTresh/100, 
      use_normalized_coordinates = True
    )
    cv2.imshow('frame', cv2.resize(image_np_with_detections, (1200, 800), interpolation= cv2.INTER_LINEAR)) 
    val=np.where(detections['detection_scores']>=(scoreTresh/100))    
    if len(val[0])>=1:
        
        
        for i in val[0]:
      
            regionPlate = FolderRegionPlate + str(i) + myTimeStamp + '.jpg'
            myBox=detections['detection_boxes'][i]
            x_current = int(0.5*W*(myBox[3]+myBox[1]))
            y_current = int(H*0.5*(myBox[2]+myBox[0]))
            x = int(constrainPoint(myBox[1]*W-offset, 0, W))
            X = int(constrainPoint(myBox[3]*W+offset, 0, W))
            y = int(constrainPoint(myBox[0]*H-offset, 0, H))
            Y = int(constrainPoint(myBox[2]*H+offset, 0, H))
            region1 = image_np[y:Y,x:X]
            canal_b, canal_g, canal_r = cv2.split(region1)
            # Aplicar CLAHE a cada canal
            
            clahe_b = clahe.apply(canal_b)
            clahe_g = clahe.apply(canal_g)
            clahe_r = clahe.apply(canal_r)
        
            # Unir los canales CLAHE procesados
            region = cv2.merge([clahe_b, clahe_g, clahe_r])
            
            cv2.imwrite(regionPlate, region, [cv2.IMWRITE_JPEG_QUALITY, 100])
        
        time_LastPlate=mycurrentTIme
        Distance= int(math.sqrt((x_previous-x_current)*(x_previous-x_current)+(y_previous-y_current)*(y_previous-y_current)))
  # #     #print('La placa se movio:', Distance)
        x_previous,y_previous= x_current, y_current
        if Distance>=60:
            myFlag = copy_files_with_space_check(my_FullImage, FolderWithPlate)
            threading_OCRProcessing = threading.Thread(target=LiPER_NNP.Predicciones_BN, args=(regionPlate, my_FullImage, FolderWithPlate, FolderOCRError))
            threading_OCRProcessing.start()
#          time.sleep(0.5)
        else:
            Counter_StaticPlate+=1
            if Counter_StaticPlate<3:
              #print('Envio reiterado:', Counter_StaticPlate)
              myFlag = copy_files_with_space_check(my_FullImage, FolderWithPlate)
              
              threading_OCRProcessing = threading.Thread(target=LiPER_NNP.Predicciones_BN, args=(regionPlate, my_FullImage, FolderWithPlate, FolderOCRError))
              
              threading_OCRProcessing.start()
#               time.sleep(0.5)
  # #       else:
  # #           #print('Se omite por posible placa inmovil reiterada:',Counter_StaticPlate)
    else:
           tiemposinplaca=mycurrentTIme-time_LastPlate
           if tiemposinplaca>=5:
               contador_placainmovil=0
  # #     else:
  # #       #print(tiemposinplaca, '[s] sin placa -> Posible obstruccion')
      
    if cv2.waitKey(1) & 0xFF==ord('q'):
      break


except Exception as errorGral:
    pass
finally:
    picam2.close()
    cv2.destroyAllWindows()

