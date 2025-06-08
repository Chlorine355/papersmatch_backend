import os
from flask import Flask, request, jsonify
import requests
from flask_cors import CORS

from get_related import get_related_papers, GraphVisualization, get_related_batch

app = Flask(__name__)
CORS(app)

app.config['JSON_AS_ASCII'] = False
app.config['SECRET_KEY'] = os.environ['PM_SECRET_KEY']

api_key = os.environ["S2_API_KEY"]


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
    response = requests.get(
        f"https://api.semanticscholar.org/graph/v1/paper/search{is_open_access}",
        params=params,
        headers={"x-api-key": api_key},
    ).json()

    results = response.get("data", [])
    total = response.get("total", 0)
    return jsonify({"data": results, "total": min(total, 1000)})


@app.route('/graph/<paper_id>', methods=['GET'])
def graph(paper_id):
    origin, related_to_root_list = get_related_papers(paper_id)
    G = GraphVisualization()
    id_to_paper = {paper_id: origin}
    G.addNode(paper_id)
    G.origin = paper_id
    related_to_root_list = [rel for rel in related_to_root_list if rel['paperId']]
    for rel in related_to_root_list:
        id_to_paper[rel['paperId']] = rel  # save
        G.addEdge(paper_id, rel["paperId"])
    related_to_root_ids = [rel['paperId'] for rel in related_to_root_list]
    newrels = get_related_batch(related_to_root_ids)
    for i in range(len(newrels)):
        if newrels[i].get("citations"):
            for citation in newrels[i]['citations']:
                if citation['paperId']:
                    id_to_paper[citation['paperId']] = citation
                    G.addEdge(related_to_root_ids[i], citation['paperId'])
        if newrels[i].get("references"):
            for reference in newrels[i].get('references', []):
                if reference['paperId']:
                    id_to_paper[reference['paperId']] = reference
                    G.addEdge(related_to_root_ids[i], reference['paperId'])
    gr = G.get_graph()
    node_list = list(gr.nodes)
    all_keys = list(id_to_paper.keys())
    for key in all_keys:
        if key not in node_list:
            del id_to_paper[key]
    return jsonify({"nodes": list(id_to_paper.values()), "edges": list(gr.edges)})


@app.route('/add_to_favourites', methods=['POST'])
def add_to_favourites():
    return 0


app.run('0.0.0.0', 80)
