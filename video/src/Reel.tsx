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
