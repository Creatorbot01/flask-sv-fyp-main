"""CRIntegration Dashboard Hoster.  Run: pip install flask && python dashboardhoster.py
Design and config files are JSON. The GPS map needs internet (Leaflet from cdnjs, tiles from OpenStreetMap).

Devices only POST sensor data and GET input widget values (buttons, sliders, text). The dashboard remembers those
input values itself, so devices never need to echo them back.

Device API (all JSON):
  POST /api/data                       device sends {"deviceID":"esp1","deviceName":"Kitchen","temp":24.5,...}
  GET  /api/control/<deviceID>         device reads {"button1":"1","slider1":40,"input1":"hi"}; one-shot buttons clear after read
  GET  /api/control/<deviceID>/<name>  device reads one value; add ?peek=1 to read without clearing
  POST /api/control/<deviceID>         set a control manually, e.g. {"name":"slider1","value":40}
  GET  /api/history/<deviceID>?keys=a,b&n=100   recent numeric values (used by graph widgets)

Logic (variables and scripts made in the Creator's Logic tab, stored in the design file, run on this server):
  POST /api/function/<deviceID>        run a function block: {"function":"alert","params":{"level":3}}
  POST /api/function                   same, with "deviceID" in the body. If the design has a "function" token (Creator,
                                       Tokens tab) or config.json sets function_token, send one as header X-Token
                                       or as "token" in the body.
  GET  /api/vars/<deviceID>            read the shared variables (they are also included in GET /api/control)
  POST /api/vars/<deviceID>            write shared variables: {"count":5,"mode":"auto"}
  GET  /api/logic/<deviceID>           all variables plus recent script log (used by the Logic button)
Tokens: the design file can hold tokens (Creator, Tokens tab). They stay on the server and are never sent to the browser.
A Discord block's webhook is resolved as: full URL, else a design token name, else config.json "discord_webhooks".
config.json extras: "discord_webhooks": {"alerts": "https://discord.com/api/webhooks/..."}, "function_token": "".
"""
import ast
import hmac
import json
import math
import re
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, jsonify, request

BASE = Path(__file__).parent
DEFAULT_DIR = BASE / "defaultDashboardGeneration"
DEFAULT_DIR.mkdir(exist_ok=True)
DEFAULT_CFG = {
    "host": "0.0.0.0",
    "port": 5000,
    "offline_after_seconds": 20,
    "poll_interval_ms": 1000,
    "function_token": "",
    "discord_webhooks": {},
}

PUBLIC_CFG = ("offline_after_seconds", "poll_interval_ms")  # only these reach the browser
ID_KEY, NAME_KEY = "deviceID", "deviceName"  # payload keys are chosen by the device side, not by config.json


def load_cfg():
    p = BASE / "config.json"
    if p.exists():
        return {**DEFAULT_CFG, **json.loads(p.read_text("utf-8"))}
    p.write_text(json.dumps(DEFAULT_CFG, indent=2))
    return dict(DEFAULT_CFG)


CFG = load_cfg()
app = Flask(__name__)
devices = {}    # id -> {"data": {}, "raw": str, "last": float}
controls = {}   # id -> {name: {"value": v, "oneshot": bool}}
override = {"design": None}


def default_design():
    DEFAULT_DIR.mkdir(exist_ok=True)
    files = list(DEFAULT_DIR.glob("*.json"))
    return json.loads(max(files, key=lambda p: p.stat().st_mtime).read_text("utf-8")) if files else None


def active_design():
    if override["design"]:
        return override["design"]
    try:
        return default_design()
    except Exception:
        return None


def control_defaults(design=None):
    """What a device reads for an input widget nobody has touched yet: button idle value, slider start, empty text."""
    out = {}
    design = design if design is not None else active_design()
    for w in (design or {}).get("widgets", []):
        n = w.get("name")
        if not n:
            continue
        if w.get("type") == "button" and w.get("idleValue") not in (None, ""):
            out[n] = w["idleValue"]
        elif w.get("type") == "slider":
            out[n] = w.get("start", 0)
        elif w.get("type") == "input":
            out[n] = ""
    return out


def consume(c, name):
    """One-shot controls are read once, then fall back to their idle value (never just vanish)."""
    item = c.get(name)
    if item and item["oneshot"]:
        if item.get("idle") is not None:
            c[name] = {"value": item["idle"], "oneshot": False, "idle": item["idle"]}
        else:
            del c[name]


# ---------------------------------------------------------------------------------------------------------------
# Logic engine: variables, scripts (block programs made in the Creator's Logic tab), Discord webhooks, functions.
# Scripts live in the design file under "scripts" and run here on the server, so they work with no browser open.
# The browser never receives "scripts" (they may hold webhook URLs); it only receives widget overrides.
# ---------------------------------------------------------------------------------------------------------------
LOCK = threading.RLock()
vstate = {}   # deviceID -> {variable: value}
wover = {}    # deviceID -> {widget: {prop: value}}  (what scripts changed on the website)
logs = deque(maxlen=300)
SEND_TIMES = deque(maxlen=30)

RESERVED = {"data", "param", "controls", "deviceID", "deviceName", "true", "false", "none", "i"}
WIDGET_PROPS = ("value", "label", "visible", "color", "max", "limit")
MAX_STEPS, MAX_REPEAT, MAX_DEPTH, MAX_SENDS_PER_RUN, MAX_SENDS_PER_MIN = 5000, 100, 8, 5, 30
IDENT = re.compile(r"[A-Za-z_]\w*")
TPL = re.compile(r"\{([^{}]*)\}")
WEBHOOK_RE = re.compile(r"^https://(?:(?:canary|ptb)\.)?(?:discord|discordapp)\.com/api(?:/v\d+)?/webhooks/\d+/[\w-]+/?$")
BLOCK_NAMES = {"set": "Set variable", "change": "Change variable", "if": "If", "repeat": "Repeat", "widget": "Set widget",
               "discord": "Discord webhook", "call": "Run function", "log": "Log"}


class ScriptError(Exception):
    tagged = False


def fmt(v):
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float):
        return str(int(v)) if math.isfinite(v) and v == int(v) else str(round(v, 6))
    if isinstance(v, (dict, list)):
        return json.dumps(v)
    return str(v)


def autotype(v):
    """Text that looks like a number or true/false becomes one (Scratch style), everything else is unchanged."""
    if isinstance(v, str):
        s = v.strip()
        if s.lower() in ("true", "false"):
            return s.lower() == "true"
        if re.fullmatch(r"-?\d+", s):
            return int(s)
        try:
            f = float(s)
            if math.isfinite(f) and s.lower() not in ("nan", "inf", "-inf", "infinity", "-infinity"):
                return f
        except ValueError:
            pass
    return v


def truthy(v):
    return bool(autotype(v))


def to_num(x):
    x = autotype(x)
    if isinstance(x, bool):
        return int(x)
    if isinstance(x, (int, float)):
        return x
    raise ScriptError(f"'{fmt(x)}' is not a number")


def num_or(x, default=0):
    try:
        return to_num(x)
    except ScriptError:
        return default


FUNCS = {
    "round": lambda x, n=0: round(to_num(x), int(to_num(n))),
    "abs": lambda x: abs(to_num(x)),
    "min": lambda *a: min(to_num(x) for x in a),
    "max": lambda *a: max(to_num(x) for x in a),
    "len": lambda x: len(x) if isinstance(x, (str, list, dict)) else len(fmt(x)),
    "str": fmt,
    "num": num_or,
    "int": lambda x: int(to_num(x)),
    "upper": lambda x: fmt(x).upper(),
    "lower": lambda x: fmt(x).lower(),
    "contains": lambda a, b: fmt(b).lower() in fmt(a).lower(),
    "split": lambda x, sep=",": [q.strip() for q in fmt(x).split(fmt(sep))],
    "isnum": lambda x: isinstance(autotype(x), (int, float)) and not isinstance(autotype(x), bool),
    "now": time.time,
    "clock": lambda: time.strftime("%H:%M:%S"),
}
ARITH = {ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b, ast.Mult: lambda a, b: a * b,
         ast.Div: lambda a, b: a / b, ast.Mod: lambda a, b: a % b, ast.FloorDiv: lambda a, b: a // b}


def _arith(op, a, b):
    if isinstance(op, ast.Add):
        an, bn = autotype(a), autotype(b)
        if isinstance(a, str) or isinstance(b, str):
            if not (isinstance(an, (int, float)) and isinstance(bn, (int, float))):
                return fmt(a) + fmt(b)  # text + anything joins text
    a, b = to_num(a), to_num(b)
    if isinstance(op, (ast.Div, ast.Mod, ast.FloorDiv)) and b == 0:
        raise ScriptError("division by zero")
    return ARITH[type(op)](a, b)


def _cmp(op, a, b):
    if isinstance(op, (ast.In, ast.NotIn)):
        hit = (a in b) if isinstance(b, (list, tuple)) else fmt(a).lower() in fmt(b).lower()
        return hit if isinstance(op, ast.In) else not hit
    if isinstance(op, (ast.Lt, ast.LtE, ast.Gt, ast.GtE)) and (a is None or b is None):
        return False  # a missing payload key never passes a < or > test
    an, bn = autotype(a), autotype(b)
    if isinstance(an, (int, float)) and isinstance(bn, (int, float)):
        a, b = an, bn
    else:
        a, b = fmt(a).lower(), fmt(b).lower()  # text compares ignore case
    return {ast.Eq: a == b, ast.NotEq: a != b, ast.Lt: a < b, ast.LtE: a <= b, ast.Gt: a > b, ast.GtE: a >= b}[type(op)]


def _ev(n, env, st):
    st["n"] += 1
    if st["n"] > 2000:
        raise ScriptError("expression too complex")
    if isinstance(n, ast.Constant) and isinstance(n.value, (int, float, str, bool, type(None))):
        return n.value
    if isinstance(n, ast.Name):
        if n.id in env:
            return env[n.id]
        raise ScriptError(f"unknown name '{n.id}'")
    if isinstance(n, ast.BoolOp):
        if isinstance(n.op, ast.And):
            return all(truthy(_ev(v, env, st)) for v in n.values)
        return any(truthy(_ev(v, env, st)) for v in n.values)
    if isinstance(n, ast.UnaryOp):
        v = _ev(n.operand, env, st)
        if isinstance(n.op, ast.Not):
            return not truthy(v)
        if isinstance(n.op, ast.USub):
            return -to_num(v)
        if isinstance(n.op, ast.UAdd):
            return to_num(v)
    if isinstance(n, ast.BinOp) and type(n.op) in ARITH:
        return _arith(n.op, _ev(n.left, env, st), _ev(n.right, env, st))
    if isinstance(n, ast.Compare):
        left = _ev(n.left, env, st)
        for op, c in zip(n.ops, n.comparators):
            right = _ev(c, env, st)
            if not _cmp(op, left, right):
                return False
            left = right
        return True
    if isinstance(n, ast.IfExp):
        return _ev(n.body if truthy(_ev(n.test, env, st)) else n.orelse, env, st)
    if isinstance(n, ast.Attribute):
        base = _ev(n.value, env, st)
        if isinstance(base, dict) and not n.attr.startswith("_"):
            return base.get(n.attr)
        raise ScriptError(f"cannot read '.{n.attr}' here (use data.key, param.key or controls.key)")
    if isinstance(n, ast.Subscript):
        base, idx = _ev(n.value, env, st), _ev(n.slice, env, st)
        if isinstance(base, dict):
            return base.get(idx if isinstance(idx, str) else fmt(idx))
        if isinstance(base, (list, str)):
            k = int(to_num(idx))
            return base[k] if -len(base) <= k < len(base) else None
        raise ScriptError("cannot use [ ] on that value")
    if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in FUNCS and not n.keywords:
        return FUNCS[n.func.id](*[_ev(a, env, st) for a in n.args])
    if isinstance(n, ast.Call):
        name = n.func.id if isinstance(n.func, ast.Name) else "?"
        raise ScriptError(f"unknown function '{name}' (allowed: {', '.join(FUNCS)})")
    if isinstance(n, (ast.List, ast.Tuple)):
        return [_ev(x, env, st) for x in n.elts]
    raise ScriptError("unsupported syntax")


def evaluate(text, env):
    text = "" if text is None else str(text).strip()
    m = TPL.fullmatch(text)
    if m:
        text = m.group(1).strip()
    if not text:
        return None
    if len(text) > 300:
        raise ScriptError("expression too long")
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError:
        raise ScriptError(f"cannot read expression '{text}'")
    try:
        return _ev(tree.body, env, {"n": 0})
    except ScriptError as e:
        raise ScriptError(f"{e} (in '{text}')")
    except Exception as e:
        raise ScriptError(f"{e} (in '{text}')")


def render(text, env):
    """Text with {expressions}. A field that is only one {expression} keeps its type (number, true/false)."""
    text = "" if text is None else str(text)
    m = TPL.fullmatch(text.strip())
    if m:
        return evaluate(m.group(1), env)
    return TPL.sub(lambda mm: fmt(evaluate(mm.group(1), env)), text)


def scope_of(v):
    return "local" if v.get("scope") == "local" else "shared"


def var_defs(design):
    out = {}
    for v in (design or {}).get("variables") or []:
        n = str((v or {}).get("name", ""))
        if IDENT.fullmatch(n) and n not in RESERVED:
            out[n] = v
    return out


def get_vars(dev, defs):
    vs = vstate.setdefault(dev, {})
    for n, v in defs.items():
        if n not in vs:
            vs[n] = autotype(v.get("initial", ""))
    return vs


def shared_vars(dev, design):
    defs = var_defs(design)
    vs = get_vars(dev, defs)
    return {n: vs[n] for n, v in defs.items() if scope_of(v) == "shared"}


def log_line(dev, src, level, msg, out=None):
    entry = {"t": round(time.time(), 2), "dev": dev, "src": src, "level": level, "msg": str(msg)[:500]}
    logs.append(entry)
    if out is not None:
        out.append(f"{level}: {entry['msg']}")


class Run:
    def __init__(self, dev, script, params, design=None, parent=None):
        self.dev, self.script, self.params, self.i = dev, script, params, None
        self.name = str(script.get("name") or "script")
        if parent:
            self.ctx, self.defs, self.scripts, self.widgets = parent.ctx, parent.defs, parent.scripts, parent.widgets
            self.tokens = parent.tokens
            self.vs, self.depth = parent.vs, parent.depth + 1
            return
        design = design or {}
        d = devices.get(dev) or {}
        self.defs, self.scripts, self.depth = var_defs(design), design.get("scripts") or [], 0
        self.widgets = {w.get("name") for w in design.get("widgets", []) if w.get("name")}
        self.tokens = {str(t.get("name")): str(t.get("value")) for t in design.get("tokens") or []
                       if isinstance(t, dict) and t.get("kind", "discord") == "discord" and t.get("value")}
        self.vs = get_vars(dev, self.defs)
        ctrl = {**control_defaults(design), **{k: v["value"] for k, v in controls.get(dev, {}).items()}}
        self.ctx = {"steps": 0, "sends": 0, "out": [],
                    "base": {"true": True, "false": False, "none": None, "data": dict(d.get("data", {})), "controls": ctrl,
                             "deviceID": dev, "deviceName": d.get("name") or dev}}

    def env(self):
        e = dict(self.vs)
        e.update(self.ctx["base"])
        e["param"] = self.params
        if self.i is not None:
            e["i"] = self.i
        return e

    def log(self, level, msg):
        log_line(self.dev, self.name, level, msg, self.ctx["out"])


def exec_blocks(blocks, run):
    for b in blocks or []:
        if not isinstance(b, dict):
            continue
        run.ctx["steps"] += 1
        if run.ctx["steps"] > MAX_STEPS:
            raise ScriptError("Stopped: too many steps (endless loop?)")
        try:
            exec_one(b, run)
        except ScriptError as e:
            if not e.tagged:
                e = ScriptError(f"{BLOCK_NAMES.get(b.get('t'), b.get('t'))} block: {e}")
                e.tagged = True
            raise e


def need_var(run, name):
    if name not in run.defs:
        raise ScriptError(f"variable '{name}' is not defined (add it in the Variables list)")
    return name


def exec_one(b, run):
    t, env = b.get("t"), run.env()
    if t == "set":
        run.vs[need_var(run, b.get("var"))] = autotype(render(b.get("value", ""), env))
    elif t == "change":
        n = need_var(run, b.get("var"))
        run.vs[n] = num_or(run.vs.get(n), 0) + to_num(render(b.get("value", "1"), env))
    elif t == "if":
        exec_blocks(b.get("then") if truthy(evaluate(b.get("cond"), env)) else b.get("else"), run)
    elif t == "repeat":
        times = max(0, min(int(to_num(render(b.get("times", "1"), env))), MAX_REPEAT))
        old = run.i
        for k in range(1, times + 1):
            run.i = k
            exec_blocks(b.get("body"), run)
        run.i = old
    elif t == "widget":
        w, prop = str(b.get("widget") or ""), b.get("prop")
        if w not in run.widgets:
            raise ScriptError(f"widget '{w}' is not in the loaded design")
        if prop not in WIDGET_PROPS:
            raise ScriptError(f"unknown widget property '{prop}'")
        raw = render(b.get("value", ""), env)
        slot = wover.setdefault(run.dev, {}).setdefault(w, {})
        if raw is None or fmt(raw) == "":
            slot.pop(prop, None)  # blank clears the change, the widget goes back to normal
        elif prop == "visible":
            slot[prop] = truthy(raw)
        elif prop in ("max", "limit"):
            slot[prop] = to_num(raw)
        else:
            slot[prop] = raw if prop == "value" else fmt(raw)
    elif t == "discord":
        send_discord(b, env, run)
    elif t == "call":
        fn = str(b.get("fn") or "")
        s = next((x for x in run.scripts if x.get("trigger") == "function" and x.get("name") == fn), None)
        if not s:
            raise ScriptError(f"function '{fn}' does not exist")
        if run.depth >= MAX_DEPTH:
            raise ScriptError("functions are nested too deeply")
        args = {k: autotype(render(v, env)) for k, v in (b.get("args") or {}).items()}
        child = Run(run.dev, s, {**{p: None for p in s.get("params") or []}, **args}, parent=run)
        exec_blocks(s.get("blocks"), child)
    elif t == "log":
        run.log("log", fmt(render(b.get("value", ""), env)))
    else:
        raise ScriptError(f"unknown block type '{t}'")


def _post_discord(url, payload, dev, src):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "User-Agent": "CRIntegration/1.0"})
    try:
        urllib.request.urlopen(req, timeout=8).close()
        log_line(dev, src, "discord", "Discord message sent")
    except urllib.error.HTTPError as e:  # never include the URL in logs, the browser can read them
        log_line(dev, src, "error", f"Discord refused the message (HTTP {e.code})")
    except Exception as e:
        log_line(dev, src, "error", f"Discord message failed: {type(e).__name__}")


def send_discord(b, env, run):
    if run.ctx["sends"] >= MAX_SENDS_PER_RUN:
        raise ScriptError(f"too many Discord messages in one run (limit {MAX_SENDS_PER_RUN})")
    now = time.time()
    if len([x for x in SEND_TIMES if now - x < 60]) >= MAX_SENDS_PER_MIN:
        raise ScriptError(f"Discord limit reached ({MAX_SENDS_PER_MIN} messages per minute)")
    target = fmt(render(b.get("url", ""), env)).strip()
    url = target if target.startswith("http") else (run.tokens.get(target) or (CFG.get("discord_webhooks") or {}).get(target))
    if not url or not WEBHOOK_RE.match(str(url)):
        what = "the pasted URL" if target.startswith("http") else f"'{target}'"
        raise ScriptError(f"{what} is not a valid Discord webhook (use a Discord token name from the Tokens tab, a name from config.json discord_webhooks, or a discord.com webhook URL)")
    txt = lambda k, src=b, lim=2000: fmt(render(src.get(k, ""), env))[:lim]
    payload = {}
    if txt("content"):
        payload["content"] = txt("content")
    if txt("username"):
        payload["username"] = txt("username", lim=80)
    if txt("avatar"):
        payload["avatar_url"] = txt("avatar", lim=2048)
    e = b.get("embed") or {}
    if e.get("enabled"):
        emb = {}
        for k, lim in (("title", 256), ("description", 4096), ("url", 2048)):
            if txt(k, e, lim):
                emb[k] = txt(k, e, lim)
        if txt("author", e, 256):
            emb["author"] = {"name": txt("author", e, 256)}
        if txt("footer", e, 2048):
            emb["footer"] = {"text": txt("footer", e, 2048)}
        for k in ("thumbnail", "image"):
            if txt(k, e, 2048):
                emb[k] = {"url": txt(k, e, 2048)}
        fields = []
        for q in (e.get("fields") or [])[:25]:
            nm, val = txt("name", q, 256), txt("value", q, 1024)
            if nm and val:
                fields.append({"name": nm, "value": val, "inline": bool(q.get("inline"))})
        if fields:
            emb["fields"] = fields
        if emb:  # color and timestamp alone do not make an embed
            if re.fullmatch(r"#[0-9a-fA-F]{6}", str(e.get("color") or "")):
                emb["color"] = int(e["color"][1:], 16)
            if e.get("timestamp"):
                emb["timestamp"] = datetime.now(timezone.utc).isoformat()
            payload["embeds"] = [emb]
    if not payload.get("content") and not payload.get("embeds"):
        raise ScriptError("the message is empty (add message text or an embed with content)")
    run.ctx["sends"] += 1
    SEND_TIMES.append(now)
    threading.Thread(target=_post_discord, args=(url, payload, run.dev, run.name), daemon=True).start()
    run.log("discord", "Discord message queued")


def trigger(kind, dev, params=None, fn=None):
    """Run every script with this trigger (or the one function called fn). Returns {"ran", "errors", "log"}."""
    res = {"ran": 0, "errors": 0, "log": []}
    with LOCK:
        design = active_design() or {}
        for s in design.get("scripts") or []:
            if not isinstance(s, dict) or s.get("trigger") != kind or (kind == "function" and s.get("name") != fn):
                continue
            p = {**{k: None for k in s.get("params") or []}, **(params or {})}
            run = Run(dev, s, p, design=design)
            try:
                exec_blocks(s.get("blocks"), run)
            except ScriptError as e:
                run.log("error", e)
                res["errors"] += 1
            except Exception as e:
                run.log("error", f"Internal error: {e}")
                res["errors"] += 1
            res["ran"] += 1
            res["log"] += run.ctx["out"]
    return res


def public_design(d):
    """The browser gets the design without scripts and tokens (both can hold secrets)."""
    return {k: v for k, v in d.items() if k not in ("scripts", "tokens")} if isinstance(d, dict) else d


def dev_info(i, d):
    age = time.time() - d["last"]
    return {"id": i, "name": d.get("name") or i, "online": age <= CFG["offline_after_seconds"], "age": round(age, 1),
            "last": d["last"], "data": d["data"], "raw": d["raw"],
            "controls": {k: v["value"] for k, v in controls.get(i, {}).items()}, "widgets": wover.get(i, {})}


@app.route("/api/config")
def api_config():
    # never return the whole config: anything private added to config.json later must stay on the server
    return jsonify({k: CFG[k] for k in PUBLIC_CFG})


@app.route("/api/design", methods=["GET", "POST", "DELETE"])
def api_design():
    if request.method == "POST":
        try:
            design = json.loads(request.get_data(as_text=True))
            assert isinstance(design, dict) and isinstance(design.get("widgets"), list)
        except Exception:
            return jsonify(error="Invalid design file. Upload a .json design made by CRIntegration Creator."), 400
        override["design"] = design
        vstate.clear()
        wover.clear()
    elif request.method == "DELETE":
        override["design"] = None
        vstate.clear()
        wover.clear()
    if override["design"]:
        return jsonify(design=public_design(override["design"]), source="uploaded")
    try:
        design = default_design()
    except Exception as e:
        return jsonify(design=None, source="none", message=f"The default design file could not be read: {e}")
    if design is None:
        return jsonify(design=None, source="none",
                       message="No default dashboard given. Put a .json design file in the defaultDashboardGeneration folder, or use Upload design.")
    return jsonify(design=public_design(design), source="default folder")


@app.route("/api/data", methods=["POST"])
def api_data():
    payload = request.get_json(force=True, silent=True)
    if not isinstance(payload, dict):
        return jsonify(error="Body must be a JSON object"), 400
    dev = str(payload.get(ID_KEY) or request.args.get(ID_KEY) or "unknown")
    d = devices.setdefault(dev, {"data": {}, "raw": "", "last": 0})
    name = payload.get(NAME_KEY) or request.args.get(NAME_KEY)
    if name:
        d["name"] = str(name)
    d["data"].update(payload)
    for k, v in payload.items():
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            d.setdefault("hist", {}).setdefault(k, deque(maxlen=1000)).append([round(time.time(), 2), v])
    d["raw"] = json.dumps(payload)
    d["last"] = time.time()
    trigger("data", dev)
    return jsonify(ok=True, device=dev)


@app.route("/api/devices")
def api_devices():
    return jsonify([dev_info(i, d) for i, d in devices.items()])


@app.route("/api/history/<dev>")
def api_history(dev):
    d = devices.get(dev)
    keys = [k for k in request.args.get("keys", "").split(",") if k]
    n = max(1, min(request.args.get("n", 100, type=int), 1000))
    return jsonify({k: list(d.get("hist", {}).get(k, []))[-n:] for k in keys} if d else {})


@app.route("/api/control/<dev>", methods=["GET", "POST"])
def api_control(dev):
    c = controls.setdefault(dev, {})
    if request.method == "POST":
        b = request.get_json(force=True, silent=True) or {}
        if "name" not in b:
            return jsonify(error="name required"), 400
        c[b["name"]] = {"value": b.get("value"), "oneshot": bool(b.get("oneshot")), "idle": b.get("idle")}
        trigger("control", dev, {"name": b["name"], "value": b.get("value")})
        return jsonify(ok=True)
    design = active_design()
    out = {**control_defaults(design), **shared_vars(dev, design), **{k: v["value"] for k, v in c.items()}}
    if not request.args.get("peek"):
        for k in [k for k, v in c.items() if v["oneshot"]]:
            consume(c, k)
    return jsonify(out)


@app.route("/api/control/<dev>/<name>")
def api_control_one(dev, name):
    c = controls.setdefault(dev, {})
    item = c.get(name)
    design = active_design()
    val = item["value"] if item else {**control_defaults(design), **shared_vars(dev, design)}.get(name)
    if item and not request.args.get("peek"):
        consume(c, name)
    return jsonify({name: val})


@app.route("/api/function", methods=["POST"])
@app.route("/api/function/<dev>", methods=["POST"])
def api_function(dev=None):
    b = request.get_json(force=True, silent=True)
    toks = [str(CFG.get("function_token") or "")] + [str(t.get("value") or "") for t in (active_design() or {}).get("tokens") or []
                                                      if isinstance(t, dict) and t.get("kind") == "function"]
    toks = [x.encode() for x in toks if x]
    given = str(request.headers.get("X-Token") or (b if isinstance(b, dict) else {}).get("token") or "").encode()
    if toks and not any(hmac.compare_digest(given, x) for x in toks):
        return jsonify(error="Missing or wrong token (header X-Token)"), 401
    if not isinstance(b, dict) or not b.get("function"):
        return jsonify(error='Body must be JSON like {"function":"name","params":{"key":"value"}}'), 400
    dev = str(dev or b.get(ID_KEY) or request.args.get(ID_KEY) or "")
    params = b.get("params") if b.get("params") is not None else {}
    if not dev:
        return jsonify(error="deviceID required (in the URL, the body or ?deviceID=)"), 400
    if not isinstance(params, dict):
        return jsonify(error='"params" must be a JSON object'), 400
    fn = str(b["function"])
    res = trigger("function", dev, params, fn=fn)
    if not res["ran"]:
        names = [s.get("name") for s in (active_design() or {}).get("scripts") or [] if s.get("trigger") == "function"]
        return jsonify(error=f"No function named '{fn}' in the loaded design", available=names), 404
    return jsonify(ok=not res["errors"], function=fn, device=dev, log=res["log"]), (200 if not res["errors"] else 422)


@app.route("/api/vars/<dev>", methods=["GET", "POST"])
def api_vars(dev):
    design = active_design()
    with LOCK:
        if request.method == "POST":
            b = request.get_json(force=True, silent=True)
            defs = var_defs(design)
            if not isinstance(b, dict):
                return jsonify(error="Body must be a JSON object like {\"count\":5}"), 400
            bad = [k for k in b if k not in defs or scope_of(defs[k]) != "shared"]
            if bad:
                return jsonify(error="Not a shared variable: " + ", ".join(bad)), 400
            vs = get_vars(dev, defs)
            for k, v in b.items():
                vs[k] = autotype(v)
        return jsonify(shared_vars(dev, design))


@app.route("/api/logic/<dev>")
def api_logic(dev):
    design = active_design()
    defs = var_defs(design)
    with LOCK:
        vs = get_vars(dev, defs)
        out = [{"name": n, "scope": scope_of(v), "value": vs.get(n)} for n, v in defs.items()]
    return jsonify(vars=out, log=[e for e in logs if e["dev"] == dev][-100:])


PAGE = r"""<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>CRIntegration</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>
<style>
:root{--bg:#e8ecef;--pn:#fff;--ink:#1c2a33;--mut:#6b7c88;--ac:#0f6e8c;--ok:#0f8f6b;--al:#d6452b;--ln:#cfd7dd;--hd:#1c2a33}
[data-theme=dark]{--bg:#12191e;--pn:#1b252c;--ink:#e6eef2;--mut:#8ea0ac;--ac:#2f95b8;--ln:#2f3d47;--hd:#0b1115}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.4 Bahnschrift,"DIN Alternate","Segoe UI",system-ui,sans-serif;display:grid;grid-template:auto auto 1fr/210px 1fr;height:100vh}
header{grid-column:1/3;background:var(--hd);color:#fff;display:flex;gap:10px;align-items:center;padding:8px 14px}
header h1{font-size:15px;font-weight:400;margin:0;flex:1;display:flex;align-items:baseline;gap:12px}.brand{font-size:22px;font-weight:700;letter-spacing:.5px}#ttl{color:#9fb2bf}
#clk{font-variant-numeric:tabular-nums;font-size:18px;margin-right:8px}
button,input{font:inherit;color:var(--ink)}button{background:var(--ac);color:#fff;border:0;border-radius:4px;padding:6px 11px;cursor:pointer}
header button.g{background:transparent;color:#fff;border:1px solid #6b7c88}button:focus-visible,input:focus-visible{outline:2px solid var(--al);outline-offset:2px}
#st{grid-column:1/3;background:var(--pn);border-bottom:1px solid var(--ln);padding:8px 14px;display:flex;gap:18px;align-items:center}
#stl{white-space:nowrap}#stt{margin-left:auto;text-align:right;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--mut)}#stt code{color:var(--ink)}
.dot{width:11px;height:11px;border-radius:50%;background:var(--mut);display:inline-block;margin-right:6px}
#side{background:var(--pn);border-right:1px solid var(--ln);overflow:auto;padding:10px}#side h3{margin:2px 0 8px;font-size:14px}
.dv{padding:8px;border-radius:4px;cursor:pointer;border:1px solid transparent}.dv.s{border-color:var(--ac)}.dv small{display:block;color:var(--mut)}
main{padding:14px;overflow:auto}#grid{position:relative}
.card{position:absolute;background:var(--pn);border-radius:6px;padding:8px 10px;display:flex;flex-direction:column;overflow:hidden;border:1px solid var(--ln);container-type:size;isolation:isolate;z-index:1}
.card h4{margin:0 0 4px;font-size:13px;color:var(--mut);font-weight:600}.bd{flex:1;min-height:0;display:flex;flex-direction:column;justify-content:center;position:relative}
.bd.map{margin:0 -10px -8px;justify-content:flex-start}.mpw{flex:1;min-height:0;position:relative}.mp{position:absolute;inset:0}.er{position:absolute;inset:0;display:none;align-items:center;justify-content:center;background:rgba(214,69,43,.9);color:#fff;font-weight:600;z-index:1200}.gc{padding:3px 10px;font-size:12px;color:var(--mut);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.big{font-size:clamp(16px,30cqh,72px);word-break:break-word;line-height:1.15}.tr{height:14px;background:var(--ln);border-radius:7px;overflow:hidden;position:relative;margin:6px 0}
.tr i{display:block;height:100%;transition:width .3s,background .3s}.tr b{position:absolute;top:0;bottom:0;width:2px;background:var(--ink)}
.bd input[type=range]{width:100%}.bd img{max-width:100%;max-height:100%;border-radius:4px;align-self:center}
.bd>button{flex:1;width:100%;padding:10px;font-size:clamp(14px,22cqh,40px);transition:background .15s}.row{display:flex;gap:6px}.row button{height:clamp(32px,30cqh,72px);font-size:clamp(13px,14cqh,26px)}.row input{flex:1;min-width:0;padding:7px;height:clamp(32px,30cqh,72px);font-size:clamp(13px,14cqh,26px);border:1px solid var(--ln);border-radius:4px;background:var(--pn)}
input::placeholder{color:var(--mut);opacity:.7}.hint{color:var(--mut);padding:24px}
.gr line,.gr polyline,.gr polygon{vector-effect:non-scaling-stroke}
.gw svg{display:block}
[data-theme=dark] .leaflet-tile{filter:invert(1) hue-rotate(180deg) brightness(.95) contrast(.9)}
#bd,#lb{position:fixed;inset:0;background:rgba(10,18,23,.6);display:none;align-items:center;justify-content:center;z-index:2000}
#bd.show,#lb.show{display:flex}#md,#lm{background:var(--pn);width:min(560px,92vw);border-radius:8px;padding:16px;box-shadow:0 12px 40px rgba(0,0,0,.3)}
#md pre,#lm pre{background:#101b22;color:#d6f0e6;padding:12px;border-radius:4px;max-height:50vh;overflow:auto;margin:10px 0;white-space:pre-wrap}#md h3,#lm h3{margin:0}
@media(max-width:760px){body{grid-template:auto auto auto 1fr/1fr;height:auto}header,#st{grid-column:1}#side{border:0;max-height:160px}}
</style>
<header><h1><span class="brand">CRIntegration</span><span id="ttl"></span></h1><span id="clk"></span>
<button class="g" id="tg"></button><button class="g" onclick="up.click()">Upload design</button><button class="g" onclick="resetDesign()">Use default design</button>
<button class="g" onclick="showLogic()">Logic</button><button onclick="showLast()">Last data</button><input type="file" id="up" hidden accept=".json"></header>
<div id="st"><span id="stl"><span class="dot"></span>No device selected</span><span id="stt"></span></div>
<div id="side"><h3>Devices</h3><div id="dl"></div></div>
<main><div id="grid"></div></main>
<div id="bd" onclick="if(event.target==this)closeM()"><div id="md" role="dialog" aria-modal="true"><h3 id="mt">Last data post</h3><small id="ms"></small><pre id="mr"></pre><button onclick="closeM()">Close</button></div></div>
<div id="lb" onclick="if(event.target==this)closeL()"><div id="lm" role="dialog" aria-modal="true"><h3>Variables and script log</h3><small id="ls"></small><pre id="lv"></pre><pre id="ll"></pre><button onclick="closeL()">Close</button></div></div>
<script>
const $=id=>document.getElementById(id),esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const th=t=>{document.documentElement.dataset.theme=t;$('tg').textContent=t=='dark'?'Light mode':'Dark mode';try{localStorage.setItem('crintegration-theme',t)}catch(e){}};
let saved;try{saved=localStorage.getItem('crintegration-theme')}catch(e){}th(saved||(matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light'));
$('tg').onclick=()=>th(document.documentElement.dataset.theme=='dark'?'light':'dark');
const NOSIG='[null,null,null,null]',RE=['bar','meter','button','graph'];
let cfg={},design={widgets:[]},msg='',cur=null,devs=[],items=[],hist={};const held=new Set();
setInterval(()=>$('clk').textContent=new Date().toLocaleTimeString(),500);
const send=(name,value,oneshot,idle)=>cur?fetch('/api/control/'+encodeURIComponent(cur),{method:'POST',body:JSON.stringify({name,value,oneshot,idle})}):alert('Select a device first, controls are sent to a registered device.');
function niceStep(r,n){const raw=r/n,e=Math.pow(10,Math.floor(Math.log10(raw))),f=raw/e;return(f<=1?1:f<=2?2:f<=5?5:10)*e}
function graphSVG(pts,w,W,H){
 const pl=40,pr=12,pt=8,pb=20,pw=W-pl-pr,ph=H-pt-pb,ok=x=>String(x??'').trim()!==''&&isFinite(+x),fx=n=>+n.toFixed(2);
 if(pw<40||ph<30||!pts.length)return'';
 const vs=pts.map(q=>q[1]);let lo=ok(w.yMin)?+w.yMin:Math.min(...vs),hi=ok(w.yMax)?+w.yMax:Math.max(...vs);
 if(!(hi>lo)){if(ok(w.yMin)||ok(w.yMax))hi=lo+1;else{lo-=1;hi+=1}}
 const sy=niceStep(hi-lo,Math.max(2,Math.min(6,Math.floor(ph/34))));
 if(!ok(w.yMin))lo=Math.floor(lo/sy+1e-9)*sy;if(!ok(w.yMax))hi=Math.ceil(hi/sy-1e-9)*sy;
 const Y=v=>pt+ph-(Math.min(hi,Math.max(lo,v))-lo)/(hi-lo)*ph,tx='style="fill:var(--mut);font-size:10px"',gl='style="stroke:var(--ln)"';let g='';
 for(let i=Math.ceil(lo/sy-1e-9);i*sy<=hi+1e-9;i++){const v=i*sy,y=Y(v);g+=`<line x1="${pl}" x2="${pl+pw}" y1="${fx(y)}" y2="${fx(y)}" ${gl}/><text x="${pl-5}" y="${fx(y+3.5)}" text-anchor="end" ${tx}>${fx(v)}</text>`}
 const t1=pts[pts.length-1][0],T=Math.max(1,t1-pts[0][0]),sx=niceStep(T,Math.max(2,Math.min(8,Math.floor(pw/70))));
 for(let i=0;i*sx<=T+1e-9;i++){const a=i*sx,x=pl+pw-a/T*pw,lab=i==0?'now':sx>=60?`-${fx(a/60)}m`:`-${fx(a)}s`;
  g+=`<line x1="${fx(x)}" x2="${fx(x)}" y1="${pt}" y2="${pt+ph}" ${gl}/><text x="${fx(x)}" y="${H-5}" text-anchor="${i==0?'end':'middle'}" ${tx}>${lab}</text>`}
 const c=w.color||'#0f6e8c',xy=pts.map(q=>[pl+pw-(t1-q[0])/T*pw,Y(q[1])]),line=xy.map(q=>q.map(fx).join(',')).join(' '),l=xy[xy.length-1];
 return`<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">${g}<polygon fill="${c}" fill-opacity=".15" points="${fx(xy[0][0])},${pt+ph} ${line} ${fx(l[0])},${pt+ph}"/><polyline fill="none" stroke="${c}" stroke-width="2" stroke-linejoin="round" points="${line}"/><circle cx="${fx(l[0])}" cy="${fx(l[1])}" r="3.5" fill="${c}"/></svg>`}
function geo(v){let p=v;if(typeof v=='string')p=v.split(',').map(s=>s.trim()===''?NaN:+s);else if(v&&typeof v=='object'&&!Array.isArray(v))p=[v.lat??v.latitude,v.lng??v.lon??v.longitude];
 return Array.isArray(p)&&p.length==2&&p.every(n=>typeof n=='number'&&isFinite(n))&&Math.abs(p[0])<=90&&Math.abs(p[1])<=180?p:null}
const mk={
 text:(w,b)=>v=>b.innerHTML=`<div class=big>${esc(v??w.placeholder??'--')}</div>`,
 bar:(w,b)=>{b.innerHTML='<div class=tr><i></i></div><span></span>';const i=b.querySelector('i'),s=b.querySelector('span');
  return v=>{v=v??w.placeholder;const m=+w.max||100;i.style.width=Math.max(0,Math.min(100,+v/m*100))+'%';i.style.background=w.color||'var(--ac)';s.textContent=`${v} / ${m}`}},
 meter:(w,b)=>{const m=+w.max||100,pc=w.showPercent!==false;b.innerHTML=`<div class=tr><i></i><b style="left:${Math.min(100,w.limit/m*100)}%"></b></div><span></span>`;const i=b.querySelector('i'),s=b.querySelector('span');
  return v=>{v=+(v??w.placeholder);i.style.width=Math.max(0,Math.min(100,v/m*100))+'%';i.style.background=v>+w.limit?w.alertColor:w.color;s.textContent=pc?`${(v/m*100).toFixed(0)}% (limit ${(w.limit/m*100).toFixed(0)}%)`:`${v} (limit ${w.limit})`}},
 image:(w,b)=>{b.innerHTML='<img alt="">';const im=b.firstChild;return v=>{v=v||w.placeholder||'';const u=/^(https?:|data:|\/)/.test(v)?v:v?'data:image/jpeg;base64,'+v:'';if(im.dataset.u!==u){im.dataset.u=u;im.src=u}}},
 button:(w,b)=>{const one=w.oneshot!==false,idle=w.idleValue??'';b.innerHTML=`<button aria-label="${esc(w.label)}" style="background:${w.color||''}">${w.labelMode=='top'?'':esc(w.label)}</button>`;const x=b.firstChild;let t,on=false,skip=0;
  const col=()=>x.style.background=on?(w.pressColor||'var(--ok)'):(w.color||'');
  if(one){x.onclick=()=>{clearTimeout(t);x.style.background=w.pressColor||'var(--ok)';t=setTimeout(col,+w.pressMs||400);send(w.name,w.value,true,idle===''?null:idle)};return()=>{}}
  x.onclick=()=>{on=!on;skip=Date.now()+1500;col();send(w.name,on?w.value:idle,false)};
  return(v,d)=>{if(Date.now()<skip)return;const s=!!(d&&d.controls&&String(d.controls[w.name])===String(w.value));if(s!==on){on=s;col()}}},
 slider:(w,b)=>{b.innerHTML=`<input type=range min=${w.start} max=${w.limit} value=${w.start}><div class=big></div>`;const r=b.firstChild,o=b.lastChild,k='s:'+w.name;let t,ld;o.textContent=r.value;
  const rel=()=>{clearTimeout(t);t=setTimeout(()=>held.delete(k),800)};let st;
  r.onpointerdown=()=>held.add(k);r.onpointerup=r.onpointercancel=rel;
  r.oninput=()=>{held.add(k);rel();o.textContent=r.value;clearTimeout(st);st=setTimeout(()=>send(w.name,+r.value,false),120)};
  return(v,d)=>{const c=d&&d.controls&&w.name in d.controls?d.controls[w.name]:undefined;if(c!==undefined)v=c;if(v===undefined||v===ld||held.has(k))return;ld=v;r.value=v;o.textContent=r.value}},
 input:(w,b)=>{const auto=w.mode=='auto',k='i:'+w.name;b.innerHTML=`<div class=row><input type=text placeholder="${esc(w.placeholder)}">${auto?'':`<button>${esc(w.sendLabel||'Send')}</button>`}</div>${auto?`<small style="color:var(--mut)">sends after ${+w.delay||2.5}s without typing</small>`:''}`;
  const i=b.querySelector('input'),btn=b.querySelector('button');let t,ld;
  const fire=()=>{clearTimeout(t);held.delete(k);send(w.name,i.value,false)};
  i.oninput=()=>{held.add(k);clearTimeout(t);if(auto)t=setTimeout(fire,(+w.delay||2.5)*1000)};
  i.onkeydown=e=>{if(e.key=='Enter')fire()};i.onblur=()=>{if(!auto)held.delete(k)};if(btn)btn.onclick=fire;
  return(v,d)=>{const c=d&&d.controls&&w.name in d.controls?d.controls[w.name]:undefined;if(c!==undefined)v=c;if(v===undefined||v===ld||held.has(k))return;ld=v;i.value=v}},
 graph:(w,b)=>{b.innerHTML='<div class=big style="font-size:clamp(14px,10cqh,28px)"></div><div class=gw style="flex:1;min-height:0;position:relative;overflow:hidden"></div>';
  const big=b.querySelector('.big'),gw=b.querySelector('.gw');let pts=[];
  const draw=()=>{gw.innerHTML=graphSVG(pts,w,gw.clientWidth,gw.clientHeight)};new ResizeObserver(draw).observe(gw);
  return()=>{let h=(hist[w.name]||[]).slice(-(+w.points||50));
   if(!h.length)h=String(w.placeholder??'').split(',').map(q=>q.trim()).filter(Boolean).map(Number).filter(isFinite).map((v,i)=>[i*10,v]);
   pts=h;big.textContent=h.length?h[h.length-1][1]:'--';draw()}},
 gps:(w,b)=>{if(typeof L=='undefined'){b.innerHTML='<div class=big style="font-size:15px">Map library not loaded (internet needed)</div>';return()=>{}}
  b.className='bd map';b.innerHTML='<div class=mpw><div class=mp></div><div class=er>Error: invalid data</div></div><div class=gc></div>';
  const er=b.querySelector('.er'),gc=b.querySelector('.gc'),m=L.map(b.querySelector('.mp')).setView([20,0],2);
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'&copy; OpenStreetMap'}).addTo(m);const k=L.marker([0,0]),z=+w.zoom||15;let last;gc.textContent='No coordinate yet';
  new ResizeObserver(()=>m.invalidateSize()).observe(b);
  return v=>{v=v??w.placeholder;if(v==null||v===''){er.style.display='none';return}const p=geo(v);if(!p){er.style.display='flex';gc.textContent='Invalid data';return}
   er.style.display='none';gc.textContent=`${p[0].toFixed(5)}, ${p[1].toFixed(5)}`;if(String(p)!==last){last=String(p);k.setLatLng(p).addTo(m);m.setView(p,z)}}}
};
function build(){const g=$('grid');$('ttl').textContent=design.title||'';g.innerHTML='';items=[];held.clear();const ws=design.widgets||[];
 if(!ws.length){g.style.width=g.style.height='';g.innerHTML=`<div class=hint><b>${esc(msg||'No default dashboard given.')}</b></div>`;return}
 g.style.width=(design.width||1200)+'px';let bot=0;
 ws.forEach((w,i)=>{const y=w.y??20+i*120,hh=w.h||100;bot=Math.max(bot,y+hh);const c=document.createElement('div');c.className='card';
  c.style.cssText=`left:${w.x??20}px;top:${y}px;width:${w.w||260}px;height:${hh}px`;c.innerHTML=(w.type=='button'&&w.labelMode=='inside'?'':`<h4>${esc(w.label||w.name)}</h4>`)+'<div class=bd></div>';g.appendChild(c);
  const fn=(mk[w.type]||(()=>()=>{}))(w,c.lastChild);items.push([w,fn,c,NOSIG]);fn(undefined)});
 g.style.height=bot+40+'px'}
async function loadDesign(m,body){const r=await fetch('/api/design',{method:m,body}),j=await r.json();if(!r.ok){alert(j.error);return}design=j.design||{widgets:[]};msg=j.message||'';build();paint()}
async function resetDesign(){await loadDesign('DELETE')}
$('up').onchange=async e=>{const f=e.target.files[0];if(f)await loadDesign('POST',await f.text());e.target.value=''};
const ago=n=>n<60?Math.round(n)+'s':Math.floor(n/60)+'m '+Math.round(n%60)+'s';
function remount(it,m){const o=it[2].querySelector(':scope>.bd'),n=document.createElement('div');n.className='bd';o.replaceWith(n);it[1]=(mk[m.type]||(()=>()=>{}))(m,n)}
function paint(){const d=devs.find(x=>x.id==cur);
 items.forEach(it=>{const w=it[0],c=it[2],o=(d&&d.widgets&&d.widgets[w.name])||{};
  c.style.display=o.visible===false?'none':'';
  if(RE.includes(w.type)){const sg=JSON.stringify([o.color,o.max,o.limit,o.label]);if(sg!==it[3]){it[3]=sg;const m={...w};['color','max','limit','label'].forEach(k=>{if(o[k]!==undefined)m[k]=o[k]});remount(it,m)}}
  const h=c.querySelector('h4');if(h)h.textContent=o.label!==undefined?o.label:(w.label||w.name);
  if(!held.size)it[1](o.value!==undefined?o.value:(d?d.data[w.name]:undefined),d)});
 $('stl').innerHTML=d?`<span class=dot style="background:${d.online?'var(--ok)':'var(--al)'}"></span><b>${esc(d.name)}</b> <small style="color:var(--mut)">ID ${esc(d.id)}</small> is ${d.online?'online':'offline'}`:'<span class=dot></span>No device connected, showing placeholders';
 $('stt').textContent=d?`Last post request ${new Date(d.last*1000).toLocaleTimeString()} (${ago(d.age)} ago)`:''}
function side(){$('dl').innerHTML=devs.length?devs.map(d=>`<div class="dv ${d.id==cur?'s':''}" data-id="${esc(d.id)}"><span class="dot" style="background:${d.online?'var(--ok)':'var(--al)'}"></span>${esc(d.name)}<small>ID ${esc(d.id)}, ${d.online?'online':'offline'}, ${ago(d.age)} ago</small></div>`).join(''):'<small>Waiting for a device to POST to /api/data</small>';
 $('dl').querySelectorAll('.dv').forEach(e=>e.onclick=()=>{if(cur==e.dataset.id)return;cur=e.dataset.id;build();side();paint()})}
async function poll(){try{devs=await (await fetch('/api/devices')).json();if(!cur&&devs.length)cur=devs[0].id;const gs=(design.widgets||[]).filter(w=>w.type=='graph');
 if(cur&&gs.length)hist=await (await fetch(`/api/history/${encodeURIComponent(cur)}?keys=${gs.map(w=>encodeURIComponent(w.name)).join(',')}&n=${Math.max(...gs.map(w=>+w.points||50))}`)).json();else hist={};
 side();paint()}catch(e){}setTimeout(poll,cfg.poll_interval_ms||1000)}
function showLast(){const d=devs.find(x=>x.id==cur);$('mt').textContent='Last data post'+(d?' from '+d.name+' (ID '+d.id+')':'');$('ms').textContent=d?new Date(d.last*1000).toLocaleString():'';
 let r=d?d.raw:'No data has been posted yet. Devices send JSON to POST /api/data.';if(d)try{r=JSON.stringify(JSON.parse(d.raw),null,2)}catch(e){}$('mr').textContent=r;$('bd').classList.add('show')}
const closeM=()=>$('bd').classList.remove('show');
let lt;const closeL=()=>{clearInterval(lt);$('lb').classList.remove('show')};
async function loadLogic(){if(!cur){$('ls').textContent='Select a device first, variables are kept per device.';$('lv').textContent=$('ll').textContent='';return}
 const j=await (await fetch('/api/logic/'+encodeURIComponent(cur))).json(),t=x=>new Date(x*1000).toLocaleTimeString();
 $('ls').textContent='Device '+cur;
 $('lv').textContent=j.vars.length?j.vars.map(v=>`${v.name} (${v.scope=='local'?'website only':'shared'}) = ${JSON.stringify(v.value)}`).join('\n'):'No variables in this design.';
 $('ll').textContent=j.log.length?j.log.slice().reverse().map(e=>`${t(e.t)}  ${e.src}  ${e.level}: ${e.msg}`).join('\n'):'No script activity yet.'}
async function showLogic(){$('lb').classList.add('show');await loadLogic();clearInterval(lt);lt=setInterval(loadLogic,1000)}
addEventListener('keydown',e=>{if(e.key=='Escape'){closeM();closeL()}});
(async()=>{cfg=await (await fetch('/api/config')).json();await loadDesign('GET');poll()})();
</script></html>"""


@app.route("/")
def index():
    return PAGE


if __name__ == "__main__":
    app.run(host=CFG["host"], port=int(CFG["port"]), debug=False)
