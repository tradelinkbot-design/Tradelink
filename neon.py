import requests
import json

API_KEY = "napi_gi3hc5e6z45akcls79ravpx3t18jz0ac17pt9fg0rzeyf5mite8mjbk5yqtrxz82"
PROJECT_ID = "round-snow-63044319"

url = f"https://console.neon.tech/api/v2/projects/{PROJECT_ID}"

headers = {
    "Accept": "application/json",
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}

payload = {
    "project": {
        "settings": {
            "quota": {
                "active_time_seconds": 0,
                "compute_time_seconds": 0,
                "written_data_bytes": 0,
                "data_transfer_bytes": 0,
                "logical_size_bytes": 0,
            }
        }
    }
}

print("Sending request to Neon API...")

response = requests.patch(url, headers=headers, json=payload)

print(f"Status Code: {response.status_code}")

if response.status_code == 200:
    print("✅ Success! All quotas have been removed.")
    data = response.json()
    print(f"Project name: {data['project']['name']}")
    print(f"Project ID:   {data['project']['id']}")
    print("\n--- Quota settings ---")
    quota = data["project"].get("settings", {}).get("quota", {})
    print(json.dumps(quota, indent=2))
else:
    print("❌ Something went wrong.")
    print(json.dumps(response.json(), indent=2))