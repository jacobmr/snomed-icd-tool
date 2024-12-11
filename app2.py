from flask import Blueprint, request, jsonify, send_file, session
import requests
import pandas as pd
import os

# Define the blueprint
app2_blueprint = Blueprint('app2', __name__)

# Environment variables
UMLS_API_KEY = os.getenv("UMLS_API_KEY", "default-key")  # Use a default for local testing

# Helper functions for UMLS API
def get_tgt():
    url = 'https://utslogin.nlm.nih.gov/cas/v1/api-key'
    response = requests.post(url, data={'apikey': UMLS_API_KEY})
    if response.status_code == 201:
        return response.headers['location']
    raise Exception("Failed to obtain TGT")

def get_ticket(tgt_url):
    response = requests.post(tgt_url, data={'service': 'http://umlsks.nlm.nih.gov'})
    if response.status_code == 200:
        return response.text
    raise Exception("Failed to obtain ticket")

# Routes
@app2_blueprint.route('/snomed/search', methods=['POST'])
def snomed_search():
    try:
        term = request.json.get('term')
        if not term:
            return jsonify({'error': 'Search term is required'}), 400

        tgt_url = get_tgt()
        ticket = get_ticket(tgt_url)

        url = "https://uts-ws.nlm.nih.gov/rest/search/current"
        params = {'string': term, 'ticket': ticket, 'sabs': 'SNOMEDCT_US', 'searchType': 'words'}
        response = requests.get(url, params=params)

        if response.status_code != 200:
            return jsonify({'error': 'Search failed'}), 500

        results = response.json().get('result', {}).get('results', [])
        output = [{'name': item['name'], 'ui': item['ui']} for item in results]

        return jsonify(output)
    except Exception as e:
        return jsonify({'error': f"Internal Server Error: {str(e)}"}), 500

@app2_blueprint.route('/snomed/map', methods=['POST'])
def snomed_to_icd():
    try:
        payload = request.json
        selected_terms = payload.get('selected_terms', [])
        if not selected_terms:
            return jsonify({"error": "No terms provided"}), 400

        tgt_url = get_tgt()
        ticket = get_ticket(tgt_url)
        results = []

        for term in selected_terms:
            snomed_id = term['ui']
            snomed_name = term.get('name', 'N/A')

            # Iterate through all pages of mappings
            page = 1
            all_icd_codes = []
            while True:
                url = f"https://uts-ws.nlm.nih.gov/rest/content/current/CUI/{snomed_id}/atoms"
                params = {'ticket': ticket, 'sabs': 'ICD10CM', 'pageNumber': page}
                response = requests.get(url, params=params)

                if response.status_code != 200:
                    results.append({
                        'snomed_id': snomed_id,
                        'snomed_name': snomed_name,
                        'error': 'Failed to retrieve mappings'
                    })
                    break

                data = response.json().get('result', [])
                if not data:
                    break

                # Extract ICD-10 codes
                icd_codes = [
                    {
                        'code': atom.get('code', '').split('/')[-1],
                        'description': atom.get('name', 'N/A')
                    }
                    for atom in data if 'code' in atom
                ]
                all_icd_codes.extend(icd_codes)

                # Check if there's another page
                if len(data) < 25:  # Assuming 25 results per page
                    break
                page += 1

            results.append({
                'snomed_id': snomed_id,
                'snomed_name': snomed_name,
                'icd10': all_icd_codes
            })

        return jsonify(results)
    except Exception as e:
        return jsonify({'error': f"Internal Server Error: {str(e)}"}), 500

@app2_blueprint.route('/snomed/value-set', methods=['POST'])
def generate_value_set():
    try:
        payload = request.json
        search_term = payload.get('term', 'unknown')
        icd10_codes = payload.get('icd10_codes', [])

        if not icd10_codes:
            return jsonify({'error': 'No ICD-10 codes provided'}), 400

        # Save the file in a persistent directory
        file_dir = "/home/jacobr/vsac/"
        file_name = f"{search_term.replace(' ', '_')}_valueset.xlsx"
        file_path = os.path.join(file_dir, file_name)

        df = pd.DataFrame([{'Search Term': search_term, 'ICD-10 Codes': ', '.join(icd10_codes)}])
        df.to_excel(file_path, index=False)

        session['last_generated_file'] = file_name

        return jsonify({'message': 'File generated successfully'}), 200
    except Exception as e:
        return jsonify({'error': f"Internal Server Error: {str(e)}"}), 500

@app2_blueprint.route('/snomed/download', methods=['GET'])
def download_last_file():
    try:
        file_name = session.get('last_generated_file')
        if not file_name:
            return jsonify({'error': 'No file available for download'}), 400

        file_path = os.path.join("/home/jacobr/vsac/", file_name)
        if os.path.exists(file_path):
            return send_file(file_path, as_attachment=True, download_name=file_name)
        else:
            return jsonify({'error': 'File not found'}), 404
    except Exception as e:
        return jsonify({'error': f"Internal Server Error: {str(e)}"}), 500

@app2_blueprint.route('/vsac/<filename>', methods=['GET'])
def download_file(filename):
    try:
        file_path = os.path.join("/home/jacobr/vsac/", filename)
        if os.path.exists(file_path):
            return send_file(file_path, as_attachment=True, download_name=filename)
        else:
            return jsonify({'error': 'File not found'}), 404
    except Exception as e:
        return jsonify({'error': f"Internal Server Error: {str(e)}"}), 500