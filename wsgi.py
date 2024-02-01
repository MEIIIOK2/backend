# Importing Flask application object from the main module
from main import app

# Entry point of the script. This condition is true when the script is executed directly.
if __name__ == "__main__":
    # Run the Flask web server.
    # Flask’s development server is not meant for production use, 
    # It is a simple and lightweight solution perfect for small applications and development and testing scenarios.
    # For deploying production server, you might want to use WSGI servers like Gunicorn or uWSGI.
    app.run(debug=True)
