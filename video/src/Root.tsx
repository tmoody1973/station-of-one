import { Composition } from "remotion";
import { Reel, ReelProps } from "./Reel";

const FPS = 30;

// Placeholder props for the Studio; real renders pass public/props.json via --props.
const defaultProps: ReelProps = {
  headline: "A headline from today's newscast",
  beat: "Arts and culture",
  beatColor: "#2e6f73",
  score: 0.62,
  postsRead: 1073,
  captions: [{ text: "Captions", startMs: 0, endMs: 600, timestampMs: 300, confidence: null }],
  clipMs: 24000,
  introMs: 2500,
  endMs: 3500,
  durationMs: 30000,
  show: "The Hourly Scroll",
  station: "ONE 1.0 FM",
  url: "example.com/index.html",
};

export const RemotionRoot = () => (
  <Composition
    id="Reel"
    component={Reel}
    fps={FPS}
    width={1080}
    height={1920}
    durationInFrames={Math.round((defaultProps.durationMs / 1000) * FPS)}
    defaultProps={defaultProps}
    calculateMetadata={({ props }) => ({ durationInFrames: Math.round((props.durationMs / 1000) * FPS) })}
  />
);
