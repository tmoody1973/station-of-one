// The WONE 1.0 FM dial mark, with the needle angle as a prop so it can sweep.
const TICKS = Array.from({ length: 11 }, (_, i) => -70 + i * 14);

export const Dial: React.FC<{ size: number; needleDeg: number; color?: string }> = ({ size, needleDeg, color = "#f2f2f2" }) => {
  const r = (deg: number) => ((deg - 90) * Math.PI) / 180;
  return (
    <svg width={size} height={size} viewBox="0 0 64 64">
      <circle cx="32" cy="34" r="27" fill="none" stroke={color} strokeWidth="5" />
      <g stroke={color} strokeWidth="2.5" strokeLinecap="round">
        {TICKS.map((d, i) => {
          const r1 = i % 5 === 0 ? 15 : 17.5;
          return <line key={d} x1={32 + r1 * Math.cos(r(d))} y1={34 + r1 * Math.sin(r(d))} x2={32 + 20 * Math.cos(r(d))} y2={34 + 20 * Math.sin(r(d))} />;
        })}
      </g>
      <line x1="32" y1="34" x2={32 + 18 * Math.cos(r(needleDeg))} y2={34 + 18 * Math.sin(r(needleDeg))} stroke="#C8102E" strokeWidth="5" strokeLinecap="round" />
      <circle cx="32" cy="34" r="5" fill={color} />
    </svg>
  );
};
