import { useState } from "react";
import FileUploader from "./FileUploader";
import VoiceRecorder from "./VoiceRecorder";
import type { AttachedDocument } from "../types";

interface Props {
  onSend: (text: string) => void;
  attachedDocuments: AttachedDocument[];
  onDocumentUploaded: (documentId: string, filename: string) => void;
  onRemoveDocument: (documentId: string) => void;
  onError: (message: string) => void;
  disabled?: boolean;
}

export default function ChatInput({
  onSend,
  attachedDocuments,
  onDocumentUploaded,
  onRemoveDocument,
  onError,
  disabled,
}: Props) {
  const [text, setText] = useState("");

  const canSend = text.trim().length > 0 || attachedDocuments.length > 0;

  const handleSend = () => {
    const trimmed = text.trim();
    if (!trimmed && attachedDocuments.length === 0) return;

    // If the user attached a file but didn't type anything, send a
    // sensible default prompt instead of blocking send entirely --
    // the backend requires a non-empty `message`.
    const finalText = trimmed || "Please summarize the uploaded document(s).";

    onSend(finalText);
    setText("");
  };

  return (
    <div className="border border-slate-300 rounded-2xl bg-white shadow-sm p-2">
      {attachedDocuments.length > 0 && (
        <div className="flex flex-wrap gap-1.5 px-2 pt-1 pb-2">
          {attachedDocuments.map((doc) => (
            <span
              key={doc.document_id}
              className="inline-flex items-center gap-1 text-xs bg-sky-50 text-sky-700 border border-sky-200 rounded-full pl-2.5 pr-1.5 py-1"
            >
              📎 {doc.filename}
              <button
                type="button"
                title="Remove document"
                onClick={() => onRemoveDocument(doc.document_id)}
                className="hover:bg-sky-100 rounded-full w-4 h-4 leading-none"
              >
                ×
              </button>
            </span>
          ))}
        </div>
      )}
      <div className="flex items-end gap-2">
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              handleSend();
            }
          }}
          placeholder={
            attachedDocuments.length > 0
              ? "Ask a question about your uploaded document(s)... (or just press send)"
              : "Ask anything about Indian law..."
          }
          rows={1}
          className="flex-1 resize-none outline-none px-2 py-2 text-slate-800 placeholder:text-slate-400 max-h-32"
        />
        <FileUploader onUploaded={onDocumentUploaded} onError={onError} />
        <VoiceRecorder onTranscribed={(t) => setText((prev) => (prev ? prev + " " + t : t))} onError={onError} />
        <button
          type="button"
          onClick={handleSend}
          disabled={disabled || !canSend}
          className="bg-indigo-600 text-white rounded-xl px-4 py-2 font-medium disabled:opacity-40 hover:bg-indigo-700"
        >
          ➤
        </button>
      </div>
    </div>
  );
}