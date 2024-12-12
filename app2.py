from flask import Blueprint, request, jsonify, send_file, session
import requests
import pandas as pd
import os

# Define the blueprint
app2_blueprint = Blueprint('app2', __name__)

# Environment variables
UMLS_API_KEY = os.getenv("UMLS_API_KEY", "fa49cc0a-d8a6-43c9-a5e2-3610dacbf8fd")  # Default key for local testing

# Helper functions for UMLS API
def get_tgt():
    """Obtain Ticket-Granting Ticket (TGT)"""
    url = "https://utslogin.nlm.nih.gov/cas/v1/api-key"
    response = requests.post(url, data={"apikey": UMLS_API_KEY})
    if response.status_code == 201:
        return response.headers["location"]
    raise Exception("Failed to obtain TGT")

def get_ticket(tgt_url):
    """Obtain a Service Ticket (ST)"""
    response = requests.post(tgt_url, data={"service": "http://umlsks.nlm.nih.gov"})
    if response.status_code == 200:
        return response.text
    raise Exception("Failed to obtain ticket")

# Routes
@app2_blueprint.route('/snomed/search', methods=['POST'])
def snomed_search():
    """Search SNOMED CT Terms for Disorders Only"""
    try:
        term = request.json.get("term")
        if not term:
            return jsonify({"error": "Search term is required"}), 400

        tgt_url = get_tgt()

        # Step 1: Perform the search
        ticket = get_ticket(tgt_url)
        search_url = "https://uts-ws.nlm.nih.gov/rest/search/current"
        params = {
            "string": term,
            "ticket": ticket,
            "sabs": "SNOMEDCT_US",
            "searchType": "words"
        }
        search_response = requests.get(search_url, params=params)
        if search_response.status_code != 200:
            return jsonify({"error": "Failed to search SNOMED CT terms"}), 500

        # Step 2: Extract CUIs for SNOMED CT
        results = search_response.json().get("result", {}).get("results", [])
        snomed_cuis = [
            result.get("ui") for result in results if result.get("rootSource") == "SNOMEDCT_US"
        ]

        if not snomed_cuis:
            return jsonify({"message": "No SNOMED CT disorders found"}), 404

        # Step 3: Retrieve disorders mapped to ICD-10
        output = []
        for cui in snomed_cuis:
            print(f"Retrieving SNOMED CT terms for CUI: {cui}")
            ticket = get_ticket(tgt_url)  # Fetch a fresh ticket
            atoms_url = f"https://uts-ws.nlm.nih.gov/rest/content/current/CUI/{cui}/atoms"
            atoms_params = {"ticket": ticket, "sabs": "SNOMEDCT_US"}
            atoms_response = requests.get(atoms_url, params=atoms_params)
            if atoms_response.status_code != 200:
                print(f"Failed to retrieve atoms for CUI {cui}. Status: {atoms_response.status_code}, Response: {atoms_response.text}")
                continue

            # Filter atoms for disorders and ICD-10 mappable terms
            atoms = atoms_response.json().get("result", [])
            for atom in atoms:
                if atom.get("rootSource") == "SNOMEDCT_US" and "disorder" in atom.get("name", "").lower():
                    code = atom.get("code", "").split("/")[-1]
                    name = atom.get("name", "")
                    if code and name:
                        output.append({"code": code, "name": name})
                        print(f"Extracted Disorder: Code: {code}, Name: {name}")

        # Step 4: Return the results
        print(f"Response Sent to UX: {output}")
        return jsonify(output)
    except Exception as e:
        return jsonify({"error": f"Internal Server Error: {str(e)}"}), 500


@app2_blueprint.route('/snomed/map', methods=['POST'])
def snomed_to_icd():
    """Map SNOMED CT Codes to ICD-10"""
    try:
        payload = request.json
        selected_terms = payload.get('selected_terms', [])
        if not selected_terms:
            return jsonify({"error": "No terms provided"}), 400

        tgt_url = get_tgt()
        results = []

        for term in selected_terms:
            snomed_code = term.get('code')  # Use 'code' instead of 'ui'
            snomed_name = term.get('name', 'N/A')

            if not snomed_code:
                results.append({
                    "snomed_code": None,
                    "snomed_name": snomed_name,
                    "error": "Invalid SNOMED code"
                })
                continue

            print(f"Mapping SNOMED Code: {snomed_code}, Name: {snomed_name}")

            # Fetch fresh ticket for mapping request
            ticket = get_ticket(tgt_url)
            mapping_url = f"https://uts-ws.nlm.nih.gov/rest/content/current/source/SNOMEDCT_US/{snomed_code}/mappings"
            mapping_params = {"ticket": ticket, "targetSource": "ICD10CM"}
            mapping_response = requests.get(mapping_url, params=mapping_params)

            if mapping_response.status_code != 200:
                print(f"Failed to retrieve mappings for SNOMED Code: {snomed_code}")
                results.append({
                    "snomed_code": snomed_code,
                    "snomed_name": snomed_name,
                    "error": "Failed to retrieve mappings"
                })
                continue

            # Extract ICD-10 mappings
            mappings = mapping_response.json().get('result', [])
            icd10_codes = [
                {"code": mapping.get('targetCode'), "description": mapping.get('targetName')}
                for mapping in mappings if mapping.get('targetCode')
            ]

            results.append({
                "snomed_code": snomed_code,
                "snomed_name": snomed_name,
                "icd10": icd10_codes or []
            })

        return jsonify(results)
    except Exception as e:
        return jsonify({"error": f"Internal Server Error: {str(e)}"}), 500

@app2_blueprint.route('/snomed/value-set', methods=['POST'])
def generate_value_set():
    """Generate an Excel file for SNOMED CT terms and ICD-10 codes"""
    try:
        payload = request.json
        search_term = payload.get("term", "unknown")
        icd10_codes = payload.get("icd10_codes", [])

        if not icd10_codes:
            return jsonify({"error": "No ICD-10 codes provided"}), 400

        # Save the file in a persistent directory
        file_dir = "/home/jacobr/vsac/"
        os.makedirs(file_dir, exist_ok=True)  # Ensure directory exists
        file_name = f"{search_term.replace(' ', '_')}_valueset.xlsx"
        file_path = os.path.join(file_dir, file_name)

        df = pd.DataFrame([{"Search Term": search_term, "ICD-10 Codes": ", ".join(icd10_codes)}])
        df.to_excel(file_path, index=False)

        session["last_generated_file"] = file_name

        return jsonify({"message": "File generated successfully", "file_path": file_path}), 200
    except Exception as e:
        return jsonify({"error": f"Internal Server Error: {str(e)}"}), 500


@app2_blueprint.route('/snomed/download', methods=['GET'])
def download_last_file():
    """Download the last generated value set file"""
    try:
        file_name = session.get("last_generated_file")
        if not file_name:
            return jsonify({"error": "No file available for download"}), 400

        file_path = os.path.join("/home/jacobr/vsac/", file_name)
        if os.path.exists(file_path):
            return send_file(file_path, as_attachment=True, download_name=file_name)
        else:
            return jsonify({"error": "File not found"}), 404
    except Exception as e:
        return jsonify({"error": f"Internal Server Error: {str(e)}"}), 500