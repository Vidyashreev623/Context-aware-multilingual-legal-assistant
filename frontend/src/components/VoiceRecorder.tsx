import { useVoiceRecorder, isSpeechRecognitionSupported } from "../hooks/useVoiceRecorder";

interface Props {
  onTranscribed: (text: string) => void;
  onError: (message: string) => void;
}

export default function VoiceRecorder({ onTranscribed, onError }: Props) {
  const { isRecording, seconds, start, stop } = useVoiceRecorder();

  if (!isSpeechRecognitionSupported()) {
    return null; // hide the mic button entirely on unsupported browsers (e.g. Firefox, some Safari versions)
  }

  const handleClick = async () => {
    if (!isRecording) {
      try {
        await start();
      } catch {
        onError("Microphone access denied or unavailable.");
      }
      return;
    }
    const text = await stop();
    if (text) {
      onTranscribed(text);
    } else {
      onError("Didn't catch that — try again.");
    }
  };

  return (
    <button
      type="button"
      onClick={handleClick}
      title={isRecording ? "Stop recording" : "Record voice question"}
      className={`p-2 rounded-lg text-slate-500 hover:bg-slate-100 ${
        isRecording ? "bg-red-50 text-red-500" : ""
      }`}
    >
      {isRecording ? `⏹ ${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}` : "🎤"}
    </button>
  );
}