
import http.server
import socketserver
import os
import urllib.parse
import time
from datetime import datetime
import threading
import cv2
import sys
import json
import re
import calendar

# --- CONFIG ---
PORT = 8000
# --- CONFIG ---
PORT = 8000
from config.paths import ROOT, LOG_DIR, EMBED_DIR, BODY_EMB_DIR
LOGS_PATH = os.path.join(LOG_DIR, "system.log")

# --- GLOBAL VIDEO STATE ---
CAMERA_SYSTEM = None
LATEST_FRAME = None
LATEST_FRAMES_DICT = {} # Stores individual raw frames {0: frame, 1: frame}
FRAME_LOCK = threading.Lock()
IS_CAMERA_RUNNING = False

# HTML Template (Using Double Braces for CSS to avoid .format() errors)
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Indoor Tracking Dashboard</title>
    <style>
        :root {{ --bg-color: #121212; --card-bg: #1e1e1e; --text-color: #e0e0e0; --accent: #00ff00; --error: #ff4444; }}
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: var(--bg-color); color: var(--text-color); margin: 0; padding: 20px; }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        h1, h2, h3 {{ color: var(--accent); margin-top: 0; }}
        .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; margin-bottom: 30px; }}
        .card {{ background-color: var(--card-bg); padding: 20px; border-radius: 8px; border: 1px solid #333; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }}
        .card h3 {{ font-size: 0.9em; color: #888; text-transform: uppercase; letter-spacing: 1px; }}
        .card .value {{ font-size: 2.5em; font-weight: bold; margin: 10px 0; }}
        .status-ok {{ color: var(--accent); }}
        .status-idle {{ color: #ffa500; }}
        
        table {{ width: 100%; border-collapse: collapse; background: var(--card-bg); border-radius: 8px; overflow: hidden; }}
        th, td {{ padding: 12px 15px; text-align: left; border-bottom: 1px solid #333; }}
        th {{ background-color: #2d2d2d; color: var(--accent); }}
        tr:hover {{ background-color: #2d2d2d; }}
        
        .search-box {{ display: flex; gap: 10px; margin-bottom: 20px; }}
        input[type="text"] {{ flex: 1; padding: 12px; border-radius: 5px; border: 1px solid #333; background: #2d2d2d; color: white; }}
        button {{ padding: 12px 25px; background: #006400; color: white; border: none; border-radius: 5px; cursor: pointer; font-weight: bold; }}
        button:hover {{ background: var(--accent); color: black; }}
        
        pre {{ background: #000; padding: 15px; border-radius: 5px; overflow-x: auto; color: #0f0; border: 1px solid #333; max-height: 400px; overflow-y: scroll;}}
        
        .nav {{ margin-bottom: 20px; border-bottom: 1px solid #333; padding-bottom: 10px; }}
        .nav a {{ color: #888; text-decoration: none; margin-right: 20px; font-weight: bold; font-size: 1.1em; }}
        .nav a.active {{ color: var(--accent); border-bottom: 2px solid var(--accent); padding-bottom: 10px; }}
        
        .video-container {{ text-align: center; margin-bottom: 20px; background: #000; border: 2px solid var(--accent); border-radius: 8px; overflow: hidden; }}
        .video-container img {{ max-width: 100%; height: auto; }}
        .btn-cam {{ background: #333; margin-left: 10px; }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div style="display:flex; align-items:center; justify-content:space-between;">
                <h1> Camera Tracking Dashboard</h1>
                <span style="color: #666;">v1.1 (Live Stream)</span>
            </div>
            <div class="nav">
                <a href="/" class="{ACTIVE_HOME}">Dashboard & Camera</a>
                <a href="/users" class="{ACTIVE_USERS}">User Database</a>
                <a href="/logs" class="{ACTIVE_LOGS}">Logs & Search</a>
                <a href="/summary" class="{ACTIVE_SUMMARY}">Data Rekap</a>
            </div>
        </header>

        {CONTENT}

        <footer style="margin-top: 50px; text-align: center; color: #555; font-size: 0.8em;">
            <p>Running on Python builtin http.server (Threading) | Port {PORT}</p>
        </footer>
    </div>
</body>
</html>
"""

def video_frame_callback(frame, raw_frames=None):
    global LATEST_FRAME, LATEST_FRAMES_DICT
    
    # 1. Update Global Grid
    success, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 60])
    if success:
        data = buffer.tobytes()
        with FRAME_LOCK:
            LATEST_FRAME = data
            
            # 2. Update Individual Frames (for user specific view)
            if raw_frames:
                for i, rf in enumerate(raw_frames):
                     # Encode lightly
                     s, b = cv2.imencode('.jpg', rf, [int(cv2.IMWRITE_JPEG_QUALITY), 50])
                     if s:
                         LATEST_FRAMES_DICT[i] = b.tobytes()

def start_camera_system():
    global CAMERA_SYSTEM, IS_CAMERA_RUNNING
    if IS_CAMERA_RUNNING: return
    
    try:
        from indoor.video import VideoSystem
        from config.settings import SETTINGS
        
        target_cam_count = SETTINGS.get("max_cameras", 1)
        print(f"[DASHBOARD] Starting Video System in background with {target_cam_count} cameras...")
        
        CAMERA_SYSTEM = VideoSystem(max_cameras=target_cam_count)
        CAMERA_SYSTEM.on_frame_callback = video_frame_callback
        
        # Run in a separate thread because VideoSystem.run() is blocking
        t = threading.Thread(target=CAMERA_SYSTEM.run, daemon=True)
        t.start()
        IS_CAMERA_RUNNING = True
    except Exception as e:
        print(f"[DASHBOARD] Failed to start camera: {e}")

def stop_camera_system():
    global CAMERA_SYSTEM, IS_CAMERA_RUNNING
    if not IS_CAMERA_RUNNING or CAMERA_SYSTEM is None: return
    
    print("[DASHBOARD] Stopping Video System...")
    CAMERA_SYSTEM.running = False # Signal thread to stop
    IS_CAMERA_RUNNING = False
    CAMERA_SYSTEM = None

class StreamingHandler(http.server.BaseHTTPRequestHandler):
    def get_stats(self):
        user_count = 0
        if os.path.exists(EMBED_DIR):
            user_count = len([f for f in os.listdir(EMBED_DIR) if f.endswith('.npy')])
        
        log_size = "0 KB"
        status = "STOPPED"
        status_class = "status-idle"
        
        if IS_CAMERA_RUNNING:
            status = "LIVE MONITORING"
            status_class = "status-ok"
        elif os.path.exists(LOGS_PATH):
            mtime = os.path.getmtime(LOGS_PATH)
            if time.time() - mtime < 20:
                status = "ACTIVE (LOGS)"
                status_class = "status-ok"
            
        return user_count, status, status_class

    def parse_attendance_logs(self, name):
        """
        Parse system.log -> Aggregate per Date.
        Returns:
            daily_summary (list): [{date, first_in, total_duration_str, rooms, is_present}]
            history (list): Raw granular history (unused now but kept for logic if needed)
            first_seen_today: ...
            total_duration_today: ...
        """
        daily_stats = {} # {date: {first_in, total_sec, rooms: set()}}
        history = []
        first_seen_today = "-"
        total_seconds_today = 0
        today_str = datetime.now().strftime('%Y-%m-%d')

        if not os.path.exists(LOGS_PATH):
            return [], [], first_seen_today, "-", {}

        ptrn_new = re.compile(r"\[(\d{4}-\d{2}-\d{2})\] \d+\. .*? \| .*? \| (\d{2}:\d{2}:\d{2}) → (\d{2}:\d{2}:\d{2}) \| (.*?) \| (.*)")
        ptrn_old = re.compile(r"\d+\. .*? \| .*? \| (\d{2}:\d{2}:\d{2}) → (\d{2}:\d{2}:\d{2}) \| (.*?) \| (.*)")

        try:
            with open(LOGS_PATH, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
            
            for line in lines:
                if name not in line: continue
                
                date_val = today_str 
                in_t, out_t, room, st = "", "", "", ""
                
                match_new = ptrn_new.search(line)
                if match_new:
                    date_val, in_t, out_t, room, st = match_new.groups()
                else:
                    match_old = ptrn_old.search(line)
                    if match_old:
                        in_t, out_t, room, st = match_old.groups()
                    else:
                        continue 

                # Calc Duration
                fmt = "%H:%M:%S"
                t1 = datetime.strptime(in_t, fmt)
                t2 = datetime.strptime(out_t, fmt)
                dur = (t2 - t1).total_seconds()
                
                # Format Duration Entry
                m_e, s_e = divmod(int(dur), 60)
                h_e, m_e = divmod(m_e, 60)
                entry_dur = f"{h_e:02d}:{m_e:02d}:{s_e:02d}"

                # Append to History (Detailed Logs)
                history.append({
                    "date": date_val,
                    "in": in_t,
                    "out": out_t,
                    "room": room.strip(),
                    "status": st.strip(),
                    "duration": entry_dur
                })
                
                # --- AGGREGATION LOGIC ---
                if date_val not in daily_stats:
                    daily_stats[date_val] = {
                        "first_in": in_t,
                        "total_sec": 0,
                        "rooms": set()
                    }
                
                # Update First In (find earliest)
                if in_t < daily_stats[date_val]["first_in"]:
                    daily_stats[date_val]["first_in"] = in_t
                
                daily_stats[date_val]["total_sec"] += dur
                daily_stats[date_val]["rooms"].add(room.strip())
                
                # Today Stats
                if date_val == today_str:
                    total_seconds_today += dur

        except Exception as e:
            print(f"Error parsing logs: {e}")

        # --- MERGE LIVE ACTIVE SESSION (FROM RAM) ---
        # This ensures real-time checkmark even if not written to file yet
        try:
            from indoor.presence_manager import presence_manager
            if presence_manager and name in presence_manager.state:
                 for r_name, st in presence_manager.state[name].items():
                     if st['status'] == 'INDOOR':
                         # Create temporary log entry
                         live_in = st['in_time']
                         live_now = time.time()
                         live_dur = (live_now - live_in)
                         
                         # Format
                         m_l, s_l = divmod(int(live_dur), 60)
                         h_l, m_l = divmod(m_l, 60)
                         live_dur_str = f"{h_l:02d}:{m_l:02d}:{s_l:02d}"
                         
                         live_in_str = datetime.fromtimestamp(live_in).strftime('%H:%M:%S')
                         today_live = datetime.fromtimestamp(live_in).strftime('%Y-%m-%d')
                         
                         # Add to History
                         history.append({
                            "date": today_live,
                            "in": live_in_str,
                            "out": "ACTIVE",
                            "room": r_name,
                            "status": "INDOOR",
                            "duration": live_dur_str
                         })
                         
                         # Add to Aggregation
                         if today_live not in daily_stats:
                            daily_stats[today_live] = { "first_in": live_in_str, "total_sec": 0, "rooms": set() }
                         
                         if live_in_str < daily_stats[today_live]["first_in"]:
                             daily_stats[today_live]["first_in"] = live_in_str
                         
                         daily_stats[today_live]["total_sec"] += live_dur
                         daily_stats[today_live]["rooms"].add(r_name)
                         
                         if today_live == today_str:
                             total_seconds_today += live_dur
        except ImportError:
            pass
            
        # Convert Dict to List & Format
        daily_summary = []
        for d, stat in daily_stats.items():
            m, s = divmod(int(stat["total_sec"]), 60)
            h, m = divmod(m, 60)
            dur_str = f"{h:02d}:{m:02d}:{s:02d}"
            
            daily_summary.append({
                "date": d,
                "first_in": stat["first_in"],
                "duration": dur_str,
                "rooms": ", ".join(list(stat["rooms"])[:1]), # Ambil 1 ruangan utama saja biar rapi
                "is_present": True
            })
            
        daily_summary.sort(key=lambda x: x['date'], reverse=True)

        if today_str in daily_stats:
            first_seen_today = daily_stats[today_str]["first_in"]
        
        m, s = divmod(int(total_seconds_today), 60)
        h, m = divmod(m, 60)
        total_duration_today_str = f"{h:02d}:{m:02d}:{s:02d}"
        
        return daily_summary, history, first_seen_today, total_duration_today_str, daily_stats

    def render_dashboard(self):
        user_count, status, status_class = self.get_stats()
        
        cam_action = "Start Camera"
        cam_url = "/start_cam"
        video_html = '<div style="padding:40px; color:#555;">Camera System is OFFLINE</div>'
        
        if IS_CAMERA_RUNNING:
            cam_action = "Stop Camera" 
            cam_url = "/stop_cam"
            # Use global feed
            video_html = '<img src="/video_feed" alt="Live Stream" />'
        
        html = f"""
        <div class="grid">
            <div class="card">
                <h3>👥 Registered Users</h3>
                <div class="value">{user_count}</div>
            </div>
            <div class="card">
                <h3>🔌 System Status</h3>
                <div class="value {status_class}">{status}</div>
            </div>
            <div class="card">
                <h3>🎮 Control</h3>
                <div style="margin-top:10px;">
                    <form action="{cam_url}" method="POST">
                        <button type="submit" style="background:{'#8b0000' if IS_CAMERA_RUNNING else '#006400'}">{cam_action}</button>
                    </form>
                </div>
            </div>
        </div>
        
        <h2> Realtime Surveillance</h2>
        <div class="video-container">
            {video_html}
        </div>
        """
        return HTML_TEMPLATE.format(CONTENT=html, ACTIVE_HOME="active", ACTIVE_USERS="", ACTIVE_LOGS="", ACTIVE_SUMMARY="", PORT=PORT)

    def render_user_detail(self, name):
        # Lazy import
        try:
            from indoor.presence_manager import presence_manager
        except ImportError:
            presence_manager = None

        # Parse Query Params for Month/Year
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        
        now = datetime.now()
        try:
            sel_month = int(params.get("month", [now.month])[0])
            sel_year = int(params.get("year", [now.year])[0])
        except:
            sel_month, sel_year = now.month, now.year
            
        # 1. Check if user exists
        mod_time = "-"
        has_body = False
        if os.path.exists(EMBED_DIR):
             # Try clean name first
             path = os.path.join(EMBED_DIR, f"{name}.npy")
             if os.path.exists(path):
                 mt = os.path.getmtime(path)
                 mod_time = datetime.fromtimestamp(mt).strftime('%Y-%m-%d %H:%M:%S')
             
             if os.path.exists(os.path.join(BODY_EMB_DIR, f"{name}.npy")):
                 has_body = True
        
        # If user not found, return error page
        if not os.path.exists(os.path.join(EMBED_DIR, f"{name}.npy")):
            return HTML_TEMPLATE.format(CONTENT=f"<h2>User {name} not found.</h2><a href='/users'>Back</a>", ACTIVE_HOME="", ACTIVE_USERS="active", ACTIVE_LOGS="", ACTIVE_SUMMARY="", PORT=PORT)

        # 2. Get Dynamic Data (Live Status)
        status = "⚫ OFFLINE"
        room = "-"
        duration_str = "-"
        last_seen_live = "-"
        is_active = False
        
        if IS_CAMERA_RUNNING and presence_manager:
            rooms = presence_manager.get_current_rooms(name)
            if rooms:
                status = "🟢 INDOOR"
                room = ", ".join(rooms)
                is_active = True
                if name in presence_manager.state:
                    for r_name, st in presence_manager.state[name].items():
                        if st['status'] == 'INDOOR':
                            delta = time.time() - st['in_time']
                            m, s = divmod(int(delta), 60)
                            h, m = divmod(m, 60)
                            duration_str = f"{h:02d}:{m:02d}:{s:02d}"
                            last_seen_live = datetime.fromtimestamp(st['last_seen']).strftime('%H:%M:%S')
                            break
            else:
                 if name in presence_manager.state:
                     st = list(presence_manager.state[name].values())[0] # Pick first room
                     s = st['status']
                     if s == 'OUTDOOR': status = "⚪ OUTDOOR"
                     elif s == 'PENDING': status = "🕒 VERIFYING..."
                     elif s == 'UNKNOWN': status = "❓ CHECKING..."
                     else: status = s
                     
                     if 'last_seen' in st:
                         last_seen_live = datetime.fromtimestamp(st['last_seen']).strftime('%H:%M:%S')
                     
                     if "INDOOR" in status or "VERIFYING" in status:
                         is_active = True

        # 3. Get Logs & Prepare Data
        # history contains ALL raw logs. daily_summary contains per-day aggregation.
        daily_summary, history, first_seen_today, total_duration_today, daily_stats = self.parse_attendance_logs(name)
        
        # Filter Presence Map by Selected Month
        # But wait, presence_map needs to cover ALL data to populate the grid correctly?
        # Actually we construct the grid for 'sel_month', so we just need lookup.
        presence_map = {d['date']: True for d in daily_summary}
        
        # Prepare Detail Data (Group by Date) -> JSON for Frontend
        detail_map = {}
        for h in history:
            d = h['date']
            if d not in detail_map: detail_map[d] = []
            detail_map[d].append({
                "in": h['in'],
                "out": h['out'],
                "dur": h['duration'],
                "room": h['room'],
                "st": h['status']
            })
        
        daily_details_json = json.dumps(detail_map)
        
        # GENERATE HISTORY TABLE ROWS
        history_rows = ""
        sorted_dates = sorted(daily_stats.keys(), reverse=True) # Newest first
        has_data = False
        
        for d_str in sorted_dates:
             try:
                 d_obj = datetime.strptime(d_str, "%Y-%m-%d")
                 # Filter by Month/Year
                 if d_obj.month == sel_month and d_obj.year == sel_year:
                     has_data = True
                     # Format Duration
                     sec = daily_stats[d_str]['total_sec']
                     m, s = divmod(int(sec), 60)
                     h, m = divmod(m, 60)
                     dur_fmt = f"{h:02d} jam {m:02d} menit {s:02d} detik"
                     
                     history_rows += f"""
                     <tr id="row-{d_str}" style="border-bottom:1px solid #333; transition:0.2s;">
                        <td style="padding:12px 10px; color:#ddd;">{d_str}</td>
                        <td style="padding:12px 10px; color:#0f0; font-weight:bold; text-align:right;">{dur_fmt}</td>
                     </tr>
                     """
             except: continue
             
        if not has_data:
            history_rows = "<tr><td colspan='2' style='padding:20px; text-align:center; color:#555;'>Tidak ada data untuk bulan ini</td></tr>"

        # Build Calendar Grid
        month_name = calendar.month_name[sel_month]
        _, days_in_month = calendar.monthrange(sel_year, sel_month)
        
        calendar_cells = ""
        
        # Get the weekday of the first day of the month (0=Monday, 6=Sunday)
        first_day_weekday = calendar.weekday(sel_year, sel_month, 1)
        
        # Add empty cells for days before the 1st of the month
        for _ in range(first_day_weekday):
            calendar_cells += '<div style="background:#1a1a1a;"></div>' # Empty cell

        for day in range(1, days_in_month + 1):
            date_str = f"{sel_year}-{sel_month:02d}-{day:02d}"
            is_present = presence_map.get(date_str, False)
            
            # Check if future
            is_future = False
            try:
                curr_date = datetime.strptime(date_str, "%Y-%m-%d")
                if curr_date > datetime.now(): is_future = True
            except: pass

            if is_present:
                safe_name = urllib.parse.quote(name)
                img_url = f"/snapshots/{safe_name}/{date_str}.jpg"
                cell_content = f"""
                <div style="display:flex; justify-content:flex-end; gap:5px; margin-top:auto;">
                    <div onclick="showSnapshot('{img_url}', '{date_str}')" style="cursor:pointer; opacity:0.8; transition:0.2s;" onmouseover="this.style.opacity=1" onmouseout="this.style.opacity=0.8" title="Lihat Foto">
                        ✅
                    </div>
                    <div onclick="showDetails('{date_str}')" style="cursor:pointer; opacity:0.8; transition:0.2s;" onmouseover="this.style.opacity=1" onmouseout="this.style.opacity=0.8" title="Lihat Log Detail">
                        📄
                    </div>
                </div>
                """
            else:
                cell_content = "" # Cleaner empty cells
            
            # Highlight Today
            bg_style = "background:#222;"
            date_style = "color:#555;"
            border_style = ""
            
            if date_str == datetime.now().strftime("%Y-%m-%d"):
                bg_style = "background:#2a2a2a;"
                date_style = "color:#fff; font-weight:bold;"
                border_style = "border:1px solid #444;"
            
            calendar_cells += f"""
            <div style="{bg_style} {border_style} border-radius:8px; padding:8px; min-height:85px; display:flex; flex-direction:column;">
                <div style="font-size:0.8em; {date_style} text-align:right; margin-bottom:5px;">{day}</div>
                {cell_content}
            </div>
            """
            
        # Month Selector Options
        month_opts = ""
        for m in range(1, 13):
            sel = "selected" if m == sel_month else ""
            month_opts += f'<option value="{m}" {sel}>{calendar.month_name[m]}</option>'

        attendance_section = f"""
        <div style="background:#1e1e1e; padding:15px; border-radius:10px; margin-top:20px;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:15px;">
                <h4 style="margin:0;">📅 Kalender Absensi</h4>
                <form method="GET" style="display:flex; gap:10px;">
                    <input type="hidden" name="name" value="{name}">
                    <select name="month" onchange="this.form.submit()" style="background:#333; color:#fff; border:none; padding:5px; border-radius:4px;">
                        {month_opts}
                    </select>
                    <input type="number" name="year" value="{sel_year}" onchange="this.form.submit()" style="background:#333; color:#fff; border:none; padding:5px; border-radius:4px; width:60px;">
                </form>
            </div>
            
            <div style="display:grid; grid-template-columns: repeat(7, 1fr); gap:5px; text-align:center; font-size:0.8em; font-weight:bold; color:#aaa; margin-bottom:5px;">
                <div>SEN</div><div>SEL</div><div>RAB</div><div>KAM</div><div>JUM</div><div>SAB</div><div>MIN</div>
            </div>
            
            <div style="display:grid; grid-template-columns: repeat(7, 1fr); gap:5px;">
                {calendar_cells}
            </div>
        </div>
        """

        # 4. Build Layout
        
        # Initial Video State
        video_display_style = "display:block;" if is_active else "display:none;"
        placeholder_style = "display:none;" if is_active else "display:flex;"
        
        # Use user-specific feed
        safe_name = urllib.parse.quote(name)
        img_src = f"/user_feed?name={safe_name}"
        
        # Fallback to global video_feed if user is active but we fallback for some reason, 
        # (Logic handled in backend /user_feed handler actually, so we trust it)
        
        video_block = f"""
        <div id="video-wrapper" style="{video_display_style} background:#000; border:2px solid #0f0; border-radius:10px; overflow:hidden; box-shadow: 0 0 20px rgba(0,255,0,0.2);">
            <div style="background:#006400; padding:10px 15px; font-weight:bold; font-size:1.1em; display:flex; justify-content:space-between;">
                <span>📹 LIVE FEED</span>
                <span style="color:#fff;">LOKASI: <span id="loc-display">{room}</span></span>
            </div>
            <img src="{img_src}" style="width:100%; display:block;" alt="Live Camera Feed">
        </div>
        """

        placeholder_block = f"""
        <div id="placeholder-wrapper" style="{placeholder_style} background:#1e1e1e; border:1px solid #333; height:300px; flex-direction:column; align-items:center; justify-content:center; border-radius:10px; color:#555;">
            <h1 style="font-size:3em; margin:0;">👁️‍🗨️</h1>
            <p style="font-size:1.2em; margin-top:10px;">Target Tidak Terlihat</p>
            <p style="font-size:0.8em;">Kamera sedang aktif namun <strong>{name}</strong> tidak terdeteksi.</p>
        </div>
        """
        
        if not IS_CAMERA_RUNNING:
             video_block = ""
             placeholder_block = """
            <div style="background:#111; border:1px solid #333; height:300px; display:flex; align-items:center; justify-content:center; border-radius:10px;">
                <div style="text-align:center;">
                    <h1 style="font-size:3em;">🚫</h1>
                    <p style="color:#888;">Sistem Offline</p>
                    <form action="/start_cam" method="POST"><button>Start Camera</button></form>
                </div>
            </div>
            """

        html = f"""
        <div style="margin-bottom:20px;">
            <a href="/users" style="text-decoration:none; color:#888;">&larr; Kembali ke Database</a>
        </div>

        <div class="grid" style="grid-template-columns: 2fr 1.2fr; gap:30px;">
            <!-- LEFT: VIDEO ONLY -->
            <div>
                {video_block}
                {placeholder_block}

                <div style="background:#1e1e1e; padding:20px; border-radius:15px; margin-top:20px; box-shadow:0 4px 10px rgba(0,0,0,0.3);">
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:20px; border-bottom:1px solid #333; padding-bottom:10px;">
                        <h4 style="margin:0; font-size:1.1em; color:#ddd;">📜 Riwayat Bulanan</h4>
                        <!-- FILTER FORM -->
                        <form method="GET" style="display:flex; gap:10px;">
                            <input type="hidden" name="name" value="{name}">
                            <select name="month" onchange="this.form.submit()" style="background:#2d2d2d; color:#fff; border:1px solid #444; padding:5px 10px; border-radius:6px; cursor:pointer;">
                                {month_opts}
                            </select>
                            <input type="number" name="year" value="{sel_year}" onchange="this.form.submit()" style="background:#2d2d2d; color:#fff; border:1px solid #444; padding:5px 10px; border-radius:6px; width:70px;">
                        </form>
                    </div>
                    
                    <div style="max-height:400px; overflow-y:auto; padding-right:5px;">
                        <table style="width:100%; border-collapse:collapse; font-size:0.9em;">
                            <thead style="position:sticky; top:0; background:#1e1e1e;">
                                <tr style="color:#666; text-transform:uppercase; font-size:0.75em; letter-spacing:1px; border-bottom:2px solid #333;">
                                    <th style="padding:10px; text-align:left;">Tanggal</th>
                                    <th style="padding:10px; text-align:right;">Total Durasi</th>
                                </tr>
                            </thead>
                            <tbody>
                                {history_rows}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>

            <!-- RIGHT: INFO & ATTENDANCE -->
            <div>
                <div class="card" style="border-top: 4px solid var(--accent); position:sticky; top:20px;">
                    <h1 style="margin-bottom:5px; font-size:2em; word-wrap:break-word;">{name}</h1>
                    <div style="color:#888; margin-bottom:20px; font-size:0.9em;">ID: {name}</div>
                    
                    <div style="background:#2d2d2d; padding:15px; border-radius:8px; margin-bottom:20px; text-align:center;">
                        <div style="color:#aaa; font-size:0.9em; text-transform:uppercase; letter-spacing:1px;">Status Terkini</div>
                        <div id="status-display" style="font-size:1.8em; font-weight:bold; margin-top:5px; color:{'#0f0' if is_active else '#fff'}">{status}</div>
                    </div>
                    
                    <!-- SUMMARY CARDS (TODAY) -->
                    <div style="display:grid; grid-template-columns: 1fr 1fr; gap:10px; margin-bottom:10px;">
                        <div style="background:#222; padding:10px; border-radius:5px;">
                            <div style="font-size:0.8em; color:#888;">Log Awal (Hari Ini)</div>
                            <div style="font-size:1.2em; font-weight:bold; color:#0f0;">{first_seen_today}</div>
                        </div>
                        <div style="background:#222; padding:10px; border-radius:5px;">
                            <div style="font-size:0.8em; color:#888;">Total Durasi (Hari Ini)</div>
                            <div style="font-size:1.2em; font-weight:bold; color:#0f0;">{total_duration_today}</div>
                        </div>
                    </div>

                    <div style="display:grid; grid-template-columns: 1fr 1fr; gap:10px; margin-bottom:20px;">
                        <div style="background:#222; padding:10px; border-radius:5px;">
                            <div style="font-size:0.8em; color:#888;">Durasi (Sesi Ini)</div>
                            <div id="duration-display" style="font-size:1.2em; font-weight:bold;">{duration_str}</div>
                        </div>
                        <div style="background:#222; padding:10px; border-radius:5px;">
                            <div style="font-size:0.8em; color:#888;">Terakhir Terlihat</div>
                            <div id="last-seen-display" style="font-size:1.2em; font-weight:bold;">{last_seen_live}</div>
                        </div>
                    </div>

                    <h4 style="border-bottom:1px solid #333; padding-bottom:5px;">Data Profil</h4>
                    <table style="font-size:0.9em; width:100%; margin-bottom:10px;">
                        <tr><td>Face Embedding</td><td style="text-align:right;">✅ Ready</td></tr>
                        <tr><td>Body Vector</td><td style="text-align:right;">{'✅ Ready' if has_body else '❌ Missing'}</td></tr>
                        <tr><td>Last Update</td><td style="text-align:right;">{mod_time}</td></tr>
                    </table>

                    {attendance_section}
                    
                </div>
            </div>
        </div>
        
        <!-- SNAPSHOT MODAL -->
        <div id="snapModal" style="display:none; position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.8); z-index:9999; justify-content:center; align-items:center;">
             <div style="background:#222; padding:20px; border-radius:10px; max-width:80%; max-height:80%; text-align:center; position:relative;">
                <span onclick="closeSnapshot()" style="position:absolute; top:10px; right:15px; color:#fff; font-size:2em; cursor:pointer;">&times;</span>
                <h3 id="modalDate" style="color:#0f0; margin-top:0;">DATE</h3>
                <img id="modalImg" src="" style="max-width:100%; max-height:60vh; border:2px solid #555;">
                <p style="color:#ccc; margin-top:10px;">Bukti Kehadiran (First Seen)</p>
             </div>
        </div>

        <!-- DETAIL LOG MODAL -->
        <div id="detailModal" style="display:none; position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.8); z-index:9999; justify-content:center; align-items:center;">
             <div style="background:#1e1e1e; padding:20px; border-radius:10px; width:600px; max-width:90%; max-height:80vh; overflow-y:auto; position:relative; box-shadow: 0 0 20px #000;">
                <span onclick="closeDetails()" style="position:absolute; top:10px; right:15px; color:#aaa; font-size:2em; cursor:pointer;">&times;</span>
                <h3 id="detailDate" style="color:#fff; border-bottom:1px solid #333; padding-bottom:10px; margin-top:0;">Log Detail</h3>
                
                <table style="width:100%; border-collapse:collapse; font-size:0.9em; color:#ddd;">
                    <thead>
                        <tr style="border-bottom:2px solid #444; text-align:left;">
                            <th style="padding:10px;">Masuk</th>
                            <th style="padding:10px;">Keluar</th>
                            <th style="padding:10px;">Durasi</th>
                            <th style="padding:10px;">Ruang</th>
                        </tr>
                    </thead>
                    <tbody id="detailBody">
                        <!-- JS Injected -->
                    </tbody>
                </table>
             </div>
        </div>

        <!-- REALTIME POLLER & SCRIPTS -->
        <script>
        const dailyData = {daily_details_json};

        function showSnapshot(url, date) {{
            const modal = document.getElementById('snapModal');
            document.getElementById('modalImg').src = url;
            document.getElementById('modalDate').innerText = date;
            modal.style.display = 'flex';
        }}
        function closeSnapshot() {{
            document.getElementById('snapModal').style.display = 'none';
        }}

        function showDetails(date) {{
            const modal = document.getElementById('detailModal');
            const tbody = document.getElementById('detailBody');
            const header = document.getElementById('detailDate');
            
            header.innerText = "Log Detail: " + date;
            tbody.innerHTML = "";
            
            const logs = dailyData[date] || [];
            if(logs.length === 0) {{
                tbody.innerHTML = '<tr><td colspan="4" style="text-align:center; padding:20px;">Tidak ada data detail.</td></tr>';
            }} else {{
                logs.forEach(l => {{
                    const row = `
                    <tr style="border-bottom:1px solid #333;">
                        <td style="padding:10px; color:#0f0;">${{l.in}}</td>
                        <td style="padding:10px;">${{l.out}}</td>
                        <td style="padding:10px; color:#aaa;">${{l.dur}}</td>
                        <td style="padding:10px; color:var(--accent);">${{l.room}}</td>
                    </tr>
                    `;
                    tbody.innerHTML += row;
                }});
            }}
            
            modal.style.display = 'flex';
        }}
        function closeDetails() {{
             document.getElementById('detailModal').style.display = 'none';
        }}

        // Close on click outside
        window.onclick = function(e) {{
            if (e.target.id == 'snapModal') closeSnapshot();
            if (e.target.id == 'detailModal') closeDetails();
        }}

        setInterval(function() {{
            const url = '/api/status?name=' + encodeURIComponent('{name}') + '&t=' + new Date().getTime();
            fetch(url)
            .then(response => response.json())
            .then(data => {{
                // Update Text Elements
                const statusEl = document.getElementById('status-display');
                if (statusEl) {{
                    statusEl.innerText = data.status;
                    statusEl.style.color = data.status.includes('INDOOR') ? '#0f0' : (data.status.includes('OUTDOOR') ? '#fff' : '#aaa');
                }}
                
                if(document.getElementById('duration-display')) document.getElementById('duration-display').innerText = data.duration;
                if(document.getElementById('last-seen-display')) document.getElementById('last-seen-display').innerText = data.last_seen;
                if(document.getElementById('room-display')) document.getElementById('room-display').innerText = data.room;
                if(document.getElementById('loc-display')) document.getElementById('loc-display').innerText = data.room;

                // 🔥 REALTIME HISTORY TABLE UPDATE 🔥
                // 🔥 REALTIME HISTORY TABLE UPDATE 🔥
                if (data.total_duration_today && data.today_date) {{
                     const row = document.getElementById("row-" + data.today_date);
                     if (row) {{
                         // Format HH:MM:SS -> X jam Y menit Z detik
                         const parts = data.total_duration_today.split(":");
                         if (parts.length === 3) {{
                              const fmt = parseInt(parts[0]) + " jam " + parseInt(parts[1]) + " menit " + parseInt(parts[2]) + " detik";
                              if(row.cells[1]) row.cells[1].innerText = fmt;
                         }}
                     }}
                }}

                // Update Video Visibility
                const vidWrapper = document.getElementById('video-wrapper');
                const phWrapper = document.getElementById('placeholder-wrapper');

                if (vidWrapper && phWrapper) {{
                    if (data.is_active) {{
                        vidWrapper.style.display = 'block';
                        phWrapper.style.display = 'none';
                        if(statusEl) statusEl.style.color = '#0f0';
                    }} else {{
                        vidWrapper.style.display = 'none';
                        phWrapper.style.display = 'flex';
                        if(statusEl) statusEl.style.color = '#fff';
                    }}
                }}
            }})
            .catch(err => console.error("Polling Error:", err));
        }}, 1000);
        </script>
        """
        return HTML_TEMPLATE.format(CONTENT=html, ACTIVE_HOME="", ACTIVE_USERS="active", ACTIVE_LOGS="", ACTIVE_SUMMARY="", PORT=PORT)

    def render_users(self, query=None):
        # Lazy import
        try:
            from indoor.presence_manager import presence_manager
        except ImportError:
            presence_manager = None

        users_data = []
        if os.path.exists(EMBED_DIR):
            files = sorted([f for f in os.listdir(EMBED_DIR) if f.endswith('.npy')])
            for f in files:
                name = f.replace(".npy", "")
                if query and query.lower() not in name.lower(): continue
                
                f_path = os.path.join(EMBED_DIR, f)
                mod_time = datetime.fromtimestamp(os.path.getmtime(f_path)).strftime('%Y-%m-%d')
                
                status = "OFFLINE"
                if IS_CAMERA_RUNNING and presence_manager:
                    if presence_manager.is_person_inside_any_room(name): 
                        status = "🟢 INDOOR"
                    elif name in presence_manager.state:
                         st = list(presence_manager.state[name].values())[0] # Pick first room
                         s = st['status']
                         if s == 'OUTDOOR': status = "⚪ OUTDOOR"
                         elif s == 'PENDING': status = "🕒 VERIFYING..."
                         elif s == 'UNKNOWN': status = "❓ CHECKING..."
                         else: status = s
                
                users_data.append({"name": name, "status": status, "updated": mod_time})

        # SEARCH FORM
        html = f"""
        <h2>🔍 User Database</h2>
        <form action="/users" method="GET" class="search-box">
            <input type="text" name="q" placeholder="Search Name..." value="{query or ''}">
            <button type="submit">Filter</button>
            <a href="/users"><button type="button" style="background: #333;">Reset</button></a>
        </form>
        """

        rows = ""
        for i, u in enumerate(users_data):
            # SAFE URL ENCODING for names with spaces
            safe_name = urllib.parse.quote(u['name'])
            rows += f"""
            <tr onclick="window.location='/user_detail?name={safe_name}'" style="cursor:pointer; transition:0.2s;">
                <td>{i+1}</td>
                <td style="font-size:1.1em;"><strong>{u['name']}</strong></td>
                <td>{u['status']}</td>
                <td>{u['updated']}</td>
                <td style="text-align:right;">
                    <a href="/user_detail?name={safe_name}" style="background:var(--accent); color:#000; padding:5px 10px; border-radius:4px; text-decoration:none; font-weight:bold; font-size:0.8em;">VIEW MONITOR &rarr;</a>
                </td>
            </tr>
            """
        
        html += f"""
        <table>
            <thead><tr><th width="40">#</th><th>Name</th><th>Status</th><th>Updated</th><th style="text-align:right;">Action</th></tr></thead>
            <tbody>{rows}</tbody>
        </table>
        """
        return HTML_TEMPLATE.format(CONTENT=html, ACTIVE_HOME="", ACTIVE_USERS="active", ACTIVE_LOGS="", ACTIVE_SUMMARY="", PORT=PORT)

    def render_logs(self, query=None):
        results = ""
        if os.path.exists(LOGS_PATH):
            with open(LOGS_PATH, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
                if query:
                    lines = [l for l in lines if query.lower() in l.lower()]
                results = "".join(lines[-100:])
        
        html = f"""
        <h2>🕵️ System Logs</h2>
        <form action="/logs" method="GET" class="search-box">
            <input type="text" name="q" placeholder="Search logs..." value="{query or ''}">
            <button type="submit">Search</button>
        </form>
        <pre>{results}</pre>
        """
        return HTML_TEMPLATE.format(CONTENT=html, ACTIVE_HOME="", ACTIVE_USERS="", ACTIVE_LOGS="active", ACTIVE_SUMMARY="", PORT=PORT)

    def render_summary(self, mode='all', date_val=None, month_val=None, year_val=None):
        # 1. Defaults
        if not year_val: year_val = str(datetime.now().year)
        if not month_val: month_val = str(datetime.now().month)
        if not date_val: date_val = datetime.now().strftime("%Y-%m-%d")

        # 2. Gather Data
        summary_data = []
        if os.path.exists(EMBED_DIR):
            files = [f for f in os.listdir(EMBED_DIR) if f.endswith('.npy')]
            for f in files:
                name = f.replace(".npy", "")
                
                # Get Stats
                try:
                    _, _, _, _, daily_stats = self.parse_attendance_logs(name)
                except:
                    daily_stats = {}

                total_seconds_filtered = 0
                days_present_filtered = 0
                
                # 3. Apply Filters
                for day_key, data in daily_stats.items():
                    include = False
                    if mode == 'all':
                        include = True
                    elif mode == 'day':
                        if day_key == date_val: include = True
                    elif mode == 'month':
                        # day_key is YYYY-MM-DD
                        if day_key.startswith(f"{year_val}-{int(month_val):02d}"): include = True
                    elif mode == 'year':
                        if day_key.startswith(year_val): include = True
                    
                    if include:
                        total_seconds_filtered += data.get('total_sec', 0)
                        days_present_filtered += 1
                
                avg_seconds = total_seconds_filtered / days_present_filtered if days_present_filtered > 0 else 0
                
                # Format
                m, s = divmod(int(total_seconds_filtered), 60)
                h, m = divmod(m, 60)
                total_dur_fmt = f"{h}h {m}m"
                
                m, s = divmod(int(avg_seconds), 60)
                h, m = divmod(m, 60)
                avg_dur_fmt = f"{h}h {m}m"
                
                # Status (Only show live status if mode is TODAY or ALL)
                status = "-"
                is_today = (mode == 'day' and date_val == datetime.now().strftime("%Y-%m-%d"))
                if mode == 'all' or is_today: 
                    status = "OFFLINE"
                    try:
                        from indoor.presence_manager import presence_manager
                        if IS_CAMERA_RUNNING and presence_manager:
                            if presence_manager.is_person_inside_any_room(name):
                                 status = "🟢 INDOOR"
                    except: pass
                
                summary_data.append({
                    "name": name,
                    "days": days_present_filtered,
                    "total_sec": total_seconds_filtered,
                    "total_str": total_dur_fmt,
                    "avg_str": avg_dur_fmt,
                    "status": status
                })

        # 4. Sort by Total Duration (Desc)
        summary_data.sort(key=lambda x: x['total_sec'], reverse=True)
        
        # 5. Build Table
        rows = ""
        for i, u in enumerate(summary_data):
            rank_style = "font-weight:bold;"
            if i == 0: rank_style += " color:#d4af37;" 
            elif i == 1: rank_style += " color:#c0c0c0;" 
            elif i == 2: rank_style += " color:#cd7f32;" 
            
            rows += f"""
            <tr style="border-bottom:1px solid var(--border-color); transition:0.2s;">
                <td style="padding:15px; {rank_style}">{i+1}</td>
                <td style="padding:15px; font-weight:500;">{u['name']}</td>
                <td style="padding:15px; text-align:center;">{u['days']} Hari</td>
                <td style="padding:15px; text-align:center; font-weight:bold; color:var(--accent);">{u['total_str']}</td>
                <td style="padding:15px; text-align:center; color:#666;">{u['avg_str']}</td>
                <td style="padding:15px; font-size:0.9em;">{u['status']}</td>
            </tr>
            """

        # 6. Filter Controls UI
        month_opts = ""
        for m in range(1, 13):
            sel = "selected" if str(m) == str(month_val) else ""
            month_opts += f'<option value="{m}" {sel}>{calendar.month_name[m]}</option>'

        html = f"""
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:20px;">
            <h2 style="margin:0;">📊 Rekap Data (Summary)</h2>
            
            <form method="GET" action="/summary" style="display:flex; gap:10px; background:var(--card-bg); padding:10px; border-radius:8px; border:1px solid var(--border-color);">
                <select name="mode" id="mode_sel" onchange="updateUI()" style="padding:8px; border-radius:4px; border:1px solid #ccc;">
                    <option value="all" {"selected" if mode=='all' else ""}>Semua Waktu</option>
                    <option value="day" {"selected" if mode=='day' else ""}>Harian</option>
                    <option value="month" {"selected" if mode=='month' else ""}>Bulanan</option>
                    <option value="year" {"selected" if mode=='year' else ""}>Tahunan</option>
                </select>
                
                <span id="input_day" style="display:none;">
                    <input type="date" name="date" value="{date_val}" style="padding:7px; border-radius:4px; border:1px solid #ccc;">
                </span>
                
                <span id="input_month" style="display:none;">
                    <select name="month" style="padding:8px; border-radius:4px; border:1px solid #ccc;">{month_opts}</select>
                </span>
                
                <span id="input_year" style="display:none;">
                    <input type="number" name="year" value="{year_val}" style="width:70px; padding:7px; border-radius:4px; border:1px solid #ccc;">
                </span>
                
                <button type="submit" style="padding:8px 15px;">Filter</button>
            </form>
        </div>

        <script>
        function updateUI() {{
            const mode = document.getElementById('mode_sel').value;
            document.getElementById('input_day').style.display = (mode === 'day') ? 'inline' : 'none';
            document.getElementById('input_month').style.display = (mode === 'month') ? 'inline' : 'none';
            document.getElementById('input_year').style.display = (mode === 'month' || mode === 'year') ? 'inline' : 'none';
        }}
        updateUI(); // Init
        </script>

        <div class="card" style="padding:0; overflow:hidden;">
            <table style="width:100%; border-collapse:collapse;">
                <thead>
                    <tr style="background:var(--accent); color:white;">
                        <th style="padding:15px; width:50px;">Rank</th>
                        <th style="padding:15px; text-align:left;">Nama User</th>
                        <th style="padding:15px; text-align:center;">Total Hadir</th>
                        <th style="padding:15px; text-align:center;">Total Durasi</th>
                        <th style="padding:15px; text-align:center;">Rata-rata / Hari</th>
                        <th style="padding:15px; text-align:left;">Status Saat Ini</th>
                    </tr>
                </thead>
                <tbody>
                    {rows}
                </tbody>
            </table>
        </div>
        """
        return HTML_TEMPLATE.format(CONTENT=html, ACTIVE_HOME="", ACTIVE_USERS="", ACTIVE_LOGS="", ACTIVE_SUMMARY="active", PORT=PORT)

    def do_GET(self):
        if self.path == '/video_feed':
            self.send_response(200)
            self.send_header('Content-type', 'multipart/x-mixed-replace; boundary=frame')
            self.end_headers()
            try:
                while True:
                    with FRAME_LOCK:
                        if LATEST_FRAME is None:
                            time.sleep(0.1)
                            continue
                        frame_data = LATEST_FRAME
                    
                    self.wfile.write(b'--frame\r\n')
                    self.wfile.write(b'Content-Type: image/jpeg\r\n\r\n')
                    self.wfile.write(frame_data)
                    self.wfile.write(b'\r\n')
                    time.sleep(0.04) # ~25 FPS max for web
            except Exception:
                pass
            return

        # 🔥 NEW: USER SPECIFIC FEED 🔥
        if self.path.startswith('/user_feed'):
            self.send_response(200)
            self.send_header('Content-type', 'multipart/x-mixed-replace; boundary=frame')
            self.end_headers()
            
            parsed = urllib.parse.urlparse(self.path)
            q = urllib.parse.parse_qs(parsed.query)
            target_name = q.get('name', [None])[0]

            try:
                while True:
                    if not IS_CAMERA_RUNNING or not CAMERA_SYSTEM:
                        time.sleep(1.0)
                        continue

                    display_data = None

                    # 1. Cari user ada di kamera mana saja
                    active_cams = CAMERA_SYSTEM.find_user_cameras(target_name)
                    
                    with FRAME_LOCK:
                        # Jika user tidak terlihat, atau global frame belum ada
                        if not active_cams or not LATEST_FRAMES_DICT:
                            # Opsional: Tampilkan Global Grid sebagai Fallback 
                            # atau Placeholder Hitam
                            # Kita fallback ke Global Grid biar user tau sistem jalan
                            display_data = LATEST_FRAME 
                        else:
                            # Jika user terlihat di satu atau lebih kamera
                            # Ambil frame dari LATEST_FRAMES_DICT
                            valid_frames_data = []
                            for idx in active_cams:
                                if idx in LATEST_FRAMES_DICT:
                                    valid_frames_data.append(LATEST_FRAMES_DICT[idx])
                            
                            if len(valid_frames_data) == 1:
                                display_data = valid_frames_data[0]
                            elif len(valid_frames_data) > 1:
                                # Jika > 1 kamera, kita harus decode -> hstack -> encode ulang
                                # Ini agak berat, tapi jarang terjadi (overlap area)
                                try:
                                    decoded_frames = []
                                    for fd in valid_frames_data:
                                        nparr = np.frombuffer(fd, np.uint8)
                                        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                                        decoded_frames.append(img)
                                    
                                    combined = np.hstack(decoded_frames)
                                    s, b = cv2.imencode('.jpg', combined, [int(cv2.IMWRITE_JPEG_QUALITY), 60])
                                    if s: display_data = b.tobytes()
                                except:
                                    display_data = LATEST_FRAME
                            else:
                                display_data = LATEST_FRAME

                    if display_data:
                        self.wfile.write(b'--frame\r\n')
                        self.wfile.write(b'Content-Type: image/jpeg\r\n\r\n')
                        self.wfile.write(display_data)
                        self.wfile.write(b'\r\n')
                    
                    time.sleep(0.04)
            except Exception:
                pass
            return

        # 🔥 NEW: SNAPSHOT HANDLER 🔥
        if self.path.startswith('/snapshots/'):
            try:
                rel_path = urllib.parse.unquote(self.path[len('/snapshots/'):])
                if '..' in rel_path:
                    self.send_error(403, "Forbidden")
                    return
                    
                full_path = os.path.join(LOG_DIR, "snapshots", rel_path)
                
                if os.path.exists(full_path):
                    with open(full_path, "rb") as f:
                        img_data = f.read()
                    self.send_response(200)
                    self.send_header('Content-type', 'image/jpeg')
                    self.end_headers()
                    self.wfile.write(img_data)
                else:
                    self.send_error(404, "Snapshot not found")
            except Exception as e:
                print(f"Error serving snapshot: {e}")
                self.send_error(500)
            return

        # API HANDLER
        if self.path.startswith('/api/status'):
            try:
                from indoor.presence_manager import presence_manager
                parsed = urllib.parse.urlparse(self.path)
                query_params = urllib.parse.parse_qs(parsed.query)
                name = query_params.get("name", [None])[0]
                
                # CALCULATE TOTAL DURATION TODAY (Including Live)
                # We reuse parse_attendance_logs to get the accurate summed duration
                try:
                    _, _, _, total_dur_today, _ = self.parse_attendance_logs(name)
                except:
                    total_dur_today = "-"

                resp = {
                    "status": "⚫ OFFLINE", 
                    "room": "-", 
                    "duration": "-", 
                    "is_active": False,
                    "last_seen": "-",
                    "total_duration_today": total_dur_today,
                    "today_date": datetime.now().strftime("%Y-%m-%d")
                }
                
                if name and IS_CAMERA_RUNNING and presence_manager:
                    # Logic same as render_user_detail
                    rooms = presence_manager.get_current_rooms(name)
                    if rooms:
                        resp["status"] = "🟢 INDOOR"
                        resp["room"] = ", ".join(rooms)
                        resp["is_active"] = True
                        if name in presence_manager.state:
                            for r_name, st in presence_manager.state[name].items():
                                if st['status'] == 'INDOOR':
                                    delta = time.time() - st['in_time']
                                    m, s = divmod(int(delta), 60)
                                    h, m = divmod(m, 60)
                                    resp["duration"] = f"{h:02d}:{m:02d}:{s:02d}"
                                    resp["last_seen"] = datetime.fromtimestamp(st['last_seen']).strftime('%H:%M:%S')
                                    break
                    else:
                         if name in presence_manager.state:
                             st = list(presence_manager.state[name].values())[0] # Pick first room
                             s = st['status']
                             if s == 'OUTDOOR': resp["status"] = "⚪ OUTDOOR"
                             elif s == 'PENDING': resp["status"] = "🕒 VERIFYING..."
                             elif s == 'UNKNOWN': resp["status"] = "❓ CHECKING..."
                             else: resp["status"] = s
                             
                             if 'last_seen' in st:
                                 resp["last_seen"] = datetime.fromtimestamp(st['last_seen']).strftime('%H:%M:%S')
                             
                             if "INDOOR" in resp["status"] or "VERIFYING" in resp["status"]:
                                 resp["is_active"] = True

                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(resp).encode("utf-8"))
                return
            except Exception as e:
                self.send_response(500)
                self.end_headers()
            return

        try:
            parsed = urllib.parse.urlparse(self.path)
            query_params = urllib.parse.parse_qs(parsed.query)
            
            if parsed.path == "/": content = self.render_dashboard()
            elif parsed.path == "/users": 
                q = query_params.get("q", [None])[0]
                content = self.render_users(q)
            elif parsed.path == "/user_detail":
                name = query_params.get("name", [None])[0]
                if name: content = self.render_user_detail(name)
                else: content = "Error: No name specified."
            elif parsed.path == "/logs": 
                q = query_params.get("q", [None])[0]
                content = self.render_logs(q)
            elif parsed.path == "/summary":
                mode = query_params.get("mode", ["all"])[0]
                date_val = query_params.get("date", [None])[0]
                month_val = query_params.get("month", [None])[0]
                year_val = query_params.get("year", [None])[0]
                content = self.render_summary(mode, date_val, month_val, year_val)
            else:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"404 Not Found")
                return

            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(content.encode("utf-8"))
        except Exception as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(f"Error: {e}".encode("utf-8"))

    def do_POST(self):
        if self.path == "/start_cam":
            start_camera_system()
            self.send_response(303)
            self.send_header('Location', '/')
            self.end_headers()
        elif self.path == "/stop_cam":
            stop_camera_system()
            self.send_response(303)
            self.send_header('Location', '/')
            self.end_headers()

class ThreadingHTTPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True

if __name__ == "__main__":
    socketserver.TCPServer.allow_reuse_address = True
    print(f"\n✅ SYSTEM ONLINE!")
    print(f"📡 Dashboard running at: http://localhost:{PORT}")
    
    with ThreadingHTTPServer(("", PORT), StreamingHandler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n🛑 Shutting down...")
