import { useCallback, useRef, useState } from "react";
import { synthesizeSpeech } from "../services/api";

// Phase 17: lets an assistant answer be read aloud (the counterpart
// to useVoiceRecorder.ts's voice *input*) -- built for users who
// can't read or write, so the whole question-answer turn can happen
// by ear alone. Only one message plays at a time: starting a new one
// (or auto-speak firing for a fresh answer) stops whatever was
// already playing, same as a real voice assistant would behave.
export function useTextToSpeech() {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const urlRef = useRef<string | null>(null);
  const [speakingId, setSpeakingId] = useState<string | null>(null);
  const [loadingId, setLoadingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const cleanup = useCallback(() => {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.onended = null;
      audioRef.current.onerror = null;
      audioRef.current = null;
    }
    if (urlRef.current) {
      URL.revokeObjectURL(urlRef.current);
      urlRef.current = null;
    }
  }, []);

  const stop = useCallback(() => {
    cleanup();
    setSpeakingId(null);
    setLoadingId(null);
  }, [cleanup]);

  const speak = useCallback(
    async (id: string, text: string, language: string) => {
      // Clicking the speaker on whatever is already playing/loading
      // toggles it off, rather than restarting it.
      if (speakingId === id || loadingId === id) {
        stop();
        return;
      }
      stop();
      setError(null);
      setLoadingId(id);
      try {
        const blob = await synthesizeSpeech(text, language);
        const url = URL.createObjectURL(blob);
        urlRef.current = url;
        const audio = new Audio(url);
        audioRef.current = audio;
        audio.onended = () => {
          cleanup();
          setSpeakingId(null);
        };
        audio.onerror = () => {
          cleanup();
          setSpeakingId(null);
          setError("Unable to play the audio.");
        };
        await audio.play();
        setLoadingId(null);
        setSpeakingId(id);
      } catch (err) {
        cleanup();
        setLoadingId(null);
        setSpeakingId(null);
        setError(err instanceof Error ? err.message : "Unable to read this answer aloud.");
      }
    },
    [speakingId, loadingId, stop, cleanup]
  );

  return { speak, stop, speakingId, loadingId, error };
}
