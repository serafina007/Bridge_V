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
    info = get_contract_info(chain, contract_info)
    
    contract = w3.eth.contract(
        address=Web3.to_checksum_address(info["address"]),
        abi=info["abi"]
    )
    
    latest_block = w3.eth.get_block_number()
    start_block = max(0, latest_block - 5)
    
    # Event type
    event_name = "Deposit" if chain == "source" else "Unwrap"
    
    try:
        event_filter = getattr(contract.events, event_name).create_filter(
            from_block=start_block, to_block=latest_block
        )
        events = event_filter.get_all_entries()
    except Exception:
        print(f"No {event_name} event in ABI on {chain}")
        return
    
    if not events:
        print(f"No {event_name} events found on {chain} ({start_block} → {latest_block})")
        return
    
    # Determine target chain
    target_chain = "destination" if chain == "source" else "source"
    w3_target = connect_to(target_chain)
    tgt_info = get_contract_info(target_chain, contract_info)
    tgt_contract = w3_target.eth.contract(
        address=Web3.to_checksum_address(tgt_info["address"]),
        abi=tgt_info["abi"]
    )
    
    # Warden account
    warden_sk = int(tgt_info["warden_sk"], 16)
    warden_acct = w3_target.eth.account.from_key(warden_sk)
    
    # Process events
    for e in events:
        if chain == "source":  # Deposit → wrap
            token = e["args"]["token"]
            recipient = e["args"]["recipient"]
            amount = e["args"]["amount"]
            
            tx = tgt_contract.functions.wrap(token, recipient, amount).build_transaction({
                "from": warden_acct.address,
                "nonce": w3_target.eth.get_transaction_count(warden_acct.address),
                "gas": 500_000,
                "gasPrice": w3_target.eth.gas_price
            })
            signed_tx = w3_target.eth.account.sign_transaction(tx, private_key=warden_sk)
            tx_hash = w3_target.eth.send_raw_transaction(signed_tx.rawTransaction)
            print(f"[BRIDGE] wrap called → {tx_hash.hex()}")
        
        else:  # Destination → Source (Unwrap → withdraw)
            wtoken = e["args"]["wrappedToken"]
            recipient = e["args"]["recipient"]
            amount = e["args"]["amount"]
            
            tx = tgt_contract.functions.withdraw(wtoken, recipient, amount).build_transaction({
                "from": warden_acct.address,
                "nonce": w3_target.eth.get_transaction_count(warden_acct.address),
                "gas": 500_000,
                "gasPrice": w3_target.eth.gas_price
            })
            signed_tx = w3_target.eth.account.sign_transaction(tx, private_key=warden_sk)
            tx_hash = w3_target.eth.send_raw_transaction(signed_tx.rawTransaction)
            print(f"[BRIDGE] withdraw called → {tx_hash.hex()}")
        
        # Only process one event at a time to avoid duplicates
        return

# -------- MAIN --------
if __name__ == "__main__":
    scan_blocks("source")       # Scan source for Deposit → wrap
    scan_blocks("destination")
