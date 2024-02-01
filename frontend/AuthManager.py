from functools import wraps
from flask import request,jsonify
import jwt
from config import app,conn


def require_auth(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        print('incoming')
        # Retrieve the 'Authorization' token from the request headers.
        token = request.headers.get('Authorization')

        # If the token exists...
        if token:

            # ...decode it. The JWT is assumed to be in the 'Bearer <token>' format, hence the split and [1].
            decoded = jwt.decode(token.split(' ')[1], app.config['SECRET_KEY'], "HS256")
            print(decoded)
            try:
                cur = conn.cursor() # Create a cursor object.

                # Execute a SQL command: select the count of users with the uid found in the decoded token.
                cur.execute("SELECT count(*) FROM users where uid=(%s);", (decoded['uid'],))
                 
                resp = cur.fetchone()
                conn.commit()
                cur.close()

                # If no user with this uid was found return a 'User not found' message in JSON format.
                if resp[0] == 0:
                    return jsonify('User not found')
                
                # If the user was found, call the decorated function with uid set to the one from the decoded token, plus any other arguments.
                return f(uid=decoded['uid'], *args, **kwargs)
            
            # In case any exception occurs during the above...
            except BaseException as e:
                print(e.args)
                # ...and rollback any changes made to the database during this request.
                conn.rollback()
        else:
             # If the token was not provided in the request, return a 'Not Authorized' message in JSON format.
            return jsonify('Not Authorized')

    return wrapper



