import requests

url = "https://api.fortyguard.com/v1/system/fetch-api-key-usage"
headers = {
    "api-key": "cecd048cf0c2b1bc283eeacf984095c0",
    "Content-Type": "application/json"
}
response = requests.post(url, headers=headers, json={})

print(response.status_code)
print(response.json())