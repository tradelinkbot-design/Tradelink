import requests
import json
import time

API_KEY = "napi_gi3hc5e6z45akcls79ravpx3t18jz0ac17pt9fg0rzeyf5mite8mjbk5yqtrxz82"
PROJECT_ID = "round-snow-63044319"
ENDPOINT_ID = "ep-icy-dawn-ai5exv2z"
BASE_URL = "https://console.neon.tech/api/v2"

headers = {
    "Accept": "application/json",
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}

# Step 1 - Patch quota
def patch_quota():
    print("Step 1: Patching compute_time_seconds quota to 0...")
    payload = {
        "project": {
            "settings": {
                "quota": {
                    "compute_time_seconds": 0
                }
            }
        }
    }
    response = requests.patch(
        f"{BASE_URL}/projects/{PROJECT_ID}",
        headers=headers,
        json=payload,
    )
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        quota = response.json()["project"].get("settings", {}).get("quota", {})
        print(f"✅ Quota applied: {json.dumps(quota, indent=2)}")
        return True
    else:
        print(f"❌ Patch failed: {response.text}")
        return False

# Step 2 - Verify quota
def verify_quota():
    print("\nStep 2: Verifying quota was applied...")
    response = requests.get(
        f"{BASE_URL}/projects/{PROJECT_ID}",
        headers=headers,
    )
    if response.status_code == 200:
        quota = response.json()["project"].get("settings", {}).get("quota", {})
        compute_limit = quota.get("compute_time_seconds", "not set")
        print(f"compute_time_seconds = {compute_limit}")
        if compute_limit == 0:
            print("✅ Quota confirmed as 0 (unlimited).")
            return True
        else:
            print("⚠️  Quota not yet 0 — may need another attempt.")
            return False
    else:
        print(f"❌ Verify failed: {response.text}")
        return False

# Step 3 - Start compute with retry
def start_compute(max_retries=5):
    print("\nStep 3: Attempting to start compute...")
    for attempt in range(1, max_retries + 1):
        wait = 2 ** attempt  # exponential backoff: 2, 4, 8, 16, 32 seconds
        print(f"\nAttempt {attempt}/{max_retries}...")
        response = requests.post(
            f"{BASE_URL}/projects/{PROJECT_ID}/endpoints/{ENDPOINT_ID}/start",
            headers=headers,
        )
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            state = response.json().get("endpoint", {}).get("current_state", "unknown")
            print(f"✅ Compute started! State: {state}")
            return True
        elif response.status_code == 423:
            data = response.json()
            print(f"⚠️  Still locked: {data.get('message', '')}")
            if attempt < max_retries:
                print(f"Waiting {wait} seconds before retry...")
                time.sleep(wait)
        else:
            print(f"❌ Unexpected error: {response.text}")
            return False
    print("\n❌ All retry attempts failed.")
    return False

# Run all steps
if patch_quota():
    time.sleep(5)  # short pause after patch
    if verify_quota():
        time.sleep(5)  # short pause before starting
        start_compute()
    else:
        print("\nQuota not confirmed — skipping start. Try running the script again.")