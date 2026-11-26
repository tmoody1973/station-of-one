#!/usr/bin/env bash
# Check 4b: can the Sprite render the daily vertical video with Remotion, and how long does it take?
# 45 s, 1080x1920, 30 fps (1,350 frames): count-up, headline with word-by-word captions
# (placeholder timing), the check 2 Gemini clip as audio, end card.
# Setup per the remotion-best-practices skill (v4.0.512): create-video --blank, @remotion/media,
# `npx remotion browser ensure` (remotion.dev/docs/cli/browser/ensure).
# Run:  sprite exec -s brave-indigo-lion --stdin -- bash -s < spikes/check4b_remotion.sh
set -euo pipefail
W=~/spikes/check4b; mkdir -p "$W"; cd "$W"
t() { date +%s.%N; }
el() { python3 -c "print(f'{$2-$1:.1f}s')"; }

s=$(t)
[ -d reel ] || npx --yes create-video@latest --yes --blank --no-tailwind reel > scaffold.log 2>&1
cd reel
npm i --silent > /dev/null 2>&1
npx --yes remotion add @remotion/media > add.log 2>&1 || { tail -20 add.log; exit 1; }
echo "scaffold + install: $(el $s $(t))  remotion $(node -p "require('remotion/package.json').version")"
echo "--- src/index.ts:"; cat src/index.ts

mkdir -p public
cp ~/spikes/check2/a_generatecontent.wav public/voice.wav

cat > src/Root.tsx <<'TSX'
import { Audio } from "@remotion/media";
import {
  AbsoluteFill, Composition, Sequence, interpolate, staticFile, useCurrentFrame, useVideoConfig,
} from "remotion";

const WORDS = "Mozilla says Firefox ESR 115 reaches end of support on March first".split(" ");

const Counter = () => {
  const frame = useCurrentFrame();
  const n = Math.round(interpolate(frame, [0, 90], [0, 2140], { extrapolateRight: "clamp" }));
  return (
    <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", color: "#fff" }}>
      <div style={{ fontSize: 180, fontWeight: 700 }}>{n.toLocaleString("en-US")}</div>
      <div style={{ fontSize: 56 }}>posts read so you didn't</div>
    </AbsoluteFill>
  );
};

const Captions = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const perWord = 0.45 * fps; // placeholder timing; real timing comes from speech-to-text
  const shown = Math.min(WORDS.length, Math.floor(frame / perWord) + 1);
  return (
    <AbsoluteFill style={{ padding: "320px 90px", color: "#fff", fontSize: 76, lineHeight: 1.25 }}>
      {WORDS.slice(0, shown).map((w, i) => (
        <span key={i} style={{ color: i === shown - 1 ? "#ff8a98" : "#fff" }}>{w} </span>
      ))}
    </AbsoluteFill>
  );
};

const EndCard = () => (
  <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", color: "#fff", fontSize: 64 }}>
    <div style={{ fontWeight: 700 }}>The Hourly Scroll</div>
    <div style={{ fontSize: 44, marginTop: 24 }}>bucket.example/index.html</div>
  </AbsoluteFill>
);

export const Reel = () => (
  <AbsoluteFill style={{ backgroundColor: "#141414", fontFamily: "sans-serif" }}>
    <Sequence durationInFrames={120}><Counter /></Sequence>
    <Sequence from={120} durationInFrames={1020}>
      <Audio src={staticFile("voice.wav")} />
      <Captions />
    </Sequence>
    <Sequence from={1140}><EndCard /></Sequence>
  </AbsoluteFill>
);

export const RemotionRoot = () => (
  <Composition id="Reel" component={Reel} durationInFrames={1350} fps={30} width={1080} height={1920} />
);
TSX

s=$(t)
npx remotion browser ensure > browser.log 2>&1 || { tail -20 browser.log; exit 1; }
echo "browser ensure: $(el $s $(t))"

s=$(t)
npx remotion render Reel out/reel.mp4 --log=error > render.log 2>&1 || { tail -30 render.log; exit 1; }
echo "render 1,350 frames: $(el $s $(t))"
ffprobe -v error -show_entries stream=codec_name,width,height,r_frame_rate:format=duration,size -of compact=p=0 out/reel.mp4
echo "== disk"; du -sh "$W" 2>/dev/null; df -h / | tail -1
