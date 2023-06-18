from firebase_functions import https_fn
from firebase_admin import initialize_app
from bs4 import BeautifulSoup
import json
import requests

initialize_app()


def dis_slovarcek(query):
    response = requests.get(f"https://dis-slovarcek.ijs.si/search?search_query={query}")

    # Check if the request was successful
    if response.status_code != 200:
        print(
            "Error accessing dis-slovarcek.ijs.si. Status code:", response.status_code
        )
        return

    soup = BeautifulSoup(response.content, "html.parser")
    result_containers = soup.find_all(id="all-search-results")

    results = []

    for result_container in result_containers:
        result = result_container.find(class_="accordion")

        en = result.find(class_="search-result-left").text.replace("\n", "")
        sl = result.find(class_="search-result-right").text.replace("\n", "")

        id = f'dis-slovarcek-{en}-{sl}'

        results.append({"en": en, "sl": sl, "source": "dis slovarcek", "id": id})

    return results


@https_fn.on_request()
def slovar(req: https_fn.Request) -> https_fn.Response:
    # Set CORS headers for preflight requests
    if req.method == "OPTIONS":
        headers = {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST",
            "Access-Control-Allow-Headers": "Content-Type",
            "Access-Control-Max-Age": "3600",
        }
        return ("", 204, headers)

    # Only allow POST requests
    if req.method != "POST":
        print(f"Method {req.method} not allowed")
        return https_fn.Response("Only POST requests are accepted", status=400)

    query = req.get_json().get("query")

    translations = []
    translations.append(dis_slovarcek(query))

    headers = {"Access-Control-Allow-Origin": "*"}

    return https_fn.Response(json.dumps(translations), status=200, headers=headers)
