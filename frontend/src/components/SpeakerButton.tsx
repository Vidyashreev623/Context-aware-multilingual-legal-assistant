interface Props {
  isLoading: boolean;
  isSpeaking: boolean;
  onToggle: () => void;
}

// A real backend call every click (Rule 1: no fake buttons) --
// onToggle() runs useTextToSpeech's speak()/stop(), which hits
// /api/voice/synthesize, exactly the way VoiceRecorder.tsx's mic
// button hits /api/voice/transcribe.
export default function SpeakerButton({ isLoading, isSpeaking, onToggle }: Props) {
  return (
    <button
      type="button"
      onClick={onToggle}
      title={isSpeaking ? "Stop reading aloud" : "Read this answer aloud"}
      className={`shrink-0 p-1.5 rounded-full hover:bg-slate-100 ${
        isSpeaking ? "text-indigo-600 bg-indigo-50" : "text-slate-400"
      }`}
    >
      {isLoading ? "⏳" : isSpeaking ? "🔊" : "🔈"}
    </button>
  );
}
