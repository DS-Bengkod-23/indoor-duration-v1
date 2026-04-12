# indoor/presence_manager.py
# ============================================================
# PRESENCE MANAGER (FINAL – STABLE, ANTI SALAH SESAAT)
# ------------------------------------------------------------
# - Presence berbasis ROOM NAME (bukan kamera)
# - Kamera berbeda tapi room sama = tetap INDOOR
# - Grace time untuk cegah flip-flop antar kamera
# - FALSE detection singkat TIDAK masuk log
# - Log hanya dibuat saat status BENAR-BENAR stabil
# ============================================================
import time
import os
import cv2  # Added for image saving
import threading # Added for async I/O
from typing import Dict, List, Set, Optional, Any # Added Any for frame
from config.settings import SETTINGS
from config.paths import LOG_DIR


class PresenceManager:
    """
    Presence state machine (FINAL STABLE):
      - Status: PENDING → INDOOR → UNKNOWN → OUTDOOR
      - Key utama: room_name (bukan CAM_X)
      - PENDING mencegah salah log karena mis-prediksi sesaat
    """

    def __init__(self):
        self.timeout: float = SETTINGS.get("presence_timeout", 30.0)
        self.unknown_to_outdoor: float = SETTINGS.get("unknown_to_outdoor", 10.0)
        self.room_mapping: Dict[str, str] = SETTINGS.get("room_mapping", {})
        self.default_room_name: str = SETTINGS.get(
            "default_room_name", "Ruangan Tidak Dikenal"
        )

        # grace time antar kamera (detik)
        self.grace_move: float = 2.5

        # 🔑 MINIMAL waktu agar kehadiran dianggap valid (ANTI SALAH SESUAT)
        self.min_presence_time: float = 3.0

        # state:
        # person_id -> room_name -> {
        #   in_time, last_seen, status, log_index
        # }
        self.state: Dict[str, Dict[str, Dict]] = {}

        # history logs
        self.logs: List[Dict] = []
        
        # Ensure snapshot directory
        self.snap_dir = os.path.join(LOG_DIR, "snapshots")
        if not os.path.exists(self.snap_dir):
            os.makedirs(self.snap_dir)

    # ---------------------------------------------------------
    # helpers
    # ---------------------------------------------------------
    def _room_name(self, room_id: str) -> str:
        return self.room_mapping.get(room_id, self.default_room_name)

    def _fmt_time(self, ts: Optional[float]) -> str:
        if ts is None:
            return "--:--:--"
        return time.strftime("%H:%M:%S", time.localtime(ts))
        
    def _save_snapshot(self, person_id: str, frame):
        """Save a snapshot for proof of presence if not exists for today."""
        if frame is None: return
        
        try:
            today = time.strftime('%Y-%m-%d')
            user_dir = os.path.join(self.snap_dir, person_id)
            if not os.path.exists(user_dir):
                os.makedirs(user_dir)
                
            filename = os.path.join(user_dir, f"{today}.jpg")
            
            # Only save if not already exists (Proof of FIRST presence)
            if not os.path.exists(filename):
                # 🔥 ASYNC I/O GUARD 🔥
                # Lempar proses simpan HDD ke belakang agar Kamera tak Freeze.
                def save_img():
                    try: cv2.imwrite(filename, frame)
                    except: pass
                
                threading.Thread(target=save_img, daemon=True).start()
                print(f"[SNAPSHOT] Memulai Background Save {person_id} ke {filename}")
        except Exception as e:
            print(f"[ERROR] Failed to init snapshot async thread: {e}")

    def _print_log(self, idx: int):
        log = self.logs[idx]
        msg = (
            f"{idx+1}. {log['person_id']} | {log['room_id']} | "
            f"{self._fmt_time(log['in_time'])} → {self._fmt_time(log['out_time'])} | "
            f"{log['room_name']} | {log['status']}"
        )
        print(msg)
        
        # WRITE TO FILE
        # 🔥 FIX: Hanya tulis ke file jika sesi SELESAI (OUTDOOR/UNKNOWN)
        # Ini mencegah duplikasi log pendek saat baru masuk.
        if log['status'] != "INDOOR":
            try:
                # Tambahkan Tanggal [YYYY-MM-DD] untuk parsing yang lebih baik
                file_msg = f"[{time.strftime('%Y-%m-%d')}] {msg}\n"
                
                # 🔥 ASYNC I/O GUARD 🔥
                # Tulis file secara paralel tanpa nge-block Stream Video.
                def append_log():
                    with open(os.path.join(LOG_DIR, "system.log"), "a", encoding="utf-8") as f:
                        f.write(file_msg)
                
                threading.Thread(target=append_log, daemon=True).start()
            except Exception as e:
                print(f"[ERROR] Gagal execute log async: {e}")

    def _append_log(
        self,
        person_id: str,
        room_id: str,
        room_name: str,
        in_time: float,
        out_time: float,
        status: str,
    ) -> int:
        log = {
            "person_id": person_id,
            "room_id": room_id,
            "room_name": room_name,
            "in_time": in_time,
            "out_time": out_time,
            "status": status,
        }
        idx = len(self.logs)
        self.logs.append(log)
        print(f"[PRESENCE] {status}")
        self._print_log(idx)
        return idx

    def _update_out_time(self, idx: int, out_time: float):
        if idx is None or idx < 0 or idx >= len(self.logs):
            return
        self.logs[idx]["out_time"] = out_time

    def update_presence(self, room_id: str, active_ids: Any, now: float, frame=None):
        """
        room_id   : CAM_0, CAM_1, ...
        active_ids: Set[str] OR Dict[str, float] (Name -> Start Time)
        active_ids: set person_id hasil tracker (SUDAH STABIL)
        frame     : current frame for snapshot (optional)
        """

        room_name = self._room_name(room_id)
        
        # Handle Dict input (Retroactive) vs Set input (Legacy)
        active_map = {}
        if isinstance(active_ids, dict):
            active_names = set(active_ids.keys())
            active_map = active_ids
        else:
            active_names = set(active_ids)

        # ======================================================
        # UPDATE / CREATE STATES
        # ======================================================
        for pid in active_names:
            rooms = self.state.setdefault(pid, {})

            active_room = None
            active_state = None
            for rname, st in rooms.items():
                if st["status"] in ("INDOOR", "PENDING"):
                    active_room = rname
                    active_state = st
                    break

            # ==================================================
            # KASUS 1: BELUM ADA RUANG AKTIF → MASUK PENDING
            # ==================================================
            if active_room is None:
                # 🔥 RETROACTIVE LOGIC: Use original start time if available
                start_time = active_map.get(pid, now)
                
                rooms[room_name] = {
                    "in_time": start_time,
                    "last_seen": now, # Last seen tetap NOW agar tidak timeout
                    "status": "PENDING",
                    "log_index": None,
                }
                continue


            # ==================================================
            # KASUS 2: MASIH DI RUANG YANG SAMA
            # ==================================================
            if active_room == room_name:
                active_state["last_seen"] = now

                if active_state["status"] == "INDOOR":
                    self._update_out_time(active_state["log_index"], now)

                continue

            # ==================================================
            # KASUS 3: PINDAH RUANG (CEK GRACE TIME)
            # ==================================================
            delta = now - active_state["last_seen"]
            if delta < self.grace_move:
                if active_state["status"] == "INDOOR":
                    self._update_out_time(active_state["log_index"], now)
                continue

            # ==================================================
            # PINDAH RUANG VALID
            # ==================================================
            if active_state["status"] == "INDOOR":
                self._append_log(
                    pid,
                    room_id,
                    active_room,
                    active_state["in_time"],
                    active_state["last_seen"],
                    "OUTDOOR",
                )

            active_state["status"] = "OUTDOOR"

            rooms[room_name] = {
                "in_time": now,
                "last_seen": now,
                "status": "PENDING",
                "log_index": None,
            }

        # ======================================================
        # PENDING → INDOOR (HANYA JIKA STABIL)
        # ======================================================
        for pid, rooms in self.state.items():
            for rname, st in rooms.items():
                if st["status"] == "PENDING":
                    if now - st["in_time"] >= self.min_presence_time:
                        idx = self._append_log(
                            pid,
                            rname,
                            rname,
                            st["in_time"],
                            now,
                            "INDOOR",
                        )
                        st["status"] = "INDOOR"
                        st["log_index"] = idx
                        
                        # SAVE SNAPSHOT (Proof of Presence)
                        if frame is not None:
                            self._save_snapshot(pid, frame)

        # ======================================================
        # TIMEOUT HANDLING
        # ======================================================
        for pid, rooms in self.state.items():
            for rname, st in rooms.items():
                if st["status"] == "INDOOR":
                    if now - st["last_seen"] >= self.timeout:
                        idx = self._append_log(
                            pid,
                            rname,
                            rname,
                            st["in_time"],
                            st["last_seen"],
                            "UNKNOWN",
                        )
                        st["status"] = "UNKNOWN"
                        st["log_index"] = idx

                elif st["status"] == "UNKNOWN":
                    if now - st["last_seen"] >= self.unknown_to_outdoor:
                        idx = self._append_log(
                            pid,
                            rname,
                            rname,
                            st["in_time"],
                            st["last_seen"],
                            "OUTDOOR",
                        )
                        st["status"] = "OUTDOOR"
                        st["log_index"] = idx

    # ---------------------------------------------------------
    # shutdown flush
    # ---------------------------------------------------------
    def flush_all(self, now: float):
        for pid, rooms in self.state.items():
            for rname, st in rooms.items():
                if st["status"] in ("INDOOR", "UNKNOWN"):
                    self._append_log(
                        pid,
                        rname,
                        rname,
                        st["in_time"],
                        st["last_seen"],
                        "OUTDOOR",
                    )
                    st["status"] = "OUTDOOR"

    # ---------------------------------------------------------
    # helpers for API/UI
    # ---------------------------------------------------------
    def get_logs(self) -> List[Dict]:
        return list(self.logs)

    def print_logs(self):
        print("===== PRESENCE LOGS =====")
        for i in range(len(self.logs)):
            self._print_log(i)
        print("=========================")

    def is_person_inside_any_room(self, person_id: str) -> bool:
        for st in self.state.get(person_id, {}).values():
            if st["status"] == "INDOOR":
                return True
        return False

    def get_current_rooms(self, person_id: str) -> List[str]:
        return [
            r
            for r, st in self.state.get(person_id, {}).items()
            if st["status"] == "INDOOR"
        ]

    def start_tentative(self, person_id: str, now: float):
        """
        Dipanggil saat AI mulai ragu (fail_count > 0 tapi belum > 3).
        Catat waktu mulai ragu sebagai 'tentative_start' tanpa mengubah apapun.
        Waktu tetap berjalan seperti biasa.
        """
        for rooms in self.state.get(person_id, {}).values():
            if rooms["status"] == "INDOOR" and "tentative_start" not in rooms:
                rooms["tentative_start"] = now
                print(f"[TENTATIVE] {person_id} mulai diragukan sejak {self._fmt_time(now)}")

    def confirm_tentative(self, person_id: str):
        """
        Dipanggil saat AI mengkonfirmasi identitas benar kembali.
        Hapus marker ragu — waktu selama ragu otomatis terhitung karena out_time terus update.
        """
        for rooms in self.state.get(person_id, {}).values():
            if rooms["status"] == "INDOOR" and "tentative_start" in rooms:
                del rooms["tentative_start"]
                print(f"[TENTATIVE] {person_id} dikonfirmasi BENAR. Durasi tetap dihitung.")

    def reject_tentative(self, person_id: str):
        """
        Dipanggil saat AI memutuskan identitas SALAH (drop ke oranye).
        Rollback out_time ke sebelum periode ragu — waktu selama ragu dibuang.
        """
        for rooms in self.state.get(person_id, {}).values():
            if rooms["status"] == "INDOOR":
                tentative_start = rooms.pop("tentative_start", None)
                if tentative_start is not None:
                    self._update_out_time(rooms["log_index"], tentative_start)
                    print(f"[TENTATIVE] {person_id} terbukti SALAH. Durasi di-rollback ke {self._fmt_time(tentative_start)}")

# singleton
presence_manager = PresenceManager()
