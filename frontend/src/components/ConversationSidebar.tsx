import { useState } from "react";
import { useConversations } from "../hooks/useConversations";
import type { ConversationSummary } from "../types";

interface Props {
  activeConversationId: string | null;
  onNewChat: () => void;
  onSelectConversation: (conversationId: string) => void;
}

export default function ConversationSidebar({ activeConversationId, onNewChat, onSelectConversation }: Props) {
  const { conversations, error, rename, remove } = useConversations(activeConversationId);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingTitle, setEditingTitle] = useState("");

  const startRename = (conv: ConversationSummary) => {
    setEditingId(conv.conversation_id);
    setEditingTitle(conv.title);
  };

  const commitRename = async () => {
    if (editingId && editingTitle.trim()) {
      await rename(editingId, editingTitle.trim());
    }
    setEditingId(null);
  };

  const handleDelete = async (conversationId: string) => {
    await remove(conversationId);
    if (conversationId === activeConversationId) onNewChat();
  };

  return (
    <aside className="w-64 shrink-0 bg-slate-50 border-r border-slate-200 flex flex-col p-4">
      <div className="mb-4">
        <h1 className="text-lg font-bold text-indigo-700">Context-aware Multingual legal Assistant</h1>
        <p className="text-xs text-slate-500">Indian Law</p>
      </div>
      <button
        onClick={onNewChat}
        className="mb-4 bg-indigo-600 text-white rounded-lg py-2 text-sm font-medium hover:bg-indigo-700"
      >
        + New Chat
      </button>
      <div className="text-xs uppercase tracking-wide text-slate-400 mb-2">Recent Conversations</div>

      {error && <div className="text-xs text-red-600 mb-2">{error}</div>}

      {conversations.length === 0 && !error && (
        <div className="flex-1 text-sm text-slate-400 italic">No conversations yet.</div>
      )}

      <div className="flex-1 overflow-y-auto -mx-2 px-2 space-y-1">
        {conversations.map((conv) => {
          const isActive = conv.conversation_id === activeConversationId;
          const isEditing = editingId === conv.conversation_id;
          return (
            <div
              key={conv.conversation_id}
              className={`group rounded-lg px-3 py-2 text-sm cursor-pointer flex items-center justify-between gap-2 ${
                isActive ? "bg-indigo-100 text-indigo-800" : "hover:bg-slate-100 text-slate-700"
              }`}
              onClick={() => !isEditing && onSelectConversation(conv.conversation_id)}
            >
              {isEditing ? (
                <input
                  autoFocus
                  value={editingTitle}
                  onChange={(e) => setEditingTitle(e.target.value)}
                  onClick={(e) => e.stopPropagation()}
                  onBlur={commitRename}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") commitRename();
                    if (e.key === "Escape") setEditingId(null);
                  }}
                  className="flex-1 min-w-0 bg-white border border-indigo-300 rounded px-1 py-0.5 text-sm outline-none"
                />
              ) : (
                <span className="truncate flex-1">{conv.title}</span>
              )}

              {!isEditing && (
                <span className="hidden group-hover:flex items-center gap-1 shrink-0">
                  <button
                    title="Rename"
                    onClick={(e) => {
                      e.stopPropagation();
                      startRename(conv);
                    }}
                    className="text-slate-400 hover:text-indigo-600 text-xs"
                  >
                    ✎
                  </button>
                  <button
                    title="Delete"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleDelete(conv.conversation_id);
                    }}
                    className="text-slate-400 hover:text-red-600 text-xs"
                  >
                    🗑
                  </button>
                </span>
              )}
            </div>
          );
        })}
      </div>
    </aside>
  );
}
