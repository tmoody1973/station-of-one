import { Audio } from "@remotion/media";
import type { Caption } from "@remotion/captions";
import { loadFont } from "@remotion/google-fonts/SpaceGrotesk";
import { loadFont as loadMono } from "@remotion/google-fonts/JetBrainsMono";
import { AbsoluteFill, Easing, Sequence, interpolate, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { AudioBars } from "./AudioBars";
import { Captions } from "./Captions";
import { IdBlock } from "./IdBlock";
import { ScoreDial } from "./ScoreDial";

const { fontFamily } = loadFont("normal", { weights: ["500", "700"], subsets: ["latin"] });
const { fontFamily: mono } = loadMono("normal", { weights: ["500"], subsets: ["latin"] });

export type ReelProps = {
  headline: string;
  beat: string;
  beatColor: string;
  score: number;
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
const OUT = Easing.bezier(0.16, 1, 0.3, 1);
const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
// Safe area: text stays between 250 px from the top and 400 px from the bottom.

// The ID block punches in: a springy overshoot, then settles.
const punch = (frame: number, fps: number, delay = 0) =>
  interpolate(frame, [delay, delay + 0.7 * fps], [0.3, 1], { ...clamp, easing: Easing.spring({ damping: 9 }), output: "perceptual-scale" });

const DotField: React.FC<{ frame: number; fps: number }> = ({ frame, fps }) => {
  const lit = interpolate(frame, [0.2 * fps, 1.8 * fps], [0, 1], clamp);
  return (
    <div style={{ position: "absolute", top: 300, left: 90, right: 90, display: "grid", gridTemplateColumns: "repeat(12, 1fr)", gap: 22, opacity: 0.55 }}>
      {Array.from({ length: 96 }, (_, i) => {
        const on = ((i * 37) % 96) / 96 < lit;  // scattered order, lighting up as the count climbs
        return <div key={i} style={{ aspectRatio: "1", borderRadius: "50%", background: on ? (i % 7 === 0 ? "#C8102E" : "#3a3d44") : "#1b1d21" }} />;
      })}
    </div>
  );
};

const Intro: React.FC<{ postsRead: number; station: string }> = ({ postsRead, station }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const n = Math.round(interpolate(frame, [0.2 * fps, 1.8 * fps], [0, postsRead], { ...clamp, easing: OUT }));
  return (
    <AbsoluteFill>
      <DotField frame={frame} fps={fps} />
      <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", gap: 18 }}>
        <div style={{ scale: String(punch(frame, fps)), marginBottom: 20 }}>
          <IdBlock size={90} />
        </div>
        <div style={{ fontFamily: mono, fontSize: 210, color: "#f2f2f2", lineHeight: 1 }}>{n.toLocaleString("en-US")}</div>
        <div style={{ fontFamily, fontSize: 62, color: MUTED, translate: `0px ${interpolate(frame, [0.3 * fps, 0.8 * fps], [40, 0], { ...clamp, easing: OUT })}px`,
                      opacity: interpolate(frame, [0.3 * fps, 0.8 * fps], [0, 1], clamp) }}>posts read today</div>
        <div style={{ fontFamily: mono, fontSize: 44, color: "#ff8a98", opacity: interpolate(frame, [0.8 * fps, 1.2 * fps], [0, 1], clamp) }}>{station}</div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

const Headline: React.FC<{ frame: number; fps: number; p: ReelProps }> = ({ frame, fps, p }) => {
  const words = p.headline.split(" ");
  const wipe = interpolate(frame, [0, 0.35 * fps], [0, 100], { ...clamp, easing: OUT });
  return (
    <div style={{ position: "absolute", top: 250, left: 80, right: 80, display: "flex", flexDirection: "column", gap: 26 }}>
      <div style={{ alignSelf: "flex-start", background: p.beatColor, clipPath: `inset(0 ${100 - wipe}% 0 0)`, padding: "10px 20px", borderRadius: 6,
                    fontFamily, fontSize: 36, fontWeight: 700, letterSpacing: 3, textTransform: "uppercase", color: "#fff" }}>{p.beat}</div>
      <div style={{ fontFamily, fontSize: 70, fontWeight: 700, lineHeight: 1.1, color: "#f2f2f2" }}>
        {words.map((w, i) => {
          const start = 0.2 * fps + i * 2;  // each word two frames after the last
          return (
            <span key={i} style={{ display: "inline-block", whiteSpace: "pre",
                                   opacity: interpolate(frame, [start, start + 6], [0, 1], clamp),
                                   translate: `0px ${interpolate(frame, [start, start + 12], [50, 0], { ...clamp, easing: OUT })}px` }}>
              {w}{i < words.length - 1 ? " " : ""}
            </span>
          );
        })}
      </div>
    </div>
  );
};

const Story: React.FC<ReelProps> = (p) => {
  const frame = useCurrentFrame();
  const { fps, width } = useVideoConfig();
  const progress = frame / ((p.clipMs / 1000) * fps);
  return (
    <AbsoluteFill>
      <Headline frame={frame} fps={fps} p={p} />
      <ScoreDial frame={frame} fps={fps} score={p.score} fontFamily={fontFamily} mono={mono} />
      <AudioBars frame={frame} fps={fps} color={p.beatColor} />
      <Captions captions={p.captions} fontFamily={fontFamily} />
      <div style={{ position: "absolute", bottom: 440, left: 80, right: 80, fontFamily, fontSize: 32, color: MUTED }}>
        Synthetic voices · machine-edited · {p.show}
      </div>
      <div style={{ position: "absolute", bottom: 404, left: 0, height: 10, width: width * progress, background: "#C8102E" }} />
    </AbsoluteFill>
  );
};

const EndCard: React.FC<ReelProps> = (p) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const rise = (delay: number) => ({ opacity: interpolate(frame, [delay, delay + 8], [0, 1], clamp),
                                     translate: `0px ${interpolate(frame, [delay, delay + 14], [40, 0], { ...clamp, easing: OUT })}px` });
  return (
    <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", gap: 26, padding: "250px 80px 400px" }}>
      <div style={{ scale: String(punch(frame, fps)), marginBottom: 20 }}><IdBlock size={110} /></div>
      <div style={{ fontFamily, fontSize: 96, fontWeight: 700, color: "#f2f2f2", textAlign: "center", ...rise(6) }}>{p.show}</div>
      <div style={{ fontFamily: mono, fontSize: 48, color: "#ff8a98", ...rise(12) }}>{p.station}</div>
      <div style={{ fontFamily: mono, fontSize: 34, color: "#f2f2f2", textAlign: "center", wordBreak: "break-all", marginTop: 30, ...rise(18) }}>{p.url}</div>
      <div style={{ fontFamily, fontSize: 36, color: MUTED, marginTop: 30, ...rise(24) }}>Every hour. Runs on a Fly.io Sprite.</div>
    </AbsoluteFill>
  );
};

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
