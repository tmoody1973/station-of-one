import { useWindowedAudioData, visualizeAudio } from "@remotion/media-utils";
import { staticFile } from "remotion";

// Bars driven by the newscast voice. Frame comes from the parent (per the skill: not useCurrentFrame in a child).
export const AudioBars: React.FC<{ frame: number; fps: number; color: string }> = ({ frame, fps, color }) => {
  const { audioData, dataOffsetInSeconds } = useWindowedAudioData({ src: staticFile("clip.wav"), frame, fps, windowInSeconds: 10 });
  if (!audioData) return null;
  const f = visualizeAudio({ fps, frame, audioData, numberOfSamples: 64, optimizeFor: "speed", dataOffsetInSeconds }).slice(1, 25);
  return (
    <div style={{ position: "absolute", top: 860, left: 80, right: 80, height: 150, display: "flex", alignItems: "center", gap: 10 }}>
      {f.map((v, i) => (
        <div key={i} style={{ flex: 1, height: `${Math.min(100, 8 + Math.sqrt(v) * 160)}%`, borderRadius: 8, background: i % 3 === 0 ? "#C8102E" : color }} />
      ))}
    </div>
  );
};
