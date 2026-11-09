/**
 * Trinetra Voice Command & Accessibility Engine
 * ==============================================
 * Hands-free speech recognition supporting natural Nepali and English commands.
 * Built for blind users: enables demand-driven neural wakeups ("यो पैसा हेर त", "यो ठाउँ याद राख त").
 * Collaborates with OS Haptic Vibration and ARIA Live announcements.
 */

import { cameraApi } from "./cameraApi";

export type VoiceCommandType = "navigation" | "currency" | "ocr" | "sign_language" | "bookmark" | "scene" | "bus_route" | "qr_payment" | "date" | "mute" | "help" | "unknown";

export interface VoiceCommandMatch {
  type: VoiceCommandType;
  transcript: string;
  matchedPhrase: string;
}

// Trigger dictionaries in Devanagari and Romanized phonetic transcripts
const NAVIGATION_TRIGGERS = [
  "बाटो", "नेभिगेसन", "हिँड्ने", "बाटो देखाऊ", "वरिपरि बाटो",
  "navigation", "path", "walk", "bato", "navigate"
];

const SIGN_TRIGGERS = [
  "सांकेतिक भाषा", "साइन भाषा", "इशारा", "साइन अनुवाद",
  "sign language", "sign", "gesture", "deaf"
];

const CURRENCY_TRIGGERS = [
  "पैसा", "रुपैयाँ", "नोट", "कतिको नोट", "पैसा हेर", "यो पैसा हेर त",
  "money", "currency", "cash", "banknote", "paisa", "rupiya", "not hera"
];

const BOOKMARK_TRIGGERS = [
  "ठाउँ याद", "याद राख", "लोकेसन सेभ", "स्थान सेभ", "ठाउँ सेभ", "यो ठाउँ याद राख त",
  "save location", "remember this place", "bookmark", "where am i", "thau yad", "location save"
];

const SCENE_TRIGGERS = [
  "के छ", "अगाडि के छ", "हेर त", "वरिपरि हेर", "दृश्य", "वरिपरि के छ",
  "describe", "look", "what is ahead", "scene", "ke chha", "hera ta"
];

const OCR_TRIGGERS = [
  "पढ", "पढ्नुहोस्", "के लेखेको छ", "यो पढ त", "अक्षर", "किताब पढ",
  "read", "text", "read this", "padha", "ke lekheko", "akshar"
];

const BUS_TRIGGERS = [
  "बस", "बस नम्बर", "गाडी नम्बर", "कहाँ जाने", "बस रुट", "गाडी हेर",
  "bus", "bus route", "gadi", "tempo", "route", "bus number"
];

const QR_TRIGGERS = [
  "क्यूआर", "क्युआर", "पेमेन्ट", "भुक्तानी", "इसेवा", "खल्ती", "क्युआर स्क्यान",
  "qr", "qr code", "payment", "esewa", "fonepay", "khalti", "scan qr"
];

const DATE_TRIGGERS = [
  "मिति", "कति गते", "आज के बार", "क्यालेन्डर", "तिथि", "कति तारिख",
  "date", "today", "calendar", "miti", "gate"
];

const MUTE_TRIGGERS = [
  "चुप", "शान्त", "रोक", "मौन", "चुप लाग", "शान्त बस",
  "stop", "quiet", "silence", "mute", "chup", "shanta"
];

const HELP_TRIGGERS = [
  "मद्दत", "सहयोग", "सहायता", "गाइड", "help", "guide", "assist", "maddat"
];

export function matchVoiceCommand(rawTranscript: string): VoiceCommandMatch {
  const clean = rawTranscript.trim().toLowerCase();

  for (const phrase of NAVIGATION_TRIGGERS) {
    if (clean.includes(phrase.toLowerCase())) {
      return { type: "navigation", transcript: rawTranscript, matchedPhrase: phrase };
    }
  }

  for (const phrase of SIGN_TRIGGERS) {
    if (clean.includes(phrase.toLowerCase())) {
      return { type: "sign_language", transcript: rawTranscript, matchedPhrase: phrase };
    }
  }

  for (const phrase of CURRENCY_TRIGGERS) {
    if (clean.includes(phrase.toLowerCase())) {
      return { type: "currency", transcript: rawTranscript, matchedPhrase: phrase };
    }
  }

  for (const phrase of BOOKMARK_TRIGGERS) {
    if (clean.includes(phrase.toLowerCase())) {
      return { type: "bookmark", transcript: rawTranscript, matchedPhrase: phrase };
    }
  }

  for (const phrase of SCENE_TRIGGERS) {
    if (clean.includes(phrase.toLowerCase())) {
      return { type: "scene", transcript: rawTranscript, matchedPhrase: phrase };
    }
  }

  for (const phrase of OCR_TRIGGERS) {
    if (clean.includes(phrase.toLowerCase())) {
      return { type: "ocr", transcript: rawTranscript, matchedPhrase: phrase };
    }
  }

  for (const phrase of BUS_TRIGGERS) {
    if (clean.includes(phrase.toLowerCase())) {
      return { type: "bus_route", transcript: rawTranscript, matchedPhrase: phrase };
    }
  }

  for (const phrase of QR_TRIGGERS) {
    if (clean.includes(phrase.toLowerCase())) {
      return { type: "qr_payment", transcript: rawTranscript, matchedPhrase: phrase };
    }
  }

  for (const phrase of DATE_TRIGGERS) {
    if (clean.includes(phrase.toLowerCase())) {
      return { type: "date", transcript: rawTranscript, matchedPhrase: phrase };
    }
  }

  for (const phrase of MUTE_TRIGGERS) {
    if (clean.includes(phrase.toLowerCase())) {
      return { type: "mute", transcript: rawTranscript, matchedPhrase: phrase };
    }
  }

  for (const phrase of HELP_TRIGGERS) {
    if (clean.includes(phrase.toLowerCase())) {
      return { type: "help", transcript: rawTranscript, matchedPhrase: phrase };
    }
  }

  return { type: "unknown", transcript: rawTranscript, matchedPhrase: "" };
}

/**
 * Native OS Haptic Vibration Feedback
 */
export function triggerHaptic(pattern: "command" | "hazard" | "success"): void {
  if (typeof navigator !== "undefined" && "vibrate" in navigator) {
    try {
      if (pattern === "command") {
        navigator.vibrate(80); // Short tap confirmation
      } else if (pattern === "hazard") {
        navigator.vibrate([150, 60, 150]); // Urgent double pulse
      } else if (pattern === "success") {
        navigator.vibrate([70, 30, 70, 30, 70]); // Triple confirmation
      }
    } catch {
      // Haptics not permitted or unavailable
    }
  }
}

export type VoiceListenerCallback = (match: VoiceCommandMatch) => void;

export class VoiceCommandService {
  private recognition: any = null;
  private isListening: boolean = false;
  private mediaRecorder: MediaRecorder | null = null;
  private audioStream: MediaStream | null = null;
  private audioChunks: Blob[] = [];
  private recordingTimer: number | null = null;
  private onCommand: VoiceListenerCallback | null = null;
  private onStateChange: ((listening: boolean, error?: string, statusText?: string) => void) | null = null;

  constructor() {
    this.initRecognition();
  }

  private initRecognition() {
    if (typeof window === "undefined") return;

    const SpeechRecognition =
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;

    if (!SpeechRecognition) {
      return;
    }

    try {
      this.recognition = new SpeechRecognition();
      this.recognition.continuous = false;
      this.recognition.interimResults = false;
      this.recognition.lang = "ne-NP";

      this.recognition.onresult = (event: any) => {
        const lastResult = event.results[event.results.length - 1];
        if (lastResult && lastResult.isFinal) {
          const transcript = lastResult[0].transcript;
          const match = matchVoiceCommand(transcript);
          if (match.type !== "unknown") {
            triggerHaptic("command");
            this.onCommand?.(match);
          }
        }
      };

      this.recognition.onerror = (event: any) => {
        if (event.error !== "no-speech") {
          console.warn("Speech recognition notice:", event.error);
        }
      };
    } catch (e) {
      console.warn("SpeechRecognition init error:", e);
    }
  }

  public isSupported(): boolean {
    return (
      typeof navigator !== "undefined" &&
      navigator.mediaDevices &&
      typeof navigator.mediaDevices.getUserMedia === "function"
    );
  }

  /**
   * Starts a voice command listening burst.
   * Employs local MediaRecorder audio capture with backend offline transcription,
   * alongside Web Speech API where available.
   */
  public async start(
    onCommand: VoiceListenerCallback,
    onStateChange?: (listening: boolean, error?: string, statusText?: string) => void
  ): Promise<boolean> {
    this.onCommand = onCommand;
    this.onStateChange = onStateChange || null;

    if (!this.isSupported()) {
      this.onStateChange?.(false, "तपाईंको उपकरणमा अडियो रेकर्डर उपलब्ध छैन।");
      return false;
    }

    try {
      this.audioStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (err: any) {
      let errMsg = "माइक्रोफोन सुरु गर्न सकिएन।";
      if (err.name === "NotAllowedError" || err.name === "PermissionDeniedError") {
        errMsg = "माइक्रोफोन अनुमति अस्वीकार भयो। कृपया ब्राउजरमा माइक्रोफोन अनुमति दिनुहोस्।";
      } else if (err.name === "NotFoundError" || err.name === "DevicesNotFoundError") {
        errMsg = "कुनै माइक्रोफोन उपकरण फेला परेन। कृपया माइक जोड्नुहोस्।";
      }
      this.onStateChange?.(false, errMsg);
      return false;
    }

    try {
      this.isListening = true;
      this.audioChunks = [];
      this.mediaRecorder = new MediaRecorder(this.audioStream);

      this.mediaRecorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) {
          this.audioChunks.push(event.data);
        }
      };

      this.mediaRecorder.onstop = async () => {
        this.isListening = false;
        this.cleanupStream();

        if (this.audioChunks.length === 0) {
          this.onStateChange?.(false, undefined, "कुनै आवाज रेकर्ड भएन।");
          return;
        }

        const audioBlob = new Blob(this.audioChunks, { type: "audio/wav" });
        this.onStateChange?.(false, undefined, "प्रशोधन हुँदैछ… (Analyzing offline)");

        try {
          const reader = new FileReader();
          reader.readAsDataURL(audioBlob);
          reader.onloadend = async () => {
            try {
              const base64Data = (reader.result as string).split(",")[1];
              const sttRes = await cameraApi.transcribeSpeech(base64Data);

              if (sttRes.status === "recognized" && sttRes.command !== "none") {
                triggerHaptic("command");
                this.onStateChange?.(false, undefined, sttRes.message);
                this.onCommand?.({
                  type: sttRes.command as VoiceCommandType,
                  transcript: sttRes.transcript,
                  matchedPhrase: sttRes.transcript,
                });
              } else if (sttRes.status === "silence") {
                this.onStateChange?.(false, undefined, "कुनै आवाज सुनिएन। कृपया नजिकै बोल्नुहोस्।");
              } else {
                this.onStateChange?.(false, undefined, sttRes.message || "आदेश पहिचान हुन सकेन।");
              }
            } catch (postErr: any) {
              this.onStateChange?.(false, "अफलाइन आवाज इन्जिनसँग सम्पर्क हुन सकेन।");
            }
          };
        } catch {
          this.onStateChange?.(false, "अडियो रूपान्तरण असफल भयो।");
        }
      };

      this.mediaRecorder.start();
      this.onStateChange?.(true, undefined, "सुन्दैछ… बोल्नुहोस् (Listening… speak command)");

      // Concurrently start Web Speech if available
      try {
        if (this.recognition) {
          this.recognition.start();
        }
      } catch {
        // Tolerated
      }

      // Automatically conclude command recording after 3.2 seconds
      if (this.recordingTimer) window.clearTimeout(this.recordingTimer);
      this.recordingTimer = window.setTimeout(() => {
        this.stop();
      }, 3200);

      return true;
    } catch (err: any) {
      this.cleanupStream();
      this.isListening = false;
      this.onStateChange?.(false, `रेकर्डिङ सुरु गर्न समस्या: ${err.message || err}`);
      return false;
    }
  }

  public stop(): void {
    if (this.recordingTimer) {
      window.clearTimeout(this.recordingTimer);
      this.recordingTimer = null;
    }

    if (this.mediaRecorder && this.mediaRecorder.state !== "inactive") {
      try {
        this.mediaRecorder.stop();
      } catch {
        // Ignore
      }
    }

    if (this.recognition) {
      try {
        this.recognition.stop();
      } catch {
        // Ignore
      }
    }

    this.isListening = false;
  }

  private cleanupStream(): void {
    if (this.audioStream) {
      this.audioStream.getTracks().forEach((track) => track.stop());
      this.audioStream = null;
    }
  }

  public getListeningState(): boolean {
    return this.isListening;
  }
}

export const voiceCommandService = new VoiceCommandService();

