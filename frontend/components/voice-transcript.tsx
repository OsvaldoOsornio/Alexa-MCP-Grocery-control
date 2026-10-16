import { LoaderCircle, Mic, TriangleAlert } from "lucide-react";
import type { VoiceTurn } from "@/lib/kitchen-data";

type VoiceTranscriptProps = {
  turn: VoiceTurn;
};

/**
 * The voice exchange, across the top of the Echo Show frame.
 *
 * The tool chip prints `turn.tool`, which is the same string the MCP call was
 * issued with, so it cannot show a tool the server did not run. When a call is
 * in flight the chip is already correct and only the reply is pending.
 */
export function VoiceTranscript({ turn }: VoiceTranscriptProps) {
  return (
    <section className="voice-strip" aria-label="Voice exchange" aria-live="polite">
      <span className={`voice-wake wake-${turn.state}`}>
        {turn.state === "working" ? (
          <LoaderCircle className="spin" size={26} strokeWidth={2.4} />
        ) : turn.state === "failed" ? (
          <TriangleAlert size={26} strokeWidth={2.4} />
        ) : (
          <Mic size={26} strokeWidth={2.4} />
        )}
      </span>

      <div className="voice-lines">
        <p className="voice-utterance">&ldquo;{turn.utterance}&rdquo;</p>
        <p className={`voice-reply reply-${turn.state}`}>
          {turn.state === "working" ? "Working on it…" : turn.reply}
        </p>
      </div>

      <div className="voice-tool">
        <span className="voice-tool-label">MCP tool</span>
        <code className="voice-tool-name">{turn.tool}</code>
        <span className={`voice-tool-state tool-${turn.state}`}>
          {turn.state === "working"
            ? "calling"
            : turn.state === "failed"
              ? "returned an error"
              : "returned"}
        </span>
      </div>
    </section>
  );
}
