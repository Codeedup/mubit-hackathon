import type {CSSProperties, ReactNode} from 'react';
import {AbsoluteFill, Audio, getStaticFiles, Img, interpolate, OffthreadVideo, Sequence, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';

const color = {navy: '#071520', panel: '#102632', white: '#f2eee5', muted: '#a8bdc3', teal: '#54d5c1', amber: '#ffbf69', red: '#ef7067'};
const assetNames = new Set(getStaticFiles().map((file) => file.name.replace(/^\//, '')));
const assetExists = (filename: string) => assetNames.has(`assets/${filename}`);
const base: CSSProperties = {fontFamily: 'Arial, Helvetica, sans-serif', backgroundColor: color.navy, color: color.white, overflow: 'hidden'};

function Frame({number, section, title, caption, seconds, children}: {number: string; section: string; title: string; caption: string; seconds: number; children: ReactNode}) {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const opacity = interpolate(frame, [0, 18], [0, 1], {extrapolateRight: 'clamp'});
  return <AbsoluteFill style={base}>
    <AbsoluteFill style={{background: 'radial-gradient(circle at 80% 15%, #174d58, transparent 36%), linear-gradient(135deg, #071520, #0b202c)'}} />
    <AbsoluteFill style={{opacity: 0.2, backgroundImage: 'linear-gradient(#4e7b831f 1px, transparent 1px), linear-gradient(90deg, #4e7b831f 1px, transparent 1px)', backgroundSize: '64px 64px'}} />
    <div style={{position: 'absolute', top: 56, left: 92, right: 92, display: 'flex', justifyContent: 'space-between', fontSize: 21, fontWeight: 700, letterSpacing: 4, color: color.teal}}><span>ROBO / MEDIC</span><span style={{color: color.muted}}>{number} / {section}</span></div>
    <h1 style={{position: 'absolute', left: 92, top: 135, right: 92, margin: 0, fontSize: 88, letterSpacing: -3, lineHeight: 1.04, opacity}}>{title}</h1>
    <div style={{position: 'absolute', left: 92, right: 92, top: 265, bottom: 160, opacity}}>{children}</div>
    <div style={{position: 'absolute', left: 92, right: 92, bottom: 50, minHeight: 80, display: 'flex', alignItems: 'center', borderTop: '1px solid #30505a', paddingTop: 16, fontSize: 44, lineHeight: 1.18, fontWeight: 600}}>{caption}</div>
    <div style={{position: 'absolute', bottom: 0, left: 0, height: 7, width: `${Math.min(100, frame / (seconds * fps) * 100)}%`, background: color.teal}} />
  </AbsoluteFill>;
}

function Media({filename, label, image = false, still, zoom = 1, shiftX = 0, shiftY = 0}: {filename: string; label: string; image?: boolean; still?: string; zoom?: number; shiftX?: number; shiftY?: number}) {
  const available = assetExists(filename);
  const fallback = still && assetExists(still);
  const frame = useCurrentFrame();
  const drift = interpolate(frame, [0, 600], [0, 0.04], {extrapolateRight: 'clamp'});
  return <div style={{position: 'relative', width: '100%', height: '100%', overflow: 'hidden', borderRadius: 22, border: `1px solid ${available ? color.teal : color.amber}88`, background: 'linear-gradient(145deg, #153441, #0b1d28)', boxShadow: '0 28px 80px #0005'}}>
    {available && (image ? <Img src={staticFile(`assets/${filename}`)} style={{width: '100%', height: '100%', objectFit: 'contain'}} /> : <OffthreadVideo src={staticFile(`assets/${filename}`)} muted style={{width: '100%', height: '100%', objectFit: 'contain'}} />)}
    {!available && fallback && <Img src={staticFile(`assets/${still}`)} style={{position: 'absolute', width: '100%', height: '100%', objectFit: image ? 'contain' : 'fill', transform: `translate(${shiftX}px, ${shiftY}px) scale(${zoom + drift})`}} />}
    {!available && !fallback && <div style={{height: '100%', display: 'grid', placeItems: 'center', textAlign: 'center', fontSize: 45, fontWeight: 700}}>{label}</div>}
    <div style={{position: 'absolute', left: 24, top: 22, padding: '10px 18px', borderRadius: 8, background: '#071520df', color: color.teal, fontSize: 22, fontWeight: 700, letterSpacing: 1}}>{available ? 'SOURCE FOOTAGE' : image ? 'CONSOLE CAPTURE · DATE NOT SHOWN' : 'APP CAPTURE · OFFLINE FIXTURE'}</div>
  </div>;
}

function Note({heading, text, amber = false}: {heading: string; text: string; amber?: boolean}) {
  return <div style={{borderLeft: `5px solid ${amber ? color.amber : color.teal}`, background: color.panel, padding: '22px 24px', borderRadius: '0 14px 14px 0'}}><div style={{color: amber ? color.amber : color.teal, fontSize: 24, letterSpacing: 2, fontWeight: 800}}>{heading}</div><div style={{fontSize: 36, lineHeight: 1.15, marginTop: 12}}>{text}</div></div>;
}

function Split({filename, label, image, still, zoom, shiftX, shiftY, children}: {filename: string; label: string; image?: boolean; still?: string; zoom?: number; shiftX?: number; shiftY?: number; children: ReactNode}) {
  return <div style={{display: 'grid', gridTemplateColumns: '1.42fr 0.58fr', gap: 30, height: '100%'}}><Media filename={filename} label={label} image={image} still={still} zoom={zoom} shiftX={shiftX} shiftY={shiftY} /><div style={{display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: 26}}>{children}</div></div>;
}

function HardwareIllustration() {
  return <div style={{height: '100%', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 38, alignItems: 'center'}}>
    <div style={{height: '86%', border: `2px solid ${color.teal}88`, borderRadius: 24, padding: 42, background: color.panel, display: 'flex', flexDirection: 'column', justifyContent: 'space-between'}}>
      <div style={{fontSize: 23, letterSpacing: 3, color: color.teal, fontWeight: 800}}>TABLETOP RIG · ILLUSTRATION</div>
      <div style={{display: 'flex', alignItems: 'center', gap: 34}}><div style={{width: 150, height: 150, border: `14px solid ${color.teal}`, borderRadius: '50%', display: 'grid', placeItems: 'center', fontSize: 40}}>N20</div><div style={{fontSize: 51, fontWeight: 700}}>Motor<br />+ servo</div></div>
      <div style={{fontSize: 31, color: color.muted}}>Physical demonstration, separately observed</div>
    </div>
    <div style={{display: 'flex', flexDirection: 'column', gap: 28}}><Note heading="SOFTWARE INPUT" text="Synthetic four-motor simulator readings." /><Note heading="SAFETY BOUNDARY" text="Diagnosis is advisory; it does not command the rig." amber /><Note heading="HUMAN CHECK" text="A technician performs physical inspection." /></div>
  </div>;
}

function MubitStatus() {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const showingDashboard = frame < 7 * fps;
  const screenshot = showingDashboard ? 'mubit-dashboard-2026-10-24.png' : 'mubit-tasks-2026-10-24.png';

  return <div style={{display: 'grid', gridTemplateColumns: '1.32fr 0.68fr', gap: 30, height: '100%'}}>
    <div style={{position: 'relative', overflow: 'hidden', borderRadius: 22, border: `1px solid ${color.teal}88`, background: '#171e1a', boxShadow: '0 28px 80px #0005'}}>
      <Img src={staticFile(`assets/${screenshot}`)} style={{width: '100%', height: '100%', objectFit: 'cover', objectPosition: 'left center'}} />
      <div style={{position: 'absolute', left: 24, top: 22, padding: '10px 18px', borderRadius: 8, background: '#071520ee', color: color.teal, fontSize: 22, fontWeight: 800, letterSpacing: 1}}>MUBIT CONSOLE · 24 OCT · {showingDashboard ? '14:33' : '23:30'}</div>
    </div>
    <div style={{display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: 22}}>
      {showingDashboard ? <>
        <Note heading="REQUESTS RECORDED" text="Four requests in this dashboard capture." />
        <Note heading="ADAPTERS SERVING" text="Zero at the time of capture." amber />
        <div style={{fontSize: 24, color: color.muted, lineHeight: 1.25}}>The console says first training starts at 25 examples.</div>
      </> : <>
        <Note heading="TASK STATE" text="Still reviewing examples; 12 of 25 shown." />
        <Note heading="ADAPTER STATUS" text="No adapter was serving at this point." amber />
        <div style={{fontSize: 23, color: color.muted, lineHeight: 1.25}}>The first training threshold had not been reached. We hope to test the adapter path when it is ready.</div>
      </>}
    </div>
  </div>;
}

export const RoboMedicDemo: React.FC = () => {
  const {fps} = useVideoConfig();
  const customNarration = assetExists('narration.mp3');
  return <AbsoluteFill style={base}>
    {customNarration && <Audio src={staticFile('assets/narration.mp3')} />}
    <Sequence durationInFrames={10 * fps} name="01 Problem">{!customNarration && <Audio src={staticFile('assets/demo-voice-01.wav')} />}<Frame number="01" section="THE PROBLEM" title="ROBO MEDIC" caption="A fault alert needs a useful diagnosis, and a practical next check." seconds={10}><div style={{height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between'}}><div style={{maxWidth: 1020, fontSize: 65, lineHeight: 1.15, fontWeight: 700}}>From an opaque alert to an <span style={{color: color.teal}}>evidence-based next step.</span></div><div style={{width: 360, height: 360, borderRadius: '50%', border: `18px solid ${color.red}`, display: 'grid', placeItems: 'center', color: color.red, fontSize: 180, fontWeight: 800}}>!</div></div></Frame></Sequence>

    <Sequence from={10 * fps} durationInFrames={20 * fps} name="02 Incident input">{!customNarration && <Audio src={staticFile('assets/demo-voice-02.wav')} />}<Frame number="02" section="THE INPUT" title="Start with the incident" caption="This demonstration uses a synthetic robot fault. The source stays visible." seconds={20}><Split filename="app-incident.mp4" still="demo-incident.png" zoom={1.65} shiftX={185} shiftY={125} label="Real app incident recording"><Note heading="SYNTHETIC CASE" text="150 RPM commanded; 0 RPM observed; about 1 A current." /><Note heading="SOURCE" text="Four-motor simulator; no physical-board intake in this build." amber /></Split></Frame></Sequence>

    <Sequence from={30 * fps} durationInFrames={25 * fps} name="03 Diagnosis">{!customNarration && <Audio src={staticFile('assets/demo-voice-03.wav')} />}<Frame number="03" section="THE DIAGNOSIS" title="A reasoned advisory" caption="An offline rule fixture gives advice. It is not a Mubit or LLM result." seconds={25}><Split filename="app-diagnosis.mp4" still="demo-diagnosis.png" zoom={1.7} shiftX={-465} shiftY={155} label="Actual diagnosis screen recording"><Note heading="LIKELY CAUSE" text="Wheel obstruction; medium uncertainty." /><Note heading="ALTERNATIVE" text="Motor power or driver path." /><Note heading="NEXT CHECK" text="Inspect the wheel with power isolated." amber /></Split></Frame></Sequence>

    <Sequence from={55 * fps} durationInFrames={17 * fps} name="04 Technician feedback">{!customNarration && <Audio src={staticFile('assets/demo-voice-04.wav')} />}<Frame number="04" section="HUMAN VERIFICATION" title="Record the outcome" caption="This demo reconstructs the documented simulator reset in a separate local record." seconds={17}><Split filename="app-feedback.mp4" still="demo-feedback.png" zoom={1.7} shiftX={-465} shiftY={-135} label="Technician outcome recording"><Note heading="HISTORICAL CHECK-IN" text="The documented reset restored about 152 RPM." /><Note heading="LOCAL RECORD" text="The original prediction stays unchanged." /><Note heading="BOUNDARY" text="Local feedback does not train a Mubit adapter." amber /></Split></Frame></Sequence>

    <Sequence from={72 * fps} durationInFrames={23 * fps} name="05 Hardware cutaway">{!customNarration && <Audio src={staticFile('assets/demo-voice-05.wav')} />}<Frame number="05" section="TABLETOP CONTEXT" title="Hardware stays separate" caption="Illustration only. This build does not ingest measurements from the physical rig." seconds={23}>{assetExists('hardware-rig.mp4') ? <Split filename="hardware-rig.mp4" label="N20 motor and servo tabletop clip"><Note heading="TABLETOP DEMO" text="N20 motor and servo footage." /><Note heading="BOUNDARY" text="The diagnosis does not control these motors." amber /></Split> : <HardwareIllustration />}</Frame></Sequence>

    <Sequence from={95 * fps} durationInFrames={17 * fps} name="06 Mubit status">{!customNarration && <Audio src={staticFile('assets/demo-voice-06.wav')} />}<Frame number="06" section="MUBIT STATUS" title="What we could verify" caption="Review was still underway, so an adapter wasn't ready for this demo." seconds={17}><MubitStatus /></Frame></Sequence>

    <Sequence from={112 * fps} durationInFrames={8 * fps} name="07 Close">{!customNarration && <Audio src={staticFile('assets/demo-voice-07.wav')} />}<Frame number="07" section="CLOSE" title="ROBO MEDIC" caption="Any adapter benefit still needs to be tested." seconds={8}><div style={{height: '100%', display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: 36}}><div style={{fontSize: 66, lineHeight: 1.16, fontWeight: 700}}>Evidence-based diagnosis.<br />Technician feedback.<br /><span style={{color: color.teal}}>A learning loop ready to continue.</span></div><div style={{fontSize: 30, color: color.muted}}>We hope to test whether a trained adapter makes future triage more useful.</div></div></Frame></Sequence>
  </AbsoluteFill>;
};
