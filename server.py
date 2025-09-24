# server.py
import json, socket, threading, uuid, time, os
from typing import Dict, Set

LINE_SEP = "\n"  # protocolo: uma mensagem JSON por linha

class BankServer:
    def __init__(self, host="127.0.0.1", port=5000):
        self.host, self.port = host, port
        self._srv_sock = None

        # ----- Estado do "banco" -----
        self.accounts: Dict[str, int] = {}            # saldo em centavos. Key sempre será string, Value sempre será int.
        self._locks: Dict[str, threading.Lock] = {}   # lock por conta
        self._processed: Set[str] = set()             # idempotência por tx_id. Uma transação por movimento, não podendo ter duplicatas.
        self._global_lock = threading.RLock()         # protege dicionários. Usamos RLock porque vamos precisar que a mesma thread chama o lock novamente.
        self._wal_path = "transactions.log"           # write-ahead log simples
        self._state_path = "state.json"               # snapshot ocasional

        # Para desligamento limpo
        self._shutdown = threading.Event()

        # Cria log se não existir
        if not os.path.exists(self._wal_path):
            with open(self._wal_path, "w", encoding="utf-8") as f:
                f.write("# WAL de transações (JSON por linha)\n")

        # Cria state.json se não existir
        if not os.path.exists(self._state_path):
            with open(self._state_path, "w", encoding="utf-8") as f:
                json.dump({"accounts": {}, "timestamp": time.time()}, f, ensure_ascii=False, indent=2)

    # ---------- utilidades ----------
    def _get_lock(self, user: str) -> threading.Lock:
        with self._global_lock:
            if user not in self._locks:
                self._locks[user] = threading.Lock()
            return self._locks[user]

    def _ensure_account(self, user: str):
        with self._global_lock:
            if user not in self.accounts:
                self.accounts[user] = 0

    def _persist_state(self):
        # snapshot eventual (chame após lotes de mudanças)
        tmp = {"accounts": self.accounts, "timestamp": time.time()}
        with open(self._state_path, "w", encoding="utf-8") as f:
            json.dump(tmp, f, ensure_ascii=False, indent=2)

    def _append_wal(self, entry: dict):
        with open(self._wal_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # ---------- operações de negócio ----------
    def op_init_accounts(self, accounts: Dict[str, int]):
        # Cria/atualiza contas com saldos iniciais (centavos)
        with self._global_lock:
            for u, cents in accounts.items():
                self.accounts[u] = int(cents)
                if u not in self._locks:
                    self._locks[u] = threading.Lock()
        self._persist_state()
        return {"ok": True, "accounts": self.accounts}

    def op_balance(self, user: str):
        self._ensure_account(user)
        with self._get_lock(user):
            return {"ok": True, "user": user, "balance": self.accounts[user]}

    def op_deposit(self, user: str, amount: int, tx_id: str):
        if amount <= 0:
            return {"ok": False, "error": "amount must be > 0"}

        with self._global_lock:
            if tx_id in self._processed:
                return {"ok": True, "duplicate": True}
            self._processed.add(tx_id)

        self._ensure_account(user)
        with self._get_lock(user):
            before = self.accounts[user]
            self.accounts[user] += amount
            after = self.accounts[user]
        self._append_wal({"tx": "deposit", "tx_id": tx_id, "user": user, "amount": amount, "after": after})
        return {"ok": True, "before": before, "after": after}

    def op_withdraw(self, user: str, amount: int, tx_id: str):
        if amount <= 0:
            return {"ok": False, "error": "amount must be > 0"}

        with self._global_lock:
            if tx_id in self._processed:
                return {"ok": True, "duplicate": True}
            self._processed.add(tx_id)

        self._ensure_account(user)
        with self._get_lock(user):
            if self.accounts[user] < amount:
                return {"ok": False, "error": "insufficient funds", "balance": self.accounts[user]}
            before = self.accounts[user]
            self.accounts[user] -= amount
            after = self.accounts[user]
        self._append_wal({"tx": "withdraw", "tx_id": tx_id, "user": user, "amount": amount, "after": after})
        return {"ok": True, "before": before, "after": after}

    def op_transfer(self, from_user: str, to_user: str, amount: int, tx_id: str):
        if amount <= 0:
            return {"ok": False, "error": "amount must be > 0"}
        if from_user == to_user:
            return {"ok": False, "error": "cannot transfer to same account"}

        with self._global_lock:
            if tx_id in self._processed:
                return {"ok": True, "duplicate": True}
            self._processed.add(tx_id)

        # locks em ordem determinística para evitar deadlock
        u1, u2 = sorted([from_user, to_user])
        self._ensure_account(from_user)
        self._ensure_account(to_user)

        l1, l2 = self._get_lock(u1), self._get_lock(u2)
        with l1:
            with l2:
                # agora temos os dois locks; decide débito/crédito
                if self.accounts[from_user] < amount:
                    return {"ok": False, "error": "insufficient funds", "balance": self.accounts[from_user]}
                before_from = self.accounts[from_user]
                before_to   = self.accounts[to_user]
                self.accounts[from_user] -= amount
                self.accounts[to_user]   += amount
                after_from  = self.accounts[from_user]
                after_to    = self.accounts[to_user]

        self._append_wal({
            "tx": "transfer", "tx_id": tx_id,
            "from": from_user, "to": to_user, "amount": amount,
            "after_from": after_from, "after_to": after_to
        })
        return {"ok": True,
                "from": {"user": from_user, "before": before_from, "after": after_from},
                "to":   {"user": to_user,   "before": before_to,   "after": after_to}}

    # ---------- rede ----------
    def _handle_client(self, conn: socket.socket, addr):
        with conn:
            f = conn.makefile(mode="rw", encoding="utf-8", newline=LINE_SEP)
            while not self._shutdown.is_set():
                line = f.readline()
                if not line:
                    break
                try:
                    req = json.loads(line.strip())
                except Exception as e:
                    f.write(json.dumps({"ok": False, "error": f"bad json: {e}"}) + LINE_SEP); f.flush()
                    continue

                cmd = req.get("cmd")
                try:
                    if cmd == "init_accounts":
                        res = self.op_init_accounts(req["accounts"])
                    elif cmd == "balance":
                        res = self.op_balance(req["user"])
                    elif cmd == "deposit":
                        res = self.op_deposit(req["user"], int(req["amount"]), req.get("tx_id") or str(uuid.uuid4()))
                    elif cmd == "withdraw":
                        res = self.op_withdraw(req["user"], int(req["amount"]), req.get("tx_id") or str(uuid.uuid4()))
                    elif cmd == "transfer":
                        res = self.op_transfer(req["from"], req["to"], int(req["amount"]), req.get("tx_id") or str(uuid.uuid4()))
                    elif cmd == "shutdown":
                        self._shutdown.set()
                        res = {"ok": True, "msg": "shutting down"}
                    else:
                        res = {"ok": False, "error": f"unknown cmd '{cmd}'"}
                except KeyError as e:
                    res = {"ok": False, "error": f"missing field: {e}"}
                except Exception as e:
                    res = {"ok": False, "error": f"internal: {e}"}

                f.write(json.dumps(res, ensure_ascii=False) + LINE_SEP)
                f.flush()

    def serve_forever(self):
        self._srv_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._srv_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._srv_sock.bind((self.host, self.port))
        self._srv_sock.listen(64)
        print(f"[server] listening on {self.host}:{self.port}")
        try:
            while not self._shutdown.is_set():
                self._srv_sock.settimeout(1.0)
                try:
                    conn, addr = self._srv_sock.accept()
                except socket.timeout:
                    continue
                threading.Thread(target=self._handle_client, args=(conn, addr), daemon=True).start() # cria threads por cliente
        finally:
            print("[server] closing...")
            try: self._srv_sock.close()
            except: pass
            self._persist_state()

if __name__ == "__main__":
    BankServer().serve_forever()
