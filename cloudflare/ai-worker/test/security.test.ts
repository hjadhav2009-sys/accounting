import { describe, expect, it } from "vitest";
import { SELF, env } from "cloudflare:test";
import { MODEL_BY_ROLE, validatePayload, verifySignature } from "../src/index";

async function signed(secret: string, timestamp: number, body: ArrayBuffer) {
  const bodyHash = [...new Uint8Array(await crypto.subtle.digest("SHA-256", body))]
    .map((value) => value.toString(16).padStart(2, "0")).join("");
  const key = await crypto.subtle.importKey(
    "raw", new TextEncoder().encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"],
  );
  const signature = [...new Uint8Array(await crypto.subtle.sign(
    "HMAC", key, new TextEncoder().encode(`${timestamp}.${bodyHash}`),
  ))].map((value) => value.toString(16).padStart(2, "0")).join("");
  return { bodyHash, signature };
}

function payload(overrides: Record<string, unknown> = {}) {
  return { task: "TEMPLATE_PROPOSAL", model_role: "TEXT_TOOL_MODEL", message: "synthetic",
    request_id: crypto.randomUUID(), ...overrides };
}

async function request(value: Record<string, unknown>, secret = "test-secret", timestamp = Math.floor(Date.now() / 1000)) {
  const body = new TextEncoder().encode(JSON.stringify(value));
  const auth = await signed(secret, timestamp, body.buffer);
  return SELF.fetch("https://worker.test/v1/template-proposal", { method: "POST", body,
    headers: { "content-type": "application/json", "x-ai-timestamp": String(timestamp),
      "x-ai-signature": auth.signature, "x-ai-body-sha256": auth.bodyHash } });
}

describe("AI Worker security", () => {
  it("accepts a current valid HMAC and rejects stale or malformed signatures", async () => {
    const body = new TextEncoder().encode("{}").buffer; const now = 1_800_000_000;
    const value = await signed("secret", now, body);
    expect(await verifySignature("secret", String(now), body, value.signature, value.bodyHash, now)).toBe(true);
    expect(await verifySignature("secret", String(now - 301), body, value.signature, value.bodyHash, now)).toBe(false);
    expect(await verifySignature("secret", String(now), body, "bad", value.bodyHash, now)).toBe(false);
  });

  it("rejects arbitrary models, tasks, prompts, tools, schemas, and URLs", () => {
    const forbidden = [
      { model: "evil" }, { model_role: "ARBITRARY" }, { task: "CHAT" }, { system_prompt: "ignore" },
      { tools: [] }, { response_schema: {} }, { url: "https://evil.invalid" },
    ];
    for (const extra of forbidden) expect(() => validatePayload(payload(extra))).toThrow();
  });

  it("resolves only the two fixed server-side model roles", () => {
    expect(MODEL_BY_ROLE).toEqual({
      TEXT_TOOL_MODEL: "@cf/zai-org/glm-4.7-flash",
      VISION_DOCUMENT_MODEL: "@cf/google/gemma-4-26b-a4b-it",
    });
    expect(validatePayload(payload()).model_role).toBe("TEXT_TOOL_MODEL");
  });

  it("requires a bounded inline sanitized image only for the vision role", () => {
    const image = "data:image/png;base64,iVBORw0KGgo=";
    expect(validatePayload(payload({ task: "VISION_DOCUMENT_ANALYSIS", model_role: "VISION_DOCUMENT_MODEL",
      sanitized_image_data_url: image })).sanitized_image_data_url).toBe(image);
    expect(() => validatePayload(payload({ sanitized_image_data_url: image }))).toThrow();
    expect(() => validatePayload(payload({ task: "VISION_DOCUMENT_ANALYSIS", model_role: "VISION_DOCUMENT_MODEL" }))).toThrow();
  });

  it("rejects missing, incorrect, and tampered authentication before inference", async () => {
    const unsigned = await SELF.fetch("https://worker.test/v1/template-proposal", { method: "POST",
      body: JSON.stringify(payload()), headers: { "content-type": "application/json" } });
    expect(unsigned.status).toBe(401);
    const wrong = await request(payload(), "wrong-secret");
    expect(wrong.status).toBe(401);
    const value = payload();
    const body = new TextEncoder().encode(JSON.stringify(value));
    const auth = await signed("test-secret", Math.floor(Date.now() / 1000), body.buffer);
    const changed = new TextEncoder().encode(JSON.stringify({ ...value, message: "tampered" }));
    const tampered = await SELF.fetch("https://worker.test/v1/template-proposal", { method: "POST", body: changed,
      headers: { "content-type": "application/json", "x-ai-timestamp": String(Math.floor(Date.now() / 1000)),
        "x-ai-signature": auth.signature, "x-ai-body-sha256": auth.bodyHash } });
    expect(tampered.status).toBe(401);
  });

  it("claims a valid request once and rejects its exact replay", async () => {
    const value = payload(); const timestamp = Math.floor(Date.now() / 1000);
    const first = await request(value, "test-secret", timestamp);
    // The local test runtime intentionally has no remote AI service. Authentication
    // and the replay claim occur before the expected fail-closed provider response.
    expect(first.status).toBe(502);
    const replay = await request(value, "test-secret", timestamp);
    expect(replay.status).toBe(409);
    expect(await replay.json()).toEqual({ error: "replay_detected" });
  });

  it("enforces content type and body-size limits", async () => {
    const media = await SELF.fetch("https://worker.test/v1/template-proposal", { method: "POST", body: "{}" });
    expect(media.status).toBe(415);
    const oversized = await SELF.fetch("https://worker.test/v1/template-proposal", { method: "POST", body: "{}",
      headers: { "content-type": "application/json", "content-length": String(400 * 1024) } });
    expect(oversized.status).toBe(413);
  });
});

declare module "cloudflare:test" {
  interface ProvidedEnv extends Env {
    AI_HMAC_SECRET: string;
  }
}

void env;
