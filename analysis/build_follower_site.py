#!/usr/bin/env python3
"""Generate static Curius follower graph pages."""

from __future__ import annotations

import argparse
import os
import heapq
import html
import json
import math
import sqlite3
import sys
import tempfile
from collections import Counter, defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

try:
    import networkx as nx
except Exception:  # ponytail: optional; only the deep analysis page needs modularity/betweenness.
    nx = None

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = REPO_ROOT / "data/curius.sqlite"
DEFAULT_ANALYSIS_APP = REPO_ROOT / "apps/analysis"
DEFAULT_FRONTPAGE_APP = REPO_ROOT / "apps/frontpage"
DEFAULT_GRAPH_OUT = DEFAULT_ANALYSIS_APP / "index.html"
DEFAULT_METRICS_OUT = DEFAULT_ANALYSIS_APP / "metrics.html"
DEFAULT_ALGORITHMS_OUT = DEFAULT_ANALYSIS_APP / "algorithms.html"
DEFAULT_NEXT_OUT = DEFAULT_ANALYSIS_APP / "questions.html"
DEFAULT_FRONTPAGE_OUT = DEFAULT_FRONTPAGE_APP / "index.html"
DEFAULT_ANALYSIS_URL = "../analysis"
DEFAULT_FRONTPAGE_URL = "../frontpage"
GOLDEN_ANGLE = math.pi * (3 - math.sqrt(5))

PAPER_CSS = """
  :root {
    color-scheme: light;
    --paper: #f7f0e4;
    --sheet: #fffaf0;
    --ink: #20170f;
    --muted: #6f6254;
    --rule: #d8c8b5;
    --soft: #eadfce;
    --red: #b74d2f;
    --blue: #2f63b7;
    --green: #247a4b;
    --violet: #7047a8;
  }
  * { box-sizing: border-box; }
  html { scroll-behavior: smooth; }
  body {
    margin: 0;
    background:
      radial-gradient(circle at 18% 12%, rgba(255,255,255,.58), transparent 28rem),
      linear-gradient(90deg, rgba(88,54,20,.025) 1px, transparent 1px),
      var(--paper);
    background-size: auto, 18px 18px, auto;
    color: var(--ink);
    font-family: "Palatino Linotype", Palatino, "Book Antiqua", Georgia, serif;
    font-size: 18px;
    line-height: 1.5;
  }
  a { color: var(--blue); text-decoration-thickness: .08em; text-underline-offset: .16em; }
  button, input, select { font: inherit; color: inherit; }
  code, pre { font-family: inherit; }
  .page { width: min(1180px, 100%); margin: 0 auto; padding: 26px clamp(14px, 3vw, 34px) 42px; }
  h1, h2, h3 { font-weight: 500; line-height: 1.1; letter-spacing: -.02em; }
  h1 { font-size: clamp(2rem, 7vw, 4.7rem); margin: 0 0 .35em; }
  h2 { font-size: clamp(1.45rem, 4vw, 2.4rem); margin: 2rem 0 .55rem; }
  h3 { font-size: 1.22rem; margin: 1.2rem 0 .35rem; }
  p { margin: .55rem 0; max-width: 72ch; }
  .quiet { color: var(--muted); }
  .nav { display: flex; gap: .75rem; flex-wrap: wrap; align-items: center; margin: 0 0 1.1rem; }
  .nav a { color: var(--ink); }
  .sheet {
    background: rgba(255, 250, 240, .82);
    border: 1px solid var(--rule);
    border-radius: 18px;
    box-shadow: 0 1px 0 rgba(60, 42, 20, .05);
  }
  .controls { display: grid; gap: .7rem; }
  label { display: grid; gap: .25rem; color: var(--muted); }
  input, select, button {
    border: 1px solid var(--rule);
    border-radius: 999px;
    background: rgba(255, 252, 245, .96);
    min-height: 44px;
    padding: .48rem .78rem;
  }
  button { cursor: pointer; }
  button:hover, button:focus-visible, input:focus-visible, select:focus-visible { outline: 2px solid rgba(47, 99, 183, .28); outline-offset: 2px; }
  table { border-collapse: collapse; width: 100%; margin: .8rem 0 1.2rem; font-size: .95rem; }
  th, td { border-bottom: 1px solid var(--rule); padding: .45rem .35rem; text-align: left; vertical-align: top; }
  th { font-weight: 500; color: var(--muted); }
  .math {
    display: block;
    width: fit-content;
    max-width: 100%;
    overflow-x: auto;
    margin: .9rem 0;
    padding: .7rem .85rem;
    border-left: 3px solid var(--rule);
    background: rgba(255, 252, 245, .78);
    font-size: clamp(1.08rem, 3vw, 1.35rem);
    white-space: nowrap;
  }
  .frac { display: inline-grid; grid-template-rows: auto auto; vertical-align: middle; text-align: center; line-height: 1.05; }
  .frac > span:first-child { border-bottom: 1px solid currentColor; padding: 0 .14em .05em; }
  .frac > span:last-child { padding: .06em .14em 0; }
  .term, .glossary button {
    border-radius: .25rem;
    cursor: pointer;
    padding: 0 .08em;
  }
  .term:hover, .term:focus-visible, .glossary button:hover, .glossary button:focus-visible { background: rgba(47, 99, 183, .12); outline: none; }
  .cite { white-space: nowrap; }
  .definition-card {
    position: fixed;
    left: 50%;
    bottom: 18px;
    transform: translateX(-50%);
    width: min(620px, calc(100vw - 22px));
    padding: .85rem 1rem;
    z-index: 20;
    display: none;
  }
  .definition-card[open] { display: block; }
  .definition-card button { float: right; min-height: 34px; padding: .2rem .65rem; }
  @media (max-width: 760px) {
    body { font-size: 16px; }
    .page { padding-left: 12px; padding-right: 12px; }
    table { font-size: .9rem; }
  }
"""

GRAPH_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Curius follower graph</title>
<style>
__PAPER_CSS__
  .graph-layout { display: grid; grid-template-columns: minmax(0, 1fr) minmax(280px, 350px); gap: 1rem; align-items: start; }
  .graph-tools { grid-template-columns: minmax(230px, 1fr) minmax(175px, 190px) minmax(190px, 230px) auto; column-gap: 1.45rem; row-gap: .8rem; margin: 1rem 0; }
  .graph-tools label { min-width: 0; white-space: nowrap; }
  #fit { width: auto; min-width: 118px; justify-self: end; }
  .canvas-wrap { position: relative; min-height: 620px; overflow: hidden; touch-action: none; }
  canvas { display: block; width: 100%; height: min(72vh, 720px); min-height: 520px; border-radius: 18px; cursor: grab; }
  canvas:active { cursor: grabbing; }
  .canvas-note { position: absolute; left: .8rem; right: .8rem; bottom: .7rem; color: var(--muted); background: rgba(255,250,240,.84); border: 1px solid var(--rule); border-radius: 14px; padding: .45rem .65rem; font-size: .92rem; }
  .reader { padding: .2rem 0 .2rem 1rem; border-left: 1px solid var(--rule); position: sticky; top: 12px; }
  .reader h2 { margin-top: 0; }
  .counts { display: grid; grid-template-columns: repeat(3, 1fr); gap: .55rem; margin: .85rem 0; }
  .count { border-top: 1px solid var(--rule); padding-top: .35rem; }
  .count b { display: block; font-size: 1.45rem; font-weight: 500; line-height: 1.1; }
  .count span { color: var(--muted); font-size: .9rem; }
  .people { display: grid; gap: .45rem; max-height: 260px; overflow: auto; padding-right: .15rem; }
  .person { width: 100%; border-radius: 14px; text-align: left; line-height: 1.25; }
  .person small { display: block; color: var(--muted); margin-top: .12rem; }
  .matches { margin-top: 1rem; padding-top: .8rem; border-top: 1px solid var(--rule); }
  .matches .people { grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); max-height: none; }
  .legend { display: flex; gap: .8rem; flex-wrap: wrap; color: var(--muted); margin: .4rem 0 .7rem; }
  .dot { width: .7rem; height: .7rem; display: inline-block; border-radius: 999px; margin-right: .25rem; vertical-align: -.04rem; }
  @media (max-width: 920px) {
    .graph-layout, .graph-tools { grid-template-columns: 1fr; }
    .reader { position: static; }
    .canvas-wrap { min-height: 480px; }
    canvas { height: 64vh; min-height: 430px; }
  }
</style>
</head>
<body>
<div class="page">
  <nav class="nav"><a href="__FRONTPAGE_INDEX_URL__">Curius front page</a><a href="metrics.html">Read the metrics page</a><a href="algorithms.html">Go deeper on algorithms</a><a href="questions.html">Next questions</a></nav>
  <h1>Curius follower graph</h1>
  <p>Each dot is a Curius user. A line points from the person who follows to the person being followed. The map uses every stored follow edge. High-core and high-degree people sit near the center; small or isolated weak components sit around the outside.</p>
  <p class="quiet">Drag to pan. Scroll to zoom. Click a dot, or search by name, handle, or school.</p>
  <section class="controls graph-tools">
    <label>Find a person <input id="q" type="search" autocomplete="off" placeholder="name, handle, school"></label>
    <label>Minimum followers <input id="min-followers" type="number" min="0" step="1" value="0"></label>
    <label>Show <select id="mode"><option value="whole">whole graph</option><option value="ego">neighborhood</option><option value="followers">followers</option><option value="following">following</option></select></label>
    <button id="fit" type="button">Fit graph</button>
  </section>
  <section class="graph-layout">
    <figure class="canvas-wrap sheet">
      <canvas id="graph" aria-label="Interactive follower graph"></canvas>
      <figcaption id="status" class="canvas-note"></figcaption>
    </figure>
    <aside id="reader" class="reader"></aside>
  </section>
  <section class="matches">
    <h2>Search results</h2>
    <div id="matches" class="people"></div>
  </section>
</div>
<script id="graph-data" type="application/json">__GRAPH_JSON__</script>
<script>
(() => {
  "use strict";
  const raw = JSON.parse(document.getElementById("graph-data").textContent);
  const nodes = raw.nodes.map(n => ({...n, followers: [], following: []}));
  const byId = new Map(nodes.map(n => [n.id, n]));
  for (const [follower, followed] of raw.edges) {
    const a = byId.get(follower), b = byId.get(followed);
    if (!a || !b) continue;
    a.following.push(followed);
    b.followers.push(follower);
  }
  nodes.sort((a, b) => (b.in + b.out) - (a.in + a.out) || b.in - a.in || a.slug.localeCompare(b.slug));
  const edgeSet = new Set(raw.edges.map(([a, b]) => `${a}>${b}`));
  const canvas = document.getElementById("graph");
  const ctx = canvas.getContext("2d");
  const reader = document.getElementById("reader");
  const status = document.getElementById("status");
  const q = document.getElementById("q");
  const minFollowers = document.getElementById("min-followers");
  const mode = document.getElementById("mode");
  const matches = document.getElementById("matches");
  const view = {x: 0, y: 0, scale: 1};
  let selected = nodes[0]?.id || null;
  let visibleIds = new Set(nodes.map(n => n.id));
  let pointer = null;
  let hover = null;

  function label(n) { return n.name && n.name !== n.slug ? `${n.name} · ${n.slug}` : n.slug; }
  function profileUrl(n) { return `https://curius.app/users/${encodeURIComponent(n.slug)}`; }
  function degree(n) { return n.in + n.out; }
  function matchesText(n, term) { return `${n.name} ${n.slug} ${n.school || ""}`.toLowerCase().includes(term); }
  function sortedPeople(ids) { return ids.map(id => byId.get(id)).filter(Boolean).sort((a, b) => degree(b) - degree(a) || a.slug.localeCompare(b.slug)); }
  function resize() {
    const rect = canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.max(1, Math.round(rect.width * dpr));
    canvas.height = Math.max(1, Math.round(rect.height * dpr));
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    draw();
  }
  function project(n) {
    const rect = canvas.getBoundingClientRect();
    return {x: rect.width / 2 + (n.x + view.x) * view.scale, y: rect.height / 2 + (n.y + view.y) * view.scale};
  }
  function unproject(x, y) {
    const rect = canvas.getBoundingClientRect();
    return {x: (x - rect.width / 2) / view.scale - view.x, y: (y - rect.height / 2) / view.scale - view.y};
  }
  function nodeRadius(n) { return Math.max(2.1, Math.min(12, 2.2 + Math.sqrt(Math.max(0, n.in)) * .28 + n.core * .16)); }
  function computeVisible() {
    const min = Number(minFollowers.value) || 0;
    const center = selected && byId.get(selected);
    let ids;
    if (!center || mode.value === "whole") ids = nodes.filter(n => n.in >= min).map(n => n.id);
    else if (mode.value === "followers") ids = [center.id, ...center.followers].filter(id => id === center.id || (byId.get(id)?.in || 0) >= min);
    else if (mode.value === "following") ids = [center.id, ...center.following].filter(id => id === center.id || (byId.get(id)?.in || 0) >= min);
    else ids = [center.id, ...center.followers, ...center.following].filter(id => id === center.id || (byId.get(id)?.in || 0) >= min);
    visibleIds = new Set(ids);
  }
  function fit() {
    computeVisible();
    const list = [...visibleIds].map(id => byId.get(id)).filter(Boolean);
    if (!list.length) return;
    const rect = canvas.getBoundingClientRect();
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (const n of list) { minX = Math.min(minX, n.x); minY = Math.min(minY, n.y); maxX = Math.max(maxX, n.x); maxY = Math.max(maxY, n.y); }
    const pad = 90;
    const sx = (rect.width - 48) / Math.max(1, maxX - minX + pad);
    const sy = (rect.height - 48) / Math.max(1, maxY - minY + pad);
    view.scale = Math.max(.18, Math.min(3.5, Math.min(sx, sy)));
    view.x = -(minX + maxX) / 2;
    view.y = -(minY + maxY) / 2;
    draw();
  }
  function relationColor(id) {
    if (id === selected) return "#b74d2f";
    const center = selected && byId.get(selected);
    if (!center) return "#7d715f";
    const incoming = center.followers.includes(id);
    const outgoing = center.following.includes(id);
    if (incoming && outgoing) return "#7047a8";
    if (incoming) return "#2f63b7";
    if (outgoing) return "#247a4b";
    return "#8f806c";
  }
  function drawEdge(a, b, color, alpha, width) {
    const pa = project(a), pb = project(b);
    if (pa.x < -80 && pb.x < -80) return;
    const rect = canvas.getBoundingClientRect();
    if (pa.x > rect.width + 80 && pb.x > rect.width + 80) return;
    if (pa.y < -80 && pb.y < -80) return;
    if (pa.y > rect.height + 80 && pb.y > rect.height + 80) return;
    ctx.globalAlpha = alpha;
    ctx.strokeStyle = color;
    ctx.lineWidth = Math.max(.45, width * Math.sqrt(view.scale));
    ctx.beginPath();
    ctx.moveTo(pa.x, pa.y);
    ctx.lineTo(pb.x, pb.y);
    ctx.stroke();
  }
  function drawArrow(a, b, color) {
    const pa = project(a), pb = project(b);
    const dx = pb.x - pa.x, dy = pb.y - pa.y;
    const len = Math.hypot(dx, dy);
    if (len < 8) return;
    const ux = dx / len, uy = dy / len;
    const r = nodeRadius(b) * view.scale + 4;
    const x = pb.x - ux * r, y = pb.y - uy * r;
    ctx.save();
    ctx.translate(x, y);
    ctx.rotate(Math.atan2(dy, dx));
    ctx.fillStyle = color;
    ctx.globalAlpha = .8;
    ctx.beginPath();
    ctx.moveTo(0, 0);
    ctx.lineTo(-8, -4);
    ctx.lineTo(-8, 4);
    ctx.closePath();
    ctx.fill();
    ctx.restore();
  }
  function draw() {
    if (!ctx) return;
    computeVisible();
    const rect = canvas.getBoundingClientRect();
    ctx.clearRect(0, 0, rect.width, rect.height);
    ctx.fillStyle = "#fffaf0";
    ctx.fillRect(0, 0, rect.width, rect.height);
    const center = selected && byId.get(selected);
    const focus = new Set(center ? [center.id, ...center.followers, ...center.following] : []);
    let edgeCount = 0;
    for (const [aId, bId] of raw.edges) {
      if (!visibleIds.has(aId) || !visibleIds.has(bId)) continue;
      const a = byId.get(aId), b = byId.get(bId);
      if (!a || !b) continue;
      const touches = aId === selected || bId === selected;
      if (selected && mode.value === "whole" && !touches && view.scale < .7) {
        drawEdge(a, b, "#8b7b67", .08, .65);
      } else if (touches) {
        drawEdge(a, b, bId === selected ? "#2f63b7" : "#247a4b", .72, 1.3);
        drawArrow(a, b, bId === selected ? "#2f63b7" : "#247a4b");
      } else {
        drawEdge(a, b, "#8b7b67", selected && mode.value !== "whole" ? .16 : .11, .75);
      }
      edgeCount++;
    }
    const list = [...visibleIds].map(id => byId.get(id)).filter(Boolean);
    for (const n of list) {
      const p = project(n);
      if (p.x < -30 || p.y < -30 || p.x > rect.width + 30 || p.y > rect.height + 30) continue;
      const r = nodeRadius(n) * Math.sqrt(view.scale);
      const active = n.id === selected || n.id === hover;
      const related = !selected || focus.has(n.id);
      ctx.globalAlpha = selected && mode.value === "whole" && !related ? .34 : .9;
      ctx.fillStyle = relationColor(n.id);
      ctx.beginPath();
      ctx.arc(p.x, p.y, Math.max(1.7, r), 0, Math.PI * 2);
      ctx.fill();
      if (active) {
        ctx.globalAlpha = .95;
        ctx.strokeStyle = "#20170f";
        ctx.lineWidth = 2;
        ctx.stroke();
      }
    }
    ctx.globalAlpha = 1;
    const labelNodes = list.filter(n => n.id === selected || n.id === hover || (view.scale > .85 && n.in >= 80) || (view.scale > 1.6 && degree(n) >= 18)).slice(0, 70);
    ctx.font = `${Math.max(13, 15 * Math.min(1.4, view.scale))}px Palatino, Georgia, serif`;
    ctx.textBaseline = "middle";
    for (const n of labelNodes) {
      const p = project(n);
      const text = n.name || n.slug;
      ctx.lineWidth = 4;
      ctx.strokeStyle = "rgba(255,250,240,.9)";
      ctx.strokeText(text, p.x + nodeRadius(n) * Math.sqrt(view.scale) + 4, p.y);
      ctx.fillStyle = "#20170f";
      ctx.fillText(text, p.x + nodeRadius(n) * Math.sqrt(view.scale) + 4, p.y);
    }
    const suffix = selected ? ` Selected: ${byId.get(selected)?.slug}.` : "";
    status.textContent = `Showing ${list.length.toLocaleString()} people and ${edgeCount.toLocaleString()} follows. Blue lines enter the selected person; green lines leave it.${suffix}`;
  }
  function hitTest(clientX, clientY) {
    const rect = canvas.getBoundingClientRect();
    const world = unproject(clientX - rect.left, clientY - rect.top);
    let best = null, bestD = Infinity;
    for (const id of visibleIds) {
      const n = byId.get(id);
      if (!n) continue;
      const d = Math.hypot(world.x - n.x, world.y - n.y);
      const radius = Math.max(12 / view.scale, nodeRadius(n) + 4 / view.scale);
      if (d < radius && d < bestD) { best = n; bestD = d; }
    }
    return best;
  }
  function personButton(n) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "person";
    button.innerHTML = `<span>${escapeHtml(n.name || n.slug)}</span><small>${escapeHtml(n.slug)} · ${n.in.toLocaleString()} followers · ${n.out.toLocaleString()} following</small>`;
    button.addEventListener("click", () => selectNode(n.id, true));
    return button;
  }
  function escapeHtml(value) {
    const span = document.createElement("span");
    span.textContent = String(value);
    return span.innerHTML;
  }
  function renderReader() {
    const n = selected && byId.get(selected);
    if (!n) { reader.textContent = "Select a dot to read it."; return; }
    const followers = sortedPeople(n.followers);
    const following = sortedPeople(n.following);
    const mutual = followers.filter(p => edgeSet.has(`${n.id}>${p.id}`));
    reader.innerHTML = "";
    const title = document.createElement("h2"); title.textContent = n.name || n.slug;
    const link = document.createElement("p"); link.innerHTML = `<a href="${profileUrl(n)}" target="_blank" rel="noreferrer">${escapeHtml(n.slug)}</a>`;
    const counts = document.createElement("div"); counts.className = "counts";
    counts.innerHTML = `<div class="count"><b>${n.in.toLocaleString()}</b><span>followers</span></div><div class="count"><b>${n.out.toLocaleString()}</b><span>following</span></div><div class="count"><b>${n.core}</b><span>core</span></div>`;
    const note = document.createElement("p"); note.className = "quiet";
    note.textContent = [n.school, n.twitter && `twitter: ${n.twitter}`, n.github && `github: ${n.github}`, n.website].filter(Boolean).join(" · ") || "No profile metadata in the scrape.";
    const rank = document.createElement("p");
    rank.textContent = `PageRank share ${(n.rank * 100).toFixed(2)}%. ${mutual.length.toLocaleString()} of these relationships are mutual in the stored graph.`;
    reader.append(title, link, counts, note, rank, peopleSection("Followers", followers), peopleSection("Following", following));
  }
  function peopleSection(title, people) {
    const section = document.createElement("section");
    const h = document.createElement("h3"); h.textContent = `${title} (${people.length.toLocaleString()})`;
    const list = document.createElement("div"); list.className = "people";
    people.slice(0, 42).forEach(p => list.append(personButton(p)));
    section.append(h, list);
    return section;
  }
  function renderMatches() {
    const term = q.value.trim().toLowerCase();
    const found = (term ? nodes.filter(n => matchesText(n, term)) : nodes.slice(0, 12)).slice(0, 18);
    matches.replaceChildren(...found.map(personButton));
  }
  function selectNode(id, shouldFit) {
    if (!byId.has(id)) return;
    selected = id;
    q.value = byId.get(id).slug;
    renderReader();
    renderMatches();
    if (mode.value === "whole") draw(); else shouldFit ? fit() : draw();
  }
  canvas.addEventListener("pointerdown", ev => {
    canvas.setPointerCapture(ev.pointerId);
    const hit = hitTest(ev.clientX, ev.clientY);
    pointer = {id: ev.pointerId, x: ev.clientX, y: ev.clientY, moved: false, hit: hit?.id || null};
  });
  canvas.addEventListener("pointermove", ev => {
    if (pointer && pointer.id === ev.pointerId) {
      const dx = ev.clientX - pointer.x, dy = ev.clientY - pointer.y;
      if (Math.hypot(dx, dy) > 2) pointer.moved = true;
      view.x += dx / view.scale; view.y += dy / view.scale;
      pointer.x = ev.clientX; pointer.y = ev.clientY;
      draw();
      return;
    }
    const hit = hitTest(ev.clientX, ev.clientY);
    if ((hit?.id || null) !== hover) { hover = hit?.id || null; draw(); }
  });
  canvas.addEventListener("pointerup", ev => {
    if (!pointer) return;
    const hit = hitTest(ev.clientX, ev.clientY);
    if (!pointer.moved && hit) selectNode(hit.id, false);
    pointer = null;
  });
  canvas.addEventListener("wheel", ev => {
    ev.preventDefault();
    const rect = canvas.getBoundingClientRect();
    const before = unproject(ev.clientX - rect.left, ev.clientY - rect.top);
    const factor = Math.exp(-ev.deltaY * .0012);
    view.scale = Math.max(.12, Math.min(8, view.scale * factor));
    const after = unproject(ev.clientX - rect.left, ev.clientY - rect.top);
    view.x += after.x - before.x;
    view.y += after.y - before.y;
    draw();
  }, {passive: false});
  q.addEventListener("input", renderMatches);
  q.addEventListener("keydown", ev => {
    if (ev.key !== "Enter") return;
    const term = q.value.trim().toLowerCase();
    const hit = nodes.find(n => matchesText(n, term));
    if (hit) selectNode(hit.id, true);
  });
  minFollowers.addEventListener("input", () => { mode.value === "whole" ? draw() : fit(); renderMatches(); });
  mode.addEventListener("change", fit);
  document.getElementById("fit").addEventListener("click", fit);
  window.addEventListener("resize", resize);
  renderReader();
  renderMatches();
  resize();
  fit();
})();
</script>
</body>
</html>
"""

METRICS_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Curius graph metrics</title>
<style>
__PAPER_CSS__
  .article { display: grid; grid-template-columns: minmax(0, 1fr) minmax(260px, 340px); gap: 2rem; align-items: start; }
  .side { position: sticky; top: 14px; display: grid; gap: 1rem; }
  .model, .glossary, .numbers { padding: 1rem; }
  .model svg { width: 100%; height: auto; display: block; margin-top: .7rem; }
  .model-controls { display: grid; gap: .7rem; }
  .model-controls input { width: 100%; }
  .metric-list { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .75rem; margin: 1rem 0; }
  .metric { padding: .85rem; border-top: 1px solid var(--rule); background: rgba(255,250,240,.58); }
  .metric b { display: block; font-size: 1.55rem; font-weight: 500; }
  .metric span { color: var(--muted); }
  .glossary ul, .references { list-style: none; padding: 0; margin: .5rem 0 0; }
  .glossary li, .references li { margin: .45rem 0; }
  .glossary button { border: 0; background: transparent; min-height: 0; padding: .05rem .12rem; color: var(--blue); }
  .rank-table td:first-child { width: 2rem; color: var(--muted); }
  .diagram-note { color: var(--muted); min-height: 3.2em; }
  .node-label { font-size: 15px; fill: var(--ink); }
  .edge { stroke: #8d7d68; stroke-width: 1.8; fill: none; }
  .edge.active { stroke: var(--red); stroke-width: 3; }
  .toy-node { stroke: #fffaf0; stroke-width: 3; }
  .toy-node.active { stroke: var(--ink); stroke-width: 3; }
  [hidden] { display: none !important; }
  @media (max-width: 900px) {
    .article { display: flex; flex-direction: column; }
    .article > main { order: 0; }
    .side { display: contents; }
    .model { order: -1; }
    .numbers, .glossary { order: 1; }
    .metric-list { grid-template-columns: 1fr; }
  }
</style>
</head>
<body>
<div class="page">
  <nav class="nav"><a href="__FRONTPAGE_INDEX_URL__">Curius front page</a><a href="index.html">Explore the graph</a><a href="algorithms.html">Go deeper on algorithms</a><a href="questions.html">Next questions</a></nav>
  <h1>How to read this follower graph</h1>
  <div class="article">
    <main>
      <p>Start with one edge: <span class="term" data-term="edge" tabindex="0">u → v</span> means person <span class="term" data-term="u" tabindex="0">u</span> follows person <span class="term" data-term="v" tabindex="0">v</span>. Stack those edges into an adjacency matrix <span class="term" data-term="A" tabindex="0">A</span>, where <span class="term" data-term="Auv" tabindex="0">A<sub>uv</sub></span> is 1 when the edge exists. This is the usual way to measure a directed network <a class="cite" href="https://doi.org/10.1137/S003614450342480" target="_blank" rel="noreferrer" title="Reviews graph measurements such as degree, components, and clustering.">Newman 2003</a>.</p>

      <h2>First count the arrows</h2>
      <p>Degree is the smallest useful summary. Incoming degree counts followers. Outgoing degree counts people followed.</p>
      <div class="math"><span class="term" data-term="din" tabindex="0">d<sup>in</sup>(v)</span> = <span class="term" data-term="sum" tabindex="0">∑<sub>u</sub></span> <span class="term" data-term="Auv" tabindex="0">A<sub>uv</sub></span><span aria-hidden="true">,&nbsp;&nbsp;</span><span class="term" data-term="dout" tabindex="0">d<sup>out</sup>(v)</span> = <span class="term" data-term="sum" tabindex="0">∑<sub>w</sub></span> <span class="term" data-term="Avw" tabindex="0">A<sub>vw</sub></span></div>
      <p>In this scrape, the average person has <b>__AVG_IN__</b> observed followers and follows <b>__AVG_OUT__</b> people. The graph is sparse: <b>__DENSITY_PCT__</b> of all possible directed pairs without self-follows are present.</p>
      <div class="math"><span class="term" data-term="density" tabindex="0">ρ</span> = <span class="frac"><span><span class="term" data-term="m" tabindex="0">m</span></span><span><span class="term" data-term="n" tabindex="0">n</span>(<span class="term" data-term="n" tabindex="0">n</span> − 1)</span></span></div>

      <div class="metric-list">
        <div class="metric"><b>__NODES__</b><span>people in the stored user table</span></div>
        <div class="metric"><b>__EDGES__</b><span>directed follow edges</span></div>
        <div class="metric"><b>__RECIPROCITY_PCT__</b><span>of directed edges are returned by the opposite edge</span></div>
        <div class="metric"><b>__LARGEST_WEAK_PCT__</b><span>of people sit in the largest weak component</span></div>
      </div>

      <h2>Then ask whether arrows come back</h2>
      <p>Reciprocity checks whether following is mutual. Count an edge <span class="term" data-term="edge" tabindex="0">u → v</span> as reciprocated when <span class="term" data-term="v" tabindex="0">v</span> also follows <span class="term" data-term="u" tabindex="0">u</span>.</p>
      <div class="math"><span class="term" data-term="reciprocity" tabindex="0">r</span> = <span class="frac"><span>|{(<span class="term" data-term="u" tabindex="0">u</span>,<span class="term" data-term="v" tabindex="0">v</span>) : <span class="term" data-term="Auv" tabindex="0">A<sub>uv</sub></span> = <span class="term" data-term="Avu" tabindex="0">A<sub>vu</sub></span> = 1}|</span><span><span class="term" data-term="m" tabindex="0">m</span></span></span></div>
      <p>Here, <b>__RECIPROCAL_EDGES__</b> directed edges are reciprocated. That is <b>__RECIPROCITY_PCT__</b> of the edge list.</p>

      <h2>Components say whether direction matters</h2>
      <p>A weak component ignores arrow direction. A strong component keeps direction and requires a directed path both ways. The strong-component computation is a direct graph traversal problem; Tarjan gives a linear-time version <a class="cite" href="https://doi.org/10.1137/0201010" target="_blank" rel="noreferrer" title="Gives a linear-time algorithm for strongly connected components.">Tarjan 1972</a>.</p>
      <table>
        <tr><th>component measure</th><th>value in this scrape</th><th>what it says</th></tr>
        <tr><td>weak components</td><td>__WEAK_COMPONENTS__</td><td>How many islands remain if follows are treated as undirected ties.</td></tr>
        <tr><td>largest weak component</td><td>__LARGEST_WEAK__ people</td><td>The main island visible at the center of the graph page.</td></tr>
        <tr><td>strong components</td><td>__STRONG_COMPONENTS__</td><td>How many groups have directed paths both ways.</td></tr>
        <tr><td>largest strong component</td><td>__LARGEST_STRONG__ people</td><td>The largest directed group where a walk can return.</td></tr>
      </table>

      <h2>Ranking adds one walking reader</h2>
      <p>PageRank imagines a reader who usually follows an outgoing edge and sometimes jumps anywhere. A person scores high when other high-scoring people follow them. People with no outgoing follows are treated as jumps in the generated numbers. The original paper defines the recursive score for web links <a class="cite" href="http://ilpubs.stanford.edu:8090/422/1/1999-66.pdf" target="_blank" rel="noreferrer" title="Defines PageRank as a recursive score passed through links.">Page, Brin, Motwani, and Winograd 1999</a>.</p>
      <div class="math"><span class="term" data-term="pr" tabindex="0">p(v)</span> = <span class="frac"><span>1 − <span class="term" data-term="alpha" tabindex="0">α</span></span><span><span class="term" data-term="n" tabindex="0">n</span></span></span> + <span class="term" data-term="alpha" tabindex="0">α</span> <span class="term" data-term="sum" tabindex="0">∑<sub>u→v</sub></span> <span class="frac"><span><span class="term" data-term="pru" tabindex="0">p(u)</span></span><span><span class="term" data-term="dout" tabindex="0">d<sup>out</sup>(u)</span></span></span></div>
      <table class="rank-table">
        <tr><th></th><th>highest PageRank</th><th>followers</th><th>following</th><th>PageRank</th></tr>
        __PAGERANK_ROWS__
      </table>

      <h2>Local closure asks whether neighbors know each other</h2>
      <p>Clustering uses the undirected projection of the follower graph: ignore arrow direction, keep each tie once, and ask how many possible neighbor-neighbor ties are present. Watts and Strogatz use clustering with path length to describe small-world structure <a class="cite" href="https://doi.org/10.1038/30918" target="_blank" rel="noreferrer" title="Uses clustering and path length to describe small-world networks.">Watts and Strogatz 1998</a>.</p>
      <div class="math"><span class="term" data-term="clustering" tabindex="0">C<sub>v</sub></span> = <span class="frac"><span>2<span class="term" data-term="ev" tabindex="0">e<sub>v</sub></span></span><span><span class="term" data-term="kv" tabindex="0">k<sub>v</sub></span>(<span class="term" data-term="kv" tabindex="0">k<sub>v</sub></span> − 1)</span></span></div>
      <p>The mean local clustering among people with at least two undirected neighbors is <b>__CLUSTERING__</b>. The transitivity ratio across all centered triples is <b>__TRANSITIVITY__</b>.</p>

      <h2>The dense middle is a core</h2>
      <p>A k-core peels away people with fewer than k neighbors in the undirected projection, then repeats. The largest k that keeps a person is that person's core number. A linear-time peeling algorithm is described by Batagelj and Zaversnik <a class="cite" href="https://arxiv.org/abs/cs/0310049" target="_blank" rel="noreferrer" title="Describes fast core decomposition by repeatedly removing low-degree nodes.">2003</a>.</p>
      <table class="rank-table">
        <tr><th></th><th>highest follower counts</th><th>followers</th><th>following</th><th>core</th></tr>
        __FOLLOWER_ROWS__
      </table>
      <p>The maximum core number is <b>__MAX_CORE__</b>. <b>__MAX_CORE_COUNT__</b> people sit in that innermost shell.</p>

      <h2>References</h2>
      <ol class="references">
        <li>Newman, M. E. J. “The Structure and Function of Complex Networks.” Reviews degree, components, and clustering.</li>
        <li>Tarjan, R. E. “Depth-First Search and Linear Graph Algorithms.” Gives strong-component traversal.</li>
        <li>Page, L., Brin, S., Motwani, R., Winograd, T. “The PageRank Citation Ranking.” Defines recursive link ranking.</li>
        <li>Watts, D. J., Strogatz, S. H. “Collective dynamics of small-world networks.” Uses clustering with path length.</li>
        <li>Batagelj, V., Zaversnik, M. “An O(m) Algorithm for Cores Decomposition of Networks.” Gives core peeling.</li>
      </ol>
    </main>
    <aside class="side">
      <section class="model sheet">
        <h2>Small model</h2>
        <p>Use the same definitions on six people. The diagram changes only the marks needed for the selected metric.</p>
        <div class="model-controls">
          <label>Show on diagram <select id="toy-mode"><option value="degree">degree</option><option value="reciprocity">reciprocity</option><option value="components">components</option><option value="pagerank">PageRank</option><option value="clustering">clustering</option></select></label>
          <label id="alpha-control" hidden>PageRank α <input id="alpha" type="range" min="0" max="0.95" step="0.01" value="0.85"></label>
        </div>
        <svg id="toy" viewBox="0 0 330 250" role="img" aria-label="Small directed graph model"></svg>
        <p id="toy-note" class="diagram-note"></p>
      </section>
      <section class="numbers sheet">
        <h2>Actual graph in one breath</h2>
        <p><b>__NODES__</b> people, <b>__EDGES__</b> follows, <b>__WEAK_COMPONENTS__</b> weak components, and a largest weak component containing <b>__LARGEST_WEAK__</b> people.</p>
      </section>
      <section class="glossary sheet">
        <h2>Glossary</h2>
        <ul id="glossary"></ul>
      </section>
    </aside>
  </div>
</div>
<section id="definition-card" class="definition-card sheet" aria-live="polite"><button id="close-def" type="button">Close</button><h3 id="def-title"></h3><p id="def-body"></p></section>
<script id="metrics-data" type="application/json">__METRICS_JSON__</script>
<script>
(() => {
  "use strict";
  const data = JSON.parse(document.getElementById("metrics-data").textContent);
  const definitions = {
    edge: ["edge u → v", "One stored follow relation. The arrow starts at the follower and points to the person being followed."],
    u: ["u", "A source person in a directed edge; in this graph, the follower."],
    v: ["v", "A target person in a directed edge; in this graph, the person being followed."],
    A: ["A", "The adjacency matrix. A cell records whether one person follows another."],
    Auv: ["Auv", "Auv is 1 when u follows v, and 0 when that directed edge is absent."],
    Avu: ["Avu", "Avu is 1 when v follows u. It is the return edge for u → v."],
    Avw: ["Avw", "Avw is 1 when v follows w. Summing these cells counts outgoing follows."],
    din: ["d-in(v)", "Incoming degree: how many observed followers v has."],
    dout: ["d-out(v)", "Outgoing degree: how many people v follows."],
    sum: ["Σ", "Add the quantity over every person in the indicated set."],
    density: ["ρ", "Density: the observed edge count divided by every possible directed edge between distinct people, excluding self-follows."],
    m: ["m", "The number of directed follow edges in the scrape."],
    n: ["n", "The number of people in the scrape."],
    reciprocity: ["r", "Reciprocity: the fraction of directed edges whose opposite edge also exists."],
    pr: ["p(v)", "PageRank share for person v. More share means more walking-reader mass reaches v through incoming follows."],
    pru: ["p(u)", "PageRank share currently held by a person who follows v."],
    alpha: ["α", "Damping factor. Larger α makes the walking reader follow graph edges more often and jump less often."],
    clustering: ["Cv", "Local clustering for v after ignoring arrow direction."],
    ev: ["ev", "The number of observed ties among v's neighbors."],
    kv: ["kv", "The number of distinct undirected neighbors of v."]
  };
  const card = document.getElementById("definition-card");
  const defTitle = document.getElementById("def-title");
  const defBody = document.getElementById("def-body");
  function showDef(key) {
    const value = definitions[key];
    if (!value) return;
    defTitle.textContent = value[0];
    defBody.textContent = value[1];
    card.setAttribute("open", "");
    document.querySelectorAll("[data-term]").forEach(el => el.toggleAttribute("data-active", el.dataset.term === key));
  }
  document.querySelectorAll(".term").forEach(el => {
    const value = definitions[el.dataset.term];
    if (!value) return;
    el.title = value[1];
    el.addEventListener("click", () => showDef(el.dataset.term));
    el.addEventListener("keydown", ev => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); showDef(el.dataset.term); } });
  });
  document.getElementById("close-def").addEventListener("click", () => card.removeAttribute("open"));
  const glossary = document.getElementById("glossary");
  Object.entries(definitions).forEach(([key, [title, body]]) => {
    const li = document.createElement("li");
    li.innerHTML = `<button type="button" data-key="${key}">${title}</button> ${body}`;
    li.querySelector("button").addEventListener("click", () => showDef(key));
    glossary.append(li);
  });

  const toyNodes = [
    {id:"Ada", x:70, y:72}, {id:"Grace", x:166, y:48}, {id:"Alan", x:254, y:88},
    {id:"Katherine", x:96, y:178}, {id:"Mina", x:200, y:178}, {id:"Sofia", x:278, y:178}
  ];
  const toyEdges = [["Ada","Grace"],["Ada","Alan"],["Grace","Alan"],["Alan","Ada"],["Katherine","Alan"],["Mina","Katherine"],["Katherine","Mina"],["Sofia","Mina"]];
  const byToy = new Map(toyNodes.map(n => [n.id, n]));
  const svg = document.getElementById("toy");
  const alpha = document.getElementById("alpha");
  const alphaControl = document.getElementById("alpha-control");
  const toyMode = document.getElementById("toy-mode");
  const toyNote = document.getElementById("toy-note");
  function prScores(a) {
    const out = new Map(toyNodes.map(n => [n.id, []]));
    const incoming = new Map(toyNodes.map(n => [n.id, []]));
    toyEdges.forEach(([u, v]) => { out.get(u).push(v); incoming.get(v).push(u); });
    let rank = new Map(toyNodes.map(n => [n.id, 1 / toyNodes.length]));
    for (let i = 0; i < 40; i++) {
      const dangling = toyNodes.filter(n => !out.get(n.id).length).reduce((s, n) => s + rank.get(n.id), 0);
      const next = new Map(toyNodes.map(n => [n.id, (1 - a) / toyNodes.length + a * dangling / toyNodes.length]));
      for (const n of toyNodes) {
        const outs = out.get(n.id);
        if (!outs.length) continue;
        const share = a * rank.get(n.id) / outs.length;
        outs.forEach(v => next.set(v, next.get(v) + share));
      }
      rank = next;
    }
    return rank;
  }
  function drawToy() {
    const mode = toyMode.value;
    alphaControl.hidden = mode !== "pagerank";
    const scores = prScores(Number(alpha.value));
    const mutual = new Set(toyEdges.filter(([u, v]) => toyEdges.some(([a, b]) => a === v && b === u)).map(([u, v]) => `${u}>${v}`));
    svg.innerHTML = `<defs><marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#8d7d68"></path></marker></defs>`;
    if (mode === "components") {
      const bg = document.createElementNS("http://www.w3.org/2000/svg", "path");
      bg.setAttribute("d", "M36 40 C120 5 245 8 300 70 C326 132 260 222 140 226 C50 222 20 120 36 40 Z");
      bg.setAttribute("fill", "rgba(47,99,183,.08)");
      bg.setAttribute("stroke", "rgba(47,99,183,.35)");
      svg.append(bg);
    }
    for (const [u, v] of toyEdges) {
      const a = byToy.get(u), b = byToy.get(v);
      const dx = b.x - a.x, dy = b.y - a.y, len = Math.hypot(dx, dy);
      const sx = a.x + dx / len * 17, sy = a.y + dy / len * 17;
      const ex = b.x - dx / len * 19, ey = b.y - dy / len * 19;
      const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
      line.setAttribute("x1", sx); line.setAttribute("y1", sy); line.setAttribute("x2", ex); line.setAttribute("y2", ey);
      line.setAttribute("marker-end", "url(#arrow)");
      line.setAttribute("class", `edge ${mode === "reciprocity" && mutual.has(`${u}>${v}`) ? "active" : ""}`);
      svg.append(line);
    }
    if (mode === "clustering") {
      const tri = document.createElementNS("http://www.w3.org/2000/svg", "path");
      tri.setAttribute("d", "M70 72 L166 48 L254 88 Z");
      tri.setAttribute("fill", "rgba(183,77,47,.12)");
      tri.setAttribute("stroke", "rgba(183,77,47,.45)");
      svg.insertBefore(tri, svg.children[1]);
    }
    for (const n of toyNodes) {
      const score = scores.get(n.id);
      const r = mode === "pagerank" ? 14 + score * 55 : 18;
      const c = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      c.setAttribute("cx", n.x); c.setAttribute("cy", n.y); c.setAttribute("r", r.toFixed(1));
      c.setAttribute("fill", mode === "pagerank" ? "#b74d2f" : mode === "reciprocity" && ["Katherine","Mina"].includes(n.id) ? "#7047a8" : "#2f63b7");
      c.setAttribute("class", "toy-node");
      svg.append(c);
      const labelOffsets = {Grace: [0, -12], Alan: [8, 5], Katherine: [0, 5], Mina: [0, 5], Sofia: [0, 5], Ada: [0, 5]};
      const [dx, dy] = labelOffsets[n.id] || [0, 5];
      const t = document.createElementNS("http://www.w3.org/2000/svg", "text");
      t.setAttribute("x", n.x + dx); t.setAttribute("y", n.y + (dy < 0 ? -r + dy : r + 15 + dy)); t.setAttribute("text-anchor", "middle"); t.setAttribute("class", "node-label");
      t.textContent = mode === "pagerank" ? `${n.id} ${(score * 100).toFixed(1)}` : n.id;
      svg.append(t);
    }
    const alphaText = Number(alpha.value).toFixed(2);
    const top = [...scores.entries()].sort((a, b) => b[1] - a[1])[0];
    toyNote.textContent = {
      degree: "Alan has three incoming arrows in the toy graph, so degree alone points to Alan first.",
      reciprocity: "The Katherine ↔ Mina pair is mutual: each directed edge has a return edge.",
      components: "Ignoring arrow direction puts all six people in one weak component.",
      pagerank: `With α = ${alphaText}, ${top[0]} receives the most walking-reader mass in the toy graph.`,
      clustering: "The shaded triangle shows neighbor closure: Ada, Grace, and Alan are tied around the same small neighborhood."
    }[mode];
  }
  toyMode.addEventListener("change", drawToy);
  alpha.addEventListener("input", () => { toyMode.value = "pagerank"; drawToy(); });
  drawToy();
})();
</script>
</body>
</html>
"""


ALGORITHMS_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Curius graph algorithms</title>
<style>
__PAPER_CSS__
  .article { display: grid; grid-template-columns: minmax(0, 1fr) minmax(280px, 360px); gap: 2rem; align-items: start; }
  .workbench { position: sticky; top: 14px; padding: 1rem; }
  .workbench .controls { gap: .6rem; }
  .row { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: .6rem; }
  .workbench label { min-width: 0; }
  .workbench input, .workbench select, .workbench button { width: 100%; }
  .result { margin-top: .8rem; padding-top: .7rem; border-top: 1px solid var(--rule); }
  .pill-list { display: flex; flex-wrap: wrap; gap: .35rem; margin: .5rem 0; }
  .pill { border: 1px solid var(--rule); border-radius: 999px; padding: .2rem .55rem; background: rgba(255,250,240,.78); }
  .metric-list { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: .75rem; margin: 1rem 0; }
  .metric { padding: .8rem; border-top: 1px solid var(--rule); background: rgba(255,250,240,.58); }
  .metric b { display: block; font-size: 1.45rem; font-weight: 500; line-height: 1.05; }
  .metric span { color: var(--muted); font-size: .96rem; }
  .rank-table td:first-child { width: 2rem; color: var(--muted); }
  .rank-table td, .rank-table th { font-size: .94rem; }
  .references { padding-left: 1.1rem; }
  .references li { margin: .45rem 0; }
  .definition-card h3 { margin-top: 0; }
  @media (max-width: 900px) {
    .article { display: flex; flex-direction: column; }
    .workbench { position: static; order: -1; }
    .metric-list, .row { grid-template-columns: 1fr; }
  }
</style>
</head>
<body>
<div class="page">
  <nav class="nav"><a href="__FRONTPAGE_INDEX_URL__">Curius front page</a><a href="index.html">Explore the graph</a><a href="metrics.html">Read the first metrics page</a><a href="questions.html">Next questions</a></nav>
  <h1>More graph algorithms for this follower graph</h1>
  <div class="article">
    <main>
      <p>The follower graph is not just a picture. It is a set of procedures we can run: walk from one person to another, find the dense middle, separate hubs from authorities, and suggest missing follows. Each procedure below keeps the same edge direction: <span class="term" data-term="edge" tabindex="0">u → v</span> means <span class="term" data-term="u" tabindex="0">u</span> follows <span class="term" data-term="v" tabindex="0">v</span>.</p>

      <h2>1. Reachability: can one person get to another?</h2>
      <p>Breadth-first search starts at one person, visits all neighbors one step away, then two steps away, and stops when it reaches the target. With unweighted edges, the first time BFS reaches a target is a shortest path <a class="cite" href="https://mitpress.mit.edu/9780262046305/introduction-to-algorithms/" target="_blank" rel="noreferrer" title="Gives the standard queue-based BFS shortest-path algorithm for unweighted graphs.">Cormen et al.</a>.</p>
      <div class="math"><span class="term" data-term="distance" tabindex="0">d(s,t)</span> = min |<span class="term" data-term="path" tabindex="0">path</span>| <span class="quiet">over paths from</span> <span class="term" data-term="source" tabindex="0">s</span> <span class="quiet">to</span> <span class="term" data-term="target" tabindex="0">t</span></div>
      <p>On the largest weak component, exact all-source BFS gives an average undirected distance of <b>__PATH_AVG__</b>, a 90th-percentile distance of <b>__PATH_P90__</b>, and a diameter of <b>__PATH_DIAM__</b>. Those values come from <b>__PATH_PAIRS__</b> reachable pairs inside the main island.</p>
      <p>Use the workbench to try one directed path and one undirected path. Directed paths answer “can attention flow through follows?” Undirected paths answer “are these people in the same social island?”</p>

      <h2>2. Bow-tie reachability: what can reach the core?</h2>
      <p>A strong component keeps arrow direction and requires a path both ways. The largest strong component acts like a directed knot: everyone inside can reach everyone else by following arrows. Web-graph studies often describe this as a bow tie: an <span class="term" data-term="in" tabindex="0">IN</span> side can reach the knot, an <span class="term" data-term="out" tabindex="0">OUT</span> side can be reached from it, and tendrils hang off the sides <a class="cite" href="https://doi.org/10.1016/S1389-1286(00)00083-9" target="_blank" rel="noreferrer" title="Introduces the bow-tie view of directed web reachability.">Broder et al. 2000</a>.</p>
      <div class="metric-list">
        <div class="metric"><b>__SCC__</b><span>people in the largest strong component</span></div>
        <div class="metric"><b>__IN_SCC__</b><span>people that can reach that component</span></div>
        <div class="metric"><b>__OUT_SCC__</b><span>people reachable from that component</span></div>
        <div class="metric"><b>__TENDRILS__</b><span>people outside those directed regions</span></div>
        <div class="metric"><b>__LARGEST_WEAK__</b><span>people in the largest weak component</span></div>
        <div class="metric"><b>__WEAK_COMPONENTS__</b><span>weak components total</span></div>
      </div>

      <h2>3. HITS separates hubs from authorities</h2>
      <p>PageRank gives each person one score. HITS gives two. A good <span class="term" data-term="hub" tabindex="0">hub</span> follows many good <span class="term" data-term="authority" tabindex="0">authorities</span>; a good authority is followed by many good hubs. Kleinberg used this mutual update for link analysis <a class="cite" href="https://doi.org/10.1145/324133.324140" target="_blank" rel="noreferrer" title="Defines HITS hub and authority scores by repeated mutual updates.">Kleinberg 1999</a>.</p>
      <div class="math"><span class="term" data-term="authority" tabindex="0">a(v)</span> = <span class="term" data-term="sum" tabindex="0">∑<sub>u→v</sub></span> <span class="term" data-term="hub" tabindex="0">h(u)</span><span aria-hidden="true">,&nbsp;&nbsp;</span><span class="term" data-term="hub" tabindex="0">h(u)</span> = <span class="term" data-term="sum" tabindex="0">∑<sub>u→v</sub></span> <span class="term" data-term="authority" tabindex="0">a(v)</span></div>
      <table class="rank-table">
        <tr><th></th><th>top authorities</th><th>followers</th><th>authority</th></tr>
        __AUTHORITY_ROWS__
      </table>
      <table class="rank-table">
        <tr><th></th><th>top hubs</th><th>following</th><th>hub</th></tr>
        __HUB_ROWS__
      </table>

      <h2>4. Link prediction suggests missing follows</h2>
      <p>A simple recommender asks: “Who is followed by the people I follow?” This is the directed version of common-neighbor link prediction. More elaborate variants weight rare shared neighbors more strongly, but the plain count is a good first check <a class="cite" href="https://doi.org/10.1002/asi.20591" target="_blank" rel="noreferrer" title="Surveys link-prediction scores such as common neighbors and Adamic–Adar.">Liben-Nowell and Kleinberg 2007</a>.</p>
      <div class="math"><span class="term" data-term="score" tabindex="0">score(s,c)</span> = |{<span class="term" data-term="middle" tabindex="0">x</span> : <span class="term" data-term="source" tabindex="0">s</span> → <span class="term" data-term="middle" tabindex="0">x</span> ∧ <span class="term" data-term="middle" tabindex="0">x</span> → <span class="term" data-term="candidate" tabindex="0">c</span>}|</div>
      <p>The workbench computes this score in the browser. It removes people already followed by the source and ranks the remaining candidates by shared outgoing neighborhoods.</p>

      <h2>5. Homophily checks whether metadata groups mix</h2>
      <p>If a profile lists a school, we can ask whether follow edges connect people from the same school more often than a random edge endpoint would. This is a homophily question: similar people forming more ties than chance would predict <a class="cite" href="https://doi.org/10.1146/annurev.soc.27.1.415" target="_blank" rel="noreferrer" title="Reviews homophily as similarity in social ties.">McPherson, Smith-Lovin, and Cook 2001</a>.</p>
      <div class="math"><span class="term" data-term="homophily" tabindex="0">H</span> = <span class="frac"><span><span class="term" data-term="same" tabindex="0">same-school edges</span></span><span><span class="term" data-term="known" tabindex="0">edges with both schools known</span></span></span></div>
      <p>Among <b>__SCHOOL_KNOWN__</b> edges where both endpoints list a school, <b>__SCHOOL_SAME_PCT__</b> connect the same school. The endpoint-frequency baseline is <b>__SCHOOL_EXPECTED_PCT__</b>.</p>

      <h2>What I would apply next</h2>
      <table>
        <tr><th>question</th><th>algorithm</th><th>why it fits this graph</th></tr>
        <tr><td>Who bridges separate islands?</td><td>Betweenness on the largest weak component</td><td>It finds people sitting on many shortest paths, but exact all-pairs scoring is heavier than this static build needs.</td></tr>
        <tr><td>Which follows look surprising?</td><td>Link prediction residuals</td><td>Compare observed follows against common-neighbor scores and inspect high-score missing edges.</td></tr>
        <tr><td>Where are coherent communities?</td><td>Modularity or Leiden/Louvain</td><td>Useful on the giant component; it needs a real community package, so this page stops at components and cores.</td></tr>
        <tr><td>How do interests travel?</td><td>Random walks over follows plus saved-link topics</td><td>The database has saved links and highlights, so graph paths can be connected to reading behavior.</td></tr>
      </table>

      <h2>References</h2>
      <ol class="references">
        <li>Cormen, Leiserson, Rivest, and Stein. <i>Introduction to Algorithms</i>. Gives queue-based BFS for unweighted shortest paths.</li>
        <li>Broder et al. “Graph structure in the web.” Introduces directed bow-tie reachability.</li>
        <li>Kleinberg. “Authoritative Sources in a Hyperlinked Environment.” Defines HITS hubs and authorities.</li>
        <li>Liben-Nowell and Kleinberg. “The Link-Prediction Problem for Social Networks.” Surveys common-neighbor recommendation scores.</li>
        <li>McPherson, Smith-Lovin, and Cook. “Birds of a Feather.” Reviews homophily in social ties.</li>
      </ol>
    </main>
    <aside class="workbench sheet">
      <h2>Graph workbench</h2>
      <p>Pick people by handle. The page runs BFS and two-hop recommendations locally.</p>
      <div class="controls">
        <div class="row">
          <label>From <input id="from" autocomplete="off" placeholder="anson-yu"></label>
          <label>To <input id="to" autocomplete="off" placeholder="vincent-huang"></label>
        </div>
        <label>Path type <select id="path-type"><option value="directed">directed follows</option><option value="undirected">ignore direction</option></select></label>
        <button id="find-path" type="button">Find path</button>
        <button id="recommend" type="button">Recommend follows</button>
      </div>
      <div id="workbench-result" class="result quiet">Try a path or recommendation.</div>
    </aside>
  </div>
</div>
<section id="definition-card" class="definition-card sheet" aria-live="polite"><button id="close-def" type="button">Close</button><h3 id="def-title"></h3><p id="def-body"></p></section>
<script id="algorithms-data" type="application/json">__ALGORITHMS_JSON__</script>
<script>
(() => {
  "use strict";
  const raw = JSON.parse(document.getElementById("algorithms-data").textContent);
  const nodes = raw.nodes;
  const byId = new Map(nodes.map(n => [n.id, n]));
  const bySlug = new Map(nodes.map(n => [n.slug.toLowerCase(), n]));
  const outgoing = new Map(nodes.map(n => [n.id, []]));
  const incoming = new Map(nodes.map(n => [n.id, []]));
  const undirected = new Map(nodes.map(n => [n.id, []]));
  const follows = new Set(raw.edges.map(([a, b]) => `${a}>${b}`));
  for (const [a, b] of raw.edges) {
    outgoing.get(a)?.push(b); incoming.get(b)?.push(a);
    undirected.get(a)?.push(b); undirected.get(b)?.push(a);
  }
  const definitions = {
    edge: ["u → v", "A directed follow edge: u follows v."],
    u: ["u", "The source person in an edge; the follower."],
    v: ["v", "The target person in an edge; the person being followed."],
    distance: ["d(s,t)", "The number of edges in the shortest path from source s to target t."],
    path: ["path", "A sequence of people connected by follow edges."],
    source: ["s", "The person where a traversal starts."],
    target: ["t", "The person a traversal tries to reach."],
    in: ["IN", "People that can reach the largest strong component but are not inside it."],
    out: ["OUT", "People reachable from the largest strong component but not inside it."],
    hub: ["hub h(u)", "A person who follows many high-authority people."],
    authority: ["authority a(v)", "A person followed by high-hub people."],
    sum: ["Σ", "Add the scores over the indicated incoming or outgoing edges."],
    score: ["score(s,c)", "A recommendation score for source s and candidate c."],
    middle: ["x", "A middle person followed by the source who also follows the candidate."],
    candidate: ["c", "A person not yet followed by the source."],
    homophily: ["H", "The share of known-school edges that connect the same school."],
    same: ["same-school edges", "Edges where both endpoints list the same school."],
    known: ["known-school edges", "Edges where both endpoints list a non-empty school."]
  };
  const card = document.getElementById("definition-card");
  function showDef(key) {
    const value = definitions[key];
    if (!value) return;
    document.getElementById("def-title").textContent = value[0];
    document.getElementById("def-body").textContent = value[1];
    card.setAttribute("open", "");
  }
  document.querySelectorAll(".term").forEach(el => {
    const value = definitions[el.dataset.term];
    if (!value) return;
    el.title = value[1];
    el.addEventListener("click", () => showDef(el.dataset.term));
    el.addEventListener("keydown", ev => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); showDef(el.dataset.term); } });
  });
  document.getElementById("close-def").addEventListener("click", () => card.removeAttribute("open"));
  function person(value) {
    const q = value.trim().toLowerCase();
    if (!q) return null;
    return bySlug.get(q) || nodes.find(n => `${n.name} ${n.slug} ${n.school || ""}`.toLowerCase().includes(q)) || null;
  }
  function label(n) { return n.name && n.name !== n.slug ? `${n.name} (${n.slug})` : n.slug; }
  function bfs(start, goal, neighbors) {
    const seen = new Set([start]);
    const parent = new Map();
    const queue = [start];
    for (let head = 0; head < queue.length; head++) {
      const node = queue[head];
      if (node === goal) break;
      for (const next of neighbors.get(node) || []) {
        if (seen.has(next)) continue;
        seen.add(next); parent.set(next, node); queue.push(next);
        if (next === goal) break;
      }
    }
    if (!seen.has(goal)) return null;
    const path = [goal];
    while (path[path.length - 1] !== start) path.push(parent.get(path[path.length - 1]));
    return path.reverse();
  }
  function setResult(html) { document.getElementById("workbench-result").innerHTML = html; }
  document.getElementById("find-path").addEventListener("click", () => {
    const s = person(document.getElementById("from").value);
    const t = person(document.getElementById("to").value);
    if (!s || !t) { setResult("I could not find one of those people."); return; }
    const neighbors = document.getElementById("path-type").value === "directed" ? outgoing : undirected;
    const path = bfs(s.id, t.id, neighbors);
    if (!path) { setResult(`No ${document.getElementById("path-type").value} path found from ${label(s)} to ${label(t)}.`); return; }
    setResult(`<b>${path.length - 1} step path</b><div class="pill-list">${path.map(id => `<span class="pill">${label(byId.get(id))}</span>`).join(" → ")}</div>`);
  });
  document.getElementById("recommend").addEventListener("click", () => {
    const s = person(document.getElementById("from").value);
    if (!s) { setResult("Pick a source person first."); return; }
    const already = new Set(outgoing.get(s.id) || []);
    const scores = new Map();
    for (const mid of already) {
      for (const cand of outgoing.get(mid) || []) {
        if (cand === s.id || already.has(cand)) continue;
        scores.set(cand, (scores.get(cand) || 0) + 1);
      }
    }
    const ranked = [...scores.entries()].sort((a, b) => b[1] - a[1] || (byId.get(b[0])?.in || 0) - (byId.get(a[0])?.in || 0)).slice(0, 10);
    if (!ranked.length) { setResult(`No two-hop suggestions for ${label(s)}.`); return; }
    setResult(`<b>Two-hop suggestions for ${label(s)}</b><div class="pill-list">${ranked.map(([id, score]) => `<span class="pill">${label(byId.get(id))}: ${score}</span>`).join("")}</div>`);
  });
  const first = nodes[0], second = nodes[1];
  if (first) document.getElementById("from").value = first.slug;
  if (second) document.getElementById("to").value = second.slug;
})();
</script>
</body>
</html>
"""


NEXT_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Curius next graph questions</title>
<style>
__PAPER_CSS__
  .article { display: grid; grid-template-columns: minmax(0, 1fr) minmax(260px, 340px); gap: 2rem; align-items: start; }
  .article > main { min-width: 0; }
  .side { position: sticky; top: 14px; padding: 1rem; }
  .question-table td:first-child { font-weight: 500; width: 24%; }
  .question-table td:nth-child(2) { width: 28%; }
  .answer-table td:first-child { width: 2rem; color: var(--muted); }
  .answer-table td, .answer-table th { font-size: .94rem; }
  .answer-line { border-left: 3px solid var(--rule); padding: .65rem .9rem; background: rgba(255,250,240,.62); }
  .plan { display: grid; gap: 1rem; margin: 1rem 0; }
  .plan section { padding: 1rem; border-left: 3px solid var(--rule); background: rgba(255,250,240,.55); }
  .plan h2 { margin-top: 0; }
  .tag { display: inline-block; border: 1px solid var(--rule); border-radius: 999px; padding: .08rem .5rem; margin: .15rem .2rem .15rem 0; color: var(--muted); }
  .small { font-size: .95rem; }
  .references { padding-left: 1.1rem; }
  .references li { margin: .45rem 0; }
  @media (max-width: 900px) {
    .article { display: flex; flex-direction: column; }
    .article > main, .plan, .plan section { width: 100%; max-width: 100%; min-width: 0; }
    .side { position: static; }
    .question-table, .question-table tbody, .question-table tr, .question-table td, .question-table th { display: block; width: 100%; max-width: 100%; }
    .question-table th { display: none; }
    .question-table td { border-bottom: 0; padding: .25rem 0; }
    .question-table tr { border-bottom: 1px solid var(--rule); padding: .7rem 0; }
    .question-table td::before { display: block; color: var(--muted); font-size: .88rem; }
    .question-table td:nth-child(1)::before { content: "question"; }
    .question-table td:nth-child(2)::before { content: "algorithm"; }
    .question-table td:first-child, .question-table td:nth-child(2), .question-table td:nth-child(3) { width: 100%; }
    .question-table td:nth-child(3)::before { content: "why it fits"; }
    .answer-table { display: block; overflow-x: auto; }
  }
</style>
</head>
<body>
<div class="page">
  <nav class="nav"><a href="__FRONTPAGE_INDEX_URL__">Curius front page</a><a href="index.html">Explore the graph</a><a href="metrics.html">Read metrics</a><a href="algorithms.html">Read algorithms</a></nav>
  <h1>Four next questions for the follower graph</h1>
  <div class="article">
    <main>
      <p>This page answers the four follow-up questions with the data we have now. The answers are still inspectable: sampled betweenness for bridges, two-hop residuals for follows, Louvain modularity for communities, and saved-link domains as lightweight interest topics.</p>

      <table class="question-table">
        <tr><th>question</th><th>algorithm</th><th>why it fits this graph</th></tr>
        <tr><td>Who bridges separate islands?</td><td>Betweenness on the largest weak component</td><td>It finds people sitting on many shortest paths, but exact all-pairs scoring is heavier than this static build needs.</td></tr>
        <tr><td>Which follows look surprising?</td><td>Link prediction residuals</td><td>Compare observed follows against common-neighbor scores and inspect high-score missing edges.</td></tr>
        <tr><td>Where are coherent communities?</td><td>Modularity or Leiden/Louvain</td><td>Useful on the giant component; it needs a real community package, so this page stops at components and cores.</td></tr>
        <tr><td>How do interests travel?</td><td>Random walks over follows plus saved-link topics</td><td>The database has saved links and highlights, so graph paths can be connected to reading behavior.</td></tr>
      </table>

      <div class="plan">
        <section>
          <h2>Who bridges separate islands?</h2>
          <p class="answer-line">The strongest bridge in the sampled run is <b>__BRIDGE_TOP__</b> with sampled betweenness <b>__BRIDGE_SCORE__</b>. These are people whose neighborhoods sit on many shortest routes through the largest weak component.</p>
          <p>For a person v, betweenness counts how often shortest paths between other people pass through v. Brandes gives a faster exact algorithm, but this page uses 256 deterministic BFS sources to keep the build light <a class="cite" href="https://doi.org/10.1080/0022250X.2001.9990249" target="_blank" rel="noreferrer" title="Gives the standard faster exact betweenness-centrality algorithm.">Brandes 2001</a>.</p>
          <table class="answer-table"><tr><th></th><th>bridge candidate</th><th>sampled score</th><th>followers</th><th>core</th></tr>__BRIDGE_ROWS__</table>
        </section>
        <section>
          <h2>Which follows look surprising?</h2>
          <p class="answer-line">The highest-scoring missing follow is <b>__MISSING_TOP__</b>. It appears repeatedly in two-hop neighborhoods but is not an observed follow edge.</p>
          <p>Common-neighbor scores predict a follow when people share outgoing neighborhoods. A residual asks what the score missed: high-score missing follows are plausible recommendations; low-support existing follows are unusual edges worth reading manually <a class="cite" href="https://doi.org/10.1002/asi.20591" target="_blank" rel="noreferrer" title="Surveys common-neighbor and related link-prediction scores.">Liben-Nowell and Kleinberg 2007</a>.</p>
          <h3>High-score missing follows</h3>
          <table class="answer-table"><tr><th></th><th>source</th><th>candidate</th><th>two-hop score</th><th>candidate followers</th></tr>__MISSING_ROWS__</table>
          <h3>Low-support existing follows</h3>
          <table class="answer-table"><tr><th></th><th>source</th><th>target</th><th>two-hop support</th><th>source following → target followers</th></tr>__SURPRISING_ROWS__</table>
        </section>
        <section>
          <h2>Where are coherent communities?</h2>
          <p class="answer-line">Louvain finds <b>__COMMUNITY_COUNT__</b> communities inside the largest weak component, with modularity <b>__MODULARITY__</b>. The largest groups are mostly separated by follow structure, not by school metadata, because most listed schools are McGill.</p>
          <p>Modularity methods search for groups with more internal edges than a random graph with similar degrees would expect. Louvain is a common greedy version; Leiden improves badly connected communities <a class="cite" href="https://doi.org/10.1038/s41598-019-41695-z" target="_blank" rel="noreferrer" title="Describes Leiden as a community-detection method that improves Louvain partitions.">Traag, Waltman, and van Eck 2019</a>.</p>
          <table class="answer-table"><tr><th>group</th><th>people</th><th>visible names</th><th>top saved-link domains</th><th>school signal</th></tr>__COMMUNITY_ROWS__</table>
        </section>
        <section>
          <h2>How do interests travel?</h2>
          <p class="answer-line">Among <b>__INTEREST_KNOWN__</b> follow edges where both people have saved-link domains, <b>__INTEREST_OVERLAP__</b> share at least one domain. The graph carries broad reading channels more than narrow topics.</p>
          <p>Random walks can mix follows with saved-link topics: start at a person, walk along follows, and occasionally jump to a saved link or highlighted source. Personalized PageRank is one way to keep the walk near a starting person while still letting it explore <a class="cite" href="https://doi.org/10.1145/775047.775126" target="_blank" rel="noreferrer" title="Uses topic-sensitive PageRank to bias random walks toward selected topics.">Haveliwala 2002</a>.</p>
          <h3>Domains shared along follow edges</h3>
          <p>__SHARED_DOMAINS__</p>
          <h3>Domains shared across community boundaries</h3>
          <p>__CROSS_SHARED_DOMAINS__</p>
          <h3>Domains weighted by follower PageRank</h3>
          <p>__WEIGHTED_DOMAINS__</p>
        </section>
      </div>
    </main>
    <aside class="side sheet">
      <h2>Answers in one breath</h2>
      <ol>
        <li><b>Bridge:</b> __BRIDGE_TOP__ is the top sampled betweenness bridge.</li>
        <li><b>Surprising missing follow:</b> __MISSING_TOP__ has the highest two-hop score.</li>
        <li><b>Communities:</b> __COMMUNITY_COUNT__ Louvain groups in the largest weak component.</li>
        <li><b>Interests:</b> __INTEREST_OVERLAP__ of known-domain follow edges share at least one domain.</li>
      </ol>
      <p class="small quiet">These are computed answers, not proof of causality. The names are good places to inspect the graph manually.</p>
      <h2>Current graph</h2>
      <p><b>__NODES__</b> people, <b>__EDGES__</b> follows, largest weak component <b>__LARGEST_WEAK__</b> people.</p>
    </aside>
  </div>
  <h2>References</h2>
  <ol class="references">
    <li>Brandes. “A Faster Algorithm for Betweenness Centrality.” Gives exact betweenness scoring.</li>
    <li>Liben-Nowell and Kleinberg. “The Link-Prediction Problem for Social Networks.” Surveys link-prediction scores.</li>
    <li>Traag, Waltman, and van Eck. “From Louvain to Leiden.” Describes Leiden community detection.</li>
    <li>Haveliwala. “Topic-sensitive PageRank.” Biases random walks by topic.</li>
  </ol>
</div>
</body>
</html>
"""

FRONTPAGE_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Curius Front Page</title>
<style>
__PAPER_CSS__
  .intro { max-width: 76ch; }
  .more-banner { display: inline-flex; gap: .42rem; flex-wrap: wrap; align-items: baseline; margin: 0 0 1rem; padding: .34rem .66rem; border: 1px solid var(--rule); border-radius: 999px; background: rgba(255, 250, 240, .78); color: var(--muted); font-size: .92rem; }
  .more-banner a { color: var(--ink); }
  .front-controls { display: flex; gap: .55rem; flex-wrap: wrap; align-items: center; margin: 1rem 0 1.15rem; }
  .front-controls button[aria-pressed="true"] { background: var(--ink); color: var(--sheet); border-color: var(--ink); }
  .front-layout { display: grid; grid-template-columns: minmax(0, 1fr) minmax(280px, 350px); gap: 1.4rem; align-items: start; }
  .feed-head { border-bottom: 1px solid var(--rule); padding-bottom: .6rem; margin-bottom: .45rem; }
  .feed-head h2 { margin: 0 0 .25rem; }
  .hn-list { list-style: none; padding: 0; margin: 0; counter-reset: feed; }
  .hn-item { counter-increment: feed; display: grid; grid-template-columns: 2.25rem minmax(0, 1fr); gap: .55rem; padding: .72rem 0 .78rem; border-bottom: 1px solid var(--rule); }
  .hn-item::before { content: counter(feed) "."; color: var(--muted); text-align: right; padding-top: .08rem; }
  .story-title { display: flex; gap: .35rem; flex-wrap: wrap; align-items: baseline; font-size: 1.08rem; line-height: 1.25; }
  .story-title a { color: var(--ink); text-decoration: none; overflow-wrap: anywhere; }
  .story-title a:hover { text-decoration: underline; text-underline-offset: .16em; }
  .domain, .subtext { color: var(--muted); font-size: .92rem; }
  .subtext { margin-top: .16rem; }
  .snippet { color: var(--muted); margin: .38rem 0 0; font-size: .96rem; overflow-wrap: anywhere; }
  blockquote.quote { margin: .05rem 0 .34rem; padding: 0 0 0 .7rem; border-left: 3px solid var(--rule); font-size: 1.04rem; overflow-wrap: anywhere; }
  .side { position: sticky; top: 14px; display: grid; gap: 1rem; }
  .model, .glossary, .note { padding: 1rem; }
  .model p, .note p { max-width: none; }
  .model-controls { display: grid; gap: .7rem; margin-top: .75rem; }
  .model-controls input { width: 100%; }
  .model svg { width: 100%; height: auto; display: block; margin: .8rem 0 .4rem; }
  .diagram-label { fill: var(--ink); font-size: 14px; }
  .diagram-small { fill: var(--muted); font-size: 12px; }
  .glossary ul, .references { list-style: none; padding: 0; margin: .5rem 0 0; }
  .glossary li, .references li { margin: .45rem 0; }
  .glossary button { border: 0; background: transparent; min-height: 0; padding: .05rem .12rem; color: var(--blue); }
  .empty { color: var(--muted); padding: 1rem 0; }
  [hidden] { display: none !important; }
  @media (max-width: 860px) {
    .front-layout { display: flex; flex-direction: column; }
    .side { display: contents; }
    .model { order: -1; width: 100%; }
    .note, .glossary { width: 100%; }
    main { width: 100%; }
    .hn-item { grid-template-columns: 1.85rem minmax(0, 1fr); gap: .45rem; }
  }
</style>
</head>
<body>
<div class="page">
  <aside class="more-banner" aria-label="More Curius things"><span>See more Curius things</span><a href="__ANALYSIS_INDEX_URL__">follower graph</a><span aria-hidden="true">·</span><a href="__ANALYSIS_METRICS_URL__">metrics</a><span aria-hidden="true">·</span><a href="__ANALYSIS_ALGORITHMS_URL__">algorithms</a><span aria-hidden="true">·</span><a href="__ANALYSIS_QUESTIONS_URL__">questions</a></aside>
  <h1>Curius Front Page</h1>
  <p class="intro">Curius Front Page is a public readout of what Curius readers are saving and highlighting. It turns shared bookmarks and marked passages into a compact feed, so you can see which ideas many people returned to and which discoveries just arrived.</p>
  <p class="intro quiet">Use the toggles to switch between links and highlights, then between popular and newest. The small line under each row shows the evidence behind the ranking.</p>

  <section class="front-controls" aria-label="Feed controls">
    <button type="button" data-kind="links" aria-pressed="true">Links</button>
    <button type="button" data-kind="highlights" aria-pressed="false">Highlights</button>
    <span aria-hidden="true">·</span>
    <button type="button" data-sort="popular" aria-pressed="true">popular</button>
    <button type="button" data-sort="newest" aria-pressed="false">newest</button>
  </section>

  <div class="front-layout">
    <main>
      <section id="feed-head" class="feed-head" aria-live="polite"></section>
      <ol id="feed" class="hn-list"></ol>
    </main>
    <aside class="side">
      <section class="model sheet">
        <h2>Small ranking model</h2>
        <p>Popularity is not a mood. It is a count with weights. Move the weights and the list changes when the evidence changes.</p>
        <div id="formula-link" class="math"><span class="term" data-term="slink" tabindex="0">S<sub>link</sub></span> = <span class="term" data-term="ws" tabindex="0">w<sub>s</sub></span><span class="term" data-term="us" tabindex="0">u<sub>save</sub></span> + <span class="term" data-term="wm" tabindex="0">w<sub>m</sub></span><span class="term" data-term="um" tabindex="0">u<sub>mark</sub></span> + <span class="term" data-term="h" tabindex="0">h</span></div>
        <div id="formula-highlight" class="math" hidden><span class="term" data-term="squote" tabindex="0">S<sub>quote</sub></span> = <span class="term" data-term="wr" tabindex="0">w<sub>r</sub></span><span class="term" data-term="ur" tabindex="0">u<sub>reader</sub></span> + <span class="term" data-term="wt" tabindex="0">w<sub>t</sub></span><span class="term" data-term="r" tabindex="0">r</span></div>
        <div class="model-controls">
          <label><span id="weight-a-label">save reader weight</span><input id="weight-a" type="range" min="0" max="10" step="1" value="3"></label>
          <label><span id="weight-b-label">highlight reader weight</span><input id="weight-b" type="range" min="0" max="10" step="1" value="5"></label>
        </div>
        <svg id="rank-diagram" viewBox="0 0 330 230" role="img" aria-label="Live ranking diagram"></svg>
        <p id="model-note" class="quiet"></p>
      </section>
      <section class="note sheet">
        <h2>How to read a row</h2>
        <p>The title line is the thing you can open. The small line says how many distinct readers touched it, how many marks were left, and when the underlying record was created.</p>
      </section>
      <section class="glossary sheet">
        <h2>Glossary</h2>
        <ul id="glossary"></ul>
      </section>
    </aside>
  </div>

  <h2>References</h2>
  <ol class="references">
    <li>Hacker News API. Lists the compact story fields this page echoes.</li>
    <li>SQLite aggregate functions. Gives <code>count</code> and <code>count(distinct ...)</code>, which produce the local evidence counts <a class="cite" href="https://www.sqlite.org/lang_aggfunc.html" target="_blank" rel="noreferrer" title="Documents SQLite aggregate counts used to build the feed.">SQLite</a>.</li>
  </ol>
</div>
<section id="definition-card" class="definition-card sheet" aria-live="polite"><button id="close-def" type="button">Close</button><h3 id="def-title"></h3><p id="def-body"></p></section>
<script id="frontpage-data" type="application/json">__FRONTPAGE_JSON__</script>
<script>
(() => {
  "use strict";
  const data = JSON.parse(document.getElementById("frontpage-data").textContent);
  const generatedAt = Date.parse(data.generatedAt) || Date.now();
  const feed = document.getElementById("feed");
  const feedHead = document.getElementById("feed-head");
  const formulaLink = document.getElementById("formula-link");
  const formulaHighlight = document.getElementById("formula-highlight");
  const weightA = document.getElementById("weight-a");
  const weightB = document.getElementById("weight-b");
  const weightALabel = document.getElementById("weight-a-label");
  const weightBLabel = document.getElementById("weight-b-label");
  const diagram = document.getElementById("rank-diagram");
  const modelNote = document.getElementById("model-note");
  const state = {kind: "links", sort: "popular"};
  const weights = {links: {a: 3, b: 5}, highlights: {a: 4, b: 1}};
  const definitions = {
    slink: ["Slink", "The link popularity score used when the feed is sorted by popular."],
    ws: ["ws", "Weight on distinct readers who saved a link. Larger values move broadly saved links upward."],
    us: ["usave", "The number of distinct Curius users who saved the link."],
    wm: ["wm", "Weight on distinct readers who marked text from the link. Larger values favor links that produced highlights."],
    um: ["umark", "The number of distinct Curius users with at least one highlight on the link."],
    h: ["h", "The total number of highlights on the link. It adds texture after distinct-reader counts."],
    squote: ["Squote", "The highlight popularity score used when the feed is sorted by popular."],
    wr: ["wr", "Weight on distinct readers who made the same highlight on the same link."],
    ur: ["ureader", "The number of distinct readers behind a repeated highlight."],
    wt: ["wt", "Weight on total repeats of the same highlighted passage."],
    r: ["r", "The repeat count for the same highlight text on the same link."]
  };

  function text(tag, className, value) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (value !== undefined) node.textContent = value;
    return node;
  }
  function plural(n, word) { return `${n.toLocaleString()} ${word}${n === 1 ? "" : "s"}`; }
  function age(iso) {
    const t = Date.parse(iso || "");
    if (!Number.isFinite(t)) return "undated";
    const seconds = Math.max(0, Math.floor((generatedAt - t) / 1000));
    const units = [[31536000, "year"], [2592000, "month"], [604800, "week"], [86400, "day"], [3600, "hour"], [60, "minute"]];
    for (const [size, label] of units) {
      if (seconds >= size) return `${Math.floor(seconds / size)} ${label}${Math.floor(seconds / size) === 1 ? "" : "s"} ago`;
    }
    return "just now";
  }
  function currentWeights() { return weights[state.kind]; }
  function score(item) {
    const w = currentWeights();
    if (state.kind === "links") return w.a * item.savers + w.b * item.highlighters + item.highlights;
    return w.a * item.readers + w.b * item.repeats;
  }
  function sortedItems() {
    const items = [...(data[state.kind] || [])];
    if (state.sort === "newest") {
      items.sort((a, b) => (Date.parse(b.createdAt || "") || 0) - (Date.parse(a.createdAt || "") || 0) || score(b) - score(a));
    } else {
      items.sort((a, b) => score(b) - score(a) || (Date.parse(b.createdAt || "") || 0) - (Date.parse(a.createdAt || "") || 0));
    }
    return items.slice(0, 50);
  }
  function renderHead(items) {
    feedHead.replaceChildren();
    const h = text("h2", "", `${state.sort === "popular" ? "Popular" : "Newest"} ${state.kind}`);
    const p = text("p", "quiet", state.sort === "popular"
      ? `Sorted by the visible score. ${items.length.toLocaleString()} rows are shown from the generated sample.`
      : `Sorted by creation time. The score remains visible, but it does not move the row.`);
    feedHead.append(h, p);
  }
  function renderLink(item, body) {
    const title = text("div", "story-title");
    const a = text("a", "", item.title || item.url);
    a.href = item.url; a.target = "_blank"; a.rel = "noreferrer";
    const domain = text("span", "domain", `(${item.domain})`);
    title.append(a, domain);
    const sub = text("div", "subtext", `${Math.round(score(item)).toLocaleString()} points · ${plural(item.savers, "saver")} · ${plural(item.highlighters, "reader")} marked it · ${plural(item.highlights, "highlight")} · ${age(item.createdAt)}`);
    body.append(title, sub);
    if (item.snippet) body.append(text("p", "snippet", item.snippet));
  }
  function renderHighlight(item, body) {
    body.append(text("blockquote", "quote", item.quote));
    const title = text("div", "story-title");
    const a = text("a", "", item.title || item.url);
    a.href = item.url; a.target = "_blank"; a.rel = "noreferrer";
    title.append(a, text("span", "domain", `(${item.domain})`));
    const user = item.user ? ` · latest by ${item.user}` : "";
    const sub = text("div", "subtext", `${Math.round(score(item)).toLocaleString()} points · ${plural(item.readers, "reader")} · ${plural(item.repeats, "repeat")} · ${age(item.createdAt)}${user}`);
    body.append(title, sub);
    if (item.context) body.append(text("p", "snippet", item.context));
  }
  function renderFeed(items) {
    feed.replaceChildren();
    if (!items.length) {
      feed.append(text("li", "empty", "No rows in this generated sample."));
      return;
    }
    for (const item of items) {
      const li = text("li", "hn-item");
      const body = text("div", "");
      if (state.kind === "links") renderLink(item, body); else renderHighlight(item, body);
      li.append(body);
      feed.append(li);
    }
  }
  function configureControls() {
    const isLinks = state.kind === "links";
    formulaLink.hidden = !isLinks;
    formulaHighlight.hidden = isLinks;
    weightA.value = currentWeights().a;
    weightB.value = currentWeights().b;
    weightALabel.textContent = isLinks ? `save reader weight: ${weightA.value}` : `reader weight: ${weightA.value}`;
    weightBLabel.textContent = isLinks ? `highlight reader weight: ${weightB.value}` : `repeat weight: ${weightB.value}`;
    document.querySelectorAll("[data-kind]").forEach(button => button.setAttribute("aria-pressed", String(button.dataset.kind === state.kind)));
    document.querySelectorAll("[data-sort]").forEach(button => button.setAttribute("aria-pressed", String(button.dataset.sort === state.sort)));
  }
  function renderDiagram(items) {
    const item = items[0];
    if (!item) { diagram.replaceChildren(); return; }
    const isLinks = state.kind === "links";
    const a = isLinks ? item.savers : item.readers;
    const b = isLinks ? item.highlighters : item.repeats;
    const c = isLinks ? item.highlights : 0;
    const maxA = Math.max(1, ...items.map(x => isLinks ? x.savers : x.readers));
    const maxB = Math.max(1, ...items.map(x => isLinks ? x.highlighters : x.repeats));
    const aw = 34 + Math.round(90 * a / maxA);
    const bw = 34 + Math.round(90 * b / maxB);
    const maxScore = Math.max(1, ...items.map(x => score(x)));
    const sw = Math.min(140, 40 + Math.round(score(item) / maxScore * 95));
    diagram.innerHTML = `
      <defs><marker id="arrow-front" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M 0 0 L 10 5 L 0 10 z" fill="#8d7d68"></path></marker></defs>
      <text x="16" y="24" class="diagram-label">evidence</text>
      <rect x="18" y="46" width="${aw}" height="26" rx="13" fill="#d87c4a" opacity=".85"></rect>
      <text x="28" y="64" class="diagram-small">${a.toLocaleString()} ${isLinks ? "savers" : "readers"}</text>
      <rect x="18" y="90" width="${bw}" height="26" rx="13" fill="#4e85c8" opacity=".85"></rect>
      <text x="28" y="108" class="diagram-small">${b.toLocaleString()} ${isLinks ? "markers" : "repeats"}</text>
      ${isLinks ? `<rect x="18" y="134" width="${34 + Math.min(90, c)}" height="26" rx="13" fill="#55a36f" opacity=".78"></rect><text x="28" y="152" class="diagram-small">${c.toLocaleString()} highlights</text>` : ""}
      <path d="M 158 62 C 190 62, 190 102, 220 102" stroke="#8d7d68" stroke-width="2" fill="none" marker-end="url(#arrow-front)"></path>
      <path d="M 158 102 C 190 102, 190 102, 220 102" stroke="#8d7d68" stroke-width="2" fill="none" marker-end="url(#arrow-front)"></path>
      ${isLinks ? `<path d="M 158 146 C 190 146, 190 102, 220 102" stroke="#8d7d68" stroke-width="2" fill="none" marker-end="url(#arrow-front)"></path>` : ""}
      <text x="226" y="78" class="diagram-label">score</text>
      <rect x="224" y="90" width="${sw}" height="36" rx="18" fill="#f1d08a" stroke="#d1b16d"></rect>
      <text x="238" y="113" class="diagram-label">${Math.round(score(item)).toLocaleString()}</text>
      <text x="18" y="202" class="diagram-small">${state.sort === "popular" ? "popular uses this score" : "newest ignores the arrows and sorts by date"}</text>`;
    modelNote.textContent = state.sort === "popular"
      ? "The first visible row is the current highest score under these weights."
      : "The first visible row is newest; the diagram still shows how its popularity score is computed.";
  }
  function render() {
    configureControls();
    const items = sortedItems();
    renderHead(items);
    renderFeed(items);
    renderDiagram(items);
  }
  function showDef(key) {
    const value = definitions[key];
    if (!value) return;
    document.getElementById("def-title").textContent = value[0];
    document.getElementById("def-body").textContent = value[1];
    document.getElementById("definition-card").setAttribute("open", "");
  }

  document.querySelectorAll("[data-kind]").forEach(button => button.addEventListener("click", () => { state.kind = button.dataset.kind; render(); }));
  document.querySelectorAll("[data-sort]").forEach(button => button.addEventListener("click", () => { state.sort = button.dataset.sort; render(); }));
  weightA.addEventListener("input", () => { weights[state.kind].a = Number(weightA.value); render(); });
  weightB.addEventListener("input", () => { weights[state.kind].b = Number(weightB.value); render(); });
  document.addEventListener("click", event => {
    const term = event.target.closest(".term");
    if (term) showDef(term.dataset.term);
  });
  document.addEventListener("keydown", event => {
    if (event.key === "Enter" || event.key === " ") {
      const term = event.target.closest(".term");
      if (term) { event.preventDefault(); showDef(term.dataset.term); }
    }
  });
  document.getElementById("close-def").addEventListener("click", () => document.getElementById("definition-card").removeAttribute("open"));
  document.querySelectorAll(".term").forEach(term => {
    const value = definitions[term.dataset.term];
    if (value) term.title = value[1];
  });
  const glossary = document.getElementById("glossary");
  for (const [key, [title, body]] of Object.entries(definitions)) {
    const li = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = title;
    button.addEventListener("click", () => showDef(key));
    li.append(button, ` — ${body}`);
    glossary.append(li);
  }
  render();
})();
</script>
</body>
</html>
"""


def fmt_int(value: int) -> str:
    return f"{value:,}"


def fmt_float(value: float, digits: int = 3) -> str:
    return f"{value:.{digits}f}"


def fmt_pct(value: float, digits: int = 2) -> str:
    return f"{value * 100:.{digits}f}%"


def display_name(row: sqlite3.Row) -> str:
    name = " ".join(part for part in (row["first_name"], row["last_name"]) if part).strip()
    return name or row["user_link"]


def compact_text(value: Any, limit: int = 260) -> str:
    text = " ".join(html.unescape(str(value or "")).split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rsplit(" ", 1)[0].rstrip(".,;:") + "…"


def domain_for(url: str) -> str:
    parsed = urlparse(url or "")
    domain = parsed.netloc or parsed.path.split("/", 1)[0]
    return domain.lower().removeprefix("www.") or "link"


def context_text(left: Any, right: Any) -> str:
    left_text = compact_text(left, 120)
    right_text = compact_text(right, 120)
    if left_text and right_text:
        return f"…{left_text} […] {right_text}…"
    if left_text:
        return f"…{left_text}"
    if right_text:
        return f"{right_text}…"
    return ""


def load_frontpage(db_path: Path, limit: int = 160) -> dict[str, Any]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = ON")
    links = load_frontpage_links(conn, limit)
    highlights = load_frontpage_highlights(conn, limit)
    conn.close()
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": str(db_path),
        "links": links,
        "highlights": highlights,
    }


def load_user_domains(db_path: Path) -> dict[int, Counter[str]]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = ON")
    domains: dict[int, Counter[str]] = defaultdict(Counter)
    try:
        rows = conn.execute(
            """
            SELECT sl.user_id, l.url
            FROM saved_links sl
            JOIN links l ON l.link_id = sl.link_id
            WHERE l.url IS NOT NULL AND trim(l.url) <> ''
            """
        )
    except sqlite3.OperationalError:
        conn.close()
        return {}
    for row in rows:
        domains[row["user_id"]][domain_for(row["url"])] += 1
    conn.close()
    return domains


def load_frontpage_links(conn: sqlite3.Connection, limit: int) -> list[dict[str, Any]]:
    base = """
        WITH saves AS (
            SELECT link_id, count(*) AS saves, count(DISTINCT user_id) AS savers
            FROM saved_links GROUP BY link_id
        ), marks AS (
            SELECT link_id, count(*) AS highlights, count(DISTINCT user_id) AS highlighters
            FROM highlights
            WHERE length(trim(coalesce(highlight_text, raw_highlight, ''))) > 0
            GROUP BY link_id
        )
        SELECT l.link_id, l.url, coalesce(nullif(trim(l.title), ''), l.url) AS title,
               l.snippet, l.created_at, l.modified_at, l.updated_at,
               coalesce(s.saves, 0) AS saves, coalesce(s.savers, 0) AS savers,
               coalesce(m.highlights, 0) AS highlights, coalesce(m.highlighters, 0) AS highlighters,
               coalesce(s.savers, 0) * 3 + coalesce(m.highlighters, 0) * 5 + coalesce(m.highlights, 0) AS score
        FROM links l
        LEFT JOIN saves s ON s.link_id = l.link_id
        LEFT JOIN marks m ON m.link_id = l.link_id
        WHERE l.url IS NOT NULL AND trim(l.url) <> ''
    """
    rows: dict[int, dict[str, Any]] = {}
    for order in ("score DESC, created_at DESC", "created_at DESC, score DESC"):
        for row in conn.execute(f"{base} ORDER BY {order} LIMIT ?", (limit,)):
            created = row["created_at"] or row["modified_at"] or row["updated_at"] or ""
            rows.setdefault(row["link_id"], {
                "id": row["link_id"],
                "title": compact_text(row["title"], 190),
                "url": row["url"],
                "domain": domain_for(row["url"]),
                "snippet": compact_text(row["snippet"], 260),
                "createdAt": created,
                "saves": int(row["saves"]),
                "savers": int(row["savers"]),
                "highlights": int(row["highlights"]),
                "highlighters": int(row["highlighters"]),
            })
    return list(rows.values())


def load_frontpage_highlights(conn: sqlite3.Connection, limit: int) -> list[dict[str, Any]]:
    clean = """
        WITH clean AS (
            SELECT h.highlight_id, h.user_id, h.link_id,
                   trim(replace(replace(coalesce(nullif(h.highlight_text, ''), nullif(h.raw_highlight, ''), ''), char(10), ' '), char(13), ' ')) AS quote,
                   h.left_context, h.right_context, h.created_at
            FROM highlights h
        )
    """
    popular = f"""
        {clean}, grouped AS (
            SELECT link_id, quote, count(*) AS repeats, count(DISTINCT user_id) AS readers,
                   min(created_at) AS first_at, max(created_at) AS created_at,
                   count(*) + 4 * count(DISTINCT user_id) AS score
            FROM clean
            WHERE length(quote) BETWEEN 8 AND 700
            GROUP BY link_id, quote
        )
        SELECT p.highlight_id, g.link_id, g.quote, g.repeats, g.readers, g.first_at, g.created_at,
               p.left_context, p.right_context, l.title, l.url, u.user_link
        FROM grouped g
        JOIN clean p ON p.highlight_id = (
            SELECT c2.highlight_id FROM clean c2
            WHERE c2.link_id = g.link_id AND c2.quote = g.quote
            ORDER BY c2.created_at DESC, c2.highlight_id DESC LIMIT 1
        )
        JOIN links l ON l.link_id = g.link_id
        LEFT JOIN users u ON u.user_id = p.user_id
        WHERE l.url IS NOT NULL AND trim(l.url) <> ''
        ORDER BY g.score DESC, g.created_at DESC
        LIMIT ?
    """
    newest = f"""
        {clean}
        SELECT c.highlight_id, c.link_id, c.quote, 1 AS repeats, 1 AS readers,
               c.created_at AS first_at, c.created_at, c.left_context, c.right_context,
               l.title, l.url, u.user_link
        FROM clean c
        JOIN links l ON l.link_id = c.link_id
        LEFT JOIN users u ON u.user_id = c.user_id
        WHERE length(c.quote) BETWEEN 8 AND 700 AND l.url IS NOT NULL AND trim(l.url) <> ''
        ORDER BY c.created_at DESC, c.highlight_id DESC
        LIMIT ?
    """
    rows: dict[tuple[int, str], dict[str, Any]] = {}
    for query in (popular, newest):
        for row in conn.execute(query, (limit,)):
            key = (row["link_id"], row["quote"])
            item = rows.get(key)
            created = row["created_at"] or ""
            if item is None:
                rows[key] = {
                    "id": row["highlight_id"],
                    "linkId": row["link_id"],
                    "quote": compact_text(row["quote"], 460),
                    "title": compact_text(row["title"] or row["url"], 180),
                    "url": row["url"],
                    "domain": domain_for(row["url"]),
                    "createdAt": created,
                    "firstAt": row["first_at"] or "",
                    "readers": int(row["readers"]),
                    "repeats": int(row["repeats"]),
                    "user": row["user_link"] or "",
                    "context": context_text(row["left_context"], row["right_context"]),
                }
                continue
            item["readers"] = max(item["readers"], int(row["readers"]))
            item["repeats"] = max(item["repeats"], int(row["repeats"]))
            if created > item["createdAt"]:
                item["createdAt"] = created
                item["user"] = row["user_link"] or ""
                item["context"] = context_text(row["left_context"], row["right_context"])
    return list(rows.values())


def load_graph(db_path: Path) -> tuple[list[dict[str, Any]], list[tuple[int, int]]]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = ON")
    rows = conn.execute(
        """
        WITH follower_counts AS (
            SELECT followed_user_id AS user_id, count(*) AS n FROM follows GROUP BY followed_user_id
        ), following_counts AS (
            SELECT follower_user_id AS user_id, count(*) AS n FROM follows GROUP BY follower_user_id
        )
        SELECT u.user_id, u.user_link, u.first_name, u.last_name, u.school, u.github, u.twitter,
               u.website, coalesce(u.num_followers, 0) AS api_followers,
               coalesce(fc.n, 0) AS in_count, coalesce(fg.n, 0) AS out_count
        FROM users u
        LEFT JOIN follower_counts fc ON fc.user_id = u.user_id
        LEFT JOIN following_counts fg ON fg.user_id = u.user_id
        ORDER BY in_count DESC, out_count DESC, u.user_link
        """
    ).fetchall()
    edges = [tuple(row) for row in conn.execute(
        """
        SELECT f.follower_user_id, f.followed_user_id
        FROM follows f
        JOIN users a ON a.user_id = f.follower_user_id
        JOIN users b ON b.user_id = f.followed_user_id
        ORDER BY f.follower_user_id, f.followed_user_id
        """
    ).fetchall()]
    conn.close()
    nodes = [
        {
            "id": row["user_id"],
            "slug": row["user_link"],
            "name": display_name(row),
            "school": row["school"] or "",
            "github": row["github"] or "",
            "twitter": row["twitter"] or "",
            "website": row["website"] or "",
            "apiFollowers": row["api_followers"],
            "in": row["in_count"],
            "out": row["out_count"],
        }
        for row in rows
    ]
    return nodes, edges


def build_adjacency(ids: list[int], edges: list[tuple[int, int]]) -> tuple[dict[int, list[int]], dict[int, list[int]], dict[int, set[int]]]:
    id_set = set(ids)
    outgoing: dict[int, list[int]] = {i: [] for i in ids}
    incoming: dict[int, list[int]] = {i: [] for i in ids}
    undirected: dict[int, set[int]] = {i: set() for i in ids}
    for a, b in edges:
        if a not in id_set or b not in id_set:
            continue
        outgoing[a].append(b)
        incoming[b].append(a)
        undirected[a].add(b)
        undirected[b].add(a)
    return outgoing, incoming, undirected


def weak_components(ids: list[int], undirected: dict[int, set[int]]) -> tuple[dict[int, int], list[int]]:
    raw_component: dict[int, int] = {}
    sizes: list[int] = []
    for start in ids:
        if start in raw_component:
            continue
        index = len(sizes)
        queue = deque([start])
        raw_component[start] = index
        size = 0
        while queue:
            node = queue.popleft()
            size += 1
            for nxt in undirected[node]:
                if nxt not in raw_component:
                    raw_component[nxt] = index
                    queue.append(nxt)
        sizes.append(size)
    order = sorted(range(len(sizes)), key=lambda i: sizes[i], reverse=True)
    remap = {old: new for new, old in enumerate(order)}
    return {node: remap[index] for node, index in raw_component.items()}, [sizes[i] for i in order]


def strong_component_sizes(ids: list[int], outgoing: dict[int, list[int]], incoming: dict[int, list[int]]) -> list[int]:
    visited: set[int] = set()
    order: list[int] = []
    for start in ids:
        if start in visited:
            continue
        visited.add(start)
        stack: list[tuple[int, int]] = [(start, 0)]
        while stack:
            node, i = stack[-1]
            if i < len(outgoing[node]):
                nxt = outgoing[node][i]
                stack[-1] = (node, i + 1)
                if nxt not in visited:
                    visited.add(nxt)
                    stack.append((nxt, 0))
            else:
                order.append(node)
                stack.pop()
    assigned: set[int] = set()
    sizes: list[int] = []
    for start in reversed(order):
        if start in assigned:
            continue
        size = 0
        stack = [start]
        assigned.add(start)
        while stack:
            node = stack.pop()
            size += 1
            for nxt in incoming[node]:
                if nxt not in assigned:
                    assigned.add(nxt)
                    stack.append(nxt)
        sizes.append(size)
    return sorted(sizes, reverse=True)


def strong_components(ids: list[int], outgoing: dict[int, list[int]], incoming: dict[int, list[int]]) -> tuple[dict[int, int], list[list[int]]]:
    visited: set[int] = set()
    order: list[int] = []
    for start in ids:
        if start in visited:
            continue
        visited.add(start)
        stack: list[tuple[int, int]] = [(start, 0)]
        while stack:
            node, i = stack[-1]
            if i < len(outgoing[node]):
                nxt = outgoing[node][i]
                stack[-1] = (node, i + 1)
                if nxt not in visited:
                    visited.add(nxt)
                    stack.append((nxt, 0))
            else:
                order.append(node)
                stack.pop()
    assigned: set[int] = set()
    raw: list[list[int]] = []
    for start in reversed(order):
        if start in assigned:
            continue
        members: list[int] = []
        stack = [start]
        assigned.add(start)
        while stack:
            node = stack.pop()
            members.append(node)
            for nxt in incoming[node]:
                if nxt not in assigned:
                    assigned.add(nxt)
                    stack.append(nxt)
        raw.append(members)
    raw.sort(key=len, reverse=True)
    component = {node: i for i, members in enumerate(raw) for node in members}
    return component, raw


def reachable_from(starts: set[int], adjacency: dict[int, list[int]]) -> set[int]:
    seen = set(starts)
    queue = deque(starts)
    while queue:
        node = queue.popleft()
        for nxt in adjacency[node]:
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    return seen


def largest_component_path_stats(ids: list[int], weak: dict[int, int], undirected: dict[int, set[int]]) -> dict[str, Any]:
    largest = [node for node in ids if weak[node] == 0]
    largest_set = set(largest)
    total = 0
    pairs = 0
    diameter = 0
    distance_counts: Counter[int] = Counter()
    for index, start in enumerate(largest):
        distances = {start: 0}
        queue = deque([start])
        while queue:
            node = queue.popleft()
            for nxt in undirected[node]:
                if nxt in largest_set and nxt not in distances:
                    distances[nxt] = distances[node] + 1
                    queue.append(nxt)
        for target in largest[index + 1:]:
            distance = distances[target]
            total += distance
            pairs += 1
            diameter = max(diameter, distance)
            distance_counts[distance] += 1
    threshold = math.ceil(pairs * 0.9)
    seen = 0
    p90 = 0
    for distance in sorted(distance_counts):
        seen += distance_counts[distance]
        if seen >= threshold:
            p90 = distance
            break
    return {"pairs": pairs, "average": total / pairs if pairs else 0.0, "diameter": diameter, "p90": p90, "counts": dict(distance_counts)}


def hits(ids: list[int], outgoing: dict[int, list[int]], incoming: dict[int, list[int]], iterations: int = 60) -> tuple[dict[int, float], dict[int, float]]:
    authority = {node: 1.0 for node in ids}
    hub = {node: 1.0 for node in ids}
    for _ in range(iterations):
        authority = {node: sum(hub[src] for src in incoming[node]) for node in ids}
        norm = math.sqrt(sum(value * value for value in authority.values())) or 1.0
        authority = {node: value / norm for node, value in authority.items()}
        hub = {node: sum(authority[dst] for dst in outgoing[node]) for node in ids}
        norm = math.sqrt(sum(value * value for value in hub.values())) or 1.0
        hub = {node: value / norm for node, value in hub.items()}
    return authority, hub


def school_homophily(nodes: list[dict[str, Any]], edges: list[tuple[int, int]]) -> dict[str, Any]:
    by_id = {node["id"]: node for node in nodes}
    known = 0
    same = 0
    endpoint_counts: Counter[str] = Counter()
    for a, b in edges:
        sa = by_id[a]["school"].strip().lower()
        sb = by_id[b]["school"].strip().lower()
        if not sa or not sb:
            continue
        known += 1
        endpoint_counts[sa] += 1
        endpoint_counts[sb] += 1
        if sa == sb:
            same += 1
    total_endpoints = sum(endpoint_counts.values())
    expected = sum((count / total_endpoints) ** 2 for count in endpoint_counts.values()) if total_endpoints else 0.0
    return {"knownEdges": known, "sameSchoolEdges": same, "sameShare": same / known if known else 0.0, "expectedShare": expected}


def person_item(node: dict[str, Any], **extra: Any) -> dict[str, Any]:
    item = {
        "slug": node["slug"],
        "name": node["name"],
        "followers": node["in"],
        "following": node["out"],
        "core": node.get("core", 0),
    }
    item.update(extra)
    return item


def next_question_analyses(
    nodes: list[dict[str, Any]],
    edges: list[tuple[int, int]],
    outgoing: dict[int, list[int]],
    incoming: dict[int, list[int]],
    undirected: dict[int, set[int]],
    weak: dict[int, int],
    ranks: dict[int, float],
    user_domains: dict[int, Counter[str]],
) -> dict[str, Any]:
    by_id = {node["id"]: node for node in nodes}
    ids = [node["id"] for node in nodes]
    largest = [node_id for node_id in ids if weak.get(node_id) == 0]
    largest_set = set(largest)
    bridge_rows: list[dict[str, Any]] = []
    community_rows: list[dict[str, Any]] = []
    community_count = 0
    modularity = 0.0
    community_id = {node_id: weak.get(node_id, -1) for node_id in ids}

    if nx is not None and largest:
        graph = nx.Graph()
        graph.add_nodes_from(largest)
        graph.add_edges_from((a, b) for a, b in edges if a in largest_set and b in largest_set)
        sample = min(256, graph.number_of_nodes())
        scores = nx.betweenness_centrality(graph, k=sample, seed=7, normalized=True)
        bridge_rows = [
            person_item(by_id[node_id], score=score, sample=sample)
            for node_id, score in sorted(scores.items(), key=lambda item: item[1], reverse=True)[:10]
        ]
        communities = sorted(nx.algorithms.community.louvain_communities(graph, seed=7, resolution=1.0), key=len, reverse=True)
        community_count = len(communities)
        modularity = nx.algorithms.community.modularity(graph, communities) if communities else 0.0
        community_id = {node_id: index for index, members in enumerate(communities) for node_id in members}
        for index, members in enumerate(communities[:8], 1):
            schools = Counter((by_id[node_id].get("school") or "").strip() for node_id in members)
            schools.pop("", None)
            domains: Counter[str] = Counter()
            for node_id in members:
                domains.update(user_domains.get(node_id, Counter()))
            top_members = sorted(members, key=lambda node_id: (len(undirected[node_id]), by_id[node_id]["in"], by_id[node_id]["slug"]), reverse=True)[:5]
            community_rows.append({
                "index": index,
                "size": len(members),
                "schools": schools.most_common(3),
                "domains": domains.most_common(5),
                "people": [person_item(by_id[node_id]) for node_id in top_members],
            })

    out_sets = {node_id: set(values) for node_id, values in outgoing.items()}
    in_sets = {node_id: set(values) for node_id, values in incoming.items()}
    missing_scores: Counter[tuple[int, int]] = Counter()
    for source, mids in out_sets.items():
        blocked = set(mids)
        blocked.add(source)
        for middle in mids:
            for candidate in out_sets.get(middle, set()):
                if candidate not in blocked:
                    missing_scores[(source, candidate)] += 1
    missing_rows = [
        {
            "source": person_item(by_id[source]),
            "target": person_item(by_id[target]),
            "score": score,
            "targetFollowers": len(in_sets[target]),
        }
        for (source, target), score in missing_scores.most_common(10)
    ]
    existing_rows = []
    for source, target in edges:
        support = len(out_sets[source] & in_sets[target])
        salience = math.log1p(len(out_sets[source])) * math.log1p(len(in_sets[target])) / (1 + support)
        existing_rows.append((support, -salience, source, target, salience))
    surprising_rows = [
        {
            "source": person_item(by_id[source]),
            "target": person_item(by_id[target]),
            "support": support,
            "salience": salience,
            "sourceFollowing": len(out_sets[source]),
            "targetFollowers": len(in_sets[target]),
        }
        for support, _neg, source, target, salience in sorted(existing_rows)[:10]
    ]

    known_edges = 0
    overlapping_edges = 0
    shared_domains: Counter[str] = Counter()
    cross_shared_domains: Counter[str] = Counter()
    for source, target in edges:
        source_domains = set(user_domains.get(source, Counter()))
        target_domains = set(user_domains.get(target, Counter()))
        if not source_domains or not target_domains:
            continue
        known_edges += 1
        overlap = source_domains & target_domains
        if not overlap:
            continue
        overlapping_edges += 1
        shared_domains.update(overlap)
        if community_id.get(source) != community_id.get(target):
            cross_shared_domains.update(overlap)
    weighted_domains: Counter[str] = Counter()
    for node_id, domains in user_domains.items():
        total = sum(domains.values())
        if not total:
            continue
        for domain, count in domains.items():
            weighted_domains[domain] += ranks.get(node_id, 0.0) * count / total

    return {
        "bridges": bridge_rows,
        "missingFollows": missing_rows,
        "surprisingFollows": surprising_rows,
        "communities": community_rows,
        "communityCount": community_count,
        "modularity": modularity,
        "interest": {
            "knownEdges": known_edges,
            "overlappingEdges": overlapping_edges,
            "overlapShare": overlapping_edges / known_edges if known_edges else 0.0,
            "sharedDomains": shared_domains.most_common(12),
            "crossSharedDomains": cross_shared_domains.most_common(12),
            "weightedDomains": weighted_domains.most_common(12),
        },
    }


def core_numbers(ids: list[int], undirected: dict[int, set[int]]) -> dict[int, int]:
    degree = {node: len(undirected[node]) for node in ids}
    heap = [(deg, node) for node, deg in degree.items()]
    heapq.heapify(heap)
    removed: set[int] = set()
    core: dict[int, int] = {}
    while heap:
        deg, node = heapq.heappop(heap)
        if node in removed or deg != degree[node]:
            continue
        removed.add(node)
        core[node] = deg
        for nxt in undirected[node]:
            if nxt not in removed and degree[nxt] > deg:
                degree[nxt] -= 1
                heapq.heappush(heap, (degree[nxt], nxt))
    return core


def pagerank(ids: list[int], outgoing: dict[int, list[int]], alpha: float = 0.85, iterations: int = 60) -> dict[int, float]:
    n = len(ids)
    if not n:
        return {}
    rank = {node: 1.0 / n for node in ids}
    for _ in range(iterations):
        dangling = sum(rank[node] for node in ids if not outgoing[node])
        base = (1.0 - alpha) / n + alpha * dangling / n
        nxt = {node: base for node in ids}
        for node in ids:
            links = outgoing[node]
            if not links:
                continue
            share = alpha * rank[node] / len(links)
            for target in links:
                nxt[target] += share
        rank = nxt
    return rank


def clustering(undirected: dict[int, set[int]]) -> tuple[float, float, int]:
    values: list[float] = []
    closed = 0
    triples = 0
    for node, neighbors in undirected.items():
        k = len(neighbors)
        if k < 2:
            continue
        links = sum(len(undirected[n] & neighbors) for n in neighbors) // 2
        possible = k * (k - 1) // 2
        closed += links
        triples += possible
        values.append(links / possible)
    return (sum(values) / len(values) if values else 0.0, closed / triples if triples else 0.0, len(values))


def layout_nodes(nodes: list[dict[str, Any]], undirected: dict[int, set[int]], components: dict[int, int], component_sizes: list[int], cores: dict[int, int]) -> None:
    by_id = {node["id"]: node for node in nodes}
    component_members: dict[int, list[int]] = defaultdict(list)
    for node in nodes:
        component_members[components[node["id"]]].append(node["id"])
    max_core = max(cores.values() or [0])
    for component, members in component_members.items():
        members.sort(key=lambda node: (cores[node], len(undirected[node]), by_id[node]["in"], -node), reverse=True)
        if component == 0:
            for rank, node_id in enumerate(members):
                f = rank / max(1, len(members) - 1)
                core_pull = 1.0 - (cores[node_id] / max_core if max_core else 0.0)
                radius = 55 + 610 * (f ** 0.58) + 120 * core_pull
                theta = rank * GOLDEN_ANGLE
                by_id[node_id]["x"] = round(math.cos(theta) * radius + deterministic_jitter(node_id) * 14, 2)
                by_id[node_id]["y"] = round(math.sin(theta) * radius + deterministic_jitter(node_id * 17) * 14, 2)
        elif len(members) == 1:
            node_id = members[0]
            rank = component - 1
            theta = rank * GOLDEN_ANGLE
            radius = 1040 + (rank % 9) * 27 + math.sqrt(rank + 1) * 2
            by_id[node_id]["x"] = round(math.cos(theta) * radius, 2)
            by_id[node_id]["y"] = round(math.sin(theta) * radius, 2)
        else:
            rank = component - 1
            theta = rank * GOLDEN_ANGLE
            center_radius = 850 + math.sqrt(rank + 1) * 37
            cx, cy = math.cos(theta) * center_radius, math.sin(theta) * center_radius
            local = min(120, 24 + math.sqrt(len(members)) * 15)
            for i, node_id in enumerate(members):
                a = i * GOLDEN_ANGLE
                r = local * math.sqrt((i + 1) / len(members))
                by_id[node_id]["x"] = round(cx + math.cos(a) * r, 2)
                by_id[node_id]["y"] = round(cy + math.sin(a) * r, 2)
        for node_id in members:
            by_id[node_id]["component"] = component
            by_id[node_id]["componentSize"] = component_sizes[component]


def deterministic_jitter(seed: int) -> float:
    value = (seed * 1103515245 + 12345) & 0x7FFFFFFF
    return value / 0x7FFFFFFF - 0.5


def enrich(nodes: list[dict[str, Any]], edges: list[tuple[int, int]], user_domains: dict[int, Counter[str]] | None = None) -> dict[str, Any]:
    user_domains = user_domains or {}
    ids = [node["id"] for node in nodes]
    outgoing, incoming, undirected = build_adjacency(ids, edges)
    weak, weak_sizes = weak_components(ids, undirected)
    strong, strong_lists = strong_components(ids, outgoing, incoming)
    strong_sizes = [len(members) for members in strong_lists]
    largest_scc = set(strong_lists[0]) if strong_lists else set()
    reaches_from_scc = reachable_from(largest_scc, outgoing) if largest_scc else set()
    can_reach_scc = reachable_from(largest_scc, incoming) if largest_scc else set()
    path_stats = largest_component_path_stats(ids, weak, undirected)
    cores = core_numbers(ids, undirected)
    ranks = pagerank(ids, outgoing)
    authorities, hubs = hits(ids, outgoing, incoming)
    school = school_homophily(nodes, edges)
    mean_cluster, transitivity, cluster_people = clustering(undirected)
    edge_set = set(edges)
    reciprocal_edges = sum(1 for a, b in edges if (b, a) in edge_set)
    layout_nodes(nodes, undirected, weak, weak_sizes, cores)
    for node in nodes:
        node_id = node["id"]
        node["core"] = cores[node_id]
        node["rank"] = round(ranks[node_id], 10)
        node["authority"] = round(authorities[node_id], 10)
        node["hub"] = round(hubs[node_id], 10)
        node["strongComponent"] = strong[node_id]
    next_analyses = next_question_analyses(nodes, edges, outgoing, incoming, undirected, weak, ranks, user_domains)
    max_core = max(cores.values() or [0])
    metrics = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "counts": {"nodes": len(nodes), "edges": len(edges)},
        "density": len(edges) / (len(nodes) * (len(nodes) - 1)) if len(nodes) > 1 else 0,
        "averageIn": len(edges) / len(nodes) if nodes else 0,
        "averageOut": len(edges) / len(nodes) if nodes else 0,
        "reciprocalEdges": reciprocal_edges,
        "reciprocalPairs": reciprocal_edges // 2,
        "reciprocity": reciprocal_edges / len(edges) if edges else 0,
        "weakComponents": len(weak_sizes),
        "weakSizes": weak_sizes[:20],
        "largestWeak": weak_sizes[0] if weak_sizes else 0,
        "strongComponents": len(strong_sizes),
        "strongSizes": strong_sizes[:20],
        "largestStrong": strong_sizes[0] if strong_sizes else 0,
        "meanClustering": mean_cluster,
        "transitivity": transitivity,
        "clusterPeople": cluster_people,
        "maxCore": max_core,
        "maxCoreCount": sum(1 for value in cores.values() if value == max_core),
        "pathStats": path_stats,
        "bowTie": {
            "scc": len(largest_scc),
            "in": len(can_reach_scc - largest_scc),
            "out": len(reaches_from_scc - largest_scc),
            "tendrils": len(set(ids) - (can_reach_scc | reaches_from_scc)),
        },
        "schoolHomophily": school,
        "topFollowers": top_people(nodes, lambda n: (n["in"], n["rank"])),
        "topFollowing": top_people(nodes, lambda n: (n["out"], n["rank"])),
        "topPageRank": top_people(nodes, lambda n: (n["rank"], n["in"])),
        "topCore": top_people(nodes, lambda n: (n["core"], n["in"])),
        "topAuthorities": top_people(nodes, lambda n: (n["authority"], n["in"])),
        "topHubs": top_people(nodes, lambda n: (n["hub"], n["out"])),
        "nextAnalyses": next_analyses,
    }
    return {"nodes": nodes, "edges": edges, "metrics": metrics}


def top_people(nodes: list[dict[str, Any]], key: Any, limit: int = 12) -> list[dict[str, Any]]:
    picked = sorted(nodes, key=key, reverse=True)[:limit]
    return [
        {
            "slug": node["slug"],
            "name": node["name"],
            "followers": node["in"],
            "following": node["out"],
            "core": node["core"],
            "rank": node["rank"],
            "authority": node["authority"],
            "hub": node["hub"],
        }
        for node in picked
    ]


def graph_payload(graph: dict[str, Any], db_path: Path) -> dict[str, Any]:
    return {
        "generatedAt": graph["metrics"]["generatedAt"],
        "source": str(db_path),
        "counts": graph["metrics"]["counts"],
        "nodes": graph["nodes"],
        "edges": graph["edges"],
    }


def row_link(person: dict[str, Any]) -> str:
    name = html.escape(person["name"])
    slug = html.escape(person["slug"])
    return f'<a href="https://curius.app/users/{slug}" target="_blank" rel="noreferrer">{name}</a><br><span class="quiet">{slug}</span>'


def pagerank_rows(people: list[dict[str, Any]]) -> str:
    rows = []
    for i, person in enumerate(people, 1):
        rows.append(
            f"<tr><td>{i}</td><td>{row_link(person)}</td><td>{fmt_int(person['followers'])}</td>"
            f"<td>{fmt_int(person['following'])}</td><td>{person['rank']:.3e}</td></tr>"
        )
    return "\n        ".join(rows)


def follower_rows(people: list[dict[str, Any]]) -> str:
    rows = []
    for i, person in enumerate(people, 1):
        rows.append(
            f"<tr><td>{i}</td><td>{row_link(person)}</td><td>{fmt_int(person['followers'])}</td>"
            f"<td>{fmt_int(person['following'])}</td><td>{fmt_int(person['core'])}</td></tr>"
        )
    return "\n        ".join(rows)


def authority_rows(people: list[dict[str, Any]]) -> str:
    rows = []
    for i, person in enumerate(people[:8], 1):
        rows.append(
            f"<tr><td>{i}</td><td>{row_link(person)}</td><td>{fmt_int(person['followers'])}</td>"
            f"<td>{person['authority']:.3f}</td></tr>"
        )
    return "\n        ".join(rows)


def hub_rows(people: list[dict[str, Any]]) -> str:
    rows = []
    for i, person in enumerate(people[:8], 1):
        rows.append(
            f"<tr><td>{i}</td><td>{row_link(person)}</td><td>{fmt_int(person['following'])}</td>"
            f"<td>{person['hub']:.3f}</td></tr>"
        )
    return "\n        ".join(rows)


def bridge_rows(rows: list[dict[str, Any]]) -> str:
    return "\n        ".join(
        f"<tr><td>{i}</td><td>{row_link(person)}</td><td>{fmt_float(person['score'], 3)}</td><td>{fmt_int(person['followers'])}</td><td>{fmt_int(person['core'])}</td></tr>"
        for i, person in enumerate(rows[:8], 1)
    )


def missing_follow_rows(rows: list[dict[str, Any]]) -> str:
    return "\n        ".join(
        f"<tr><td>{i}</td><td>{row_link(row['source'])}</td><td>{row_link(row['target'])}</td><td>{fmt_int(row['score'])}</td><td>{fmt_int(row['targetFollowers'])}</td></tr>"
        for i, row in enumerate(rows[:8], 1)
    )


def surprising_follow_rows(rows: list[dict[str, Any]]) -> str:
    return "\n        ".join(
        f"<tr><td>{i}</td><td>{row_link(row['source'])}</td><td>{row_link(row['target'])}</td><td>{fmt_int(row['support'])}</td><td>{fmt_int(row['sourceFollowing'])} → {fmt_int(row['targetFollowers'])}</td></tr>"
        for i, row in enumerate(rows[:8], 1)
    )


def community_rows(rows: list[dict[str, Any]]) -> str:
    out = []
    for row in rows[:6]:
        people = ", ".join(html.escape(person["name"]) for person in row["people"][:4])
        domains = ", ".join(domain for domain, _count in row["domains"][:4]) or "no saved-link domains"
        schools = ", ".join(school for school, _count in row["schools"][:2]) or "school not listed"
        out.append(f"<tr><td>{row['index']}</td><td>{fmt_int(row['size'])}</td><td>{html.escape(people)}</td><td>{html.escape(domains)}</td><td>{html.escape(schools)}</td></tr>")
    return "\n        ".join(out)


def domain_pills(rows: list[tuple[str, int | float]], limit: int = 10) -> str:
    return "".join(f"<span class=\"tag\">{html.escape(str(domain))} · {fmt_int(int(value))}</span>" for domain, value in rows[:limit])


def weighted_domain_pills(rows: list[tuple[str, float]], limit: int = 10) -> str:
    return "".join(f"<span class=\"tag\">{html.escape(domain)} · {fmt_pct(value, 2)}</span>" for domain, value in rows[:limit])


def json_script(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")


def app_url(base: str, page: str = "index.html") -> str:
    return f"{base.rstrip('/')}/{page}"


def render_graph_html(graph: dict[str, Any], db_path: Path, frontpage_url: str = DEFAULT_FRONTPAGE_URL) -> str:
    payload = graph_payload(graph, db_path)
    return (
        GRAPH_HTML.replace("__PAPER_CSS__", PAPER_CSS)
        .replace("__FRONTPAGE_INDEX_URL__", app_url(frontpage_url))
        .replace("__GRAPH_JSON__", json_script(payload))
    )


def render_frontpage_html(payload: dict[str, Any], analysis_url: str = DEFAULT_ANALYSIS_URL) -> str:
    replacements = {
        "__PAPER_CSS__": PAPER_CSS,
        "__ANALYSIS_INDEX_URL__": app_url(analysis_url),
        "__ANALYSIS_METRICS_URL__": app_url(analysis_url, "metrics.html"),
        "__ANALYSIS_ALGORITHMS_URL__": app_url(analysis_url, "algorithms.html"),
        "__ANALYSIS_QUESTIONS_URL__": app_url(analysis_url, "questions.html"),
        "__FRONTPAGE_JSON__": json_script(payload),
    }
    out = FRONTPAGE_HTML
    for old, new in replacements.items():
        out = out.replace(old, new)
    return out


def algorithms_payload(graph: dict[str, Any]) -> dict[str, Any]:
    return {
        "counts": graph["metrics"]["counts"],
        "nodes": [
            {
                "id": node["id"], "slug": node["slug"], "name": node["name"], "school": node["school"],
                "in": node["in"], "out": node["out"], "core": node["core"],
            }
            for node in graph["nodes"]
        ],
        "edges": graph["edges"],
    }


def render_metrics_html(graph: dict[str, Any], frontpage_url: str = DEFAULT_FRONTPAGE_URL) -> str:
    metrics = graph["metrics"]
    replacements = {
        "__PAPER_CSS__": PAPER_CSS,
        "__FRONTPAGE_INDEX_URL__": app_url(frontpage_url),
        "__METRICS_JSON__": json_script({"metrics": metrics}),
        "__NODES__": fmt_int(metrics["counts"]["nodes"]),
        "__EDGES__": fmt_int(metrics["counts"]["edges"]),
        "__AVG_IN__": fmt_float(metrics["averageIn"], 2),
        "__AVG_OUT__": fmt_float(metrics["averageOut"], 2),
        "__DENSITY_PCT__": fmt_pct(metrics["density"], 3),
        "__RECIPROCITY_PCT__": fmt_pct(metrics["reciprocity"], 1),
        "__RECIPROCAL_EDGES__": fmt_int(metrics["reciprocalEdges"]),
        "__LARGEST_WEAK_PCT__": fmt_pct(metrics["largestWeak"] / metrics["counts"]["nodes"] if metrics["counts"]["nodes"] else 0, 1),
        "__WEAK_COMPONENTS__": fmt_int(metrics["weakComponents"]),
        "__LARGEST_WEAK__": fmt_int(metrics["largestWeak"]),
        "__STRONG_COMPONENTS__": fmt_int(metrics["strongComponents"]),
        "__LARGEST_STRONG__": fmt_int(metrics["largestStrong"]),
        "__CLUSTERING__": fmt_float(metrics["meanClustering"], 3),
        "__TRANSITIVITY__": fmt_float(metrics["transitivity"], 3),
        "__MAX_CORE__": fmt_int(metrics["maxCore"]),
        "__MAX_CORE_COUNT__": fmt_int(metrics["maxCoreCount"]),
        "__PAGERANK_ROWS__": pagerank_rows(metrics["topPageRank"]),
        "__FOLLOWER_ROWS__": follower_rows(metrics["topFollowers"]),
    }
    out = METRICS_HTML
    for old, new in replacements.items():
        out = out.replace(old, new)
    return out


def render_next_html(graph: dict[str, Any], frontpage_url: str = DEFAULT_FRONTPAGE_URL) -> str:
    metrics = graph["metrics"]
    next_data = metrics["nextAnalyses"]
    interest = next_data["interest"]
    top_bridge = next_data["bridges"][0] if next_data["bridges"] else {"name": "No bridge computed", "score": 0}
    top_missing = next_data["missingFollows"][0] if next_data["missingFollows"] else None
    top_missing_text = f"{top_missing['source']['name']} → {top_missing['target']['name']}" if top_missing else "No missing follow scored"
    replacements = {
        "__PAPER_CSS__": PAPER_CSS,
        "__FRONTPAGE_INDEX_URL__": app_url(frontpage_url),
        "__NODES__": fmt_int(metrics["counts"]["nodes"]),
        "__EDGES__": fmt_int(metrics["counts"]["edges"]),
        "__LARGEST_WEAK__": fmt_int(metrics["largestWeak"]),
        "__BRIDGE_TOP__": html.escape(top_bridge["name"]),
        "__BRIDGE_SCORE__": fmt_float(float(top_bridge.get("score", 0)), 3),
        "__BRIDGE_ROWS__": bridge_rows(next_data["bridges"]),
        "__MISSING_TOP__": html.escape(top_missing_text),
        "__MISSING_ROWS__": missing_follow_rows(next_data["missingFollows"]),
        "__SURPRISING_ROWS__": surprising_follow_rows(next_data["surprisingFollows"]),
        "__COMMUNITY_COUNT__": fmt_int(next_data["communityCount"]),
        "__MODULARITY__": fmt_float(next_data["modularity"], 3),
        "__COMMUNITY_ROWS__": community_rows(next_data["communities"]),
        "__INTEREST_KNOWN__": fmt_int(interest["knownEdges"]),
        "__INTEREST_OVERLAP__": fmt_pct(interest["overlapShare"], 1),
        "__SHARED_DOMAINS__": domain_pills(interest["sharedDomains"]),
        "__CROSS_SHARED_DOMAINS__": domain_pills(interest["crossSharedDomains"]),
        "__WEIGHTED_DOMAINS__": weighted_domain_pills(interest["weightedDomains"]),
    }
    out = NEXT_HTML
    for old, new in replacements.items():
        out = out.replace(old, new)
    return out


def render_algorithms_html(graph: dict[str, Any], frontpage_url: str = DEFAULT_FRONTPAGE_URL) -> str:
    metrics = graph["metrics"]
    path_stats = metrics["pathStats"]
    bow_tie = metrics["bowTie"]
    school = metrics["schoolHomophily"]
    replacements = {
        "__PAPER_CSS__": PAPER_CSS,
        "__FRONTPAGE_INDEX_URL__": app_url(frontpage_url),
        "__ALGORITHMS_JSON__": json_script(algorithms_payload(graph)),
        "__PATH_AVG__": fmt_float(path_stats["average"], 2),
        "__PATH_P90__": fmt_int(path_stats["p90"]),
        "__PATH_DIAM__": fmt_int(path_stats["diameter"]),
        "__PATH_PAIRS__": fmt_int(path_stats["pairs"]),
        "__SCC__": fmt_int(bow_tie["scc"]),
        "__IN_SCC__": fmt_int(bow_tie["in"]),
        "__OUT_SCC__": fmt_int(bow_tie["out"]),
        "__TENDRILS__": fmt_int(bow_tie["tendrils"]),
        "__LARGEST_WEAK__": fmt_int(metrics["largestWeak"]),
        "__WEAK_COMPONENTS__": fmt_int(metrics["weakComponents"]),
        "__AUTHORITY_ROWS__": authority_rows(metrics["topAuthorities"]),
        "__HUB_ROWS__": hub_rows(metrics["topHubs"]),
        "__SCHOOL_KNOWN__": fmt_int(school["knownEdges"]),
        "__SCHOOL_SAME_PCT__": fmt_pct(school["sameShare"], 1),
        "__SCHOOL_EXPECTED_PCT__": fmt_pct(school["expectedShare"], 1),
    }
    out = ALGORITHMS_HTML
    for old, new in replacements.items():
        out = out.replace(old, new)
    return out


def build(
    db_path: Path,
    graph_out: Path,
    metrics_out: Path,
    algorithms_out: Path,
    next_out: Path,
    frontpage_out: Path = DEFAULT_FRONTPAGE_OUT,
    frontpage_url: str = DEFAULT_FRONTPAGE_URL,
    analysis_url: str = DEFAULT_ANALYSIS_URL,
) -> dict[str, Any]:
    if not db_path.exists():
        raise SystemExit(f"Database not found: {db_path}")
    frontpage = load_frontpage(db_path)
    user_domains = load_user_domains(db_path)
    nodes, edges = load_graph(db_path)
    graph = enrich(nodes, edges, user_domains)
    graph_out.parent.mkdir(parents=True, exist_ok=True)
    metrics_out.parent.mkdir(parents=True, exist_ok=True)
    algorithms_out.parent.mkdir(parents=True, exist_ok=True)
    next_out.parent.mkdir(parents=True, exist_ok=True)
    frontpage_out.parent.mkdir(parents=True, exist_ok=True)
    graph_out.write_text(render_graph_html(graph, db_path, frontpage_url), encoding="utf-8")
    metrics_out.write_text(render_metrics_html(graph, frontpage_url), encoding="utf-8")
    algorithms_out.write_text(render_algorithms_html(graph, frontpage_url), encoding="utf-8")
    next_out.write_text(render_next_html(graph, frontpage_url), encoding="utf-8")
    frontpage_out.write_text(render_frontpage_html(frontpage, analysis_url), encoding="utf-8")
    return graph


def self_test() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "test.sqlite"
        conn = sqlite3.connect(db)
        conn.executescript(
            """
            CREATE TABLE users (
                user_id INTEGER PRIMARY KEY, user_link TEXT UNIQUE, first_name TEXT, last_name TEXT,
                school TEXT, github TEXT, twitter TEXT, website TEXT, num_followers INTEGER
            );
            CREATE TABLE follows (follower_user_id INTEGER, followed_user_id INTEGER);
            CREATE TABLE links (
                link_id INTEGER PRIMARY KEY, url TEXT, title TEXT, snippet TEXT,
                created_at TEXT, modified_at TEXT, updated_at TEXT
            );
            CREATE TABLE saved_links (user_id INTEGER, link_id INTEGER);
            CREATE TABLE highlights (
                highlight_id INTEGER PRIMARY KEY, user_id INTEGER, link_id INTEGER,
                highlight_text TEXT, raw_highlight TEXT, left_context TEXT, right_context TEXT, created_at TEXT
            );
            INSERT INTO users VALUES (1, 'ada', 'Ada', 'Lovelace', 'Analytical Engine', '', '', '', 2);
            INSERT INTO users VALUES (2, 'grace', 'Grace', 'Hopper', 'Navy', '', '', '', 1);
            INSERT INTO users VALUES (3, 'alan', 'Alan', 'Turing', '', '', '', '', 0);
            INSERT INTO users VALUES (4, 'katherine', 'Katherine', 'Johnson', '', '', '', '', 0);
            INSERT INTO follows VALUES (2, 1), (3, 1), (1, 2), (4, 3);
            INSERT INTO links VALUES (10, 'https://example.com/engine', 'Notes on engines', 'A compact note.', '2026-07-15T00:00:00Z', NULL, '2026-07-15T00:00:00Z');
            INSERT INTO links VALUES (11, 'https://example.com/math', 'A new math note', 'Fresh note.', '2026-07-16T00:00:00Z', NULL, '2026-07-16T00:00:00Z');
            INSERT INTO saved_links VALUES (1, 10), (2, 10), (3, 11);
            INSERT INTO highlights VALUES (100, 1, 10, 'Readable programs are easier to repair.', NULL, 'A note says', 'when the pager rings.', '2026-07-15T01:00:00Z');
            INSERT INTO highlights VALUES (101, 2, 10, 'Readable programs are easier to repair.', NULL, 'Another note says', 'during review.', '2026-07-16T01:00:00Z');
            INSERT INTO highlights VALUES (102, 3, 11, 'Small checks catch large mistakes.', NULL, '', '', '2026-07-16T02:00:00Z');
            """
        )
        conn.close()
        graph_out = Path(tmp) / "graph.html"
        metrics_out = Path(tmp) / "metrics.html"
        algorithms_out = Path(tmp) / "algorithms.html"
        next_out = Path(tmp) / "next.html"
        frontpage_out = Path(tmp) / "frontpage.html"
        graph = build(
            db, graph_out, metrics_out, algorithms_out, next_out, frontpage_out,
            "https://front.example", "https://analysis.example",
        )
        graph_html = graph_out.read_text(encoding="utf-8")
        metrics_html = metrics_out.read_text(encoding="utf-8")
        algorithms_html = algorithms_out.read_text(encoding="utf-8")
        next_html = next_out.read_text(encoding="utf-8")
        frontpage_html = frontpage_out.read_text(encoding="utf-8")
        assert graph["metrics"]["counts"] == {"nodes": 4, "edges": 4}
        assert graph["metrics"]["reciprocalEdges"] == 2
        assert "graph-data" in graph_html and "canvas" in graph_html and "Palatino" in graph_html
        assert "metrics-data" in metrics_html and "PageRank" in metrics_html and "Glossary" in metrics_html
        assert "algorithms-data" in algorithms_html and "Graph workbench" in algorithms_html and "HITS" in algorithms_html
        assert "Curius next graph questions" in next_html and "Who bridges separate islands?" in next_html
        assert "frontpage-data" in frontpage_html and "Curius Front Page" in frontpage_html and "See more Curius things" in frontpage_html and "Small ranking model" in frontpage_html
        assert 'href="https://front.example/index.html"' in graph_html + metrics_html + algorithms_html + next_html
        assert 'href="https://analysis.example/metrics.html"' in frontpage_html
        assert "ui-sans-serif" not in graph_html + metrics_html + algorithms_html + next_html + frontpage_html
    print("self-test passed")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="SQLite database path")
    parser.add_argument("--graph-out", type=Path, default=DEFAULT_GRAPH_OUT, help="graph HTML output path")
    parser.add_argument("--metrics-out", type=Path, default=DEFAULT_METRICS_OUT, help="metrics HTML output path")
    parser.add_argument("--algorithms-out", type=Path, default=DEFAULT_ALGORITHMS_OUT, help="algorithms HTML output path")
    parser.add_argument("--next-out", type=Path, default=DEFAULT_NEXT_OUT, help="next-questions HTML output path")
    parser.add_argument("--frontpage-out", type=Path, default=DEFAULT_FRONTPAGE_OUT, help="front page HTML output path")
    parser.add_argument("--frontpage-url", default=os.environ.get("CURIUS_FRONTPAGE_URL", DEFAULT_FRONTPAGE_URL), help="base URL for links from analysis to frontpage")
    parser.add_argument("--analysis-url", default=os.environ.get("CURIUS_ANALYSIS_URL", DEFAULT_ANALYSIS_URL), help="base URL for links from frontpage to analysis")
    parser.add_argument("--self-test", action="store_true", help="run a tiny generated-db check")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    graph = build(
        args.db, args.graph_out, args.metrics_out, args.algorithms_out, args.next_out, args.frontpage_out,
        args.frontpage_url, args.analysis_url,
    )
    counts = graph["metrics"]["counts"]
    print(f"Wrote {args.frontpage_out}, {args.graph_out}, {args.metrics_out}, {args.algorithms_out}, and {args.next_out} ({counts['nodes']:,} people, {counts['edges']:,} follows)")


if __name__ == "__main__":
    main()
