#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests
from eth_account import Account
from web3 import Web3
from x402 import x402ClientSync
from x402.http.x402_http_client import x402HTTPClientSync
from x402.mechanisms.evm.exact.register import register_exact_evm_client
from x402.mechanisms.evm.signers import EthAccountSignerWithRPC


EVM_PRIVATE_KEY = ""
BASE_URL = "http://127.0.0.1:3005"
SEQ_DIR = Path(__file__).resolve().parent / "seq"
TIMEOUT = 180
REPORT_PATH = Path(__file__).resolve().parent / "test_x402_all_routes_report.json"

PERMIT2_ADDRESS = "0x000000000022D473030F116dDEE9F6B43aC78BA3"
MAX_UINT256 = 2**256 - 1
ALLOWED_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}

RPC_BY_NETWORK = {
    "eip155:8453": "https://base-rpc.publicnode.com",
    "eip155:137": "https://polygon-bor-rpc.publicnode.com",
    "eip155:42161": "https://arbitrum-one-rpc.publicnode.com",
}

ROUTES = [
    {
        "label": "Base USDC",
        "network": "eip155:8453",
        "asset": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
        "asset_symbol": "USDC",
        "method": "eip3009",
    },
    {
        "label": "Base USDT",
        "network": "eip155:8453",
        "asset": "0xfde4C96c8593536E31F229EA8f37b2ADa2699bb2",
        "asset_symbol": "USDT",
        "method": "permit2",
    },
    {
        "label": "Base EURC",
        "network": "eip155:8453",
        "asset": "0x60a3E35Cc302bFA44Cb288Bc5a4F316Fdb1adb42",
        "asset_symbol": "EURC",
        "method": "eip3009",
    },
    {
        "label": "Polygon USDC",
        "network": "eip155:137",
        "asset": "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359",
        "asset_symbol": "USDC",
        "method": "eip3009",
    },
    {
        "label": "Polygon USDT",
        "network": "eip155:137",
        "asset": "0xc2132D05D31c914a87C6611C10748AEb04B58e8F",
        "asset_symbol": "USDT",
        "method": "permit2",
    },
    {
        "label": "Arbitrum USDC",
        "network": "eip155:42161",
        "asset": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
        "asset_symbol": "USDC",
        "method": "eip3009",
    },
    {
        "label": "Arbitrum USDT",
        "network": "eip155:42161",
        "asset": "0xFd086bC7CD5C481DCC9C85ebE478A1C0b69FCbb9",
        "asset_symbol": "USDT",
        "method": "permit2",
    },
]

ERC20_ABI = [
    {
        "constant": True,
        "inputs": [{"name": "owner", "type": "address"}, {"name": "spender", "type": "address"}],
        "name": "allowance",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [{"name": "owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "constant": False,
        "inputs": [{"name": "spender", "type": "address"}, {"name": "amount", "type": "uint256"}],
        "name": "approve",
        "outputs": [{"name": "", "type": "bool"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
]


def main() -> int:
    private_key = load_private_key()
    frames = collect_frames(SEQ_DIR)
    if not frames:
        print(f"no image files found in {SEQ_DIR}", file=sys.stderr)
        return 2

    payer = Account.from_key(private_key)
    print(f"base_url={BASE_URL}")
    print(f"seq_dir={SEQ_DIR}")
    print(f"frame_count={len(frames)}")
    print(f"payer={payer.address}")

    report: dict[str, Any] = {
        "base_url": BASE_URL,
        "seq_dir": str(SEQ_DIR),
        "frame_count": len(frames),
        "payer": payer.address,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "results": [],
    }

    failures = 0
    with requests.Session() as session:
        for idx, route in enumerate(ROUTES, start=1):
            print("")
            print(f"=== route {idx}/{len(ROUTES)}: {route['label']} ===")
            try:
                result = test_route(session, private_key, frames, route)
                report["results"].append(result)
                if result.get("ok"):
                    print(
                        "route_ok network={network} asset={asset} tx={tx}".format(
                            network=result.get("settle_network") or "",
                            asset=result.get("accepted_asset_symbol") or "",
                            tx=result.get("settle_transaction") or "",
                        )
                    )
                else:
                    failures += 1
                    print(f"route_fail error={result.get('error')}", file=sys.stderr)
            except Exception as exc:  # pragma: no cover - debug helper
                failures += 1
                failure = {
                    "route": route["label"],
                    "network": route["network"],
                    "asset": route["asset"],
                    "asset_symbol": route["asset_symbol"],
                    "ok": False,
                    "error": str(exc),
                }
                report["results"].append(failure)
                print(f"route_exception={exc}", file=sys.stderr)

    report["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    report["failure_count"] = failures
    report["success_count"] = len(report["results"]) - failures
    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print("")
    print(f"report_path={REPORT_PATH}")
    print(f"success_count={report['success_count']}")
    print(f"failure_count={report['failure_count']}")
    return 1 if failures else 0


def test_route(
    session: requests.Session,
    private_key: str,
    frames: list[Path],
    route: dict[str, str],
) -> dict[str, Any]:
    task = create_public_task(session, len(frames))
    task_id = str(task.get("task_id") or "")
    task_token = str(task.get("task_token") or "")
    uploads = task.get("uploads") or []
    if not task_id or not task_token:
        raise RuntimeError(f"public task response missing task_id/task_token: {task}")
    if len(uploads) != len(frames):
        raise RuntimeError(f"upload count mismatch: {len(uploads)} != {len(frames)}")

    print(f"task_id={task_id}")
    upload_frames(session, uploads, frames)

    parse_url = f"{BASE_URL}/v1/public/sequences/{task_id}/parse"
    parse_payload = {
        "frames": [
            {
                "index": upload["index"],
                "object_key": upload["object_key"],
            }
            for upload in uploads
        ]
    }

    preview = session.post(
        parse_url,
        headers={
            "Content-Type": "application/json",
            "X-Task-Token": task_token,
        },
        json=parse_payload,
        timeout=TIMEOUT,
    )
    print(f"preview_status={preview.status_code}")
    if preview.status_code != 402:
        raise RuntimeError(f"expected 402 preview, got {preview.status_code}: {preview.text}")

    client = build_route_client(private_key, route)
    http_client = x402HTTPClientSync(client)
    payment_required = http_client.get_payment_required_response(
        lambda name: preview.headers.get(name),
        safe_json(preview),
    )
    selected = select_requirement(route, payment_required.accepts)
    selected_dump = selected.model_dump(by_alias=True)
    print(
        "selected_accept network={network} asset={asset} symbol={symbol} method={method} amount={amount}".format(
            network=selected_dump.get("network", ""),
            asset=selected_dump.get("asset", ""),
            symbol=((selected_dump.get("extra") or {}).get("assetSymbol") or ""),
            method=((selected_dump.get("extra") or {}).get("assetTransferMethod") or ""),
            amount=selected_dump.get("amount", ""),
        )
    )

    approval_tx = ""
    if route["method"] == "permit2":
        approval_tx = ensure_permit2_allowance(private_key, route, selected_dump["amount"])
        if approval_tx:
            print(f"permit2_approval_tx={approval_tx}")
        else:
            print("permit2_approval_tx=reused")

    payment_payload = client.create_payment_payload(payment_required)
    payment_headers = http_client.encode_payment_signature_header(payment_payload)
    paid = session.post(
        parse_url,
        headers={
            "Content-Type": "application/json",
            "X-Task-Token": task_token,
            **payment_headers,
        },
        json=parse_payload,
        timeout=TIMEOUT,
    )
    print(f"paid_status={paid.status_code}")

    settle = None
    settle_error = ""
    try:
        settle = http_client.get_payment_settle_response(lambda name: paid.headers.get(name))
    except Exception as exc:  # pragma: no cover - best effort diagnostics
        settle_error = str(exc)

    body = safe_json(paid)
    result: dict[str, Any] = {
        "route": route["label"],
        "network": route["network"],
        "asset": route["asset"],
        "asset_symbol": route["asset_symbol"],
        "method": route["method"],
        "task_id": task_id,
        "task_token": task_token,
        "preview_status": preview.status_code,
        "paid_status": paid.status_code,
        "accepted": payment_payload.accepted.model_dump(by_alias=True),
        "settle": settle.model_dump(by_alias=True) if settle else None,
        "settle_error": settle_error,
        "approval_tx": approval_tx,
        "response_body": body,
        "ok": paid.ok,
    }

    if settle is not None:
        result["settle_network"] = settle.network
        result["settle_transaction"] = settle.transaction
        result["settle_amount"] = settle.amount

    extra = (selected_dump.get("extra") or {})
    result["accepted_asset_symbol"] = extra.get("assetSymbol")
    result["accepted_method"] = extra.get("assetTransferMethod")
    result["accepted_display_amount"] = extra.get("displayAmount")

    if not paid.ok:
        result["error"] = paid.text
        return result

    sequences = body.get("sequences") if isinstance(body, dict) else None
    sequence = sequences[0] if isinstance(sequences, list) and sequences and isinstance(sequences[0], dict) else None
    if isinstance(sequence, dict):
        result["status"] = body.get("status")
        result["sequence_count"] = body.get("sequence_count") or len(sequences)
        result["sequence_id"] = sequence.get("sequence_id")
        result["result_frame_count"] = sequence.get("frame_count")
        result["gait_feature_dim"] = len(sequence.get("gait_feature") or [])
        result["reid_feature_dim"] = len(sequence.get("reid_feature") or [])
        result["face_feature_dim"] = len(sequence.get("face_feature") or [])
        result["reid_raw_dim"] = len(sequence.get("reid_raw") or [])
    return result


def load_private_key() -> str:
    private_key = EVM_PRIVATE_KEY.strip() or os.environ.get("GAIT_TEST_WALLET_PRIVATE_KEY", "").strip()
    if not private_key:
        print(
            "fill EVM_PRIVATE_KEY in examples/test_x402_all_routes.py or export GAIT_TEST_WALLET_PRIVATE_KEY",
            file=sys.stderr,
        )
        raise SystemExit(2)
    if not private_key.startswith("0x"):
        private_key = "0x" + private_key
    return private_key


def build_route_client(private_key: str, route: dict[str, str]) -> x402ClientSync:
    network = route["network"]
    rpc_url = RPC_BY_NETWORK.get(network)
    if not rpc_url:
        raise RuntimeError(f"rpc not configured for {network}")
    account = Account.from_key(private_key)
    signer = EthAccountSignerWithRPC(account, rpc_url=rpc_url)
    client = x402ClientSync(
        payment_requirements_selector=lambda version, reqs: select_requirement(route, reqs)
    )
    register_exact_evm_client(client, signer, networks=network)
    return client


def select_requirement(route: dict[str, str], requirements: list[Any]):
    target_network = route["network"].strip()
    target_asset = route["asset"].strip().lower()
    for requirement in requirements:
        network = str(getattr(requirement, "network", "")).strip()
        asset = str(getattr(requirement, "asset", "")).strip().lower()
        if network == target_network and asset == target_asset:
            return requirement
    raise RuntimeError(f"route accept not found for {route['label']}")


def create_public_task(session: requests.Session, frame_count: int) -> dict[str, Any]:
    response = session.post(
        f"{BASE_URL}/v1/public/sequences",
        json={"frame_count": frame_count},
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


def upload_frames(session: requests.Session, uploads: list[dict[str, Any]], frames: list[Path]) -> None:
    for upload, frame_path in zip(uploads, frames):
        upload_url = urljoin(BASE_URL + "/", str(upload["upload_url"]).lstrip("/"))
        response = session.put(
            upload_url,
            headers={"Content-Type": detect_content_type(frame_path)},
            data=frame_path.read_bytes(),
            timeout=TIMEOUT,
        )
        response.raise_for_status()
    print(f"uploaded_count={len(frames)}")


def ensure_permit2_allowance(private_key: str, route: dict[str, str], needed_amount: str) -> str:
    rpc_url = RPC_BY_NETWORK.get(route["network"])
    if not rpc_url:
        raise RuntimeError(f"rpc not configured for {route['network']}")
    w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 30}))
    account = Account.from_key(private_key)
    owner = Web3.to_checksum_address(account.address)
    token = Web3.to_checksum_address(route["asset"])
    spender = Web3.to_checksum_address(PERMIT2_ADDRESS)
    contract = w3.eth.contract(address=token, abi=ERC20_ABI)
    allowance = contract.functions.allowance(owner, spender).call()
    amount_int = int(needed_amount)
    print(f"permit2_allowance={allowance}")
    if allowance >= amount_int:
        return ""

    nonce = w3.eth.get_transaction_count(owner, "pending")
    tx_params: dict[str, Any] = {
        "from": owner,
        "nonce": nonce,
        "chainId": w3.eth.chain_id,
    }
    latest = w3.eth.get_block("latest")
    base_fee = latest.get("baseFeePerGas")
    if base_fee is not None:
        try:
            priority_fee = w3.eth.max_priority_fee
        except Exception:
            priority_fee = w3.to_wei(0.02, "gwei")
        tx_params["maxPriorityFeePerGas"] = int(priority_fee)
        tx_params["maxFeePerGas"] = int(base_fee) * 2 + int(priority_fee)
        tx_params["type"] = 2
    else:
        tx_params["gasPrice"] = w3.eth.gas_price

    tx = contract.functions.approve(spender, MAX_UINT256).build_transaction(tx_params)
    if "gas" not in tx:
        tx["gas"] = w3.eth.estimate_gas(tx)
    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=240)
    if int(receipt.status) != 1:
        raise RuntimeError(f"permit2 approve failed: {tx_hash.hex()}")
    return tx_hash.hex()


def collect_frames(seq_dir: Path) -> list[Path]:
    files = [item for item in seq_dir.iterdir() if item.is_file() and item.suffix.lower() in ALLOWED_SUFFIXES]
    return sorted(files, key=lambda item: item.name)


def detect_content_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".png":
        return "image/png"
    if suffix == ".bmp":
        return "image/bmp"
    if suffix == ".webp":
        return "image/webp"
    return "application/octet-stream"


def safe_json(response: requests.Response) -> Any:
    try:
        return response.json()
    except Exception:
        return {"raw_text": response.text}


if __name__ == "__main__":
    raise SystemExit(main())
