import { useEffect, useRef, useState } from "react";
import ConversationSidebar from "../components/ConversationSidebar";
import ChatWindow from "../components/ChatWindow";
import ChatInput from "../components/ChatInput";
import LanguageSelector from "../components/LanguageSelector";
import ProfileMenu from "../components/ProfileMenu";
import { useChat } from "../hooks/useChat";
import { useTextToSpeech } from "../hooks/useTextToSpeech";
import type { AttachedDocument, Language } from "../types";

const AUTO_SPEAK_STORAGE_KEY = "nyaya-auto-speak";

export default function Chat() {
  const {
    messages,
    conversationId,
    isLoading,
    isSwitching,
    error,
    sendMessage,
    startNewChat,
    switchConversation,
  } = useChat();
  const { speak, stop, speakingId, loadingId: speechLoadingId, error: speechError } = useTextToSpeech();
  const [language, setLanguage] = useState<Language>("auto");
  const [attachedDocuments, setAttachedDocuments] = useState<AttachedDocument[]>([]);
  const [inlineError, setInlineError] = useState<string | null>(null);
  // For rural / non-literate users the answer should be readable by ear
  // without a tap, so a fresh assistant reply plays automatically when
  // this is on. Persisted so the choice survives a reload.
  const [autoSpeak, setAutoSpeak] = useState<boolean>(
    () => localStorage.getItem(AUTO_SPEAK_STORAGE_KEY) === "true"
  );
  const prevMessageCountRef = useRef(0);

  useEffect(() => {
    localStorage.setItem(AUTO_SPEAK_STORAGE_KEY, String(autoSpeak));
  }, [autoSpeak]);

  // Auto-speak a newly arrived assistant answer. Guarded to "exactly one
  // new message" so loading a past conversation (many messages at once)
  // or starting a new chat never triggers playback of old history.
  useEffect(() => {
    const prevCount = prevMessageCountRef.current;
    prevMessageCountRef.current = messages.length;
    if (!autoSpeak) return;
    if (messages.length - prevCount !== 1) return;
    const last = messages[messages.length - 1];
    if (!last || last.role !== "assistant" || !last.content) return;
    const lang = last.language && last.language !== "auto" ? last.language : last.classification?.language || "en";
    speak(last.id, last.content, lang);
  }, [messages, autoSpeak, speak]);

  const handleNewChat = () => {
    stop();
    startNewChat();
    setAttachedDocuments([]);
  };

  return (
    <div className="h-screen w-screen flex bg-slate-100">
      <ConversationSidebar
        activeConversationId={conversationId}
        onNewChat={handleNewChat}
        onSelectConversation={(id) => {
          stop();
          switchConversation(id);
        }}
      />
      <div className="flex-1 flex flex-col min-w-0">
        {/* Top bar with the profile menu (top-right) */}
        <div className="flex justify-end items-center px-6 py-3 border-b border-slate-200 bg-white">
          <ProfileMenu />
        </div>

        <ChatWindow
          messages={messages}
          isLoading={isLoading || isSwitching}
          onSpeak={speak}
          speakingId={speakingId}
          speechLoadingId={speechLoadingId}
        />

        <div className="px-6 pb-6">
          {(error || inlineError || speechError) && (
            <div className="mb-2 text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
              {error || inlineError || speechError}
            </div>
          )}
          <ChatInput
            disabled={isLoading}
            attachedDocuments={attachedDocuments}
            onSend={(text) => sendMessage(text, language, attachedDocuments.map((d) => d.document_id))}
            onDocumentUploaded={(id, filename) => {
              setAttachedDocuments((prev) => [...prev, { document_id: id, filename }]);
            }}
            onRemoveDocument={(id) => {
              setAttachedDocuments((prev) => prev.filter((d) => d.document_id !== id));
            }}
            onError={setInlineError}
          />
          <div className="mt-3 flex items-center justify-center gap-4">
            <LanguageSelector value={language} onChange={setLanguage} />
            <label className="flex items-center gap-1.5 text-sm text-slate-600 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={autoSpeak}
                onChange={(e) => {
                  setAutoSpeak(e.target.checked);
                  if (!e.target.checked) stop();
                }}
                className="rounded border-slate-300 text-indigo-600 focus:ring-indigo-400"
              />
              🔊 Read answers aloud
            </label>
          </div>
        </div>
      </div>
    </div>
  );
}