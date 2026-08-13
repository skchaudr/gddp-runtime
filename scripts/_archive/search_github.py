import urllib.request
import json
import os

token = os.environ.get('GITHUB_TOKEN')
headers = {'Accept': 'application/vnd.github.v3+json'}
if token:
    headers['Authorization'] = f'token {token}'

def search_repo(query):
    url = f"https://api.github.com/search/repositories?q={urllib.parse.quote(query)}&sort=stars&order=desc&per_page=3"
    req = urllib.request.Request(url, headers=headers)
    try:
        response = urllib.request.urlopen(req)
        data = json.loads(response.read().decode())
        print(f"\nSearch: {query}")
        for item in data.get('items', []):
            print(f"- {item['full_name']} (Stars: {item['stargazers_count']}): {item['description']}")
    except Exception as e:
        print(f"Error querying {query}: {e}")

import urllib.parse
search_repo("ControlFlow agent")
search_repo("LangGraph")
search_repo("SWE-agent")
