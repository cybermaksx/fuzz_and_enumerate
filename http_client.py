import requests

def get_response(target):
    response = requests.get("https://google.com")
    print(response)
