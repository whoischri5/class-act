import os, requests
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.environ["FOOTBALL_DATA_API_KEY"]

resp = requests.get(
    "https://api.football-data.org/v4/competitions/CL",
    headers={"X-AUth-Token": API_KEY}
)

print(resp.status_code)
print(resp.json())

