from flask import Blueprint, request, jsonify
import requests
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Define the Blueprint
app2_blueprint = Blueprint('app2', __name__)

UMLS_API_KEY = 'fa49cc0a-d8a6-43c9-a5e2-3610dacbf8fd'
TGT_URL = 'https://utslogin.nlm.nih.gov/cas/v1/api-key'
SERVICE_URL = 'http://umlsks.nlm.nih.gov'

# Function to get TGT
def get_tgt():
    response = requests.post(TGT_URL, data={'apikey': UMLS_API_KEY})
    if response.status_code == 201:
        return response.headers['location']
    logger.error(f"Failed to obtain TGT. Response: {response.text}")
    raise Exception("Failed to obtain TGT")

# Function to get a single-use ticket
def get_ticket(tgt_url):
    response = requests.post(tgt_url, data={'service': SERVICE_URL})
    if response.status_code == 200:
        return response.text
    logger.error(f"Failed to obtain Service Ticket. Response: {response.text}")
    raise Exception("Failed to obtain Service Ticket")

# Function to query atoms for a given CUI
def query_atoms(cui, sab, ticket):
    atoms_url = f"https://uts-ws.nlm.nih.gov/rest/content/current/CUI/{cui}/atoms"
    params = {'ticket': ticket, 'sabs': sab}
    response = requests.get(atoms_url, params=params, headers={'Accept': 'application/json'})

    if response.status_code != 200:
        logger.error(f"Failed to query atoms for CUI {cui}. Response: {response.text}")
        return []

    try:
        data = response.json().get('result', [])
        codes = [atom['code'].split('/')[-1] for atom in data if atom.get('rootSource') == sab]
        return codes
    except Exception as e:
        logger.error(f"Error parsing response for CUI {cui}: {e}")
        return []

# Function to expand ICD ranges
def expand_range(code_range):
    expanded_codes = []

    if '-' in code_range:
        start, end = code_range.split('-')
        if start[:-1] == end[:-1]:  # Same prefix, numeric range
            prefix = start[:-1]
            start_num = int(start[-1:])
            end_num = int(end[-1:])
            expanded_codes = [f"{prefix}{i}" for i in range(start_num, end_num + 1)]
        else:
            expanded_codes.append(start)
            expanded_codes.append(end)
    else:
        expanded_codes.append(code_range.split('.')[0])  # Strip decimals for higher-order code

    return expanded_codes

@app2_blueprint.route('/snomed/map', methods=['POST'])
def snomed_to_icd():
    try:
        selected_ids = request.json.get('selected_ids', [])
        tgt_url = get_tgt()
        ticket = get_ticket(tgt_url)

        all_icd_codes = []
        for snomed_id in selected_ids:
            icd10cm_codes = query_atoms(snomed_id, 'ICD10CM', ticket)
            icd10_codes = query_atoms(snomed_id, 'ICD10', ticket)

            combined_codes = set(icd10cm_codes + icd10_codes)
            for code in combined_codes:
                expanded_codes = expand_range(code)
                all_icd_codes.extend(expanded_codes)

        unique_codes = sorted(set(all_icd_codes))
        logger.info(f"Retrieved ICD-10 codes: {unique_codes}")
        return jsonify({'icd_codes': unique_codes})

    except Exception as e:
        logger.error(f"Error in snomed_to_icd: {str(e)}")
        return jsonify({'error': 'Internal Server Error'}), 500
