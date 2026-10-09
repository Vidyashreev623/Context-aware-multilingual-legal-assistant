import type { ChatMessage } from "../types";
import SpeakerButton from "./SpeakerButton";

const DOMAIN_LABELS: Record<string, string> = {
  consumer: "Consumer",
  contract: "Contract",
  cyber: "Cyber",
  family: "Family",
  property: "Property",
  employment: "Employment",
  criminal: "Criminal",
  constitutional: "Constitutional",
  corporate: "Corporate",
  intellectual_property: "IP",
  taxation: "Taxation",
  environmental: "Environmental",
  banking: "Banking",
};

// Phase 17: /api/voice/synthesize only knows en/hi/kn (spec section
// 33's three languages). message.language can be "auto" (the user's
// selector default, spec section 36) which isn't itself a spoken
// language, so fall back to the language the answer was actually
// classified/generated in, then to English.
function resolveSpeechLanguage(message: ChatMessage): string {
  if (message.language && message.language !== "auto") return message.language;
  if (message.classification?.language) return message.classification.language;
  return "en";
}

interface Props {
  message: ChatMessage;
  onSpeak: (id: string, text: string, language: string) => void;
  isSpeaking: boolean;
  isSpeechLoading: boolean;
}

export default function MessageBubble({ message, onSpeak, isSpeaking, isSpeechLoading }: Props) {
  const isUser = message.role === "user";
  const isClarification = !isUser && message.ambiguous;

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"} mb-4`}>
      <div
        className={`max-w-[75%] rounded-2xl px-4 py-3 shadow-sm ${
          isUser
            ? "bg-indigo-600 text-white rounded-br-sm"
            : isClarification
              ? "bg-amber-50 text-slate-800 border border-amber-200 rounded-bl-sm"
              : "bg-white text-slate-800 border border-slate-200 rounded-bl-sm"
        }`}
      >
        {isClarification && (
          <div className="text-xs font-semibold text-amber-700 mb-1 uppercase tracking-wide">
            Could you clarify?
          </div>
        )}

        {isUser && message.attachedDocuments && message.attachedDocuments.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mb-2">
            {message.attachedDocuments.map((doc) => (
              <span
                key={doc.document_id}
                className="inline-flex items-center gap-1 text-xs bg-indigo-500/40 text-white border border-indigo-300/40 rounded-full px-2.5 py-1"
              >
                📎 {doc.filename}
              </span>
            ))}
          </div>
        )}

        {message.content && (
          <div className="flex items-start gap-2">
            <p className="whitespace-pre-wrap leading-relaxed flex-1">{message.content}</p>
            {!isUser && (
              <SpeakerButton
                isLoading={isSpeechLoading}
                isSpeaking={isSpeaking}
                onToggle={() => onSpeak(message.id, message.content, resolveSpeechLanguage(message))}
              />
            )}
          </div>
        )}

        {!isUser && !isClarification && message.classification?.domain && (
          <div className="mt-2 flex flex-wrap gap-1.5">
            <span className="text-[11px] px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700 border border-indigo-100">
              {DOMAIN_LABELS[message.classification.domain] ?? message.classification.domain}
            </span>
            {message.classification.state && (
              <span className="text-[11px] px-2 py-0.5 rounded-full bg-slate-50 text-slate-600 border border-slate-200">
                {message.classification.state}
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
