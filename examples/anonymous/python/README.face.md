# Python Face Recognition x402 Demo

This package only demonstrates face recognition for anonymous users with x402 payment.

## Setup

```bash
pip install requests eth-account web3 'x402[evm]'
```

## Usage

1. Open `anonymous_face_x402_demo.py`.
2. Edit `EVM_PRIVATE_KEY` and `IMAGE_PATH`.
3. Run:

```bash
python3 anonymous_face_x402_demo.py
```

The script first receives an HTTP 402 payment challenge, signs the x402 payment header, then retries `POST /v1/public/features/face`.

The input should be an aligned face image.
