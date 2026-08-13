# Python ReID x402 Demo

This package only demonstrates ReID feature extraction for anonymous users with x402 payment.

## Setup

```bash
pip install requests eth-account web3 'x402[evm]'
```

## Usage

1. Open `anonymous_reid_x402_demo.py`.
2. Edit `EVM_PRIVATE_KEY` and `IMAGE_PATH`.
3. Run:

```bash
python3 anonymous_reid_x402_demo.py
```

The script first receives an HTTP 402 payment challenge, signs the x402 payment header, then retries `POST /v1/public/features/reid`.

The input should be one cropped person image.
