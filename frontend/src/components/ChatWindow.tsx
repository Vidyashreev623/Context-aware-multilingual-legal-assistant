import type { ChatMessage } from "../types";
import MessageBubble from "./MessageBubble";
import LoadingIndicator from "./LoadingIndicator";

interface Props {
  messages: ChatMessage[];
  isLoading: boolean;
  onSpeak: (id: string, text: string, language: string) => void;
  speakingId: string | null;
  speechLoadingId: string | null;
}

export default function ChatWindow({ messages, isLoading, onSpeak, speakingId, speechLoadingId }: Props) {
  if (messages.length === 0 && !isLoading) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center text-center text-slate-500 px-6">
        <h2 className="text-xl font-semibold text-slate-700 mb-2">Context-Aware Multilingual Legal Assistant</h2>
        <p>Hello! How can I help you understand Indian law?</p>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto px-6 py-6">
      {messages.map((m) => (
        <MessageBubble
          key={m.id}
          message={m}
          onSpeak={onSpeak}
          isSpeaking={speakingId === m.id}
          isSpeechLoading={speechLoadingId === m.id}
        />
      ))}
      {isLoading && <LoadingIndicator />}
    </div>
  );
}
