import { useRef, useState } from "react";
import { uploadDocument } from "../services/api";

interface Props {
  onUploaded: (documentId: string, filename: string) => void;
  onError: (message: string) => void;
}

export default function FileUploader({ onUploaded, onError }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);

  const handleFile = async (file: File) => {
    setUploading(true);
    try {
      const res = await uploadDocument(file);
      onUploaded(res.document_id, res.filename);
    } catch (err) {
      onError(err instanceof Error ? err.message : "Unable to process document.");
    } finally {
      setUploading(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  };

  return (
    <>
      <input
        ref={inputRef}
        type="file"
        accept=".pdf,.docx,.txt"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) handleFile(file);
        }}
      />
      <button
        type="button"
        title="Upload document"
        disabled={uploading}
        onClick={() => inputRef.current?.click()}
        className="p-2 rounded-lg hover:bg-slate-100 disabled:opacity-50 text-slate-500"
      >
        {uploading ? "…" : "📎"}
      </button>
    </>
  );
}
