# Import necessary libraries from flask, utils and psycopg2.
from flask import Flask
from flask_restful import Api
from flask_cors import CORS
from utils import EnvVariables
import psycopg2
from logging.config import dictConfig
from flask_socketio import SocketIO

# Configuring the logging for the application. This dictionary defines the
# components of the logging system in a structured way.
dictConfig({
    'version': 1,
    'formatters': {'default': {
        # Format for the log messages
        'format': '[%(asctime)s] %(levelname)s in %(module)s: %(message)s',
    }},
    "handlers": {
            "console": {
                # Console handler is being set up with StreamHandler
                "class": "logging.StreamHandler",
                # Output stream is set to standard output (console)
                "stream": "ext://sys.stdout",
                "formatter": "default",
            },
            
        },
        # Setting the root logger level to NOTSET which means all messages will be processed.
        "root": {"level": "NOTSET", "handlers": ["console"]},
    
})

# Creating an instance of the Flask class.
app = Flask(__name__)
# Enabling CORS for the app. This will allow all domains by default.
CORS(app)
# Creating an API object by passing it the instance of the Flask class.
api = Api(app)
# Initializing the environment variables.
env = EnvVariables(prod=True)
print(env.database)
# Configuring the secret key for the Flask application from the environment variables.
app.config['SECRET_KEY']=env.secret
# Setting the data path from the environment variables.
data_path = env.datapath
# Logging an info level message about the server's status.
app.logger.info('Up and running')
# Establishing a connection to the Postgres database using the environment variables.
conn = psycopg2.connect(
            host=env.host,
            database=env.database,
            user=env.user,
            password=env.password)
# Logging an info level message about the successful database connection.
socketio = SocketIO(app,cors_allowed_origins="*")
app.logger.info('Connected to postgres')
