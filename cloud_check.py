import requests
response = requests.get("https://ec82bd8fa3f041a49a42a122ff3dc566.r2.cloudflarestorage.com")
print(response.status_code)
