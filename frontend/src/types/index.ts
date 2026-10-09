export type Language = "auto" | "en" | "kn" | "hi";

export interface SourceItem {
  title: string;
  section?: string;
  domain?: string;
  source_type?: "uploaded_document" | "legal_database";
  // Phase 14 (spec sections 27-28): drives "Act name — Section" vs
  // "Case name — Year" citation formatting in SourceCard.tsx.
  document_type?: "act" | "case" | "rule" | "uploaded_document";
  year?: number;
}

export interface QueryClassification {
  language: string;
  domain: string | null;
  jurisdiction: string;
  state: string | null;
  court: string | null;
  query_type: string;
  ambiguity: boolean;
  confidence: number;
}

export interface AttachedDocument {
  document_id: string;
  filename: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  language?: Language;
  sources?: SourceItem[];
  classification?: QueryClassification;
  ambiguous?: boolean;
  timestamp: string;
  // Documents the user attached to this message (user messages only).
  attachedDocuments?: AttachedDocument[];
}

export interface ChatRequest {
  conversation_id?: string | null;
  message: string;
  language: Language;
  document_ids: string[];
}

export interface ChatResponse {
  answer: string;
  language: Language;
  sources: SourceItem[];
  conversation_id: string | null;
  classification?: QueryClassification;
  ambiguous?: boolean;
}

export interface ConversationSummary {
  conversation_id: string;
  title: string;
  updated_at: string;
}

export interface ConversationDetail {
  conversation_id: string;
  title: string;
  messages: ChatMessage[];
}
export interface SignupRequest {
  email: string;
  password: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface AuthResponse {
  access_token: string;
  email: string;
}