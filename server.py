from pprint import pprint

from flask import Flask, request, jsonify
import requests
from flask_cors import CORS


app = Flask(__name__)
CORS(app)

app.config['JSON_AS_ASCII'] = False
app.config['SECRET_KEY'] = ''

api_key = ""

PAGE_SIZE = 20


@app.route('/search', methods=['GET'])
def search():
    args = request.args
    query = args.get("query")
    page = int(args.get("page"))

    year_from = args.get("yearFrom", "")
    year_to = args.get("yearTo", "")
    year_range = f"{year_from}-{year_to}" if year_from or year_to else None

    is_open_access = "?openAccessPdf" if args.get("isOpenAccess") else ""
    min_citations = args.get('minCitations', "")
    offset = PAGE_SIZE * (page - 1)

    params = {
        "query": query,
        "offset": offset,
        "limit": PAGE_SIZE,
        "fields": "title,authors,year,fieldsOfStudy,abstract,citationCount,tldr,isOpenAccess,openAccessPdf,"
                  "citationStyles,venue",
        "year": year_range,
        "minCitationCount": min_citations if min_citations else "0",
    }
    print(params)
    response = requests.get(
        f"https://api.semanticscholar.org/graph/v1/paper/search{is_open_access}",
        params=params,
        headers={"x-api-key": api_key},
    ).json()

    results = response.get("data", [])
    total = response.get("total", 0)
    return jsonify({"data": results, "total": min(total, 1000)})


app.run('0.0.0.0', 80)
