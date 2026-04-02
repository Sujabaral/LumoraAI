from ChatbotWebsite import create_app
from dotenv import load_dotenv
from flask import send_from_directory
import os

# Load .env from the project root
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '.env'))

app = create_app()

@app.route('/manifest.json')
def manifest():
    return send_from_directory('static', 'manifest.json')

@app.route('/sw.js')
def service_worker():
    return send_from_directory('static', 'sw.js')

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5001, debug=True)
