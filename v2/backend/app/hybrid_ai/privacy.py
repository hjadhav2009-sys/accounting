from __future__ import annotations

import re
import base64
from io import BytesIO
from dataclasses import dataclass
from hashlib import sha256
from typing import Iterable, Sequence

from PIL import Image, ImageDraw

from .models import PrivacyMode


@dataclass(frozen=True)
class SanitizedPayload:
    text: str
    mapping: dict[str, str]
    redaction_counts: dict[str, int]
    digest: str


@dataclass(frozen=True)
class RedactedImage:
    png_bytes: bytes
    digest: str
    width: int
    height: int
    redaction_count: int


class PrivacyService:
    """Deterministic local masking. The reversible map must never leave the backend."""

    _patterns = (
        ("PAN", re.compile(r"(?<![A-Z0-9])[A-Z]{5}[0-9]{4}[A-Z](?![A-Z0-9])", re.I)),
        ("EMAIL", re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)),
        ("PHONE", re.compile(r"(?<!\d)(?:\+?91[-\s]?)?[6-9]\d{9}(?!\d)")),
        ("UPI", re.compile(r"\b[A-Z0-9._-]{2,}@[A-Z]{2,}\b", re.I)),
        ("BANK", re.compile(r"(?<!\d)\d{9,18}(?!\d)")),
    )

    def sanitize(self, text: str, mode: PrivacyMode = PrivacyMode.BALANCED,
                 known_entities: Iterable[str] = ()) -> SanitizedPayload:
        if mode == PrivacyMode.OFF_ADMIN_ONLY:
            return SanitizedPayload(text, {}, {}, sha256(text.encode()).hexdigest())
        output = text
        mapping: dict[str, str] = {}
        counts: dict[str, int] = {}

        def replace(kind: str, match: re.Match[str]) -> str:
            value = match.group(0)
            if mode == PrivacyMode.BALANCED and kind == "BANK":
                replacement = f"<BANK_*{value[-4:]}>"
            else:
                replacement = f"<{kind}_{counts.get(kind, 0) + 1}>"
            counts[kind] = counts.get(kind, 0) + 1
            mapping[replacement] = value
            return replacement

        for kind, pattern in self._patterns:
            output = pattern.sub(lambda match, k=kind: replace(k, match), output)
        for entity in sorted({item.strip() for item in known_entities if item.strip()}, key=len, reverse=True):
            pattern = re.compile(re.escape(entity), re.I)
            output = pattern.sub(lambda match: replace("ENTITY", match), output)
        return SanitizedPayload(output, mapping, counts, sha256(output.encode()).hexdigest())

    @staticmethod
    def restore(text: str, mapping: dict[str, str]) -> str:
        for token, value in mapping.items():
            text = text.replace(token, value)
        return text

    @staticmethod
    def payload_preview(value: SanitizedPayload) -> dict[str, object]:
        return {
            "sanitized_text": value.text,
            "redaction_counts": value.redaction_counts,
            "sanitized_sha256": value.digest,
            "reversible_map_transmitted": False,
        }

    @staticmethod
    def redact_image(image_bytes: bytes, boxes: Sequence[tuple[int, int, int, int]]) -> RedactedImage:
        """Burn opaque pixels into a fresh metadata-free raster image."""
        if not image_bytes: raise ValueError("image is empty")
        with Image.open(BytesIO(image_bytes)) as source:
            image = Image.new("RGB", source.size, "white")
            image.paste(source.convert("RGB"))
        draw = ImageDraw.Draw(image)
        width, height = image.size
        for left, top, right, bottom in boxes:
            if not (0 <= left < right <= width and 0 <= top < bottom <= height):
                raise ValueError("redaction box is outside image bounds")
            draw.rectangle((left, top, right - 1, bottom - 1), fill=(0, 0, 0))
        output = BytesIO()
        image.save(output, format="PNG", optimize=False)
        content = output.getvalue()
        return RedactedImage(content, sha256(content).hexdigest(), width, height, len(boxes))

    @staticmethod
    def cloud_payload_preview(value: SanitizedPayload, *, image: RedactedImage | None,
                              model: str, task: str, estimated_usage: int | None = None) -> dict[str, object]:
        preview = PrivacyService.payload_preview(value)
        preview.update({"model": model, "task": task, "estimated_usage": estimated_usage,
                        "credentials_included": False})
        if image:
            preview.update({
                "sanitized_image_data_url": "data:image/png;base64," + base64.b64encode(image.png_bytes).decode("ascii"),
                "sanitized_image_sha256": image.digest,
                "image_redaction_count": image.redaction_count,
                "image_metadata_transmitted": False,
            })
        return preview
