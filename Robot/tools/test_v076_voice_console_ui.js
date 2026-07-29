// Focused v0.7.6 Live Voice layout and draft-preservation regression check.
const fs = require("fs");
const app = fs.readFileSync("Robot/python/bx1_management/static/app.js", "utf8");
const css = fs.readFileSync("Robot/python/bx1_management/static/styles.css", "utf8");

function requireText(value, message) { if (!value) throw new Error(message); }

requireText(app.includes('class="voice-console-page"'), "voice page lacks explicit layout root");
requireText(app.includes('class="voice-console-transcript"'), "transcript lacks explicit full-width region");
requireText(app.includes('className: "shared-live-conversation"'), "shared transcript lacks explicit panel class");
requireText(app.includes('No live conversation items yet.'), "empty shared-buffer wording missing");
requireText(!app.includes('No browser-session voice items yet.'), "obsolete browser-only wording remains");
requireText(app.includes('else if (["voice", "brain", "audio"].includes(state.page)) updateLiveVoiceDom();'), "live pages still full-render on telemetry refresh");
requireText(app.includes('pausedScrollTop') && app.includes('refreshedFeed.scrollTop = pausedScrollTop'), "paused transcript scroll is not preserved");
requireText(css.includes('.voice-console-page { display:grid; grid-template-columns:minmax(0,1fr);'), "desktop console root is not minmax responsive");
requireText(css.includes('.voice-console-top { display:grid; grid-template-columns:minmax(0,1.35fr) minmax(0,.65fr);'), "desktop status/level layout missing");
requireText(css.includes('.voice-console-page, .voice-console-top { grid-template-columns:minmax(0,1fr);'), "narrow one-column layout missing");
requireText(css.includes('.voice-session-item { width:fit-content; max-width:84%;'), "conversation bubble width is not bounded");
console.log("v0.7.6 Live Voice desktop/narrow layout and refresh regression checks: OK");
