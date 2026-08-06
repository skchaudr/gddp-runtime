import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET

queries = [
    'all:"graph-driven" AND all:agent',
    'all:"self-correction" AND all:LLM',
    'all:"state machine" AND all:agent',
    'all:"trajectory evaluation" OR all:"trajectory optimization" AND all:"LLM"',
    'all:"trust calibration" AND all:"agent"',
    'all:"LangGraph" OR all:"AutoGen" OR all:"SWE-agent" OR all:"OpenHands"'
]

for query in queries:
    print(f"\nSearching for: {query}")
    url = f'https://export.arxiv.org/api/query?search_query={urllib.parse.quote(query)}&start=0&max_results=3&sortBy=submittedDate&sortOrder=descending'
    try:
        response = urllib.request.urlopen(url)
        data = response.read()
        root = ET.fromstring(data)
        for entry in root.findall('{http://www.w3.org/2005/Atom}entry'):
            title = entry.find('{http://www.w3.org/2005/Atom}title').text.replace('\n', ' ')
            published = entry.find('{http://www.w3.org/2005/Atom}published').text
            summary = entry.find('{http://www.w3.org/2005/Atom}summary').text.replace('\n', ' ')[:200]
            print(f"- {published[:10]} | {title}\n  {summary}...")
    except Exception as e:
        print(f"Error querying {query}: {e}")
