import { useCallback, useRef, useState } from "react";

// Web Speech API isn't in standard TS lib types; declare minimally.
interface SpeechRecognitionResultLike {
  isFinal: boolean;
  [index: number]: { transcript: string };
}
interface SpeechRecognitionEventLike extends Event {
  resultIndex: number;
  results: ArrayLike<SpeechRecognitionResultLike>;
}
interface SpeechRecognitionLike extends EventTarget {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  start: () => void;
  stop: () => void;
  onresult: ((e: SpeechRecognitionEventLike) => void) | null;
  onerror: ((e: Event) => void) | null;
  onend: (() => void) | null;
}

function getSpeechRecognition(): (new () => SpeechRecognitionLike) | null {
  const w = window as any;
  return w.SpeechRecognition || w.webkitSpeechRecognition || null;
}

export function isSpeechRecognitionSupported(): boolean {
  return getSpeechRecognition() !== null;
}

export function useVoiceRecorder() {
  const [isRecording, setIsRecording] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const transcriptRef = useRef("");
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const start = useCallback(async () => {
    const SpeechRecognitionCtor = getSpeechRecognition();
    if (!SpeechRecognitionCtor) {
      throw new Error("Speech recognition isn't supported in this browser.");
    }

    // Surfaces the same permission prompt/error as before, and fails
    // fast with a clear error if the mic is blocked -- recognition.start()
    // alone doesn't always throw synchronously on denial.
    await navigator.mediaDevices.getUserMedia({ audio: true });

    const recognition = new SpeechRecognitionCtor();
    recognition.continuous = true;
    recognition.interimResults = false;
    recognition.lang = "en-IN";

    transcriptRef.current = "";
    recognition.onresult = (e) => {
      for (let i = e.resultIndex; i < e.results.length; i++) {
        if (e.results[i].isFinal) {
          transcriptRef.current += (transcriptRef.current ? " " : "") + e.results[i][0].transcript;
        }
      }
    };
    recognition.onerror = () => {
      // onend still fires after onerror; cleanup happens there.
    };

    recognition.start();
    recognitionRef.current = recognition;
    setIsRecording(true);
    setSeconds(0);
    timerRef.current = setInterval(() => setSeconds((s) => s + 1), 1000);
  }, []);

  const stop = useCallback((): Promise<string> => {
    return new Promise((resolve) => {
      const recognition = recognitionRef.current;
      if (!recognition) {
        resolve("");
        return;
      }
      recognition.onend = () => {
        if (timerRef.current) clearInterval(timerRef.current);
        setIsRecording(false);
        resolve(transcriptRef.current.trim());
      };
      recognition.stop();
    });
  }, []);

  return { isRecording, seconds, start, stop };
}