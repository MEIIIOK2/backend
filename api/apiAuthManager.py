from functools import wraps
from flask import request
from config import conn
from datetime import datetime
from config import app


# This is a decorator to require API authentication.
# It is used to protect certain routes by requiring an API key.
def require_api_auth(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        # Get the HTTP method of the request
        method = request.method
        # If it's a GET request, try to get the key from the query parameters
        if method =='GET':
            key = request.args.get('key')
        # For other methods, get the key from the form data
        else:
            key = request.form.get('key')
        # If no key is provided, return an error
        if key is None:
            return {'Error':'No access key provided'}
        try:
             # Create a cursor object and execute the SQL query to fetch the access_key and its expiry date

            cur = conn.cursor()
            cur.execute("SELECT id, expiry_date, access_level from api_access_keys a join users u on a.uid = u.uid where access_key=(%s);", (key,))
            resp = cur.fetchone() # Fetch one record
            conn.commit() # Commit any changes to the database
            cur.close() # Close the cursor
            # If the access key doesn't exist in the database
            if resp is None:
                return {'Error':'Wrong acces key'}
            # If the access key has expired
            if resp[1] < datetime.now():
                return {'Error':'Key expired'}
            
            # Uncomment the code below to insert access history into the database
            # try:
            #     cur = conn.cursor()
            #     cur.execute("INSERT INTO api_access_history (key_id,access_date) VALUES(%s,%s);", (resp[0],datetime.now(),))
            # except Exception as e:
            #     print(e)
            #     return {'Error':'Database error 1'}

            # If the key is valid and not expired, continue to the original function
            return f(access_level=resp[2], *args, **kwargs)
        # Handle any unexpected errors during the process
        except Exception as e:
             app.logger.error(e)
             app.logger.error(e,exc_info=True)
             app.logger.exception(e)
             return {'Error':'Database error 2'}
    return wrapper
