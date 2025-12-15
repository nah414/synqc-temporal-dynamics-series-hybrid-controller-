# SynQc TDS — Fullstack Review (ONE FILE) v0.4

Date: 2025-12-12

This file contains the **entire frontend + backend source** needed to review the SynQc TDS Sleek Repo in one place.

## web/index.html

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>SynQc TDS — Temporal Dynamics Console v0.4</title>
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <style>
    :root {
      --bg-main: #050412;
      --bg-panel: #0b0f23;
      --bg-panel-soft: #11162c;
      --accent: #6ae5ff;
      --accent-strong: #ffdd6e;
      --text-main: #f6f7ff;
      --text-soft: #a6acd3;
      --border-subtle: #262b44;
      --kpi-good: #2ecc71;
      --kpi-warn: #ffb94d;
      --kpi-bad: #ff4d6a;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      padding: 0;
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: radial-gradient(circle at top, #171b3f 0, #050412 55%, #02020a 100%);
      color: var(--text-main);
      overflow-x: hidden;
    }
    .app {
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      position: relative;
    }
    .particle-layer {
      position: fixed;
      inset: 0;
      overflow: hidden;
      pointer-events: none;
      z-index: 0;
    }
    .particle {
      position: absolute;
      width: 4px;
      height: 4px;
      border-radius: 999px;
      background: radial-gradient(circle at 30% 30%, #ffffff, rgba(255,255,255,0));
      opacity: 0.7;
      animation: floatParticle 18s linear infinite;
    }
    .particle::after {
      content: "";
      position: absolute;
      inset: -6px;
      border-radius: inherit;
      background: radial-gradient(circle, rgba(106,229,255,0.45), transparent 60%);
      opacity: 0.4;
      filter: blur(2px);
    }
    @keyframes floatParticle {
      0% { transform: translate3d(0, 0, 0) scale(1); opacity: 0.2; }
      20% { opacity: 0.7; }
      50% { transform: translate3d(40px, -60px, 0) scale(1.15); }
      80% { opacity: 0.4; }
      100%{ transform: translate3d(-20px,-120px,0) scale(0.9); opacity: 0; }
    }
    header {
      position: sticky;
      top: 0;
      z-index: 5;
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0.7rem 1.6rem;
      background: linear-gradient(to right, rgba(4,6,20,0.96), rgba(8,9,28,0.96));
      border-bottom: 1px solid var(--border-subtle);
      backdrop-filter: blur(18px);
    }
    .brand { display: flex; align-items: center; gap: 0.7rem; }
    .brand-logo {
      width: 30px; height: 30px; border-radius: 999px;
      background:
        radial-gradient(circle at 30% 25%, #ffffff, rgba(255,255,255,0) 55%),
        conic-gradient(from 140deg, #6ae5ff, #20e3b2, #ffdd6e, #6ae5ff);
      box-shadow: 0 0 16px rgba(106,229,255,0.8);
      position: relative;
    }
    .brand-logo::after {
      content: "";
      position: absolute; inset: 5px; border-radius: inherit;
      background: radial-gradient(circle at 70% 80%, rgba(32,227,178,0.5), transparent 55%);
      mix-blend-mode: screen;
    }
    .brand-text-title { font-weight: 600; letter-spacing: 0.04em; font-size: 1rem; }
    .brand-text-sub { font-size: 0.73rem; color: var(--text-soft); }
    .nav-links { display: flex; gap: 1.2rem; font-size: 0.83rem; }
    .nav-links button {
      background: none; border: none; color: var(--text-soft);
      cursor: pointer; padding: 0.3rem 0; position: relative;
    }
    .nav-links button.active, .nav-links button:hover { color: var(--text-main); }
    .nav-links button.active::after {
      content: ""; position: absolute; left: 0; right: 0; bottom: -0.35rem;
      height: 2px; border-radius: 999px;
      background: linear-gradient(to right, #6ae5ff, #ffdd6e);
    }
    .header-right { display: flex; align-items: center; gap: 1rem; font-size: 0.8rem; }
    .mode-toggle {
      display: inline-flex; align-items: center; gap: 0.2rem;
      padding: 0.2rem; border-radius: 999px;
      border: 1px solid var(--border-subtle);
      background: rgba(10,13,36,0.9);
    }
    .mode-pill {
      padding: 0.2rem 0.6rem; border-radius: 999px; cursor: pointer;
      font-size: 0.75rem; color: var(--text-soft);
    }
    .mode-pill.active {
      background: linear-gradient(to right, #6ae5ff, #ffdd6e);
      color: #050412; font-weight: 600;
    }
    .avatar {
      width: 28px; height: 28px; border-radius: 999px;
      display: inline-flex; align-items: center; justify-content: center;
      border: 1px solid var(--border-subtle);
      background: radial-gradient(circle at 30% 20%, #6ae5ff, #151831);
      font-size: 0.75rem;
    }
    main {
      position: relative; z-index: 1; flex: 1;
      padding: 1rem 1.5rem 1.6rem;
    }

    .view { display: none; }
    .view.active { display: block; }

    .console-grid {
      display: grid;
      grid-template-columns: minmax(260px, 320px) minmax(0, 1.9fr) minmax(260px, 0.9fr);
      grid-template-rows: minmax(260px, 1.4fr) minmax(220px, 1.2fr);
      grid-template-areas: "agent scene history" "agent scene history";
      gap: 1rem;
    }
    @media (max-width: 1100px) {
      .console-grid {
        grid-template-columns: minmax(260px, 320px) minmax(0, 1.6fr);
        grid-template-rows: auto auto auto;
        grid-template-areas: "scene scene" "agent history" "agent history";
      }
    }
    @media (max-width: 800px) {
      .console-grid {
        grid-template-columns: minmax(0, 1fr);
        grid-template-rows: auto auto auto;
        grid-template-areas: "scene" "agent" "history";
      }
    }
    .panel {
      background:
        radial-gradient(circle at 10% 0%, rgba(106,229,255,0.18), transparent 55%),
        linear-gradient(to bottom right, rgba(8,10,30,0.96), rgba(10,14,32,0.98));
      border-radius: 18px;
      border: 1px solid var(--border-subtle);
      padding: 0.85rem 0.9rem;
      box-shadow: 0 20px 40px rgba(0,0,0,0.55);
    }
    .panel-header {
      display: flex; align-items: center; justify-content: space-between;
      margin-bottom: 0.6rem; gap: 0.5rem;
    }
    .panel-title {
      font-size: 0.85rem; text-transform: uppercase;
      letter-spacing: 0.14em; color: var(--text-soft);
    }
    .panel-sub { font-size: 0.75rem; color: var(--text-soft); opacity: 0.85; }
    .panel-agent { grid-area: agent; display: flex; flex-direction: column; gap: 0.6rem; }
    .agent-tabs {
      display: inline-flex; border-radius: 999px;
      border: 1px solid var(--border-subtle);
      background: rgba(6,8,25,0.9); font-size: 0.76rem;
    }
    .agent-tabs button {
      border: none; background: transparent; padding: 0.3rem 0.8rem;
      border-radius: 999px; cursor: pointer; color: var(--text-soft);
    }
    .agent-tabs button.active {
      background: linear-gradient(to right, #6ae5ff, #ffdd6e);
      color: #050412; font-weight: 600;
    }
    .agent-body {
      flex: 1; display: flex; flex-direction: column; gap: 0.6rem; min-height: 220px;
    }
    .agent-chat-log {
      flex: 1; border-radius: 14px;
      background: rgba(8,10,30,0.96);
      border: 1px solid var(--border-subtle);
      padding: 0.6rem 0.65rem;
      font-size: 0.78rem;
      display: flex; flex-direction: column; gap: 0.4rem;
      overflow-y: auto;
    }
    .msg { max-width: 100%; line-height: 1.35; white-space: pre-wrap; word-break: break-word; }
    .msg-user { color: #6ae5ff; }
    .msg-agent{ color: var(--text-soft); }
    .agent-input-row {
      display: flex; gap: 0.4rem; margin-top: 0.1rem;
    }
    .agent-input-row input {
      flex: 1; border-radius: 999px; border: 1px solid var(--border-subtle);
      background: rgba(10,13,34,0.96);
      padding: 0.45rem 0.6rem; font-size: 0.78rem;
      color: var(--text-main); outline: none;
    }
    .agent-input-row input::placeholder { color: var(--text-soft); }
    .agent-input-row button {
      border-radius: 999px; border: none; padding: 0.4rem 0.8rem;
      font-size: 0.78rem; cursor: pointer;
      background: linear-gradient(to right, #6ae5ff, #ffdd6e);
      color: #050412; font-weight: 600;
    }

.primary-btn {
  border-radius: 12px;
  border: none;
  padding: 0.5rem 0.75rem;
  font-size: 0.8rem;
  cursor: pointer;
  background: linear-gradient(to right, #6ae5ff, #ffdd6e);
  color: #050412;
  font-weight: 700;
}
.primary-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

    .agent-setup {
      border-radius: 14px; border: 1px solid var(--border-subtle);
      background: rgba(8,10,29,0.96);
      padding: 0.55rem 0.6rem; font-size: 0.78rem;
      display: flex; flex-direction: column; gap: 0.4rem;
    }
    .field-row { display: flex; flex-direction: column; gap: 0.15rem; }
    .field-label { font-size: 0.74rem; color: var(--text-soft); }
    .field-input, .field-select {
      border-radius: 10px; border: 1px solid var(--border-subtle);
      background: #07091c; color: var(--text-main);
      padding: 0.3rem 0.45rem; font-size: 0.78rem; outline: none;
    }
    .panel-scene { grid-area: scene; display: flex; flex-direction: column; gap: 0.7rem; }
    .scene-top {
      display: flex; justify-content: space-between;
      align-items: center; gap: 0.7rem; flex-wrap: wrap;
    }
    .scene-kpis { display: flex; gap: 0.4rem; flex-wrap: wrap; }
    .kpi-card {
      min-width: 90px; border-radius: 12px; padding: 0.4rem 0.5rem;
      background: rgba(10,13,34,0.96);
      border: 1px solid var(--border-subtle);
      font-size: 0.72rem;
    }
    .kpi-label { color: var(--text-soft); margin-bottom: 0.1rem; }
    .kpi-value { font-size: 0.9rem; font-weight: 600; }
    .kpi-good { color: var(--kpi-good); }
    .kpi-warn { color: var(--kpi-warn); }
    .kpi-bad  { color: var(--kpi-bad); }
    .scene-main {
      display: grid;
      grid-template-columns: minmax(0, 1.1fr) minmax(200px, 0.9fr);
      gap: 0.8rem; align-items: stretch;
    }
    @media (max-width: 900px) {
      .scene-main { grid-template-columns: minmax(0, 1fr); }
    }
    .scene-visual {
      border-radius: 16px; border: 1px solid var(--border-subtle);
      background:
        radial-gradient(circle at 15% 10%, rgba(255,255,255,0.12), transparent 60%),
        radial-gradient(circle at 80% 90%, rgba(106,229,255,0.18), transparent 60%),
        #050616;
      padding: 0.7rem; position: relative; overflow: hidden;
    }
    .dpd-label {
      position: absolute; top: 0.6rem; right: 0.9rem;
      font-size: 0.65rem; text-transform: uppercase;
      letter-spacing: 0.12em; color: var(--text-soft);
      background: rgba(5,6,20,0.9);
      padding: 0.2rem 0.5rem; border-radius: 999px;
      border: 1px solid rgba(123,132,200,0.5);
    }
    .bloch-wrapper {
      display: flex; align-items: center; justify-content: center; padding-top: 0.2rem;
    }
    .bloch-sphere {
      width: 190px; height: 190px; border-radius: 999px;
      border: 1px solid rgba(255,255,255,0.12);
      background:
        radial-gradient(circle at 30% 20%, rgba(255,255,255,0.35), rgba(255,255,255,0) 55%),
        radial-gradient(circle at 70% 80%, rgba(106,229,255,0.55), rgba(106,229,255,0) 60%),
        radial-gradient(circle at 50% 50%, rgba(0,0,0,0.9), rgba(0,0,0,1));
      position: relative;
      box-shadow: 0 0 25px rgba(0,0,0,0.85);
    }
    .bloch-equator, .bloch-meridian {
      position: absolute; left: 50%; top: 50%;
      transform: translate(-50%, -50%);
      border-radius: 999px;
      border: 1px dashed rgba(200,210,255,0.35);
    }
    .bloch-equator { width: 130px; height: 130px; }
    .bloch-meridian{ width: 130px; height: 130px; transform: translate(-50%,-50%) rotateY(80deg); }
    .bloch-state {
      position: absolute; width: 10px; height: 10px;
      border-radius: 999px;
      background: radial-gradient(circle at 30% 30%, #ffffff, rgba(255,255,255,0));
      box-shadow: 0 0 12px rgba(255,255,255,0.8);
      animation: stateOrbit 8s ease-in-out infinite;
      transform-origin: 50% 50%;
    }
    .bloch-axis-z {
      position: absolute; left: 50%; top: 8%;
      width: 2px; height: 84%;
      transform: translateX(-50%);
      background: linear-gradient(to bottom, rgba(255,255,255,0.2), rgba(255,255,255,0));
      opacity: 0.6;
    }
    @keyframes stateOrbit {
      0%   { transform: translate(80px, 10px)   scale(1); }
      25%  { transform: translate(20px, -70px)  scale(1.1); }
      50%  { transform: translate(-75px, -5px)  scale(0.95); }
      75%  { transform: translate(-20px, 70px)  scale(1.05); }
      100% { transform: translate(80px, 10px)   scale(1); }
    }
    .scene-timeline {
      font-size: 0.75rem; color: var(--text-soft);
      display: flex; flex-direction: column; gap: 0.5rem;
    }
    .timeline-bar {
      display: flex; align-items: center; gap: 0.35rem; margin-top: 0.2rem;
    }
    .segment {
      height: 10px; border-radius: 999px; position: relative;
      background: rgba(255,255,255,0.07); flex-shrink: 0;
    }
    .segment-drive  { flex: 0.8; background: linear-gradient(to right, rgba(106,229,255,0.9), rgba(32,227,178,0.8)); }
    .segment-probe  { flex: 0.5; background: linear-gradient(to right, rgba(255,221,110,0.9), rgba(255,173,76,0.85)); }
    .segment-drive2 { flex: 0.7; background: linear-gradient(to right, rgba(32,227,178,0.9), rgba(106,229,255,0.85)); }
    .segment-label { font-size: 0.7rem; color: var(--text-soft); }
    .scene-notes { font-size: 0.73rem; color: var(--text-soft); opacity: 0.85; line-height: 1.4; }
    .panel-history { grid-area: history; display: flex; flex-direction: column; gap: 0.6rem; }
    .history-filters {
      display: flex; flex-wrap: wrap; gap: 0.35rem; font-size: 0.72rem;
    }
    .filter-pill {
      padding: 0.18rem 0.45rem; border-radius: 999px;
      border: 1px solid var(--border-subtle);
      background: rgba(7,9,26,0.95);
      color: var(--text-soft); cursor: pointer;
    }
    .filter-pill.active { border-color: #6ae5ff; color: #6ae5ff; }
    .history-table-wrap {
      flex: 1; border-radius: 14px; border: 1px solid var(--border-subtle);
      background: rgba(8,10,30,0.96);
      padding: 0.4rem 0.45rem;
      font-size: 0.75rem; overflow-y: auto;
    }
    table { width: 100%; border-spacing: 0; border-collapse: collapse; }
    th, td { padding: 0.3rem 0.25rem; text-align: left; white-space: nowrap; }
    th {
      color: var(--text-soft); font-weight: 500; font-size: 0.72rem;
      border-bottom: 1px solid var(--border-subtle);
      position: sticky; top: 0; background: rgba(7,9,26,0.97); z-index: 1;
    }
    tbody tr { border-bottom: 1px solid rgba(25,30,60,0.9); }
    tbody tr:hover { background: rgba(106,229,255,0.07); }
    .status-pill {
      padding: 0.12rem 0.4rem; border-radius: 999px; font-size: 0.7rem;
    }
    .status-ok   { background: rgba(46,204,113,0.18); color: var(--kpi-good); }
    .status-warn { background: rgba(255,185,77,0.18); color: var(--kpi-warn); }
    .status-fail { background: rgba(255,77,106,0.18); color: var(--kpi-bad); }
    .history-footer-note {
      margin-top: 0.25rem; font-size: 0.7rem; color: var(--text-soft); opacity: 0.9;
    }
    footer {
      position: relative; z-index: 1;
      padding: 0.7rem 1.6rem 1rem;
      font-size: 0.7rem; color: var(--text-soft);
      border-top: 1px solid var(--border-subtle);
      background: radial-gradient(circle at top, rgba(18,24,64,0.96), rgba(6,7,20,0.98));
    }
  
    /* --------------------------------------------
       Visual detail upgrades (v0.3)
       - Decorative layers are aria-hidden
       - Animation speeds are adjustable from JS based on KPIs
       -------------------------------------------- */
    .panel-credit{
      margin-top: 0.55rem;
      font-size: 0.72rem;
      color: rgba(215,225,255,0.72);
      letter-spacing: 0.02em;
      text-align: right;
      opacity: 0.9;
      user-select: none;
    }

    .bloch-atmosphere{
      position:absolute;
      inset: -18px;
      border-radius: 999px;
      background:
        radial-gradient(circle at 30% 30%, rgba(106,229,255,0.35), rgba(106,229,255,0) 55%),
        radial-gradient(circle at 70% 80%, rgba(32,227,178,0.25), rgba(32,227,178,0) 60%),
        radial-gradient(circle at 50% 50%, rgba(255,255,255,0.12), rgba(255,255,255,0));
      filter: blur(10px);
      opacity: 0.38;
      animation: glowPulse 6.5s ease-in-out infinite;
      pointer-events:none;
      z-index: 0;
    }
    @keyframes glowPulse {
      0%, 100% { transform: scale(0.98); filter: blur(10px); }
      50%      { transform: scale(1.02); filter: blur(12px); }
    }

    .bloch-noise{
      position:absolute;
      inset: 0;
      border-radius: 999px;
      background:
        radial-gradient(circle at 20% 15%, rgba(255,255,255,0.06), rgba(255,255,255,0) 40%),
        radial-gradient(circle at 75% 85%, rgba(106,229,255,0.08), rgba(106,229,255,0) 45%),
        repeating-linear-gradient(135deg, rgba(255,255,255,0.02) 0px, rgba(255,255,255,0.02) 2px, rgba(0,0,0,0) 6px, rgba(0,0,0,0) 10px);
      opacity: 0.0;
      mix-blend-mode: screen;
      animation: noiseDrift 5.8s ease-in-out infinite;
      pointer-events:none;
      z-index: 1;
    }
    @keyframes noiseDrift{
      0%   { transform: translate(0px, 0px) rotate(0deg); }
      50%  { transform: translate(2px, -3px) rotate(8deg); }
      100% { transform: translate(0px, 0px) rotate(0deg); }
    }

    .bloch-ring{
      position:absolute;
      left:50%;
      top:50%;
      transform: translate(-50%, -50%);
      border-radius: 999px;
      border: 1px solid rgba(200,210,255,0.18);
      box-shadow: 0 0 14px rgba(106,229,255,0.10);
      pointer-events:none;
      z-index: 2;
      animation: ringSpinA 16s linear infinite;
    }
    .bloch-ring.ring-a{
      width: 170px; height: 170px;
      border-style: dotted;
      opacity: 0.55;
      animation-name: ringSpinA;
    }
    .bloch-ring.ring-b{
      width: 140px; height: 140px;
      border-style: dashed;
      opacity: 0.42;
      animation-name: ringSpinB;
      animation-duration: 22s;
    }
    .bloch-ring.ring-c{
      width: 110px; height: 110px;
      border-style: solid;
      opacity: 0.28;
      animation-name: ringSpinC;
      animation-duration: 30s;
    }

    @keyframes ringSpinA{
      from { transform: translate(-50%, -50%) rotate(0deg); }
      to   { transform: translate(-50%, -50%) rotate(360deg); }
    }
    @keyframes ringSpinB{
      from { transform: translate(-50%, -50%) rotate(35deg) skewX(10deg); }
      to   { transform: translate(-50%, -50%) rotate(395deg) skewX(10deg); }
    }
    @keyframes ringSpinC{
      from { transform: translate(-50%, -50%) rotate(75deg) skewY(12deg); }
      to   { transform: translate(-50%, -50%) rotate(435deg) skewY(12deg); }
    }

    .bloch-trace{
      position:absolute;
      left: 50%;
      top: 50%;
      width: 170px;
      height: 170px;
      transform: translate(-50%, -50%);
      opacity: 0.55;
      z-index: 3;
      animation: traceSpin 20s linear infinite;
      pointer-events:none;
    }
    @keyframes traceSpin{
      from { transform: translate(-50%, -50%) rotate(0deg); }
      to   { transform: translate(-50%, -50%) rotate(360deg); }
    }
    .trace-path{
      fill: none;
      stroke: rgba(255,221,110,0.50);
      stroke-width: 0.85;
      stroke-dasharray: 4 7;
      animation: traceDash 3.6s linear infinite;
      filter: drop-shadow(0 0 5px rgba(255,221,110,0.12));
    }
    .trace-path2{
      stroke: rgba(32,227,178,0.36);
      stroke-dasharray: 2 6;
      animation-duration: 4.4s;
    }
    @keyframes traceDash{
      to { stroke-dashoffset: -70; }
    }

    .bloch-orbit-dot{
      position:absolute;
      left: 50%;
      top: 50%;
      width: 6px;
      height: 6px;
      border-radius: 999px;
      background: radial-gradient(circle at 30% 30%, #ffffff, rgba(255,255,255,0));
      box-shadow: 0 0 10px rgba(106,229,255,0.65);
      transform: translate(88px, 0px);
      transform-origin: -88px 0px;
      animation: orbitDot 7.5s linear infinite;
      opacity: 0.75;
      pointer-events:none;
      z-index: 6;
    }
    @keyframes orbitDot{
      from { transform: translate(88px, 0px) rotate(0deg); }
      to   { transform: translate(88px, 0px) rotate(360deg); }
    }

    /* Timeline motion cue (DPD "spark") */
    .timeline-animated{
      position: relative;
      overflow: hidden;
    }
    .timeline-spark{
      position: absolute;
      left: -25%;
      top: 50%;
      width: 22%;
      height: 2px;
      transform: translateY(-50%);
      background: linear-gradient(to right, rgba(0,0,0,0), rgba(106,229,255,0.90), rgba(0,0,0,0));
      opacity: 0.75;
      filter: blur(0.3px);
      animation: sparkMove 4.2s linear infinite;
      pointer-events:none;
    }
    @keyframes sparkMove{
      from { left: -25%; }
      to   { left: 100%; }
    }

    /* Small enhancement: allow the state animation speed to be set from JS */
    .bloch-state{
      animation-duration: 8s;
      z-index: 7;
    }


    /* --------------------------------------------
       View pages (v0.4)
       -------------------------------------------- */
    .page-wrap{
      max-width: 1100px;
      margin: 0 auto;
    }

    .small-btn{
      border-radius: 999px;
      border: 1px solid var(--border-subtle);
      background: rgba(10,13,34,0.96);
      color: var(--text-main);
      padding: 0.35rem 0.7rem;
      font-size: 0.78rem;
      cursor: pointer;
    }
    .small-btn:hover{
      border-color: rgba(106,229,255,0.65);
    }

    .hardware-list{
      margin-top: 0.65rem;
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 0.7rem;
    }
    .hardware-item{
      border-radius: 14px;
      border: 1px solid var(--border-subtle);
      background: rgba(8,10,30,0.96);
      padding: 0.6rem 0.65rem;
      display: flex;
      flex-direction: column;
      gap: 0.3rem;
    }
    .hardware-top{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 0.5rem;
    }
    .hardware-name{
      font-weight: 650;
      font-size: 0.86rem;
      letter-spacing: 0.01em;
    }
    .hardware-badge{
      font-size: 0.68rem;
      padding: 0.14rem 0.5rem;
      border-radius: 999px;
      border: 1px solid rgba(123,132,200,0.55);
      color: rgba(215,225,255,0.8);
      background: rgba(7,9,26,0.9);
      white-space: nowrap;
    }
    .hardware-meta{
      font-size: 0.74rem;
      color: var(--text-soft);
    }

    .detail-actions{
      display: flex;
      gap: 0.45rem;
      align-items: center;
    }

    .json-block{
      margin-top: 0.45rem;
      border-radius: 14px;
      border: 1px solid var(--border-subtle);
      background: rgba(7,9,26,0.96);
      padding: 0.6rem 0.7rem;
      font-size: 0.75rem;
      color: rgba(240,243,255,0.92);
      overflow: auto;
      max-height: 44vh;
    }

    .hint{
      font-size: 0.72rem;
      color: rgba(215,225,255,0.78);
      opacity: 0.92;
    }

</style>
</head>
<body>
  <div class="app">
    <div class="particle-layer" id="particleLayer"></div>

    <header>
      <div class="brand">
        <div class="brand-logo"></div>
        <div>
          <div class="brand-text-title">SynQc TDS</div>
          <div class="brand-text-sub">Temporal Dynamics Console</div>
        </div>
      </div>

      <nav class="nav-links" aria-label="Primary">
        <button class="active" data-view="console">Console</button>
        <button data-view="experiments">Experiments</button>
        <button data-view="hardware">Hardware</button>
        <button data-view="details">Details</button>
      </nav>

      <div class="header-right">
        <div class="mode-toggle">
          <div class="mode-pill active" data-mode="explore">Explore</div>
          <div class="mode-pill" data-mode="calibrate">Calibrate</div>
          <div class="mode-pill" data-mode="prod">Production</div>
        </div>
        <div class="avatar">SynQc</div>
      </div>
    </header>

    <main>
      <div class="view active" id="view-console">
        <div class="console-grid">
<section class="panel panel-agent">
        <div class="panel-header">
          <div>
            <div class="panel-title">SynQc Guide</div>
            <div class="panel-sub">Agent & experiment setup</div>
          </div>
          <div class="agent-tabs">
            <button class="active" data-tab="chat">Agent</button>
            <button data-tab="setup">Setup</button>
          </div>
        </div>

        <div class="agent-body">
          <div class="agent-chat-log" id="agentChatLog">
            <div class="msg msg-agent">
              <strong>SynQc Guide:</strong> Welcome. Tell me what you want to learn or test —
              examples: “Run a coherence health check”, “Measure latency”, “Compare this backend
              to the simulator”, or “Walk me through a full SynQc DPD example.”
            </div>
          </div>

          <div class="agent-input-row">
            <input id="agentInput" type="text" placeholder="Describe your goal, e.g. 'Check coherence on IBM simulator'…" />
            <button id="agentSend">Send</button>
          </div>

          <div class="agent-setup" id="agentSetupPanel" style="display:none;">
            <div class="field-row">
              <div class="field-label">Hardware target</div>
              <select class="field-select" id="hardwareSelect">
                <option value="sim_local">Local simulator</option>
                <option value="ibm_qpu">IBM QPU (concept)</option>
                <option value="ionq_qpu">IonQ QPU (concept)</option>
                <option value="lab_fpga">Lab FPGA rig (concept)</option>
              </select>
            </div>
            <div class="field-row">
              <div class="field-label">Experiment preset</div>
              <select class="field-select" id="presetSelect">
                <option value="health">Qubit Health Diagnostics (T1/T2/RB)</option>
                <option value="latency">Latency Characterization</option>
                <option value="backend_compare">Backend A/B Comparison</option>
                <option value="dpd_demo">Guided SynQc DPD Example</option>
              </select>
            </div>
            <div class="field-row">
              <div class="field-label" id="shotLabel">Shot budget (max)</div>
              <input class="field-input" id="shotInput" type="number" value="2048" />
            </div>
<div class="field-row">
  <div class="field-label">Notes</div>
  <textarea class="field-input" id="notesInput" rows="3" placeholder="Optional notes (chip ID, temperature, goal)…"></textarea>
  <div class="panel-sub">
    These controls represent high-level intent. Detailed pulse-level configuration,
    timing windows, and safety limits are handled by the SynQc engine and hardware backends.
  </div>
</div>

<div class="field-row">
  <div class="field-label">Actions</div>
  <button class="primary-btn" id="runPresetBtn" type="button">Run preset</button>
  <div class="panel-sub" id="runStatus" aria-live="polite">Backend: not connected yet.</div>
              <div class="panel-credit">Developed by eVision Enterprises</div>
</div>
</div>
        </div>
      </section>

      <section class="panel panel-scene">
        <div class="panel-header">
          <div>
            <div class="panel-title">Quantum Scene & KPIs</div>
            <div class="panel-sub">Drive–Probe–Drive (DPD) temporal dynamics view</div>
          </div>
        </div>
        <div class="scene-top">
          <div class="scene-kpis">
            <div class="kpi-card">
              <div class="kpi-label">Fidelity</div>
              <div class="kpi-value kpi-good" id="kpiFidelity">0.972</div>
            </div>
            <div class="kpi-card">
              <div class="kpi-label">Latency</div>
              <div class="kpi-value" id="kpiLatency">18.4 µs</div>
            </div>
            <div class="kpi-card">
              <div class="kpi-label">Backaction</div>
              <div class="kpi-value kpi-warn" id="kpiBackaction">0.21</div>
            </div>
            <div class="kpi-card">
              <div class="kpi-label">Shots used</div>
              <div class="kpi-value" id="kpiShots">1.2k / 2.0k</div>
            </div>
          </div>
          <div class="panel-sub">
            Current preset: <strong id="scenePresetLabel">Qubit Health Diagnostics</strong> ·
            Hardware: <strong id="sceneHardwareLabel">Local simulator</strong>
          </div>
        </div>
        <div class="scene-main">
          <div class="scene-visual">
            <div class="dpd-label">Drive · Probe · Drive</div>
            <div class="bloch-wrapper">
              <div class="bloch-sphere" aria-label="Bloch sphere state visualization">
                <div class="bloch-atmosphere" id="blochAtmosphere" aria-hidden="true"></div>
                <div class="bloch-noise" id="blochNoise" aria-hidden="true"></div>
                <div class="bloch-ring ring-a" id="blochRingA" aria-hidden="true"></div>
                <div class="bloch-ring ring-b" id="blochRingB" aria-hidden="true"></div>
                <div class="bloch-ring ring-c" id="blochRingC" aria-hidden="true"></div>

                <svg class="bloch-trace" id="blochTrace" viewBox="0 0 100 100" aria-hidden="true">
                  <path class="trace-path" d="M10 50 C 25 15, 75 15, 90 50 C 75 85, 25 85, 10 50 Z"></path>
                  <path class="trace-path trace-path2" d="M20 50 C 32 28, 68 28, 80 50 C 68 72, 32 72, 20 50 Z"></path>
                </svg>

                <div class="bloch-equator"></div>
                <div class="bloch-meridian"></div>
                <div class="bloch-axis-z"></div>
                <div class="bloch-state" id="blochState"></div>
                <div class="bloch-orbit-dot" id="blochOrbitDot" aria-hidden="true"></div>
              </div>
            </div>
            <div class="scene-notes">
              This visualization represents the effective state of a single qubit under a SynQc
              Drive–Probe–Drive (DPD) protocol. The moving point suggests how your combined drive,
              probe, and feedback operations move the state on (and off) the Bloch sphere in time.
            </div>
          </div>
          <div class="scene-timeline">
            <div>
              <strong>Temporal sequence</strong>
              <div class="panel-sub">
                High-level structure of the current SynQc experiment bundle.
              </div>
              <div class="timeline-bar timeline-animated">
                <div class="timeline-spark" id="timelineSpark" aria-hidden="true"></div>
                <div class="segment segment-drive"></div>
                <div class="segment segment-probe"></div>
                <div class="segment segment-drive2"></div>
              </div>
              <div class="timeline-bar">
                <span class="segment-label">Drive</span>
                <span class="segment-label">Probe (measurement / partial)</span>
                <span class="segment-label">Drive / Feedback</span>
              </div>
            </div>
            <div>
              <strong>Interpretation snapshot</strong>
              <div class="scene-notes" id="sceneInterpretation">
                No experiment has been run in this session yet. When you run a SynQc preset,
                this panel will summarize what was learned about coherence, latency, or backend
                behavior in plain language, derived from the raw KPIs.
              </div>
            </div>
          </div>
        </div>
      </section>

      <section class="panel panel-history">
        <div class="panel-header">
          <div>
            <div class="panel-title">Experiment Runs</div>
            <div class="panel-sub">Recent SynQc temporal dynamics bundles</div>
          </div>
        </div>
        <div class="history-filters" id="historyFiltersConsole">
          <div class="filter-pill active" data-filter="all">All</div>
          <div class="filter-pill" data-filter="health">Health</div>
          <div class="filter-pill" data-filter="latency">Latency</div>
          <div class="filter-pill" data-filter="compare">Compare</div>
          <div class="filter-pill" data-filter="dpd">DPD demo</div>
        </div>
        <div class="history-table-wrap">
          <table>
            <thead>
              <tr>
                <th>Time</th>
                <th>Preset</th>
                <th>Hardware</th>
                <th>Fidelity</th>
                <th>Latency</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody id="historyBody">
              <tr>
                <td>14:02:11</td>
                <td>Health (T1/T2/RB)</td>
                <td>Sim local</td>
                <td>0.973</td>
                <td>17.9 µs</td>
                <td><span class="status-pill status-ok">OK</span></td>
              </tr>
              <tr>
                <td>13:38:42</td>
                <td>Latency probe</td>
                <td>Sim local</td>
                <td>–</td>
                <td>15.1 µs</td>
                <td><span class="status-pill status-ok">OK</span></td>
              </tr>
              <tr>
                <td>12:27:05</td>
                <td>Backend compare</td>
                <td>Sim vs IBM (concept)</td>
                <td>0.962 / 0.948</td>
                <td>18.4 / 26.7 µs</td>
                <td><span class="status-pill status-warn">Δ drift</span></td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="history-footer-note">
          In a live deployment, each row links to full analysis, raw pulse/circuit definitions,
          and provider logs. This HTML file is a UI shell; the SynQc backend is responsible for
          running real experiments and storing data.
        </div>
      </section>
        </div>
      </div>

      <div class="view" id="view-experiments">
        <div class="page-wrap">
          <section class="panel">
            <div class="panel-header">
              <div>
                <div class="panel-title">Experiments</div>
                <div class="panel-sub">Backed by <code>GET /experiments/recent</code> · Click a row to open <strong>Details</strong></div>
              </div>
              <button class="small-btn" id="refreshExperimentsBtn" type="button">Reload</button>
            </div>

            <div class="history-filters" id="historyFiltersExperiments">
              <div class="filter-pill active" data-filter="all">All</div>
              <div class="filter-pill" data-filter="health">Health</div>
              <div class="filter-pill" data-filter="latency">Latency</div>
              <div class="filter-pill" data-filter="compare">Compare</div>
              <div class="filter-pill" data-filter="dpd">DPD demo</div>
            </div>

            <div class="history-table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Time</th>
                    <th>ID</th>
                    <th>Preset</th>
                    <th>Hardware</th>
                    <th>Fidelity</th>
                    <th>Latency</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody id="experimentsBody">
                  <tr><td colspan="7" class="hint">No data loaded yet. Start the backend and click Reload.</td></tr>
                </tbody>
              </table>
            </div>

            <div class="history-footer-note" id="experimentsFooterNote">
              This view is intentionally read-only: the current backend exposes run + list + fetch endpoints, but no delete/edit endpoints.
            </div>
          </section>
        </div>
      </div>

      <div class="view" id="view-hardware">
        <div class="page-wrap">
          <section class="panel">
            <div class="panel-header">
              <div>
                <div class="panel-title">Hardware targets</div>
                <div class="panel-sub">Backed by <code>GET /hardware/targets</code></div>
              </div>
              <button class="small-btn" id="refreshHardwareBtn" type="button">Reload</button>
            </div>

            <div class="panel-sub" id="hardwareMeta">Backend capability loads from <code>/health</code>.</div>
            <div class="hardware-list" id="hardwareList" role="list"></div>

            <div class="history-footer-note">
              The frontend Setup dropdown is populated from this same endpoint to ensure the controls match backend capability.
            </div>
          </section>
        </div>
      </div>

      <div class="view" id="view-details">
        <div class="page-wrap">
          <section class="panel">
            <div class="panel-header">
              <div>
                <div class="panel-title">Experiment details</div>
                <div class="panel-sub">Backed by <code>GET /experiments/{id}</code> · This is the closest thing to “Logs” supported by the current API.</div>
              </div>
              <div class="detail-actions">
                <button class="small-btn" id="detailsBackBtn" type="button">Back</button>
                <button class="small-btn" id="detailsReloadBtn" type="button">Reload</button>
              </div>
            </div>

            <div class="panel-sub" id="detailsHeader">No experiment selected yet. Go to Experiments and click a row.</div>

            <div class="scene-kpis" style="margin-top:0.55rem;"> 
              <div class="kpi-card">
                <div class="kpi-label">Fidelity</div>
                <div class="kpi-value" id="detailsKpiFidelity">—</div>
              </div>
              <div class="kpi-card">
                <div class="kpi-label">Latency</div>
                <div class="kpi-value" id="detailsKpiLatency">—</div>
              </div>
              <div class="kpi-card">
                <div class="kpi-label">Backaction</div>
                <div class="kpi-value" id="detailsKpiBackaction">—</div>
              </div>
              <div class="kpi-card">
                <div class="kpi-label">Shots used</div>
                <div class="kpi-value" id="detailsKpiShots">—</div>
              </div>
              <div class="kpi-card">
                <div class="kpi-label">Status</div>
                <div class="kpi-value" id="detailsKpiStatus">—</div>
              </div>
            </div>

            <div class="scene-notes" id="detailsInterpretation" style="margin-top:0.6rem;">Select a run to see a plain-language summary here.</div>

            <div class="panel-sub" style="margin-top:0.7rem;">Raw record</div>
            <pre class="json-block" id="detailsJson">{}</pre>
          </section>
        </div>
      </div>
    </main>

    <footer>
      SynQc TDS is the front-end console for SynQc Temporal Dynamics Series — bridging Drive–Probe–Drive
      theory, mid-circuit measurement, and real hardware backends into a single, guided control experience.
      This file is a conceptual frontend package and requires a backend API to execute real experiments.
    </footer>
  </div>

  <script>
    // --------------------------------------------
    // Visual particles
    // --------------------------------------------
    (function initParticles() {
      const layer = document.getElementById('particleLayer');
      const count = 30;
      for (let i = 0; i < count; i++) {
        const p = document.createElement('div');
        p.className = 'particle';
        const x = Math.random() * 100;
        const y = 20 + Math.random() * 80;
        const delay = Math.random() * 18;
        const scale = 0.8 + Math.random() * 0.7;
        p.style.left = x + 'vw';
        p.style.top = y + 'vh';
        p.style.animationDelay = (-delay) + 's';
        p.style.transform = 'scale(' + scale.toFixed(2) + ')';
        layer.appendChild(p);
      }
    })();

    // --------------------------------------------
    // Mode pills
    // --------------------------------------------
    document.querySelectorAll('.mode-pill').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.mode-pill').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
      });
    });

    // --------------------------------------------
    // Primary nav -> view switching (v0.4)
    // --------------------------------------------
    const navButtons = Array.from(document.querySelectorAll('.nav-links button[data-view]'));
    const views = {
      console: document.getElementById('view-console'),
      experiments: document.getElementById('view-experiments'),
      hardware: document.getElementById('view-hardware'),
      details: document.getElementById('view-details'),
    };

    let lastNonDetailsView = 'console';

    function setActiveView(viewName, { pushHash = true } = {}) {
      if (!views[viewName]) viewName = 'console';

      navButtons.forEach(b => b.classList.toggle('active', b.dataset.view === viewName));
      Object.entries(views).forEach(([k, el]) => {
        if (!el) return;
        el.classList.toggle('active', k === viewName);
      });

      if (viewName !== 'details') lastNonDetailsView = viewName;

      if (pushHash) {
        try { window.location.hash = viewName; } catch (_) { /* ignore */ }
      }

      // Best-effort refresh when opening data-backed views
      if (viewName === 'experiments') refreshExperimentsView();
      if (viewName === 'hardware') refreshHardwareView();
      if (viewName === 'details') refreshDetailsView();
    }

    navButtons.forEach(btn => {
      btn.addEventListener('click', () => setActiveView(btn.dataset.view || 'console'));
    });

    // Initialize from hash
    (function initViewFromHash(){
      const hv = (window.location.hash || '').replace('#','').trim();
      if (hv && views[hv]) setActiveView(hv, { pushHash: false });
    })();

    // --------------------------------------------
    // Agent tabs (Agent / Setup)
    // --------------------------------------------
    const agentTabs = document.querySelectorAll('.agent-tabs button');
    const chatPanel = document.getElementById('agentChatLog');
    const setupPanel = document.getElementById('agentSetupPanel');

    agentTabs.forEach(btn => {
      btn.addEventListener('click', () => {
        agentTabs.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        const tab = btn.getAttribute('data-tab');
        if (tab === 'chat') {
          chatPanel.style.display = 'flex';
          setupPanel.style.display = 'none';
        } else {
          chatPanel.style.display = 'flex';
          setupPanel.style.display = 'flex';
        }
      });
    });

    // --------------------------------------------
    // DOM references
    // --------------------------------------------
    const agentInput = document.getElementById('agentInput');
    const agentSend = document.getElementById('agentSend');

    const scenePresetLabel = document.getElementById('scenePresetLabel');
    const sceneHardwareLabel = document.getElementById('sceneHardwareLabel');
    const hardwareSelect = document.getElementById('hardwareSelect');
    const presetSelect = document.getElementById('presetSelect');
    const sceneInterpretation = document.getElementById('sceneInterpretation');

    const shotInput = document.getElementById('shotInput');
    const shotLabel = document.getElementById('shotLabel');
    const notesInput = document.getElementById('notesInput');
    const runPresetBtn = document.getElementById('runPresetBtn');
    const runStatus = document.getElementById('runStatus');

    // Console history
    const historyBody = document.getElementById('historyBody');
    const historyFiltersConsole = document.getElementById('historyFiltersConsole');

    // Experiments page
    const experimentsBody = document.getElementById('experimentsBody');
    const historyFiltersExperiments = document.getElementById('historyFiltersExperiments');
    const refreshExperimentsBtn = document.getElementById('refreshExperimentsBtn');

    // Hardware page
    const hardwareMeta = document.getElementById('hardwareMeta');
    const hardwareList = document.getElementById('hardwareList');
    const refreshHardwareBtn = document.getElementById('refreshHardwareBtn');

    // Details page
    const detailsBackBtn = document.getElementById('detailsBackBtn');
    const detailsReloadBtn = document.getElementById('detailsReloadBtn');
    const detailsHeader = document.getElementById('detailsHeader');
    const detailsJson = document.getElementById('detailsJson');
    const detailsInterpretation = document.getElementById('detailsInterpretation');

    const detailsKpiFidelity = document.getElementById('detailsKpiFidelity');
    const detailsKpiLatency = document.getElementById('detailsKpiLatency');
    const detailsKpiBackaction = document.getElementById('detailsKpiBackaction');
    const detailsKpiShots = document.getElementById('detailsKpiShots');
    const detailsKpiStatus = document.getElementById('detailsKpiStatus');

    // --------------------------------------------
    // Backend wiring
    // --------------------------------------------
    function defaultApiBase() {
      const params = new URLSearchParams(window.location.search);
      const override = params.get('api');
      if (override) return override.replace(/\/$/, "");

      // If opened as a local file, assume the backend is running on localhost:8001.
      if (window.location.protocol === 'file:') return 'http://localhost:8001';

      // If served via a dev server (e.g., Live Server / http.server), assume backend on the same host:8001.
      return `${window.location.protocol}//${window.location.hostname}:8001`;
    }

    const API_BASE = defaultApiBase();

    let MAX_SHOTS_PER_EXPERIMENT = 200000;
    let DEFAULT_SHOT_BUDGET = 2048;

    let lastRun = null;
    let recentRunsCache = [];
    let hardwareTargetsCache = [];
    let healthCache = null;

    let selectedExperimentId = null;

    function setRunStatus(text) {
      runStatus.textContent = text;
    }

    async function apiGet(path) {
      const res = await fetch(API_BASE + path, { method: 'GET' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return await res.json();
    }

    async function apiPost(path, payload) {
      const res = await fetch(API_BASE + path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        let detail = '';
        try {
          const data = await res.json();
          detail = data?.detail ? ` — ${data.detail}` : '';
        } catch (_) { /* ignore */ }
        throw new Error(`HTTP ${res.status}${detail}`);
      }
      return await res.json();
    }

    function fmtTimeFromEpochSeconds(epochSec) {
      const d = new Date(epochSec * 1000);
      return d.toLocaleTimeString([], { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
    }

    function presetLabel(preset) {
      if (preset === 'health') return 'Health (T1/T2/RB)';
      if (preset === 'latency') return 'Latency probe';
      if (preset === 'backend_compare') return 'Backend compare';
      if (preset === 'dpd_demo') return 'DPD demo';
      return preset;
    }

    function statusLabel(status) {
      if (status === 'ok') return 'OK';
      if (status === 'warn') return 'WARN';
      if (status === 'fail') return 'FAIL';
      return String(status || '').toUpperCase() || 'OK';
    }

    function statusClass(status) {
      if (status === 'fail') return 'status-fail';
      if (status === 'warn') return 'status-warn';
      return 'status-ok';
    }

    function setKpiClass(el, status) {
      el.classList.remove('kpi-good', 'kpi-warn', 'kpi-bad');
      if (status === 'fail') el.classList.add('kpi-bad');
      else if (status === 'warn') el.classList.add('kpi-warn');
      else el.classList.add('kpi-good');
    }

    function clamp01(x) {
      if (!Number.isFinite(x)) return 0;
      return Math.max(0, Math.min(1, x));
    }

    function hardwareNameForId(id) {
      // Prefer cache from /hardware/targets
      const found = (hardwareTargetsCache || []).find(t => t.id === id);
      if (found && found.name) return found.name;

      // Fall back to current select option
      const opt = Array.from(hardwareSelect.options || []).find(o => o.value === id);
      return opt ? opt.textContent : id;
    }

    // --------------------------------------------
    // Visual KPI mapping (console scene)
    // --------------------------------------------
    function applyRunToVisuals(run) {
      const kpis = run?.kpis || {};
      const fidelity = (kpis.fidelity == null) ? null : Number(kpis.fidelity);
      const latency = (kpis.latency_us == null) ? null : Number(kpis.latency_us);
      const backaction = (kpis.backaction == null) ? null : Number(kpis.backaction);

      const atm = document.getElementById('blochAtmosphere');
      const noise = document.getElementById('blochNoise');
      const state = document.getElementById('blochState');
      const ringA = document.getElementById('blochRingA');
      const ringB = document.getElementById('blochRingB');
      const ringC = document.getElementById('blochRingC');
      const trace = document.getElementById('blochTrace');
      const orbitDot = document.getElementById('blochOrbitDot');
      const spark = document.getElementById('timelineSpark');

      if (atm) {
        const alpha = (fidelity == null || !Number.isFinite(fidelity))
          ? 0.38
          : (0.18 + clamp01(fidelity) * 0.55);
        atm.style.opacity = String(alpha.toFixed(3));
      }

      if (noise) {
        const n = (backaction == null || !Number.isFinite(backaction)) ? 0.18 : Math.max(0, Math.min(backaction, 0.6));
        noise.style.opacity = String((0.02 + (n / 0.6) * 0.18).toFixed(3));
      }

      const lat = (latency == null || !Number.isFinite(latency)) ? 60 : Math.max(5, Math.min(latency, 800));
      const spin = 12 + (lat / 800) * 22;          // 12–34s
      const dash = 2.6 + (lat / 800) * 2.2;        // 2.6–4.8s
      const sparkSpeed = 3.2 + (lat / 800) * 2.0;  // 3.2–5.2s

      const back = (backaction == null || !Number.isFinite(backaction)) ? 0.22 : Math.max(0, Math.min(backaction, 0.6));
      const orbit = 9 - (back / 0.6) * 3.5;        // 5.5–9.0s

      if (ringA) ringA.style.animationDuration = `${spin.toFixed(1)}s`;
      if (ringB) ringB.style.animationDuration = `${(spin * 1.3).toFixed(1)}s`;
      if (ringC) ringC.style.animationDuration = `${(spin * 1.9).toFixed(1)}s`;
      if (trace) trace.style.animationDuration = `${(spin * 1.4).toFixed(1)}s`;
      if (spark) spark.style.animationDuration = `${sparkSpeed.toFixed(1)}s`;
      if (state) state.style.animationDuration = `${orbit.toFixed(1)}s`;
      if (orbitDot) orbitDot.style.animationDuration = `${(spin * 0.55).toFixed(1)}s`;

      const paths = trace?.querySelectorAll?.('path') || [];
      paths.forEach((p, idx) => {
        const d = (idx === 0) ? dash : (dash * 1.2);
        p.style.animationDuration = `${d.toFixed(2)}s`;
      });
    }

    // --------------------------------------------
    // KPI rendering
    // --------------------------------------------
    function applyRunToKpis(run, ids) {
      const kpis = run?.kpis || {};
      const status = kpis.status || 'ok';

      const elFid = document.getElementById(ids.fidelity);
      const elLat = document.getElementById(ids.latency);
      const elBack = document.getElementById(ids.backaction);
      const elShots = document.getElementById(ids.shots);
      const elStatus = ids.status ? document.getElementById(ids.status) : null;

      // Fidelity
      if (!elFid) return;
      if (kpis.fidelity == null) {
        elFid.textContent = '—';
        elFid.classList.remove('kpi-good', 'kpi-warn', 'kpi-bad');
      } else {
        elFid.textContent = Number(kpis.fidelity).toFixed(3);
        setKpiClass(elFid, status);
      }

      // Latency
      if (elLat) {
        elLat.textContent = (kpis.latency_us == null) ? '—' : `${Number(kpis.latency_us).toFixed(1)} µs`;
      }

      // Backaction
      if (elBack) {
        if (kpis.backaction == null) {
          elBack.textContent = '—';
          elBack.classList.remove('kpi-good', 'kpi-warn', 'kpi-bad');
        } else {
          elBack.textContent = Number(kpis.backaction).toFixed(2);
          const ba = Number(kpis.backaction);
          if (ba > 0.35) setKpiClass(elBack, 'fail');
          else if (ba > 0.25) setKpiClass(elBack, 'warn');
          else setKpiClass(elBack, 'ok');
        }
      }

      // Shots
      if (elShots) {
        const used = Number(kpis.shots_used || 0);
        const budget = Number(kpis.shot_budget || 0);
        elShots.textContent = `${used.toLocaleString()} / ${budget.toLocaleString()}`;
      }

      if (elStatus) {
        elStatus.textContent = statusLabel(status);
        elStatus.classList.remove('kpi-good', 'kpi-warn', 'kpi-bad');
        // For a status value, color it similarly
        if (status === 'fail') elStatus.classList.add('kpi-bad');
        else if (status === 'warn') elStatus.classList.add('kpi-warn');
        else elStatus.classList.add('kpi-good');
      }

      // Only the console has visuals, but it doesn't hurt to try.
      try { applyRunToVisuals(run); } catch (_) { /* non-fatal */ }
    }

    const CONSOLE_KPI_IDS = {
      fidelity: 'kpiFidelity',
      latency: 'kpiLatency',
      backaction: 'kpiBackaction',
      shots: 'kpiShots',
      status: null,
    };

    const DETAILS_KPI_IDS = {
      fidelity: 'detailsKpiFidelity',
      latency: 'detailsKpiLatency',
      backaction: 'detailsKpiBackaction',
      shots: 'detailsKpiShots',
      status: 'detailsKpiStatus',
    };

    // --------------------------------------------
    // Interpretation text
    // --------------------------------------------
    function deriveInterpretationFromRun(run) {
      const hwName = hardwareNameForId(run.hardware_target);
      const k = run.kpis || {};
      const status = k.status || 'ok';

      if (run.preset === 'health') {
        if (k.fidelity == null) {
          return `Health run completed on ${hwName}. Fidelity is not reported by this backend; inspect the record and provider logs.`;
        }
        const fid = Number(k.fidelity);
        const lat = (k.latency_us == null) ? null : Number(k.latency_us);
        const ba = (k.backaction == null) ? null : Number(k.backaction);

        const verdict =
          (status === 'fail') ? 'This looks unstable for production.' :
          (status === 'warn') ? 'This is borderline; watch drift and repeat a confirm run.' :
          'This looks stable inside normal bounds.';

        let extras = '';
        if (lat != null) extras += ` Latency was ~${lat.toFixed(1)} µs.`;
        if (ba != null) extras += ` Backaction was ${ba.toFixed(2)} (lower is better).`;

        return `Health diagnostics completed on ${hwName}. Estimated fidelity: ${fid.toFixed(3)}. ${verdict}${extras}`;
      }

      if (run.preset === 'latency') {
        const lat = (k.latency_us == null) ? null : Number(k.latency_us);
        if (lat == null) return `Latency characterization completed on ${hwName}. Latency was not reported; inspect the record.`;
        const note = lat > 50 ? 'This is fairly slow; consider tighter scheduling / batching.' :
                     lat > 25 ? 'Moderate delay; keep an eye on drift and queueing.' :
                     'Fast path looks healthy.';
        return `Latency characterization completed on ${hwName}. End-to-end latency: ~${lat.toFixed(1)} µs. ${note}`;
      }

      if (run.preset === 'backend_compare') {
        return `Backend comparison run completed on ${hwName}. This API version returns a single KPI bundle; multi-backend A/B is a planned extension.`;
      }

      if (run.preset === 'dpd_demo') {
        return `DPD demo completed on ${hwName}. Use this run to validate the Drive–Probe–Drive timing story, then graduate to health/latency presets.`;
      }

      return `Experiment completed on ${hwName}.`;
    }

    function updateInterpretationText() {
      const preset = presetSelect.value;
      const hwName = hardwareSelect.options[hardwareSelect.selectedIndex]?.text || hardwareSelect.value;

      if (lastRun && lastRun.preset === preset && lastRun.hardware_target === hardwareSelect.value) {
        sceneInterpretation.textContent = deriveInterpretationFromRun(lastRun);
        return;
      }

      if (preset === 'health') {
        sceneInterpretation.textContent =
          'A Qubit Health Diagnostics bundle will estimate T1 and T2-like coherence times, ' +
          'and optionally gate error, on ' + hwName + '. The console will summarize whether this backend ' +
          'is within your historical stability band.';
      } else if (preset === 'latency') {
        sceneInterpretation.textContent =
          'Latency Characterization will run short DPD probes to measure control-to-readout delay on ' +
          hwName + ', helping you understand timing overhead and drift.';
      } else if (preset === 'backend_compare') {
        sceneInterpretation.textContent =
          'Backend A/B Comparison will replay a reference experiment on two backends and report ' +
          'relative fidelity, coherence, and latency, so you can choose which is better for your workload.';
      } else if (preset === 'dpd_demo') {
        sceneInterpretation.textContent =
          'Guided SynQc DPD Example will show how a Drive–Probe–Drive sequence manipulates a single qubit ' +
          'over time, illustrating the link between SynQc theory and observable dynamics.';
      }
    }

    // --------------------------------------------
    // Table rendering + filtering
    // --------------------------------------------
    function clearTbody(tbody) {
      while (tbody.firstChild) tbody.removeChild(tbody.firstChild);
    }

    function applyFilterToBody(tbody, filter) {
      const rows = tbody.querySelectorAll('tr');
      rows.forEach(row => {
        const p = row.dataset.preset || '';
        const show =
          (filter === 'all') ||
          (filter === 'health' && p === 'health') ||
          (filter === 'latency' && p === 'latency') ||
          (filter === 'compare' && p === 'backend_compare') ||
          (filter === 'dpd' && p === 'dpd_demo');
        row.style.display = show ? '' : 'none';
      });
    }

    function createRunRow(run, { includeId = false } = {}) {
      const tr = document.createElement('tr');
      tr.dataset.preset = run.preset;
      tr.dataset.id = run.id;

      const tdTime = document.createElement('td');
      tdTime.textContent = fmtTimeFromEpochSeconds(run.created_at);

      const tdId = document.createElement('td');
      const shortId = (run.id || '').split('-')[0] || run.id;
      tdId.textContent = includeId ? shortId : '';

      const tdPreset = document.createElement('td');
      tdPreset.textContent = presetLabel(run.preset);

      const tdHw = document.createElement('td');
      tdHw.textContent = run.hardware_target;

      const tdFid = document.createElement('td');
      tdFid.textContent = (run.kpis?.fidelity == null) ? '–' : Number(run.kpis.fidelity).toFixed(3);

      const tdLat = document.createElement('td');
      tdLat.textContent = (run.kpis?.latency_us == null) ? '–' : `${Number(run.kpis.latency_us).toFixed(1)} µs`;

      const tdStatus = document.createElement('td');
      const pill = document.createElement('span');
      pill.className = `status-pill ${statusClass(run.kpis?.status)}`;
      pill.textContent = statusLabel(run.kpis?.status);
      tdStatus.appendChild(pill);

      tr.appendChild(tdTime);
      if (includeId) tr.appendChild(tdId);
      tr.appendChild(tdPreset);
      tr.appendChild(tdHw);
      tr.appendChild(tdFid);
      tr.appendChild(tdLat);
      tr.appendChild(tdStatus);

      tr.addEventListener('click', () => openDetails(run.id));
      return tr;
    }

    let consoleFilter = 'all';
    let experimentsFilter = 'all';

    function wireFilterPills(container, { onChange }) {
      if (!container) return;
      const pills = Array.from(container.querySelectorAll('.filter-pill'));
      pills.forEach(pill => {
        pill.addEventListener('click', () => {
          pills.forEach(x => x.classList.remove('active'));
          pill.classList.add('active');
          const f = pill.dataset.filter || 'all';
          onChange(f);
        });
      });
    }

    wireFilterPills(historyFiltersConsole, {
      onChange: (f) => {
        consoleFilter = f;
        applyFilterToBody(historyBody, consoleFilter);
      }
    });

    wireFilterPills(historyFiltersExperiments, {
      onChange: (f) => {
        experimentsFilter = f;
        applyFilterToBody(experimentsBody, experimentsFilter);
      }
    });

    // --------------------------------------------
    // Backend refresh + render
    // --------------------------------------------
    async function refreshFromBackend() {
      try {
        const h = await apiGet('/health');
        healthCache = h;

        if (h && typeof h.max_shots_per_experiment === 'number') {
          MAX_SHOTS_PER_EXPERIMENT = h.max_shots_per_experiment;
          shotInput.max = String(MAX_SHOTS_PER_EXPERIMENT);
          if (shotLabel && Number.isFinite(MAX_SHOTS_PER_EXPERIMENT)) {
            shotLabel.textContent = `Shot budget (max ${MAX_SHOTS_PER_EXPERIMENT.toLocaleString()})`;
          }
        }

        if (h && typeof h.default_shot_budget === 'number') {
          DEFAULT_SHOT_BUDGET = h.default_shot_budget;
          const existing = Number.parseInt(String(shotInput?.value || ''), 10);
          if (!Number.isFinite(existing) || existing <= 0) shotInput.value = String(DEFAULT_SHOT_BUDGET);
        }

        setRunStatus(`Backend: connected (${API_BASE}) · env=${h.env ?? 'unknown'}`);

        // Targets
        try {
          const targets = await apiGet('/hardware/targets');
          const list = Array.isArray(targets?.targets) ? targets.targets : [];
          hardwareTargetsCache = list;

          // Update setup dropdown
          const current = hardwareSelect.value;
          while (hardwareSelect.firstChild) hardwareSelect.removeChild(hardwareSelect.firstChild);
          list.forEach(t => {
            const opt = document.createElement('option');
            opt.value = t.id;
            opt.textContent = t.name;
            hardwareSelect.appendChild(opt);
          });
          if (Array.from(hardwareSelect.options).some(o => o.value === current)) {
            hardwareSelect.value = current;
          }
          hardwareSelect.dispatchEvent(new Event('change'));

          // Update hardware page
          renderHardwareList();
        } catch (_) { /* best effort */ }

        // Runs
        try {
          const recents = await apiGet('/experiments/recent?limit=50');
          recentRunsCache = Array.isArray(recents) ? recents : [];

          // Console history
          clearTbody(historyBody);
          if (recentRunsCache.length === 0) {
            const tr = document.createElement('tr');
            const td = document.createElement('td');
            td.colSpan = 6;
            td.textContent = 'No runs yet.';
            td.className = 'hint';
            tr.appendChild(td);
            historyBody.appendChild(tr);
          } else {
            recentRunsCache.forEach(r => historyBody.appendChild(createRunRow(r, { includeId: false })));
          }
          applyFilterToBody(historyBody, consoleFilter);

          // Experiments page table
          renderExperimentsTable();
        } catch (_) { /* ignore */ }

      } catch (err) {
        setRunStatus(`Backend: not reachable (${API_BASE}). Start it and refresh.`);
      }
    }

    function renderExperimentsTable() {
      clearTbody(experimentsBody);
      if (!recentRunsCache || recentRunsCache.length === 0) {
        const tr = document.createElement('tr');
        const td = document.createElement('td');
        td.colSpan = 7;
        td.textContent = 'No runs loaded.';
        td.className = 'hint';
        tr.appendChild(td);
        experimentsBody.appendChild(tr);
      } else {
        recentRunsCache.forEach(r => experimentsBody.appendChild(createRunRow(r, { includeId: true })));
      }
      applyFilterToBody(experimentsBody, experimentsFilter);
    }

    function renderHardwareList() {
      if (!hardwareList) return;
      while (hardwareList.firstChild) hardwareList.removeChild(hardwareList.firstChild);

      const allowRemote = healthCache?.allow_remote_hardware;
      const maxShots = healthCache?.max_shots_per_experiment;

      if (hardwareMeta) {
        const parts = [];
        parts.push(`Backend: ${API_BASE}`);
        if (typeof allowRemote === 'boolean') parts.push(`allow_remote_hardware=${allowRemote}`);
        if (typeof maxShots === 'number') parts.push(`max_shots_per_experiment=${maxShots.toLocaleString()}`);
        hardwareMeta.textContent = parts.join(' · ');
      }

      const list = hardwareTargetsCache || [];
      if (!list.length) {
        const empty = document.createElement('div');
        empty.className = 'hint';
        empty.textContent = 'No targets loaded.';
        hardwareList.appendChild(empty);
        return;
      }

      list.forEach(t => {
        const item = document.createElement('div');
        item.className = 'hardware-item';
        item.setAttribute('role', 'listitem');

        const top = document.createElement('div');
        top.className = 'hardware-top';

        const name = document.createElement('div');
        name.className = 'hardware-name';
        name.textContent = t.name;

        const badge = document.createElement('div');
        badge.className = 'hardware-badge';
        badge.textContent = t.kind;

        top.appendChild(name);
        top.appendChild(badge);

        const meta1 = document.createElement('div');
        meta1.className = 'hardware-meta';
        meta1.textContent = `id: ${t.id}`;

        const meta2 = document.createElement('div');
        meta2.className = 'hardware-meta';
        meta2.textContent = t.description || '';

        item.appendChild(top);
        item.appendChild(meta1);
        item.appendChild(meta2);

        hardwareList.appendChild(item);
      });
    }

    async function runSelectedPreset() {
      const preset = presetSelect.value;
      const hardware_target = hardwareSelect.value;

      let shot_budget = Number.parseInt(String(shotInput.value || ''), 10);
      if (!Number.isFinite(shot_budget) || shot_budget <= 0) shot_budget = DEFAULT_SHOT_BUDGET;
      shot_budget = Math.min(Math.max(shot_budget, 1), MAX_SHOTS_PER_EXPERIMENT);

      const notes = (notesInput?.value || '').trim() || null;

      runPresetBtn.disabled = true;
      setRunStatus('Running preset…');

      try {
        const run = await apiPost('/experiments/run', { preset, hardware_target, shot_budget, notes });
        lastRun = run;

        // Update labels
        scenePresetLabel.textContent = presetLabel(preset).replace(' (T1/T2/RB)', '');
        sceneHardwareLabel.textContent = hardwareNameForId(hardware_target);

        applyRunToKpis(run, CONSOLE_KPI_IDS);
        sceneInterpretation.textContent = deriveInterpretationFromRun(run);

        // Refresh lists
        await refreshFromBackend();

        setRunStatus(`Run complete · id=${run.id}`);
      } catch (err) {
        setRunStatus(`Run failed: ${err.message}`);
      } finally {
        runPresetBtn.disabled = false;
      }
    }

    runPresetBtn.addEventListener('click', runSelectedPreset);

    // --------------------------------------------
    // Details view: load experiment record
    // --------------------------------------------
    async function openDetails(experimentId) {
      selectedExperimentId = experimentId;
      setActiveView('details');
      await refreshDetailsView();
    }

    async function refreshDetailsView() {
      if (!selectedExperimentId) {
        detailsHeader.textContent = 'No experiment selected yet. Go to Experiments and click a row.';
        detailsInterpretation.textContent = 'Select a run to see a plain-language summary here.';
        detailsJson.textContent = '{}';
        applyRunToKpis({ kpis: {} }, DETAILS_KPI_IDS);
        return;
      }

      try {
        const run = await apiGet(`/experiments/${selectedExperimentId}`);

        detailsHeader.textContent = `id=${run.id} · preset=${run.preset} · hardware=${hardwareNameForId(run.hardware_target)}`;
        detailsInterpretation.textContent = deriveInterpretationFromRun(run);
        detailsJson.textContent = JSON.stringify(run, null, 2);
        applyRunToKpis(run, DETAILS_KPI_IDS);
      } catch (err) {
        detailsHeader.textContent = `Could not load id=${selectedExperimentId}`;
        detailsInterpretation.textContent = `Error: ${err.message}`;
        detailsJson.textContent = '{}';
      }
    }

    detailsBackBtn.addEventListener('click', () => setActiveView(lastNonDetailsView));
    detailsReloadBtn.addEventListener('click', () => refreshDetailsView());

    // --------------------------------------------
    // Experiments / Hardware page controls
    // --------------------------------------------
    refreshExperimentsBtn.addEventListener('click', async () => {
      await refreshFromBackend();
      renderExperimentsTable();
    });

    refreshHardwareBtn.addEventListener('click', async () => {
      await refreshFromBackend();
      renderHardwareList();
    });

    function refreshExperimentsView(){
      // If we already have cache, render immediately; otherwise fetch.
      if (recentRunsCache && recentRunsCache.length) {
        renderExperimentsTable();
      } else {
        refreshFromBackend();
      }
    }

    function refreshHardwareView(){
      if (hardwareTargetsCache && hardwareTargetsCache.length) {
        renderHardwareList();
      } else {
        refreshFromBackend();
      }
    }

    // --------------------------------------------
    // Chat: safe rendering (no innerHTML)
    // --------------------------------------------
    function appendMessage(text, who) {
      const div = document.createElement('div');
      div.className = 'msg ' + (who === 'user' ? 'msg-user' : 'msg-agent');

      const label = document.createElement('strong');
      label.textContent = (who === 'user' ? 'You:' : 'SynQc Guide:');

      div.appendChild(label);
      div.appendChild(document.createTextNode(' '));
      div.appendChild(document.createTextNode(String(text)));

      chatPanel.appendChild(div);
      chatPanel.scrollTop = chatPanel.scrollHeight;
    }

    function interpretIntent(msg) {
      const lower = msg.toLowerCase();
      if (lower.includes('health') || lower.includes('stable') || lower.includes('coherence')) {
        presetSelect.value = 'health';
        scenePresetLabel.textContent = 'Qubit Health Diagnostics';
        return 'I will configure the Qubit Health Diagnostics suite (T1/T2*/echo, optional RB) ' +
               'for your selected backend. You can refine shot budget or backend in the Setup tab.';
      }
      if (lower.includes('latency')) {
        presetSelect.value = 'latency';
        scenePresetLabel.textContent = 'Latency Characterization';
        return 'I will prepare a Latency Characterization bundle with low-shot DPD probes to measure ' +
               'end-to-end and backend-only delay.';
      }
      if (lower.includes('compare') || lower.includes('backend')) {
        presetSelect.value = 'backend_compare';
        scenePresetLabel.textContent = 'Backend A/B Comparison';
        return 'I will set up a backend comparison run: your reference experiment will be replayed on two ' +
               'backends so we can compare fidelity and latency directly.';
      }
      if (lower.includes('example') || lower.includes('demo')) {
        presetSelect.value = 'dpd_demo';
        scenePresetLabel.textContent = 'Guided SynQc DPD Example';
        return 'I will walk you through a guided SynQc Drive–Probe–Drive example on a local simulator, ' +
               'explaining each step as we go.';
      }
      return 'I have recorded your goal. Use the Setup tab to pick the closest preset (Health, Latency, ' +
             'Backend Compare, or DPD Demo) and I will adapt it to your backend and constraints.';
    }

    agentSend.addEventListener('click', () => {
      const text = agentInput.value.trim();
      if (!text) return;
      appendMessage(text, 'user');
      agentInput.value = '';
      const reply = interpretIntent(text);
      appendMessage(reply, 'agent');
      updateInterpretationText();
    });

    agentInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') agentSend.click();
    });

    hardwareSelect.addEventListener('change', () => {
      sceneHardwareLabel.textContent = hardwareSelect.options[hardwareSelect.selectedIndex]?.text || hardwareSelect.value;
      updateInterpretationText();
    });

    presetSelect.addEventListener('change', () => {
      const val = presetSelect.value;
      scenePresetLabel.textContent = presetLabel(val);
      updateInterpretationText();
    });

    // --------------------------------------------
    // Boot
    // --------------------------------------------
    refreshFromBackend();
    updateInterpretationText();
  </script>
</body>
</html>
```

## backend/pyproject.toml

```toml
[project]
name = "synqc-tds-backend"
version = "0.1.0"
description = "Backend API and engine for SynQc Temporal Dynamics Series (SynQc TDS) console."
requires-python = ">=3.12"
authors = [{name = "Adam & Nova (eVision)"}]

dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.30.0",
    "pydantic>=2.9.0",
    "numpy>=2.0.0"
]

[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[tool.synqc]
# Custom section to remind future us about safety and design choices.
max_shots_per_experiment = 200000
max_shots_per_session = 1000000
```

## backend/synqc_backend/api.py

```py
from __future__ import annotations

from pathlib import Path
from typing import List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .engine import SynQcEngine
from .hardware_backends import list_backends
from .models import (
    ExperimentPreset,
    ExperimentStatus,
    HardwareTarget,
    HardwareTargetsResponse,
    RunExperimentRequest,
    RunExperimentResponse,
    ExperimentSummary,
)
from .storage import ExperimentStore


# Instantiate storage and engine
persist_path = Path("./synqc_experiments.json")
store = ExperimentStore(max_entries=512, persist_path=persist_path)
engine = SynQcEngine(store=store)

app = FastAPI(
    title="SynQc Temporal Dynamics Series Backend",
    description=(
        "Backend API for SynQc TDS console — exposes high-level experiment presets "
        "(health, latency, backend comparison, DPD demo) and returns KPIs.")
)

# CORS: allow localhost UIs and simple static frontends
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    # SECURITY: Do not combine allow_credentials=True with a wildcard origin.
    # For local dev, we keep origins open but disable credentials.
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["meta"])
def health() -> dict:
    """Simple health check endpoint."""
    return {
        "status": "ok",
        "env": settings.env,
        "max_shots_per_experiment": settings.max_shots_per_experiment,
        "max_shots_per_session": settings.max_shots_per_session,
        "default_shot_budget": settings.default_shot_budget,
        "allow_remote_hardware": settings.allow_remote_hardware,
        "presets": [p.value for p in ExperimentPreset],
    }


@app.get("/hardware/targets", response_model=HardwareTargetsResponse, tags=["hardware"])
def get_hardware_targets() -> HardwareTargetsResponse:
    """List available hardware targets.

    In this v0.1 backend only a local simulator is implemented. Future versions can
    add QPU and lab backends in `hardware_backends.py`.
    """
    targets: List[HardwareTarget] = []
    for backend_id, backend in list_backends().items():
        if (not settings.allow_remote_hardware) and backend_id != "sim_local":
            continue
        targets.append(
            HardwareTarget(
                id=backend_id,
                name=backend.name,
                kind=backend.kind,
                description=(
                    "Local SynQc simulator" if backend.kind == "sim"
                    else "SynQc hardware backend (concept/simulated until provider integration)"
                ),
            )
        )
    return HardwareTargetsResponse(targets=targets)


@app.post("/experiments/run", response_model=RunExperimentResponse, tags=["experiments"])
def run_experiment(req: RunExperimentRequest) -> RunExperimentResponse:
    """Run a SynQc experiment preset and return KPIs and metadata."""
    try:
        return engine.run_experiment(req)
    except KeyError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/experiments/{experiment_id}", response_model=RunExperimentResponse, tags=["experiments"])
def get_experiment(experiment_id: str) -> RunExperimentResponse:
    """Return a specific experiment run by id."""
    run = store.get(experiment_id)
    if not run:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return run


@app.get("/experiments/recent", response_model=list[ExperimentSummary], tags=["experiments"])
def list_recent_experiments(limit: int = 50) -> list[ExperimentSummary]:
    """Return the most recent experiment summaries (bounded)."""
    if limit <= 0:
        raise HTTPException(status_code=400, detail="limit must be positive")
    return store.list_recent(limit=limit)
```

## backend/synqc_backend/models.py

```py
from __future__ import annotations

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class ExperimentPreset(str, Enum):
    """High-level experiment presets supported by the SynQc engine."""

    HEALTH = "health"
    LATENCY = "latency"
    BACKEND_COMPARE = "backend_compare"
    DPD_DEMO = "dpd_demo"


class ExperimentStatus(str, Enum):
    """Coarse-grained status for a completed experiment bundle."""

    OK = "ok"
    WARN = "warn"
    FAIL = "fail"


class KpiBundle(BaseModel):
    """Key performance indicators for a SynQc experiment run."""

    fidelity: Optional[float] = Field(
        default=None,
        description="Estimated state/process fidelity (0–1)."
    )
    latency_us: Optional[float] = Field(
        default=None,
        description="End-to-end latency in microseconds."
    )
    backaction: Optional[float] = Field(
        default=None,
        description="Scalar measure of probe-induced disturbance (0–1)."
    )
    shots_used: int = Field(
        default=0,
        description="Number of shots actually used by this run."
    )
    shot_budget: int = Field(
        default=0,
        description="Shot budget configured for this run."
    )
    status: ExperimentStatus = Field(
        default=ExperimentStatus.OK,
        description="Overall health/status classification for this run."
    )


class HardwareTarget(BaseModel):
    """Description of a hardware backend target."""

    id: str
    name: str
    kind: str  # e.g. "sim", "superconducting", "trapped_ion", "fpga_lab"
    description: str


class RunExperimentRequest(BaseModel):
    """API-facing request model for running a SynQc experiment preset."""

    preset: ExperimentPreset
    hardware_target: str = Field(
        description="Backend identifier, e.g. 'sim_local', 'ibm_qpu', 'ionq_qpu'."
    )
    shot_budget: Optional[int] = Field(
        default=None,
        description="Maximum number of shots to use; if omitted, defaults are applied."
    )
    notes: Optional[str] = Field(
        default=None,
        description="Optional free-form notes from the client."
    )


class RunExperimentResponse(BaseModel):
    """Response returned after an experiment run has been accepted and executed."""

    id: str
    preset: ExperimentPreset
    hardware_target: str
    kpis: KpiBundle
    created_at: float
    notes: Optional[str] = None


class ExperimentSummary(BaseModel):
    """Lightweight summary for listing experiment runs."""

    id: str
    preset: ExperimentPreset
    hardware_target: str
    kpis: KpiBundle
    created_at: float


class HardwareTargetsResponse(BaseModel):
    """List wrapper for hardware targets."""

    targets: List[HardwareTarget]
```

## backend/synqc_backend/engine.py

```py
from __future__ import annotations

import time
import uuid
from typing import Tuple

from .config import settings
from .hardware_backends import get_backend
from .models import (
    ExperimentPreset,
    ExperimentStatus,
    KpiBundle,
    RunExperimentRequest,
    RunExperimentResponse,
)
from .storage import ExperimentStore


class SynQcEngine:
    """Core engine for SynQc Temporal Dynamics Series backend.

    Responsibilities:
      - Apply configuration and guardrails (shot limits, basic policies).
      - Translate high-level presets into backend calls.
      - Aggregate KPIs and store experiment records.
    """

    def __init__(self, store: ExperimentStore) -> None:
        self._store = store
        self._session_shots_used = 0

    def _apply_shot_guardrails(self, req: RunExperimentRequest) -> Tuple[int, bool]:
        """Determine effective shot budget and whether to flag a warning.

        Returns:
            (effective_shot_budget, warn_for_target)
        """
        shot_budget = req.shot_budget or settings.default_shot_budget
        if shot_budget > settings.max_shots_per_experiment:
            shot_budget = settings.max_shots_per_experiment

        warn_for_target = False
        if req.hardware_target != "sim_local" and shot_budget > settings.default_shot_budget:
            warn_for_target = True

        if self._session_shots_used + shot_budget > settings.max_shots_per_session:
            # In a more advanced implementation, we might reject the request.
            # Here we clamp down to the remaining budget.
            remaining = max(settings.max_shots_per_session - self._session_shots_used, 0)
            shot_budget = max(remaining, 0)

        return shot_budget, warn_for_target

    def run_experiment(self, req: RunExperimentRequest) -> RunExperimentResponse:
        """Run a high-level SynQc experiment according to the request."""
        effective_shot_budget, warn_for_target = self._apply_shot_guardrails(req)

        backend = get_backend(req.hardware_target)
        start = time.time()
        kpis = backend.run_experiment(req.preset, effective_shot_budget)
        end = time.time()

        # Update session shot usage
        self._session_shots_used += kpis.shots_used

        # Fill missing KPI fields and tweak status if guardrails were hit
        if kpis.shot_budget == 0:
            kpis.shot_budget = effective_shot_budget

        # If we had to clamp or warn on target, bump status to WARN (if not already FAIL)
        if warn_for_target and kpis.status is not ExperimentStatus.FAIL:
            kpis.status = ExperimentStatus.WARN

        # If latency is missing, approximate with wall-clock delta
        if kpis.latency_us is None:
            kpis.latency_us = (end - start) * 1e6

        run_id = str(uuid.uuid4())
        run = RunExperimentResponse(
            id=run_id,
            preset=req.preset,
            hardware_target=req.hardware_target,
            kpis=kpis,
            created_at=end,
            notes=req.notes,
        )
        self._store.add(run)
        return run
```

## backend/synqc_backend/storage.py

```py
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Dict, List, Optional

from .models import RunExperimentResponse, ExperimentSummary


class ExperimentStore:
    """In-memory store for experiment runs, with optional JSON persistence.

    This is intentionally simple. It keeps a bounded number of recent experiments
    and can optionally persist them to a JSON file for inspection.
    """

    def __init__(self, max_entries: int = 512, persist_path: Optional[Path] = None) -> None:
        self._max_entries = max_entries
        self._persist_path = persist_path
        self._lock = threading.Lock()
        self._runs: Dict[str, RunExperimentResponse] = {}

        if self._persist_path and self._persist_path.exists():
            try:
                data = json.loads(self._persist_path.read_text())
                for entry in data:
                    run = RunExperimentResponse.model_validate(entry)
                    self._runs[run.id] = run
            except Exception:
                # If the file is corrupt or incompatible, we ignore it.
                pass

    def add(self, run: RunExperimentResponse) -> None:
        with self._lock:
            self._runs[run.id] = run
            if len(self._runs) > self._max_entries:
                # drop oldest
                oldest_id = sorted(self._runs.values(), key=lambda r: r.created_at)[0].id
                self._runs.pop(oldest_id, None)
            self._persist()

    def get(self, run_id: str) -> Optional[RunExperimentResponse]:
        with self._lock:
            return self._runs.get(run_id)

    def list_recent(self, limit: int = 50) -> List[ExperimentSummary]:
        with self._lock:
            runs_sorted = sorted(self._runs.values(), key=lambda r: r.created_at, reverse=True)
            return [
                ExperimentSummary(
                    id=r.id,
                    preset=r.preset,
                    hardware_target=r.hardware_target,
                    kpis=r.kpis,
                    created_at=r.created_at,
                )
                for r in runs_sorted[:limit]
            ]

    def _persist(self) -> None:
        if not self._persist_path:
            return
        try:
            data = [r.model_dump(mode="json") for r in self._runs.values()]
            self._persist_path.write_text(json.dumps(data, indent=2))
        except Exception:
            # Persistence failures should not kill the engine.
            pass
```

## backend/synqc_backend/config.py

```py
from __future__ import annotations

from pydantic import BaseModel
from typing import Literal


class SynQcSettings(BaseModel):
    """Configuration settings for the SynQc backend.

    In a more advanced deployment this could be subclassed from pydantic.BaseSettings
    to read environment variables. For now we keep it simple and explicit.
    """

    env: Literal["dev", "prod"] = "dev"

    # Shot-related guardrails
    max_shots_per_experiment: int = 200_000
    max_shots_per_session: int = 1_000_000

    # Default shot budget if caller doesn't specify
    default_shot_budget: int = 2_048

    # Whether we allow non-simulator targets in this deployment
    allow_remote_hardware: bool = True


settings = SynQcSettings()
```

## backend/synqc_backend/hardware_backends.py

```py
from __future__ import annotations

import random
import time
import zlib
from abc import ABC, abstractmethod
from typing import Dict

from .config import settings
from .models import ExperimentPreset, KpiBundle, ExperimentStatus


class BaseBackend(ABC):
    """Abstract base class for SynQc hardware backends.

    Concrete subclasses implement the logic to translate a high-level preset + shot
    budget into real hardware calls (or simulations) and return KPIs.
    """

    id: str
    name: str
    kind: str

    def __init__(self, id: str, name: str, kind: str) -> None:
        self.id = id
        self.name = name
        self.kind = kind

    @abstractmethod
    def run_experiment(self, preset: ExperimentPreset, shot_budget: int) -> KpiBundle:
        """Run the requested preset and return a KpiBundle.

        Implementations MUST obey the provided shot_budget (or lower),
        and they SHOULD NOT exceed engine-level limits. Those limits are
        enforced separately in the SynQcEngine, but backends need to be
        well-behaved as well.
        """


class LocalSimulatorBackend(BaseBackend):
    """Simple local simulator backend.

    This is intentionally lightweight and self-contained: it generates
    plausible KPI values without talking to real quantum hardware. The
    structure, not the physics, is the focus here.

    Future versions can replace the random draws with calls into a
    true SynQc simulator.
    """

    def __init__(self) -> None:
        super().__init__(id="sim_local", name="Local simulator", kind="sim" )

    def run_experiment(self, preset: ExperimentPreset, shot_budget: int) -> KpiBundle:
        # Clamp shots to something reasonable in this demo backend
        shots_used = min(shot_budget, settings.max_shots_per_experiment)

        # Seed randomness with time + preset to provide variety but some continuity
        base_seed = int(time.time()) ^ hash(preset.value)
        rng = random.Random(base_seed)

        if preset is ExperimentPreset.HEALTH:
            fidelity = 0.94 + rng.random() * 0.04  # 0.94–0.98
            latency = 15.0 + rng.random() * 6.0
            backaction = 0.15 + rng.random() * 0.1
        elif preset is ExperimentPreset.LATENCY:
            fidelity = None
            latency = 10.0 + rng.random() * 15.0
            backaction = 0.1 + rng.random() * 0.1
        elif preset is ExperimentPreset.BACKEND_COMPARE:
            fidelity = 0.93 + rng.random() * 0.05
            latency = 18.0 + rng.random() * 10.0
            backaction = 0.2 + rng.random() * 0.1
        else:  # DPD_DEMO or unknown
            fidelity = 0.9 + rng.random() * 0.08
            latency = 12.0 + rng.random() * 8.0
            backaction = 0.1 + rng.random() * 0.1

        status: ExperimentStatus
        if fidelity is not None and fidelity < 0.9:
            status = ExperimentStatus.FAIL
        elif fidelity is not None and fidelity < 0.94:
            status = ExperimentStatus.WARN
        else:
            status = ExperimentStatus.OK

        return KpiBundle(
            fidelity=fidelity,
            latency_us=latency,
            backaction=backaction,
            shots_used=shots_used,
            shot_budget=shot_budget,
            status=status,
        )




class ConceptSimBackend(BaseBackend):
    """Simulated placeholder backend for UI wiring.

    IMPORTANT:
      - This does NOT call real QPUs or lab hardware.
      - It exists so the frontend can stay functional and consistent while we
        integrate real provider SDKs in a controlled way.
    """

    def __init__(
        self,
        *,
        id: str,
        name: str,
        kind: str,
        fidelity_base: float | None,
        fidelity_span: float,
        latency_base_us: float,
        latency_span_us: float,
        backaction_base: float,
        backaction_span: float,
    ) -> None:
        super().__init__(id=id, name=name, kind=kind)
        self._fidelity_base = fidelity_base
        self._fidelity_span = fidelity_span
        self._latency_base_us = latency_base_us
        self._latency_span_us = latency_span_us
        self._backaction_base = backaction_base
        self._backaction_span = backaction_span

    def _rng(self, preset: ExperimentPreset) -> random.Random:
        # Use a stable-ish seed: time changes provide variety, zlib keeps deterministic mixing.
        salt = zlib.adler32(f"{self.id}:{preset.value}".encode("utf-8"))
        seed = int(time.time()) ^ salt
        return random.Random(seed)

    def run_experiment(self, preset: ExperimentPreset, shot_budget: int) -> KpiBundle:
        shots_used = min(shot_budget, settings.max_shots_per_experiment)
        rng = self._rng(preset)

        # Latency always exists for these demos.
        latency_us = self._latency_base_us + rng.random() * self._latency_span_us

        # Backaction always exists in this simplified KPI model.
        backaction = self._backaction_base + rng.random() * self._backaction_span

        fidelity = None
        if preset is not ExperimentPreset.LATENCY and self._fidelity_base is not None:
            fidelity = self._fidelity_base + rng.random() * self._fidelity_span
            fidelity = max(0.0, min(1.0, fidelity))

        status: ExperimentStatus
        if fidelity is not None and fidelity < 0.90:
            status = ExperimentStatus.FAIL
        elif fidelity is not None and fidelity < 0.94:
            status = ExperimentStatus.WARN
        elif backaction > 0.35:
            status = ExperimentStatus.WARN
        else:
            status = ExperimentStatus.OK

        return KpiBundle(
            fidelity=fidelity,
            latency_us=latency_us,
            backaction=backaction,
            shots_used=shots_used,
            shot_budget=shot_budget,
            status=status,
        )

# Registry of backends
_BACKENDS: Dict[str, BaseBackend] = {
    "sim_local": LocalSimulatorBackend(),

    # Concept placeholders (simulated):
    "ibm_qpu": ConceptSimBackend(
        id="ibm_qpu",
        name="IBM QPU (concept)",
        kind="superconducting",
        fidelity_base=0.92,
        fidelity_span=0.05,
        latency_base_us=28.0,
        latency_span_us=45.0,
        backaction_base=0.18,
        backaction_span=0.20,
    ),
    "ionq_qpu": ConceptSimBackend(
        id="ionq_qpu",
        name="IonQ QPU (concept)",
        kind="trapped_ion",
        fidelity_base=0.93,
        fidelity_span=0.06,
        latency_base_us=120.0,
        latency_span_us=260.0,
        backaction_base=0.10,
        backaction_span=0.18,
    ),
    "lab_fpga": ConceptSimBackend(
        id="lab_fpga",
        name="Lab FPGA rig (concept)",
        kind="fpga_lab",
        fidelity_base=None,      # Not meaningful for a classical rig in this toy KPI model
        fidelity_span=0.0,
        latency_base_us=2.0,
        latency_span_us=8.0,
        backaction_base=0.01,
        backaction_span=0.05,
    ),
}


def get_backend(target_id: str) -> BaseBackend:
    """Return a backend instance for the given target id.

    Raises KeyError if the backend is not known. The engine will catch this
    and translate to a user-visible error.
    """
    if target_id not in _BACKENDS:
        raise KeyError(f"Unknown hardware_target '{target_id}'")
    return _BACKENDS[target_id]


def list_backends() -> Dict[str, BaseBackend]:
    """Return the current backend registry (id -> backend)."""
    return dict(_BACKENDS)
```

## README.md

```md
# SynQc TDS Console — Sleek Repo v0.4

This repository combines:

- The **approved SynQc TDS frontend console look** (single-file UI).
- A **FastAPI backend** that runs SynQc experiment presets and returns KPIs.
- The **SynQc Temporal Dynamics Series technical archive** (for engineering + GPT context).
- A **GPT Pro context instruction file** for configuring a SynQc Guide assistant.

## What’s new in v0.4

- Primary nav is now **fully functional** and maps to real backend capability:
  - **Console**: run presets + KPIs + inline history
  - **Experiments**: read-only list from `GET /experiments/recent` (click a row to open Details)
  - **Hardware**: list from `GET /hardware/targets`
  - **Details**: record view from `GET /experiments/{id}` (replaces misleading “Logs”)
- Fixed a JavaScript brace issue so the UI script executes reliably.
- Filters now work independently on both Console history and the Experiments page.

## What’s new in v0.3

- Frontend visuals upgraded (still single-file, no external assets):
  - Bloch “atmosphere”, rotating rings, animated trace paths, and a DPD timeline spark.
  - KPIs now drive subtle animation cues (fidelity ↔ glow, latency ↔ spin speed, backaction ↔ noise).
- Setup panel pulls backend guardrails from `GET /health`:
  - `max_shots_per_experiment` drives the **Shot budget max** label and input clamp.
  - `default_shot_budget` is used when the field is empty/invalid.
- `GET /hardware/targets` respects `allow_remote_hardware` (filters non-sim targets when disabled).
- Added a single-file, fullstack review artifact: `SYNQC_FULLSTACK_ONEFILE_v0.4.md`.
- Control panel includes the credit line: **Developed by eVision Enterprises**.

## What’s new in v0.2

- Frontend chat logging is now **XSS-safe** (no `innerHTML`; all message text is rendered via `textContent`).
- Frontend now includes a **Run preset** action wired to the backend:
  - Calls `POST /experiments/run`
  - Updates KPI tiles + run history
  - Pulls `/hardware/targets` + `/experiments/recent` on load
- Backend CORS is adjusted for sanity: wildcard origins allowed for local dev, **credentials disabled**.
- Backend includes **concept placeholder backends** (IBM / IonQ / FPGA) so the UI stays functional while real provider SDKs are integrated.

---

## Repo layout

- `web/index.html`
  - The console UI (portable, no external assets).  
  - By default it assumes the backend is running at `http://localhost:8001`.
  - Override with `?api=http://HOST:PORT` (example below).

- `backend/`
  - Python package `synqc_backend` (FastAPI + engine + storage).

- `docs/SynQc_Temporal_Dynamics_Series_Technical_Archive_v0_1.md`
  - Full technical archive (design + guardrails + workflow reference).

- `gpt/SynQc_GPT_Pro_Context_Instructions_v0_1.md`
  - Copy/paste instructions for building a GPT called **SynQc Guide** using the knowledge file above.

---

## Run it locally (Windows-friendly)

### 1) Start the backend

From the repo root:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .\backend
uvicorn synqc_backend.api:app --host 127.0.0.1 --port 8001 --reload
```

Open backend docs:
- `http://127.0.0.1:8001/docs`

### 2) Open the frontend

Option A (fastest): open `web/index.html` directly in your browser.

Option B (recommended): serve it so the browser origin is clean:

```powershell
cd web
py -m http.server 8080
```

Then open:
- `http://127.0.0.1:8080/`

### 3) (Optional) Point the UI at a different backend URL

If your backend isn’t on `localhost:8001`, open:

- `http://127.0.0.1:8080/?api=http://127.0.0.1:8001`

---

## Security note (why the XSS fix matters)

Any time user text or backend text touches the DOM, treat it as hostile input.  
This repo’s UI now renders message and table text using DOM nodes + `textContent`, not HTML injection.

---

Version tag:
- **Sleek Repo v0.4 (2025-12-12)**
```
