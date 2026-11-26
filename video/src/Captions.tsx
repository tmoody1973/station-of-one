import { useMemo } from "react";
import { AbsoluteFill, Sequence, useCurrentFrame, useVideoConfig } from "remotion";
import { createTikTokStyleCaptions } from "@remotion/captions";
import type { Caption, TikTokPage } from "@remotion/captions";

const SWITCH_CAPTIONS_EVERY_MS = 1400;
const HIGHLIGHT = "#ff8a98";

const CaptionPage: React.FC<{ page: TikTokPage; fontFamily: string }> = ({ page, fontFamily }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const nowMs = page.startMs + (frame / fps) * 1000;
  return (
    // A plain box, not AbsoluteFill: AbsoluteFill is always 100% wide, so left/right offsets pushed text off-screen.
    <div style={{ position: "absolute", top: 1060, left: 80, right: 80, bottom: 420 }}>
      <div style={{ fontFamily, fontSize: 84, fontWeight: 700, lineHeight: 1.15, whiteSpace: "pre-wrap", color: "#f2f2f2" }}>
        {page.tokens.map((t) => (
          <span key={t.fromMs} style={{ color: t.fromMs <= nowMs && t.toMs > nowMs ? HIGHLIGHT : "#f2f2f2" }}>
            {t.text}
          </span>
        ))}
      </div>
    </div>
  );
};

export const Captions: React.FC<{ captions: Caption[]; fontFamily: string }> = ({ captions, fontFamily }) => {
  const { fps } = useVideoConfig();
  const { pages } = useMemo(
    () => createTikTokStyleCaptions({ captions, combineTokensWithinMilliseconds: SWITCH_CAPTIONS_EVERY_MS }),
    [captions],
  );
  return (
    <AbsoluteFill>
      {pages.map((page, i) => {
        const next = pages[i + 1] ?? null;
        const from = Math.round((page.startMs / 1000) * fps);
        const until = next ? Math.round((next.startMs / 1000) * fps) : from + Math.round((page.durationMs / 1000) * fps) + fps;
        return until - from > 0 ? (
          <Sequence key={i} from={from} durationInFrames={until - from} layout="none">
            <CaptionPage page={page} fontFamily={fontFamily} />
          </Sequence>
        ) : null;
      })}
    </AbsoluteFill>
  );
};
