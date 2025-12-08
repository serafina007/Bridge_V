from web3 import Web3
from web3.providers.rpc import HTTPProvider
from web3.middleware import ExtraDataToPOAMiddleware #Necessary for POA chains
from datetime import datetime
import json
import pandas as pd


def connect_to(chain):
    if chain == 'source':  # The source contract chain is avax
        api_url = f"https://api.avax-test.network/ext/bc/C/rpc" #AVAX C-chain testnet

    if chain == 'destination':  # The destination contract chain is bsc
        api_url = f"https://data-seed-prebsc-1-s1.binance.org:8545/" #BSC testnet

    if chain in ['source','destination']:
        w3 = Web3(Web3.HTTPProvider(api_url))
        # inject the poa compatibility middleware to the innermost layer
        w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    return w3


def get_contract_info(chain, contract_info):
    """
        Load the contract_info file into a dictionary
        This function is used by the autograder and will likely be useful to you
    """
    try:
        with open(contract_info, 'r')  as f:
            contracts = json.load(f)
    except Exception as e:
        print( f"Failed to read contract info\nPlease contact your instructor\n{e}" )
        return 0
    return contracts[chain]



def scan_blocks(chain, contract_info="contract_info.json"):
    """
        chain - (string) should be either "source" or "destination"
        Scan the last 5 blocks of the source and destination chains
        Look for 'Deposit' events on the source chain and 'Unwrap' events on the destination chain
        When Deposit events are found on the source chain, call the 'wrap' function the destination chain
        When Unwrap events are found on the destination chain, call the 'withdraw' function on the source chain
    """

    # This is different from Bridge IV where chain was "avax" or "bsc"
    if chain not in ['source','destination']:
        print( f"Invalid chain: {chain}" )
        return 0
    
    #YOUR CODE HERE
    w3 = connect_to(chain)

    # load contract
    info = get_contract_info(chain, contract_info)
    bridge_addr = info["address"].lower()
    abi = info["abi"]
    bridge = w3.eth.contract(address=info["address"], abi=abi)

    # scan last 5 blocks
    latest = w3.eth.block_number
    start = max(0, latest - 5)

    # --- instead of Deposit/Unwrap, scan ALL logs ---
    try:
        events = bridge.events.Transfer().get_logs(
            fromBlock=start,
            toBlock=latest
        )
    except:
        print(f"No Transfer event in ABI on {chain}")
        return

    if not events:
        print(f"No Transfer events on {chain} ({start}→{latest})")
        return

    # determine counterpart
    other = "destination" if chain == "source" else "source"
    w3o = connect_to(other)
    tgt = get_contract_info(other, contract_info)
    tgt_addr = tgt["address"]
    tgt_abi = tgt["abi"]
    wrapped = w3o.eth.contract(address=tgt_addr, abi=tgt_abi)

    # warden signs
    warden = w3o.eth.account.from_key(int(tgt["warden_sk"], 16))

    for ev in events:
        args = ev["args"]
        sender = args["from"].lower()
        receiver = args["to"].lower()
        amount = args["value"]

        # ===================== SOURCE → DEST =====================
        if chain == "source" and receiver == bridge_addr:

            tx = wrapped.functions.mint(sender, amount).build_transaction({
                "nonce": w3o.eth.get_transaction_count(warden.address),
                "gas": 500_000,
                "from": warden.address,
                "gasPrice": w3o.eth.gas_price
            })
            signed = warden.sign_transaction(tx)
            txh = w3o.eth.send_raw_transaction(signed.rawTransaction)
            print(f"[BRIDGE] Mint on {other}: {txh.hex()}")
            return 1

        # ===================== DEST → SOURCE =====================
        if chain == "destination" and sender == bridge_addr:

            tx = wrapped.functions.withdraw(sender, amount).build_transaction({
                "nonce": w3o.eth.get_transaction_count(warden.address),
                "gas": 500_000,
                "from": warden.address,
                "gasPrice": w3o.eth.gas_price
            })
            signed = warden.sign_transaction(tx)
            txh = w3o.eth.send_raw_transaction(signed.rawTransaction)
            print(f"[BRIDGE] Burn on {other}: {txh.hex()}")
            return 1
