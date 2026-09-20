import os
import time
import uuid
from datetime import date, datetime

import qrcode
import requests
from dotenv import load_dotenv

# Base URL depends on whether you are using Sandbox or Production environments
API_BASE_URL = "https://api-sandbox.partners.scb/partners/sandbox"
load_dotenv()  # reads .env in the current directory and loads into os.environ
API_KEY = os.environ["SCB_API_KEY"]
API_SECRET = os.environ["SCB_API_SECRET"]
biller_id = os.environ["SCB_BILLER_ID"]


def get_access_token():
    print("[?] Generating Access Token...")
    """
    Step 1: Generate Access Token using Client Credentials.
    API Endpoint: POST /v1/oauth/token
    """
    url = f"{API_BASE_URL}/v1/oauth/token"

    headers = {
        "Content-Type": "application/json",
        "requestUId": str(uuid.uuid4()),
        "resourceOwnerId": API_KEY,
        "accept-language": "EN"
    }

    payload = {
        "applicationKey": API_KEY,
        "applicationSecret": API_SECRET
    }

    response = requests.post(url, json=payload, headers=headers)
    response_data = response.json()

    if response.status_code == 200:
        return response_data.get("data", {}).get("accessToken")
    else:
        print("Failed to get token:", response_data)
        return None


def generate_qr_code(access_token, amount, ref1, ref2, ref3):
    print("[?] Generating QR code...")
    """
    Step 2: QR Code Generation
    API Endpoint: POST /v1/payment/qrcode/create
    """
    url = f"{API_BASE_URL}/v1/payment/qrcode/create"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}",
        "requestUId": str(uuid.uuid4()),
        "resourceOwnerId": API_KEY,
        "accept-language": "EN"
    }

    # Note: Ensure you match these fields with the exact API Reference schema
    # for C Scan B Payment (QR 30 or QR CS).
    payload = {
        "qrType": "PP",
        "ppType": "BILLERID",
        "ppId": "787394314968506",
        "amount": amount,
        "ref1": ref1,
        "ref2": ref2,
        "ref3": ref3
    }

    response = requests.post(url, json=payload, headers=headers)
    return response.json()


def generate_qr_from_raw_data(raw_data, filename="qr_code.png"):
    img = qrcode.make(raw_data)
    img.save(filename)
    print(f"[x] QR code image generated and saved to {filename}")


def inquire_payment_status(access_token, ref1, ref2, ref3, biller_id, amount):
    """
    Payment Transaction Inquiry (Thai QR Code Tag 30 / C Scan B).
    API Endpoint: GET /v1/payment/billpayment/inquiry

    Use this to actively check whether a QR has been paid, instead of
    (or in addition to) waiting for SCB's asynchronous Payment Confirmation
    callback to hit your server. SCB's own docs recommend calling this
    whenever a customer says they paid but no webhook arrived.

    eventCode 00300100 = Thai QR Code Tag 30 (C Scan B) -- matches the
    qrType/ppType used in generate_qr_code() above.
    """
    url = f"{API_BASE_URL}/v1/payment/billpayment/inquiry"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}",
        "requestUId": str(uuid.uuid4()),
        "resourceOwnerId": API_KEY,
        "accept-language": "EN"
    }

    params = {
        "eventCode": "00300100",
        "transactionDate": date.today().strftime("%Y-%m-%d"),
        "billerId": biller_id,
        "reference1": ref1,
        "reference2": ref2,
        "reference3": ref3,
        "amount": amount
    }
    response = requests.get(url, headers=headers, params=params)

    try:
        return response.status_code, response.json()
    except ValueError:
        return response.status_code, {"raw": response.text}


if __name__ == "__main__":
    token = get_access_token()
    amount = "10000.00"
    now = datetime.now()
    ref1 = f"ORD{int(time.time())}{uuid.uuid4().hex[:6].upper()}"[:20]
    ref2 = f"GUEST{now.strftime('%H%M%S')}{now.microsecond // 1000:03d}"
    ref3 = f"SCB{date.today().strftime('%d%m%y')}"

    print("[x] " + f"{ref1}", ref2, ref3)

    if token:
        qr_data = generate_qr_code(
            token,
            amount,
            ref1=ref1,
            ref2=ref2,
            ref3=ref3)
        generate_qr_from_raw_data(qr_data['data']['qrRawData'])
        while True:
            time.sleep(2)
            payment_status = inquire_payment_status(
                token, ref1, ref2, ref3, biller_id, amount)
            print(payment_status)
            if not (payment_status[0] == 404):
                break

        print("[x] Payment Successful")
