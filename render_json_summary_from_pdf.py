import requests
import json
import os
from urllib.parse import urlparse, parse_qs
import time
import openai
import backoff
import logging
from datetime import datetime
import random

#--------Initialise
logger = logging.getLogger()
logger.setLevel(logging.INFO)

#----Infographic and type mapping
infograph_templates = {
    1: {
           1: {
                "title": "provide a title based on summary of the paper - should be less than 10 words",
                "imageOne": "provide an image description suitable for step 1",
                "textOne": "provide an key point suitable suitable for step 1",
                "imageTwo": "provide an image description suitable for step 2",
                "textTwo": "provide an key point suitable suitable for step 2",
                "imageThree": "provide an image description suitable for step 3",
                "textThree": "provide an key point for step 3"
           }, 
           2: {
                "title": "provide a title based on summary of the paper - should be less than 10 words",
                "subtitle": "provide a sub-title based on summary of the paper - should be less than 6 words",
                "caption": "provide key point suitable for the step 1 and image 1",
                "captionImage": "provide an image description that is suitable for the overall study and is step 1 of the process",
                "imageOne": "provide an image description suitable for first route from step 1",
                "textOne": "provide an key point suitable suitable for first route from step 1",
                "imageTwo": "provide an image description suitable for second route from step 1",
                "textTwo": "provide an key point suitable suitable for second route from step 1",
                "imageThree": "provide an image description suitable for imageOne last step",
                "textThree": "provide an key point for textOne last step",
                "imageFour": "provide an image description suitable for imageTwo last step",
                "textFour": "provide an key point for textTwo last step"
           }
        },
    2: {
        1: {
                "title": "provide a title based on summary of the paper - should be less than 10 words",
                "image_1_description": "provide an image description that is suitable for the overall study",
                "image_1_keywords": [],
                "image_1_title": "provide key point suitable for the paper and image 1",
                "image_2_description": "provide an image description for first comparison",
                "image_2_keywords": [],
                "image_2_title": "provide key point suitable for first comparison and image 2",
                "image_3_description": "provide an image description for second comparison",
                "image_3_keywords": [],
                "image_3_title": "provide key point suitable for second comparison and image 3",
                "conclusion" : "result of the study in less than 10/12 words"
            },
         2: {
                "title": "provide a title based on summary of the paper - should be less than 10 words",
                "image_1_description": "provide an image description that is suitable for the overall study",
                "image_1_keywords": [],
                "image_1_title": "provide key point suitable for the paper and image 1",
                "image_2_description": "provide an image description for first comparison",
                "image_2_keywords": [],
                "image_2_title": "provide key point suitable for first comparison and image 2",
                "image_3_description": "provide an image description for second comparison",
                "image_3_keywords": [],
                "image_3_title": "provide key point suitable for second comparison and image 3",
                "image_4_description": "provide an image description for second comparison",
                "image_4_keywords": [],
                "image_4_title": "provide key point suitable for second comparison and image 3",
                "conclusion" : "result of the study in less than 10/12 words"
            }
    },
    3: {
        1: {
                "title": "provide a title based on summary of the paper - should be less than 10 words",
                "imageOne": "provide an image description suitable for step 1",
                "textOne": "provide an key point suitable suitable for step 1",
                "imageTwo": "provide an image description suitable for step 2",
                "textTwo": "provide an key point suitable suitable for step 2",
                "imageThree": "provide an image description suitable for step 3",
                "textThree": "provide an key point for step 3"
           }},
    4: {
        1: {
                "title": "provide a title based on summary of the paper - should be less than 10 words",
                "imageOne": "provide an image description suitable for step 1",
                "textOne": "provide an key point suitable suitable for step 1",
                "imageTwo": "provide an image description suitable for step 2",
                "textTwo": "provide an key point suitable suitable for step 2",
                "imageThree": "provide an image description suitable for step 3",
                "textThree": "provide an key point for step 3"
           }},

    5: {
        1: {
                "title": "provide a title based on summary of the paper - should be less than 10 words",
                "imageOne": "provide an image description suitable for step 1",
                "textOne": "provide an key point suitable suitable for step 1",
                "imageTwo": "provide an image description suitable for step 2",
                "textTwo": "provide an key point suitable suitable for step 2",
                "imageThree": "provide an image description suitable for step 3",
                "textThree": "provide an key point for step 3"
           }}
}

#GPT
with open("./credentials/gcp_credentials.json") as f:
    gcp_creds = json.load(f)
openai.api_key = gcp_creds['api_key']
@backoff.on_exception(backoff.expo,
                      requests.exceptions.Timeout,
                      max_time=600,
                      max_tries=1)
#-------------


def _log(status, error=None, resource_info=None):
    logger.info(json.dumps({
        "status": status,
        "timetsamp": str(datetime.now()),
        "error": error,
        "resource_info": resource_info
    }))

    if status == 'skipped':
        return {
            "statusCode": 400,
            "body": json.dumps(
                {
                    "message": error,
                }
            ),
        }

def download_json_from_url(url, titan_output_dir, op_filename=None):
    #Download PDF from URL     
    response = requests.get(url)
    if not op_filename:
        parsed_url = urlparse(url)
        query_params = parse_qs(parsed_url.query)
        op_filename = query_params.get('response-content-disposition', [''])[0].split('=')[-1]
    save_path = os.path.join(titan_output_dir, op_filename)
    with open(save_path, 'wb') as file:
        file.write(response.content)
    return save_path

def download_pdf(pdf_url, save_path):
    try:
        user_agents = [
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_6) AppleWebKit/537.36 '
        '(KHTML, like Gecko) Chrome/85.0.4183.83 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_4) AppleWebKit/605.1.15 '
        '(KHTML, like Gecko) Version/12.1 Safari/605.1.15',
        'Mozilla/5.0 (iPad; CPU OS 7_0 like Mac OS X) AppleWebKit/537.51.1 '
        '(KHTML, like Gecko) CriOS/30.0.1599.12 Mobile/11A465 Safari/8536.25 '
        '(3B92C18B-D9DE-4CB7-A02A-22FD2AF17C8F)',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_7_5) AppleWebKit/536.25 '
        '(KHTML, like Gecko) Version/6.0 Safari/536.25',
        'Mozilla/5.0 (compatible; MSIE 10.0; Macintosh; '
        'Intel Mac OS X 10_7_3; Trident/6.0)',
        'Mozilla/5.0 (Windows; U; MSIE 9.0; Windows NT 9.0; en-US)']
        headers={
                'user-agent': random.choice(user_agents),
                'accept': 'text/html,application/xhtml+xml,'
                          'application/xml;q=0.9,image/webp,'
                          'image/apng,*/*;q=0.8,'
                          'application/signed-exchange;v=b3;q=0.9',
                'accept-language': 'en-US,en;q=0.9'}
        response = requests.get(pdf_url, headers=headers)
        if response.status_code == 200:
            with open(save_path, "wb") as f:
                f.write(response.content)
        else:
            raise Exception("PDF cannot be downloaded, status code:"+response.status_code)
    except Exception as e:
        raise Exception(f'An error occurred: {str(e)}')
    
def titan_pdf_to_text(file_loc, titan_output_dir):
    #-----------------Titan PDF to Full-Text
    api_base_url = "nv-alb-titan-test-107111713.us-east-1.elb.amazonaws.com:80"
    url = f"http://{api_base_url}/api/v1/submit"

    payload = {'job_config': '{"extract": true, "doc_class":false, "fos":false}',
    'metadata': '{}'}
    files=[ ('file',(file_loc.split("/")[-1],open(file_loc,'rb'),'application/pdf'))]
    headers = {
    'Authorization': 'Bearer ABC123_LOCAL'
    }

    #Submit to Titan
    response = requests.request("POST", url, headers=headers, data=payload, files=files)

    #Fetch status from Titan and download output
    print(json.loads(response.text))
    job_request_id = json.loads(response.text)['request_id']
    url = f"http://{api_base_url}/api/v1/fetch?request_id={job_request_id}"
    payload = {}
    while True:
        response_fetch = requests.request("GET", url, headers=headers, data=payload)
        resp = json.loads(response_fetch.text)
        print(resp)
        if resp['status_job'] == "in_progress":
            time.sleep(50)
            continue
        elif "status_job" == "failed":
            raise Exception(f"Titan extraction failed: {resp}")
        else:
            url = resp['data']['url']
            save_path = download_json_from_url(url, titan_output_dir)
        break
    return save_path
    
def first_prompt_from_txt_file(text_file_path):
    #------------Prompt Creation
    prompt = f'For the research article - \n"'

    with open(text_file_path) as f:
        data = json.load(f)

    sections_data = {}
    for section in data['article_sections']:
        if section.get('section') in sections_data.keys():
            sections_data[section['section']].append(section['text'])
        else:
            sections_data[section['section']] = [section['text']]
    for x,y in sections_data.items():
        if not ("author contrib" in x.lower() and "supplementary" in x.lower()):
            y = " ".join(y)
            prompt += x+"\n"+y+"\n"
    if data.get('figure_legends') or data.get('table_captions'):
        prompt += "\n Figure/Table Captions \n"
        for figure in data['figure_legends']:
            prompt += figure.get('text')+ "\n"
        for table in data['table_captions']:
            prompt += table.get('text')+ "\n"
    prompt += '''" \n Considering the following classification of infographics and their respective type (if available), which one is the more suitable to describe this paper?
    1. **Listicle Infographics**: 
    - **Types**
            - 1. For 3 steps
            - 2. For 3 steps, where first step has two routes
    2. **Comparative Infographics**:
    - **Types**
            - 1. For 2 groups comparison
            - 2. For 3 groups comparison
    3. **Informational Infographics**:
    4. **Geographical & Map Infographics**:
    5. **Timeline Infographics**:

    Just give number of the infographic and it's type number in the following format
    infographic: <number>
    type: <number>'''

    return prompt

def second_prompt_generation(infograph, infograph_type=1):
    prompt = f'''Provide a summary of the paper that will fit in "Comparative Infographics" style with 2 group comparisons. 
                Every image description should be very specific about what the image is and it should not have more than 2 elements
                Every image keyword should provide with a set of 4/5 words that can help us find image through keywords
                Every image title should be of less than 10/12 words.
                Note: If stats are required in an image then please mention the stats/numbers in the image description

                Reply in the following format considering the rules mentioned above. 
                {json.dumps(infograph_templates[infograph][infograph_type])}
                '''
    return prompt


def generate_text(messages, max_length=800, temparature=0.5):
    response = openai.ChatCompletion.create(model="gpt-4", messages=messages, max_tokens=max_length, temperature=temparature)
    return response

def pdf_processor(file_loc):
    try:
        titan_output_dir = "./data/"
        _log(status="START", resource_info="Titan")
        try:
            titan_op_path = titan_pdf_to_text(file_loc, titan_output_dir)
        except Exception as e:
            raise Exception(f"Titan Failure: {e}")
        #GPT 
        prompt = [{"role": "user", "content": first_prompt_from_txt_file(titan_op_path)}]
        _log(status="START", resource_info="PROMPT 1 AI GENERATOR")
        #ToDo: Get type of infograph
        try:
            prompt_1_op = generate_text(prompt).choices[0]['message']
        except Exception as e:
            raise Exception(f"GPT Failure: {e}")
        print(prompt_1_op)
        prompt.append(prompt_1_op)
        infograph = int(prompt_1_op['content'].split("\n")[0].strip().split(":")[-1])
        type_p = prompt_1_op['content'].split("\n")[-1].strip().split(":")
        if len(type_p)>1:
            info_type = int(type_p[-1])
        else:
            info_type = 1
        _log(status="START", resource_info="PROMPT 2 AI GENERATOR")
        prompt.append({"role": "user", 
                                    "content": second_prompt_generation(infograph=infograph, infograph_type=info_type)})
        print(prompt)
        try:
            prompt_2_op = generate_text(prompt).choices[0]['message']['content']
        except Exception as e:
            raise Exception(f"GPT Failure: {e}")
        print(prompt_2_op)
        explainable_json = json.loads(prompt_2_op)
        explainable_json.update({'inforgraphics': infograph})
        return(explainable_json)
    except Exception as e:
        raise Exception (f'''PDF Processing failed: {e}''')


