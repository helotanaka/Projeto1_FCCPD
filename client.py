# client.py
import json, socket, sys

LINE_SEP = "\n"

def rpc(host, port, payload: dict):
    with socket.create_connection((host, port), timeout=5) as sock:
        f = sock.makefile(mode="rw", encoding="utf-8", newline=LINE_SEP)
        f.write(json.dumps(payload) + LINE_SEP)
        f.flush()
        line = f.readline()
        return json.loads(line)

def main():
    if len(sys.argv) < 4:
        print("Uso:")
        print("  python client.py HOST PORT init '{\"alice\":100000,\"bob\":50000} (crie um json com as contas)'")
        print("  python client.py HOST PORT balance alice")
        print("  python client.py HOST PORT deposit alice 2500")
        print("  python client.py HOST PORT withdraw bob 1000")
        print("  python client.py HOST PORT transfer alice bob 777")
        print("  Valores são em centavos (R$ 1,23 => 123).")
        return

    host, port = sys.argv[1], int(sys.argv[2])
    cmd = sys.argv[3]

    if cmd == "init":
        filename = sys.argv[4]  # nome do arquivo JSON passado no terminal
        with open(filename, "r", encoding="utf-8") as f:
            accounts = json.load(f)  # lê o JSON do arquivo
        print(rpc(host, port, {"cmd":"init_accounts","accounts":accounts}))
    elif cmd == "balance":
        print(rpc(host, port, {"cmd":"balance","user":sys.argv[4]}))
    elif cmd == "deposit":
        print(rpc(host, port, {"cmd":"deposit","user":sys.argv[4],"amount":int(sys.argv[5])}))
    elif cmd == "withdraw":
        print(rpc(host, port, {"cmd":"withdraw","user":sys.argv[4],"amount":int(sys.argv[5])}))
    elif cmd == "transfer":
        print(rpc(host, port, {"cmd":"transfer","from":sys.argv[4],"to":sys.argv[5],"amount":int(sys.argv[6])}))
    elif cmd == "shutdown":
        print(rpc(host, port, {"cmd":"shutdown"}))
    else:
        print("Comando não reconhecido.")

if __name__ == "__main__":
    main()
