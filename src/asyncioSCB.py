import asyncio
import os
import random
import string
import time
import uuid
from datetime import date, datetime

import httpx
import qrcode
import requests
from dotenv import load_dotenv

# Base URL depends on whether you are using Sandbox or Production environments
# Base URL depends on whether you are using Sandbox or Production environments
API_BASE_URL = "https://api-sandbox.partners.scb/partners/sandbox"
load_dotenv()  # reads .env in the current directory and loads into os.environ
API_KEY = os.environ["SCB_API_KEY"]
API_SECRET = os.environ["SCB_API_SECRET"]
biller_id = os.environ["SCB_BILLER_ID"]


async def get_access_token(client):
    print("[?] Generating Access Token...")
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

    response = await client.post(url, json=payload, headers=headers, timeout=10)
    response_data = response.json()

    if response.status_code == 200:
        return response_data.get("data", {}).get("accessToken")
    print("Failed to get token:", response_data)
    return None


async def generate_qr_code(client, access_token, amount, ref1, ref2, ref3):
    print("[?] Generating QR code...")
    url = f"{API_BASE_URL}/v1/payment/qrcode/create"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}",
        "requestUId": str(uuid.uuid4()),
        "resourceOwnerId": API_KEY,
        "accept-language": "EN"
    }
    payload = {
        "qrType": "PP",
        "ppType": "BILLERID",
        "ppId": biller_id,
        "amount": amount,
        "ref1": ref1,
        "ref2": ref2,
        "ref3": ref3
    }

    response = await client.post(url, json=payload, headers=headers, timeout=10)
    return response.json()


def generate_qr_from_raw_data(raw_data, filename="qr_code.png"):
    img = qrcode.make(raw_data)
    img.save(filename)
    print(f"[x] QR code image generated and saved to {filename}")


async def inquire_payment_status(client, access_token, ref1, ref2, ref3, biller_id, amount):
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

    try:
        response = await client.get(url, headers=headers, params=params, timeout=10)
    except httpx.RequestError as exc:
        return None, {"error": str(exc)}

    try:
        return response.status_code, response.json()
    except ValueError:
        return response.status_code, {"raw": response.text}


async def wait_for_payment(client, token, ref1, ref2, ref3, biller_id, amount,
                           poll_interval=2, max_seconds=300):
    """Poll until paid, timed out, or a hard error — without blocking the event loop."""
    deadline = asyncio.get_event_loop().time() + max_seconds

    while asyncio.get_event_loop().time() < deadline:
        await asyncio.sleep(poll_interval)  # non-blocking sleep
        status_code, payload = await inquire_payment_status(
            client, token, ref1, ref2, ref3, biller_id, amount
        )
        payload = {**payload, "ref1": ref1, "ref2": ref2, "ref3": ref3}
        print(status_code, payload)

        if status_code == 200:
            return "paid", payload
        if status_code is not None and status_code != 404:
            return "error", payload

    return "timeout", {"message": f"No payment after {max_seconds}s"}


async def process_order(client, amount):
    token = await get_access_token(client)
    if not token:
        return {"error": "no token"}

    now = datetime.now()
    ref1 = f"ORD{''.join(random.choices(string.digits+string.ascii_uppercase, k=10))}"
    ref2 = f"GUEST{now.strftime('%H%M%S')}{now.microsecond // 1000:03d}"
    ref3 = f"SCB{date.today().strftime('%d%m%y')}"

    qr_data = await generate_qr_code(client, token, amount, ref1=ref1, ref2=ref2, ref3=ref3)
    generate_qr_from_raw_data(qr_data['data']['qrRawData'], f"qr_{ref1}.png")
    print(f"[x] QR ready for {ref1}")

    result, details = await wait_for_payment(client, token, ref1, ref2, ref3, biller_id, amount)
    return {"ref1": ref1, "result": result, "details": details}


async def main():
    async with httpx.AsyncClient() as client:
        task1 = asyncio.create_task(process_order(client, "10000.00"))

        # ... later, start a new order while task1 is still polling ...
        task2 = asyncio.create_task(process_order(client, "5000.00"))

        results = await asyncio.gather(task1, task2)
        for r in results:
            print(r)


if __name__ == "__main__":
    asyncio.run(main())
