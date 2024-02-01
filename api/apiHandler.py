from flask_restful import Resource
from flask import request, send_file, jsonify
from utils import get_metadata_from_fileStorage
import numpy as np
import pandas as pd
import datetime
from config import app,data_path,conn
from api.apiAuthManager import require_api_auth
import os
from io import BytesIO, StringIO
from zipfile import ZipFile, ZIP_DEFLATED, ZIP_STORED

from time import time



class ReturnMultipleByApi(Resource):
    
    @require_api_auth # this decorator ensures that the client is authenticated before this function can be executed
    def post(self, access_level):
        form = request.form # get the form data from the request

        # Initialize a base SQL query string based on accsess level
        if access_level == 'analyst':
            # Initialize a base SQL query string based on accsess level
            string = 'select * from no_blind_data where 1=1'
        else: 
            string = 'select * from all_data where 1=1'   

        # Iterate over each key in the form data
        for key in form.keys():
            if key =='key': # if the key is 'key', ignore and continue to the next key
                continue

            # Get the values associated with the key
            filter = form.getlist(key)
            print(filter)
            key = key.split(' ')[0]
            print(key)
            
            # If there's only one filter value
            if len(filter) == 1:
                print(filter)
                params = filter[0].split(' ')
                print(params)
                # Check if the filter starts with a comparison operator (<, >, =)
                if filter[0].startswith(('<','>','=')):

                    # if so, update the SQL query string to include this condition
                    string += f" and {key} {params[0]} '{params[1]}'"
                else:

                    # if not, add the condition as an equality check
                    string += f" and {key} = '{params[0]}'"
            else:
                 # if there are multiple values for the filter, add a 'IN' condition in the SQL query
                vals = str(filter)[1:-1]
                string += f' and {key} in({vals})'

        # Try to execute the SQL query and process the results
        try:
            data = pd.read_sql_query(string, conn)
            conn.commit()
            
            # Get unique measurement_ids and calibration_measurement_ids
            measurement_ids = data['measurement_id'].unique().tolist()
            calibration_measurement_ids = data['calibration_measurement_id'].unique().tolist()
            background_ids = data['background_id'].dropna().astype(int).unique().tolist()
            print(background_ids)
            # Convert the data into a CSV string
            data = data.to_csv(index=False, 
                            #    sep=';'
                               )
            
            # Initialize an in-memory bytes buffer
            stream = BytesIO()

            start = time()
            # Open a new zip file in write mode
            with ZipFile(stream, 'w') as zf:

                # For each measurement_id, add the corresponding .npy file to the zip
                for mid in measurement_ids:
                    file = os.path.join(f'{data_path}measurements/{mid}.npy')
                    zf.write(file, 'measurements/'+str(mid)+'.npy',compress_type=ZIP_DEFLATED,compresslevel=1)

                # For each calibration_measurement_id, add the corresponding .npy file to the zip
                for cid in calibration_measurement_ids:
                    file = os.path.join(f'{data_path}calibration_measurements/{cid}.npy')
                    zf.write(file, 'calibration_measurements/'+str(cid)+'.npy',compress_type=ZIP_DEFLATED,compresslevel=1)
                
                for bid in background_ids:
                    file = os.path.join(f'{data_path}backgrounds/{bid}.npy')
                    zf.write(file, 'backgrounds/'+str(bid)+'.npy',compress_type=ZIP_DEFLATED,compresslevel=1)

                # Also add the data CSV to the zip
                zf.writestr('description.csv', data)

            # Seek back to the beginning of the stream
            stream.seek(0)
            app.logger.info(f'Zip operation took: {time() - start} seconds')
            # Return the zip file as a download
            
            return send_file(stream,download_name='data.zip')

         # Handle any exceptions that occur during the query execution or file processing   
        except Exception as e:
            print(e)
            conn.rollback() # Rollback any changes in the database
            return jsonify(str(e)) # Return the error message to the client
