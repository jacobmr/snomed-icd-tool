from flask import Blueprint, request, jsonify
import requests

# Define the Blueprint
app2_blueprint = Blueprint('app2', __name__)

UMLS_API_KEY = 'fa49cc0a-d8a6-43c9-a5e2-3610dacbf8fd'

# Function to get TGT
def get_tgt():
    url = 'https://utslogin.nlm.nih.gov/cas/v1/api-key'
    response = requests.post(url, data={'apikey': UMLS_API_KEY})
    if response.status_code == 201:
        return response.headers['location']
    raise Exception("Failed to obtain TGT")

# Function to get a single-use ticket
def get_ticket(tgt_url):
    response = requests.post(tgt_url, data={'service': 'http://umlsks.nlm.nih.gov'})
    if response.status_code == 200:
        return response.text
    raise Exception("Failed to obtain ticket")

@app2_blueprint.route('/snomed/search', methods=['POST'])
def snomed_search():
    try:
        term = request.json.get('term')
        print(f"Received term: {term}")  # Debug: Log the input

        tgt_url = get_tgt()
        ticket = get_ticket(tgt_url)
        print(f"Generated ticket: {ticket}")  # Debug: Log the ticket

        url = "https://uts-ws.nlm.nih.gov/rest/search/current"
        params = {
            'string': term,
            'ticket': ticket,
            'sabs': 'SNOMEDCT_US',
            'searchType': 'words'
        }
        response = requests.get(url, params=params)
        print(f"UMLS API Response: {response.status_code}")  # Debug: Log response code

        if response.status_code != 200:
            return jsonify({'error': 'Search failed'}), 500

        results = response.json().get('result', {}).get('results', [])
        output = [{'name': item['name'], 'ui': item['ui']} for item in results]
        print(f"Search results: {output}")  # Debug: Log the output
        return jsonify(output)
    except Exception as e:
        print(f"Error in snomed_search: {str(e)}")
        return jsonify({'error': 'Internal Server Error'}), 500

# ICD mapping route
@app2_blueprint.route('/snomed/map', methods=['POST'])
def snomed_to_icd():
    selected_ids = request.json.get('selected_ids', [])
    tgt_url = get_tgt()
    ticket = get_ticket(tgt_url)
    results = []

    for snomed_id in selected_ids:
        url = f"https://uts-ws.nlm.nih.gov/rest/content/current/CUI/{snomed_id}/atoms"
        params = {'ticket': ticket, 'sabs': 'ICD10CM'}
        response = requests.get(url, params=params)
        if response.status_code == 200:
            data = response.json().get('result', [])
            icd_codes = [atom['code'] for atom in data if 'code' in atom]
            results.append({'snomed_id': snomed_id, 'icd10': icd_codes})
        else:
            results.append({'snomed_id': snomed_id, 'icd10': []})

    return jsonify(results)