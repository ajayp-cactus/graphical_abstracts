from flask import Flask
from flask_cors import CORS
from flask_sslify import SSLify
from flask import Flask, request, jsonify
import requests
from render_json_summary_from_pdf import pdf_processor, download_pdf
import uuid

# Initialise flask app
app = Flask(__name__)
CORS(app, supports_credentials=True)
sslify = SSLify(app)
AUTH_TOKEN = "test"
request_id = str(uuid.uuid4())


@app.route("/hello", methods=["GET"])
def hello():
    """Method 1: Return a simple hello"""
    return "Hello", 200

@app.route("/check_auth", methods=["GET"])
def check_auth():
    # Get the authentication token from the request headers
    auth_token = request.headers.get('Authorization')

    # Check if the token is valid
    if auth_token != AUTH_TOKEN:
        return jsonify({'error': 'Authentication failed'}), 401
    else:
        return jsonify({'status': 'Authentication successful'}), 200

@app.route('/process_pdf', methods=['POST'])
def process_pdf():
    # Get the authentication token from the request headers
    auth_token = request.headers.get('Authorization')
    try:
        # Check if the token is valid
        if auth_token != AUTH_TOKEN:
            return jsonify({'error': 'Authentication failed'}), 401

        # Get the PDF or PDF URL from the request data
        pdf_data = request.get_json()

        pdf_url = pdf_data['pdf_url']
        pdf_path = f"./data/{request_id}.pdf"
        download_pdf(pdf_url, pdf_path)
        json_result = pdf_processor(pdf_path)
            

        result = {'status': 'success',
                  'request_id': request_id,
                  'json_result': json_result}
        
        return jsonify(result)
    except Exception as e:
        result = {'status': 'failed',
                  'request_id': request_id,
                  'error': e}
        return jsonify(result)

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=8080, debug=True)
