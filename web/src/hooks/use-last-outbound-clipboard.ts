"use client";

import { useCallback, useRef, useState } from "react";

import { writeOutboundClipboardText } from "@/lib/api";

export function useLastOutboundClipboard() {
  const [clipboardText, setClipboardText] = useState("");
  const [copying, setCopying] = useState(false);
  const [copied, setCopied] = useState(false);
  const [copyFailed, setCopyFailed] = useState(false);
  const copiedTimerRef = useRef<number | null>(null);

  const remember = useCallback((text: string) => {
    setClipboardText(text?.trim() ? text : "");
    setCopied(false);
    setCopyFailed(false);
    if (copiedTimerRef.current !== null) {
      window.clearTimeout(copiedTimerRef.current);
      copiedTimerRef.current = null;
    }
  }, []);

  const clear = useCallback(() => {
    setClipboardText("");
    setCopied(false);
    setCopyFailed(false);
    if (copiedTimerRef.current !== null) {
      window.clearTimeout(copiedTimerRef.current);
      copiedTimerRef.current = null;
    }
  }, []);

  const copy = useCallback(async (overrideText?: string): Promise<boolean> => {
    const text = (overrideText ?? clipboardText)?.trim();
    if (!text || copying) return false;
    setCopying(true);
    try {
      await writeOutboundClipboardText(text);
      setCopied(true);
      setCopyFailed(false);
      if (copiedTimerRef.current !== null) {
        window.clearTimeout(copiedTimerRef.current);
      }
      copiedTimerRef.current = window.setTimeout(() => {
        setCopied(false);
        copiedTimerRef.current = null;
      }, 2000);
      return true;
    } catch {
      setCopied(false);
      setCopyFailed(true);
      return false;
    } finally {
      setCopying(false);
    }
  }, [clipboardText, copying]);

  const rememberAndCopy = useCallback(
    async (text: string): Promise<boolean> => {
      remember(text);
      return copy(text);
    },
    [remember, copy]
  );

  const acknowledgeCopySuccess = useCallback(() => {
    setCopied(true);
    setCopyFailed(false);
    if (copiedTimerRef.current !== null) {
      window.clearTimeout(copiedTimerRef.current);
    }
    copiedTimerRef.current = window.setTimeout(() => {
      setCopied(false);
      copiedTimerRef.current = null;
    }, 2000);
  }, []);

  return {
    clipboardText,
    remember,
    clear,
    copy,
    rememberAndCopy,
    copying,
    copied,
    copyFailed,
    acknowledgeCopySuccess,
  };
}
