import { loadFont } from "@remotion/google-fonts/ArchivoBlack";

const { fontFamily } = loadFont("normal", { weights: ["400"], subsets: ["latin"] });

// The ONE 1.0 FM ID block (renamed from WONE, Nov 27) (Tarik picked option B, Nov 26): black band with yellow 1.0 over red band with white ONE.
export const IdBlock: React.FC<{ size: number }> = ({ size }) => (
  <div style={{ display: "inline-flex", flexDirection: "column", fontFamily, lineHeight: 1, borderRadius: size * 0.1, overflow: "hidden",
                boxShadow: `0 0 0 ${Math.round(size * 0.05)}px #f2f2f2` }}>
    <div style={{ background: "#0a0a0a", color: "#FFC629", fontSize: size * 1.3, padding: `${size * 0.08}px ${size * 0.3}px 0`, textAlign: "center", letterSpacing: -size * 0.03 }}>1.0</div>
    <div style={{ background: "#E4002B", color: "#fff", fontSize: size, padding: `${size * 0.1}px ${size * 0.32}px ${size * 0.12}px`, letterSpacing: size * 0.04 }}>ONE</div>
  </div>
);
