from flask_restful import Resource
from flask import request,jsonify, send_file
from config import conn,app,data_path
from frontend.AuthManager import require_auth
import uuid
import csv
from io import StringIO, BytesIO
import numpy as np
from joblib import load
from sklearn.metrics import accuracy_score, recall_score, precision_score
import pandas as pd
from datetime import datetime, timedelta
from utils import get_metadata_from_zipFile, save_image
import jwt
from werkzeug.security import generate_password_hash,check_password_hash
from zipfile import ZipFile
import re
import collections
import requests
import time
from config import socketio 
import matplotlib.pyplot as plt
from PIL import Image
import io
import base64
import json
import hashlib

import os
CRED = '\033[91m'
CEND = '\033[0m'

class Demo(Resource):
    @require_auth
    def post(self,uid):
        image = request.files.get('image')
        image = np.loadtxt(image)
        clf = load('./Horizon_Model_Cu_12mm_norm_l2_std_pca_3_svc_rbf_q_10.0_23.0_per_nm_20231211T195322.280704_model.joblib')
        df = pd.DataFrame()
        # {'calculated_distance':0.012,'measurement_data':arr}
        df['calculated_distance'] = np.nan
        df['measurement_data'] = np.nan
        df['measurement_data'] = df['measurement_data'].astype(object)
        df.at[0,'calculated_distance'] = 0.012
        df.at[0,'measurement_data'] = image
        
        # print(df)
        res = clf.predict_proba(df)
        print(res)
        res = np.round(res[0][0]*100,2)
        # res = int(res[0])*100
        q = np.quantile(image,0.991)
        image[image>q] = q
        buffer = BytesIO()
        plt.imsave(buffer,image,format='png',cmap='hot',dpi=300)
        # img = Image.open(image)
        # img.save(buffer,format='png')
        # buffer.getvalue()
        img = base64.b64encode(buffer.getvalue()).decode()
        
        

        return {'prediction':res, 'image':img}

class UploadModel(Resource):
    @require_auth
    def post(self,uid):
        timer = time.time()
        model = request.files.get('Model') # acquire model file
        form = request.form

        # gather filters
        study = form.getlist('study') 
        machine = form.getlist('machine')
        distance = form.getlist('distance')
        client = form.get('sid')
        app.logger.info(study)
        app.logger.info(machine)
        app.logger.info(distance)

        app.logger.info(model)
        socketio.emit('modelupdate',{'msg':'Querying the database'},room=client)
        cur= conn.cursor()

        # building sql query to retrieve measurements that are:
        # - only blind 
        # - calculated_distance not NULL
        sql = 'select measurement_id , calculated_distance, cancer_tissue from measurement m join patient p on p.patient_id = m.patient_id  JOIN calibration_measurement on m.calibration_measurement_id  = calibration_measurement.calibration_measurement_id WHERE calculated_distance is not null and blind is true and cancer_tissue is not null '
        
        # applying filters
        tup = []
        if len(study) != 0:
            sql+='and study_id in %s'
            tup.append(tuple(study))
        if len(machine) != 0:
            sql+='and m.machine_id in %s'
            tup.append(tuple(machine))
        if len(distance) != 0:
            sql+='and calibration_measurement.manual_distance in %s'
            tup.append(tuple(distance))
        tup = tuple(tup)
        print(tup)
        cur.execute(sql,tup)

        data = cur.fetchall()
        conn.commit()
        df = pd.DataFrame(data, columns=['measurement_id' , 'calculated_distance', 'cancer_tissue'])
        df['measurement_data'] = np.nan
        df['measurement_data'] = df['measurement_data'].astype(object)
        df.set_index('measurement_id', inplace=True)

        # crazy process of setting nympy.array as a cell value 🤯🤯🤯
        ids = df.index.values
        for file in ids:
            matrix = np.load(f'{data_path}measurements/{file}.npy')
            df.at[file, 'measurement_data'] = matrix
        socketio.emit('modelupdate',{'msg':'Dataset created'},room=client)

        clf = load(model) # Load classifier
        app.logger.info('model loaded')
        y_true = df["cancer_tissue"].astype(int).values # Load true labels
        # print(y_true)
        app.logger.info('dataset created')
        app.logger.info(len(df))
        socketio.emit('modelupdate',{'msg':'Running prediction'},room=client)
        # print(df)
        y_pred = clf.predict(df) # Predict labels from model
        socketio.emit('modelupdate',{'msg':'Prediction successful'},room=client)

        app.logger.info(f'Dataset length: {len(df)}')
        accuracy = accuracy_score(y_true, y_pred)
        precision = precision_score(y_true, y_pred) 
        sensitivity = recall_score(y_true, y_pred) 
        specificity = recall_score(y_true, y_pred, pos_label=0)
        response = {
            'message': f"""Accuracy: {round(accuracy,2)}
            Precision: {round(accuracy,2)}
            Sensitivity: {round(sensitivity,2)}
            Specificity: {round(specificity,2)}
            Runtime: {round(time.time() - timer,2)} seconds """
        }
        # app.logger.info(response)
        return jsonify(response)
    
class GetModelFilters(Resource):
    @require_auth
    def post(self,uid):
        cur = conn.cursor()
        form = request.get_json()

        study = form.get('study')

        # if no study filters, return all studies
        if study is None or len(study)==0:
            cur.execute('SELECT * from study ORDER by study_id asc')
            data = cur.fetchall()
            conn.commit()
            response = {}
            response['filter'] = 'study'
            response['options'] = data
            return response

        # if no machine filters, get all study filters 
        # and return all machines for chosen studies
        machine = form.get('machine')        
        studies = []
        for st in study:
            studies.append(st.get('value'))
        if machine is None or len(machine)==0:
            cur.execute('SELECT distinct(ma.machine_id) ,ma.name from measurement m join study s on m.study_id = s.study_id JOIN machine ma on  m.machine_id = ma.machine_id WHERE m.study_id in %s ORDER by machine_id  ASC ',(tuple(studies),))
            data = cur.fetchall()
            conn.commit()
            response = {}
            response['filter'] = 'machine'
            response['options'] = data
            return response
        
        # if there are study and machine filters provided,
        # return all eligible manual distances 
        machines = []
        for ma in machine:
            machines.append(ma.get('value'))
        if len(machine) ==0:
            cur.execute('SELECT distinct(cm.manual_distance ) ,cm.manual_distance  from measurement m join study s on m.study_id = s.study_id JOIN machine ma on  m.machine_id = ma.machine_id join calibration_measurement cm on cm.calibration_measurement_id = m.calibration_measurement_id  WHERE m.study_id in %s  ORDER by cm.manual_distance ASC' ,(tuple(studies),))
        else:
            cur.execute('SELECT distinct(cm.manual_distance ) ,cm.manual_distance  from measurement m join study s on m.study_id = s.study_id JOIN machine ma on  m.machine_id = ma.machine_id join calibration_measurement cm on cm.calibration_measurement_id = m.calibration_measurement_id  WHERE m.study_id in %s and ma.machine_id in %s ORDER by cm.manual_distance ASC' ,(tuple(studies),tuple(machines),))
        data = cur.fetchall()
        # print(data)
        conn.commit()
        response = {}
        response['filter'] = 'distance'
        response['options'] = data
        return response
        
        

class UploadCalibration(Resource):
    @require_auth
    def post(self,uid):
        res = {}
        res['error'] = 0
        res['message'] =''
        file = request.files.get('File')

        try:
            csv = pd.read_csv(file)
            print(csv)
            if 'calibration_measurement_id' not in csv.columns.to_list():
                print('calibration_measurement_id' in csv.columns.to_list())
                print(csv.columns.to_list())
                res['error'] = 1
                res['message'] = 'No headers provided, or you are using ";" as delimiter\n Please use "," instead.'
                return res
        except Exception as e:
            app.logger.error(e)
            res['error'] = 1
            res['message'] = 'Unable to read file. Please check for correct format'
            return res
        csv = csv.apply(pd.to_numeric,errors='coerce')
        
        #uploading calculated_distance
        try:
            distance = csv[csv['calculated_distance'].notnull()]
        except Exception as e:
            app.logger.error(e)
            res['error'] = 1
            res['message'] = str(e)
            return res
        cur = conn.cursor()
        for i in range(len(distance)):
            try:
                cur.execute(f"UPDATE calibration_measurement SET calculated_distance = {distance.iloc[i]['calculated_distance']} WHERE calibration_measurement_id = {distance.iloc[i]['calibration_measurement_id']};")
            except Exception as e:
                res['error'] = 1
                res['message'] += f'\n {str(e)}'
                conn.rollback()
        isna = csv[csv['calculated_distance'].isna()]
        if len(isna)>0:
            res['message'] = f"""Calculated distance:
            Calibration measurements with id's: {str(isna['calibration_measurement_id'].values.tolist())} were not uploaded because values could not be parsed.
            Please check for mistakes \n \n"""
        else:
            res['message'] = """Calculated distance:
            Everything uploaded without errors.\n\n"""

        #uploading beam center
        
        if not all( val in csv.columns for val in ['center_col','center_row']):
            
            res['message'] += """Beam center:
                No data provided"""
            return res
        try:
            center = csv[(csv['center_row'].notnull() & csv['center_col'].notnull())]
        except Exception as e:
            app.logger.error(e)
            res['error'] = 1
            res['message'] += str(e)
            return res
        cur = conn.cursor()
        for i in range(len(center)):
            try:
                cur.execute(f"UPDATE calibration_measurement SET center_row = {csv.iloc[i]['center_row']} ,center_col = {csv.iloc[i]['center_col']} WHERE calibration_measurement_id = {distance.iloc[i]['calibration_measurement_id']};")
            except Exception as e:
                res['error'] = 1
                res['message'] += f'\n {str(e)}'
                conn.rollback()
        isna = csv[(csv['center_row'].isnull() | csv['center_col'].isna())]
        print(isna)
        if len(isna)>0:
            res['message'] += f"""Beam center:
            Calibration measurements with id's: {str(isna['calibration_measurement_id'].values.tolist())} were not uploaded because values could not be parsed.
            Please check for mistakes"""
        else:
            res['message'] += """Beam center:
            Everything uploaded without errors."""
        conn.commit()
        cur.close()
        return res
    


class SubmitPatient(Resource):
    @require_auth
    def post(self,uid):
        progress = lambda: collections.defaultdict(progress)
        # tree = progress()
        res = {}
        app.logger.info('recieved file')
        ############# DATABASE INITIAL CONNECTION #############
        ### Getting current information from database about studies, patients and machines
        response = {'Error':None}
        try:
            cur = conn.cursor()
            cur.execute(f"SELECT patient_id, code_name FROM patient")
            patient_data = dict(cur.fetchall())
            cur.close()

            cur = conn.cursor()
            cur.execute(f"SELECT study_id, study_name FROM study")
            study_data = dict(cur.fetchall())
            cur.close()

            cur = conn.cursor()
            cur.execute(f"SELECT machine_id, name FROM machine")
            machine_data = dict(cur.fetchall())
            cur.close()
        except BaseException as e:
            app.logger.error(e.args)
            conn.rollback()
            response['Error'] = e.args
            return jsonify(response)
        
        
        ### Checking directories format and getting a list of directories 
        
        def initial_check(measurements_directories, all_dir):
            dirs = []
            missing_folder_err = [f'ERROR. The following files are incorrrectly inserted. Please check for missing folders or create a folder for them.']
            excess_folder_err = [f'ERROR. The following files contain excess folders. Please check for formatting errors.']
            unknown_err = [f'ERROR. The following files are inserted incorrectly.']
            missing_dsc_err = [f'ERROR. Missing desciption file (.dsc) for the following files. Please check that if the formatting is the same for both .txt and .dsc files.']

            ### Going through each file in directory and getting information from the path

            for directory in measurements_directories:
                dir = directory.split('/')

                ### Checking format of the directory
                if '__MACOSX' in dir[0]:
                    continue
                if len(dir) == 5:    
                        directory = '/'.join(dir[:len(dir)-1])
                        dirs.append(directory)

                if len(dir) != 5:   
                    if len(dir) < 5: 
                        error_message = f'{CRED}ERROR. Directory for the file {"/".join(dir)} has missing folders{CEND}'
                        missing_folder_err.append("/".join(dir))
                        app.logger.error(error_message)
                        continue
                    if len(dir) == 6:
                        if 'Repeat' in dir[3].split('_'):
                            repeat_dir = dir
                            directory = '/'.join(repeat_dir[:len(repeat_dir)-1])
                            dir.pop(3)
                            dirs.append(directory)
                        else:
                            error_message = f'{CRED}ERROR. Directory for the file {"/".join(dir)} has excess folders{CEND}'
                            excess_folder_err.append("/".join(dir))
                            app.logger.error(error_message)
                            continue
                    else:
                        error_message = f'{CRED}ERROR. Directory for the file {"/".join(dir)} is incorrect{CEND}'
                        app.logger.error(error_message)
                        unknown_err.append("/".join(dir))
                        continue

                ### Checking existance of the .dsc file

                file_name = directory+'/'+dir[4]
                if not file_name +'.dsc' in all_dir:
                    error_message = f'{CRED}ERROR. .dsc file for {file_name} does not exist{CEND}'
                    app.logger.error(error_message)
                    missing_dsc_err.append(file_name)
                    continue

                dirs.append(directory)
                dirs = list(dict.fromkeys(dirs))      

            error_message = ''
            if len(missing_folder_err) > 1: error_message += "\n\n" + "\n".join(missing_folder_err)
            if len(excess_folder_err) > 1: error_message += "\n\n" + "\n".join(excess_folder_err)
            if len(unknown_err) > 1: error_message += "\n\n" + "\n".join(unknown_err)
            if len(missing_dsc_err) > 1: error_message += "\n\n" + "\n".join(missing_dsc_err)

            if len(error_message) > 0:
                app.logger.error(error_message)
                res['error'] = 1
                res['message'] = error_message[2:]
                return res
            else:
                return dirs
        
        ### Getting data and files to upload to DB 

        def upload_to_db(measurements_dir, directory, patient_data=patient_data, study_data=study_data, machine_data=machine_data):
            calibration_measurement_id = -1
            patient_id = -1
            study_id = -1
            machine_id = -1
            sample_id = -1

            ### Going through each file in directory and getting information from the path
            for d in measurements_dir: 
                dir = d.split('/')

                if len(dir) > 5:
                    dir.pop(3)

                dir = [fol.split('_') for fol in dir]
                study_name = dir[0][0].replace(" ", "_").replace("-", "_")
                code_name = str(dir[0][2]) #patient
                name = dir[1][0] #machine
                target = dir[1][1] #machine
                manual_distance = re.sub('\D', '', dir[2][1]) #calibration_measurement
                measurement_date = f'{dir[3][0]}-{dir[3][1]}-{dir[3][2]} 12:00:00'
                tissue_size = dir[3][5]
                cancer_tissue = True if dir[3][6].lower() == 'cancer' else False
                blind  = request.form.get('Blind')
                
                file_name = '_'.join(dir[4])
                app.logger.info("reading file: "+ file_name)
                try:
                    with ZipFile(request.files.get('File')) as zf:
                        file = zf.read(directory+'/'+file_name+'.dsc')
                        image = zf.read(directory+'/'+file_name)
                except Exception as e:
                    error_message = f'{CRED} ERROR {e.args[0]}{CEND}'
                    app.logger.error(error_message)
                    continue

                ### Getting information from .dsc file of the measurement
                app.logger.info("reading metadata from.dsc file")
                calibration_date = datetime.utcfromtimestamp(get_metadata_from_zipFile(file)[0]).strftime('%Y-%m-%d %H:%M:%S')
                exposure_time = get_metadata_from_zipFile(file)[1]
                measurement_date = calibration_date
                
                # tree[study_name][code_name][name][target][manual_distance][measurement_date][tissue_size][cancer_tissue][exposure_time][file_name]=False
                
                ### Getting ids of studies, machines, patients and updating data about them if the record does not exist

                if study_name in study_data.values():
                    study_id = list(study_data.keys())[list(study_data.values()).index(study_name)]
                else:
                    cur = conn.cursor()
                    cur.execute(f"INSERT INTO study(study_name) VALUES ('{study_name}') RETURNING study_id")
                    conn.commit() 
                    study_id = cur.fetchall()[0][0]
                    cur.close()
                    study_data[study_id] = study_name
                if code_name in patient_data.values():   
                    patient_id = list(patient_data.keys())[list(patient_data.values()).index(code_name)]
                
                else:
                    cur = conn.cursor()
                    cur.execute("INSERT INTO patient(code_name,cancer_diagnosis,blind) VALUES(%s,%s,%s) RETURNING patient_id",(code_name,True,blind))
                    conn.commit()   
                    patient_id = cur.fetchall()[0][0]
                    cur.close()  
                    patient_data[patient_id] = code_name
                app.logger.info(f"patient_id: {patient_id}")

                if name in machine_data.values():
                    machine_id = list(machine_data.keys())[list(machine_data.values()).index(name)]
                else:
                    cur = conn.cursor()
                    cur.execute("INSERT INTO machine(target, name) VALUES(%s,%s) RETURNING machine_id",(str(target),str(name)))
                    conn.commit() 
                    machine_id = cur.fetchall()[0][0]
                    cur.close()
                    machine_data[machine_id] = name
                app.logger.info(f"macine_id: {machine_id}")
                print(data_path)
                ############# UPLOADING TO THE DATABASE #############
                if file_name[:2] == 'Ag':
                    hash = hashlib.md5(image).hexdigest()
                    cur = conn.cursor()
                    print(hash)
                    cur.execute('select calibration_measurement_id from calibration_measurement where hash = %s',((hash,)))
                    resp = cur.fetchone()
                    conn.commit()
                    cur.close()
                    print(resp)
                    if not resp:
                       
                        calibration_measurement = [calibration_date, machine_id, manual_distance, file_name, uid, hash]

                        cur = conn.cursor()
                        cur.execute("INSERT INTO calibration_measurement(calibration_date, machine_id, manual_distance, orig_file_name, uploaded_by, hash) VALUES (%s,%s,%s,%s,%s,%s) RETURNING calibration_measurement_id;",(calibration_measurement))    
                        conn.commit() 
                        calibration_measurement_id = cur.fetchall()[0][0]
                        cur.close()
                        msg = save_image(calibration_measurement_id, image, data_path+'calibration_measurements')
                        app.logger.info(msg)
                    else:
                        calibration_measurement_id = resp[0]
                    # tree[study_name][code_name][name][target][manual_distance][measurement_date][tissue_size][cancer_tissue][exposure_time][file_name]=True

                else:
                    try:
                        cur = conn.cursor()
                        cur.execute("INSERT INTO sample(sample_type, patient_id) values (%s,%s) returning sample_id",((None,patient_id)))
                        conn.commit()
                        sample_id = cur.fetchall()[0][0]
                        cur.close()
                    except Exception as e:
                        conn.rollback()
                        response['Error'] = e.args
                        app.logger.error(e.args)
                        return jsonify(response)
                    hash = hashlib.md5(image).hexdigest()
                    cur = conn.cursor()
                    cur.execute('select measurement_id from measurement where hash = %s',((hash,)))
                    resp = cur.fetchone()
                    conn.commit()
                    cur.close()
                    print(resp)
                    tissue_type = "Breast"
                    if not resp:
                       
                        measurement = [calibration_measurement_id, machine_id, study_id, cancer_tissue, patient_id, tissue_size, exposure_time, measurement_date, file_name, uid,sample_id, hash, tissue_type]

                        cur = conn.cursor()
                        cur.execute("INSERT INTO measurement(calibration_measurement_id, machine_id, study_id, cancer_tissue, patient_id, tissue_size, exposure_time, measurement_date, orig_file_name, uploaded_by, sample_id, hash, tissue_type) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING measurement_id;",(measurement))
                        conn.commit() 
                        measurement_id = cur.fetchall()[0][0]
                        cur.close() 
                        msg = save_image(measurement_id, image, data_path+'measurements')
                        app.logger.info(msg)
                    else:
                        measurement_id = resp[0]
                    # tree[study_name][code_name][name][target][manual_distance][measurement_date][tissue_size][cancer_tissue][exposure_time][file_name]=True
            app.logger.info(f'measurement {measurement_id} uploaded to database')
            return True


        ############# ZIP POST START #############
        ### Getting directory data from zip and creating a list of directories where measurements files are contained
        file = request.files.keys()
        with ZipFile(request.files.get('File')) as data:
            all_dir = data.namelist()

        measurements_directories = [f for f in all_dir if f[-3:] == 'txt']
        measurements_directories = [x for x in measurements_directories if not x.startswith('__MACOSX')]


        ### Checking full directory and returning either error or measurements 
        dirs = initial_check(measurements_directories, all_dir)

        if type(dirs) != list:
            return dirs
        
        ### Going through each folder and selecting .txt files
        for dir in dirs:
            directory = dir
            app.logger.info(f'working in {dir}')
            measurements_dir = [i for i in measurements_directories if dir in i]
            measurements_dir.sort()

            ### Selecting different detectors measurements files to match calibrations
            det1_measurements = [x for x in measurements_dir if 'det1' in x]
            det2_measurements = [x for x in measurements_dir if 'det2' in x]

            ### Uploding to DB
            if len(det1_measurements)> 0:
                tree_det1 = upload_to_db(det1_measurements, directory)
                tree_det2 = upload_to_db(det2_measurements, directory)
                tree = [tree_det1, tree_det2]
            else:
                tree = upload_to_db(measurements_dir, directory)

        print(tree)
        res['error'] = 0
        res['message'] = 'Uploaded'
        return res

   

class Login(Resource):
    # HTTP POST method for login
    def post(self):
        # Get JSON data from request
        auth = request.get_json()
        # Extract email and password from request data
        email = auth.get('email')
        password = auth.get('password')

        # If no email or password provided, return a 400 error
        if not email or not password:
            return 'no username or pass',400
        cur = conn.cursor()

        # Execute the SQL command to find the user by email
        cur.execute('SELECT uid,password from users WHERE email = (%s);', (email,))

        # Fetch the first (and hopefully only) result
        resp = cur.fetchone()
        cur.close()
        print(resp)

        # If a user was found...
        if resp:
            # ...extract their ID and password hash...
            _uid = resp[0]
            _pass = resp[1]

            # ...check if the provided password matches the hashed password...
            if check_password_hash(_pass,password):

                # Prepare a response object
                resp = {
                    'tokenType': "Bearer"
                }
                # Create a JWT token with user ID and expiry time
                token = jwt.encode({'uid':_uid,'exp':datetime.now()+timedelta(1)},app.config['SECRET_KEY'])
                # Add additional information to the response
                resp['expiresIN'] = 1440 # Token expiry time in minutes
                resp['authState'] = _uid # User ID
                resp['token'] = token # JWT token
                print('success') # Log success
                print(resp)
                return jsonify(resp)
            pass

class GetToken(Resource):
    @require_auth
    def get(self,uid):

        # Create a new session object
        session = requests.session()

        # POST request to login and get a bearer token
        # Note: Yes, credentials are hardcoded, and this is OK!!!!!
        bearer = session.post("https://superset.mlgarden.dev/api/v1/security/login", json= {'password': ,
                    'provider':
                    'refresh': 
                    'username': "})
                    # единственные хардкодед переменные которые я удалил
        
        # Extract the access_token from the response
        bearer = bearer.json()['access_token']
        
        # GET request to get the CSRF token, using the bearer token in the Authorization header
        csrf = session.get('https://superset.mlgarden.dev/api/v1/security/csrf_token/',headers={'Authorization':'Bearer '+ bearer})

        # Extract the CSRF token from the response
        csrf = csrf.json()['result']
        
        # POST request to get a guest token, sending the CSRF token in the headers
        # This request also sends a JSON payload specifying the resource and user details
        token = session.post("https://superset.mlgarden.dev/api/v1/security/guest_token/", json={"resources": [
              {
                "id": "ea5e4076-546e-4f68-a0d6-6821e88ebf6d",
                "type": "dashboard"
              }
            ],
            "user": {
              "first_name": "",
              "last_name": "",
              "username": ""
                                  # единственные хардкодед переменные которые я удалил

            },
            "rls":[]}, headers= {'Authorization':'Bearer '+ bearer,"X-CSRFToken":csrf})
        # Return the token to the frontend
        return token.json()['token']
    

class Register(Resource):

    def post(self):

        # Get the JSON data sent with the POST request
        data = request.get_json()
        
        # Hash the password sent in JSON data using sha256 method
        pwd = generate_password_hash(data['password'],method='sha256')

        # Generate a unique ID for the new user
        uid = uuid.uuid4()

        # Get the 'email' and 'name' fields from the JSON data
        email = data.get('email')
        name = data.get('name')
        

        cur = conn.cursor()

        # Check if a user already exists with the same email in the database
        cur.execute("SELECT count(*) FROM users where email=(%s);",(email,))
        resp = cur.fetchone()
        
        # If no user exists with the same email (response is 0), add new user to the database
        if resp[0] == 0:
            cur.execute("INSERT INTO users VALUES (%s,%s,%s,%s);", (str(uid),name,email,str(pwd)))
            conn.commit() # Commit the changes made to the database
        
        # Close the cursor to avoid memory leaks
        cur.close()
        return 200