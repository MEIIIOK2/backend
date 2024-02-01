# Import the application object and the API object from the config module
from config import app, api, socketio
# Import the different handlers used for various operations 
from frontend.frontendHandler import Register, Login, SubmitPatient, GetToken, UploadCalibration, UploadModel, GetModelFilters, Demo

# Import a handler for an API endpoint to rettrieve dada from the database
from api.apiHandler import  ReturnMultipleByApi

from websockets.websocketHandler import SocketHandler


api.add_resource(SubmitPatient, '/upload')
api.add_resource(UploadCalibration, '/calibration')
api.add_resource(Register, '/signin')
api.add_resource(Login, '/login')
api.add_resource(GetToken,'/token')
api.add_resource(UploadModel,'/assessment/modelupload')
api.add_resource(GetModelFilters, '/assessment/getfilters')

api.add_resource(ReturnMultipleByApi, '/api/getmultiple')
api.add_resource(Demo,'/demo')

socketio.on_namespace(SocketHandler())
# This is the entry point of the application. 
# If this script is run directly (as opposed to being imported), then the app will start running.
if __name__ == '__main__':
    # The app is set to run on all interfaces (0.0.0.0) and in debug mode.
    # Debug mode provides more detailed error messages and allows for hot-reloading the server when code changes are detected.
    socketio.run(app,host = '0.0.0.0', debug=True)