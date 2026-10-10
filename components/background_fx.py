"""
Hiệu ứng nền động cho toàn bộ app:
  • Các mảng màu gradient mờ trôi chậm (aurora)
  • Mạng hạt nối nhau bằng đường mảnh, phản ứng với chuột (nối về con trỏ, bị đẩy nhẹ)
  • Quầng sáng đi theo con trỏ + gợn sóng khi bấm chuột

Cách hoạt động: Streamlit không chạy <script> trong st.markdown, nên dùng components.html
(iframe cùng origin) để chèn MỘT LẦN đoạn mã lõi vào trang chính (window.parent). Mã lõi chạy
trong trang chính nên không bị dừng khi Streamlit tạo lại iframe; các lần sau iframe chỉ gửi
cấu hình mới (đổi giao diện Sáng/Tối, bật/tắt) qua sự kiện "fxcfg".
Tự tạm dừng khi tab bị ẩn; tôn trọng cài đặt "giảm chuyển động" của hệ điều hành.
"""
from __future__ import annotations

import json

import streamlit.components.v1 as components

_THEMES = {
    "light": {
        "blobs": ["rgba(37,99,235,0.30)", "rgba(6,182,212,0.26)", "rgba(139,92,246,0.24)", "rgba(16,185,129,0.20)"],
        "dot": "37,99,235", "line": "37,99,235", "glow": "rgba(37,99,235,0.18)",
        "bg": "#f4f7fb", "glass": "rgba(255,255,255,0.72)", "glass_border": "rgba(226,232,240,0.9)",
    },
    "dark": {
        "blobs": ["rgba(37,99,235,0.38)", "rgba(6,182,212,0.26)", "rgba(139,92,246,0.32)", "rgba(16,185,129,0.22)"],
        "dot": "125,170,255", "line": "96,150,255", "glow": "rgba(88,166,255,0.22)",
        "bg": "#0b1020", "glass": "rgba(13,17,23,0.72)", "glass_border": "rgba(48,54,61,0.9)",
    },
}

# Mã lõi – chạy trong trang chính, chỉ khởi tạo một lần
_CORE = r"""
(function () {
  if (window.__fxLoaded) return; window.__fxLoaded = true;
  const doc = document;
  let root = null, glow = null, cv = null, ctx = null, running = false;
  let W = 0, H = 0, pts = [], ripples = [];
  const mouse = { x: -9999, y: -9999, active: false };
  const reduce = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;
  const LINK = 130, MOUSE_R = 170;

  function css(c) {
    let st = doc.getElementById("fx-style");
    if (!st) { st = doc.createElement("style"); st.id = "fx-style"; doc.head.appendChild(st); }
    // Selector có độ ưu tiên cao hơn CSS giao diện sẵn có (cũng dùng !important)
    st.textContent = `
      html body { background: ${c.bg} !important; }
      html body .stApp, html body [data-testid="stAppViewContainer"], html body [data-testid="stMain"],
      html body .main { background: transparent !important; background-color: transparent !important; }
      html body header, html body header[data-testid="stHeader"], html body [data-testid="stAppHeader"],
      html body .stAppHeader { background: ${c.glass} !important; background-color: ${c.glass} !important;
        backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px); }
      html body section[data-testid="stSidebar"] { background: ${c.glass} !important;
        backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px); border-right: 1px solid ${c.glass_border} !important; }
      html body div[data-testid="stElementContainer"]:has(> iframe[height="0"]),
      html body div.element-container:has(> iframe[height="0"]) { display: none !important; }
      /* Lớp nền nằm DƯỚI toàn bộ nội dung (z-index âm) – không thay đổi position của các khối
         Streamlit, nên thanh bên / trang chính vẫn cuộn bình thường */
      #fx-root { position: fixed; inset: 0; z-index: -1; pointer-events: none; overflow: hidden; }
      #fx-root .blob { position: absolute; width: 46vmax; height: 46vmax; border-radius: 50%;
        filter: blur(70px); will-change: transform; transition: background 1s; }
      #fx-root canvas { position: absolute; inset: 0; }
      #fx-glow { position: absolute; left: 0; top: 0; width: 520px; height: 520px; margin: -260px 0 0 -260px;
        border-radius: 50%; background: radial-gradient(circle, ${c.glow} 0%, transparent 65%);
        transition: opacity .4s; opacity: 0; }
      @keyframes fxa { 0%{transform:translate(0,0) scale(1)} 33%{transform:translate(18vw,12vh) scale(1.15)}
                       66%{transform:translate(-12vw,20vh) scale(.9)} 100%{transform:translate(0,0) scale(1)} }
      @keyframes fxb { 0%{transform:translate(0,0) scale(1)} 50%{transform:translate(-20vw,-14vh) scale(1.2)}
                       100%{transform:translate(0,0) scale(1)} }
      @media (prefers-reduced-motion: reduce) { #fx-root .blob { animation: none !important; } }`;
  }

  function build(c) {
    root = doc.createElement("div"); root.id = "fx-root";
    const spots = [
      { top: "-12vmax", left: "-10vmax", anim: "fxa 26s" }, { top: "-8vmax", right: "-14vmax", anim: "fxb 32s" },
      { top: "40vh", left: "30vw", anim: "fxa 38s reverse" }, { bottom: "-16vmax", right: "-6vmax", anim: "fxb 30s reverse" }];
    spots.forEach((s, i) => {
      const b = doc.createElement("div"); b.className = "blob";
      Object.assign(b.style, { top: s.top || "", left: s.left || "", right: s.right || "", bottom: s.bottom || "",
        background: c.blobs[i], animation: s.anim + " ease-in-out infinite" });
      root.appendChild(b);
    });
    glow = doc.createElement("div"); glow.id = "fx-glow"; root.appendChild(glow);
    cv = doc.createElement("canvas"); root.appendChild(cv); ctx = cv.getContext("2d");
    doc.body.prepend(root); resize();
  }

  function resize() {
    if (!cv) return;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    W = innerWidth; H = innerHeight;
    cv.width = W * dpr; cv.height = H * dpr; cv.style.width = W + "px"; cv.style.height = H + "px";
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const n = Math.round(Math.min(90, (W * H) / 16000));
    pts = Array.from({ length: n }, () => ({ x: Math.random() * W, y: Math.random() * H,
      vx: (Math.random() - .5) * .35, vy: (Math.random() - .5) * .35, r: Math.random() * 1.6 + .8 }));
  }

  function frame() {
    if (!running) return;
    const c = window.__fxCfg;
    ctx.clearRect(0, 0, W, H);
    for (const p of pts) {
      if (!reduce) { p.x += p.vx; p.y += p.vy; }
      if (p.x < 0 || p.x > W) p.vx *= -1;
      if (p.y < 0 || p.y > H) p.vy *= -1;
      if (mouse.active) {
        const dx = p.x - mouse.x, dy = p.y - mouse.y, d = Math.hypot(dx, dy);
        if (d < MOUSE_R && d > .1) { const f = (MOUSE_R - d) / MOUSE_R * .9; p.x += dx / d * f; p.y += dy / d * f; }
      }
    }
    for (let i = 0; i < pts.length; i++) {
      const a = pts[i];
      for (let j = i + 1; j < pts.length; j++) {
        const b = pts[j], d = Math.hypot(a.x - b.x, a.y - b.y);
        if (d < LINK) { ctx.strokeStyle = `rgba(${c.line},${(1 - d / LINK) * .22})`; ctx.lineWidth = 1;
          ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke(); }
      }
      if (mouse.active) {
        const d = Math.hypot(a.x - mouse.x, a.y - mouse.y), R = MOUSE_R * 1.3;
        if (d < R) { ctx.strokeStyle = `rgba(${c.line},${(1 - d / R) * .55})`; ctx.lineWidth = 1.1;
          ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(mouse.x, mouse.y); ctx.stroke(); }
      }
      ctx.fillStyle = `rgba(${c.dot},.55)`; ctx.beginPath(); ctx.arc(a.x, a.y, a.r, 0, Math.PI * 2); ctx.fill();
    }
    ripples = ripples.filter(r => r.a > .01);
    for (const r of ripples) { r.r += 6; r.a *= .93; ctx.strokeStyle = `rgba(${c.line},${r.a})`; ctx.lineWidth = 2;
      ctx.beginPath(); ctx.arc(r.x, r.y, r.r, 0, Math.PI * 2); ctx.stroke(); }
    if (doc.hidden) setTimeout(() => requestAnimationFrame(frame), 500); else requestAnimationFrame(frame);
  }

  function apply() {
    const c = window.__fxCfg;
    if (!c.enabled) {
      running = false;
      if (root) { root.remove(); root = null; cv = null; }
      const st = doc.getElementById("fx-style"); if (st) st.remove();
      return;
    }
    css(c);
    if (!root) build(c);
    else root.querySelectorAll(".blob").forEach((b, i) => b.style.background = c.blobs[i % c.blobs.length]);
    if (!running) { running = true; requestAnimationFrame(frame); }
  }

  addEventListener("resize", resize);
  doc.addEventListener("mousemove", e => {
    mouse.x = e.clientX; mouse.y = e.clientY; mouse.active = true;
    if (glow) { glow.style.transform = `translate(${e.clientX}px, ${e.clientY}px)`; glow.style.opacity = 1; }
  }, { passive: true });
  doc.addEventListener("mouseleave", () => { mouse.active = false; if (glow) glow.style.opacity = 0; });
  doc.addEventListener("mousedown", e => ripples.push({ x: e.clientX, y: e.clientY, r: 0, a: .5 }), { passive: true });
  addEventListener("fxcfg", apply);
  apply();
})();
"""

_LOADER = """
<script>
(function () {
  const P = window.parent;
  P.__fxCfg = __CFG__;
  if (!P.__fxLoaded) {
    const s = P.document.createElement("script");
    s.textContent = __CORE__;
    P.document.head.appendChild(s);
  } else {
    P.dispatchEvent(new P.Event("fxcfg"));
  }
})();
</script>
"""


def inject_background(theme: str = "light", enabled: bool = True):
    cfg = dict(_THEMES.get(theme, _THEMES["light"]))
    cfg["enabled"] = bool(enabled)
    html = _LOADER.replace("__CFG__", json.dumps(cfg)).replace("__CORE__", json.dumps(_CORE))
    components.html(html, height=0)
