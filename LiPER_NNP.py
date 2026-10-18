# LiPER_NNP

# Designed by: Guillermo Campos and Rodrigo Vallejo
# On Behalf of: ARIA Business Bots and Ernst & Young

# Import libraries
# import matplotlib.pyplot as plt
import warnings
import io
import ocr_evidence
import SendNotifications as SendEmail





import StartSettings


import sys





import os
import shutil
import http.client
import urllib.parse
import time

import HandlingEvents as myEvent
import json
from datetime import datetime


def handle_http_error(status_code, reason, context=""):
    """Maneja errores HTTP comunes y proporciona mensajes descriptivos"""
    error_messages = {
        400: "Solicitud incorrecta - datos invÃ¡lidos",
        401: "No autorizado - credenciales invÃ¡lidas",
        403: "Acceso prohibido - permisos insuficientes o token expirado",
        404: "Recurso no encontrado",
        429: "Demasiadas solicitudes - lÃ­mite de rate alcanzado",
        500: "Error interno del servidor",
        502: "Bad Gateway - problema con el servidor proxy",
        503: "Servicio no disponible - servidor temporalmente inaccesible"
    }

    message = error_messages.get(status_code, f"Error HTTP {status_code}: {reason}")
    full_message = f"{context} - {message}" if context else message

    print(full_message)
    myEvent.logEvent(full_message)
    return full_message


def make_api_request(url, headers, data=None, max_retries=2):
    """Retry only explicit 429 rejections, never ambiguous POST failures."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != 'https' or not parsed.netloc:
        raise ValueError('API URL must use HTTPS')
    path = parsed.path or '/'
    if parsed.query:
        path += '?' + parsed.query
    for attempt in range(max_retries + 1):
        conn = http.client.HTTPSConnection(parsed.netloc, timeout=10)
        try:
            conn.request('POST', path, body=json.dumps(data if data is not None else {}), headers=headers)
            response = conn.getresponse()
            body = response.read().decode('utf-8')
            if 200 <= response.status < 300:
                return True, json.loads(body) if body else {}, response.status
            if response.status == 429 and attempt < max_retries:
                try:
                    delay = min(30, max(1, int(response.getheader('Retry-After') or (attempt + 1) * 2)))
                except ValueError:
                    delay = (attempt + 1) * 2
                time.sleep(delay)
                continue
            handle_http_error(response.status, response.reason)
            return False, None, response.status
        except (OSError, ValueError, http.client.HTTPException):
            # A POST may already have reached the server; retrying could duplicate it.
            myEvent.setup_logging().exception('API request failed; not repeating ambiguous POST')
            return False, None, 0
        finally:
            conn.close()
    return False, None, 0


def get_token():
    """Obtiene token de autenticaciÃ³n con manejo robusto de errores"""
    apikey = StartSettings.genyusKey
    headers = {
        'apikey': apikey,
        'Content-Type': 'application/json'
    }

    url = 'https://uat-genyus.ey.com/appSecServ/tokenAuthConnect'

    success, response_data, status_code = make_api_request(url, headers)

    if success and response_data:
        token = response_data.get('data')
        if token:
            print("Token obtenido exitosamente")
            return token
        else:
            print("Respuesta exitosa pero sin token en los datos")
            myEvent.logEvent("Token no encontrado en respuesta de API")
            return None
    else:
        print(f"Error al obtener token. CÃ³digo de estado: {status_code}")
        return None



def validate_credentials():
    """Valida que las credenciales necesarias estÃ©n configuradas"""
    errors = []

    if not hasattr(StartSettings, 'genyusKey') or not StartSettings.genyusKey:
        errors.append("genyusKey no configurada en StartSettings")

    if not hasattr(StartSettings, 'ocrKey') or not StartSettings.ocrKey:
        errors.append("ocrKey no configurada en StartSettings")

    if not hasattr(StartSettings, 'myOCREndpoint') or not StartSettings.myOCREndpoint:
        errors.append("myOCREndpoint no configurado en StartSettings")

    if not hasattr(StartSettings, 'serialLiper') or not StartSettings.serialLiper:
        errors.append("serialLiper no configurado en StartSettings")

    if errors:
        error_msg = "Credenciales no configuradas: " + ", ".join(errors)
        print(error_msg)
        myEvent.logEvent(error_msg)
        return False

    return True


def containsNumber(s):
    contains_digit = False
    for character in s:
        if character.isdigit():
            contains_digit = True
    return contains_digit

def copyPlateImage(image, pic_folder):
    if not os.path.exists(pic_folder):
        os.makedirs(pic_folder)
    try:
        shutil.copy(image, pic_folder)
    except OSError:
        myEvent.setup_logging().exception('Could not preserve OCR image')



# Start of the photo slection module
def Predicciones_BN(plateFile,fullImage, folderpath, ocrPath):

    plates=[]
    evidence = None
    raw_lines = []
    ocr_status = "not_submitted"
    imageIsOpen = False
    computervision_client = None
    substep = 'Initialization'

    myEvent.logEvent('Inicio de reconocimiento de placa')

    # Validar credenciales antes de proceder
    if not validate_credentials():
        myEvent.logEvent('Error: Credenciales no vÃ¡lidas, abortando procesamiento')
        return

    try:

        substep=' Autenticacion OCR '+ time.strftime("%H%M%S")
        # Transform the image to text using OCR
        '''
        Authenticate your credentials and creates a client.
        '''
        from azure.cognitiveservices.vision.computervision import ComputerVisionClient
        from azure.cognitiveservices.vision.computervision.models import OperationStatusCodes
        from msrest.authentication import CognitiveServicesCredentials
        subscription_key = StartSettings.ocrKey
        endpoint = StartSettings.myOCREndpoint

        if not subscription_key or not endpoint:
            raise Exception("Credenciales OCR no configuradas correctamente")

        computervision_client = ComputerVisionClient(endpoint, CognitiveServicesCredentials(subscription_key))
        computervision_client.config.connection.timeout = 15
        from urllib3.util.retry import Retry
        computervision_client.config.retry_policy.policy = Retry(total=0, connect=0, read=0, status=0)
        '''
        END - Authenticate
        '''
        '''
        Streaming local image to OCR
        '''
        if not os.path.exists(plateFile):
            raise Exception(f"Archivo de imagen no encontrado: {plateFile}")

        with open(plateFile, 'rb') as crop_stream:
            crop_bytes = crop_stream.read()
        # One byte sequence is both preserved and submitted, without re-encoding.
        try:
            evidence = ocr_evidence.preserve(crop_bytes, fullImage, folderpath)
            ocr_evidence.finish(*evidence, "pending", [], [])
        except Exception:
            myEvent.setup_logging().exception('Could not save OCR evidence; continuing OCR')
        image_data = io.BytesIO(crop_bytes)
        imageIsOpen = True
        substep=' Envio de imagen a OCR '

        try:
            read_response = computervision_client.read_in_stream(image_data,  raw=True)
        except Exception as ocr_error:
            if "403" in str(ocr_error):
                raise Exception(f"Error 403 en OCR: Acceso prohibido. Verificar subscription key y endpoint. Error: {str(ocr_error)}")
            elif "401" in str(ocr_error):
                raise Exception(f"Error 401 en OCR: Credenciales invÃ¡lidas. Error: {str(ocr_error)}")
            else:
                raise Exception(f"Error en OCR: {str(ocr_error)}")

        # Get the operation location (URL with an ID at the end) from the response
        read_operation_location = read_response.headers['Operation-Location']
        # Grab the ID from the URL
        operation_id = read_operation_location.split('/')[-1]

        # Call the 'GET' API and wait for it to retrieve the results
        max_wait_time = 30  # mÃ¡ximo 30 segundos de espera
        deadline = time.monotonic() + max_wait_time
        while True:
            try:
                read_result = computervision_client.get_read_result(operation_id)
                if read_result.status not in ['notStarted', 'running']:
                    break
                time.sleep(1)
                if time.monotonic() > deadline:
                    raise Exception("Timeout esperando resultado de OCR")
            except Exception as ocr_error:
                if "403" in str(ocr_error):
                    raise Exception(f"Error 403 obteniendo resultado OCR: {str(ocr_error)}")
                else:
                    raise Exception(f"Error obteniendo resultado OCR: {str(ocr_error)}")

        # #print the detected text, line by line
        ocr_status = str(read_result.status)
        substep=' Procesando repuesta OCR '
        if read_result.status == OperationStatusCodes.succeeded:
            for text_result in read_result.analyze_result.read_results:
                for line in text_result.lines:

                    clearPlate=''
                    tempPlate= line.text
                    raw_lines.append(tempPlate)
                    if containsNumber(tempPlate)==False:
                        continue

                    tempPlate = tempPlate.replace('=', '-')
                    tempPlate = tempPlate.replace('&', '')
                    tempPlate = tempPlate.replace(' -', '-')
                    tempPlate = tempPlate.replace('- ', '-')
                    tempPlate = tempPlate.strip()
                    tempPlate = tempPlate.replace(' ', '')

                    if tempPlate.endswith('-'):
                        tempPlate=tempPlate+'A'
                    if '-'in tempPlate:
                        tempPlate = tempPlate.replace(' ', '')


                    if (tempPlate==tempPlate.upper() and not tempPlate.replace('-', '').isnumeric() and tempPlate.replace('-', '').isalnum() and tempPlate.islower()==False and  len(tempPlate)>=5 and tempPlate!='PETRO' and tempPlate!='SEVEN' ):

                        clearPlate=tempPlate
                        clearPlate = clearPlate.replace(' ', '')
                        clearPlate = clearPlate.replace('-', '')
                        plates.append(clearPlate)
    except Exception as error:
        ocr_status = 'error'
        myEvent.setup_logging().exception('OCR processing failed')
        myEvent.logEvent(f'Error en procesamiento OCR {substep}: {str(error)}')
        SendEmail.sendErrorAlert('Procesamiento de imagenes OCR' + substep, str(error))
        clearPlate=' '
    finally:
        try:
            myplates = list(dict.fromkeys(plates))
            if evidence is not None:
                try:
                    ocr_evidence.finish(*evidence, ocr_status, raw_lines, myplates)
                except Exception:
                    myEvent.setup_logging().exception('Could not finish OCR evidence')
            sendPlate(myplates, fullImage)
            # Keep the original full capture in SavedPlates AND, on failure, ErrorOCR.
            copyPlateImage(fullImage, folderpath if myplates else ocrPath)
        finally:
            if imageIsOpen:
                image_data.close()
            if computervision_client is not None:
                try:
                    computervision_client.close()
                except Exception:
                    myEvent.setup_logging().exception('OCR client cleanup failed')



def sendPlate(myPlates, imageName):
    """EnvÃ­a placas detectadas a la base de datos con manejo robusto de errores"""
    if len(myPlates) >= 1:
        for clearPlate in myPlates:
            try:
                if len(clearPlate) > 4 and len(clearPlate) < 8:
                    # Obtener token de autenticaciÃ³n
                    token = get_token()
                    if not token:
                        print(f"No se pudo obtener token para enviar placa {clearPlate}")
                        continue

                    # Preparar datos para envÃ­o
                    apikey = StartSettings.genyusKey
                    myserial = StartSettings.serialLiper

                    print(f'Enviando placa: {clearPlate}')

                    # Preparar headers y datos
                    headers = {
                        'apikey': apikey,
                        'Authorization': f'Bearer {token}',
                        'Content-Type': 'application/json'
                    }

                    data = {
                        'metadata': {'url': '/MexGasStation', 'service': '/postPlateDetected'},
                        'payload': {'plate': clearPlate, 'serie': myserial, 'side': '1'}
                    }

                    url = 'https://uat-genyus.ey.com/appSecServ/receiveConnect'

                    # Realizar solicitud
                    success, response_data, status_code = make_api_request(url, headers, data)

                    if success:
                        print(f'Respuesta de la base de datos: {response_data}')
                        print('Placa enviada a base de datos exitosamente')
                        myEvent.logPlates(clearPlate, imageName)
                    elif status_code in (401, 403):
                        # Intentar con nuevo token
                        print('Token expirado, obteniendo nuevo token...')
                        new_token = get_token()
                        if new_token:
                            headers['Authorization'] = f'Bearer {new_token}'
                            retry_success, retry_data, retry_status = make_api_request(url, headers, data, max_retries=1)
                            if retry_success:
                                print('Placa enviada exitosamente con nuevo token')
                                myEvent.logPlates(clearPlate, imageName)
                            else:
                                print(f'Error {retry_status} enviando placa en segundo intento')
                        else:
                            print('No se pudo obtener nuevo token')
                    else:
                        print(f'Error {status_code} enviando placa {clearPlate}')

            except Exception as error:
                print(f'Error procesando placa {clearPlate}: {str(error)}')
                myEvent.logEvent(f'Error procesando placa {clearPlate}: {str(error)}')



if __name__ == '__main__':
    raise SystemExit('Run MainPlateGSF.py; no test plates are sent automatically.')
