import type {
  ChatRequest,
  ChatResponse,
  ConversationDetail,
  ConversationSummary,
} from "../types";

// Never call Gemini or any LLM directly from the frontend.
// Everything goes through our own FastAPI backend.
const API_BASE =
  import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api";

const TOKEN_KEY = "nyaya_token";

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = "Unable to connect to server.";

    try {
      const body = await res.json();
      // FastAPI validation errors (422) send `detail` as an array of
      // objects, not a string -- show something readable for those.
      if (typeof body.detail === "string") {
        detail = body.detail;
      } else if (Array.isArray(body.detail) && body.detail[0]?.msg) {
        detail = body.detail[0].msg;
      }
    } catch {
      /* ignore parse errors */
    }

    throw new Error(detail);
  }

  return res.json() as Promise<T>;
}

async function safeFetch(
  input: string,
  init?: RequestInit
): Promise<Response> {
  try {
    return await fetch(input, init);
  } catch {
    throw new Error("Unable to connect to server.");
  }
}

/**
 * Get the JWT access token stored after login/signup.
 */
function getAuthToken(): string | null {
  return sessionStorage.getItem(TOKEN_KEY);
}

/**
 * Headers for authenticated API requests.
 */
function authHeaders(): HeadersInit {
  const token = getAuthToken();

  if (!token) {
    return {};
  }

  return {
    Authorization: `Bearer ${token}`,
  };
}

function postJson(path: string, body: unknown): Promise<Response> {
  return safeFetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}


// ============================================================
// HEALTH
// ============================================================

export async function checkHealth(): Promise<{ status: string }> {
  const res = await safeFetch(`${API_BASE}/health`);
  return handle(res);
}


// ============================================================
// AUTH
// ============================================================

export interface AuthResult {
  access_token: string;
  email: string;
  name?: string | null;
}

export async function login(
  credentials: { email: string; password: string }
): Promise<AuthResult> {
  return handle(await postJson("/auth/login", credentials));
}

// --- Signup: email -> emailed code -> name + password ---

export async function requestSignupCode(email: string): Promise<{ message: string }> {
  return handle(await postJson("/auth/signup/request-code", { email }));
}

export async function verifySignupCode(
  email: string,
  code: string
): Promise<{ verified_token: string }> {
  return handle(await postJson("/auth/signup/verify-code", { email, code }));
}

export async function completeSignup(payload: {
  email: string;
  verified_token: string;
  name: string;
  password: string;
}): Promise<AuthResult> {
  return handle(await postJson("/auth/signup/complete", payload));
}

// --- Forgot password: email -> emailed code -> new password ---

export async function requestPasswordResetCode(email: string): Promise<{ message: string }> {
  return handle(await postJson("/auth/forgot-password/request-code", { email }));
}

export async function verifyPasswordResetCode(
  email: string,
  code: string
): Promise<{ verified_token: string }> {
  return handle(await postJson("/auth/forgot-password/verify-code", { email, code }));
}

export async function resetPassword(payload: {
  email: string;
  verified_token: string;
  new_password: string;
}): Promise<{ message: string }> {
  return handle(await postJson("/auth/forgot-password/reset", payload));
}

// --- Current user (profile menu) ---

export async function getCurrentUser(): Promise<{
  id: string;
  email: string;
  name: string | null;
}> {
  const res = await safeFetch(`${API_BASE}/auth/me`, {
    headers: { ...authHeaders() },
  });
  return handle(res);
}


// ============================================================
// CHAT
// ============================================================

export async function sendChatMessage(
  req: ChatRequest
): Promise<ChatResponse> {
  const res = await safeFetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
    },
    body: JSON.stringify(req),
  });

  return handle(res);
}


// ============================================================
// DOCUMENT UPLOAD
// ============================================================

export async function uploadDocument(
  file: File
): Promise<{
  document_id: string;
  filename: string;
  status: string;
  language: string;
  chunk_count: number;
}> {
  const formData = new FormData();

  formData.append("file", file);

  const res = await safeFetch(`${API_BASE}/upload`, {
    method: "POST",
    headers: {
      ...authHeaders(),
    },
    body: formData,
  });

  return handle(res);
}


// ============================================================
// VOICE
// ============================================================

export async function transcribeVoice(
  audioBlob: Blob
): Promise<{ text: string; language: string }> {
  const formData = new FormData();

  formData.append("audio", audioBlob, "recording.webm");

  const res = await safeFetch(`${API_BASE}/voice/transcribe`, {
    method: "POST",
    headers: {
      ...authHeaders(),
    },
    body: formData,
  });

  return handle(res);
}

export async function synthesizeSpeech(
  text: string,
  language: string
): Promise<Blob> {
  const res = await safeFetch(`${API_BASE}/voice/synthesize`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
    },
    body: JSON.stringify({
      text,
      language,
    }),
  });

  if (!res.ok) {
    let detail = "Unable to read this answer aloud.";

    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {
      /* ignore parse errors */
    }

    throw new Error(detail);
  }

  return res.blob();
}


// ============================================================
// CONVERSATIONS
// ============================================================

export async function listConversations(): Promise<
  ConversationSummary[]
> {
  const res = await safeFetch(`${API_BASE}/conversations`, {
    headers: {
      ...authHeaders(),
    },
  });

  return handle(res);
}

export async function getConversation(
  conversationId: string
): Promise<ConversationDetail> {
  const res = await safeFetch(
    `${API_BASE}/conversations/${conversationId}`,
    {
      headers: {
        ...authHeaders(),
      },
    }
  );

  return handle(res);
}

export async function createConversation(): Promise<ConversationSummary> {
  const res = await safeFetch(`${API_BASE}/conversations`, {
    method: "POST",
    headers: {
      ...authHeaders(),
    },
  });

  return handle(res);
}

export async function renameConversation(
  conversationId: string,
  title: string
): Promise<ConversationSummary> {
  const res = await safeFetch(
    `${API_BASE}/conversations/${conversationId}`,
    {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
        ...authHeaders(),
      },
      body: JSON.stringify({
        title,
      }),
    }
  );

  return handle(res);
}

export async function deleteConversation(
  conversationId: string
): Promise<{ deleted: string }> {
  const res = await safeFetch(
    `${API_BASE}/conversations/${conversationId}`,
    {
      method: "DELETE",
      headers: {
        ...authHeaders(),
      },
    }
  );

  return handle(res);
}
