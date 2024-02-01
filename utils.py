import os
from dotenv import load_dotenv
import base64

import numpy as np
import io
class EnvVariables:
    def __init__(self, prod = True) -> None:
            load_dotenv()
            if prod:
                self.host = os.environ.get('HOST')
                self.database = os.environ.get('DATABASE')
                self.user = os.environ.get('DBUSER')
                self.password = os.environ.get('PASSWORD')
                self.secret = os.environ.get('SECRET')
                self.datapath = os.environ.get('DATAPATH')
                
            else:
                self.host = os.environ.get('HOST_TEST')
                self.database = os.environ.get('DATABASE_TEST')
                self.user = os.environ.get('DBUSER_TEST')
                self.password = os.environ.get('PASSWORD_TEST')
                self.secret = os.environ.get('SECRET')
                self.datapath= os.environ.get('DATAPATH_TEST')
                

def extract_metadata(cont):
    st_time = ''
    acq_time = ''
    find = '"Start time"'
    index = cont.find(find)
    enterscount = 0
    val =''
    for i in range(index,index+100):

        if enterscount ==2:
            if cont[i] =='\n':
                break
            val+=cont[i]

        if cont[i] =='\n':
            enterscount+=1
    st_time = val

    find = '"Acq time"'
    index = cont.find(find)
    enterscount = 0
    val = ''
    for i in range(index, index + 100):
        if enterscount == 2:
            if cont[i] == '\n':
                break
            val += cont[i]

        if cont[i] == '\n':
            enterscount += 1
    acq_time = val
    _st_time =''
    for c in st_time:
        if c in [' ','.']:
            break
        else:
            _st_time +=c
    st_time = int(_st_time)

    _aqc_time = ''
    for c in acq_time:
        if c in [' ', '.']:
            break
        else:
            _aqc_time += c
    acq_time = int(_aqc_time)
    return st_time,acq_time


def get_metadata(file):
    with open(file,'r') as f:
        cont = f.read()
        st_time,acq_time = extract_metadata(cont)
        return st_time,acq_time

def get_metadata_from_fileStorage(file):
    cont = file.read().decode('utf-8')
    st_time,acq_time = extract_metadata(cont)
    return st_time,acq_time

def get_metadata_from_zipFile(file):
    cont = file.decode('utf-8')
    st_time,acq_time = extract_metadata(cont)
    return st_time,acq_time

def save_image(name,image, data_path):
    if not os.path.exists(data_path):
        err = f'Error: folder {data_path} does not exist'
        print(err)
        return err
    arr = np.loadtxt(io.BytesIO(image))
    np.save(f'{data_path}/{name}.npy', arr)
    return 'Saved succesfully'

