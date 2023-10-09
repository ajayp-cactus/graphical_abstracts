from flask import Flask
from flask_cors import CORS
from flask_sslify import SSLify
from flask import Flask, request, jsonify
import requests
from render_json_summary_from_pdf import pdf_processor, download_pdf
import uuid
import os
import redis
import json
from multiprocessing import Process
from threading import Thread
# Initialise flask app
app = Flask(__name__)
CORS(app, supports_credentials=True,resources={r"*": {"origins": "*"}})
sslify = SSLify(app)
AUTH_TOKEN = "test"
request_id = str(uuid.uuid4())
UPLOAD_FOLDER='./data/'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
ALLOWED_EXTENSIONS = {'pdf'}

with open("./credentials/gcp_credentials.json") as f:
    gcp_creds = json.load(f)
    
r = redis.Redis(
  host='eu2-workable-halibut-30662.upstash.io',
  port=30662,
  password=gcp_creds['redis_password']
)

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

        pdf_path = f"{UPLOAD_FOLDER}/{request_id}.pdf"
        if 'file' in request.files:
            file = request.files['file']
            if file.filename == '':
                return {
                  'status': 'failed',
                  'request_id': request_id,
                  'error': 'invalid file'
                  }
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], f"{request_id}.pdf"))
        else:
            # Get the PDF or PDF URL from the request data
            pdf_data = request.get_json()
            pdf_url = pdf_data['pdf_url']
            download_pdf(pdf_url, pdf_path)
        model_type = pdf_data['type'] if pdf_data.get('type') else 'gpt'
        json_result = pdf_processor(pdf_path, model_type)
        
        result = {'status': 'success',
                  'request_id': request_id,
                  'json_result': json_result}
        
        return jsonify(result)
    except Exception as e:
        result = {'status': 'failed',
                  'request_id': request_id,
                  'error': e}
        return jsonify(result)
    
    
@app.route('/process_pdf_async', methods=['POST','OPTIONS'])
def process_pdf_async():
    if request.method =='OPTIONS':
        result = {'status': 'true'}
        response = jsonify(result)
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', '*')
        response.headers.add('Access-Control-Allow-Methods', '*')
        return response
    print(request.headers)
    print(request.form,request.files)
    # if len(request.form)==0:
    #     requests_data=request.get_json()
    # else:
    request_data=request.form
    # Get the authentication token from the request headers
    auth_token = request.headers.get('Authorization')
    
    try:
        # Check if the token is valid
        if auth_token != AUTH_TOKEN:
            return jsonify({'error': 'Authentication failed'}), 401

        pdf_path = f"{UPLOAD_FOLDER}/{request_id}.pdf"
        if 'file' in request.files:
            file = request.files['file']
            if file.filename == '':
                return {
                  'status': 'failed',
                  'request_id': request_id,
                  'error': 'invalid file'
                  }
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], f"{request_id}.pdf"))
        else:
            # Get the PDF or PDF URL from the request data
            
            pdf_url = request_data['pdf_url']
            download_pdf(pdf_url, pdf_path)
        # json_result = pdf_processor(pdf_path)
        # asyncio.run(async_process(request_id,pdf_path))
        # process = Process(target=async_process, args=(request_id,pdf_path))
        # process.start()
        
        thread = Thread(target = async_process, args = (request_id,pdf_path))
        thread.start()

        result = {'status': 'in_progress',
                  'request_id': request_id}
        response = jsonify(result)
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', '*')
        response.headers.add('Access-Control-Allow-Methods', '*')
        return response
    except Exception as e:
        result = {'status': 'failed',
                  'request_id': request_id,
                  'error': e}
        response = jsonify(result)
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', '*')
        response.headers.add('Access-Control-Allow-Methods', '*')
        return response
    
def async_process(request_id,pdf_path):
    model_type = pdf_data['type'] if pdf_data.get('type') else 'gpt'
    json_result = pdf_processor(pdf_path, model_type)
    r.json().set(request_id, "$", json_result)
    return True
    

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=8080, debug=True)
