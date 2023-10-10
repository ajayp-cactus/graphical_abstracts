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
import vertexai
from vertexai.language_models import ChatModel, InputOutputTextPair
import tiktoken
import redis

#GPT
with open("./credentials/gcp_credentials.json") as f:
    gcp_creds = json.load(f)
openai.api_key = gcp_creds['api_key']

r = redis.Redis(
  host='eu2-workable-halibut-30662.upstash.io',
  port=30662,
  password=gcp_creds['redis_password']
)

#--------Initialise
logger = logging.getLogger()
logger.setLevel(logging.INFO)

encoding = tiktoken.encoding_for_model("gpt-4")
#----Infographic and type mapping
infograph_templates = r.json().get("Template","$")[0]
# print(infograph_templates)

#GCP Vertext AI
vertexai.init(project="cactus-agnis-workshop-5483", location="us-central1")


@backoff.on_exception(backoff.expo,
                      requests.exceptions.Timeout,
                      max_time=600,
                      max_tries=1)
#-------------


def _log(status, error=None, resource_info=None):
    print(json.dumps({
        "status": status,
        "timetsamp": str(datetime.now()),
        "error": error,
        "resource_info": resource_info
    }))

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
    api_base_url = "nv-alb-titan-prod-1415563017.us-east-1.elb.amazonaws.com:80"
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
            time.sleep(2)
            continue
        elif "status_job" == "failed":
            raise Exception(f"Titan extraction failed: {resp}")
        else:
            url = resp['data']['url']
            save_path = download_json_from_url(url, titan_output_dir)
        break
    return save_path
    
def get_research_text(text_file_path):
    #------------Prompt Creation
    prompt = ''
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
    token_count = len(encoding.encode(prompt))
    print(f"****************Token count:{token_count}********")
    if token_count > 7000:
        decrease_by = token_count - 7000
        prompt = prompt[:decrease_by]
    return prompt

def gpt_first_prompt_msg_generation(research_text):
    msg = [{
        "role": "system",
        "content": "You are a helpful assistant created by MTG. Your role is to suggest infographics templates, based on the research paper context provided to you. There are four types of templates you can choose from. The description of templates is as follows:\n\n[Template-1]\nName - Comparative Infographics\nDescription - The infographic template is designed for comparing up to three groups or stages. It has a clear left-to-right flow, making it suitable for presenting processes or sequences. The three main sections are vertically aligned, each containing placeholders for images, subtitles, and detailed text.\nUses - \n1) Before and after comparisons\n2) Baseline versus post-treatment\n3) Pre-treatment versus post-treatment\nKeywords - The following keywords can help you identify this template:\n1. Comparative Study\n2. Controlled Experiment\n3. Cross-sectional Study\n4. Cohort Study\n5. Randomized Controlled Trial\n\n[Template-2]\nName - Comparative Infographics\nDescription - This template is designed to compare three distinct groups or items. The vertical alignment of the elements suggests a top-to-bottom reading flow. Each group is represented by an image, a title (or subtitle), and a detailed explanation. The template is ideal for comparing three different scenarios, stages, or items in a scientific context.\nUses - \n1) Before and after comparisons\n2) Baseline versus post-treatment\n3) Pre-treatment versus post-treatment\nKeywords - The following keywords can help you identify this template:\n1. Comparative Study\n2. Controlled Experiment\n3. Cross-sectional Study\n4. Cohort Study\n5. Randomized Controlled Trial\n\n\n[Template-3]\nName - Sequential Infographics\nDescription - This template is designed to showcase a sequence or progression of four steps or stages. The horizontal alignment and the arrows connecting each section suggest a left-to-right reading flow. Each stage is represented by an image, a title (or subtitle), and a detailed explanation. The template is ideal for illustrating a process, timeline, or sequence of events in a scientific context.\nUses - \n1) stage development\n2) treatment process\nKeywords - The following keywords can help you identify this template:\n1. Longitudinal Study\n2. Case Study\n3. Process Analysis\n4. Time-Series Study\n5. Developmental Study\n\n[Template-4]\nName - Comparative Infographics\nDescription - This template is designed for a side-by-side comparison of two main elements or groups. The vertical division suggests two distinct but related sections. Each section has an image, a title, and a detailed explanation. The template is ideal for illustrating contrasts, comparisons, or two related concepts in a scientific context.\nKeywords - The following keywords can help you identify this template:\n1. Longitudinal Study\n2. Case Study\n3. Process Analysis\n4. Time-Series Study\n5. Developmental Study\n\nNOTE: Return only the type of template i.e. Template-1, Template-2, Template-3, or Template-4 without any filler text or preambles in titlecase format."
        },
        {
        "role": "user",
        "content": f"Research_context:\n{research_text}\n\nOutput: "
        }
    ]
    return msg

def gcp_first_prompt_msg_generation(research_text):
    context = "You are a helpful assistant created by MTG. Your role is to suggest infographics templates, based on the research paper context provided to you. There are four types of templates you can choose from. The description of templates is as follows:\n\n[Template-1]\nName - Comparative Infographics\nDescription - The infographic template is designed for comparing up to three groups or stages. It has a clear left-to-right flow, making it suitable for presenting processes or sequences. The three main sections are vertically aligned, each containing placeholders for images, subtitles, and detailed text.\nUses - \n1) Before and after comparisons\n2) Baseline versus post-treatment\n3) Pre-treatment versus post-treatment\nKeywords - The following keywords can help you identify this template:\n1. Comparative Study\n2. Controlled Experiment\n3. Cross-sectional Study\n4. Cohort Study\n5. Randomized Controlled Trial\n\n[Template-2]\nName - Comparative Infographics\nDescription - This template is designed to compare three distinct groups or items. The vertical alignment of the elements suggests a top-to-bottom reading flow. Each group is represented by an image, a title (or subtitle), and a detailed explanation. The template is ideal for comparing three different scenarios, stages, or items in a scientific context.\nUses - \n1) Before and after comparisons\n2) Baseline versus post-treatment\n3) Pre-treatment versus post-treatment\nKeywords - The following keywords can help you identify this template:\n1. Comparative Study\n2. Controlled Experiment\n3. Cross-sectional Study\n4. Cohort Study\n5. Randomized Controlled Trial\n\n\n[Template-3]\nName - Sequential Infographics\nDescription - This template is designed to showcase a sequence or progression of four steps or stages. The horizontal alignment and the arrows connecting each section suggest a left-to-right reading flow. Each stage is represented by an image, a title (or subtitle), and a detailed explanation. The template is ideal for illustrating a process, timeline, or sequence of events in a scientific context.\nUses - \n1) stage development\n2) treatment process\nKeywords - The following keywords can help you identify this template:\n1. Longitudinal Study\n2. Case Study\n3. Process Analysis\n4. Time-Series Study\n5. Developmental Study\n\n[Template-4]\nName - Comparative Infographics\nDescription - This template is designed for a side-by-side comparison of two main elements or groups. The vertical division suggests two distinct but related sections. Each section has an image, a title, and a detailed explanation. The template is ideal for illustrating contrasts, comparisons, or two related concepts in a scientific context.\nKeywords - The following keywords can help you identify this template:\n1. Longitudinal Study\n2. Case Study\n3. Process Analysis\n4. Time-Series Study\n5. Developmental Study\n\nNOTE: Return only the type of template i.e. Template-1, Template-2, Template-3, or Template-4 without any filler text or preambles in titlecase format."
    message = f"Research context:\n{research_text}\n\nOutput:"
    return context, message

def gpt_second_prompt_generation(infograph, reserach_text):
    messages=[
        infograph_templates[infograph]
    ,
    {
      "role": "user",
      "content": f"Research_context:\n{reserach_text}\n\n\nOutput: "
    }
  ]
    return messages

def gcp_second_prompt_generation(infograph, reserach_text):
    context = infograph_templates[infograph]['content']
    message = f"Research context:\n{reserach_text}\n\nOutput:"
    return context, message

def generate_text_gpt(messages, max_length=800, temparature=0.5):
    response = openai.ChatCompletion.create(model="gpt-4", messages=messages, max_tokens=max_length, temperature=temparature)
    return response

def generate_text_gcp(prompt, context, max_length=200, temparature=0):
    parameters = {
    "max_output_tokens": max_length,
    "temperature": temparature,
    "top_p": 0.8,
    "top_k": 40
}
    chat_model = ChatModel.from_pretrained("chat-bison")
    chat = chat_model.start_chat(context=context)
    response = chat.send_message(prompt, **parameters)
    return (response.text.strip())

def pdf_processor(file_loc, model_type):
    try:
        titan_output_dir = "./data/"
        _log(status="START", resource_info="Titan")
        try:
            titan_op_path = titan_pdf_to_text(file_loc, titan_output_dir)
        except Exception as e:
            raise Exception(f"Titan Failure: {e}")
        _log(status="START", resource_info="Titan")
        research_text = get_research_text(titan_op_path)

        if model_type == "gpt":
            prompt = gpt_first_prompt_msg_generation(research_text)
            _log(status="START", resource_info="PROMPT 1 AI GENERATOR")
            #ToDo: Get type of infograph
            try:
                prompt_1_op = generate_text_gpt(prompt, max_length=86).choices[0]['message']
            except Exception as e:
                raise Exception(f"GPT Failure: {e}")
            infograph = prompt_1_op['content']

            prompt2 = gpt_second_prompt_generation(infograph=infograph, reserach_text=research_text)
            _log(status="START", resource_info="PROMPT 2 AI GENERATOR")
            try:
                prompt_2_op = generate_text_gpt(prompt2, max_length=426).choices[0]['message']['content']
            except Exception as e:
                raise Exception(f"GPT Failure: {e}")
            print(prompt_2_op)
        elif model_type == 'gcp':
            context, prompt = gcp_first_prompt_msg_generation(research_text)
            _log(status="START", resource_info="PROMPT 1 AI GENERATOR")
            #ToDo: Get type of infograph
            try:
                prompt_1_op = generate_text_gcp(prompt=prompt, context=context, max_length=86)
            except Exception as e:
                raise Exception(f"GPT Failure: {e}")
            
            infograph = prompt_1_op
            print(f"****GCP Prompt 1: {infograph}")
            context2, prompt2 = gcp_second_prompt_generation(infograph=infograph, reserach_text=research_text)
            _log(status="START", resource_info="PROMPT 2 AI GENERATOR")
            try:
                prompt_2_op = generate_text_gcp(prompt=prompt2, context=context2, max_length=426)
            except Exception as e:
                raise Exception(f"GPT Failure: {e}")
            print(prompt_2_op)

        explainable_json = json.loads(prompt_2_op)
        explainable_json.update({'inforgraphics': infograph})
        return(explainable_json)
    except Exception as e:
        raise Exception (f'''PDF Processing failed: {e}''')
