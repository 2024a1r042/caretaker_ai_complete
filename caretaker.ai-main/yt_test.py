import urllib.request
import urllib.parse
import re

def search_youtube(query):
    query_string = urllib.parse.urlencode({"search_query": query})
    req = urllib.request.Request(
        "https://www.youtube.com/results?" + query_string,
        headers={'User-Agent': 'Mozilla/5.0'}
    )
    html_content = urllib.request.urlopen(req)
    search_results = re.findall(r'watch\?v=([a-zA-Z0-9_-]{11})', html_content.read().decode())
    if search_results:
        return search_results[0]
    return None

if __name__ == "__main__":
    vid = search_youtube("pal pal dil ke paas kishore kumar")
    print("Video ID:", vid)
