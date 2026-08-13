# Python Object Search x402 Demo

This package only demonstrates Object Search for anonymous users with x402 payment.

## Setup

```bash
pip install requests eth-account web3 'x402[evm]'
```

## Usage

1. Open `anonymous_object_search_x402_demo.py`.
2. Edit `EVM_PRIVATE_KEY`, `IMAGE_PATH`, and `PROMPT`.
3. Run:

```bash
python3 anonymous_object_search_x402_demo.py
```

The script first receives an HTTP 402 payment challenge, signs the x402 payment header, then retries `POST /v1/public/object-search`.
