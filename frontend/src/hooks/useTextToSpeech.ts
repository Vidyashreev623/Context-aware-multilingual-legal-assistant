
import { useCallback, useEffect, useRef, useState } from "react";
import { synthesizeSpeech } from "../services/api";

export function useTextToSpeech() {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const urlRef = useRef<string | null>(null);
  const utteranceRef = useRef<SpeechSynthesisUtterance | null>(null);
  const requestIdRef = useRef(0);

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

    if ("speechSynthesis" in window) {
      window.speechSynthesis.cancel();
    }

    utteranceRef.current = null;
  }, []);

  const stop = useCallback(() => {
    requestIdRef.current += 1;
    cleanup();
    setSpeakingId(null);
    setLoadingId(null);
  }, [cleanup]);

  useEffect(() => {
    return () => {
      requestIdRef.current += 1;
      cleanup();
    };
  }, [cleanup]);

  const speak = useCallback(
    async (id: string, text: string, language: string) => {
      if (speakingId === id || loadingId === id) {
        stop();
        return;
      }

      stop();
      setError(null);
      setLoadingId(id);

      const requestId = requestIdRef.current;

      const browserFallback = () => {
        if (requestId !== requestIdRef.current) return;

        if (
          !("speechSynthesis" in window) ||
          !("SpeechSynthesisUtterance" in window)
        ) {
          setLoadingId(null);
          setSpeakingId(null);
          setError("Speech playback is not supported in this browser.");
          return;
        }

        // Remove Markdown formatting before speaking.
        const cleanText = text
          .replace(/```[\s\S]*?```/g, " ")
          .replace(/[*_#`]/g, "")
          .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
          .trim();

        if (!cleanText) {
          setLoadingId(null);
          setError("There is no text to read aloud.");
          return;
        }

        const utterance = new SpeechSynthesisUtterance(cleanText);

        const languageMap: Record<string, string> = {
          en: "en-IN",
          english: "en-IN",
          hi: "hi-IN",
          hindi: "hi-IN",
          kn: "kn-IN",
          kannada: "kn-IN",
          ta: "ta-IN",
          tamil: "ta-IN",
          te: "te-IN",
          telugu: "te-IN",
          ml: "ml-IN",
          malayalam: "ml-IN",
        };

        const selectedLanguage = language.toLowerCase();
        utterance.lang =
          languageMap[selectedLanguage] ||
          (selectedLanguage.includes("-")
            ? language
            : "en-IN");

        const voices = window.speechSynthesis.getVoices();
        const matchingVoice = voices.find(
          (voice) =>
            voice.lang.toLowerCase() === utterance.lang.toLowerCase()
        );

        if (matchingVoice) {
          utterance.voice = matchingVoice;
        }

        utterance.rate = 0.95;
        utterance.pitch = 1;

        utterance.onstart = () => {
          if (requestId !== requestIdRef.current) return;
          setLoadingId(null);
          setSpeakingId(id);
        };

        utterance.onend = () => {
          if (requestId !== requestIdRef.current) return;
          utteranceRef.current = null;
          setSpeakingId(null);
          setLoadingId(null);
        };

        utterance.onerror = (event) => {
          if (requestId !== requestIdRef.current) return;
          utteranceRef.current = null;
          setSpeakingId(null);
          setLoadingId(null);

          if (event.error !== "canceled" && event.error !== "interrupted") {
            setError("Browser speech playback failed.");
          }
        };

        utteranceRef.current = utterance;
        window.speechSynthesis.speak(utterance);
      };

      try {
        const blob = await synthesizeSpeech(text, language);

        if (requestId !== requestIdRef.current) return;

        const url = URL.createObjectURL(blob);
        urlRef.current = url;

        const audio = new Audio(url);
        audioRef.current = audio;

        audio.onended = () => {
          if (requestId !== requestIdRef.current) return;
          cleanup();
          setSpeakingId(null);
        };

        audio.onerror = () => {
          if (requestId !== requestIdRef.current) return;
          cleanup();
          browserFallback();
        };

        try {
          await audio.play();

          if (requestId !== requestIdRef.current) {
            cleanup();
            return;
          }

          setLoadingId(null);
          setSpeakingId(id);
        } catch {
          if (requestId !== requestIdRef.current) return;
          cleanup();
          browserFallback();
        }
      } catch {
        if (requestId !== requestIdRef.current) return;
        cleanup();
        browserFallback();
      }
    },
    [speakingId, loadingId, stop, cleanup]
  );

  return { speak, stop, speakingId, loadingId, error };
}
