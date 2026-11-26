import { Audio } from "@remotion/media";
import type { Caption } from "@remotion/captions";
import { loadFont } from "@remotion/google-fonts/SpaceGrotesk";
import { loadFont as loadMono } from "@remotion/google-fonts/JetBrainsMono";
import { AbsoluteFill, Easing, Sequence, interpolate, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { Captions } from "./Captions";

const { fontFamily } = loadFont("normal", { weights: ["500", "700"], subsets: ["latin"] });
const { fontFamily: mono } = loadMono("normal", { weights: ["500"], subsets: ["latin"] });

export type ReelProps = {
  headline: string;
  beat: string;
  beatColor: string;
  postsRead: number;
  captions: Caption[];
  clipMs: number;
  introMs: number;
  endMs: number;
  durationMs: number;
  show: string;
  station: string;
  url: string;
};

const BG = "#111214";
const MUTED = "#b8bcc4";
// Safe area: text stays between 250 px from the top and 400 px from the bottom.

const Intro: React.FC<{ postsRead: number; station: string }> = ({ postsRead, station }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const n = Math.round(interpolate(frame, [0, 1.8 * fps], [0, postsRead], {
    extrapolateRight: "clamp", easing: Easing.out(Easing.cubic) }));
  return (
    <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", gap: 20 }}>
      <div style={{ fontFamily: mono, fontSize: 200, color: "#f2f2f2" }}>{n.toLocaleString("en-US")}</div>
      <div style={{ fontFamily, fontSize: 60, color: MUTED }}>posts read today</div>
      <div style={{ fontFamily: mono, fontSize: 44, color: "#ff8a98", marginTop: 40 }}>{station}</div>
    </AbsoluteFill>
  );
};

const Story: React.FC<ReelProps> = (p) => (
  <AbsoluteFill>
    <div style={{ position: "absolute", top: 250, left: 80, right: 80, display: "flex", flexDirection: "column", gap: 28 }}>
      <div style={{ fontFamily, fontSize: 40, fontWeight: 700, letterSpacing: 3, textTransform: "uppercase", color: p.beatColor === "#C8102E" ? "#ff8a98" : "#f2f2f2", display: "flex", alignItems: "center", gap: 18 }}>
        <span style={{ width: 28, height: 28, borderRadius: 14, background: p.beatColor, display: "inline-block" }} />
        {p.beat}
      </div>
      <div style={{ fontFamily, fontSize: 68, fontWeight: 700, lineHeight: 1.1, color: "#f2f2f2" }}>{p.headline}</div>
      <div style={{ height: 8, width: 160, background: "#C8102E" }} />
    </div>
    <Captions captions={p.captions} fontFamily={fontFamily} />
    <div style={{ position: "absolute", bottom: 400, left: 80, right: 80, fontFamily, fontSize: 34, color: MUTED }}>
      Synthetic voices · machine-edited · {p.show}
    </div>
  </AbsoluteFill>
);

const EndCard: React.FC<ReelProps> = (p) => (
  <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", gap: 26, padding: "250px 80px 400px" }}>
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="220" height="220" role="img" aria-label="WONE 1.0 FM"><circle cx="32" cy="34" r="27" fill="none" stroke="#f2f2f2" strokeWidth="5"/><g stroke="#f2f2f2" strokeWidth="2.5" strokeLinecap="round"><line x1="17.9" y1="28.9" x2="13.2" y2="27.2"/><line x1="17.5" y1="24.2" x2="15.4" y2="22.8"/><line x1="20.3" y1="21.0" x2="18.6" y2="19.1"/><line x1="23.8" y1="18.5" x2="22.6" y2="16.3"/><line x1="27.8" y1="17.0" x2="27.2" y2="14.6"/><line x1="32.0" y1="19.0" x2="32.0" y2="14.0"/><line x1="36.2" y1="17.0" x2="36.8" y2="14.6"/><line x1="40.2" y1="18.5" x2="41.4" y2="16.3"/><line x1="43.7" y1="21.0" x2="45.4" y2="19.1"/><line x1="46.5" y1="24.2" x2="48.6" y2="22.8"/><line x1="46.1" y1="28.9" x2="50.8" y2="27.2"/></g><line x1="32" y1="34" x2="23.5" y2="18.1" stroke="#C8102E" strokeWidth="5" strokeLinecap="round"/><circle cx="32" cy="34" r="5" fill="#f2f2f2"/></svg>
    <div style={{ fontFamily, fontSize: 96, fontWeight: 700, color: "#f2f2f2", textAlign: "center" }}>{p.show}</div>
    <div style={{ fontFamily: mono, fontSize: 48, color: "#ff8a98" }}>{p.station}</div>
    <div style={{ fontFamily: mono, fontSize: 34, color: "#f2f2f2", textAlign: "center", wordBreak: "break-all", marginTop: 30 }}>{p.url}</div>
    <div style={{ fontFamily, fontSize: 36, color: MUTED, marginTop: 30 }}>Every hour. Runs on a Fly.io Sprite.</div>
  </AbsoluteFill>
);

export const Reel: React.FC<ReelProps> = (p) => {
  const { fps } = useVideoConfig();
  const f = (ms: number) => Math.round((ms / 1000) * fps);
  return (
    <AbsoluteFill style={{ backgroundColor: BG }}>
      <Sequence durationInFrames={f(p.introMs)}><Intro postsRead={p.postsRead} station={p.station} /></Sequence>
      <Sequence from={f(p.introMs)} durationInFrames={f(p.clipMs)}>
        <Audio src={staticFile("clip.mp3")} />
        <Story {...p} />
      </Sequence>
      <Sequence from={f(p.introMs + p.clipMs)}><EndCard {...p} /></Sequence>
    </AbsoluteFill>
  );
};
