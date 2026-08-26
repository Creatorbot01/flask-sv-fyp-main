from flask import Flask, request, jsonify, render_template_string, redirect
import requests
import time

app = Flask(__name__)

# ══════════════════════════════════════════════════════════════
#  MULTI-DEVICE STATE
#  Each ESP32 sends its own DEVICE_ID (e.g. "0001") on every call.
#  We keep one state dict per device instead of one global dict.
# ══════════════════════════════════════════════════════════════
DEFAULT_LATEST_DATA = {
    "speed_gps": 0,
    "speed_mpu": 0,
    "lat": "0",
    "lon": "0",
    "time": "NA",
    "roll": "0",
    "pitch": "0",
    "yaw": "0"
}

DEFAULT_SPEED_LIMIT = 25.0  # default for a bicycle
FALL_ROLL_THRESHOLD = 60.0   # degrees
FALL_PITCH_THRESHOLD = 60.0  # degrees
ALERT_COOLDOWN = 15  # seconds, gates how often Discord gets pinged

# A device counts as "SerialData Error" on the dashboard once it hasn't
# posted fresh data for this long. The ESP32 only calls /filldata when it
# has just parsed a good line from the Arduino, so staleness here already
# means either the Arduino serial link or the WiFi link is down.
DEVICE_TIMEOUT = 15  # seconds

# How long the "warning" status stays lit on the dashboard after being
# triggered (speed breach, fall/tip-over, or emergency button). This is
# separate from ALERT_COOLDOWN, which only throttles Discord pings.
WARNING_DISPLAY_DURATION = 10  # seconds

devices = {}
# devices["0001"] = {
#     "latest_data": {...},
#     "speed_limit": 25.0,
#     "last_speed_alert_time": 0,
#     "last_fall_alert_time": 0,
#     "return_home_active": False,
#     "last_seen": 0,          # epoch time of last /filldata POST
#     "last_warning_time": 0,  # epoch time the warning state was last (re)triggered
#     "warning_message": "",   # human readable reason for the current/last warning
# }

DISCORD_WEBHOOK_URL = "https://discordapp.com/api/webhooks/1523269941300826112/KBim0FO8JCk509-rz8ji499I4oFAbJmAN66FcSpGDsfaH7LyT2M6N9Bmlk1_3BrzJlma"

# Discord embed side colors (decimal, not hex string)
COLOR_WARNING = 0xFACC15   # yellow - speed breach
COLOR_DANGER = 0xEF4444    # red - fall/tip-over, emergency


def send_discord_embed(title, description, color=COLOR_WARNING, fields=None, mention_everyone=True):
    """Send a rich embed to the Discord webhook. Used for anything that should
    ping the channel loudly (speed breach, fall/tip-over, emergency button)."""
    embed = {
        "title": title,
        "description": description,
        "color": color,
    }
    if fields:
        embed["fields"] = fields

    payload = {
        "content": "@everyone" if mention_everyone else "",
        "embeds": [embed],
    }
    try:
        requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=5)
    except Exception as e:
        print("Discord webhook failed:", e)


def get_device(device_id):
    """Return the state dict for a device, creating it with defaults if new."""
    if device_id not in devices:
        devices[device_id] = {
            "latest_data": dict(DEFAULT_LATEST_DATA),
            "speed_limit": DEFAULT_SPEED_LIMIT,
            "last_speed_alert_time": 0,
            "last_fall_alert_time": 0,
            "return_home_active": False,
            "last_seen": 0,
            "last_warning_time": 0,
            "warning_message": "",
        }
    return devices[device_id]


def trigger_warning(dev, message):
    """Mark a device as currently in a warning state (shown on the dashboard),
    independent of whether a Discord alert actually fires (that's cooldown-gated)."""
    dev["last_warning_time"] = time.time()
    dev["warning_message"] = message


# ── Root just sends browsers to the dashboard ──
@app.route("/", methods=["GET"])
def root():
    return redirect("/main")


# ── ESP32 sends its sensor/status data here ──
@app.route("/filldata", methods=["POST"])
def fill_data():
    payload = request.get_json()
    if not payload:
        return jsonify({"status": "no payload"}), 400

    device_id = str(payload.get("device_id", "UNKNOWN"))
    dev = get_device(device_id)
    dev["latest_data"].update({k: v for k, v in payload.items() if k != "device_id"})
    dev["last_seen"] = time.time()
    print(f"[RECEIVED {device_id}]", dev["latest_data"])

    now = time.time()
    latest_data = dev["latest_data"]

    # ── Speed limit check ──
    try:
        speed_gps = float(latest_data["speed_gps"])
    except (ValueError, TypeError):
        speed_gps = 0

    if speed_gps >= dev["speed_limit"]:
        trigger_warning(dev, f"Speed limit exceeded: {speed_gps} km/h (limit {dev['speed_limit']} km/h)")
        if now - dev["last_speed_alert_time"] >= ALERT_COOLDOWN:
            dev["last_speed_alert_time"] = now
            send_discord_embed(
                title=f"⚠️ Speed Limit Exceeded — {device_id}",
                description="Rider is currently over the configured speed limit.",
                color=COLOR_WARNING,
                fields=[
                    {"name": "Speed (GPS)", "value": f"{speed_gps} km/h", "inline": True},
                    {"name": "Limit", "value": f"{dev['speed_limit']} km/h", "inline": True},
                    {"name": "Location", "value": f"{latest_data['lat']}, {latest_data['lon']}", "inline": False},
                ],
            )

    # ── Fall / tip-over check ──
    try:
        roll = float(latest_data["roll"])
        pitch = float(latest_data["pitch"])
    except (ValueError, TypeError):
        roll, pitch = 0, 0

    if abs(roll) >= FALL_ROLL_THRESHOLD or abs(pitch) >= FALL_PITCH_THRESHOLD:
        trigger_warning(dev, f"Possible fall/tip-over: Roll {roll}°, Pitch {pitch}°")
        if now - dev["last_fall_alert_time"] >= ALERT_COOLDOWN:
            dev["last_fall_alert_time"] = now
            send_discord_embed(
                title=f"🚨 Possible Fall/Tip-over — {device_id}",
                description="Orientation sensor crossed the fall threshold.",
                color=COLOR_DANGER,
                fields=[
                    {"name": "Roll", "value": f"{roll}°", "inline": True},
                    {"name": "Pitch", "value": f"{pitch}°", "inline": True},
                    {"name": "Location", "value": f"{latest_data['lat']}, {latest_data['lon']}", "inline": False},
                    {"name": "Time", "value": str(latest_data["time"]), "inline": False},
                ],
            )

    return jsonify({"status": "ok"})


# ── ESP32 posts here when the emergency button is pressed ──
@app.route("/emergency", methods=["POST"])
def emergency():
    payload = request.get_json() or {}
    device_id = str(payload.get("device_id", "UNKNOWN"))
    dev = get_device(device_id)
    lat = payload.get("lat", dev["latest_data"].get("lat", "0"))
    lon = payload.get("lon", dev["latest_data"].get("lon", "0"))
    t = payload.get("time", dev["latest_data"].get("time", "NA"))

    trigger_warning(dev, f"EMERGENCY button pressed at {lat},{lon}")
    send_discord_embed(
        title=f"🆘 EMERGENCY — {device_id}",
        description="Emergency button was pressed on the device.",
        color=COLOR_DANGER,
        fields=[
            {"name": "Location", "value": f"{lat}, {lon}", "inline": False},
            {"name": "Time", "value": str(t), "inline": False},
        ],
    )
    return jsonify({"status": "ok"})


# ── ESP32 polls this for its current speed limit and any pending return-home alert ──
@app.route("/getdata", methods=["GET"])
def get_data():
    device_id = str(request.args.get("device_id", "UNKNOWN"))
    dev = get_device(device_id)
    return jsonify({
        "limit": dev["speed_limit"],
        "return_home": dev["return_home_active"],
    })


# ── ESP32 calls this once the rider acknowledges the return-home prompt ──
@app.route("/ack_return_home", methods=["POST"])
def ack_return_home():
    payload = request.get_json() or {}
    device_id = str(payload.get("device_id", "UNKNOWN"))
    dev = get_device(device_id)
    dev["return_home_active"] = False
    return jsonify({"status": "ok"})


# ── Parent clicks this on the dashboard to ask a specific rider to head home ──
@app.route("/trigger_return_home", methods=["POST"])
def trigger_return_home():
    device_id = str(request.form.get("device_id") or (request.get_json(silent=True) or {}).get("device_id", "UNKNOWN"))
    dev = get_device(device_id)
    dev["return_home_active"] = True
    return jsonify({"status": "ok"})


# ── Dashboard sets a new limit for one device ──
@app.route("/set_limit", methods=["POST"])
def set_limit():
    device_id = str(request.form.get("device_id", "UNKNOWN"))
    new_limit = request.form.get("limit")
    dev = get_device(device_id)
    if new_limit:
        dev["speed_limit"] = float(new_limit)
    return jsonify({"status": "ok", "limit": dev["speed_limit"]})


# ── Browser: raw JSON dump of every device's full state ──
@app.route("/apigetdata", methods=["GET"])
def api_get_data():
    now = time.time()
    out = {}
    for device_id, dev in devices.items():
        seconds_since_seen = now - dev["last_seen"] if dev["last_seen"] else None
        online = dev["last_seen"] != 0 and seconds_since_seen <= DEVICE_TIMEOUT

        # Status precedence: offline beats warning beats ok.
        if not online:
            status = "offline"
        elif dev["last_warning_time"] and (now - dev["last_warning_time"]) <= WARNING_DISPLAY_DURATION:
            status = "warning"
        else:
            status = "ok"

        out[device_id] = {
            "data": dev["latest_data"],
            "limit": dev["speed_limit"],
            "return_home": dev["return_home_active"],
            "online": online,
            "seconds_since_seen": seconds_since_seen,
            "status": status,
            "warning_message": dev["warning_message"] if status == "warning" else "",
            "last_seen": dev["last_seen"],
            "last_warning_time": dev["last_warning_time"],
        }
    return jsonify({"devices": out})


# ── Dashboard page ──
@app.route("/main", methods=["GET"])
def dashboard():
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Bicycle Dashboard</title>
        <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
        <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
        <style>
            body {
                font-family: sans-serif;
                color: #0f0;
                font-size: 18px;
                padding: 20px;
                margin: 0;
                min-height: 100vh;
                background:
                    radial-gradient(circle at 10% 10%, rgba(217,70,239,.35), transparent 30%),
                    radial-gradient(circle at 90% 20%, rgba(34,211,238,.22), transparent 25%),
                    radial-gradient(circle at 50% 90%, rgba(109,40,217,.45), transparent 32%),
                    linear-gradient(145deg, #120321, #260346, #41086f, #17052f);
            }

            /* TECH BACKGROUND */
            .tech-grid {
                position: fixed;
                inset: 0;
                pointer-events: none;
                opacity: .22;
                background-image:
                    linear-gradient(rgba(255,255,255,.10) 1px, transparent 1px),
                    linear-gradient(90deg, rgba(255,255,255,.10) 1px, transparent 1px);
                background-size: 35px 35px;
                mask-image: linear-gradient(to bottom, black, transparent);
                z-index: 0;
            }
            .tech-line {
                position: fixed;
                height: 2px;
                width: 150px;
                background: linear-gradient(90deg, transparent, #d946ef, transparent);
                animation: techMove 7s linear infinite;
                opacity: .5;
                z-index: 0;
            }
            .line1 { top: 18%; left: -170px; }
            .line2 { top: 62%; left: -220px; animation-delay: 2.5s; }
            @keyframes techMove {
                from { transform: translateX(0); }
                to { transform: translateX(calc(100vw + 350px)); }
            }

            input, button { font-size: 16px; padding: 5px; }
            .label { color: #aaa; }
            .return-btn { background: #522; color: #fff; border: 1px solid #f66; margin-top: 8px; }
            .return-btn.active { background: #f66; color: #111; }
            #devices { display: flex; flex-wrap: wrap; gap: 15px; margin-top: 15px; position: relative; z-index: 1; }
            h2 { position: relative; z-index: 1; }
            .device-box {
                border: 2px solid #0f0; border-radius: 8px; padding: 12px;
                width: 300px; background: rgba(24,24,24,.85);
            }
            .device-box.offline { border-color: #f66; color: #f88; }
            .device-box.warning { border-color: #facc15; color: #ffe066; }
            .device-box h3 { margin: 0 0 8px 0; color: #fff; }
            .device-map { height: 160px; width: 100%; margin-top: 8px; border: 1px solid #0f0; border-radius: 4px; background: #222; }
            .device-box.offline .device-map { border-color: #f66; }
            .device-box.warning .device-map { border-color: #facc15; }
            .status-ok { color: #0f0; }
            .status-error { color: #f66; font-weight: bold; }
            .status-warning { color: #facc15; font-weight: bold; }
            .no-devices { color: #888; position: relative; z-index: 1; }
        </style>
    </head>
    <body>
        <div class="tech-grid"></div>
        <div class="tech-line line1"></div>
        <div class="tech-line line2"></div>

        <h2>Bicycle Dashboard</h2>
        <div id="devices"><p class="no-devices">Waiting for devices to check in...</p></div>

        <script>
            var maps = {}; // device_id -> { map, marker, firstFix }

            function setLimit(deviceId) {
                var input = document.getElementById('limit_input_' + deviceId);
                var val = input.value;
                if (!val) return;
                var body = new URLSearchParams();
                body.append('device_id', deviceId);
                body.append('limit', val);
                fetch('/set_limit', { method: 'POST', body: body }).then(refreshData);
                input.value = '';
            }

            function callRiderHome(deviceId) {
                var body = new URLSearchParams();
                body.append('device_id', deviceId);
                fetch('/trigger_return_home', { method: 'POST', body: body }).then(refreshData);
            }

            function renderDeviceBox(deviceId, info) {
                var box = document.getElementById('box-' + deviceId);
                if (!box) {
                    box = document.createElement('div');
                    box.id = 'box-' + deviceId;
                    box.className = 'device-box';
                    // Everything that changes on every 2s refresh lives in
                    // #status-<id>. The limit input/button and the return-home
                    // button are built ONCE here and never touched by innerHTML
                    // again -- only their text/value/class get updated below.
                    // Rebuilding an <input> via innerHTML on every refresh was
                    // wiping out whatever the user was mid-typing (and stealing
                    // focus), which is why the field looked like it kept
                    // "refreshing" while entering a new limit.
                    box.innerHTML =
                        '<h3>Device ' + deviceId + '</h3>' +
                        '<div id="status-' + deviceId + '"></div>' +
                        '<p><span class="label">Limit:</span> <span id="limit_display_' + deviceId + '"></span> km/h</p>' +
                        '<input type="number" step="0.1" id="limit_input_' + deviceId + '" placeholder="New limit" style="width:80px;">' +
                        '<button onclick="setLimit(\'' + deviceId + '\')">Set</button>' +
                        '<br>' +
                        '<button id="return_btn_' + deviceId + '" class="return-btn" onclick="callRiderHome(\'' + deviceId + '\')">Call Rider Home</button>' +
                        '<div class="device-map" id="map-' + deviceId + '"></div>';
                    document.getElementById('devices').appendChild(box);

                    // Own small map per device, created once and never torn down.
                    var m = L.map('map-' + deviceId, { attributionControl: false }).setView([0, 0], 2);
                    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                        attribution: '&copy; OpenStreetMap contributors'
                    }).addTo(m);
                    maps[deviceId] = { map: m, marker: null, firstFix: false };
                    // Leaflet sometimes mis-sizes a map created inside a flex
                    // box before layout settles; nudge it once after render.
                    setTimeout(function () { m.invalidateSize(); }, 150);
                }

                var statusClass = info.status !== 'ok' ? ' ' + info.status : '';
                box.className = 'device-box' + statusClass;

                var d = info.data;
                var statusHtml;
                if (info.status === 'offline') {
                    statusHtml = '<span class="status-error">Device Error or Offline</span>';
                } else if (info.status === 'warning') {
                    statusHtml = '<span class="status-warning">⚠ WARNING: ' + info.warning_message + '</span>';
                } else {
                    statusHtml = '<span class="status-ok">OK</span>';
                }

                // Only this block gets rewritten every refresh -- no form
                // controls live inside it, so nothing the user is typing
                // anywhere else on the page is ever touched.
                document.getElementById('status-' + deviceId).innerHTML =
                    '<p><span class="label">Status:</span> ' + statusHtml + '</p>' +
                    '<p><span class="label">Speed (GPS):</span> ' + (info.online ? d.speed_gps : '--') + ' km/h</p>' +
                    '<p><span class="label">Position:</span> ' + (info.online ? (d.lat + ', ' + d.lon) : '--') + '</p>' +
                    '<p><span class="label">Time:</span> ' + (info.online ? d.time : '--') + '</p>' +
                    '<p><span class="label">Orientation:</span> R' + (info.online ? d.roll : '--') +
                        ' P' + (info.online ? d.pitch : '--') + ' Y' + (info.online ? d.yaw : '--') + '</p>';

                // Limit value display is just text -- update it directly,
                // never touch the input field's own value.
                document.getElementById('limit_display_' + deviceId).textContent = info.limit;

                // Update the existing return-home button in place (class +
                // label) instead of recreating it.
                var returnBtn = document.getElementById('return_btn_' + deviceId);
                if (info.return_home) {
                    returnBtn.className = 'return-btn active';
                    returnBtn.textContent = 'Return Home (ACTIVE)';
                } else {
                    returnBtn.className = 'return-btn';
                    returnBtn.textContent = 'Call Rider Home';
                }

                if (info.online) {
                    var lat = parseFloat(d.lat);
                    var lon = parseFloat(d.lon);
                    if (!isNaN(lat) && !isNaN(lon) && (lat !== 0 || lon !== 0)) {
                        var entry = maps[deviceId];
                        if (!entry.marker) {
                            entry.marker = L.marker([lat, lon]).addTo(entry.map).bindPopup(deviceId);
                        } else {
                            entry.marker.setLatLng([lat, lon]);
                        }
                        if (!entry.firstFix) {
                            entry.map.setView([lat, lon], 15);
                            entry.firstFix = true;
                        }
                    }
                }
            }

            function refreshData() {
                fetch('/apigetdata')
                    .then(response => response.json())
                    .then(json => {
                        var ids = Object.keys(json.devices);
                        var container = document.getElementById('devices');
                        var placeholder = container.querySelector('.no-devices');
                        if (ids.length > 0 && placeholder) placeholder.remove();
                        if (ids.length === 0 && !placeholder) {
                            container.innerHTML = '<p class="no-devices">Waiting for devices to check in...</p>';
                        }
                        ids.forEach(function (deviceId) {
                            renderDeviceBox(deviceId, json.devices[deviceId]);
                        });
                    })
                    .catch(err => console.error('Fetch error:', err));
            }

            refreshData();
            setInterval(refreshData, 2000);
        </script>
    </body>
    </html>
    """
    return render_template_string(html)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
