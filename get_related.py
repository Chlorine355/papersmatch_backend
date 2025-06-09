import networkx as nx
import requests
import os


api_key = os.environ["S2_API_KEY"]


def get_related_papers(paper_id):
    r = requests.get(f"https://api.semanticscholar.org/graph/v1/paper/{paper_id}?fields=title,abstract,year,authors,"
                     f"fieldsOfStudy,"
                     f"externalIds,"
                     f"citationCount,citations.citationCount,citations.title,citations.abstract,citations.year,"
                     f"citations.authors,citations.fieldsOfStudy,"
                     "references.citationCount,references.title,references.abstract,references.year,"
                     "references.authors,references.fieldsOfStudy",
                     headers={'x-api-key': api_key}).json()
    refs = r.get('references', [])
    if refs is None:
        refs = []
    references = sorted(refs, key=lambda x: x['citationCount'] if x['citationCount'] else 0,
                        reverse=True)[:20]
    cits = r.get('citations', [])
    if cits is None:
        cits = []
    citations = sorted(cits, key=lambda x: x['citationCount'] if x['citationCount'] else 0, reverse=True)[:20]

    del r['references']
    del r['citations']
    return r, references + citations


def get_related_batch(paper_ids):
    if not paper_ids:
        return []
    try:
        r = requests.post(
            'https://api.semanticscholar.org/graph/v1/paper/batch',
            params={'fields': "citations,references"},
            json={"ids": paper_ids},
            headers={'x-api-key': api_key}).json()
        if type(r) == 'dict':
            return []
        return r
    except Exception:
        return []

def get_batch_papers(paper_ids):
    if not paper_ids:
        return []
    try:
        r = requests.post(
            'https://api.semanticscholar.org/graph/v1/paper/batch',
            params={'fields': "title,abstract,year,authors,"
                     f"fieldsOfStudy,venue,"
                     f"citationCount"},
            json={"ids": paper_ids},
            headers={'x-api-key': api_key}).json()
        if type(r) == 'dict':
            return []
        print(r)
        return r
    except Exception:
        return []


class GraphVisualization:
    def __init__(self):
        self.visual = []
        self.nodes = []
        self.origin = ''

    def addEdge(self, a, b):
        temp = [a, b]
        self.visual.append(temp)

    def addNode(self, a):
        self.nodes.append(a)

    def get_graph(self):
        G = nx.Graph()
        G.add_edges_from(self.visual)
        G.add_nodes_from(self.nodes)
        if len(G.nodes) < 5:
            return G
        for limit in range(15, -1, -1):
            f = 1
            while f:
                f = 0
                for node in list(G.nodes):
                    if G.degree[node] < limit:
                        f = 1
                        G.remove_node(node)
            if len(G.nodes) == 0:
                G.add_edges_from(self.visual)
            else:
                if len(G.nodes) < 10 and len(G.nodes) != 1:
                    G.clear()
                    G.add_edges_from(self.visual)
                    continue
                break
        T = nx.algorithms.minimum_spanning_tree(G)
        G.clear()
        G.add_edges_from(T.edges())
        if len(G.nodes) > 35:
            for adj_node in G[self.origin]:
                if len(G[adj_node]) > 3:
                    to_delete = []
                    for adj_adj_node in G[adj_node]:
                        to_delete.append(adj_adj_node)
                    to_delete.remove(self.origin)
                    G.remove_nodes_from(to_delete[:-3])
        return G
