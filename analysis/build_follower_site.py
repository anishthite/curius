#!/usr/bin/env python3
"""Generate static Curius follower graph pages."""

from __future__ import annotations

import argparse
import os
import heapq
import html
import json
import re
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
DEFAULT_ABOUT_OUT = DEFAULT_ANALYSIS_APP / "about.html"
DEFAULT_FRONTPAGE_OUT = DEFAULT_FRONTPAGE_APP / "index.html"
DEFAULT_HOW_OUT = DEFAULT_FRONTPAGE_APP / "how-this-works.html"
DEFAULT_ABOUT_COPY_FILE = REPO_ROOT / "analysis/about_copy.json"
# The deployed Workers preserve the two existing public hostnames.
DEFAULT_ANALYSIS_URL = "https://curius-graph.thite.site"
DEFAULT_FRONTPAGE_URL = "https://curius-links.thite.site"
GOLDEN_ANGLE = math.pi * (3 - math.sqrt(5))
POSTHOG_HTML = """
<script>
  if (!["localhost", "127.0.0.1", "::1"].includes(window.location.hostname)) {
    !function(t,e){var o,n,p,r;e.__SV||(window.posthog=e,e._i=[],e.init=function(i,s,a){function g(t,e){var o=e.split(".");2==o.length&&(t=t[o[0]],e=o[1]),t[e]=function(){t.push([e].concat(Array.prototype.slice.call(arguments,0)))}}(p=t.createElement("script")).type="text/javascript",p.crossOrigin="anonymous",p.async=!0,p.src=s.api_host.replace(".i.posthog.com","-assets.i.posthog.com")+"/static/array.js",(r=t.getElementsByTagName("script")[0]).parentNode.insertBefore(p,r);var u=e;for(void 0!==a?u=e[a]=[]:a="posthog",u.people=u.people||[],u.toString=function(t){var e="posthog";return"posthog"!==a&&(e+="."+a),t||(e+=" (stub)"),e},u.people.toString=function(){return u.toString(1)+".people (stub)"},o="init capture register register_once register_for_session unregister unregister_for_session getFeatureFlag getFeatureFlagResult isFeatureEnabled reloadFeatureFlags updateEarlyAccessFeatureEnrollment getEarlyAccessFeatures on onFeatureFlags onSessionId getSurveys getActiveMatchingSurveys renderSurvey canRenderSurvey getNextSurveyStep identify setPersonProperties group resetGroups setPersonPropertiesForFlags resetPersonPropertiesForFlags setGroupPropertiesForFlags resetGroupPropertiesForFlags reset get_distinct_id getGroups get_session_id get_session_replay_url alias set_config startSessionRecording stopSessionRecording sessionRecordingStarted captureException loadToolbar get_property getSessionProperty createPersonProfile opt_in_capturing opt_out_capturing has_opted_in_capturing has_opted_out_capturing clear_opt_in_out_capturing debug".split(" "),n=0;n<o.length;n++)g(u,o[n]);e._i.push([i,s,a])},e.__SV=1)}(document,window.posthog||[]);
    posthog.init("phc_lwrp8rJxreMnGicmxPIe8YksCzEnpjdZJKTG5Tn3Nps", {
      api_host: "https://us.i.posthog.com",
      defaults: "2026-05-30",
      person_profiles: "identified_only"
    });
  }
</script>
"""

DEFAULT_ABOUT_COPY = {
    "frontpage": {
        "subheader": "A public readout of what Curius readers are saving, marking, and returning to.",
        "seeMoreLabel": "See more",
    },
    "graph": {
        "subheader": "The social network from",
        "seeMoreText": "See more about the data",
    },
    "about": {
        "title": "About the Curius Graph",
        "lede": "This is a public follower graph of curius.app, updated July 28, 2026 at 11:59 AM PDT.",
        "paragraphs": [],
        "followersHeading": "Most followed people",
        "followersCopy": "",
        "domainsHeading": "Most popular saved-link domains",
        "domainsCopy": "",
    },
}

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
    .nav a { display: inline-flex; align-items: center; min-height: 44px; }
    table { font-size: .9rem; }
  }
"""

GRAPH_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="#ffffff">
<title>The Curius Follower Graph</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=Lora:wght@400;500;600&family=Source+Sans+Pro:wght@400;600;700&display=swap" rel="stylesheet">
<style>
__PAPER_CSS__
  body { background: var(--paper); }
  .graph-page { --reader-width: clamp(310px, 23vw, 380px); display: grid; grid-template-rows: auto auto auto minmax(0, 1fr); width: min(1640px, 100%); min-height: 100vh; height: 100vh; padding: 12px clamp(8px, 1.5vw, 20px) 0; }
  .graph-page.has-selection { padding-right: calc(var(--reader-width) + clamp(20px, 2vw, 34px)); }
  .graph-hero { text-align: left; margin: 0 0 .35rem; }
  .graph-hero h1 { font-size: clamp(2.1rem, 5.6vw, 4.45rem); margin: .08rem 0 .12rem; }
  .graph-subhead { max-width: 82ch; margin: 0 0 .55rem; color: var(--muted); font-size: clamp(.96rem, 1.4vw, 1.08rem); line-height: 1.34; }
  .graph-subhead a { color: var(--ink); }
  .graph-layout { display: grid; grid-template-columns: minmax(0, 1fr); gap: .75rem; min-height: 0; align-items: stretch; }
  .graph-tools { display: flex; flex-wrap: wrap; gap: .4rem; margin: .25rem 0 .35rem; align-items: center; max-width: 940px; padding: .05rem 0; background: transparent; }
  .graph-tools input, .graph-tools select, .graph-tools button { min-height: 34px; padding: .24rem .62rem; border: 0; font-size: .9rem; background: rgba(255, 252, 245, .76); }
  .graph-tools button:hover, .graph-tools input:hover, .graph-tools select:hover { background: rgba(255, 252, 245, .98); }
  .graph-tools .clear-person, .reader .clear-person { min-height: 0; border: 0; padding: 0 .1rem; background: transparent; color: var(--muted); font-size: .78rem; text-decoration: underline; text-underline-offset: .16em; }
  .graph-tools .clear-person:hover, .graph-tools .clear-person:focus-visible, .reader .clear-person:hover, .reader .clear-person:focus-visible { color: var(--blue); background: transparent; }
  #q { flex: 1 1 320px; max-width: none; }
  .min-filter { display: flex; grid-template-columns: none; gap: .32rem; align-items: center; color: var(--muted); font-size: .85rem; }
  .min-filter span { white-space: nowrap; }
  #min-followers { width: 7ch; }
  #mode { width: 10.2rem; }
  #fit { width: auto; min-width: 58px; }
  .canvas-wrap { position: relative; height: 100%; min-height: 0; margin: 0; overflow: hidden; touch-action: none; }
  .canvas-wrap.sheet { border: 0; border-radius: 10px 10px 0 0; box-shadow: none; background: rgba(255, 250, 240, .16); }
  .graph-canvas { position: relative; display: block; width: 100%; height: 100%; min-height: 0; border-radius: 10px; cursor: grab; overflow: hidden; background: #fffaf0; touch-action: none; }
  .graph-page.has-matches .canvas-wrap { min-height: 0; }
  .graph-page.has-matches .graph-canvas { height: 100%; }
  .graph-canvas:active { cursor: grabbing; }
  .graph-canvas canvas { position: absolute; inset: 0; display: block; width: 100%; height: 100%; border-radius: 10px; transform-origin: 0 0; will-change: transform; }
  .canvas-note { position: absolute; left: .65rem; right: .65rem; bottom: .6rem; color: var(--muted); background: rgba(255,250,240,.78); border: 0; border-radius: 8px; padding: .42rem .6rem; font-size: .9rem; box-shadow: 0 1px 8px rgba(60, 42, 20, .05); }
  .canvas-note b { color: var(--ink); font-weight: 500; }
  .graph-legend { display: flex; flex-wrap: wrap; gap: .28rem .7rem; align-items: center; }
  .legend-key { display: inline-flex; gap: .28rem; align-items: center; white-space: nowrap; }
  .legend-dot { width: .62rem; height: .62rem; border-radius: 999px; display: inline-block; box-shadow: 0 0 0 1px rgba(32, 23, 15, .12); }
  .legend-dot.selected { background: #9f3f26; }
  .legend-dot.follower { background: #254f98; }
  .legend-dot.following { background: #1c653d; }
  .legend-dot.mutual { background: #5e398f; }
  .legend-dot.other { background: #5f5140; opacity: .85; }
  .reader { position: fixed; inset: 0 0 0 auto; z-index: 12; display: flex; flex-direction: column; width: var(--reader-width); height: 100vh; margin: 0; overflow: hidden; padding: 20px 18px 24px; border-left: 0; background: rgba(255, 250, 240, .92); box-shadow: -12px 0 28px rgba(60, 42, 20, .08); font-size: .94rem; }
  .reader[hidden] { display: none; }
  .reader-head { display: flex; align-items: baseline; justify-content: space-between; gap: .6rem; }
  .reader h2 { margin-top: 0; }
  .counts { display: grid; grid-template-columns: repeat(3, 1fr); gap: .35rem; margin: .45rem 0; }
  .count { position: relative; padding: .28rem .32rem; border-radius: 8px; background: rgba(255, 250, 240, .52); }
  .count b { display: block; font-size: 1.16rem; font-weight: 500; line-height: 1.05; }
  .count span { color: var(--muted); font-size: .78rem; }
  .info-dot {
    display: inline-grid;
    place-items: center;
    width: 1rem;
    height: 1rem;
    min-height: 0;
    margin-left: .18rem;
    padding: 0;
    border: 1px solid rgba(111, 98, 84, .5);
    border-radius: 999px;
    background: rgba(255, 252, 245, .92);
    color: var(--muted);
    font-size: .68rem;
    font-style: italic;
    line-height: 1;
    vertical-align: .08rem;
    cursor: help;
  }
  .info-dot:hover, .info-dot:focus-visible { background: rgba(255, 252, 245, 1); outline: 2px solid rgba(47, 99, 183, .24); outline-offset: 2px; }
  .info-tooltip {
    position: absolute;
    right: 0;
    top: calc(100% + .38rem);
    width: min(260px, calc(100vw - 2rem));
    padding: .5rem .58rem;
    border: 1px solid var(--rule);
    border-radius: 8px;
    background: rgba(255, 252, 245, .98);
    box-shadow: 0 8px 22px rgba(60, 42, 20, .13);
    color: var(--ink);
    font-size: .82rem;
    font-style: normal;
    line-height: 1.28;
    text-align: left;
    visibility: hidden;
    opacity: 0;
    transform: translateY(-2px);
    transition: opacity .14s ease, transform .14s ease, visibility .14s ease;
    z-index: 4;
  }
  .info-dot:hover .info-tooltip, .info-dot:focus .info-tooltip { visibility: visible; opacity: 1; transform: translateY(0); }
  .reader .people-section { position: relative; display: flex; flex: 0 1 auto; min-height: 0; flex-direction: column; margin-top: .95rem; }
  .reader .people-section h3 { flex: 0 0 auto; }
  .reader .people-section::after { content: none; }
  .reader .people-section .people { flex: 0 1 auto; min-height: 0; max-height: clamp(150px, 28vh, 290px); }
  .people { display: grid; gap: .32rem; max-height: clamp(220px, 34vh, 360px); overflow: auto; overscroll-behavior: contain; padding: .18rem .22rem .5rem 0; border-radius: 8px; scrollbar-gutter: stable; box-shadow: none; }
  .people::-webkit-scrollbar { width: 8px; }
  .people::-webkit-scrollbar-thumb { border-radius: 999px; background: rgba(111, 98, 84, .34); }
  .person { display: grid; align-content: center; gap: .12rem; width: 100%; min-height: 3.12rem; border: 0; border-radius: 8px; text-align: left; padding: .38rem .5rem; background: transparent; }
  .person:hover { outline: 0; background: rgba(255, 252, 245, .96); }
  .person:focus-visible { outline: 0; background: rgba(255, 252, 245, .96); box-shadow: inset 0 0 0 2px rgba(47, 99, 183, .3); }
  .person span { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: .95rem; line-height: 1.08; }
  .person small { display: block; overflow: hidden; color: var(--muted); text-overflow: ellipsis; white-space: nowrap; font-size: .76rem; line-height: 1.12; }
  .matches { max-width: min(980px, 100%); margin: .05rem 0 .55rem; padding: 0 .12rem .16rem 0; }
  .matches[hidden] { display: none; }
  .matches.people { display: flex; flex-wrap: wrap; gap: .32rem; max-height: 118px; overflow: auto; box-shadow: none; }
  .matches .person { flex: 0 1 320px; max-width: 320px; min-height: 0; padding: .46rem .62rem; }
  .matches .person span { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 1rem; line-height: 1.12; }
  .matches .person small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: .8rem; }
  .profile-links { display: flex; flex-wrap: wrap; gap: .25rem .55rem; margin: .3rem 0; }
  .profile-links a { white-space: nowrap; }
  .reader-footer { flex: 0 0 auto; margin-top: .8rem; padding-top: .8rem; color: var(--muted); border-top: 1px solid rgba(216, 200, 181, .62); font-size: .78rem; line-height: 1.3; }
  .reader.is-empty .reader-footer { margin-top: auto; }
  .reader-footer a { color: var(--muted); }
  .legend { display: flex; gap: .8rem; flex-wrap: wrap; color: var(--muted); margin: .4rem 0 .7rem; }
  .dot { width: .7rem; height: .7rem; display: inline-block; border-radius: 999px; margin-right: .25rem; vertical-align: -.04rem; }
  @media (max-width: 1280px) {
    .graph-hero h1 { font-size: clamp(2.1rem, 4.8vw, 3.8rem); }
    .graph-subhead { font-size: clamp(.96rem, 1.18vw, 1.04rem); }
  }
  @media (max-width: 920px) {
    .graph-page, .graph-page.has-selection { display: block; min-height: 0; height: auto; padding: 12px 12px 48px; }
    .graph-hero { margin-bottom: .55rem; }
    .graph-hero h1 { font-size: clamp(1.9rem, 8vw, 3rem); }
    .graph-subhead { font-size: .98rem; line-height: 1.28; }
    .graph-layout { grid-template-columns: 1fr; gap: 1rem; }
    .graph-tools { border-radius: 18px; gap: .55rem; margin: .35rem 0 .8rem; }
    .graph-tools input, .graph-tools select, .graph-tools button { min-height: 46px; padding: .48rem .82rem; font-size: 1rem; }
    .min-filter { min-height: 44px; font-size: .94rem; }
    #q { max-width: none; }
    .reader { display: block; position: static; width: auto; height: auto; max-height: none; margin-top: 1.1rem; overflow: visible; padding: .9rem .85rem 1rem; border: 1px solid rgba(216, 200, 181, .48); border-radius: 10px; background: rgba(255, 250, 240, .54); box-shadow: none; font-size: 1rem; }
    .reader .people-section { display: block; min-height: 0; }
    .reader .people-section .people { max-height: clamp(220px, 38vh, 320px); overflow: auto; }
    .canvas-wrap { height: auto; min-height: clamp(400px, 58vh, 540px); }
    .graph-canvas { height: clamp(400px, 58vh, 540px); min-height: 0; }
    .canvas-note { left: .5rem; right: .5rem; bottom: .5rem; padding: .36rem .5rem; font-size: .84rem; }
    .graph-legend { gap: .18rem .55rem; }
  }
  @media (max-width: 520px) {
    .graph-page { padding-left: 14px; padding-right: 14px; }
    .graph-tools { display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: stretch; gap: .5rem; }
    #q { grid-column: 1 / -1; width: 100%; }
    .graph-tools input, .graph-tools select, .graph-tools button { min-height: 46px; padding: .46rem .66rem; }
    #q { min-height: 48px; padding: .52rem .72rem; }
    .min-filter { grid-column: 1 / -1; display: grid; grid-template-columns: auto minmax(0, 1fr); min-height: 44px; gap: .5rem; min-width: 0; }
    .min-filter span { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    #min-followers { width: 100%; text-align: center; }
    #mode { width: 100%; min-width: 0; }
    #fit { min-width: 62px; }
    .matches { margin-bottom: .85rem; padding: .55rem 0; }
    .matches.people { display: grid; grid-template-columns: 1fr; max-height: none; overflow: visible; }
    .matches .person { max-width: 100%; }
    .person { min-height: 3.4rem; padding: .5rem .62rem; }
    .canvas-wrap { min-height: clamp(430px, 62vh, 560px); }
    .graph-canvas { height: clamp(430px, 62vh, 560px); }
    .legend-key { display: none; }
  }

  /* Match the original Curius app: bright canvas, editorial type, and a single yellow accent. */
  :root {
    --paper: #ffffff;
    --sheet: #ffffff;
    --ink: #161616;
    --muted: #8b8b8b;
    --rule: #ededed;
    --soft: #fafafa;
    --blue: #161616;
    --green: #161616;
    --highlight: #ffdf00;
  }
  body {
    background: #fff;
    color: var(--ink);
    font-family: "Source Sans Pro", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    font-size: 15px;
    line-height: 1.45;
  }
  a { color: inherit; }
  .graph-page {
    --reader-width: clamp(310px, 23vw, 380px);
    width: min(1360px, 100%);
    padding: 17px clamp(18px, 3vw, 32px) 0;
  }
  .graph-page.has-selection { padding-right: calc(var(--reader-width) + clamp(22px, 3vw, 42px)); }
  .graph-hero { margin: 0; }
  .graph-topbar { display: flex; align-items: center; justify-content: space-between; gap: 1rem; min-height: 44px; padding-bottom: 10px; border-bottom: 1px solid var(--rule); }
  .graph-wordmark { color: var(--ink); font-size: 20px; font-weight: 600; letter-spacing: -.025em; text-decoration: none; }
  .graph-nav { display: flex; gap: 1rem; align-items: center; font-size: 14px; }
  .graph-nav a { color: #777; text-decoration: none; }
  .graph-nav a:hover, .graph-nav a:focus-visible { color: var(--ink); text-decoration: underline; text-underline-offset: .18em; }
  .graph-intro { padding: 24px 0 13px; }
  .graph-eyebrow { margin: 0 0 7px; color: #777; font-family: "IBM Plex Mono", monospace; font-size: 11px; letter-spacing: .02em; text-transform: uppercase; }
  .graph-hero h1 { margin: 0; color: var(--ink); font-family: Lora, Georgia, serif; font-size: clamp(1.9rem, 3.8vw, 3.25rem); font-weight: 400; letter-spacing: -.04em; line-height: 1.16; }
  .graph-subhead { max-width: 60ch; margin: 8px 0 0; color: #666; font-size: 15px; line-height: 1.45; }
  .graph-subhead a { color: var(--ink); text-decoration-color: var(--highlight); text-decoration-thickness: 2px; text-underline-offset: .14em; }
  .graph-tools { gap: 6px; max-width: none; margin: 0 0 10px; padding: 0; }
  .graph-tools input, .graph-tools select, .graph-tools button {
    min-height: 34px;
    border: 1px solid #e7e7e7;
    border-radius: 2px;
    background: #fff;
    color: var(--ink);
    font-family: "Source Sans Pro", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    font-size: 14px;
  }
  .graph-tools input:hover, .graph-tools select:hover, .graph-tools button:hover { background: var(--soft); }
  .graph-tools input:focus-visible, .graph-tools select:focus-visible, .graph-tools button:focus-visible, .graph-wordmark:focus-visible, .graph-nav a:focus-visible { outline: 2px solid rgba(0, 0, 0, .42); outline-offset: 2px; }
  #q { flex-basis: 360px; }
  .min-filter { color: #777; font-family: "IBM Plex Mono", monospace; font-size: 11px; }
  #fit { border-color: var(--ink); background: var(--highlight); box-shadow: 3px 3px 0 var(--highlight); }
  #fit:hover { background: var(--highlight); }
  .graph-tools .clear-person, .reader .clear-person { color: #777; font-family: "IBM Plex Mono", monospace; font-size: 11px; }
  .graph-tools .clear-person:hover, .graph-tools .clear-person:focus-visible, .reader .clear-person:hover, .reader .clear-person:focus-visible { color: var(--ink); }
  .canvas-wrap.sheet { border: 1px solid var(--rule); border-radius: 0; background: #fff; }
  .graph-canvas { border-radius: 0; background: #fff; }
  .graph-canvas canvas { border-radius: 0; }
  .canvas-note { left: 10px; right: 10px; bottom: 10px; padding: 7px 9px; border: 1px solid var(--rule); border-radius: 0; background: rgba(255, 255, 255, .94); box-shadow: none; color: #777; font-family: "Source Sans Pro", sans-serif; font-size: 13px; }
  .canvas-note b { color: var(--ink); font-weight: 600; }
  .legend-dot { border-radius: 50%; box-shadow: 0 0 0 1px rgba(0, 0, 0, .14); }
  .legend-dot.selected { background: #e2bd00; }
  .legend-dot.follower { background: #555; }
  .legend-dot.following { background: #777; }
  .legend-dot.mutual { background: #2d2d2d; }
  .legend-dot.other { background: #555; }
  .reader { border-left: 1px solid var(--rule); background: rgba(255, 255, 255, .98); box-shadow: none; font-family: "Source Sans Pro", sans-serif; font-size: 14px; }
  .reader h2 { font-family: Lora, Georgia, serif; font-size: 26px; font-weight: 400; letter-spacing: -.03em; }
  .reader h3 { font-family: Lora, Georgia, serif; font-size: 17px; font-weight: 400; }
  .count { border-radius: 0; background: var(--soft); }
  .count b { font-weight: 600; }
  .info-dot { border-color: #bbb; border-radius: 50%; background: #fff; color: #777; }
  .info-dot:hover, .info-dot:focus-visible { background: var(--soft); outline-color: rgba(0, 0, 0, .28); }
  .info-tooltip { border-radius: 0; background: #fff; box-shadow: 0 8px 22px rgba(0, 0, 0, .09); }
  .people { border-radius: 0; }
  .people::-webkit-scrollbar-thumb { background: #cfcfcf; }
  .person { border-radius: 0; }
  .person:hover, .person:focus-visible { background: var(--soft); box-shadow: inset 2px 0 0 var(--highlight); }
  .reader-footer { border-top-color: var(--rule); color: #777; }
  .reader-footer a { color: inherit; }
  @media (max-width: 920px) {
    .graph-page, .graph-page.has-selection { padding: 14px 17px 42px; }
    .graph-topbar { min-height: 40px; padding-bottom: 8px; }
    .graph-wordmark { font-size: 18px; }
    .graph-nav { gap: .8rem; font-size: 13px; }
    .graph-intro { padding: 22px 0 12px; }
    .graph-hero h1 { font-size: clamp(1.85rem, 8vw, 2.7rem); }
    .graph-subhead { font-size: 14px; }
    .graph-tools { border-radius: 0; gap: 6px; margin-bottom: 12px; }
    .graph-tools input, .graph-tools select, .graph-tools button { min-height: 42px; font-size: 15px; }
    .reader { border: 1px solid var(--rule); border-radius: 0; background: #fff; }
  }
  @media (max-width: 520px) {
    .graph-page, .graph-page.has-selection { padding-left: 14px; padding-right: 14px; }
    .graph-tools { gap: 6px; }
    .graph-tools input, .graph-tools select, .graph-tools button, #q { min-height: 42px; }
    .min-filter { min-height: 42px; }
    .canvas-note { left: 7px; right: 7px; bottom: 7px; font-size: 12px; }
  }
</style>
__POSTHOG_HTML__
</head>
<body>
<div class="page graph-page">
  <header class="graph-hero">
    <div class="graph-topbar">
      <a class="graph-wordmark" href="https://curius.app" target="_blank" rel="noreferrer">Curius</a>
      <nav class="graph-nav" aria-label="Curius graph navigation"><a href="__FRONTPAGE_INDEX_URL__">Links</a><a href="about.html">About</a></nav>
    </div>
    <div class="graph-intro">
      <p class="graph-eyebrow">Community</p>
      <h1>Follower graph</h1>
      <p class="graph-subhead">__GRAPH_SUBHEADER__ <a href="https://curius.app" target="_blank" rel="noreferrer">curius.app</a>, visualized. <a href="about.html">__GRAPH_SEE_MORE_TEXT__</a>.</p>
    </div>
  </header>
  <section class="controls graph-tools" aria-label="Graph controls">
    <input id="q" type="search" autocomplete="off" placeholder="Search name or handle" aria-label="Search by name or handle">
    <button id="clear-selection" class="clear-person" type="button" hidden>Clear</button>
    <label class="min-filter"><span>Min followers</span><input id="min-followers" type="number" min="0" step="1" value="0" aria-label="Minimum followers" title="Minimum followers"></label>
    <select id="mode" aria-label="View"><option value="whole">whole graph</option><option value="ego">neighborhood</option><option value="followers">followers</option><option value="following">following</option></select>
    <button id="fit" type="button">Fit</button>
  </section>
  <div id="matches" class="matches people" aria-label="Search results" hidden></div>
  <section class="graph-layout">
    <figure class="canvas-wrap sheet">
      <div id="graph" class="graph-canvas" role="img" aria-label="Interactive follower graph"></div>
      <figcaption id="status" class="canvas-note"></figcaption>
    </figure>
    <aside id="reader" class="reader" hidden></aside>
  </section>
</div>
<script id="graph-data" type="application/json">__GRAPH_JSON__</script>
<script>
(() => {
  "use strict";
  const raw = JSON.parse(document.getElementById("graph-data").textContent);
  const graphPage = document.querySelector(".graph-page");
  const nodes = raw.nodes.map(n => ({...n, followers: [], following: []}));
  const byId = new Map(nodes.map(n => [n.id, n]));
  for (const [follower, followed] of raw.edges) {
    const a = byId.get(follower), b = byId.get(followed);
    if (!a || !b) continue;
    a.following.push(followed);
    b.followers.push(follower);
  }
  nodes.sort((a, b) => (b.in + b.out) - (a.in + a.out) || b.in - a.in || a.slug.localeCompare(b.slug));
  for (const n of nodes) {
    n.followersSet = new Set(n.followers);
    n.followingSet = new Set(n.following);
  }
  const graphStage = document.getElementById("graph");
  const webglCanvas = document.createElement("canvas");
  const overlayCanvas = document.createElement("canvas");
  webglCanvas.setAttribute("aria-hidden", "true");
  overlayCanvas.setAttribute("aria-hidden", "true");
  overlayCanvas.style.pointerEvents = "none";
  graphStage.append(webglCanvas, overlayCanvas);
  const gl = webglCanvas.getContext("webgl", {alpha: false, antialias: true, powerPreference: "high-performance"});
  const overlay = overlayCanvas.getContext("2d");
  const reader = document.getElementById("reader");
  const status = document.getElementById("status");
  const q = document.getElementById("q");
  const clearButton = document.getElementById("clear-selection");
  const minFollowers = document.getElementById("min-followers");
  const mode = document.getElementById("mode");
  const matches = document.getElementById("matches");
  const edgeRecords = raw.edges.map(([aId, bId]) => ({aId, bId, a: byId.get(aId), b: byId.get(bId)})).filter(edge => edge.a && edge.b);
  const view = {x: 0, y: 0, scale: 1};
  const canvasSize = {width: 1, height: 1, dpr: 1, graphDpr: 1};
  let selected = null;
  let visibleIds = new Set(nodes.map(n => n.id));
  let visibleList = nodes;
  let visibleEdges = edgeRecords;
  let visibleDirty = true;
  let graphDirty = true;
  const activePointers = new Map();
  let pointer = null;
  let pinch = null;
  let hover = null;
  let moving = false;
  let settleTimer = 0;
  let renderPending = false;
  let hoverEvent = null;
  let hoverPending = false;
  let edgeAlphaMode = "";
  let lastStatus = "";
  let edgeVertexCount = 0;
  let nodeVertexCount = 0;

  function label(n) { return n.name && n.name !== n.slug ? `${n.name} · ${n.slug}` : n.slug; }
  function profileUrl(n) { return `https://curius.app/users/${encodeURIComponent(n.slug)}`; }
  function degree(n) { return n.in + n.out; }
  function matchesText(n, term) { return `${n.name} ${n.slug}`.toLowerCase().includes(term); }
  function sortedPeople(ids) { return ids.map(id => byId.get(id)).filter(Boolean).sort((a, b) => degree(b) - degree(a) || a.slug.localeCompare(b.slug)); }
  function nodeRadius(n) { return Math.max(3, Math.min(14.5, 2.95 + Math.sqrt(Math.max(0, n.in)) * .34 + n.core * .2)); }
  function markVisibleDirty() { visibleDirty = true; graphDirty = true; }
  function ensureVisible() { if (visibleDirty) computeVisible(); }
  function computeVisible() {
    const min = Number(minFollowers.value) || 0;
    const center = selected && byId.get(selected);
    let ids;
    if (!center || mode.value === "whole") ids = nodes.filter(n => n.in >= min || n.id === center?.id).map(n => n.id);
    else if (mode.value === "followers") ids = [center.id, ...center.followers].filter(id => id === center.id || (byId.get(id)?.in || 0) >= min);
    else if (mode.value === "following") ids = [center.id, ...center.following].filter(id => id === center.id || (byId.get(id)?.in || 0) >= min);
    else ids = [center.id, ...center.followers, ...center.following].filter(id => id === center.id || (byId.get(id)?.in || 0) >= min);
    visibleIds = new Set(ids);
    visibleList = ids.map(id => byId.get(id)).filter(Boolean);
    visibleEdges = edgeRecords.filter(edge => visibleIds.has(edge.aId) && visibleIds.has(edge.bId));
    visibleDirty = false;
    graphDirty = true;
  }
  function visibleBBox() {
    computeVisible();
    if (!visibleList.length) return null;
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (const n of visibleList) { minX = Math.min(minX, n.x); minY = Math.min(minY, n.y); maxX = Math.max(maxX, n.x); maxY = Math.max(maxY, n.y); }
    const pad = 110;
    return {x: [minX - pad, maxX + pad], y: [minY - pad, maxY + pad]};
  }
  function fit(animate = true) {
    const bbox = visibleBBox();
    if (!bbox) return;
    const sx = (canvasSize.width - 48) / Math.max(1, bbox.x[1] - bbox.x[0]);
    const sy = (canvasSize.height - 48) / Math.max(1, bbox.y[1] - bbox.y[0]);
    view.scale = Math.max(.18, Math.min(3.5, Math.min(sx, sy)));
    view.x = -(bbox.x[0] + bbox.x[1]) / 2;
    view.y = -(bbox.y[0] + bbox.y[1]) / 2;
    scheduleRender();
  }
  function focusNode(id) {
    const n = byId.get(id);
    if (!n) return;
    ensureVisible();
    view.x = -n.x;
    view.y = -n.y;
    view.scale = clampScale(window.matchMedia("(max-width: 920px)").matches ? Math.max(view.scale, 1.45) : Math.max(view.scale, .9));
    refreshGraph();
  }
  function relationColor(id) {
    if (id === selected) return "#e2bd00";
    const center = selected && byId.get(selected);
    if (!center) return "#555555";
    const incoming = center.followersSet.has(id);
    const outgoing = center.followingSet.has(id);
    if (incoming && outgoing) return "#2d2d2d";
    if (incoming) return "#555555";
    if (outgoing) return "#777777";
    return "#555555";
  }
  function updateStatus() {
    ensureVisible();
    const summary = `Showing <b>${visibleList.length.toLocaleString()}</b> people and <b>${visibleEdges.length.toLocaleString()}</b> follows`;
    const selectedNode = selected && byId.get(selected);
    const nextStatus = selectedNode
      ? `<div class="graph-legend"><span>${summary} · selected <b>${escapeHtml(selectedNode.slug)}</b></span><span class="legend-key"><span class="legend-dot selected"></span>selected</span><span class="legend-key"><span class="legend-dot follower"></span>follows selected</span><span class="legend-key"><span class="legend-dot following"></span>selected follows</span><span class="legend-key"><span class="legend-dot mutual"></span>mutual</span><span class="legend-key"><span class="legend-dot other"></span>other</span></div>`
      : `<div class="graph-legend"><span>${summary}. Search or click a dot to select a person.</span></div>`;
    if (nextStatus !== lastStatus) {
      status.innerHTML = nextStatus;
      lastStatus = nextStatus;
    }
  }
  function refreshGraph() {
    graphDirty = true;
    scheduleRender();
  }

  function hexToRgb(hex) {
    const value = Number.parseInt(hex.slice(1), 16);
    return [(value >> 16) / 255, ((value >> 8) & 255) / 255, (value & 255) / 255];
  }
  function pushColor(out, hex, alpha) {
    const rgb = hexToRgb(hex);
    out.push(rgb[0], rgb[1], rgb[2], alpha);
  }
  function currentEdgeAlphaMode() {
    return selected && mode.value === "whole" && view.scale < .7 ? "thin-whole" : "normal";
  }
  function relatedToSelected(id) {
    const center = selected && byId.get(selected);
    return !center || id === selected || center.followersSet.has(id) || center.followingSet.has(id);
  }
  function compileShader(type, source) {
    const shader = gl.createShader(type);
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(shader));
    return shader;
  }
  function createProgram(vertexSource, fragmentSource) {
    const program = gl.createProgram();
    gl.attachShader(program, compileShader(gl.VERTEX_SHADER, vertexSource));
    gl.attachShader(program, compileShader(gl.FRAGMENT_SHADER, fragmentSource));
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(program));
    return program;
  }
  const edgeProgram = gl && createProgram(`
    attribute vec2 a_pos;
    attribute vec2 a_offset;
    attribute vec4 a_color;
    uniform vec3 u_view;
    uniform vec2 u_size;
    varying vec4 v_color;
    void main() {
      vec2 screen = vec2(u_size.x * 0.5 + (a_pos.x + u_view.x) * u_view.z, u_size.y * 0.5 + (a_pos.y + u_view.y) * u_view.z);
      screen += a_offset;
      vec2 clip = vec2(screen.x / u_size.x * 2.0 - 1.0, 1.0 - screen.y / u_size.y * 2.0);
      gl_Position = vec4(clip, 0.0, 1.0);
      v_color = a_color;
    }
  `, `
    precision mediump float;
    varying vec4 v_color;
    void main() { gl_FragColor = v_color; }
  `);
  const nodeProgram = gl && createProgram(`
    attribute vec2 a_pos;
    attribute vec4 a_color;
    attribute float a_size;
    uniform vec3 u_view;
    uniform vec2 u_size;
    uniform float u_dpr;
    varying vec4 v_color;
    void main() {
      vec2 screen = vec2(u_size.x * 0.5 + (a_pos.x + u_view.x) * u_view.z, u_size.y * 0.5 + (a_pos.y + u_view.y) * u_view.z);
      vec2 clip = vec2(screen.x / u_size.x * 2.0 - 1.0, 1.0 - screen.y / u_size.y * 2.0);
      gl_Position = vec4(clip, 0.0, 1.0);
      gl_PointSize = max(1.7, a_size * sqrt(u_view.z)) * u_dpr;
      v_color = a_color;
    }
  `, `
    precision mediump float;
    varying vec4 v_color;
    void main() {
      vec2 p = gl_PointCoord * 2.0 - 1.0;
      float d = dot(p, p);
      if (d > 1.0) discard;
      float edge = smoothstep(1.0, 0.72, d);
      gl_FragColor = vec4(v_color.rgb, v_color.a * edge);
    }
  `);
  const edgePositionBuffer = gl && gl.createBuffer();
  const edgeOffsetBuffer = gl && gl.createBuffer();
  const edgeColorBuffer = gl && gl.createBuffer();
  const nodePositionBuffer = gl && gl.createBuffer();
  const nodeColorBuffer = gl && gl.createBuffer();
  const nodeSizeBuffer = gl && gl.createBuffer();
  const EDGE_LINE_WIDTH = 1.4;

  function setBuffer(buffer, values) {
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(values), gl.STATIC_DRAW);
  }
  function rebuildGraphBuffers() {
    ensureVisible();
    if (!gl) return;
    const edgePositions = [];
    const edgeOffsets = [];
    const edgeColors = [];
    const lowWholeGraph = currentEdgeAlphaMode() === "thin-whole";
    for (const {aId, bId, a, b} of visibleEdges) {
      const touches = aId === selected || bId === selected;
      const color = touches ? (bId === selected ? "#555555" : "#777777") : "#b5b5b5";
      const alpha = lowWholeGraph && !touches ? .08 : touches ? .72 : selected && mode.value !== "whole" ? .16 : .11;
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      const length = Math.hypot(dx, dy);
      if (!length) continue;
      const nx = -dy / length * EDGE_LINE_WIDTH * .5;
      const ny = dx / length * EDGE_LINE_WIDTH * .5;
      edgePositions.push(a.x, a.y, b.x, b.y, b.x, b.y, a.x, a.y, b.x, b.y, a.x, a.y);
      edgeOffsets.push(nx, ny, nx, ny, -nx, -ny, nx, ny, -nx, -ny, -nx, -ny);
      for (let i = 0; i < 6; i += 1) pushColor(edgeColors, color, alpha);
    }
    const nodePositions = [];
    const nodeColors = [];
    const nodeSizes = [];
    for (const n of visibleList) {
      const related = relatedToSelected(n.id);
      nodePositions.push(n.x, n.y);
      pushColor(nodeColors, relationColor(n.id), selected && mode.value === "whole" && !related ? .46 : .95);
      nodeSizes.push(nodeRadius(n));
    }
    setBuffer(edgePositionBuffer, edgePositions);
    setBuffer(edgeOffsetBuffer, edgeOffsets);
    setBuffer(edgeColorBuffer, edgeColors);
    setBuffer(nodePositionBuffer, nodePositions);
    setBuffer(nodeColorBuffer, nodeColors);
    setBuffer(nodeSizeBuffer, nodeSizes);
    edgeVertexCount = edgePositions.length / 2;
    nodeVertexCount = nodePositions.length / 2;
    edgeAlphaMode = currentEdgeAlphaMode();
    graphDirty = false;
  }
  function ensureGraphBuffers() {
    ensureVisible();
    if (graphDirty || edgeAlphaMode !== currentEdgeAlphaMode()) rebuildGraphBuffers();
  }
  function resize(shouldRender = true) {
    const rect = graphStage.getBoundingClientRect();
    const dpr = Math.max(1, window.devicePixelRatio || 1);
    const graphDpr = Math.min(dpr, 1.5);
    canvasSize.width = Math.max(1, rect.width);
    canvasSize.height = Math.max(1, rect.height);
    canvasSize.dpr = dpr;
    canvasSize.graphDpr = graphDpr;
    webglCanvas.width = Math.max(1, Math.round(canvasSize.width * graphDpr));
    webglCanvas.height = Math.max(1, Math.round(canvasSize.height * graphDpr));
    overlayCanvas.width = Math.max(1, Math.round(canvasSize.width * dpr));
    overlayCanvas.height = Math.max(1, Math.round(canvasSize.height * dpr));
    overlay.setTransform(dpr, 0, 0, dpr, 0, 0);
    setLayerOffset(0, 0);
    if (shouldRender) scheduleRender();
  }
  function setLayerOffset(dx, dy) {
    const transform = dx || dy ? `translate3d(${dx}px, ${dy}px, 0)` : "";
    webglCanvas.style.transform = transform;
    overlayCanvas.style.transform = transform;
  }
  function project(n) {
    return {x: canvasSize.width / 2 + (n.x + view.x) * view.scale, y: canvasSize.height / 2 + (n.y + view.y) * view.scale};
  }
  function unproject(x, y) {
    return {x: (x - canvasSize.width / 2) / view.scale - view.x, y: (y - canvasSize.height / 2) / view.scale - view.y};
  }
  function clampScale(value) {
    return Math.max(.12, Math.min(8, value));
  }
  function pointerDistance(a, b) {
    return Math.hypot(a.x - b.x, a.y - b.y);
  }
  function pointerMidpoint(a, b) {
    return {x: (a.x + b.x) / 2, y: (a.y + b.y) / 2};
  }
  function scheduleRender() {
    if (renderPending) return;
    renderPending = true;
    requestAnimationFrame(() => {
      renderPending = false;
      render();
    });
  }
  function settleRender(delay = 80) {
    clearTimeout(settleTimer);
    settleTimer = setTimeout(() => {
      moving = false;
      scheduleRender();
    }, delay);
  }
  function render() {
    ensureGraphBuffers();
    const quickMove = gl && moving;
    if (!quickMove) {
      for (const n of visibleList) {
        n.sx = canvasSize.width / 2 + (n.x + view.x) * view.scale;
        n.sy = canvasSize.height / 2 + (n.y + view.y) * view.scale;
      }
    }
    if (gl) renderWebGL();
    else renderFallback2d();
    if (quickMove) {
      overlay.clearRect(0, 0, canvasSize.width, canvasSize.height);
    } else {
      drawOverlay();
      updateStatus();
    }
  }
  function bindAttribute(program, name, buffer, size) {
    const location = gl.getAttribLocation(program, name);
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    gl.enableVertexAttribArray(location);
    gl.vertexAttribPointer(location, size, gl.FLOAT, false, 0, 0);
  }
  function setCommonUniforms(program) {
    gl.uniform3f(gl.getUniformLocation(program, "u_view"), view.x, view.y, view.scale);
    gl.uniform2f(gl.getUniformLocation(program, "u_size"), canvasSize.width, canvasSize.height);
  }
  function renderWebGL() {
    gl.viewport(0, 0, webglCanvas.width, webglCanvas.height);
    gl.clearColor(1, 1, 1, 1);
    gl.clear(gl.COLOR_BUFFER_BIT);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
    gl.useProgram(edgeProgram);
    setCommonUniforms(edgeProgram);
    bindAttribute(edgeProgram, "a_pos", edgePositionBuffer, 2);
    bindAttribute(edgeProgram, "a_offset", edgeOffsetBuffer, 2);
    bindAttribute(edgeProgram, "a_color", edgeColorBuffer, 4);
    gl.drawArrays(gl.TRIANGLES, 0, edgeVertexCount);
    gl.useProgram(nodeProgram);
    setCommonUniforms(nodeProgram);
    gl.uniform1f(gl.getUniformLocation(nodeProgram, "u_dpr"), canvasSize.graphDpr);
    bindAttribute(nodeProgram, "a_pos", nodePositionBuffer, 2);
    bindAttribute(nodeProgram, "a_color", nodeColorBuffer, 4);
    bindAttribute(nodeProgram, "a_size", nodeSizeBuffer, 1);
    gl.drawArrays(gl.POINTS, 0, nodeVertexCount);
  }
  function drawEdge2d(a, b, color, alpha, width) {
    if (a.sx < -80 && b.sx < -80) return;
    if (a.sx > canvasSize.width + 80 && b.sx > canvasSize.width + 80) return;
    if (a.sy < -80 && b.sy < -80) return;
    if (a.sy > canvasSize.height + 80 && b.sy > canvasSize.height + 80) return;
    overlay.globalAlpha = alpha;
    overlay.strokeStyle = color;
    overlay.lineWidth = Math.max(.6, width * Math.sqrt(view.scale));
    overlay.beginPath();
    overlay.moveTo(a.sx, a.sy);
    overlay.lineTo(b.sx, b.sy);
    overlay.stroke();
  }
  function renderFallback2d() {
    overlay.clearRect(0, 0, canvasSize.width, canvasSize.height);
    overlay.fillStyle = "#ffffff";
    overlay.fillRect(0, 0, canvasSize.width, canvasSize.height);
    const lowWholeGraph = currentEdgeAlphaMode() === "thin-whole";
    for (const {aId, bId, a, b} of visibleEdges) {
      const touches = aId === selected || bId === selected;
      if (lowWholeGraph && !touches) drawEdge2d(a, b, "#b5b5b5", .08, .85);
      else if (touches) drawEdge2d(a, b, bId === selected ? "#555555" : "#777777", .72, 1.65);
      else drawEdge2d(a, b, "#b5b5b5", selected && mode.value !== "whole" ? .16 : .11, 1);
    }
    const focus = selected ? byId.get(selected) : null;
    for (const n of visibleList) {
      if (n.sx < -30 || n.sy < -30 || n.sx > canvasSize.width + 30 || n.sy > canvasSize.height + 30) continue;
      const r = nodeRadius(n) * Math.sqrt(view.scale);
      overlay.globalAlpha = selected && mode.value === "whole" && focus && !relatedToSelected(n.id) ? .46 : .95;
      overlay.fillStyle = relationColor(n.id);
      overlay.beginPath();
      overlay.arc(n.sx, n.sy, Math.max(1.7, r), 0, Math.PI * 2);
      overlay.fill();
    }
    overlay.globalAlpha = 1;
  }
  function drawOverlay() {
    if (gl) overlay.clearRect(0, 0, canvasSize.width, canvasSize.height);
    for (const n of visibleList) {
      if (n.id !== selected && n.id !== hover) continue;
      if (n.sx < -30 || n.sy < -30 || n.sx > canvasSize.width + 30 || n.sy > canvasSize.height + 30) continue;
      overlay.globalAlpha = .95;
      overlay.strokeStyle = "#161616";
      overlay.lineWidth = 2;
      overlay.beginPath();
      overlay.arc(n.sx, n.sy, Math.max(1.7, nodeRadius(n) * Math.sqrt(view.scale)), 0, Math.PI * 2);
      overlay.stroke();
    }
    overlay.globalAlpha = 1;
    const mobileLabels = window.matchMedia("(max-width: 520px)").matches;
    const labelNodes = visibleList.filter(n => n.id === selected || n.id === hover || (!mobileLabels && ((view.scale > .85 && n.in >= 80) || (view.scale > 1.6 && degree(n) >= 18))) || (mobileLabels && view.scale > 2.4 && n.in >= 180)).slice(0, mobileLabels ? 12 : 70);
    overlay.font = `${mobileLabels ? Math.max(12, 13 * Math.min(1.18, view.scale)) : Math.max(13, 15 * Math.min(1.4, view.scale))}px Source Sans Pro, sans-serif`;
    overlay.textBaseline = "middle";
    for (const n of labelNodes) {
      if (n.sx < -80 || n.sy < -50 || n.sx > canvasSize.width + 80 || n.sy > canvasSize.height + 50) continue;
      const text = n.name || n.slug;
      overlay.lineWidth = 4;
      overlay.strokeStyle = "rgba(255,255,255,.92)";
      overlay.strokeText(text, n.sx + nodeRadius(n) * Math.sqrt(view.scale) + 4, n.sy);
      overlay.fillStyle = "#161616";
      overlay.fillText(text, n.sx + nodeRadius(n) * Math.sqrt(view.scale) + 4, n.sy);
    }
  }
  function hitTest(clientX, clientY) {
    const rect = graphStage.getBoundingClientRect();
    const world = unproject(clientX - rect.left, clientY - rect.top);
    let best = null, bestD = Infinity;
    ensureVisible();
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
  function safeExternalUrl(value) {
    const text = String(value || "").trim();
    if (!text) return "";
    const url = /^https?:\/\//i.test(text) ? text : `https://${text}`;
    try {
      const parsed = new URL(url);
      return parsed.protocol === "http:" || parsed.protocol === "https:" ? parsed.href : "";
    } catch {
      return "";
    }
  }
  function twitterUrl(value) {
    const text = String(value || "").trim();
    if (!text) return "";
    if (/^https?:\/\//i.test(text)) return safeExternalUrl(text);
    const handle = text.replace(/^@/, "").replace(/^(twitter|x)\.com\//i, "").split(/[/?#]/)[0];
    return handle ? `https://twitter.com/${encodeURIComponent(handle)}` : "";
  }
  function githubUrl(value) {
    const text = String(value || "").trim();
    if (!text) return "";
    if (/^https?:\/\//i.test(text)) return safeExternalUrl(text);
    const handle = text.replace(/^@/, "").replace(/^github\.com\//i, "").split(/[/?#]/)[0];
    return handle ? `https://github.com/${encodeURIComponent(handle)}` : "";
  }
  function appendProfileLink(row, label, href) {
    if (!href) return;
    const a = document.createElement("a");
    a.href = href; a.target = "_blank"; a.rel = "noopener noreferrer"; a.textContent = label;
    row.append(a);
  }
  function readerFooter() {
    const footer = document.createElement("p");
    footer.className = "reader-footer";
    footer.innerHTML = `built by <a href="https://twitter.com/anishthite" target="_blank" rel="noopener noreferrer">anish</a> with <a href="https://spanner.sh" target="_blank" rel="noopener noreferrer">spanner</a>`;
    return footer;
  }
  function renderReader() {
    const n = selected && byId.get(selected);
    reader.classList.toggle("is-empty", !n);
    graphPage.classList.toggle("has-selection", Boolean(n));
    clearButton.hidden = !n;
    if (!n) {
      reader.hidden = true;
      reader.replaceChildren();
      return;
    }
    reader.hidden = false;
    const followers = sortedPeople(n.followers);
    const following = sortedPeople(n.following);
    reader.innerHTML = "";
    const header = document.createElement("div"); header.className = "reader-head";
    const title = document.createElement("h2"); title.textContent = n.name || n.slug;
    const clear = document.createElement("button"); clear.type = "button"; clear.className = "clear-person"; clear.textContent = "Clear"; clear.addEventListener("click", clearSelection);
    header.append(title, clear);
    const links = document.createElement("p"); links.className = "profile-links";
    appendProfileLink(links, "Curius", profileUrl(n));
    appendProfileLink(links, "Twitter", twitterUrl(n.twitter));
    appendProfileLink(links, "GitHub", githubUrl(n.github));
    appendProfileLink(links, "Website", safeExternalUrl(n.website));
    const counts = document.createElement("div"); counts.className = "counts";
    counts.innerHTML = `<div class="count"><b>${n.in.toLocaleString()}</b><span>followers</span></div><div class="count"><b>${n.out.toLocaleString()}</b><span>following</span></div><div class="count"><b>${n.core}</b><span>core score <button class="info-dot" type="button" aria-label="Core score explanation" aria-describedby="core-score-tip">i<span id="core-score-tip" class="info-tooltip" role="tooltip">Core score is the k-core number: the deepest dense shell this person remains in after repeatedly removing people with fewer than k connections. Follows are treated as undirected here.</span></button></span></div>`;
    reader.append(header, links, counts, peopleSection("Followers", followers), peopleSection("Following", following), readerFooter());
  }
  function peopleSection(title, people) {
    const section = document.createElement("section");
    section.className = "people-section";
    const h = document.createElement("h3"); h.textContent = `${title} (${people.length.toLocaleString()})`;
    const list = document.createElement("div"); list.className = "people";
    people.slice(0, 42).forEach(p => list.append(personButton(p)));
    section.append(h, list);
    return section;
  }
  function renderMatches() {
    const term = q.value.trim().toLowerCase();
    matches.hidden = !term;
    graphPage.classList.toggle("has-matches", Boolean(term));
    if (!term) { matches.replaceChildren(); resize(); return; }
    const found = nodes.filter(n => matchesText(n, term)).slice(0, 18);
    matches.replaceChildren(...found.map(personButton));
    resize();
  }
  function hideMatches() {
    matches.hidden = true;
    matches.replaceChildren();
    graphPage.classList.remove("has-matches");
    resize();
  }
  function scrollMobileGraphIntoView() {
    if (!window.matchMedia("(max-width: 920px)").matches) return;
    requestAnimationFrame(() => {
      const behavior = window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth";
      graphStage.scrollIntoView({block: "start", behavior});
    });
  }
  function clearSelection() {
    if (!selected && !q.value) return;
    selected = null;
    q.value = "";
    mode.value = "whole";
    markVisibleDirty();
    renderReader();
    hideMatches();
    fit(false);
  }
  function selectNode(id, shouldFit) {
    if (!byId.has(id)) return;
    const isMobile = window.matchMedia("(max-width: 920px)").matches;
    selected = id;
    q.value = byId.get(id).slug;
    q.blur();
    markVisibleDirty();
    renderReader();
    if (isMobile) hideMatches();
    else renderMatches();
    if (shouldFit && isMobile) focusNode(id);
    else if (mode.value === "whole") refreshGraph();
    else shouldFit ? fit() : refreshGraph();
    if (shouldFit) scrollMobileGraphIntoView();
  }
  function trackPointer(ev) {
    activePointers.set(ev.pointerId, {id: ev.pointerId, x: ev.clientX, y: ev.clientY});
  }
  function startPinch() {
    const points = [...activePointers.values()];
    if (points.length < 2) return;
    const [a, b] = points;
    const center = pointerMidpoint(a, b);
    const rect = graphStage.getBoundingClientRect();
    const world = unproject(center.x - rect.left, center.y - rect.top);
    pinch = {
      a: a.id,
      b: b.id,
      distance: Math.max(1, pointerDistance(a, b)),
      scale: view.scale,
      worldX: world.x,
      worldY: world.y,
    };
    pointer = null;
    moving = true;
    setLayerOffset(0, 0);
  }
  function updatePinch() {
    if (!pinch) return false;
    const a = activePointers.get(pinch.a);
    const b = activePointers.get(pinch.b);
    if (!a || !b) return false;
    const center = pointerMidpoint(a, b);
    const rect = graphStage.getBoundingClientRect();
    const nextScale = clampScale(pinch.scale * pointerDistance(a, b) / pinch.distance);
    view.scale = nextScale;
    view.x = (center.x - rect.left - canvasSize.width / 2) / nextScale - pinch.worldX;
    view.y = (center.y - rect.top - canvasSize.height / 2) / nextScale - pinch.worldY;
    moving = true;
    scheduleRender();
    return true;
  }
  function endPinchPointer(pointerId) {
    activePointers.delete(pointerId);
    if (!pinch) return false;
    if (activePointers.size >= 2) startPinch();
    else {
      pinch = null;
      moving = false;
      settleRender(90);
    }
    return true;
  }
  graphStage.addEventListener("pointerdown", ev => {
    graphStage.setPointerCapture(ev.pointerId);
    trackPointer(ev);
    clearTimeout(settleTimer);
    if (activePointers.size >= 2) {
      startPinch();
      hover = null;
      return;
    }
    const hit = hitTest(ev.clientX, ev.clientY);
    pointer = {id: ev.pointerId, x: ev.clientX, y: ev.clientY, startX: ev.clientX, startY: ev.clientY, startViewX: view.x, startViewY: view.y, dx: 0, dy: 0, moved: false, hit: hit?.id || null};
    hover = null;
  });
  function scheduleHover(ev) {
    hoverEvent = {clientX: ev.clientX, clientY: ev.clientY};
    if (hoverPending) return;
    hoverPending = true;
    requestAnimationFrame(() => {
      hoverPending = false;
      if (!hoverEvent) return;
      const hit = hitTest(hoverEvent.clientX, hoverEvent.clientY);
      const nextHover = hit?.id || null;
      if (nextHover !== hover) {
        hover = nextHover;
        scheduleRender();
      }
    });
  }
  graphStage.addEventListener("pointermove", ev => {
    if (activePointers.has(ev.pointerId)) trackPointer(ev);
    if (pinch) {
      updatePinch();
      return;
    }
    if (pointer && pointer.id === ev.pointerId) {
      pointer.dx = ev.clientX - pointer.startX;
      pointer.dy = ev.clientY - pointer.startY;
      if (Math.hypot(pointer.dx, pointer.dy) > 2) pointer.moved = true;
      pointer.x = ev.clientX;
      pointer.y = ev.clientY;
      if (pointer.moved) {
        moving = true;
        setLayerOffset(pointer.dx, pointer.dy);
      }
      return;
    }
    scheduleHover(ev);
  });
  graphStage.addEventListener("pointerup", ev => {
    if (endPinchPointer(ev.pointerId)) return;
    activePointers.delete(ev.pointerId);
    if (!pointer) return;
    if (pointer.moved) {
      view.x = pointer.startViewX + pointer.dx / view.scale;
      view.y = pointer.startViewY + pointer.dy / view.scale;
      setLayerOffset(0, 0);
      moving = false;
      render();
    } else {
      const hit = hitTest(ev.clientX, ev.clientY);
      if (hit) selectNode(hit.id, false);
    }
    pointer = null;
  });
  graphStage.addEventListener("pointercancel", ev => {
    activePointers.delete(ev.pointerId);
    if (pinch && activePointers.size >= 2) {
      startPinch();
      return;
    }
    pinch = null;
    if (pointer?.id === ev.pointerId) pointer = null;
    if (!activePointers.size) {
      moving = false;
      setLayerOffset(0, 0);
      scheduleRender();
    }
  });
  graphStage.addEventListener("wheel", ev => {
    ev.preventDefault();
    moving = true;
    const rect = graphStage.getBoundingClientRect();
    const before = unproject(ev.clientX - rect.left, ev.clientY - rect.top);
    const factor = Math.exp(-ev.deltaY * .0012);
    view.scale = clampScale(view.scale * factor);
    const after = unproject(ev.clientX - rect.left, ev.clientY - rect.top);
    view.x += after.x - before.x;
    view.y += after.y - before.y;
    scheduleRender();
    settleRender(90);
  }, {passive: false});
  clearButton.addEventListener("click", clearSelection);
  q.addEventListener("input", () => {
    if (!q.value.trim() && selected) { clearSelection(); return; }
    renderMatches();
  });
  q.addEventListener("keydown", ev => {
    if (ev.key !== "Enter") return;
    const term = q.value.trim().toLowerCase();
    const hit = nodes.find(n => matchesText(n, term));
    if (hit) selectNode(hit.id, true);
  });
  minFollowers.addEventListener("input", () => { markVisibleDirty(); mode.value === "whole" ? refreshGraph() : fit(); renderMatches(); });
  mode.addEventListener("change", () => { markVisibleDirty(); fit(); });
  document.getElementById("fit").addEventListener("click", fit);
  window.addEventListener("resize", resize);
  renderReader();
  renderMatches();
  resize(false);
  fit(false);
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
  <nav class="nav"><a href="about.html">About</a></nav>
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
  <nav class="nav"><a href="about.html">About</a></nav>
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


ABOUT_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>About the Curius graph</title>
<style>
__PAPER_CSS__
  .article { max-width: 940px; }
  .lede { font-size: clamp(1.18rem, 2.8vw, 1.55rem); line-height: 1.38; max-width: 60ch; }
  .chart-section { margin: 2.2rem 0 0; padding-top: 1rem; border-top: 1px solid var(--rule); }
  .bar-chart { display: grid; gap: .66rem; margin: 1.1rem 0 1.4rem; }
  .chart-row { display: grid; grid-template-columns: minmax(11rem, 16rem) minmax(0, 1fr) 5.5rem; gap: .7rem; align-items: center; }
  .chart-label { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .chart-label a { color: var(--ink); text-decoration: none; }
  .chart-label a:hover { text-decoration: underline; text-underline-offset: .16em; }
  .chart-label small { display: block; overflow: hidden; color: var(--muted); text-overflow: ellipsis; white-space: nowrap; font-size: .82rem; line-height: 1.12; }
  .chart-track { height: .8rem; border-radius: 999px; background: rgba(216, 200, 181, .42); overflow: hidden; }
  .chart-bar { display: block; height: 100%; min-width: 3px; border-radius: inherit; background: linear-gradient(90deg, var(--blue), var(--green)); }
  .chart-count { color: var(--muted); text-align: right; font-variant-numeric: tabular-nums; }
  @media (max-width: 700px) {
    .chart-row { grid-template-columns: minmax(0, 1fr) 4.8rem; gap: .42rem .65rem; }
    .chart-track { grid-column: 1 / -1; grid-row: 2; }
  }
</style>
</head>
<body>
<div class="page">
  <nav class="nav"><a href="index.html">Back</a></nav>
  <main class="article">
    <h1>__ABOUT_TITLE__</h1>
    <p class="lede">__ABOUT_LEDE__</p>
    __ABOUT_PARAGRAPHS__

    <section class="chart-section" aria-labelledby="followers-heading">
      <h2 id="followers-heading">__FOLLOWERS_HEADING__</h2>
      <div class="bar-chart people-chart" role="list" aria-label="Most followed people">
        __FOLLOWER_CHART__
      </div>
    </section>

    <section class="chart-section" aria-labelledby="domains-heading">
      <h2 id="domains-heading">__DOMAINS_HEADING__</h2>
      <div class="bar-chart domain-chart" role="list" aria-label="Most popular saved-link domains">
        __POPULAR_DOMAIN_CHART__
      </div>
    </section>
  </main>
</div>
</body>
</html>
"""

FRONTPAGE_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="A live list of links Curius readers are saving and returning to.">
<meta name="theme-color" content="#f7f0e4">
<title>Curius Links</title>
<style>
__PAPER_CSS__
  .page { width: min(840px, 100%); padding-top: clamp(16px, 3vw, 30px); }
  .site-header { display: flex; justify-content: space-between; gap: 1rem; align-items: center; padding: 0 0 1.1rem; border-bottom: 1px solid var(--rule); }
  .wordmark { color: var(--ink); font-size: 1.28rem; font-weight: 600; letter-spacing: -.035em; text-decoration: none; }
  .site-nav { display: flex; gap: .95rem; align-items: center; font-size: .9rem; }
  .site-nav a { display: inline-flex; align-items: center; min-height: 44px; color: var(--muted); text-decoration: none; }
  .site-nav a:hover, .site-nav a:focus-visible { color: var(--ink); text-decoration: underline; text-underline-offset: .16em; }
  .feed-toolbar { display: flex; justify-content: space-between; gap: 1rem; align-items: baseline; margin: 1.45rem 0 .55rem; }
  .feed-toolbar h1 { margin: 0; font-size: clamp(1.65rem, 4vw, 2.1rem); }
  .sort-controls { display: flex; gap: .25rem; padding: .2rem; border: 1px solid var(--rule); border-radius: 999px; background: rgba(255, 250, 240, .7); }
  .sort-controls button { min-height: 32px; padding: .18rem .62rem; border: 0; background: transparent; color: var(--muted); font-size: .86rem; }
  .sort-controls button[aria-pressed="true"] { background: var(--ink); border-color: var(--ink); color: var(--sheet); }
  .sort-controls button:hover:not([aria-pressed="true"]) { color: var(--ink); background: rgba(32, 23, 15, .06); }
  .hn-list { list-style: none; padding: 0; margin: 0; counter-reset: feed; }
  .hn-item { counter-increment: feed; display: grid; grid-template-columns: 2.1rem minmax(0, 1fr); gap: .7rem; padding: 1rem 0 1.05rem; border-bottom: 1px solid var(--rule); }
  .hn-item::before { content: counter(feed, decimal-leading-zero); color: var(--muted); font-size: .8rem; letter-spacing: .04em; text-align: right; padding-top: .22rem; }
  .story-title { display: flex; gap: .42rem; flex-wrap: wrap; align-items: baseline; font-size: clamp(1.06rem, 2vw, 1.18rem); line-height: 1.25; }
  .story-title a { color: var(--ink); text-decoration: none; overflow-wrap: anywhere; }
  .story-title a:hover, .story-title a:focus-visible { color: var(--blue); text-decoration: underline; text-underline-offset: .16em; }
  .domain { color: var(--muted); font-size: .82rem; overflow-wrap: anywhere; }
  .subtext { margin-top: .25rem; color: var(--muted); font-size: .84rem; }
  .snippet { color: #514538; margin: .42rem 0 0; font-size: .92rem; line-height: 1.38; overflow-wrap: anywhere; }
  .empty { color: var(--muted); padding: 1rem 0; }
  @media (max-width: 520px) {
    .page { padding-top: 14px; }
    .site-header { padding-bottom: .8rem; }
    .site-nav { gap: .7rem; font-size: .82rem; }
    .feed-toolbar { margin-top: 1rem; align-items: center; }
    .hn-item { grid-template-columns: 1.55rem minmax(0, 1fr); gap: .5rem; padding: .88rem 0 .93rem; }
    .hn-item::before { font-size: .7rem; padding-top: .28rem; }
    .domain { flex-basis: 100%; }
  }
</style>
</head>
<body>
<div class="page">
  <header class="site-header">
    <a class="wordmark" href="index.html" aria-label="Curius Links home">Curius</a>
    <nav class="site-nav" aria-label="Curius links navigation"><a href="how-this-works.html">About</a><a href="__ANALYSIS_INDEX_URL__">Graph</a></nav>
  </header>
  <main aria-label="Curius link feed">
    <div class="feed-toolbar">
      <h1 id="feed-heading" aria-live="polite">Popular links</h1>
      <div class="sort-controls" aria-label="Sort links">
        <button type="button" data-sort="popular" aria-pressed="true">Popular</button>
        <button type="button" data-sort="newest" aria-pressed="false">Newest</button>
      </div>
    </div>
    <ol id="feed" class="hn-list">__FRONTPAGE_FEED_HTML__</ol>
  </main>
</div>
<script id="frontpage-data" type="application/json">__FRONTPAGE_JSON__</script>
<script>
(() => {
  "use strict";
  const data = JSON.parse(document.getElementById("frontpage-data").textContent);
  const generatedAt = Date.parse(data.generatedAt) || Date.now();
  const feed = document.getElementById("feed");
  const feedHeading = document.getElementById("feed-heading");
  const sortButtons = document.querySelectorAll("[data-sort]");
  const state = {sort: "popular"};
  const views = data.views || buildViews(data);
  let currentSort = "popular";

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
  function score(item) {
    if (Number.isFinite(item.score)) return item.score;
    return 3 * item.savers + 5 * item.highlighters + item.highlights;
  }
  function buildViews(source) {
    const rows = (source.links || []).map(item => ({...item, score: score(item), createdAtMs: Date.parse(item.createdAt || "") || 0}));
    return {
      popular: rows.slice().sort((a, b) => b.score - a.score || b.createdAtMs - a.createdAtMs).slice(0, 50),
      newest: rows.slice().sort((a, b) => b.createdAtMs - a.createdAtMs || b.score - a.score).slice(0, 50),
    };
  }
  function renderLink(item, body) {
    const title = text("div", "story-title");
    const a = text("a", "", item.title || item.url);
    a.href = item.url; a.target = "_blank"; a.rel = "noreferrer";
    title.append(a, text("span", "domain", `(${item.domain})`));
    body.append(title, text("div", "subtext", `${Math.round(score(item)).toLocaleString()} points · ${plural(item.savers, "saver")} · ${plural(item.highlighters, "reader")} marked it · ${plural(item.highlights, "highlight")} · ${age(item.createdAt)}`));
    if (item.snippet) body.append(text("p", "snippet", item.snippet));
  }
  function renderFeed(items) {
    if (!items.length) {
      feed.replaceChildren(text("li", "empty", "No rows in this generated sample."));
      return;
    }
    const fragment = document.createDocumentFragment();
    for (const item of items) {
      const li = text("li", "hn-item");
      const body = text("div", "");
      renderLink(item, body);
      li.append(body);
      fragment.append(li);
    }
    feed.replaceChildren(fragment);
  }
  function render() {
    sortButtons.forEach(button => button.setAttribute("aria-pressed", String(button.dataset.sort === state.sort)));
    if (state.sort === currentSort) return;
    currentSort = state.sort;
    const items = views[state.sort] || [];
    feedHeading.textContent = `${state.sort === "popular" ? "Popular" : "Newest"} links`;
    renderFeed(items);
  }

  sortButtons.forEach(button => button.addEventListener("click", () => { state.sort = button.dataset.sort; render(); }));
})();
</script>
</body>
</html>
"""

HOW_THIS_WORKS_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="How Curius Links orders public saves and highlights.">
<meta name="theme-color" content="#f7f0e4">
<title>About Curius Links</title>
<style>
__PAPER_CSS__
  .page { width: min(760px, 100%); }
  .topbar { display: flex; justify-content: space-between; gap: 1rem; align-items: center; padding-bottom: 1.1rem; border-bottom: 1px solid var(--rule); }
  .back-link { display: inline-flex; align-items: center; min-height: 44px; color: var(--ink); font-size: .94rem; text-decoration: none; }
  .back-link:hover, .back-link:focus-visible { text-decoration: underline; text-underline-offset: .16em; }
  .graph-link { display: inline-flex; align-items: center; min-height: 44px; color: var(--muted); font-size: .86rem; }
  .article { padding: clamp(1.6rem, 5vw, 3.4rem) 0 2rem; }
  .eyebrow { margin: 0 0 .5rem; color: var(--muted); font-size: .84rem; letter-spacing: .09em; text-transform: uppercase; }
  .article h1 { margin-bottom: .55rem; font-size: clamp(2.35rem, 7vw, 4.2rem); }
  .lede { max-width: 39ch; margin: 0; font-size: clamp(1.12rem, 2.4vw, 1.42rem); line-height: 1.42; }
  .article section { margin-top: clamp(2rem, 5vw, 3.3rem); }
  .article h2 { margin: 0 0 .55rem; font-size: clamp(1.45rem, 4vw, 2rem); }
  .article p + p { margin-top: .9rem; }
  .formula-card { margin: 1.1rem 0 0; padding: clamp(1rem, 3vw, 1.35rem); }
  .formula-card h3 { margin: 0; font-size: 1rem; }
  .formula-card .math { margin: .65rem 0; }
  .detail-list { list-style: none; padding: 0; margin: 1rem 0 0; border-top: 1px solid var(--rule); }
  .detail-list li { padding: .72rem 0; border-bottom: 1px solid var(--rule); }
  .detail-list strong { display: inline-block; min-width: 7.5rem; font-weight: 600; }
  .source-note { color: var(--muted); font-size: .94rem; }
  @media (max-width: 520px) {
    .topbar { padding-bottom: .8rem; }
    .article { padding-top: 1.8rem; }
    .detail-list strong { display: block; margin-bottom: .08rem; }
  }
</style>
</head>
<body>
<div class="page">
  <header class="topbar"><a class="back-link" href="index.html">← Curius Links</a><a class="graph-link" href="__ANALYSIS_INDEX_URL__">Follower graph</a></header>
  <main class="article">
    <p class="eyebrow">Curius Links</p>
    <h1>About this list</h1>
    <p class="lede">A quiet, public view of the links Curius readers save, return to, and mark up.</p>

    <section>
      <h2>What appears here</h2>
      <p>Each row is one saved link from the public Curius crawl. Its title opens the original source. The line beneath it shows the activity Curius has seen around that link and when it was last active.</p>
      <ul class="detail-list">
        <li><strong>Popular</strong>orders links by the activity score below.</li>
        <li><strong>Newest</strong>orders them by their most recent save or highlight activity.</li>
        <li><strong>Points</strong>give a compact signal of attention, not a judgment of quality.</li>
      </ul>
    </section>

    <section>
      <h2>How links are ranked</h2>
      <p>Popularity favors activity shared across people, while still crediting the total number of highlights.</p>
      <div class="sheet formula-card">
        <h3>Link score</h3>
        <div class="math">S<sub>link</sub> = 3u<sub>save</sub> + 5u<sub>mark</sub> + h</div>
        <p><code>u<sub>save</sub></code> is the number of distinct savers, <code>u<sub>mark</sub></code> is the number of distinct readers who highlighted the link, and <code>h</code> is the total number of highlights.</p>
      </div>
    </section>

    <section>
      <h2>A few terms</h2>
      <ul class="detail-list">
        <li><strong>Saver</strong>a distinct Curius reader who saved the link.</li>
        <li><strong>Reader marked it</strong>a distinct reader who made at least one highlight on the link.</li>
        <li><strong>Highlight</strong>a saved passage associated with the link.</li>
      </ul>
    </section>

    <section>
      <h2>Scope</h2>
      <p class="source-note">This is a generated snapshot of public Curius activity. Counts can change as the crawl refreshes, and a link’s position is only a reflection of the activity visible in that snapshot.</p>
    </section>
  </main>
</div>
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


def parse_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def frontpage_score(item: dict[str, Any]) -> int:
    if isinstance(item.get("score"), int):
        return item["score"]
    return 3 * int(item.get("savers") or 0) + 5 * int(item.get("highlighters") or 0) + int(item.get("highlights") or 0)


def frontpage_views(payload: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Return the two small, client-side views used by the links-only front page."""
    rows = []
    for item in payload.get("links", []):
        row = dict(item)
        row["score"] = frontpage_score(row)
        created = parse_datetime(row.get("createdAt"))
        row["createdAtMs"] = int(created.timestamp() * 1000) if created else 0
        rows.append(row)
    return {
        "popular": sorted(rows, key=lambda item: (item["score"], item["createdAtMs"]), reverse=True)[:50],
        "newest": sorted(rows, key=lambda item: (item["createdAtMs"], item["score"]), reverse=True)[:50],
    }


def plural(value: int, word: str) -> str:
    return f"{value:,} {word}{'' if value == 1 else 's'}"


def frontpage_age(iso: Any, generated_at: Any) -> str:
    started = parse_datetime(iso)
    generated = parse_datetime(generated_at) or datetime.now(timezone.utc)
    if not started:
        return "undated"
    seconds = max(0, int((generated - started).total_seconds()))
    for size, label in ((31536000, "year"), (2592000, "month"), (604800, "week"), (86400, "day"), (3600, "hour"), (60, "minute")):
        if seconds >= size:
            count = seconds // size
            return f"{count} {label}{'' if count == 1 else 's'} ago"
    return "just now"


def render_frontpage_row(item: dict[str, Any], generated_at: Any) -> str:
    domain = html.escape(str(item.get("domain") or "link"))
    url = html.escape(str(item.get("url") or "#"), quote=True)
    title = html.escape(str(item.get("title") or item.get("url") or "Untitled"))
    age = html.escape(frontpage_age(item.get("createdAt"), generated_at))
    score = f"{frontpage_score(item):,}"
    subtext = (
        f"{score} points · {plural(int(item.get('savers') or 0), 'saver')} · "
        f"{plural(int(item.get('highlighters') or 0), 'reader')} marked it · "
        f"{plural(int(item.get('highlights') or 0), 'highlight')} · {age}"
    )
    snippet = html.escape(str(item.get("snippet") or ""))
    snippet_html = f"<p class=\"snippet\">{snippet}</p>" if snippet else ""
    body = (
        f"<div class=\"story-title\"><a href=\"{url}\" target=\"_blank\" rel=\"noreferrer\">{title}</a>"
        f"<span class=\"domain\">({domain})</span></div><div class=\"subtext\">{html.escape(subtext)}</div>{snippet_html}"
    )
    return f"<li class=\"hn-item\"><div>{body}</div></li>"


def render_frontpage_feed(rows: list[dict[str, Any]], generated_at: Any) -> str:
    if not rows:
        return "<li class=\"empty\">No rows in this generated sample.</li>"
    return "".join(render_frontpage_row(item, generated_at) for item in rows)


def load_frontpage(db_path: Path, limit: int = 160) -> dict[str, Any]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = ON")
    links = load_frontpage_links(conn, limit)
    conn.close()
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": str(db_path),
        "links": links,
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
            SELECT link_id, count(*) AS saves, count(DISTINCT user_id) AS savers,
                   max(saved_at) AS latest_saved_at
            FROM saved_links GROUP BY link_id
        ), marks AS (
            SELECT link_id, count(*) AS highlights, count(DISTINCT user_id) AS highlighters,
                   max(created_at) AS latest_highlight_at
            FROM highlights
            WHERE length(trim(coalesce(highlight_text, raw_highlight, ''))) > 0
            GROUP BY link_id
        )
        SELECT l.link_id, l.url, coalesce(nullif(trim(l.title), ''), l.url) AS title,
               l.snippet, l.created_at, l.modified_at, l.updated_at,
               coalesce(
                   CASE
                       WHEN s.latest_saved_at IS NULL THEN m.latest_highlight_at
                       WHEN m.latest_highlight_at IS NULL THEN s.latest_saved_at
                       WHEN s.latest_saved_at >= m.latest_highlight_at THEN s.latest_saved_at
                       ELSE m.latest_highlight_at
                   END,
                   l.created_at, l.modified_at, l.updated_at
               ) AS activity_at,
               coalesce(s.saves, 0) AS saves, coalesce(s.savers, 0) AS savers,
               coalesce(m.highlights, 0) AS highlights, coalesce(m.highlighters, 0) AS highlighters,
               coalesce(s.savers, 0) * 3 + coalesce(m.highlighters, 0) * 5 + coalesce(m.highlights, 0) AS score
        FROM links l
        LEFT JOIN saves s ON s.link_id = l.link_id
        LEFT JOIN marks m ON m.link_id = l.link_id
        WHERE l.url IS NOT NULL AND trim(l.url) <> ''
    """
    rows: dict[int, dict[str, Any]] = {}
    for order in ("score DESC, activity_at DESC", "activity_at DESC, score DESC"):
        for row in conn.execute(f"{base} ORDER BY {order} LIMIT ?", (limit,)):
            created = row["activity_at"] or row["created_at"] or row["modified_at"] or row["updated_at"] or ""
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
                "score": int(row["score"]),
            })
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
    popular_domains: Counter[str] = Counter()
    for node_id, domains in user_domains.items():
        total = sum(domains.values())
        if not total:
            continue
        popular_domains.update(domains)
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
            "knownDomainUsers": sum(1 for domains in user_domains.values() if sum(domains.values()) > 0),
            "popularDomains": popular_domains.most_common(12),
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
        "nodes": [
            {
                "id": node["id"], "slug": node["slug"], "name": node["name"],
                "github": node["github"], "twitter": node["twitter"], "website": node["website"],
                "in": node["in"], "out": node["out"], "core": node["core"], "rank": node["rank"],
                "x": node["x"], "y": node["y"],
            }
            for node in graph["nodes"]
        ],
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


def merge_copy(defaults: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    merged = dict(defaults)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge_copy(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_about_copy(copy_file: Path = DEFAULT_ABOUT_COPY_FILE) -> dict[str, Any]:
    if not copy_file.exists():
        return DEFAULT_ABOUT_COPY
    loaded = json.loads(copy_file.read_text(encoding="utf-8"))
    return merge_copy(DEFAULT_ABOUT_COPY, loaded)


def copy_text(copy: dict[str, Any], section: str, key: str) -> str:
    return html.escape(str(copy[section][key]))


def copy_paragraphs(copy: dict[str, Any], section: str, key: str) -> str:
    return "\n    ".join(f"<p>{html.escape(str(value))}</p>" for value in copy[section].get(key, []))


def domain_chart(rows: list[tuple[str, int]], limit: int = 10) -> str:
    picked = rows[:limit]
    max_count = max((count for _domain, count in picked), default=1)
    out = []
    for domain, count in picked:
        pct = max(1, round(count / max_count * 100))
        out.append(
            f"<div class=\"chart-row\" role=\"listitem\">"
            f"<span class=\"chart-label\">{html.escape(domain)}</span>"
            f"<span class=\"chart-track\" aria-hidden=\"true\"><span class=\"chart-bar\" style=\"width: {pct}%\"></span></span>"
            f"<span class=\"chart-count\">{fmt_int(count)}</span>"
            f"</div>"
        )
    return "\n        ".join(out)


def follower_chart(rows: list[dict[str, Any]], limit: int = 10) -> str:
    picked = rows[:limit]
    max_count = max((int(person["followers"]) for person in picked), default=1)
    out = []
    for person in picked:
        count = int(person["followers"])
        pct = max(1, round(count / max_count * 100))
        name = html.escape(person["name"])
        slug = html.escape(person["slug"])
        out.append(
            f"<div class=\"chart-row\" role=\"listitem\">"
            f"<span class=\"chart-label\"><a href=\"https://curius.app/users/{slug}\" target=\"_blank\" rel=\"noreferrer\">{name}</a><small>{slug}</small></span>"
            f"<span class=\"chart-track\" aria-hidden=\"true\"><span class=\"chart-bar\" style=\"width: {pct}%\"></span></span>"
            f"<span class=\"chart-count\">{fmt_int(count)}</span>"
            f"</div>"
        )
    return "\n        ".join(out)


def json_script(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")


def app_url(base: str, page: str = "index.html") -> str:
    base = base.rstrip("/")
    return f"{base}/{page}" if base else page


def render_graph_html(
    graph: dict[str, Any],
    db_path: Path,
    frontpage_url: str = DEFAULT_FRONTPAGE_URL,
    about_copy: dict[str, Any] | None = None,
) -> str:
    payload = graph_payload(graph, db_path)
    copy = about_copy or DEFAULT_ABOUT_COPY
    return (
        GRAPH_HTML.replace("__PAPER_CSS__", PAPER_CSS)
        .replace("__POSTHOG_HTML__", POSTHOG_HTML)
        .replace("__FRONTPAGE_INDEX_URL__", app_url(frontpage_url))
        .replace("__GRAPH_SUBHEADER__", copy_text(copy, "graph", "subheader"))
        .replace("__GRAPH_SEE_MORE_TEXT__", copy_text(copy, "graph", "seeMoreText"))
        .replace("__GRAPH_JSON__", json_script(payload))
    )


def render_how_this_works_html(analysis_url: str = DEFAULT_ANALYSIS_URL) -> str:
    replacements = {
        "__PAPER_CSS__": PAPER_CSS,
        "__ANALYSIS_INDEX_URL__": app_url(analysis_url),
        "__ANALYSIS_METRICS_URL__": app_url(analysis_url, "metrics.html"),
        "__ANALYSIS_ALGORITHMS_URL__": app_url(analysis_url, "algorithms.html"),
        "__ANALYSIS_ABOUT_URL__": app_url(analysis_url, "about.html"),
    }
    out = HOW_THIS_WORKS_HTML
    for old, new in replacements.items():
        out = out.replace(old, new)
    return out


def render_frontpage_html(
    payload: dict[str, Any],
    analysis_url: str = DEFAULT_ANALYSIS_URL,
    about_copy: dict[str, Any] | None = None,
) -> str:
    views = frontpage_views(payload)
    default_rows = views["popular"]
    script_payload = {"generatedAt": payload["generatedAt"], "views": views}
    replacements = {
        "__PAPER_CSS__": PAPER_CSS,
        "__ANALYSIS_INDEX_URL__": app_url(analysis_url),
        "__FRONTPAGE_FEED_HTML__": render_frontpage_feed(default_rows, payload["generatedAt"]),
        "__FRONTPAGE_JSON__": json_script(script_payload),
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


def render_about_html(
    graph: dict[str, Any],
    frontpage_url: str = DEFAULT_FRONTPAGE_URL,
    about_copy: dict[str, Any] | None = None,
) -> str:
    metrics = graph["metrics"]
    interest = metrics["nextAnalyses"]["interest"]
    copy = about_copy or DEFAULT_ABOUT_COPY
    replacements = {
        "__PAPER_CSS__": PAPER_CSS,
        "__FRONTPAGE_INDEX_URL__": app_url(frontpage_url),
        "__ABOUT_TITLE__": copy_text(copy, "about", "title"),
        "__ABOUT_LEDE__": copy_text(copy, "about", "lede"),
        "__ABOUT_PARAGRAPHS__": copy_paragraphs(copy, "about", "paragraphs"),
        "__FOLLOWERS_HEADING__": copy_text(copy, "about", "followersHeading"),
        "__FOLLOWER_CHART__": follower_chart(metrics["topFollowers"]),
        "__DOMAINS_HEADING__": copy_text(copy, "about", "domainsHeading"),
        "__POPULAR_DOMAIN_CHART__": domain_chart(interest["popularDomains"]),
    }
    out = ABOUT_HTML
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
    about_out: Path,
    frontpage_out: Path = DEFAULT_FRONTPAGE_OUT,
    frontpage_url: str = DEFAULT_FRONTPAGE_URL,
    analysis_url: str = DEFAULT_ANALYSIS_URL,
    how_out: Path = DEFAULT_HOW_OUT,
    copy_file: Path = DEFAULT_ABOUT_COPY_FILE,
) -> dict[str, Any]:
    if not db_path.exists():
        raise SystemExit(f"Database not found: {db_path}")
    about_copy = load_about_copy(copy_file)
    frontpage = load_frontpage(db_path)
    user_domains = load_user_domains(db_path)
    nodes, edges = load_graph(db_path)
    graph = enrich(nodes, edges, user_domains)
    graph_out.parent.mkdir(parents=True, exist_ok=True)
    metrics_out.parent.mkdir(parents=True, exist_ok=True)
    algorithms_out.parent.mkdir(parents=True, exist_ok=True)
    about_out.parent.mkdir(parents=True, exist_ok=True)
    frontpage_out.parent.mkdir(parents=True, exist_ok=True)
    how_out.parent.mkdir(parents=True, exist_ok=True)
    graph_out.write_text(render_graph_html(graph, db_path, frontpage_url, about_copy), encoding="utf-8")
    metrics_out.write_text(render_metrics_html(graph, frontpage_url), encoding="utf-8")
    algorithms_out.write_text(render_algorithms_html(graph, frontpage_url), encoding="utf-8")
    about_out.write_text(render_about_html(graph, frontpage_url, about_copy), encoding="utf-8")
    frontpage_out.write_text(render_frontpage_html(frontpage, analysis_url, about_copy), encoding="utf-8")
    how_out.write_text(render_how_this_works_html(analysis_url), encoding="utf-8")
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
            CREATE TABLE saved_links (user_id INTEGER, link_id INTEGER, saved_at TEXT);
            CREATE TABLE highlights (
                highlight_id INTEGER PRIMARY KEY, user_id INTEGER, link_id INTEGER,
                highlight_text TEXT, raw_highlight TEXT, left_context TEXT, right_context TEXT, created_at TEXT
            );
            INSERT INTO users VALUES (1, 'ada', 'Ada', 'Lovelace', 'Analytical Engine', 'ada-lovelace', '@ada', 'ada.example', 2);
            INSERT INTO users VALUES (2, 'grace', 'Grace', 'Hopper', 'Navy', '', '', '', 1);
            INSERT INTO users VALUES (3, 'alan', 'Alan', 'Turing', '', '', '', '', 0);
            INSERT INTO users VALUES (4, 'katherine', 'Katherine', 'Johnson', '', '', '', '', 0);
            INSERT INTO follows VALUES (2, 1), (3, 1), (1, 2), (4, 3);
            INSERT INTO links VALUES (10, 'https://example.com/engine', 'Notes on engines', 'A compact note.', '2026-07-15T00:00:00Z', NULL, '2026-07-15T00:00:00Z');
            INSERT INTO links VALUES (11, 'https://example.com/math', 'A new math note', 'Fresh note.', '2026-07-16T00:00:00Z', NULL, '2026-07-16T00:00:00Z');
            INSERT INTO saved_links VALUES (1, 10, '2026-07-15T00:30:00Z'), (2, 10, '2026-07-17T03:00:00Z'), (3, 11, '2026-07-16T00:30:00Z');
            INSERT INTO highlights VALUES (100, 1, 10, 'Readable programs are easier to repair.', NULL, 'A note says', 'when the pager rings.', '2026-07-15T01:00:00Z');
            INSERT INTO highlights VALUES (101, 2, 10, 'Readable programs are easier to repair.', NULL, 'Another note says', 'during review.', '2026-07-16T01:00:00Z');
            INSERT INTO highlights VALUES (102, 3, 11, 'Small checks catch large mistakes.', NULL, '', '', '2026-07-16T02:00:00Z');
            """
        )
        conn.close()
        graph_out = Path(tmp) / "graph.html"
        metrics_out = Path(tmp) / "metrics.html"
        algorithms_out = Path(tmp) / "algorithms.html"
        about_out = Path(tmp) / "about.html"
        frontpage_out = Path(tmp) / "frontpage.html"
        how_out = Path(tmp) / "how-this-works.html"
        graph = build(
            db, graph_out, metrics_out, algorithms_out, about_out, frontpage_out,
            "https://front.example", "https://analysis.example", how_out=how_out,
        )
        graph_html = graph_out.read_text(encoding="utf-8")
        metrics_html = metrics_out.read_text(encoding="utf-8")
        algorithms_html = algorithms_out.read_text(encoding="utf-8")
        about_html = about_out.read_text(encoding="utf-8")
        frontpage_html = frontpage_out.read_text(encoding="utf-8")
        how_html = how_out.read_text(encoding="utf-8")
        assert graph["metrics"]["counts"] == {"nodes": 4, "edges": 4}
        assert graph["metrics"]["reciprocalEdges"] == 2
        assert "graph-data" in graph_html and "webglCanvas" in graph_html and "graph-canvas" in graph_html and "Source Sans Pro" in graph_html
        assert 'getContext("webgl", {alpha: false' in graph_html and "gl.clearColor(1, 1, 1, 1)" in graph_html
        assert "const EDGE_LINE_WIDTH = 1.4" in graph_html and "gl.drawArrays(gl.TRIANGLES, 0, edgeVertexCount)" in graph_html
        assert ".canvas-wrap.sheet { border: 1px solid var(--rule); border-radius: 0; background: #fff; }" in graph_html and ".graph-canvas canvas { border-radius: 0; }" in graph_html
        assert 'overlay.fillStyle = "#ffffff"' in graph_html and "background: #fff;" in graph_html
        assert "The Curius Follower Graph" in graph_html and "The social network from" in graph_html and "https://curius.app" in graph_html and "about.html" in graph_html
        assert "posthog.init" in graph_html and "phc_lwrp8rJxreMnGicmxPIe8YksCzEnpjdZJKTG5Tn3Nps" in graph_html
        assert ".graph-topbar { display: flex;" in graph_html and 'href="https://front.example/index.html"' in graph_html and "min-filter" in graph_html and "Min followers" in graph_html
        assert "Each dot is a Curius user" not in graph_html and "school" not in graph_html
        assert "safeExternalUrl" in graph_html and "profile-links" in graph_html
        assert "const activePointers = new Map()" in graph_html and "function startPinch()" in graph_html and "function updatePinch()" in graph_html
        assert "function focusNode(id)" in graph_html and "function hideMatches()" in graph_html and "graphStage.scrollIntoView" in graph_html
        assert "const isMobile = window.matchMedia" in graph_html and "if (isMobile) hideMatches()" in graph_html
        assert "const mobileLabels = window.matchMedia" in graph_html and "slice(0, mobileLabels ? 12 : 70)" in graph_html
        assert "touch-action: none;" in graph_html and "height: clamp(400px, 58vh, 540px)" in graph_html and "height: clamp(430px, 62vh, 560px)" in graph_html
        assert ".person:hover { outline: 0;" in graph_html and ".person:focus-visible { outline: 0;" in graph_html
        assert ".person span { display: block;" in graph_html and ".person small { display: block;" in graph_html
        assert "matches.hidden = !term" in graph_html and 'id="matches" class="matches people" aria-label="Search results" hidden' in graph_html
        assert 'id="hide-matches"' not in graph_html and "matches-head" not in graph_html and "<h2>Search results</h2>" not in graph_html
        assert ".matches.people" in graph_html and "grid-template-columns: 1fr" in graph_html and "max-height: none; overflow: visible" in graph_html
        assert ".graph-tools { display: grid; grid-template-columns: minmax(0, 1fr) auto;" in graph_html
        assert ".min-filter { grid-column: 1 / -1; display: grid; grid-template-columns: auto minmax(0, 1fr);" in graph_html
        assert 'id="reader" class="reader" hidden' in graph_html and "let selected = null;" in graph_html and "function clearSelection()" in graph_html and 'id="clear-selection"' in graph_html
        assert "reader-footer" in graph_html and "twitter.com/anishthite" in graph_html and "spanner.sh" in graph_html
        assert "metrics-data" in metrics_html and "PageRank" in metrics_html and "Glossary" in metrics_html
        assert "algorithms-data" in algorithms_html and "Graph workbench" in algorithms_html and "HITS" in algorithms_html
        analysis_html = graph_html + metrics_html + algorithms_html + about_html
        assert "About the Curius graph" in about_html and "Most followed people" in about_html and "Most popular saved-link domains" in about_html
        assert about_html.count('class="bar-chart') == 2 and "In one breath" not in about_html and "questions.html" not in analysis_html
        assert "frontpage-data" in frontpage_html and "Curius Links" in frontpage_html and "Popular links" in frontpage_html
        assert 'data-sort="popular"' in frontpage_html and 'data-sort="newest"' in frontpage_html
        assert "data-kind" not in frontpage_html and "highlights:popular" not in frontpage_html
        assert "S<sub>link</sub>" in how_html and "About this list" in how_html and "Scope" in how_html
        assert analysis_html.count('<nav class="nav') == 3
        assert analysis_html.count('href="about.html"') == 4 and analysis_html.count("About") >= 4
        assert 'href="https://front.example/index.html"' in graph_html
        payload = json.loads(re.search(r'<script id="frontpage-data" type="application/json">(.*?)</script>', frontpage_html, re.S).group(1))
        assert payload["views"]["newest"][0]["id"] == 10
        assert payload["views"]["popular"][0]["score"] >= payload["views"]["popular"][-1]["score"]
        assert "<ol id=\"feed\" class=\"hn-list\"><li class=\"hn-item\">" in frontpage_html
        assert 'href="https://analysis.example/index.html"' in frontpage_html + how_html
        assert "ui-sans-serif" not in graph_html + metrics_html + algorithms_html + about_html + frontpage_html + how_html
    print("self-test passed")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="SQLite database path")
    parser.add_argument("--graph-out", type=Path, default=DEFAULT_GRAPH_OUT, help="graph HTML output path")
    parser.add_argument("--metrics-out", type=Path, default=DEFAULT_METRICS_OUT, help="metrics HTML output path")
    parser.add_argument("--algorithms-out", type=Path, default=DEFAULT_ALGORITHMS_OUT, help="algorithms HTML output path")
    parser.add_argument("--about-out", "--next-out", dest="about_out", type=Path, default=DEFAULT_ABOUT_OUT, help="about HTML output path")
    parser.add_argument("--frontpage-out", type=Path, default=DEFAULT_FRONTPAGE_OUT, help="front page HTML output path")
    parser.add_argument("--how-out", type=Path, default=DEFAULT_HOW_OUT, help="front page how-this-works HTML output path")
    parser.add_argument("--copy-file", type=Path, default=DEFAULT_ABOUT_COPY_FILE, help="editable about/frontpage copy JSON")
    parser.add_argument("--frontpage-url", default=os.environ.get("CURIUS_FRONTPAGE_URL", DEFAULT_FRONTPAGE_URL), help="base URL for links from analysis to frontpage")
    parser.add_argument("--analysis-url", default=os.environ.get("CURIUS_ANALYSIS_URL", DEFAULT_ANALYSIS_URL), help="base URL for links from frontpage to analysis")
    parser.add_argument("--self-test", action="store_true", help="run a tiny generated-db check")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    graph = build(
        args.db, args.graph_out, args.metrics_out, args.algorithms_out, args.about_out, args.frontpage_out,
        args.frontpage_url, args.analysis_url, how_out=args.how_out, copy_file=args.copy_file,
    )
    counts = graph["metrics"]["counts"]
    print(f"Wrote {args.frontpage_out}, {args.how_out}, {args.graph_out}, {args.metrics_out}, {args.algorithms_out}, and {args.about_out} ({counts['nodes']:,} people, {counts['edges']:,} follows)")


if __name__ == "__main__":
    main()
