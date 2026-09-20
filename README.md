# SCB QR Payment Integration

Two implementations of the same SCB (Siam Commercial Bank) Partner API QR payment flow — generate a Thai QR (Tag 30 / C-Scan-B) via BillerID, then poll until it's paid. Pick the file that matches how your system needs to handle orders.

| File | Style | Best for |
|---|---|---|
| `SCB.py` | Blocking / synchronous | Vending machines, kiosks, IoT devices |
| `asyncioSCB.py` | Async / non-blocking | Websites, backend APIs, servers |

---

## `SCB.py` — Blocking

Uses plain `requests` calls and blocking `time.sleep()` while polling for payment. Each order is created, then the script sits and waits until that one order is paid (or times out) before it can start the next.

**Why this fits vending machines / IoT:**
- These devices only ever handle **one transaction at a time** — a customer pays, gets their item, then the next customer starts.
- No event loop or concurrency needed — simpler code, smaller footprint, easier to run on constrained hardware (Raspberry Pi, embedded Linux boards, POS terminals).
- Easier to reason about and debug on single-purpose devices: request QR → display QR → poll → dispense/print → done.

**Trade-off:** if you tried to reuse this for a website, every customer would have to wait for the previous customer's payment (or timeout, up to 5 minutes) to finish before the next request is even processed. Fine for one physical machine, bad for a shared server handling many users.

---

## `asyncioSCB.py` — Non-blocking

Uses `httpx.AsyncClient` and `asyncio.sleep()`, so polling for one order's payment doesn't block anything else. Multiple orders can be created and polled concurrently via `asyncio.gather()` / `asyncio.create_task()`.

**Why this fits websites/backends:**
- Many customers can generate QR codes and have their payments polled **at the same time**, on a single process/thread.
- A slow or unpaid order doesn't hold up other customers' checkouts.
- Suited for wrapping in a web framework (FastAPI, etc.) where each incoming HTTP request needs to be handled without freezing the server for other users.

---

## How the flow works (both versions)

1. **Get access token** — `POST /v1/oauth/token` using `applicationKey` / `applicationSecret`.
2. **Generate QR** — `POST /v1/payment/qrcode/create` with `qrType: PP`, `ppType: BILLERID`, your `billerId`, amount, and three reference values (`ref1`, `ref2`, `ref3`).
3. **Render QR** — the raw QR payload (`qrRawData`) is turned into a scannable QR code image.
4. **Poll for payment** — `GET /v1/payment/billpayment/inquiry` repeatedly (eventCode `00300100`) until:
   - `200` → paid
   - non-404 error → something went wrong
   - timeout reached → give up (default 300s)

SCB also supports an asynchronous webhook callback for payment confirmation — polling here is the fallback/alternative approach for when you want to actively check status instead of (or alongside) waiting for that callback.

---

## Setup

```bash
pip install requests httpx qrcode
```

### Required credentials

Set these as environment variables — **do not hardcode them in the script**:

```bash
export SCB_API_KEY=your_application_key
export SCB_API_SECRET=your_application_secret
export SCB_BILLER_ID=your_biller_id
```

| Variable | Description |
|---|---|
| `SCB_API_KEY` | SCB Partner API application key |
| `SCB_API_SECRET` | SCB Partner API application secret |
| `SCB_BILLER_ID` | Your registered BillerID for QR generation |

### Environment

By default both scripts point at SCB's **sandbox** environment:

```
https://api-sandbox.partners.scb/partners/sandbox
```

Switch to production endpoints only once you've completed SCB's onboarding/testing process for live billing.

---

## ⚠️ Important notes

- **Never commit real API keys/secrets to this repo.** Use environment variables or a `.env` file (and add `.env` to `.gitignore`).
- Sandbox credentials and production credentials are different — don't mix them up.
- `ref1` should be unique per order (used to look up the transaction on future inquiries); the scripts generate it randomly.
- Default poll timeout is 300 seconds (5 minutes) — tune this to your actual expected payment window.
- On `SCB.py`, remember blocking sleeps mean the whole script is unresponsive while waiting — don't run it in a context expecting concurrent handling.
- On `asyncioSCB.py`, remember all async functions must be awaited within a running event loop (`asyncio.run(...)`), and shared `httpx.AsyncClient` instances should be closed properly (e.g. via `async with`).

---

## License

Add your license here.
