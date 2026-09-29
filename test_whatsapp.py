import requests

PHONE_NUMBER_ID = "1187662211100957"
ACCESS_TOKEN = "EAAgQZB1il46UBR6O50YQde6W7Pe5vclYBrdYqvADT9FEJPWeVY4EkF5iLncGFsFJpXHRXgkjsrIk8ZCwFAmZBCJlsV8ZCW9bRvgW5ZCvrFllelgFxwe0hF7HRdAdHMVP3HslqgZAAgthmzZAHfl5szo4jpVxeCvHZAcRVShJCaSGfkTpZBCfz2L9eDErDnsI35PotLfLLkYHNs09j7KdXuuZAZCBr5qUT0ZBQ7mbTDuwQiQuzpcSCjBn4mXn7IFeGAIaJiZBKxcRAEtgw3n6YuJO70kDAxis7mQZDZD"
YOUR_WHATSAPP_NUMBER = "2348055081771"  # your number, no + sign

url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"

headers = {
    "Authorization": f"Bearer {ACCESS_TOKEN}",
    "Content-Type": "application/json"
}

payload = {
    "messaging_product": "whatsapp",
    "to": YOUR_WHATSAPP_NUMBER,
    "type": "template",
    "template": {
        "name": "hello_world",
        "language": {"code": "en_US"}
    }
}

response = requests.post(url, headers=headers, json=payload)
print("Status:", response.status_code)
print("Response:", response.json())