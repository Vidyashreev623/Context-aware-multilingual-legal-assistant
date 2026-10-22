import { useCallback, useState } from "react";
import { getConversation, sendChatMessage } from "../services/api";
import type { AttachedDocument, ChatMessage, Language } from "../types";

export function useChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isSwitching, setIsSwitching] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Shows the uploaded file in the conversation immediately, before any
  // message is sent -- purely local/display, no backend call involved.
  const addUploadedDocumentNotice = useCallback((doc: AttachedDocument) => {
    const notice: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content: "",
      timestamp: new Date().toISOString(),
      attachedDocuments: [doc],
    };
    setMessages((prev) => [...prev, notice]);
  }, []);

  const sendMessage = useCallback(
    async (
  text: string,
  language: Language,
  documentIds: string[] = []
) => {
      const userMsg: ChatMessage = {
        id: crypto.randomUUID(),
        role: "user",
        content: text,
        timestamp: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, userMsg]);
      setIsLoading(true);
      setError(null);

      try {
        const res = await sendChatMessage({
          conversation_id: conversationId,
          message: text,
          language,
          document_ids: documentIds,
        });
        if (res.conversation_id) setConversationId(res.conversation_id);

        const assistantMsg: ChatMessage = {
          id: crypto.randomUUID(),
          role: "assistant",
          content: res.answer,
          language: res.language,
          sources: res.sources,
          classification: res.classification,
          ambiguous: res.ambiguous,
          timestamp: new Date().toISOString(),
        };
        setMessages((prev) => [...prev, assistantMsg]);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to connect to server.");
      } finally {
        setIsLoading(false);
      }
    },
    [conversationId]
  );

  const startNewChat = useCallback(() => {
    setMessages([]);
    setConversationId(null);
    setError(null);
  }, []);

  const switchConversation = useCallback(async (targetConversationId: string) => {
    setIsSwitching(true);
    setError(null);
    try {
      const detail = await getConversation(targetConversationId);
      setMessages(detail.messages);
      setConversationId(detail.conversation_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to connect to server.");
    } finally {
      setIsSwitching(false);
    }
  }, []);

  return {
    messages,
    conversationId,
    isLoading,
    isSwitching,
    error,
    sendMessage,
    startNewChat,
    switchConversation,
    addUploadedDocumentNotice,
  };
}