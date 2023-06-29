from firebase_functions import https_fn
from firebase_admin import initialize_app
from bs4 import BeautifulSoup
import json
import requests

initialize_app()

headers = {"Access-Control-Allow-Origin": "*"}


def set_cors(req: https_fn.Request) -> https_fn.Response:
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

    return None


def get_query(req: https_fn.Request) -> str | https_fn.Response:
    query = req.get_json().get("query")

    if not query:
        return https_fn.Response("Query not provided", status=400)

    return query


@https_fn.on_request()
def dis(req: https_fn.Request) -> https_fn.Response:
    ret = set_cors(req)
    if ret is not None:
        return ret
    query = get_query(req)

    print(query)

    response = requests.get(f"https://dis-slovarcek.ijs.si/search?search_query={query}")

    # Check if the request was successful
    if response.status_code != 200:
        print(
            "Error accessing https://dis-slovarcek.ijs.si. Status code:",
            response.status_code,
        )
        return

    soup = BeautifulSoup(response.content, "html.parser")
    result_containers = soup.find_all(id="all-search-results")

    results = []

    for result_container in result_containers:
        result = result_container.find(class_="accordion")

        en = result.find(class_="search-result-left").text.strip()
        sl = result.find(class_="search-result-right").text.strip()

        results.append({"en": en, "sl": sl})

    return https_fn.Response(json.dumps(results), status=200, headers=headers)


# LTFE slovar v primeru, da je rezultatov veliko vrne samo prvih nekaj,
# zato za vsak jezik queryjamo endpoint, ki vrne vse rezultate
@https_fn.on_request()
def ltfe(req: https_fn.Request) -> https_fn.Response:
    ret = set_cors(req)
    if ret is not None:
        return ret
    query = get_query(req)

    results = []

    response = requests.get(f"http://slovar.ltfe.org/index/add/eng/?q={query}&type=all")
    if response.status_code != 200:
        print(
            "Error accessing http://slovar.ltfe.org. Status code:", response.status_code
        )
        return
    soup = BeautifulSoup(response.content, "html.parser")
    result_containers = soup.find_all(class_="wHead")
    for result_container in result_containers:
        sl = result_container.find(class_="lang").text.strip()
        en = result_container.contents[0].strip()

        results.append({"en": en, "sl": sl})

    response = requests.get(f"http://slovar.ltfe.org/index/add/slo/?q={query}&type=all")
    if response.status_code != 200:
        print(
            "Error accessing http://slovar.ltfe.org. Status code:", response.status_code
        )
        return
    soup = BeautifulSoup(response.content, "html.parser")
    result_containers = soup.find_all(class_="wHead")
    for result_container in result_containers:
        en = result_container.find(class_="lang").text.strip()
        sl = result_container.contents[0].strip()

        results.append({"en": en, "sl": sl})

    return https_fn.Response(json.dumps(results), status=200, headers=headers)


# Na IJS ne znajo napisati programa, ki bi generiral pravilen HTML, zato rabimo ročno parsati text
@https_fn.on_request()
def ijs(req: https_fn.Request) -> https_fn.Response:
    ret = set_cors(req)
    if ret is not None:
        return ret
    query = get_query(req)

    response = requests.get(f"https://www.ijs.si/cgi-bin/rac-slovar?w={query}")

    # Check if the request was successful
    if response.status_code != 200:
        print("Error accessing https://www.ijs.si. Status code:", response.status_code)
        return

    soup = BeautifulSoup(response.content, "html.parser")

    translation_container = soup.find("dl")

    results = []

    for translation in str(translation_container.contents).split("\n"):
        translation = translation.replace("['\\n', ", "")
        translation = translation.replace("<dt>", "")

        if len(translation.split("<dd>")) == 2:
            en, sl = translation.split("<dd>")

        results.append({"en": en, "sl": sl})

    return https_fn.Response(json.dumps(results), status=200, headers=headers)
