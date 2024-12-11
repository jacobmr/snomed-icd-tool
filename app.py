from flask import Flask, render_template, request, jsonify, send_file
from dotenv import load_dotenv
import os
import requests
import pandas as pd
import subprocess



# Load environment variables
load_dotenv()

# Retrieve the API Key
API_KEY = os.getenv("UMLS_API_KEY")
if not API_KEY:
    raise RuntimeError("UMLS_API_KEY is not set. Please check your environment configuration.")

# VSAC FHIR API constants
BASE_URL = "https://cts.nlm.nih.gov/fhir/"
AUTH = ('apikey', API_KEY)
HEADERS = {"Accept": "application/fhir+json"}

# Initialize Flask app
app = Flask(__name__)

# Import and register the blueprint from app2
from app2 import app2_blueprint
app.register_blueprint(app2_blueprint, url_prefix='/app2')

# Utility Functions
def search_valuesets(term):
    """
    Search for value sets by a term in their name.
    """
    url = f"{BASE_URL}ValueSet"
    params = {"name:contains": term, "_count": 20}

    response = requests.get(url, auth=AUTH, headers=HEADERS, params=params)
    if response.status_code == 200:
        return response.json()
    else:
        raise ValueError(f"Error searching value sets: {response.status_code} {response.text}")

# Routes
@app.route('/')
def index():
    return render_template('index.html')


@app.route('/sync-git', methods=['POST'])
def sync_git():
    try:
        # Replace with your project directory
        project_dir = "/home/jacobr/vsac/"

        # Run git commands
        subprocess.run(["git", "-C", project_dir, "add", "."], check=True)
        subprocess.run(["git", "-C", project_dir, "commit", "-m", "Auto-sync from web button"], check=True)
        subprocess.run(["git", "-C", project_dir, "push", "origin", "main"], check=True)

        return jsonify({"message": "Git sync completed successfully"}), 200
    except subprocess.CalledProcessError as e:
        print(f"Git sync error: {e}")
        return jsonify({"error": "Git sync failed"}), 500
    except Exception as e:
        print(f"Unexpected error during Git sync: {e}")
        return jsonify({"error": f"Unexpected error: {str(e)}"}), 500



@app.route('/snomed-tool')
def snomed_tool():
    return render_template('index2.html')

@app.route('/search', methods=['POST'])
def search():
    """
    Endpoint to search for value sets based on a term.
    """
    term = request.form.get('term')
    if not term:
        return jsonify({"error": "Search term is required"}), 400

    try:
        # Make the API call
        results = search_valuesets(term)

        # Validate the response structure
        if "entry" not in results:
            return jsonify({"error": "No entries found in the response"}), 400

        # Extract and filter value sets
        value_sets = [
            {
                "id": resource.get("id"),
                "name": resource.get("name"),
                "title": resource.get("title"),
                "url": resource.get("url"),
            }
            for vs in results.get("entry", [])
            if (resource := vs.get("resource"))
        ]

        if not value_sets:
            return jsonify({"error": "No value sets found"}), 400

        return jsonify(value_sets)
    except Exception as e:
        return jsonify({"error": f"An unexpected error occurred: {str(e)}"}), 500

@app.route('/view/<value_set_id>', methods=['GET'])
def view_value_set(value_set_id):
    """
    Fetch details of a specific value set by ID.
    """
    try:
        url = f"{BASE_URL}ValueSet/{value_set_id}"
        response = requests.get(url, auth=AUTH, headers=HEADERS)
        if response.status_code == 200:
            return jsonify(response.json())
        else:
            return jsonify({"error": f"Error fetching details: {response.status_code}"}), response.status_code
    except Exception as e:
        return jsonify({"error": f"An unexpected error occurred: {str(e)}"}), 500

@app.route('/retrieve', methods=['POST'])
def retrieve():
    """
    Retrieve and save selected value sets to an Excel file.
    """
    try:
        selected_ids = request.json.get('selected_ids', [])
        if not selected_ids:
            return jsonify({"error": "No value sets selected"}), 400

        excel_data = []

        for oid in selected_ids:
            try:
                url = f"{BASE_URL}ValueSet/{oid}/$expand"
                response = requests.get(url, auth=AUTH, headers=HEADERS)
                if response.status_code == 200:
                    data = response.json()
                    for concept in data.get("expansion", {}).get("contains", []):
                        excel_data.append({
                            "Value Set OID": oid,
                            "Code": concept.get("code"),
                            "Display": concept.get("display")
                        })
                else:
                    return jsonify({"error": f"Error fetching data for {oid}: {response.text}"}), 500
            except Exception as e:
                return jsonify({"error": f"Exception while expanding value set {oid}: {str(e)}"}), 500

        # Write to Excel
        file_path = "/home/jacobr/vsac/generated_value_sets.xlsx"
        df = pd.DataFrame(excel_data)
        df.to_excel(file_path, index=False)

        return jsonify({"message": "File generated successfully", "download_url": "/retrieve/download"}), 200
    except Exception as e:
        return jsonify({"error": f"An unexpected error occurred: {str(e)}"}), 500

@app.route('/retrieve/download', methods=['GET'])
def download():
    """
    Endpoint to serve the generated Excel file.
    """
    try:
        file_path = "/home/jacobr/vsac/generated_value_sets.xlsx"
        return send_file(file_path, as_attachment=True, download_name="value_sets.xlsx")
    except Exception as e:
        return jsonify({"error": f"Unable to serve file: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(debug=False)