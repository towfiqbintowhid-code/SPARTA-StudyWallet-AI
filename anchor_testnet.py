"""OPTIONAL: anchor the audit-log chain head on the Ethereum Sepolia TESTNET (free test coins, no real money).

Why: the hash chain detects edits, but someone could delete the newest entries. Publishing the latest hash
on a public chain gives a timestamped proof that the log looked exactly like this at that moment.

Usage:
  python anchor_testnet.py --dry-run                 # no network, shows what would be written
  export SEPOLIA_RPC_URL=https://ethereum-sepolia-rpc.publicnode.com
  export ANCHOR_PRIVATE_KEY=0x...                    # a THROWAWAY test wallet only, never a real one
  pip install web3
  python anchor_testnet.py                           # sends 1 tx, prints tx hash + explorer link
The tx hash is appended to evidence/onchain_anchor.txt (use it as extra execution evidence).
"""
import os, sys, time, pathlib, json
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import tools, agent

def build_ledger():
    lg = tools.Ledger()
    for q in ["What's my balance?", "send 3000 to Dorm Landlord", "send 9000 to Dorm Landlord"]:
        agent.run_agent(q, [], lg)
    for code in list(lg.pending): tools.confirm_transfer(code, lg)
    return lg

def main():
    lg = build_ledger(); head = lg._entries[-1]["hash"]
    assert lg.verify_integrity(), "chain invalid, refusing to anchor"
    payload = ("studywallet-audit-head:" + head).encode()
    print("Entries:", len(lg._entries), "\nChain head:", head, "\nPayload:", payload.decode())
    if "--dry-run" in sys.argv: print("Dry run only, nothing sent."); return
    from web3 import Web3
    w3 = Web3(Web3.HTTPProvider(os.environ["SEPOLIA_RPC_URL"])); acct = w3.eth.account.from_key(os.environ["ANCHOR_PRIVATE_KEY"])
    tx = {"to": acct.address, "value": 0, "data": payload, "nonce": w3.eth.get_transaction_count(acct.address),
          "chainId": 11155111, "gas": 60000, "maxFeePerGas": w3.eth.gas_price * 2, "maxPriorityFeePerGas": w3.to_wei(1, "gwei")}
    signed = acct.sign_transaction(tx); h = w3.to_hex(w3.eth.send_raw_transaction(signed.raw_transaction))   # always '0x...'.
    w3.eth.wait_for_transaction_receipt(h, timeout=180)
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} head={head} tx={h} https://sepolia.etherscan.io/tx/{h}"
    out = pathlib.Path(__file__).parent / "evidence"; out.mkdir(exist_ok=True)
    with open(out / "onchain_anchor.txt", "a") as f: f.write(line + "\n")
    print(line)

if __name__ == "__main__": main()
