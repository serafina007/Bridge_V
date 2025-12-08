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

    # Load scanned chain contract info
    info = get_contract_info(chain, contract_info)
    contract_address = Web3.to_checksum_address(info["address"])
    contract = w3.eth.contract(address=contract_address, abi=info["abi"])

    # Scan last 5 blocks
    latest = w3.eth.block_number
    start = max(0, latest - 5)

    try:
        events = contract.events.Transfer().get_logs(fromBlock=start, toBlock=latest)
    except Exception as e:
        print(f"No Transfer events found on {chain} chain: {e}")
        return

    if not events:
        print(f"No Transfer events on {chain} ({start} → {latest})")
        return

    # Determine target chain
    target_chain = "destination" if chain == "source" else "source"
    w3t = connect_to(target_chain)
    tgt_info = get_contract_info(target_chain, contract_info)
    tgt_contract = w3t.eth.contract(address=tgt_info["address"], abi=tgt_info["abi"])

    # Warden signing account
    warden_sk = int(tgt_info["warden_sk"], 16)
    warden_acct = w3t.eth.account.from_key(warden_sk)
    w3t.eth.default_account = warden_acct.address

    # Process events
    for e in events:
        sender = e["args"]["from"]
        recipient = e["args"]["to"]
        amount = e["args"]["value"]

        # ---------- SOURCE → DESTINATION (mint) ----------
        if chain == "source" and recipient.lower() == contract_address.lower():
            tx = tgt_contract.functions.mint(sender, amount).build_transaction({
                "from": warden_acct.address,
                "nonce": w3t.eth.get_transaction_count(warden_acct.address),
                "gas": 500_000,
                "gasPrice": w3t.eth.gas_price
            })
            signed_tx = w3t.eth.account.sign_transaction(tx, private_key=warden_sk)
            tx_hash = w3t.eth.send_raw_transaction(signed_tx.rawTransaction)
            print(f"[BRIDGE] mint sent → {tx_hash.hex()}")
            return 1  # Important: only process one event at a time

        # ---------- DESTINATION → SOURCE (withdraw) ----------
        if chain == "destination" and sender.lower() == tgt_info["address"].lower():
            tx = tgt_contract.functions.withdraw(recipient, amount).build_transaction({
                "from": warden_acct.address,
                "nonce": w3t.eth.get_transaction_count(warden_acct.address),
                "gas": 500_000,
                "gasPrice": w3t.eth.gas_price
            })
            signed_tx = w3t.eth.account.sign_transaction(tx, private_key=warden_sk)
            tx_hash = w3t.eth.send_raw_transaction(signed_tx.rawTransaction)
            print(f"[BRIDGE] withdraw sent → {tx_hash.hex()}")
            return 1
