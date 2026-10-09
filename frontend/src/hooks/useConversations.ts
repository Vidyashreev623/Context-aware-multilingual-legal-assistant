import { useCallback, useEffect, useState } from "react";
import { deleteConversation, listConversations, renameConversation } from "../services/api";
import type { ConversationSummary } from "../types";

/**
 * Phase 10: drives the sidebar's "Recent Conversations" list against
 * the real /api/conversations endpoints. Deliberately separate from
 * useChat (which owns the *active* conversation's messages) -- this
 * hook only owns the list/rename/delete of conversation summaries.
 */
export function useConversations(activeConversationId: string | null) {
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const list = await listConversations();
      setConversations(list);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to connect to server.");
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // A new message on the active conversation changes its title/order
  // (see backend/app/database/repositories.py's add_message), so
  // re-sync the list whenever the active conversation changes -- this
  // also covers a brand-new conversation appearing for the first time.
  useEffect(() => {
    if (activeConversationId) refresh();
  }, [activeConversationId, refresh]);

  const rename = useCallback(
    async (conversationId: string, title: string) => {
      await renameConversation(conversationId, title);
      await refresh();
    },
    [refresh]
  );

  const remove = useCallback(
    async (conversationId: string) => {
      await deleteConversation(conversationId);
      await refresh();
    },
    [refresh]
  );

  return { conversations, error, refresh, rename, remove };
}
