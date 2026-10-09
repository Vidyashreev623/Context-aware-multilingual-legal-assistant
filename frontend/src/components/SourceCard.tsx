import type { SourceItem } from "../types";

// Spec section 31: an answer drawing on an uploaded document must
// clearly say so, distinct from a legal-knowledge-base citation --
// this badge is that distinction, driven by the backend's own
// classification of the chunk (rag_service.py's _build_sources), never
// guessed on the frontend.
//
// Phase 14 (spec section 27's answer format: "Act name — Section" vs
// "Case name — Year"): a case-law chunk legitimately has no `section`
// at all, so it must NOT be rendered as if it were an Act missing a
// section number. `document_type` (also straight from the chunk's own
// metadata, never guessed) decides which citation shape to use.
export default function SourceCard({ source }: { source: SourceItem }) {
  const isUploaded = source.source_type === "uploaded_document";
  const isCase = source.document_type === "case";
  const isRule = source.document_type === "rule";

  return (
    <div className="text-xs bg-slate-50 border border-slate-200 rounded-md px-2 py-1.5 flex items-center gap-1.5">
      {isUploaded ? (
        <span className="shrink-0 text-[10px] font-medium px-1.5 py-0.5 rounded bg-sky-100 text-sky-700">
          📎 Your document
        </span>
      ) : isCase ? (
        <span className="shrink-0 text-[10px] font-medium px-1.5 py-0.5 rounded bg-violet-100 text-violet-700">
          ⚖️ Case law
        </span>
      ) : (
        <span className="shrink-0 text-[10px] font-medium px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-700">
          {isRule ? "📋 Rule" : "📄 Act"}
        </span>
      )}
      <span className="font-medium">{source.title}</span>
      {!isCase && source.section && <span> — Section {source.section}</span>}
      {isCase && source.year && <span> — {source.year}</span>}
      {!isUploaded && source.domain && <span className="text-slate-400"> · {source.domain}</span>}
    </div>
  );
}
