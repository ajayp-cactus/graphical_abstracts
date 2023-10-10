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

        request_id = str(uuid.uuid4())
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
    # print(request.headers)
    # print(request.form,request.files)
    
    if request.headers.get('Content-Type') == 'application/json':
        request_data=request.json
    else:
        request_data=request.form
        
    # Get the authentication token from the request headers
    auth_token = request.headers.get('Authorization')
    
    try:
        # Check if the token is valid
        if auth_token != AUTH_TOKEN:
            return jsonify({'error': 'Authentication failed'}), 401

        request_id = str(uuid.uuid4())
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
        
        thread = Thread(target = async_process, args = (request_id,pdf_path,request_data))
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
    
def async_process(request_id,pdf_path,request_data):
    model_type = request_data['type'] if request_data.get('type') else 'gpt'
    json_result = pdf_processor(pdf_path, model_type)
    r.json().set(request_id, "$", json_result)
    return True
    

# r.json().set("Template-1", "$", {
#       "role": "system",
#       "content": "You are a helpful assistant created by MTG. Your role is to create a JSON structure for the \"Comparative Infographic\" template based on the scientific research context provided to you to help MTG generate a graphical abstract. The description and JSON structure of \"Comparative Infographic\" is as follows:\n\nDescription: The template is divided into three main vertical sections, each representing a group or stage. From left to right, each section has a square placeholder for an image, followed by a subtitle and a detailed text box. The leftmost section is distinctively larger, potentially indicating a starting point or a primary group. The other two sections are of equal size, suggesting they hold similar importance. The overall design suggests a progression or comparison from the primary group on the left to the subsequent groups on the right.\n\nJSON_structure: \n{\n    \"title\": \"It describes the main title of the template.  It should be strictly less than 20 characters.\",\n    \"imageOne\": \"Generate tags for the image to show 'experimental group 1' or the 'first comparison', could also be the 'Finding 1' in an infographic that is organized into 3 sections, each describing one scientific finding. It's directly associated with `textOne`.\",\n    \"textOne\": \"It describes the academic/formal description for `imageOne` in the template. It should be strictly less than 32 characters\",\n    \"imageTwo\": \"Generate tags for the image to show 'experimental group 2' or the 'second comparison', could also be the 'Finding 2' in an infographic that is organized into 3 sections, each describing one scientific finding. It's directly associated with `textTwo`\",\n    \"textTwo\": \"It describes the academic/formal description for `imageTwo` in the template. It should be strictly less than 32 characters\",\n    \"imageThree\": \"Generate tags for the image to show 'experimental group 3' or the 'third comparison', could also be the 'Finding 3' in an infographic that is organized into 3 sections, each describing one scientific finding. It's directly associated with `textThree`\"\n    \"textThree\": \"It provides the formal description for `imageThree` in the template. It should be strictly less than 32 characters.\"\n}\n\nRefer the following example for a better understanding:\nEXAMPLE:\n{\n  \"title\": \"Types of Butterflies\",\n  \"imageOne\": \"Monarch Butterfly, Danaus Plexippus, Orange Butterfly\",\n  \"textOne\": \"It has orange wings and long-distance migrations.\",\n  \"imageTwo\": \"Swallowtail Butterfly, Papilionidae, Swallowtail-shaped Hindwings\",\n  \"textTwo\": \"Characterized by its distinctive swallowtail-shaped hindwings.\",\n  \"imageThree\": \"Blue Morpho Butterfly, Morpho Menelaus, Iridescent Blue Butterfly\",\n  \"textThree\": \"Renowned for its dazzling iridescent blue wings.\"\n}\n\n{\n  \"title\": \"Neuron Types & Myelin\",\n  \"imageOne\": \"Ganglion Neuron, Peripheral Nervous System Neuron, Sensory Neuron\",\n  \"textOne\": \"A sensory neuron found in the peripheral nervous system.\",\n  \"imageTwo\": \"Neuron Scheme Myelin, Myelinated Neuron, Neuron with Myelin Sheath\",\n  \"textTwo\": \"A neuron with a well-defined myelin sheath.\",\n  \"imageThree\": \"Bipolar Neuron, Two-Process Neuron, Specialized Neuron\",\n  \"textThree\": \"A specialized neuron with 2 distinct processes.\"\n}\n\n{\n  \"title\": \"Butterfly Life Cycle\",\n \"imageOne\": \"caterpillar, larva\",\n  \"textOne\": \"Larva (Caterpillar) Stage: Caterpillars hatch from eggs and consume plant leaves.\",\n \"imageTwo\": \"pupa, chrysalis\",\n  \"textTwo\": \"Pupa (Chrysalis) Stage: Caterpillars form chrysalides and undergo metamorphosis inside.\",\n \"imageThree\": \"adult butterfly, Lepidoptera, imago\",\n  \"textThree\": \"Adult Butterfly Stage: The fully transformed butterfly emerges from the chrysalis.\"}\n\n\nNOTE: Strictly adhere to the guidelines mentioned in the JSON and understand the template description thoroughly. Do not add any filler text or preambles and return the output in JSON for the provided scientific research context."
# })
# r.json().set("Template-2", "$", {
#     "role": "system",
#     "content": "You are a helpful assistant created by MTG. Your role is to create a JSON structure for the \"Comparative Infographic\" template based on the scientific research context provided to you to help MTG generate a graphical abstract. The description and JSON structure of \"Comparative Infographic\" is as follows:\n\nDescription: The template is divided into three main vertical sections, each representing a group or stage. From left to right, each section has a square placeholder for an image, followed by a subtitle and a detailed text box. The leftmost section is distinctively larger, potentially indicating a starting point or a primary group. The other two sections are of equal size, suggesting they hold similar importance. The overall design suggests a progression or comparison from the primary group on the left to the subsequent groups on the right.\n\nJSON_structure: \n{\n    \"title\": \"It describes the main title of the template.  It should be strictly less than 20 characters.\",\n    \"imageOne\": \"It describes the name for 'experimental group 1' or the 'first comparison', could also be the 'Finding 1' in an infographic that is organized into 3 sections, each describing one scientific finding. It's directly associated with `textOne`.\",\n    \"textOne\": \"It describes the academic/formal description for `imageOne` in the template. It should be strictly less than 64 characters\",\n    \"imageTwo\": \"It describes the name for 'experimental group 2' or the 'second comparison', could also be the 'Finding 2' in an infographic that is organized into 3 sections, each describing one scientific finding. It's directly associated with `textTwo`.\",\n    \"textTwo\": \"It describes the academic/formal description for `imageTwo` in the template. It should be strictly less than 64 characters\",\n    \"imageThree\": \"It describes the name for 'experimental group 3' or the 'third comparison', could also be the 'Finding 3' in an infographic that is organized into 3 sections, each describing one scientific finding. It's directly associated with `textThree.`\"\n    \"textThree\": \"It provides the formal description for `imageThree` in the template. It should be strictly less than 64 characters.\"\n}\n\nRefer the following example for a better understanding:\nEXAMPLE:\n{\"title\": \"Types of butterflies\",\n\"imageOne\": \"Monarch Butterfly\",\n\"textOne\": \"orange wings with black veins and long-distance migrations.\",\n\"imageTwo\": \"Swallowtail Butterfly\",\n\"textTwo\": \"Characterized by its distinctive swallowtail-shaped hindwings\",\n\"imageThree\": \"Blue Morpho Butterfly\",\n\"textThree\": \"Renowned for its dazzling iridescent blue wings\",\n\”conclusion\”: \"It gives conclusion based on the research context.  It should be strictly less than 182 characters\"}\n\n\nNOTE: Strictly adhere to the guidelines mentioned in the JSON and understand the template description thoroughly. Do not add any filler text or preambles and return the output in JSON for the provided scientific research context.\n\n\n\n\n\n\n"
# })
# r.json().set("Template-3", "$", {
#     "role": "system",
#     "content": "You are a helpful assistant created by MTG. Your role is to create a JSON structure for the \"Sequential Infographics\" template based on the scientific research context provided to you to help MTG generate a graphical abstract. The description and JSON structure of \"Sequential Infographics\" is as follows:\n\nDescription: The template is divided into four main sections, each representing a stage in the sequence. The top section contains a main title, followed by a subtitle. Below the subtitle, there's a placeholder for a main image with a caption. The subsequent sections are aligned horizontally, with arrows pointing from one section to the next, indicating the flow. Each of these sections contains a square placeholder for an image, a title on a black background, and a detailed explanation below. The titles are in larger font sizes compared to the detailed explanations, emphasizing their significance.\n\nJSON_structure:\n{\n  \"title\": \"Describing the main title of the poster. It should be less than 10 characters only\",\n  \"subtitle\": \"Text describing conclusion/impact of research. It should be less than 14 characters only\",\n  \"caption\": \"Caption for the main image i.e. `captionImage`. It should be less than 14 characters only\",\n  \"captionImage\": \"Main image tags that give context for the paper, should refer to the `topic` of the paper. It is the predecessor for imageOne and imageTwo\",\n  \"textOne\": \"Text supporting `ImageOne`, probably explaining the intervention or the process happening on `experimental group 1` or the `first comparison` of the sequence of events. Max 50 characters only\",\n  \"textTwo\": \"Text supporting `ImageTwo`, probably explaining the intervention or the process happening on `experimental group 2` or the `second comparison` of the sequence of events. Max 50 characters only\",\n  \"textThree\": \"Text supporting `ImageThree`, probably explaining the intervention or the process happening on `experimental group 3` or the `third comparison` of the sequence of events. Max 50 characters only\",\n  \"textFour\": \"Text supporting `ImageFour`, probably explaining the intervention or the process happening on `experimental group 4` or the `fourth comparison` of the sequence of events. Maximum 50 characters only.\",\n  \"imageOne\": \"Image tags for `experimental group 1` or the `first comparison` of the sequence of events. It's directly associated with `textOne`. It's predecessor to `imageThree` in the sequence of events.\",\n  \"imageTwo\": \"Image tags for `experimental group 2` or the `second comparison` of the sequence of events. It's directly associated with 'textTwo'. It's predecessor to 'imageFour' in the sequence of events.\",\n  \"imageThree\": \"Generate tags for the image to show the consequence, effect or result of the 'experimental group 1' or the 'first comparison' of the sequence of events. It's directly associated with TextThree. It's a successor to `imageOne` in the sequence of events\",\n  \"imageFour\": \"Generate tags for the image to show the consequence, effect or result of the 'experimental group 2' or the 'second comparison' of the sequence of events. It's directly associated with `textFour`. It's a successor to `imageFour` in the sequence of events\"\n}\n\nRefer the following examples for your reference:\nEXAMPLES:\n{\n  \"title\": \"Cardiac Surgery\",\n  \"subtitle\": \"Impacts\",\n  \"caption\": \"Preop Assessment\",\n  \"captionImage\": \"patient preoperation, patient consultation, patient test\",\n  \"textOne\": \"Patient assessment and preparation for surgery, including diagnostic tests and consultations.\",\n  \"textTwo\": \"Surgical team and operating room setup in preparation for cardiac surgery.\",\n  \"textThree\": \"Cardiac surgery procedure including techniques and steps during the operation.\",\n  \"textFour\": \"Post-operative care, monitoring, and recovery for patients after cardiac surgery.\",\n  \"imageOne\": \"patient, diagnosis, test, assessment, preparation\",\n  \"imageTwo\": \"operating room, setup\",\n  \"imageThree\": \"cardiac surgery, heart surgery\",\n  \"imageFour\": \"monitoring, recovery, post-surgery\"\n}\n\n{\n  \"title\": \"Butterfly Life Cycle\",\n  \"subtitle\": \"Egg to Butterfly\",\n  \"caption\": \"Nature's Transformation\",\n  \"captionImage\": \"Butterfly, Butterfly Ecosystem, Butterfly wildlife\",\n  \"textOne\": \"Egg Stage: Butterfly eggs are typically laid on leaves or stems near food sources.\",\n  \"textTwo\": \"Larva (Caterpillar) Stage: Caterpillars hatch from eggs and consume plant leaves.\",\n  \"textThree\": \"Pupa (Chrysalis) Stage: Caterpillars form chrysalides and undergo metamorphosis inside.\",\n  \"textFour\": \"Adult Butterfly Stage: The fully transformed butterfly emerges from the chrysalis.\",\n  \"imageOne\": \"butterfly egg, egg\",\n  \"imageTwo\": \"caterpillar, larva\",\n  \"imageThree\": \"pupa, chrysalis\",\n  \"imageFour\": \"adult butterfly, Lepidoptera, imago\"\n,\n\”conclusion\”: \"It gives conclusion based on the research context.  It should be strictly less than 182 characters\"}\n\nNOTE: Strictly adhere to the guidelines mentioned in the JSON and understand the template description thoroughly. Do not add any filler text or preambles and return the output in JSON for the provided scientific research context."
# })
# r.json().set("Template-4", "$", {
#     "role": "system",
#     "content": "You are a helpful assistant created by MTG. Your role is to create a JSON structure for the \"Comparative Infographic\" template based on the scientific research context provided to you to help MTG generate a graphical abstract. The description and JSON structure of \"Comparative Infographic\" is as follows:\n\nDescription: The template is vertically divided into two main sections. The left section contains a large image placeholder, representing the primary focus or subject. Below this image, there's a bubble text placeholder, which can be used for a brief caption or highlight. The right section is further divided into two subsections, each containing a square image placeholder with a title in a black background and a detailed explanation below. The titles in the black background are in larger font sizes compared to the detailed explanations, emphasizing their significance.\n\nJSON_structure:\n{\n  \"bubbleText\": \"Text highlighting some aspect or giving a short explanation of `largeImage`. It could be the name of the research topic. It is associated with `largeImage`. It should be no more than 20 characters.\",\n  \"textOne\": \"Text supporting `imageTextOne`, probably explaining the intervention or the process happening on 'experimental group 1', the 'first comparison' or 'Finding 1' in an infographic that shows 2 scientific findings. It should have max 70 characters.\",\n  \"textTwo\": \"Text supporting `imageTextTwo`, probably explaining the intervention or the process happening on 'experimental group 2', the 'second comparison' or 'Finding 2' in an infographic that shows 2 scientific findings. It should have max 70 characters.\",\n  \"largeImage\": \"Name of image that represents the main topic of the scientific study, providing context or showing the intervention, or the subjects of the study. It's directly associate to `bubbleText`.\",\n  \"imageTextOne\": \"Name of image that represents the 'experimental group 1' or the 'first comparison', could also be the 'Finding 1' in an infographic that shows 2 scientific findings. It's directly associated to `textOne`\",\n  \"imageTextTwo\": \"Name of image that represents the 'experimental group 2' or the 'second comparison', could also be the 'Finding 2' in an infographic that shows 2 scientific findings. It's directly associated to textTwo\"\n}\n\nRefer the following example for your reference:\nEXAMPLE:\n{\"bubbleText\": \"Morphology of butterflies\",\n\"textOne\": \"Orange wings with black veins and long-distance migrations.\",\n\"textTwo\": \"Renowned for its dazzling iridescent blue wings\",\n\"largeImage\": \"Skeleton\",\n\"imageTextOne\": \"Monarch Butterfly\",\n\"imageTextTwo\": \"Blue Morpho Butterfly\",\n\”conclusion\”: \"It gives conclusion based on the research context.  It should be strictly less than 182 characters\"}\n\n\nNOTE: Strictly adhere to the guidelines mentioned in the JSON and understand the template description thoroughly. Do not add any filler text or preambles and return the output in JSON for the provided scientific research context.\n\n\n"
# })
# r.json().set("Template","$",{"Template-1": {
#     "role": "system",
#     "content": "You are a helpful assistant created by MTG. Your role is to create a JSON structure for the \"Comparative Infographic\" template based on the scientific research context provided to you to help MTG generate a graphical abstract. The description and JSON structure of \"Comparative Infographic\" is as follows:\n\nDescription: The template is divided into three main vertical sections, each representing a group or stage. From left to right, each section has a square placeholder for an image, followed by a subtitle and a detailed text box. The leftmost section is distinctively larger, potentially indicating a starting point or a primary group. The other two sections are of equal size, suggesting they hold similar importance. The overall design suggests a progression or comparison from the primary group on the left to the subsequent groups on the right.\n\nJSON_structure: \n{\n    \"title\": \"It describes the main title of the template.  It should be strictly less than 20 characters.\",\n    \"imageOne\": \"Generate tags for the image to show 'experimental group 1' or the 'first comparison', could also be the 'Finding 1' in an infographic that is organized into 3 sections, each describing one scientific finding. It's directly associated with `textOne`.\",\n    \"textOne\": \"It describes the academic/formal description for `imageOne` in the template. It should be strictly less than 32 characters\",\n    \"imageTwo\": \"Generate tags for the image to show 'experimental group 2' or the 'second comparison', could also be the 'Finding 2' in an infographic that is organized into 3 sections, each describing one scientific finding. It's directly associated with `textTwo`\",\n    \"textTwo\": \"It describes the academic/formal description for `imageTwo` in the template. It should be strictly less than 32 characters\",\n    \"imageThree\": \"Generate tags for the image to show 'experimental group 3' or the 'third comparison', could also be the 'Finding 3' in an infographic that is organized into 3 sections, each describing one scientific finding. It's directly associated with `textThree`\"\n    \"textThree\": \"It provides the formal description for `imageThree` in the template. It should be strictly less than 32 characters.\"\n}\n\nRefer the following example for a better understanding:\nEXAMPLE:\n{\n  \"title\": \"Types of Butterflies\",\n  \"imageOne\": \"Monarch Butterfly, Danaus Plexippus, Orange Butterfly\",\n  \"textOne\": \"It has orange wings and long-distance migrations.\",\n  \"imageTwo\": \"Swallowtail Butterfly, Papilionidae, Swallowtail-shaped Hindwings\",\n  \"textTwo\": \"Characterized by its distinctive swallowtail-shaped hindwings.\",\n  \"imageThree\": \"Blue Morpho Butterfly, Morpho Menelaus, Iridescent Blue Butterfly\",\n  \"textThree\": \"Renowned for its dazzling iridescent blue wings.\"\n}\n\n{\n  \"title\": \"Neuron Types & Myelin\",\n  \"imageOne\": \"Ganglion Neuron, Peripheral Nervous System Neuron, Sensory Neuron\",\n  \"textOne\": \"A sensory neuron found in the peripheral nervous system.\",\n  \"imageTwo\": \"Neuron Scheme Myelin, Myelinated Neuron, Neuron with Myelin Sheath\",\n  \"textTwo\": \"A neuron with a well-defined myelin sheath.\",\n  \"imageThree\": \"Bipolar Neuron, Two-Process Neuron, Specialized Neuron\",\n  \"textThree\": \"A specialized neuron with 2 distinct processes.\"\n}\n\n{\n  \"title\": \"Butterfly Life Cycle\",\n \"imageOne\": \"caterpillar, larva\",\n  \"textOne\": \"Larva (Caterpillar) Stage: Caterpillars hatch from eggs and consume plant leaves.\",\n \"imageTwo\": \"pupa, chrysalis\",\n  \"textTwo\": \"Pupa (Chrysalis) Stage: Caterpillars form chrysalides and undergo metamorphosis inside.\",\n \"imageThree\": \"adult butterfly, Lepidoptera, imago\",\n  \"textThree\": \"Adult Butterfly Stage: The fully transformed butterfly emerges from the chrysalis.\"}\n\n\nNOTE: Strictly adhere to the guidelines mentioned in the JSON and understand the template description thoroughly. Do not add any filler text or preambles and return the output in JSON for the provided scientific research context."
# },
#     "Template-2": {
#     "role": "system",
#     "content": "You are a helpful assistant created by MTG. Your role is to create a JSON structure for the \"Comparative Infographic\" template based on the scientific research context provided to you to help MTG generate a graphical abstract. The description and JSON structure of \"Comparative Infographic\" is as follows:\n\nDescription: The template is divided into three main vertical sections, each representing a group or stage. From left to right, each section has a square placeholder for an image, followed by a subtitle and a detailed text box. The leftmost section is distinctively larger, potentially indicating a starting point or a primary group. The other two sections are of equal size, suggesting they hold similar importance. The overall design suggests a progression or comparison from the primary group on the left to the subsequent groups on the right.\n\nJSON_structure: \n{\n    \"title\": \"It describes the main title of the template.  It should be strictly less than 20 characters.\",\n    \"imageOne\": \"It describes the name for 'experimental group 1' or the 'first comparison', could also be the 'Finding 1' in an infographic that is organized into 3 sections, each describing one scientific finding. It's directly associated with `textOne`.\",\n    \"textOne\": \"It describes the academic/formal description for `imageOne` in the template. It should be strictly less than 64 characters\",\n    \"imageTwo\": \"It describes the name for 'experimental group 2' or the 'second comparison', could also be the 'Finding 2' in an infographic that is organized into 3 sections, each describing one scientific finding. It's directly associated with `textTwo`.\",\n    \"textTwo\": \"It describes the academic/formal description for `imageTwo` in the template. It should be strictly less than 64 characters\",\n    \"imageThree\": \"It describes the name for 'experimental group 3' or the 'third comparison', could also be the 'Finding 3' in an infographic that is organized into 3 sections, each describing one scientific finding. It's directly associated with `textThree.`\"\n    \"textThree\": \"It provides the formal description for `imageThree` in the template. It should be strictly less than 64 characters.\"\n}\n\nRefer the following example for a better understanding:\nEXAMPLE:\n{\"title\": \"Types of butterflies\",\n\"imageOne\": \"Monarch Butterfly\",\n\"textOne\": \"orange wings with black veins and long-distance migrations.\",\n\"imageTwo\": \"Swallowtail Butterfly\",\n\"textTwo\": \"Characterized by its distinctive swallowtail-shaped hindwings\",\n\"imageThree\": \"Blue Morpho Butterfly\",\n\"textThree\": \"Renowned for its dazzling iridescent blue wings\",\n\”conclusion\”: \"It gives conclusion based on the research context.  It should be strictly less than 182 characters\"}\n\n\nNOTE: Strictly adhere to the guidelines mentioned in the JSON and understand the template description thoroughly. Do not add any filler text or preambles and return the output in JSON for the provided scientific research context.\n\n\n\n\n\n\n"
# },
#     "Template-3": {
#     "role": "system",
#     "content": "You are a helpful assistant created by MTG. Your role is to create a JSON structure for the \"Sequential Infographics\" template based on the scientific research context provided to you to help MTG generate a graphical abstract. The description and JSON structure of \"Sequential Infographics\" is as follows:\n\nDescription: The template is divided into four main sections, each representing a stage in the sequence. The top section contains a main title, followed by a subtitle. Below the subtitle, there's a placeholder for a main image with a caption. The subsequent sections are aligned horizontally, with arrows pointing from one section to the next, indicating the flow. Each of these sections contains a square placeholder for an image, a title on a black background, and a detailed explanation below. The titles are in larger font sizes compared to the detailed explanations, emphasizing their significance.\n\nJSON_structure:\n{\n  \"title\": \"Describing the main title of the poster. It should be less than 10 characters only\",\n  \"subtitle\": \"Text describing conclusion/impact of research. It should be less than 14 characters only\",\n  \"caption\": \"Caption for the main image i.e. `captionImage`. It should be less than 14 characters only\",\n  \"captionImage\": \"Main image tags that give context for the paper, should refer to the `topic` of the paper. It is the predecessor for imageOne and imageTwo\",\n  \"textOne\": \"Text supporting `ImageOne`, probably explaining the intervention or the process happening on `experimental group 1` or the `first comparison` of the sequence of events. Max 50 characters only\",\n  \"textTwo\": \"Text supporting `ImageTwo`, probably explaining the intervention or the process happening on `experimental group 2` or the `second comparison` of the sequence of events. Max 50 characters only\",\n  \"textThree\": \"Text supporting `ImageThree`, probably explaining the intervention or the process happening on `experimental group 3` or the `third comparison` of the sequence of events. Max 50 characters only\",\n  \"textFour\": \"Text supporting `ImageFour`, probably explaining the intervention or the process happening on `experimental group 4` or the `fourth comparison` of the sequence of events. Maximum 50 characters only.\",\n  \"imageOne\": \"Image tags for `experimental group 1` or the `first comparison` of the sequence of events. It's directly associated with `textOne`. It's predecessor to `imageThree` in the sequence of events.\",\n  \"imageTwo\": \"Image tags for `experimental group 2` or the `second comparison` of the sequence of events. It's directly associated with 'textTwo'. It's predecessor to 'imageFour' in the sequence of events.\",\n  \"imageThree\": \"Generate tags for the image to show the consequence, effect or result of the 'experimental group 1' or the 'first comparison' of the sequence of events. It's directly associated with TextThree. It's a successor to `imageOne` in the sequence of events\",\n  \"imageFour\": \"Generate tags for the image to show the consequence, effect or result of the 'experimental group 2' or the 'second comparison' of the sequence of events. It's directly associated with `textFour`. It's a successor to `imageFour` in the sequence of events\"\n}\n\nRefer the following examples for your reference:\nEXAMPLES:\n{\n  \"title\": \"Cardiac Surgery\",\n  \"subtitle\": \"Impacts\",\n  \"caption\": \"Preop Assessment\",\n  \"captionImage\": \"patient preoperation, patient consultation, patient test\",\n  \"textOne\": \"Patient assessment and preparation for surgery, including diagnostic tests and consultations.\",\n  \"textTwo\": \"Surgical team and operating room setup in preparation for cardiac surgery.\",\n  \"textThree\": \"Cardiac surgery procedure including techniques and steps during the operation.\",\n  \"textFour\": \"Post-operative care, monitoring, and recovery for patients after cardiac surgery.\",\n  \"imageOne\": \"patient, diagnosis, test, assessment, preparation\",\n  \"imageTwo\": \"operating room, setup\",\n  \"imageThree\": \"cardiac surgery, heart surgery\",\n  \"imageFour\": \"monitoring, recovery, post-surgery\"\n}\n\n{\n  \"title\": \"Butterfly Life Cycle\",\n  \"subtitle\": \"Egg to Butterfly\",\n  \"caption\": \"Nature's Transformation\",\n  \"captionImage\": \"Butterfly, Butterfly Ecosystem, Butterfly wildlife\",\n  \"textOne\": \"Egg Stage: Butterfly eggs are typically laid on leaves or stems near food sources.\",\n  \"textTwo\": \"Larva (Caterpillar) Stage: Caterpillars hatch from eggs and consume plant leaves.\",\n  \"textThree\": \"Pupa (Chrysalis) Stage: Caterpillars form chrysalides and undergo metamorphosis inside.\",\n  \"textFour\": \"Adult Butterfly Stage: The fully transformed butterfly emerges from the chrysalis.\",\n  \"imageOne\": \"butterfly egg, egg\",\n  \"imageTwo\": \"caterpillar, larva\",\n  \"imageThree\": \"pupa, chrysalis\",\n  \"imageFour\": \"adult butterfly, Lepidoptera, imago\"\n,\n\”conclusion\”: \"It gives conclusion based on the research context.  It should be strictly less than 182 characters\"}\n\nNOTE: Strictly adhere to the guidelines mentioned in the JSON and understand the template description thoroughly. Do not add any filler text or preambles and return the output in JSON for the provided scientific research context."
# },
#     "Template-4":  {
#     "role": "system",
#     "content": "You are a helpful assistant created by MTG. Your role is to create a JSON structure for the \"Comparative Infographic\" template based on the scientific research context provided to you to help MTG generate a graphical abstract. The description and JSON structure of \"Comparative Infographic\" is as follows:\n\nDescription: The template is vertically divided into two main sections. The left section contains a large image placeholder, representing the primary focus or subject. Below this image, there's a bubble text placeholder, which can be used for a brief caption or highlight. The right section is further divided into two subsections, each containing a square image placeholder with a title in a black background and a detailed explanation below. The titles in the black background are in larger font sizes compared to the detailed explanations, emphasizing their significance.\n\nJSON_structure:\n{\n  \"bubbleText\": \"Text highlighting some aspect or giving a short explanation of `largeImage`. It could be the name of the research topic. It is associated with `largeImage`. It should be no more than 20 characters.\",\n  \"textOne\": \"Text supporting `imageTextOne`, probably explaining the intervention or the process happening on 'experimental group 1', the 'first comparison' or 'Finding 1' in an infographic that shows 2 scientific findings. It should have max 70 characters.\",\n  \"textTwo\": \"Text supporting `imageTextTwo`, probably explaining the intervention or the process happening on 'experimental group 2', the 'second comparison' or 'Finding 2' in an infographic that shows 2 scientific findings. It should have max 70 characters.\",\n  \"largeImage\": \"Name of image that represents the main topic of the scientific study, providing context or showing the intervention, or the subjects of the study. It's directly associate to `bubbleText`.\",\n  \"imageTextOne\": \"Name of image that represents the 'experimental group 1' or the 'first comparison', could also be the 'Finding 1' in an infographic that shows 2 scientific findings. It's directly associated to `textOne`\",\n  \"imageTextTwo\": \"Name of image that represents the 'experimental group 2' or the 'second comparison', could also be the 'Finding 2' in an infographic that shows 2 scientific findings. It's directly associated to textTwo\"\n}\n\nRefer the following example for your reference:\nEXAMPLE:\n{\"bubbleText\": \"Morphology of butterflies\",\n\"textOne\": \"Orange wings with black veins and long-distance migrations.\",\n\"textTwo\": \"Renowned for its dazzling iridescent blue wings\",\n\"largeImage\": \"Skeleton\",\n\"imageTextOne\": \"Monarch Butterfly\",\n\"imageTextTwo\": \"Blue Morpho Butterfly\",\n\”conclusion\”: \"It gives conclusion based on the research context.  It should be strictly less than 182 characters\"}\n\n\nNOTE: Strictly adhere to the guidelines mentioned in the JSON and understand the template description thoroughly. Do not add any filler text or preambles and return the output in JSON for the provided scientific research context.\n\n\n"
# }})
if __name__ == '__main__':
    app.run(host="0.0.0.0", port=8080, debug=True)
