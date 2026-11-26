import { Easing, interpolate } from "remotion";

// Jev's "likely to matter in a week" score sweeping around a ring, with the number counting up.
export const ScoreDial: React.FC<{ frame: number; fps: number; score: number; fontFamily: string; mono: string }> = ({ frame, fps, score, fontFamily, mono }) => {
  const p = interpolate(frame, [0.6 * fps, 1.8 * fps], [0, score], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.bezier(0.16, 1, 0.3, 1) });
  const R = 54, C = 2 * Math.PI * R;
  return (
    <div style={{ position: "absolute", top: 660, left: 80, right: 80, display: "flex", alignItems: "center", gap: 30,
                  opacity: interpolate(frame, [0.4 * fps, 0.8 * fps], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }) }}>
      <svg width={140} height={140} viewBox="0 0 140 140" style={{ rotate: "-90deg" }}>
        <circle cx="70" cy="70" r={R} fill="none" stroke="#2c2e33" strokeWidth="14" />
        <circle cx="70" cy="70" r={R} fill="none" stroke="#C8102E" strokeWidth="14" strokeLinecap="round" strokeDasharray={`${C * p} ${C}`} />
      </svg>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        <span style={{ fontFamily: mono, fontSize: 76, color: "#f2f2f2", lineHeight: 1 }}>{Math.round(p * 100)}%</span>
        <span style={{ fontFamily, fontSize: 34, color: "#b8bcc4" }}>Jev: likely to matter in a week</span>
      </div>
    </div>
  );
};
