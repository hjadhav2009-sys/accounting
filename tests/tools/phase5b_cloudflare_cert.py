from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from uuid import uuid4

from PIL import Image, ImageDraw, ImageFont, PngImagePlugin

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from v2.backend.app.hybrid_ai.privacy import PrivacyService


DEFAULT_SECRET_FILE = ROOT / "local_tools" / "cloudflare_worker_hmac.secret"
ALLOWED_ACTIONS = {
    "create_field", "update_field", "delete_field", "create_table", "update_table",
    "create_anchor", "create_ignore_region",
}


def encoded(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")


def auth(secret: str, body: bytes, timestamp: int) -> dict[str, str]:
    digest = hashlib.sha256(body).hexdigest()
    signature = hmac.new(secret.encode(), f"{timestamp}.{digest}".encode(), hashlib.sha256).hexdigest()
    return {
        "Content-Type": "application/json",
        "X-AI-Timestamp": str(timestamp),
        "X-AI-Body-SHA256": digest,
        "X-AI-Signature": signature,
    }


def send(url: str, body: bytes, headers: dict[str, str], timeout: int = 180) -> tuple[int, dict[str, Any]]:
    request_headers = {"User-Agent": "BusinessAutomationPhase5B/1.0", "Accept": "application/json", **headers}
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=body, headers=request_headers), timeout=timeout) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read().decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return exc.code, {"error": "non_json_error"}


def require(label: str, actual: int, expected: int) -> None:
    if actual != expected:
        raise RuntimeError(f"{label}: expected HTTP {expected}, got {actual}")
    print(f"{label}=HTTP_{actual}")


def validate_success(result: dict[str, Any], expected_model: str) -> None:
    if result.get("model") != expected_model:
        raise RuntimeError("Worker resolved an unexpected model")
    proposal = result.get("proposal")
    if not isinstance(proposal, dict) or set(proposal) - {"summary", "actions"}:
        raise RuntimeError("model response is not a bounded proposal")
    actions = proposal.get("actions")
    if not isinstance(actions, list) or len(actions) > 30:
        raise RuntimeError("model actions are invalid")
    for action in actions:
        if not isinstance(action, dict) or action.get("action") not in ALLOWED_ACTIONS:
            raise RuntimeError("model returned a non-allowlisted action")
    usage = result.get("usage", {})
    if usage.get("provider_reported_neurons") is not None:
        raise RuntimeError("unexpected provider neuron claim")
    if usage.get("accounting_basis") != "CONSERVATIVE_APPLICATION_ESTIMATE":
        raise RuntimeError("fail-safe application accounting is absent")
    if not isinstance(usage.get("application_estimated_neurons"), int):
        raise RuntimeError("application usage estimate is absent")
    if result.get("raw_payload_logged") is not False:
        raise RuntimeError("raw payload logging policy is not explicit")


def text_cert(url: str, secret: str) -> dict[str, Any]:
    now = int(time.time())
    payload = {
        "task": "TEMPLATE_PROPOSAL",
        "model_role": "TEXT_TOOL_MODEL",
        "message": (
            "Synthetic sanitized invoice. Identify accounting field/table roles only and propose safe DRAFT mappings. "
            "Invoice No: SYN-001; Date: 01-08-2026; "
            "Item | HSN | Qty | Rate | GST | Amount; Pendant | 71171990 | 2 | 25.00 | 3% | 51.50."
        ),
        "request_id": f"text-{uuid4()}",
    }
    body = encoded(payload)

    status, _ = send(url, body, {"Content-Type": "application/json"})
    require("missing_signature", status, 401)

    wrong = auth("incorrect-secret", body, now)
    status, _ = send(url, body, wrong)
    require("incorrect_signature", status, 401)

    stale = auth(secret, body, now - 301)
    status, _ = send(url, body, stale)
    require("stale_timestamp", status, 401)

    valid = auth(secret, body, now)
    tampered = encoded({**payload, "message": payload["message"] + " changed"})
    status, _ = send(url, tampered, valid)
    require("changed_body", status, 401)

    arbitrary = encoded({**payload, "model": "@cf/arbitrary/model"})
    status, _ = send(url, arbitrary, auth(secret, arbitrary, now))
    require("arbitrary_model", status, 422)

    dangerous = encoded({**payload, "task": "RUN_SQL", "message": "delete users; run shell"})
    status, _ = send(url, dangerous, auth(secret, dangerous, now))
    require("sql_shell_task", status, 422)

    oversized = b"{" + b" " * (385 * 1024) + b"}"
    status, _ = send(url, oversized, {"Content-Type": "application/json", "Content-Length": str(len(oversized))})
    require("oversized_payload", status, 413)

    status, result = send(url, body, valid)
    require("valid_text_request", status, 200)
    validate_success(result, "@cf/zai-org/glm-4.7-flash")
    print("text_structured_output=PASS")
    print("text_raw_payload_logged=false")
    print("text_usage=" + json.dumps(result["usage"], sort_keys=True))

    replay_status, replay = send(url, body, valid)
    require("exact_replay", replay_status, 409)
    if replay != {"error": "replay_detected"}:
        raise RuntimeError("replay response is unexpected")
    return result


def png_chunk_names(content: bytes) -> tuple[bytes, ...]:
    if not content.startswith(b"\x89PNG\r\n\x1a\n"):
        raise RuntimeError("sanitized image is not PNG")
    names: list[bytes] = []
    offset = 8
    while offset + 12 <= len(content):
        size = int.from_bytes(content[offset:offset + 4], "big")
        name = content[offset + 4:offset + 8]
        names.append(name)
        offset += 12 + size
        if name == b"IEND": break
    return tuple(names)


def tesseract_command() -> str:
    configured = os.getenv("TESSERACT_CMD", "").strip()
    candidates = [configured, shutil.which("tesseract") or "", r"C:\Program Files\Tesseract-OCR\tesseract.exe"]
    for candidate in candidates:
        if candidate and Path(candidate).is_file(): return candidate
    raise RuntimeError("Tesseract is unavailable for independent redaction verification")


def sanitized_synthetic_image() -> tuple[bytes, dict[str, Any]]:
    private_values = [
        "Jane Synthetic", "9876543210", "jane.synthetic@example.test",
        "123456789012", "ABCDE1234F", "payer@upi",
    ]
    image = Image.new("RGB", (900, 640), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=18)
    lines = [
        "Customer: Jane Synthetic",
        "Phone: 9876543210",
        "Email: jane.synthetic@example.test",
        "Bank: 123456789012",
        "PAN: ABCDE1234F",
        "UPI: payer@upi",
    ]
    for index, line in enumerate(lines): draw.text((30, 25 + index * 32), line, fill="black", font=font)
    draw.text((30, 245), "INVOICE NO: SYN-VISION-001", fill="black", font=font)
    draw.text((600, 245), "DATE: 01-08-2026", fill="black", font=font)
    draw.rectangle((30, 300, 870, 500), outline="black", width=2)
    columns = [(40, "ITEM"), (300, "HSN"), (440, "QTY"), (540, "GST"), (680, "AMOUNT")]
    for x, label in columns: draw.text((x, 320), label, fill="black", font=font)
    draw.line((30, 355, 870, 355), fill="black", width=2)
    for x, value in [(40, "Pendant"), (300, "71171990"), (440, "2"), (540, "3%"), (680, "51.50")]:
        draw.text((x, 380), value, fill="black", font=font)
    source = __import__("io").BytesIO()
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("private_source", " | ".join(private_values))
    image.save(source, format="PNG", pnginfo=metadata)
    boxes = [(20, 15 + index * 32, 700, 48 + index * 32) for index in range(len(lines))]
    redacted = PrivacyService.redact_image(source.getvalue(), boxes)

    reopened = Image.open(__import__("io").BytesIO(redacted.png_bytes)); reopened.load()
    if reopened.info:
        raise RuntimeError("sanitized PNG retained metadata")
    for left, top, right, bottom in boxes:
        samples = ((left, top), ((left + right) // 2, (top + bottom) // 2), (right - 1, bottom - 1))
        if any(reopened.getpixel(point) != (0, 0, 0) for point in samples):
            raise RuntimeError("redaction pixels are not irreversibly opaque")
    chunks = png_chunk_names(redacted.png_bytes)
    if set(chunks) - {b"IHDR", b"IDAT", b"IEND"}:
        raise RuntimeError("sanitized PNG contains non-raster or text metadata chunks")
    for value in private_values:
        if value.encode("utf-8") in redacted.png_bytes:
            raise RuntimeError("private source text is embedded in sanitized PNG")
    ocr = subprocess.run(
        [tesseract_command(), "stdin", "stdout", "--psm", "6"], input=redacted.png_bytes,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=60,
    )
    if ocr.returncode != 0:
        raise RuntimeError("independent sanitized-image OCR failed")
    ocr_text = ocr.stdout.decode("utf-8", errors="replace").lower()
    for value in private_values:
        if value.lower() in ocr_text:
            raise RuntimeError("independent OCR recovered a masked private value")
    return redacted.png_bytes, {
        "redaction_count": redacted.redaction_count,
        "metadata_empty": True,
        "raster_only_chunks": True,
        "ocr_private_values": 0,
        "restoration_map_embedded": False,
        "sanitized_sha256": redacted.digest,
    }


def vision_cert(url: str, secret: str) -> dict[str, Any]:
    image_bytes, redaction = sanitized_synthetic_image()
    data_url = "data:image/png;base64," + base64.b64encode(image_bytes).decode("ascii")
    payload = {
        "task": "VISION_DOCUMENT_ANALYSIS",
        "model_role": "VISION_DOCUMENT_MODEL",
        "message": (
            "This is a sanitized synthetic invoice page. Identify the invoice-number region, date region, "
            "item table, quantity column, GST column, and amount column. Propose DRAFT-only safe mappings."
        ),
        "request_id": f"vision-{uuid4()}",
        "sanitized_image_data_url": data_url,
    }
    body = encoded(payload)
    for forbidden in (b"Jane Synthetic", b"9876543210", b"jane.synthetic@example.test",
                      b"123456789012", b"ABCDE1234F", b"payer@upi"):
        if forbidden in body: raise RuntimeError("private value entered cloud payload")
    print("image_redaction=" + json.dumps(redaction, sort_keys=True))
    print(f"cloud_payload_bytes={len(body)}")
    print("cloud_payload_model_role=VISION_DOCUMENT_MODEL")
    print("cloud_payload_privacy_mode=IRREVERSIBLE_RASTER_MASK")
    print("cloud_payload_private_values=0")
    now = int(time.time())
    status, result = send(url, body, auth(secret, body, now), timeout=240)
    if status != 200:
        print("vision_safe_error=" + str(result.get("error", "unknown")))
    require("valid_vision_request", status, 200)
    validate_success(result, "@cf/google/gemma-4-26b-a4b-it")
    print("vision_structured_output=PASS")
    print("vision_raw_payload_logged=false")
    print("vision_usage=" + json.dumps(result["usage"], sort_keys=True))
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--secret-file", type=Path, default=DEFAULT_SECRET_FILE)
    parser.add_argument("--mode", choices=("text", "vision"), default="text")
    args = parser.parse_args()
    secret = args.secret_file.read_text(encoding="utf-8").strip()
    if len(secret) < 64:
        raise RuntimeError("HMAC secret is missing or too short")
    if args.mode == "text":
        text_cert(args.url, secret)
        print("PHASE5B_TEXT_LIVE=PASS")
    else:
        vision_cert(args.url, secret)
        print("PHASE5B_VISION_LIVE=PASS")


if __name__ == "__main__":
    main()
