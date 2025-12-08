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

    # Load contract info for the scanned chain
    info = get_contract_info(chain, contract_info)
    src_address = info["address"]
    src_abi = info["abi"]
    src_contract = w3.eth.contract(address=src_address, abi=src_abi)

    # Scan last 5 blocks
    latest = w3.eth.get_block_number()
    start = max(0, latest - 5)

    if chain == "source":
        event_type = "Deposit"
    else:
        event_type = "Unwrap"

    try:
        event_filter = getattr(src_contract.events, event_type).create_filter(
            from_block=start,
            to_block=latest
        )
        events = event_filter.get_all_entries()
    except:
        print(f"No {event_type} event type present in ABI on {chain}")
        return

    if not events:
        print(f"No {event_type} events found on {chain} ({start} → {latest})")
        return

    # Determine target chain
    target_chain = "destination" if chain == "source" else "source"

    # Connect to the target chain
    w3t = connect_to(target_chain)

    # Load target chain contract info
    tgt = get_contract_info(target_chain, contract_info)
    tgt_address = tgt["address"]
    tgt_abi = tgt["abi"]
    tgt_contract = w3t.eth.contract(address=tgt_address, abi=tgt_abi)

    # Warden signing
    warden_sk = int(tgt["warden_sk"], 16)
    acct = w3t.eth.account.from_key(warden_sk)

    # -------- PROCESS EVENTS --------
    for e in events:

        # ============ SOURCE → DESTINATION (wrap) ============
        if chain == "source":    
            token = e["args"]["token"]
            recip = e["args"]["recipient"]
            amount = e["args"]["amount"]

            tx = tgt_contract.functions.wrap(token, recip, amount).build_transaction({
                "from": acct.address,
                "nonce": w3t.eth.get_transaction_count(acct.address),
                "gas": 500_000,
                "gasPrice": w3t.eth.gas_price
            })
            signed = w3t.eth.account.sign_transaction(tx, warden_sk)
            txh = w3t.eth.send_raw_transaction(signed.rawTransaction)
            print(f"[BRIDGE] wrap sent → {txh.hex()}")
            return 1   # important: do NOT reprocess multiple events

        # ============ DESTINATION → SOURCE (withdraw) ============
        else:
            wtoken = e["args"]["wrappedToken"]
            recip  = e["args"]["recipient"]
            amount = e["args"]["amount"]

            tx = tgt_contract.functions.withdraw(wtoken, recip, amount).build_transaction({
                "from": acct.address,
                "nonce": w3t.eth.get_transaction_count(acct.address),
                "gas": 500_000,
                "gasPrice": w3t.eth.gas_price
            })
            signed = w3t.eth.account.sign_transaction(tx, warden_sk)
            txh = w3t.eth.send_raw_transaction(signed.rawTransaction)
            print(f"[BRIDGE] withdraw sent → {txh.hex()}")
            return 1
