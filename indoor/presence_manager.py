# indoor/presence_manager.py
# ============================================================
# PRESENCE MANAGER (FINAL – ANTI SPAM, ROOM-AWARE)
# ------------------------------------------------------------
# - Presence berbasis ROOM NAME (bukan kamera)
# - Kamera berbeda tapi room sama = tetap INDOOR
# - Grace time untuk cegah flip-flop antar kamera
# - Log hanya dibuat saat status BENAR-BENAR berubah
# ============================================================

import time
from typing import Dict, List, Set, Optional
from config.settings import SETTINGS


class PresenceManager:
    """
    Presence state machine (FINAL):
      - Status: INDOOR -> UNKNOWN -> OUTDOOR
      - Key utama: room_name (bukan CAM_X)
      - Grace window untuk perpindahan antar kamera
      - Anti spam log
    """

    def __init__(self):
        self.timeout: float = SETTINGS.get("presence_timeout", 10.0)
        self.unknown_to_outdoor: float = SETTINGS.get("unknown_to_outdoor", 10.0)
        self.room_mapping: Dict[str, str] = SETTINGS.get("room_mapping", {})
        self.default_room_name: str = SETTINGS.get(
            "default_room_name", "Ruangan Tidak Dikenal"
        )

        # grace time anti flip-flop (detik)
        self.grace_move: float = 2.5

        # state:
        # person_id -> room_name -> {
        #   in_time, last_seen, status, log_index
        # }
        self.state: Dict[str, Dict[str, Dict]] = {}

        # history logs
        self.logs: List[Dict] = []

    # ---------------------------------------------------------
    # helpers
    # ---------------------------------------------------------
    def _room_name(self, room_id: str) -> str:
        return self.room_mapping.get(room_id, self.default_room_name)

    def _fmt_time(self, ts: Optional[float]) -> str:
        if ts is None:
            return "--:--:--"
        return time.strftime("%H:%M:%S", time.localtime(ts))

    def _print_log(self, idx: int):
        log = self.logs[idx]
        print(
            f"{idx+1}. {log['person_id']} | {log['room_id']} | "
            f"{self._fmt_time(log['in_time'])} → {self._fmt_time(log['out_time'])} | "
            f"{log['room_name']} | {log['status']}"
        )

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

    # ---------------------------------------------------------
    # core update (dipanggil dari VideoSystem)
    # ---------------------------------------------------------
    def update_presence(self, room_id: str, active_ids: Set[str], now: float):
        """
        room_id   : CAM_0, CAM_1, ...
        active_ids: set person_id hasil tracker (SUDAH share ID)
        """

        room_name = self._room_name(room_id)
        active_ids = set(active_ids)

        for pid in active_ids:
            rooms = self.state.setdefault(pid, {})

            # cari ruangan INDOOR aktif (jika ada)
            active_room = None
            active_state = None
            for rname, st in rooms.items():
                if st["status"] == "INDOOR":
                    active_room = rname
                    active_state = st
                    break

            # ==================================================
            # KASUS 1: BELUM ADA RUANG AKTIF
            # ==================================================
            if active_room is None:
                idx = self._append_log(
                    pid, room_id, room_name, now, now, "INDOOR"
                )
                rooms[room_name] = {
                    "in_time": now,
                    "last_seen": now,
                    "status": "INDOOR",
                    "log_index": idx,
                }
                continue

            # ==================================================
            # KASUS 2: MASIH DI RUANG YANG SAMA
            # ==================================================
            if active_room == room_name:
                active_state["last_seen"] = now
                self._update_out_time(active_state["log_index"], now)
                continue

            # ==================================================
            # KASUS 3: TERDETEKSI DI RUANG LAIN
            # → cek grace time
            # ==================================================
            delta = now - active_state["last_seen"]
            if delta < self.grace_move:
                # masih dianggap ruangan lama
                self._update_out_time(active_state["log_index"], now)
                continue

            # ==================================================
            # BENAR-BENAR PINDAH RUANG
            # ==================================================
            # tutup ruangan lama
            self._append_log(
                pid,
                room_id,
                active_room,
                active_state["in_time"],
                active_state["last_seen"],
                "OUTDOOR",
            )
            active_state["status"] = "OUTDOOR"

            # buka ruangan baru
            idx = self._append_log(
                pid, room_id, room_name, now, now, "INDOOR"
            )
            rooms[room_name] = {
                "in_time": now,
                "last_seen": now,
                "status": "INDOOR",
                "log_index": idx,
            }

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


# singleton
presence_manager = PresenceManager()
