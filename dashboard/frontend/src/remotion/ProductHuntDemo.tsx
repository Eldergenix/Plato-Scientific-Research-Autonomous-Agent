import type { CSSProperties, ReactNode } from "react";
import {
  AbsoluteFill,
  Easing,
  Img,
  interpolate,
  Sequence,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import {
  BarChart3,
  BookOpenCheck,
  FileText,
  FlaskConical,
  GitBranch,
  KeyRound,
  Rocket,
  ShieldCheck,
  Sparkles,
} from "lucide-react";

export const PRODUCT_HUNT_DEMO_FPS = 30;
export const PRODUCT_HUNT_DEMO_DURATION = PRODUCT_HUNT_DEMO_FPS * 50;

const COLORS = {
  bg: "#070707",
  panel: "#0f1010",
  panelElevated: "#141415",
  panelActive: "#202021",
  border: "#262628",
  borderSubtle: "rgba(255, 255, 255, 0.08)",
  text: "#ffffff",
  secondary: "#e3e4e7",
  tertiary: "#919193",
  muted: "#515153",
  lime: "#D5FF50",
  orange: "#ff6154",
  blue: "#4ea7fc",
  green: "#27a644",
  amber: "#f0bf00",
};

const STAGES = ["Idea", "Literature", "Method", "Results", "Paper", "Referee"];
const SCREENSHOTS = [
  "plato-screens/dashboard-home-final.png",
  "plato-screens/dashboard-phase2-stage-detail.png",
  "plato-screens/dashboard-models-final.png",
  "plato-screens/dashboard-costs-final.png",
  "plato-screens/dashboard-activity-final.png",
];

const easeOut = Easing.bezier(0.16, 1, 0.3, 1);
const easeInOut = Easing.bezier(0.45, 0, 0.55, 1);

function frameAt(seconds: number, fps: number) {
  return seconds * fps;
}

function timedProgress(frame: number, fps: number, start: number, duration: number, easing = easeOut) {
  return interpolate(frame, [frameAt(start, fps), frameAt(start + duration, fps)], [0, 1], {
    easing,
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
}

function fadeWindow(frame: number, fps: number, start: number, end: number) {
  const fadeIn = timedProgress(frame, fps, start, 0.6);
  const fadeOut = interpolate(frame, [frameAt(end - 0.6, fps), frameAt(end, fps)], [1, 0], {
    easing: Easing.in(Easing.cubic),
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return Math.min(fadeIn, fadeOut);
}

export function ProductHuntDemo() {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  return (
    <AbsoluteFill style={styles.root}>
      <Backdrop />
      <Header />
      <Sequence from={0} durationInFrames={frameAt(8, fps)}>
        <HeroScene />
      </Sequence>
      <Sequence from={frameAt(7.2, fps)} durationInFrames={frameAt(10, fps)}>
        <PipelineScene />
      </Sequence>
      <Sequence from={frameAt(16.3, fps)} durationInFrames={frameAt(12, fps)}>
        <WorkspaceScene />
      </Sequence>
      <Sequence from={frameAt(27.4, fps)} durationInFrames={frameAt(11, fps)}>
        <ControlScene />
      </Sequence>
      <Sequence from={frameAt(37.6, fps)} durationInFrames={frameAt(12.4, fps)}>
        <FinalScene />
      </Sequence>
      <TimelineRail frame={frame} fps={fps} />
    </AbsoluteFill>
  );
}

function Backdrop() {
  return (
    <AbsoluteFill
      style={{
        background:
          "linear-gradient(180deg, rgba(213, 255, 80, 0.08), transparent 28%), linear-gradient(135deg, #070707 0%, #0f1010 45%, #070707 100%)",
      }}
    >
      <div style={styles.grid} />
      <div style={styles.topGlow} />
      <div style={styles.bottomFade} />
    </AbsoluteFill>
  );
}

function Header() {
  return (
    <div style={styles.header}>
      <div style={styles.brandLockup}>
        <Img src={staticFile("light-theme-logo.svg")} style={styles.logo} />
        <div>
          <div style={styles.brandName}>Plato</div>
          <div style={styles.brandMeta}>Autonomous scientific research</div>
        </div>
      </div>
      <div style={styles.phBadge}>
        <Rocket size={16} strokeWidth={1.8} />
        Product Hunt demo
      </div>
    </div>
  );
}

function HeroScene() {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const enter = timedProgress(frame, fps, 0.15, 1);
  const shot = timedProgress(frame, fps, 1.15, 1.1);
  const exit = fadeWindow(frame, fps, 0, 8);

  return (
    <SceneFrame opacity={exit}>
      <div
        style={{
          ...styles.heroCopy,
          opacity: enter,
          transform: `translateY(${interpolate(enter, [0, 1], [32, 0])}px)`,
        }}
      >
        <Kicker icon={<Sparkles size={18} />}>AI research agents, in one workspace</Kicker>
        <h1 style={styles.h1}>Turn experimental data into a peer-reviewable paper.</h1>
        <p style={styles.lead}>
          Plato plans the idea, builds the method, runs analysis, writes the manuscript,
          and routes it through a reviewer-panel revision loop.
        </p>
        <StageTicker progress={timedProgress(frame, fps, 2.2, 3.8)} />
      </div>
      <ScreenshotCard
        src={SCREENSHOTS[0]}
        label="Live research workspace"
        style={{
          width: 940,
          right: 102,
          top: 198,
          opacity: shot,
          transform: `translateY(${interpolate(shot, [0, 1], [48, 0])}px) rotateX(0deg) rotateY(-7deg) rotateZ(1deg)`,
        }}
      />
    </SceneFrame>
  );
}

function PipelineScene() {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const opacity = fadeWindow(frame, fps, 0, 10);
  const activeIndex = Math.min(5, Math.floor(timedProgress(frame, fps, 1.1, 6.2) * STAGES.length));

  return (
    <SceneFrame opacity={opacity}>
      <div style={styles.splitLeft}>
        <Kicker icon={<GitBranch size={18} />}>One run, every stage visible</Kicker>
        <h2 style={styles.h2}>A scientific pipeline you can inspect.</h2>
        <p style={styles.bodyText}>
          Each stage has its own state, logs, costs, and review gates, so a launch demo
          can show real progress without hiding the research machinery.
        </p>
        <div style={styles.pipelineStack}>
          {STAGES.map((stage, index) => {
            const done = index < activeIndex;
            const active = index === activeIndex;
            return (
              <PipelineRow
                key={stage}
                label={stage}
                detail={pipelineDetail(stage)}
                done={done}
                active={active}
                index={index}
              />
            );
          })}
        </div>
      </div>
      <AgentConsole activeIndex={activeIndex} />
    </SceneFrame>
  );
}

function WorkspaceScene() {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const opacity = fadeWindow(frame, fps, 0, 12);
  const carousel = timedProgress(frame, fps, 1, 8.5, easeInOut);
  const offset = interpolate(carousel, [0, 0.45, 1], [0, -330, -660]);

  return (
    <SceneFrame opacity={opacity}>
      <div style={styles.centerCopy}>
        <Kicker icon={<BookOpenCheck size={18} />}>Built for launch-day clarity</Kicker>
        <h2 style={styles.h2}>Show the product, not a black box.</h2>
        <p style={styles.bodyText}>
          A Product Hunt viewer sees the dashboard, the stage detail view, model routing,
          budget controls, and activity trail in under a minute.
        </p>
      </div>
      <div style={styles.carouselViewport}>
        <div style={{ ...styles.carouselTrack, transform: `translateX(${offset}px)` }}>
          <MiniShot src={SCREENSHOTS[1]} title="Stage detail" icon={<FlaskConical size={21} />} />
          <MiniShot src={SCREENSHOTS[2]} title="Model matrix" icon={<ShieldCheck size={21} />} />
          <MiniShot src={SCREENSHOTS[3]} title="Cost ledger" icon={<BarChart3 size={21} />} />
          <MiniShot src={SCREENSHOTS[4]} title="Activity feed" icon={<FileText size={21} />} />
        </div>
      </div>
    </SceneFrame>
  );
}

function ControlScene() {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const opacity = fadeWindow(frame, fps, 0, 11);
  const enter = timedProgress(frame, fps, 0.8, 1);

  return (
    <SceneFrame opacity={opacity}>
      <div
        style={{
          ...styles.controlGrid,
          opacity: enter,
          transform: `translateY(${interpolate(enter, [0, 1], [42, 0])}px)`,
        }}
      >
        <ProofCard
          icon={<ShieldCheck size={30} />}
          label="Guardrails"
          title="Approvals before expensive stages"
          body="Demo mode can lock code execution and paper generation behind explicit gates."
        />
        <ProofCard
          icon={<BarChart3 size={30} />}
          label="Costs"
          title="Token spend stays visible"
          body="Budget caps and model-level spend make serious runs explainable before launch."
        />
        <ProofCard
          icon={<KeyRound size={30} />}
          label="Setup"
          title="Provider keys stay scoped"
          body="Per-provider key management keeps hosted demos and local labs on the same interface."
        />
      </div>
      <ScreenshotCard
        src={SCREENSHOTS[3]}
        label="Costs and caps"
        style={{
          width: 1050,
          right: 86,
          bottom: 106,
          opacity: timedProgress(frame, fps, 1.8, 1),
          transform: "rotateZ(-1.2deg)",
        }}
      />
    </SceneFrame>
  );
}

function FinalScene() {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const opacity = fadeWindow(frame, fps, 0, 12.4);
  const enter = timedProgress(frame, fps, 0.2, 1);
  const pulse = interpolate(Math.sin(frame / 18), [-1, 1], [0.82, 1]);

  return (
    <SceneFrame opacity={opacity}>
      <div style={styles.finalShell}>
        <div style={{ ...styles.finalLogoWrap, transform: `scale(${0.92 + enter * 0.08})` }}>
          <Img src={staticFile("light-theme-logo.svg")} style={styles.finalLogo} />
        </div>
        <h2 style={styles.finalTitle}>Plato</h2>
        <p style={styles.finalLead}>
          Autonomous scientific research runs with a dashboard your team can actually trust.
        </p>
        <div style={styles.ctaRow}>
          <span style={{ ...styles.primaryCta, boxShadow: `0 0 ${36 * pulse}px rgba(213, 255, 80, 0.22)` }}>
            Try the live demo
          </span>
          <span style={styles.secondaryCta}>Read the paper</span>
          <span style={styles.secondaryCta}>Star on GitHub</span>
        </div>
        <div style={styles.launchLine}>For researchers turning data into defensible papers.</div>
      </div>
    </SceneFrame>
  );
}

function SceneFrame({ children, opacity }: { children: ReactNode; opacity: number }) {
  return (
    <AbsoluteFill
      style={{
        opacity,
        padding: "154px 102px 94px",
      }}
    >
      {children}
    </AbsoluteFill>
  );
}

function Kicker({ icon, children }: { icon: ReactNode; children: ReactNode }) {
  return (
    <div style={styles.kicker}>
      {icon}
      <span>{children}</span>
    </div>
  );
}

function StageTicker({ progress }: { progress: number }) {
  return (
    <div style={styles.stageTicker}>
      {STAGES.map((stage, index) => {
        const active = progress * STAGES.length >= index;
        return (
          <div key={stage} style={{ ...styles.stagePill, opacity: active ? 1 : 0.38 }}>
            <span
              style={{
                ...styles.stageDot,
                background: active ? COLORS.lime : COLORS.muted,
              }}
            />
            {stage}
          </div>
        );
      })}
    </div>
  );
}

function ScreenshotCard({ src, label, style }: { src: string; label: string; style: CSSProperties }) {
  return (
    <div style={{ ...styles.screenshotCard, ...style }}>
      <div style={styles.windowChrome}>
        <div style={styles.windowDots}>
          <span style={{ ...styles.windowDot, background: COLORS.orange }} />
          <span style={{ ...styles.windowDot, background: COLORS.amber }} />
          <span style={{ ...styles.windowDot, background: COLORS.green }} />
        </div>
        <span style={styles.windowLabel}>{label}</span>
      </div>
      <Img src={staticFile(src)} style={styles.screenshotImage} />
    </div>
  );
}

function MiniShot({ src, title, icon }: { src: string; title: string; icon: ReactNode }) {
  return (
    <div style={styles.miniShot}>
      <div style={styles.miniHeader}>
        <span style={styles.miniIcon}>{icon}</span>
        <span>{title}</span>
      </div>
      <Img src={staticFile(src)} style={styles.miniImage} />
    </div>
  );
}

function PipelineRow({
  label,
  detail,
  done,
  active,
  index,
}: {
  label: string;
  detail: string;
  done: boolean;
  active: boolean;
  index: number;
}) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const enter = timedProgress(frame, fps, 0.8 + index * 0.12, 0.7);
  return (
    <div
      style={{
        ...styles.pipelineRow,
        opacity: enter,
        transform: `translateX(${interpolate(enter, [0, 1], [-30, 0])}px)`,
        borderColor: active ? "rgba(213, 255, 80, 0.48)" : COLORS.borderSubtle,
        background: active ? "rgba(213, 255, 80, 0.07)" : COLORS.panel,
      }}
    >
      <span
        style={{
          ...styles.pipelineStatus,
          background: done ? COLORS.green : active ? COLORS.lime : COLORS.panelActive,
          color: done || active ? COLORS.bg : COLORS.tertiary,
        }}
      >
        {done ? "OK" : active ? "RUN" : "Q"}
      </span>
      <div>
        <div style={styles.pipelineLabel}>{label}</div>
        <div style={styles.pipelineDetail}>{detail}</div>
      </div>
    </div>
  );
}

function AgentConsole({ activeIndex }: { activeIndex: number }) {
  const lines = [
    "retrieval: arXiv, OpenAlex, Crossref, PubMed",
    "novelty: claim evidence matrix updated",
    "method: executable plan drafted",
    "results: figures and manifest linked",
    "paper: LaTeX sections ready for review",
    "referee: statistics, novelty, writing axes scored",
  ];
  return (
    <div style={styles.console}>
      <div style={styles.consoleTop}>
        <span style={styles.consoleTitle}>agent stream</span>
        <span style={styles.consoleLive}>live</span>
      </div>
      <div style={styles.consoleBody}>
        {lines.map((line, index) => (
          <div
            key={line}
            style={{
              ...styles.consoleLine,
              opacity: index <= activeIndex ? 1 : 0.24,
              color: index <= activeIndex ? COLORS.secondary : COLORS.muted,
            }}
          >
            <span style={styles.consolePrompt}>plato</span>
            <span>{line}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function ProofCard({
  icon,
  label,
  title,
  body,
}: {
  icon: ReactNode;
  label: string;
  title: string;
  body: string;
}) {
  return (
    <div style={styles.proofCard}>
      <div style={styles.proofIcon}>{icon}</div>
      <div style={styles.proofLabel}>{label}</div>
      <div style={styles.proofTitle}>{title}</div>
      <div style={styles.proofBody}>{body}</div>
    </div>
  );
}

function TimelineRail({ frame, fps }: { frame: number; fps: number }) {
  const progress = interpolate(frame, [0, frameAt(50, fps)], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <div style={styles.timelineRail}>
      <div style={{ ...styles.timelineFill, width: `${progress * 100}%` }} />
    </div>
  );
}

function pipelineDetail(stage: string) {
  switch (stage) {
    case "Idea":
      return "Generate a testable research direction";
    case "Literature":
      return "Retrieve sources and map claims to evidence";
    case "Method":
      return "Draft reproducible analysis steps";
    case "Results":
      return "Run computation and capture figures";
    case "Paper":
      return "Write the manuscript with citations";
    default:
      return "Review, score, and revise the draft";
  }
}

const styles: Record<string, CSSProperties> = {
  root: {
    backgroundColor: COLORS.bg,
    color: COLORS.text,
    fontFamily:
      "Inter, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica, Arial, sans-serif",
    letterSpacing: 0,
  },
  grid: {
    position: "absolute",
    inset: 0,
    backgroundImage:
      "linear-gradient(rgba(255,255,255,0.035) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.035) 1px, transparent 1px)",
    backgroundSize: "64px 64px",
    maskImage: "linear-gradient(180deg, rgba(0,0,0,0.72), transparent 72%)",
  },
  topGlow: {
    position: "absolute",
    left: 0,
    right: 0,
    top: 0,
    height: 240,
    background: "linear-gradient(90deg, rgba(213, 255, 80, 0.16), rgba(255, 97, 84, 0.08), transparent)",
  },
  bottomFade: {
    position: "absolute",
    left: 0,
    right: 0,
    bottom: 0,
    height: 280,
    background: "linear-gradient(0deg, #070707 0%, rgba(7, 7, 7, 0) 100%)",
  },
  header: {
    position: "absolute",
    left: 88,
    right: 88,
    top: 54,
    height: 58,
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    zIndex: 20,
  },
  brandLockup: {
    display: "flex",
    alignItems: "center",
    gap: 18,
  },
  logo: {
    width: 34,
    height: 45,
    objectFit: "contain",
    filter: "drop-shadow(0 0 20px rgba(255,255,255,0.1))",
  },
  brandName: {
    fontSize: 22,
    lineHeight: "24px",
    fontWeight: 650,
  },
  brandMeta: {
    marginTop: 3,
    color: COLORS.tertiary,
    fontSize: 13,
  },
  phBadge: {
    height: 38,
    display: "flex",
    alignItems: "center",
    gap: 9,
    borderRadius: 999,
    padding: "0 16px",
    background: "rgba(255, 97, 84, 0.12)",
    border: "1px solid rgba(255, 97, 84, 0.36)",
    color: "#ffd8d4",
    fontSize: 14,
    fontWeight: 600,
  },
  heroCopy: {
    position: "absolute",
    left: 102,
    top: 210,
    width: 700,
  },
  kicker: {
    display: "inline-flex",
    alignItems: "center",
    gap: 10,
    height: 34,
    padding: "0 14px",
    borderRadius: 999,
    color: COLORS.lime,
    background: "rgba(213, 255, 80, 0.08)",
    border: "1px solid rgba(213, 255, 80, 0.28)",
    fontSize: 14,
    fontWeight: 650,
  },
  h1: {
    margin: "28px 0 0",
    fontSize: 82,
    lineHeight: "88px",
    fontWeight: 720,
    letterSpacing: 0,
    maxWidth: 720,
  },
  lead: {
    margin: "26px 0 0",
    color: COLORS.secondary,
    fontSize: 25,
    lineHeight: "37px",
    maxWidth: 670,
  },
  stageTicker: {
    display: "flex",
    flexWrap: "wrap",
    gap: 10,
    marginTop: 38,
    width: 650,
  },
  stagePill: {
    display: "inline-flex",
    alignItems: "center",
    gap: 8,
    height: 36,
    padding: "0 14px",
    borderRadius: 999,
    background: COLORS.panelElevated,
    border: `1px solid ${COLORS.border}`,
    color: COLORS.secondary,
    fontSize: 14,
    fontWeight: 600,
  },
  stageDot: {
    width: 8,
    height: 8,
    borderRadius: 999,
  },
  screenshotCard: {
    position: "absolute",
    borderRadius: 18,
    overflow: "hidden",
    border: `1px solid ${COLORS.borderSubtle}`,
    background: COLORS.panel,
    boxShadow: "0 30px 80px rgba(0, 0, 0, 0.46), 0 0 0 1px rgba(255,255,255,0.03)",
    transformOrigin: "center center",
  },
  windowChrome: {
    height: 44,
    display: "flex",
    alignItems: "center",
    gap: 16,
    padding: "0 18px",
    background: "#101112",
    borderBottom: `1px solid ${COLORS.borderSubtle}`,
  },
  windowDots: {
    display: "flex",
    gap: 7,
  },
  windowDot: {
    width: 9,
    height: 9,
    borderRadius: 99,
  },
  windowLabel: {
    color: COLORS.tertiary,
    fontSize: 13,
    fontWeight: 600,
  },
  screenshotImage: {
    width: "100%",
    display: "block",
  },
  splitLeft: {
    position: "absolute",
    left: 112,
    top: 178,
    width: 700,
  },
  h2: {
    margin: "24px 0 0",
    fontSize: 62,
    lineHeight: "68px",
    letterSpacing: 0,
    fontWeight: 720,
    maxWidth: 760,
  },
  bodyText: {
    margin: "22px 0 0",
    fontSize: 22,
    lineHeight: "34px",
    color: COLORS.secondary,
    maxWidth: 720,
  },
  pipelineStack: {
    marginTop: 36,
    display: "grid",
    gap: 12,
    width: 620,
  },
  pipelineRow: {
    display: "flex",
    alignItems: "center",
    gap: 16,
    minHeight: 72,
    borderRadius: 14,
    border: "1px solid",
    padding: "14px 16px",
  },
  pipelineStatus: {
    width: 44,
    height: 32,
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 999,
    fontSize: 12,
    fontWeight: 800,
  },
  pipelineLabel: {
    fontSize: 20,
    fontWeight: 680,
  },
  pipelineDetail: {
    marginTop: 4,
    fontSize: 14,
    color: COLORS.tertiary,
  },
  console: {
    position: "absolute",
    right: 112,
    top: 210,
    width: 770,
    minHeight: 594,
    borderRadius: 18,
    background: "rgba(15, 16, 16, 0.9)",
    border: `1px solid ${COLORS.borderSubtle}`,
    boxShadow: "0 30px 80px rgba(0, 0, 0, 0.42)",
    overflow: "hidden",
  },
  consoleTop: {
    height: 58,
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "0 22px",
    borderBottom: `1px solid ${COLORS.borderSubtle}`,
  },
  consoleTitle: {
    color: COLORS.tertiary,
    fontSize: 14,
    fontWeight: 700,
    textTransform: "uppercase",
  },
  consoleLive: {
    borderRadius: 999,
    padding: "5px 10px",
    background: "rgba(39,166,68,0.14)",
    color: "#a2f0b5",
    fontSize: 12,
    fontWeight: 800,
    textTransform: "uppercase",
  },
  consoleBody: {
    display: "grid",
    gap: 17,
    padding: 26,
  },
  consoleLine: {
    display: "flex",
    gap: 16,
    fontFamily: "JetBrains Mono, SFMono-Regular, Menlo, monospace",
    fontSize: 17,
    lineHeight: "28px",
  },
  consolePrompt: {
    color: COLORS.lime,
  },
  centerCopy: {
    position: "absolute",
    left: 112,
    right: 112,
    top: 158,
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    textAlign: "center",
  },
  carouselViewport: {
    position: "absolute",
    left: 110,
    right: 110,
    bottom: 104,
    height: 510,
    overflow: "hidden",
  },
  carouselTrack: {
    height: "100%",
    display: "flex",
    gap: 28,
    alignItems: "center",
  },
  miniShot: {
    width: 720,
    height: 455,
    flex: "0 0 auto",
    borderRadius: 18,
    background: COLORS.panel,
    border: `1px solid ${COLORS.borderSubtle}`,
    overflow: "hidden",
    boxShadow: "0 28px 70px rgba(0, 0, 0, 0.44)",
  },
  miniHeader: {
    height: 62,
    display: "flex",
    alignItems: "center",
    gap: 12,
    padding: "0 20px",
    fontSize: 19,
    fontWeight: 700,
    borderBottom: `1px solid ${COLORS.borderSubtle}`,
  },
  miniIcon: {
    width: 34,
    height: 34,
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 10,
    color: COLORS.bg,
    background: COLORS.lime,
  },
  miniImage: {
    width: "100%",
    height: 393,
    objectFit: "cover",
    objectPosition: "top left",
  },
  controlGrid: {
    position: "absolute",
    left: 104,
    top: 178,
    width: 560,
    display: "grid",
    gridTemplateColumns: "1fr",
    gap: 16,
    zIndex: 2,
  },
  proofCard: {
    borderRadius: 18,
    padding: 24,
    background: "rgba(15, 16, 16, 0.94)",
    border: `1px solid ${COLORS.borderSubtle}`,
    boxShadow: "0 20px 60px rgba(0, 0, 0, 0.24)",
  },
  proofIcon: {
    width: 54,
    height: 54,
    borderRadius: 16,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    color: COLORS.bg,
    background: COLORS.lime,
  },
  proofLabel: {
    marginTop: 18,
    color: COLORS.tertiary,
    fontSize: 13,
    fontWeight: 800,
    textTransform: "uppercase",
  },
  proofTitle: {
    marginTop: 7,
    fontSize: 23,
    lineHeight: "29px",
    fontWeight: 720,
  },
  proofBody: {
    marginTop: 10,
    color: COLORS.secondary,
    fontSize: 16,
    lineHeight: "25px",
  },
  finalShell: {
    position: "absolute",
    inset: "158px 160px 120px",
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    textAlign: "center",
    borderRadius: 28,
    background:
      "linear-gradient(180deg, rgba(213,255,80,0.09), rgba(15,16,16,0.94) 38%, rgba(15,16,16,0.72))",
    border: "1px solid rgba(213,255,80,0.2)",
    boxShadow: "0 40px 100px rgba(0,0,0,0.44)",
  },
  finalLogoWrap: {
    width: 118,
    height: 118,
    borderRadius: 28,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    background: "#f7f8f8",
    boxShadow: "0 20px 50px rgba(255, 255, 255, 0.08)",
  },
  finalLogo: {
    width: 57,
    height: 76,
    objectFit: "contain",
  },
  finalTitle: {
    margin: "26px 0 0",
    fontSize: 90,
    lineHeight: "96px",
    letterSpacing: 0,
    fontWeight: 760,
  },
  finalLead: {
    margin: "18px 0 0",
    color: COLORS.secondary,
    fontSize: 27,
    lineHeight: "40px",
    maxWidth: 920,
  },
  ctaRow: {
    display: "flex",
    gap: 14,
    marginTop: 42,
  },
  primaryCta: {
    height: 52,
    display: "inline-flex",
    alignItems: "center",
    borderRadius: 999,
    padding: "0 25px",
    color: COLORS.bg,
    background: COLORS.lime,
    fontSize: 17,
    fontWeight: 800,
  },
  secondaryCta: {
    height: 52,
    display: "inline-flex",
    alignItems: "center",
    borderRadius: 999,
    padding: "0 23px",
    color: COLORS.secondary,
    background: COLORS.panelActive,
    border: `1px solid ${COLORS.borderSubtle}`,
    fontSize: 17,
    fontWeight: 700,
  },
  launchLine: {
    marginTop: 38,
    color: COLORS.tertiary,
    fontSize: 18,
  },
  timelineRail: {
    position: "absolute",
    left: 88,
    right: 88,
    bottom: 52,
    height: 3,
    borderRadius: 999,
    background: "rgba(255,255,255,0.08)",
    overflow: "hidden",
  },
  timelineFill: {
    height: "100%",
    background: `linear-gradient(90deg, ${COLORS.lime}, ${COLORS.orange})`,
  },
};
