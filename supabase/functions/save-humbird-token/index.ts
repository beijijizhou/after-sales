import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

const ALLOWED_PLATFORMS = new Set([
  "Haloo",
  "莆田",
  "隆丰",
  "赛博",
]);

Deno.serve(async (request) => {
  if (request.method === "OPTIONS") {
    return new Response("ok", { headers: CORS_HEADERS });
  }

  if (request.method !== "POST") {
    return jsonResponse({ error: "Method not allowed" }, 405);
  }

  try {
    const body = await request.json();
    const platform = String(body.platform || "").trim();
    const token = String(body.token || "").trim();
    const updatedBy = String(body.updated_by || "qa-extension").trim();

    if (!ALLOWED_PLATFORMS.has(platform)) {
      return jsonResponse({ error: "Unsupported platform" }, 400);
    }

    if (!token || token.length < 20) {
      return jsonResponse({ error: "Invalid token" }, 400);
    }

    const supabaseUrl = requiredEnv("SUPABASE_URL");
    const serviceRoleKey = requiredEnv("SUPABASE_SERVICE_ROLE_KEY");
    const encryptionSecret =
      Deno.env.get("ERP_TOKEN_ENCRYPTION_KEY") || serviceRoleKey;
    const encryptedToken = await encryptToken(token, encryptionSecret);
    const now = new Date().toISOString();
    const client = createClient(supabaseUrl, serviceRoleKey);

    const { error } = await client
      .from("erp_api_credentials")
      .upsert(
        {
          platform,
          encrypted_token: encryptedToken,
          token_fingerprint: await fingerprint(token),
          status: "active",
          last_refreshed_at: now,
          last_error: null,
          updated_by: updatedBy || "qa-extension",
          updated_at: now,
        },
        { onConflict: "platform" },
      );

    if (error) {
      return jsonResponse({ error: error.message }, 500);
    }

    return jsonResponse({
      platform,
      saved: true,
      status: "active",
      token_fingerprint: await fingerprint(token),
      updated_at: now,
    });
  } catch (error) {
    return jsonResponse(
      { error: error instanceof Error ? error.message : String(error) },
      500,
    );
  }
});

async function encryptToken(token: string, secret: string) {
  const keyBytes = await sha256Bytes(`after-sales:erp-api-token:${secret}`);
  const key = await crypto.subtle.importKey(
    "raw",
    keyBytes,
    "AES-GCM",
    false,
    ["encrypt"],
  );
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const ciphertext = new Uint8Array(
    await crypto.subtle.encrypt(
      { name: "AES-GCM", iv },
      key,
      new TextEncoder().encode(token),
    ),
  );

  return `aesgcm:v1:${base64Url(iv)}:${base64Url(ciphertext)}`;
}

async function fingerprint(token: string) {
  const hash = await sha256Bytes(token);
  return [...hash]
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("")
    .slice(0, 12);
}

async function sha256Bytes(value: string) {
  return new Uint8Array(
    await crypto.subtle.digest(
      "SHA-256",
      new TextEncoder().encode(value),
    ),
  );
}

function base64Url(bytes: Uint8Array) {
  return btoa(String.fromCharCode(...bytes))
    .replaceAll("+", "-")
    .replaceAll("/", "_")
    .replaceAll("=", "");
}

function requiredEnv(name: string) {
  const value = Deno.env.get(name);
  if (!value) {
    throw new Error(`Missing ${name}`);
  }
  return value;
}

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      ...CORS_HEADERS,
      "Content-Type": "application/json",
    },
  });
}
