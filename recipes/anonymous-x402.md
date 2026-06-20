# Anonymous x402

Use this recipe when the caller should use public paid APIs without a registered
API key.

## Use

- Create tasks under `/v1/public/...`.
- Keep the returned `task_token`.
- Public paid endpoints may return HTTP 402 with a payment context.
- Sign the x402 payment payload with an EVM wallet.
- Retry the same HTTP request with payment headers.

## Do Not Use

- Do not send `Authorization: Bearer <api_key>` on anonymous public routes.
- Do not use MCP JSON-RPC for anonymous x402 payment. Anonymous x402 is an HTTP
  public API flow.

## Run

```bash
pip install requests eth-account 'x402[evm]' web3
export GAIT_TEST_WALLET_PRIVATE_KEY='0x...'
export GAIT_API_BASE_URL='https://www.w-agent.cn/api'
python3 examples/anonymous/python/anonymous_sequence_x402_demo.py
```
