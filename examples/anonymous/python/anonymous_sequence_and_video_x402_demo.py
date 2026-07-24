#!/usr/bin/env python3
"""
Batch real x402 tester for anonymous public sequence and video APIs.

Configure EVM_PRIVATE_KEY below or export GAIT_TEST_WALLET_PRIVATE_KEY.
Results are written under RESULT_DIR as one JSON file per sequence/video plus
summary.json.
"""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests

try:
    from eth_account import Account
    from web3 import Web3
    from x402 import x402ClientSync
    from x402.http.x402_http_client import x402HTTPClientSync
    from x402.mechanisms.evm.exact.register import register_exact_evm_client
    from x402.mechanisms.evm.signers import EthAccountSignerWithRPC
except Exception as exc:  # pragma: no cover
    print(f"missing python dependencies: {exc}", file=sys.stderr)
    sys.exit(2)


ROOT = Path(__file__).resolve().parents[3]

# Anonymous x402 demo configuration.
#
# Result JSON may include optional emotions fields. pose_2ds and pose_3ds are
# returned only by the standalone gait-pose API.
#
# Public APIs do not use a registered API Key. Instead, the client receives a
# 402 Payment Required challenge, signs an x402 payment payload with an EVM
# wallet private key, and retries the same API operation with payment headers.
EVM_PRIVATE_KEY = ""
BASE_URL = os.environ.get("GAIT_API_BASE_URL", "http://116.198.210.0:3005")

# Sequence input:
#   examples/seqs may contain nested folders.
#   Each leaf folder that directly contains images is treated as one sequence.
# Video input:
#   examples/video is scanned recursively for common video file extensions.
SEQ_ROOT = ROOT / "examples" / "seqs"
VIDEO_ROOT = ROOT / "examples" / "video"

# All raw API responses and derived similarity reports are written here.
RESULT_DIR = ROOT / "tmp" / "public_x402_batch_results"
TIMEOUT = 1800
POLL_INTERVAL = 2.0

ALLOWED_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
ALLOWED_VIDEO_SUFFIXES = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".mpeg", ".mpg", ".m4v"}

PERMIT2_ADDRESS = "0x000000000022D473030F116dDEE9F6B43aC78BA3"
MAX_UINT256 = 2**256 - 1
RPC_BY_NETWORK = {
    "eip155:8453": "https://base-rpc.publicnode.com",
    "eip155:137": "https://polygon-bor-rpc.publicnode.com",
    "eip155:42161": "https://arbitrum-one-rpc.publicnode.com",
}


def main() -> int:
    private_key = load_private_key()
    RESULT_DIR.mkdir(parents=True, exist_ok=True)

    # Discover all local test inputs before making API calls. The summary file
    # is written immediately so a partial run still records what was attempted.
    seq_dirs = collect_leaf_sequence_dirs(SEQ_ROOT)
    videos = collect_video_files(VIDEO_ROOT)
    summary: dict[str, Any] = {
        "started_at": iso_now(),
        "base_url": BASE_URL,
        "seq_root": str(SEQ_ROOT),
        "video_root": str(VIDEO_ROOT),
        "result_dir": str(RESULT_DIR),
        "sequence_count": len(seq_dirs),
        "video_count": len(videos),
        "sequences": [],
        "videos": [],
    }
    write_json(RESULT_DIR / "summary.json", summary)

    print(f"base_url={BASE_URL}")
    print(f"seq_root={SEQ_ROOT} leaf_sequences={len(seq_dirs)}")
    print(f"video_root={VIDEO_ROOT} videos={len(videos)}")
    print(f"result_dir={RESULT_DIR}")
    check_api_health()

    with requests.Session() as session:
        # Public gait sequence parsing is: create task -> upload frames -> preview
        # parse returns 402 -> pay x402 -> retry parse.
        for index, seq_dir in enumerate(seq_dirs, start=1):
            print(f"[sequence {index}/{len(seq_dirs)}] {seq_dir}")
            item = run_and_save("sequence", seq_dir, lambda: run_public_sequence_x402(session, private_key, seq_dir))
            summary["sequences"].append(item)
            write_json(RESULT_DIR / "summary.json", summary)

        # Public video parsing has two paid phases: phase 1 before SDK parsing
        # starts, and phase 2 before returning final sequence results.
        for index, video_path in enumerate(videos, start=1):
            print(f"[video {index}/{len(videos)}] {video_path}")
            item = run_and_save("video", video_path, lambda: run_public_video_x402(session, private_key, video_path))
            summary["videos"].append(item)
            write_json(RESULT_DIR / "summary.json", summary)

    # After all sequence API results are saved, compute pairwise dot-product
    # similarity across all successful standalone sequence results.
    sequence_similarity = compute_sequence_similarity_report(summary["sequences"])
    sequence_similarity_path = RESULT_DIR / "sequence_similarities.json"
    write_json(sequence_similarity_path, sequence_similarity)
    summary["sequence_similarity"] = {
        "result_file": str(sequence_similarity_path),
        "sequence_count": sequence_similarity["sequence_count"],
        "pair_count": sequence_similarity["pair_count"],
    }
    summary["finished_at"] = iso_now()
    write_json(RESULT_DIR / "summary.json", summary)
    print(f"summary_path={RESULT_DIR / 'summary.json'}")
    print(f"sequence_similarity_path={sequence_similarity_path}")
    return 0


def run_and_save(kind: str, source: Path, fn) -> dict[str, Any]:
    """Run one API operation and persist its full result or error as JSON."""
    started_at = iso_now()
    safe_name = safe_filename(str(source.relative_to(ROOT) if source.is_relative_to(ROOT) else source))
    out_path = RESULT_DIR / kind / f"{safe_name}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = fn()
        record = {
            "kind": kind,
            "source": str(source),
            "started_at": started_at,
            "finished_at": iso_now(),
            "ok": True,
            "result": result,
        }
        print(f"{kind}=ok source={source} result_file={out_path}")
    except Exception as exc:
        record = {
            "kind": kind,
            "source": str(source),
            "started_at": started_at,
            "finished_at": iso_now(),
            "ok": False,
            "error": str(exc),
        }
        selected_accept = getattr(exc, "selected_accept", None)
        if selected_accept:
            record["selected_accept"] = selected_accept
        print(f"{kind}=failed source={source} error={exc}", file=sys.stderr)
    write_json(out_path, record)
    return {
        "source": str(source),
        "ok": bool(record["ok"]),
        "result_file": str(out_path),
        "task_id": nested_get(record, "result", "task_id") or "",
        "error": record.get("error", ""),
        "selected_accept": record.get("selected_accept"),
    }


def run_public_sequence_x402(session: requests.Session, private_key: str, seq_dir: Path) -> dict[str, Any]:
    """Parse one anonymous public sequence directory with x402 payment.

    API flow:
      1. POST /v1/public/sequences with frame_count.
      2. PUT each frame to the upload_url returned by step 1.
      3. POST /parse once without payment. The server returns HTTP 402 and a
         PAYMENT-REQUIRED challenge header.
      4. Sign and send the x402 payment, then retry /parse.
    """
    frames = collect_frames(seq_dir)
    created = request_json(session, "POST", "/v1/public/sequences", json_payload={"frame_count": len(frames)})
    task_id = created["task_id"]
    task_token = created["task_token"]
    uploads = created["uploads"]
    if len(uploads) != len(frames):
        raise RuntimeError(f"upload count mismatch: api={len(uploads)} local={len(frames)}")

    parse_frames: list[dict[str, Any]] = []
    for index, frame in enumerate(frames):
        upload = uploads[index]
        upload_binary(session, upload["upload_url"], frame)
        # Use the server-provided index and object_key rather than local
        # filenames. This keeps parsing independent from client file paths.
        parse_frames.append({"index": upload["index"], "object_key": upload["object_key"]})

    # The first parse request intentionally has no payment headers. It asks the
    # server for the exact x402 challenge for this task/order.
    parse_url = f"/v1/public/sequences/{task_id}/parse"
    preview = raw_request(
        session,
        "POST",
        parse_url,
        headers={"X-Task-Token": task_token, "Content-Type": "application/json"},
        json_payload={"frames": parse_frames},
    )
    if preview.status_code != 402:
        raise RuntimeError(f"expected 402 for public sequence preview, got {preview.status_code}: {preview.text}")
    paid_resp, selected = pay_x402_request(session, private_key, preview, parse_url, {"frames": parse_frames}, task_token)
    if paid_resp.status_code != 200:
        raise_http(paid_resp)
    parsed = paid_resp.json()
    return {
        "task_id": task_id,
        "task_token": task_token,
        "sequence_dir": str(seq_dir),
        "frame_count": len(frames),
        "selected_accept": selected,
        "sequence_count": parsed.get("sequence_count") or len(parsed.get("sequences") or []),
        "parsed": parsed,
    }


def run_public_video_x402(session: requests.Session, private_key: str, video_path: Path) -> dict[str, Any]:
    """Upload and parse one anonymous public video file with x402 payment.

    Public video billing is split into two phases:
      phase 1: pay after upload, before parsing starts.
      phase 2: pay after parsing, before final result retrieval.
    """
    filename = video_path.name
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    created = request_json(
        session,
        "POST",
        "/v1/public/videos",
        json_payload={
            "filename": filename,
            "content_type": content_type,
            "size_bytes": video_path.stat().st_size,
        },
    )
    task_id = created["task_id"]
    task_token = created["task_token"]
    upload_binary(session, created["upload_url"], video_path, content_type=content_type)

    # Phase 1 payment starts video processing. The preview request returns 402,
    # then pay_x402_request signs and retries the same endpoint.
    settle1_url = f"/v1/public/videos/{task_id}/settle-phase1"
    preview1 = raw_request(
        session,
        "POST",
        settle1_url,
        headers={"X-Task-Token": task_token, "Content-Type": "application/json"},
        json_payload={},
    )
    if preview1.status_code != 402:
        raise RuntimeError(f"expected 402 for public video phase1 preview, got {preview1.status_code}: {preview1.text}")
    paid1, selected1 = pay_x402_request(session, private_key, preview1, settle1_url, {}, task_token)
    if paid1.status_code != 200:
        raise_http(paid1)

    result_url = f"/v1/public/videos/{task_id}/result"
    deadline = time.time() + TIMEOUT
    selected2: dict[str, Any] | None = None
    final_result: dict[str, Any] | None = None
    while time.time() < deadline:
        resp = raw_request(session, "GET", result_url, headers={"X-Task-Token": task_token})
        if resp.status_code == 200:
            final_result = resp.json()
            break
        if resp.status_code == 402:
            # Phase 2 is required after SDK parsing finishes. Paying phase 2
            # unlocks the final parsed sequence list.
            settle2_url = f"/v1/public/videos/{task_id}/settle-phase2"
            preview2 = raw_request(
                session,
                "POST",
                settle2_url,
                headers={"X-Task-Token": task_token, "Content-Type": "application/json"},
                json_payload={},
            )
            if preview2.status_code != 402:
                raise RuntimeError(f"expected 402 for public video phase2 preview, got {preview2.status_code}: {preview2.text}")
            paid2, selected2 = pay_x402_request(session, private_key, preview2, settle2_url, {}, task_token)
            if paid2.status_code != 200:
                raise_http(paid2)
            time.sleep(POLL_INTERVAL)
            continue
        if resp.status_code != 409:
            raise_http(resp)
        time.sleep(POLL_INTERVAL)
    if final_result is None:
        raise RuntimeError(f"timed out waiting for public video result: task_id={task_id}")
    similarities = compute_video_similarity(final_result)
    return {
        "task_id": task_id,
        "task_token": task_token,
        "video_path": str(video_path),
        "phase1_accept": selected1,
        "phase2_accept": selected2,
        "result": final_result,
        "similarities": similarities,
    }


def pay_x402_request(
    session: requests.Session,
    private_key: str,
    preview_response: requests.Response,
    path: str,
    request_payload: dict[str, Any],
    task_token: str,
) -> tuple[requests.Response, dict[str, Any]]:
    """Read a 402 x402 challenge, sign payment, and retry the protected API.

    The server sends PAYMENT-REQUIRED as base64 JSON. It may contain several
    accepted payment routes, for example Base USDC/eip3009 or Base USDT/permit2.
    This demo chooses an affordable route, builds the matching x402 client, and
    retries the original request with payment headers.
    """
    payment_required_header = preview_response.headers.get("PAYMENT-REQUIRED") or preview_response.headers.get("X-Payment-Required")
    if not payment_required_header:
        raise RuntimeError("missing PAYMENT-REQUIRED header")
    challenge = json.loads(base64.b64decode(payment_required_header).decode("utf-8"))
    accepts = challenge.get("accepts") or []
    if not accepts:
        raise RuntimeError("x402 accepts is empty")
    selected = select_affordable_accept(private_key, accepts)

    # assetTransferMethod decides whether the wallet must pre-approve Permit2.
    # eip3009 routes use token authorization signatures and do not need ERC-20
    # allowance. permit2 routes need ERC-20 allowance to the Permit2 contract.
    route = {
        "network": selected["network"],
        "asset": selected["asset"],
        "method": ((selected.get("extra") or {}).get("assetTransferMethod") or "exact").lower(),
    }
    if route["method"] == "permit2":
        ensure_permit2_allowance(private_key, route, selected["amount"])

    # Important: force the x402 SDK to sign the exact accept route selected
    # above. Without this selector, a challenge with multiple accepts on the
    # same network could make the SDK sign a different token than expected.
    client = build_route_client(private_key, route["network"], selected)
    http_client = x402HTTPClientSync(client)
    payment_required = http_client.get_payment_required_response(
        lambda name: preview_response.headers.get(name),
        safe_json(preview_response),
    )
    payment_payload = client.create_payment_payload(payment_required)
    payment_headers = http_client.encode_payment_signature_header(payment_payload)
    headers = {"X-Task-Token": task_token, "Content-Type": "application/json", **payment_headers}
    paid_resp = raw_request(session, "POST", path, headers=headers, json_payload=request_payload)
    if paid_resp.status_code >= 400:
        err = X402PaymentError(f"HTTP {paid_resp.status_code} POST {urljoin(BASE_URL.rstrip('/') + '/', path.lstrip('/'))}\n{paid_resp.text}")
        err.selected_accept = selected
        raise err
    return paid_resp, selected


def select_affordable_accept(private_key: str, accepts: list[dict[str, Any]]) -> dict[str, Any]:
    """Choose a payment route whose token balance can cover the required amount."""
    ranked: list[tuple[int, int, dict[str, Any]]] = []
    for index, accept in enumerate(accepts):
        try:
            balance = token_balance(private_key, accept["network"], accept["asset"])
        except Exception:
            balance = -1
        ranked.append((index, balance, accept))
    affordable = [item for item in ranked if item[1] >= int(item[2]["amount"])]
    if affordable:
        affordable.sort(key=lambda item: (-item[1], item[0]))
        return affordable[0][2]
    ranked.sort(key=lambda item: (-item[1], item[0]))
    selected = ranked[0][2]
    best_balance = ranked[0][1]
    needed = int(selected["amount"])
    symbol = ((selected.get("extra") or {}).get("assetSymbol")) or "token"
    raise RuntimeError(f"no affordable x402 accept: best route {selected.get('network', '')} {symbol} balance={best_balance} needed={needed}")


def select_payment_requirement(selected_accept: dict[str, Any], requirements: list[Any]) -> Any:
    """Return the SDK payment requirement matching the selected accept route."""
    target_network = str(selected_accept.get("network") or "").strip()
    target_asset = str(selected_accept.get("asset") or "").strip().lower()
    target_amount = str(selected_accept.get("amount") or "").strip()
    for requirement in requirements:
        network = str(getattr(requirement, "network", "")).strip()
        asset = str(getattr(requirement, "asset", "")).strip().lower()
        amount = str(getattr(requirement, "amount", "")).strip()
        if network == target_network and asset == target_asset and amount == target_amount:
            return requirement
    for requirement in requirements:
        network = str(getattr(requirement, "network", "")).strip()
        asset = str(getattr(requirement, "asset", "")).strip().lower()
        if network == target_network and asset == target_asset:
            return requirement
    symbol = ((selected_accept.get("extra") or {}).get("assetSymbol")) or "token"
    raise RuntimeError(f"x402 selected accept not found in requirements: {target_network} {symbol} {target_asset}")


def token_balance(private_key: str, network: str, asset: str) -> int:
    """Read ERC-20 token balance for the payer on one EVM network."""
    rpc_url = RPC_BY_NETWORK.get(network)
    if not rpc_url:
        raise RuntimeError(f"no RPC configured for network {network}")
    web3 = Web3(Web3.HTTPProvider(rpc_url))
    account = Account.from_key(private_key)
    token = web3.eth.contract(
        address=Web3.to_checksum_address(asset),
        abi=[{
            "constant": True,
            "inputs": [{"name": "owner", "type": "address"}],
            "name": "balanceOf",
            "outputs": [{"name": "", "type": "uint256"}],
            "stateMutability": "view",
            "type": "function",
        }],
    )
    return int(token.functions.balanceOf(Web3.to_checksum_address(account.address)).call())


def build_route_client(private_key: str, network: str, selected_accept: dict[str, Any] | None = None) -> x402ClientSync:
    """Build an x402 EVM client for one network and optional fixed accept route."""
    rpc_url = RPC_BY_NETWORK.get(network)
    if not rpc_url:
        raise RuntimeError(f"no RPC configured for network {network}")
    signer = EthAccountSignerWithRPC(Account.from_key(private_key), rpc_url)
    if selected_accept is None:
        client = x402ClientSync()
    else:
        client = x402ClientSync(
            payment_requirements_selector=lambda version, reqs: select_payment_requirement(selected_accept, reqs)
        )
    register_exact_evm_client(client, signer, networks=network)
    return client


def ensure_permit2_allowance(private_key: str, route: dict[str, str], needed_amount: str) -> None:
    """Approve Permit2 for USDT-style routes when allowance is insufficient."""
    rpc_url = RPC_BY_NETWORK.get(route["network"])
    if not rpc_url:
        raise RuntimeError(f"no RPC configured for network {route['network']}")
    web3 = Web3(Web3.HTTPProvider(rpc_url))
    account = Account.from_key(private_key)
    token = web3.eth.contract(
        address=Web3.to_checksum_address(route["asset"]),
        abi=[
            {
                "constant": True,
                "inputs": [{"name": "owner", "type": "address"}, {"name": "spender", "type": "address"}],
                "name": "allowance",
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
        ],
    )
    owner = Web3.to_checksum_address(account.address)
    spender = Web3.to_checksum_address(PERMIT2_ADDRESS)
    allowance = int(token.functions.allowance(owner, spender).call())
    if allowance >= int(needed_amount):
        return
    tx = token.functions.approve(spender, MAX_UINT256).build_transaction(
        {"from": owner, "nonce": web3.eth.get_transaction_count(owner), "chainId": web3.eth.chain_id}
    )
    tx["gas"] = int(web3.eth.estimate_gas(tx) * 1.2)
    if "maxFeePerGas" not in tx and "gasPrice" not in tx:
        latest = web3.eth.get_block("latest")
        base_fee = latest.get("baseFeePerGas")
        priority = web3.to_wei(0.02, "gwei")
        if base_fee is not None:
            tx["maxPriorityFeePerGas"] = priority
            tx["maxFeePerGas"] = int(base_fee * 2 + priority)
        else:
            tx["gasPrice"] = web3.eth.gas_price
    signed = account.sign_transaction(tx)
    tx_hash = web3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = web3.eth.wait_for_transaction_receipt(tx_hash, timeout=300)
    if receipt.status != 1:
        raise RuntimeError(f"permit2 approve failed: {tx_hash.hex()}")


def collect_leaf_sequence_dirs(root: Path) -> list[Path]:
    """Return leaf directories that directly contain image frames."""
    dirs: list[Path] = []
    if not root.exists():
        return dirs
    for current, child_dirs, files in os.walk(root):
        image_count = sum(1 for name in files if Path(name).suffix.lower() in ALLOWED_IMAGE_SUFFIXES)
        if image_count > 0 and not child_dirs:
            dirs.append(Path(current))
    return sorted(dirs, key=lambda path: str(path))


def collect_video_files(root: Path) -> list[Path]:
    """Return supported video files under root, including nested directories."""
    if not root.exists():
        return []
    return sorted(
        [path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in ALLOWED_VIDEO_SUFFIXES],
        key=lambda path: str(path),
    )


def collect_frames(seq_dir: Path) -> list[Path]:
    """Return image frames in deterministic filename order."""
    frames = [path for path in seq_dir.iterdir() if path.is_file() and path.suffix.lower() in ALLOWED_IMAGE_SUFFIXES]
    frames.sort(key=lambda path: path.name)
    if not frames:
        raise RuntimeError(f"no frames under {seq_dir}")
    return frames


def compute_sequence_similarity_report(sequence_items: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute pairwise feature similarity across successful sequence results."""
    sequences: list[dict[str, Any]] = []
    for item in sequence_items:
        if not item.get("ok"):
            continue
        result_file = item.get("result_file")
        if not result_file:
            continue
        record = read_json(Path(result_file))
        parsed_sequences = nested_get(record, "result", "parsed", "sequences")
        if not isinstance(parsed_sequences, list) or not parsed_sequences or not isinstance(parsed_sequences[0], dict):
            continue
        sequence = parsed_sequences[0]
        identity = sequence_identity(sequence, source=item.get("source", ""), task_id=item.get("task_id", ""))
        sequences.append({"identity": identity, "features": extract_features(sequence)})

    pairs: list[dict[str, Any]] = []
    for left_index in range(len(sequences)):
        for right_index in range(left_index + 1, len(sequences)):
            left = sequences[left_index]
            right = sequences[right_index]
            pairs.append({
                "left": left["identity"],
                "right": right["identity"],
                "similarity": feature_similarity(left["features"], right["features"]),
            })
    return {
        "generated_at": iso_now(),
        "sequence_count": len(sequences),
        "pair_count": len(pairs),
        "pairs": pairs,
    }


def compute_video_similarity(video_result: dict[str, Any]) -> dict[str, Any]:
    """Compute pairwise feature similarity among sequences in one video."""
    raw_sequences = video_result.get("sequences") or []
    sequences: list[dict[str, Any]] = []
    for index, sequence in enumerate(raw_sequences):
        if not isinstance(sequence, dict):
            continue
        identity = sequence_identity(sequence, index=index)
        sequences.append({"identity": identity, "features": extract_features(sequence)})

    pairs: list[dict[str, Any]] = []
    for left_index in range(len(sequences)):
        for right_index in range(left_index + 1, len(sequences)):
            left = sequences[left_index]
            right = sequences[right_index]
            pairs.append({
                "left": left["identity"],
                "right": right["identity"],
                "similarity": feature_similarity(left["features"], right["features"]),
            })
    return {
        "sequence_count": len(sequences),
        "pair_count": len(pairs),
        "pairs": pairs,
    }


def extract_features(sequence: dict[str, Any]) -> dict[str, list[float]]:
    """Read the three feature vectors used for similarity comparison."""
    return {
        "gait_feature": numeric_vector(sequence.get("gait_feature")),
        "reid_feature": numeric_vector(sequence.get("reid_feature")),
        "face_feature": numeric_vector(sequence.get("face_feature")),
    }


SAME_PERSON_THRESHOLD = 0.7


def feature_similarity(left: dict[str, list[float]], right: dict[str, list[float]]) -> dict[str, Any]:
    """Compute per-feature dot products plus fused identity similarity."""
    scores = {
        name: dot_product(left.get(name) or [], right.get(name) or [])
        for name in ("gait_feature", "reid_feature", "face_feature")
    }
    gait_sim = score_or_zero(scores["gait_feature"])
    reid_sim = score_or_zero(scores["reid_feature"])
    face_sim = score_or_zero(scores["face_feature"])
    fused = fused_identity_similarity(face_sim, gait_sim, reid_sim)
    scores["fused_similarity"] = {
        "score": fused,
        "threshold": SAME_PERSON_THRESHOLD,
        "same_person_likely": fused > SAME_PERSON_THRESHOLD,
        "inputs": {
            "face_similarity": face_sim,
            "gait_similarity": gait_sim,
            "reid_similarity": reid_sim,
        },
    }
    return scores


def score_or_zero(item: dict[str, Any]) -> float:
    score = item.get("score")
    return float(score) if isinstance(score, (int, float)) else 0.0


def fused_identity_similarity(face_sim: float, gait_sim: float, reid_sim: float) -> float:
    """Fuse face, gait and ReID similarities. Scores above 0.7 likely indicate the same person."""
    result = max(gait_sim, 0)
    if face_sim > 0.45:
        result = max(gait_sim, 0.7)
    elif face_sim > 0.35:
        result *= 1.1
    elif face_sim > 0.4:
        result *= 1.1
    elif face_sim != 0 and face_sim < 0.1:
        result *= 0.9
    if reid_sim > 0.8:
        result *= 1.1
    if face_sim > 0.5:
        result *= 1.1
    if face_sim > 0.6:
        result *= 1.1
    return min(result, 1.0)


def dot_product(left: list[float], right: list[float]) -> dict[str, Any]:
    """Return dot-product similarity and dimension diagnostics."""
    left_len = len(left)
    right_len = len(right)
    if left_len == 0 or right_len == 0:
        return {
            "score": None,
            "left_dim": left_len,
            "right_dim": right_len,
            "used_dim": 0,
            "skipped": True,
            "reason": "empty_feature",
        }
    used_dim = min(left_len, right_len)
    return {
        "score": sum(left[index] * right[index] for index in range(used_dim)),
        "left_dim": left_len,
        "right_dim": right_len,
        "used_dim": used_dim,
        "skipped": False,
        "dimension_mismatch": left_len != right_len,
    }


def numeric_vector(value: Any) -> list[float]:
    """Keep only numeric feature values and convert them to float."""
    if not isinstance(value, list):
        return []
    vector: list[float] = []
    for item in value:
        if isinstance(item, (int, float)):
            vector.append(float(item))
    return vector


def sequence_identity(sequence: dict[str, Any], source: str = "", task_id: str = "", index: int | None = None) -> dict[str, Any]:
    """Build a small stable identity block for similarity report entries."""
    identity: dict[str, Any] = {
        "sequence_id": sequence.get("sequence_id") or "",
        "frame_count": sequence.get("frame_count") or 0,
    }
    if source:
        identity["source"] = source
    if task_id:
        identity["task_id"] = task_id
    if index is not None:
        identity["index"] = index
    batch = sequence.get("batch")
    if batch is not None:
        identity["batch"] = batch
    return identity


def upload_binary(session: requests.Session, upload_url: str, path: Path, content_type: str | None = None) -> None:
    """Upload one binary file to a service-relative upload URL."""
    mime = content_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    url = urljoin(BASE_URL.rstrip("/") + "/", upload_url.lstrip("/"))
    resp = session.put(url, data=path.read_bytes(), headers={"Content-Type": mime, "Accept": "application/json"}, timeout=TIMEOUT)
    if resp.status_code >= 400:
        raise_http(resp)


def request_json(session: requests.Session, method: str, path: str, headers: dict[str, str] | None = None, json_payload: Any | None = None) -> dict[str, Any]:
    """Send a JSON API request and raise a readable error for non-2xx replies."""
    resp = raw_request(session, method, path, headers=headers, json_payload=json_payload)
    if resp.status_code >= 400:
        raise_http(resp)
    return resp.json() if resp.text else {}


def raw_request(session: requests.Session, method: str, path: str, headers: dict[str, str] | None = None, json_payload: Any | None = None) -> requests.Response:
    req_headers = {"Accept": "application/json"}
    if headers:
        req_headers.update(headers)
    url = urljoin(BASE_URL.rstrip("/") + "/", path.lstrip("/"))
    return session.request(method, url, headers=req_headers, json=json_payload, timeout=TIMEOUT)


def check_api_health() -> None:
    """Fail fast when the configured API endpoint is not reachable."""
    url = urljoin(BASE_URL.rstrip("/") + "/", "healthz")
    try:
        resp = requests.get(url, headers={"Accept": "application/json"}, timeout=5)
    except Exception as exc:
        raise RuntimeError(f"api health check failed: {url}: {exc}") from exc
    if resp.status_code != 200:
        raise RuntimeError(f"api health check failed: HTTP {resp.status_code} {url}\n{resp.text}")


def raise_http(resp: requests.Response) -> None:
    raise RuntimeError(f"HTTP {resp.status_code} {resp.request.method} {resp.request.url}\n{resp.text}")


class X402PaymentError(RuntimeError):
    selected_accept: dict[str, Any] | None = None


def safe_json(resp: requests.Response) -> Any:
    try:
        return resp.json()
    except Exception:
        return {}


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_private_key() -> str:
    private_key = EVM_PRIVATE_KEY.strip() or os.environ.get("GAIT_TEST_WALLET_PRIVATE_KEY", "").strip()
    if not private_key:
        raise RuntimeError("fill EVM_PRIVATE_KEY in examples/anonymous/python/anonymous_sequence_and_video_x402_demo.py or export GAIT_TEST_WALLET_PRIVATE_KEY")
    return private_key if private_key.startswith("0x") else "0x" + private_key


def safe_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_")[:180] or "item"


def nested_get(data: dict[str, Any], *keys: str) -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def iso_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as exc:
        print(f"fatal_error={exc}", file=sys.stderr)
        raise
